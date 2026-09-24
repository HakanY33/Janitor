"""Breakeven komisyonu, komisyonun sonuc dagilimi ve `R-ZONE-08` ic validasyonu.

    python -m scripts.bg scripts.robustness

Taban **E3** (`docs/measurements/add_reject_e.md`): D1 + `ADD-REJECT-E` `L = %3`.
Ayrilmis %20 **hicbir bolumde okunmaz** (`train_frac`).

Uc bolum, hepsi ayni tabandan:

**(a) Breakeven komisyonu.** `R-EXIT-01` "sonrasinda stop maliyete cekilir" diyor ve
ayni kural ilk TP'nin alt sinirini "islem ucretlerini karsilayacak kadar" diye veriyor.
Kod bugune kadar breakeven'i **ham** ortalama maliyete koydu: orada kapanan yarinin
bruto sifirdir, odenen gidis-donus komisyonu net zarar kalir. `breakeven_fees` kolu
seviyeyi o komisyon kadar kar tarafina oteler (limit kolunda maker giris + taker cikis
= 7 bps). Slippage **kapsam disi**: yayinlanan bir oran degil, varsayim (§8).

**(b) Komisyon nereye gidiyor.** Islem sonucuna gore (nihai TP / TP1+breakeven / stop /
digeri) islem basina ortalama komisyon ve brut. "Komisyon-negatif" = o sonuc tipinin
ortalama brutu kendi komisyonunu karsilamiyor.

**(c) `R-ZONE-08` bolunmus ic validasyon.** Egitim dilimi zamanda ikiye bolunur. Her
aday ozellik icin islem basina **net bps** gruplanir; once ilk yari, sonra ikinci yari.
Dayanikli = iki yarida da **isaret ayni** ve **>=14/20 sembolde tutarli**.

    Skor kurulmaz, filtre uygulanmaz. Bu betik yalnizca hangi ozelligin dayanikli
    oldugunu **rapor eder**; `R-ZONE-08` agirliklari bu betikten cikmaz.

Tertil ve sembol esikleri **yalnizca ilk yaridan** kesilir ve ikinci yaride aynen
kullanilir: esigin kendisi de modelin bir parcasidir, ikinci yaride yeniden kesilirse
o yari artik dogrulama olmaz.

`bps` tabani **tepe notional**'dir (`tepe miktar x giris fiyati`), giris notional'i
degil: tepe/giris orani ortalama 2,58x (`docs/measurements/tp_placement.md`).
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.levers import olc
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, Trade, load_symbol, reset_for_rerun
from src.backtest.portfolio import LONG
from src.features.structure import DOWN, UP

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 112)
    say(metin)
    say("=" * 112)


# Taban E3 = D1 + ADD-REJECT-E %3 (docs/measurements/add_reject_e.md).
E3_TABANI = {"require_indicator": True, "limit_orders": True,
             "max_adds": 3, "reduce_once": True, "stop_loss_cap": Decimal("0.03")}

SONUC = {"FINAL_TP": "nihai TP", "BREAKEVEN": "TP1 + breakeven", "STOP": "stop"}
"""Islem sonucu -> rapor etiketi. Listede olmayan neden `digeri`ne duser."""


def sonuc_tipi(t: Trade) -> str:
    """Islem sonucu. `STOP`'u TP1'den gecip gecmedigine gore ayirir: TP1 sonrasi
    stop, breakeven seviyesinin **altindan** gecen bir mumdur (bosluk), ayri olaydir."""
    if t.reason == "STOP" and t.reached_tp1:
        return "stop (TP1 sonrasi)"
    return SONUC.get(t.reason, "digeri")


def taban(t: Trade) -> Decimal:
    """`bps` tabani: tepe notional = tepe miktar x giris fiyati."""
    return t.qty * t.entry_price


def net_bps(t: Trade) -> float:
    b = taban(t)
    return float(t.pnl / b * 10_000) if b > 0 else 0.0


# --- (c) aday ozellikler ------------------------------------------------------


@dataclass
class Ozellik:
    """Bir aday ozellik: islemi bir gruba atar, iki grup arasinda karsitlik kurar.

    `sembol_ici=False` sembol seviyesinde bir ozelliktir (her sembol tek grupta olur);
    orada sembol-ici karsitlik hesaplanamaz, tutarlilik farkli tanimlanir (bkz. rapor).
    """

    ad: str
    grup: Callable[[Trade], str]
    a: str  # karsitligin arti tarafi
    b: str  # eksi tarafi
    sembol_ici: bool = True


def _bias_grubu(t: Trade) -> str:
    """R-ZONE-10 · giriste **bilinen** 4h yon pozisyonla uyumlu mu.

    Yon `UP`/`DOWN`/`NONE` (`src/features/structure.py`), taraf `LONG`/`SHORT`:
    `UP` LONG ile, `DOWN` SHORT ile uyumludur. `NONE` uyumsuz degil, **bilinmiyor** —
    ucuncu grup olarak durur ve karsitliga girmez. Bu yon 4h swing yapisindan gelir,
    SMA vekilinden degil (`OPEN-24` kapandi).
    """
    if t.entry_bias not in (UP, DOWN):
        return "yon yok"
    return "uyumlu" if (t.entry_bias == UP) == (t.side == LONG) else "karsi"


def ozellikler(trades: list[Trade], fees: dict) -> list[Ozellik]:
    """Aday ozellikler. Tertil ve sembol esikleri **bu** islem kumesinden kesilir.

    Cagiran ilk yariyi verir; donen `Ozellik` listesi ikinci yaride aynen kullanilir.
    """
    legler = sorted(t.leg_pct for t in trades if t.leg_pct > 0)
    if len(legler) < 3:
        raise ValueError("leg tertili icin yeterli islem yok")
    # Kesim noktalari ilk yaridan; ikinci yaride yeniden kesilmez.
    k1, k2 = legler[len(legler) // 3], legler[2 * len(legler) // 3]

    def leg_grubu(t: Trade) -> str:
        return "alt" if t.leg_pct <= k1 else ("ust" if t.leg_pct > k2 else "orta")

    # Sembol basina tick/leg: fiyat adimi leg'in kacta kaci. Sembol seviyesinde tek
    # sayi (leg medyani), esik semboller arasi medyan.
    oran: dict[str, float] = {}
    per: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.leg_pct > 0 and t.entry_price > 0:
            tick = float(fees[t.symbol].tick)
            leg = t.leg_pct * float(t.entry_price)  # leg, fiyat cinsinden
            if leg > 0:
                per[t.symbol].append(tick / leg)
    for s, v in per.items():
        oran[s] = statistics.median(v)
    esik = statistics.median(oran.values()) if oran else 0.0

    def tick_leg_grubu(t: Trade) -> str:
        v = oran.get(t.symbol)
        return "bilinmiyor" if v is None else ("yuksek" if v > esik else "dusuk")

    say(f"  leg tertil kesimleri (ilk yaridan): alt <= {k1 * 100:.2f}%  "
        f"< orta <= {k2 * 100:.2f}%  < ust")
    say(f"  tick/leg sembol esigi (ilk yaridan): {esik:.5f}  "
        f"(min {min(oran.values(), default=0):.5f} · maks {max(oran.values(), default=0):.5f})")
    return [
        Ozellik("giris dali (OB / FVG)",
                lambda t: "OB" if t.had_ob else ("FVG" if t.had_fvg else "ciplak"),
                "OB", "FVG"),
        Ozellik("4h yapi bias uyumu (R-ZONE-10)", _bias_grubu, "uyumlu", "karsi"),
        Ozellik("touch_count", lambda t: "1" if t.touch_count <= 1 else "2+", "1", "2+"),
        Ozellik("leg buyuklugu tertili", leg_grubu, "ust", "alt"),
        Ozellik("tick/leg orani (sembol)", tick_leg_grubu, "yuksek", "dusuk",
                sembol_ici=False),
    ]


def grupla(trades: list[Trade], o: Ozellik) -> dict[str, list[float]]:
    g: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        g[o.grup(t)].append(net_bps(t))
    return dict(g)


def isaret(x: float) -> int:
    return 0 if x == 0 else (1 if x > 0 else -1)


def tutarlilik(trades: list[Trade], o: Ozellik, delta: float, min_grup: int,
               semboller: list[str]) -> tuple[int, int, int]:
    """(tutarli, olculebilir, toplam sembol).

    Sembol-ici ozellikte: sembolun kendi `A - B` farki havuzun isaretiyle ayni mi.
    Sembol seviyesindeki ozellikte karsitlik sembol **icinde** kurulamaz; orada olcu
    sembolun ortalamasinin havuz ortalamasinin dogru tarafinda olup olmadigidir.
    """
    per: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for t in trades:
        per[t.symbol][o.grup(t)].append(net_bps(t))
    tutarli = olculebilir = 0
    if o.sembol_ici:
        for s in semboller:
            a, b = per[s].get(o.a, []), per[s].get(o.b, [])
            if len(a) < min_grup or len(b) < min_grup:
                continue
            olculebilir += 1
            tutarli += isaret(statistics.mean(a) - statistics.mean(b)) == isaret(delta)
        return tutarli, olculebilir, len(semboller)

    genel = statistics.mean([net_bps(t) for t in trades]) if trades else 0.0
    for s in semboller:
        hepsi = [v for vs in per[s].values() for v in vs]
        gruplar = {g for g in per[s] if per[s][g]}
        if len(hepsi) < min_grup or gruplar not in ({o.a}, {o.b}):
            continue
        olculebilir += 1
        beklenen = isaret(delta) if gruplar == {o.a} else -isaret(delta)
        tutarli += isaret(statistics.mean(hepsi) - genel) == beklenen
    return tutarli, olculebilir, len(semboller)


def yari_raporu(trades: list[Trade], ozs: list[Ozellik], min_grup: int,
                semboller: list[str]) -> dict[str, dict]:
    """Bir yarinin butun ozellik gruplarini yazar; karsitlik ve tutarliligi doner."""
    sonuc: dict[str, dict] = {}
    for o in ozs:
        g = grupla(trades, o)
        say("")
        say(f"  {o.ad}")
        say(f"    {'grup':<16}{'islem':>8}{'pay':>8}{'net bps/islem':>16}"
            f"{'medyan bps':>14}{'kazanan %':>12}")
        n = sum(len(v) for v in g.values()) or 1
        for ad in sorted(g, key=lambda k: -len(g[k])):
            v = g[ad]
            say(f"    {ad:<16}{len(v):>8,}{len(v) / n * 100:>7.1f}%"
                f"{statistics.mean(v):>16.2f}{statistics.median(v):>14.2f}"
                f"{sum(1 for x in v if x > 0) / len(v) * 100:>11.1f}%")
        a, b = g.get(o.a, []), g.get(o.b, [])
        if not a or not b:
            say(f"    karsitlik {o.a} - {o.b}: olculemedi (grup bos)")
            sonuc[o.ad] = {"delta": None, "tutarli": 0, "olculebilir": 0}
            continue
        delta = statistics.mean(a) - statistics.mean(b)
        tut, olc_, top = tutarlilik(trades, o, delta, min_grup, semboller)
        say(f"    karsitlik {o.a} - {o.b} = {delta:+.2f} bps/islem   "
            f"sembol tutarliligi {tut}/{top} (olculebilir {olc_})"
            + ("" if o.sembol_ici else "  [sembol seviyesi olcusu]"))
        sonuc[o.ad] = {"delta": delta, "tutarli": tut, "olculebilir": olc_,
                       "n_a": len(a), "n_b": len(b)}
    return sonuc


def main() -> int:
    p = argparse.ArgumentParser(description="breakeven komisyonu + R-ZONE-08 ic validasyon")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--terminate", default="none")
    p.add_argument("--min-grup", type=int, default=5,
                   help="sembol tutarliliginda grup basina en az islem")
    p.add_argument("--esik", type=int, default=14, help="dayaniklilik icin sembol esigi")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/robustness.txt")
    p.add_argument("--csv", default="logs/robustness.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)

    t0 = time.time()
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        c0 = time.time()
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s:<24} "
              f"{'hazir' if sd is not None else 'ATLANDI':<8} {time.time() - c0:>6.1f} sn",
              file=sys.stderr, flush=True)
    if not data:
        sys.exit("hicbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme = time.time() - t0
    costs = build_cost_model(isimler, a.exchange)

    olculer: dict[str, dict] = {}
    trades: dict[str, list[Trade]] = {}

    def kos(ad: str, aciklama: str, **kw) -> None:
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        # Maliyet modeli her kolda sifirdan: sayaclar ve kalem defteri toplanmasin.
        cm = build_cost_model(isimler, a.exchange)
        res = Backtest(
            data, cm, a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik,
            a.uyari_adds == "evet", progress_every=a.progress_every,
            terminate=a.terminate, **E3_TABANI, **kw,
        ).run()
        olculer[ad] = {"aciklama": aciklama, **olc(res, a.balance)}
        trades[ad] = res.trades
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    kos("E3", "breakeven ham maliyette (bugunku)", breakeven_fees=False)
    kos("E3B", "breakeven gidis-donus komisyonu kadar otelenmis", breakeven_fees=True)
    kollar = ["E3", "E3B"]

    baslik(f"BREAKEVEN KOMISYONU · KOMISYON DAGILIMI · R-ZONE-08  "
           f"spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say("  sembol cikarma yok - ORDI dahil")
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  TABAN = E3: D1 (R-ENTRY-02 (3) kapali - limit emri - TP tam seviyede - "
        "ekleme tavani 3 - kucultme bir kez) + ADD-REJECT-E L = %3")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr} - sonlandirma {a.terminate}")
    say(f"  yukleme {yukleme / 60:.1f} dk")
    say("")
    for k in kollar:
        say(f"  {k:<6} = {olculer[k]['aciklama']}")

    # --- (a) breakeven komisyonu ---------------------------------------------
    baslik("(a) BREAKEVEN KOMISYONU - R-EXIT-01 'islem ucreti dahil' maliyet")
    say("  Ham breakeven kalan yariyi tam ortalama maliyetten kapatir: o yarinin brutu")
    say("  sifir, odenen gidis-donus komisyonu net zarardir. E3B seviyeyi o komisyon")
    say("  kadar kar tarafina oteler (limit kolunda maker giris 2 bps + taker cikis")
    say("  5 bps = 7 bps). Slippage kapsam disi: yayinlanan oran degil, varsayim (§8).")
    say("  Oteleme stopu **erken** tetikler; kar yarisini kucultup stop yarisini")
    say("  buyutebilir. Net etkinin isareti bu iki etkinin toplamidir.")
    say("")
    say(f"  {'olcu':<34}" + "".join(f"{k:>16}" for k in kollar))
    satirlar = [
        ("islem sayisi", lambda m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.2f}"),
        ("komisyon", lambda m: f"{m['komisyon']:,.2f}"),
        ("slippage", lambda m: f"{m['slippage']:,.2f}"),
        ("funding", lambda m: f"{m['funding']:,.2f}"),
        ("NET PnL", lambda m: f"{m['net']:,.2f}"),
        ("net getiri", lambda m: f"{m['net_%']:.1f}%"),
        ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
        ("uzlasma farki", lambda m: f"{m['uzlasma_farki']:.2E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<34}" + "".join(f"{f(olculer[k]):>16}" for k in kollar))
    for ad, anahtar in (("NET PnL farki", "net"), ("brut farki", "brut_slipsiz"),
                        ("komisyon farki", "komisyon")):
        d = olculer["E3B"][anahtar] - olculer["E3"][anahtar]
        say(f"  {ad:<34}{'':>32}{d:>16,.2f}")
    bozuk = [k for k in kollar if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    say("")
    say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. **" if bozuk
        else "  (uzlasma farki Decimal bolme artigi; her kolda kalemler kapaniyor)")
    say("")
    say(f"  {'sonuc dagilimi':<24}" + "".join(f"{k:>16}" for k in kollar))
    tipler = sorted({sonuc_tipi(t) for k in kollar for t in trades[k]})
    for tip in tipler:
        say(f"  {tip:<24}" + "".join(
            f"{sum(1 for t in trades[k] if sonuc_tipi(t) == tip):>16,}" for k in kollar))

    # --- (b) komisyon nereye gidiyor -----------------------------------------
    baslik("(b) KOMISYON NEREYE GIDIYOR - islem sonucuna gore")
    say("  Brut burada islem basina **fiyat** PnL'idir ve slippage dolum fiyatinin")
    say("  icindedir (islem basina ayristirilamaz; kol toplami (a)'da ayri satirda).")
    say("  `komisyon-negatif` = ortalama brut kendi ortalama komisyonunu karsilamiyor.")
    say("  `bps` tabani tepe notional = tepe miktar x giris fiyati.")
    for k in kollar:
        say("")
        say(f"  {k} ({olculer[k]['aciklama']})")
        say(f"    {'sonuc':<24}{'islem':>8}{'pay':>8}{'brut':>12}{'komisyon':>11}"
            f"{'funding':>10}{'net':>12}{'brut-kom':>11}{'kom bps':>10}{'net bps':>10}")
        satir = []
        for tip in tipler:
            g = [t for t in trades[k] if sonuc_tipi(t) == tip]
            if not g:
                continue
            n = len(g)
            brut = sum((t.gross for t in g), Decimal("0")) / n
            kom = sum((t.fees for t in g), Decimal("0")) / n
            fun = sum((t.funding for t in g), Decimal("0")) / n
            net = sum((t.pnl for t in g), Decimal("0")) / n
            kom_bps = statistics.mean([float(t.fees / taban(t) * 10_000)
                                       for t in g if taban(t) > 0])
            nb = statistics.mean([net_bps(t) for t in g])
            isrt = "  <-- komisyon-negatif" if brut < kom else ""
            say(f"    {tip:<24}{n:>8,}{n / len(trades[k]) * 100:>7.1f}%{brut:>12,.2f}"
                f"{kom:>11,.2f}{fun:>10,.2f}{net:>12,.2f}{brut - kom:>11,.2f}"
                f"{kom_bps:>10.1f}{nb:>10.1f}{isrt}")
            satir.append({"kol": k, "sonuc": tip, "islem": n, "brut_ort": brut,
                          "komisyon_ort": kom, "funding_ort": fun, "net_ort": net,
                          "brut_eksi_kom": brut - kom, "komisyon_bps": kom_bps,
                          "net_bps": nb})
        toplam_kom = sum((t.fees for t in trades[k]), Decimal("0"))
        say(f"    {'TUM ISLEMLER':<24}{len(trades[k]):>8,}{100:>7.1f}%"
            f"{sum((t.gross for t in trades[k]), Decimal('0')) / len(trades[k]):>12,.2f}"
            f"{toplam_kom / len(trades[k]):>11,.2f}"
            f"{sum((t.funding for t in trades[k]), Decimal('0')) / len(trades[k]):>10,.2f}"
            f"{sum((t.pnl for t in trades[k]), Decimal('0')) / len(trades[k]):>12,.2f}")
        say(f"    toplam komisyon {toplam_kom:,.2f} · sonuc tipine gore paylar:")
        for tip in tipler:
            g = [t for t in trades[k] if sonuc_tipi(t) == tip]
            if g:
                pay = sum((t.fees for t in g), Decimal("0"))
                say(f"      {tip:<24}{pay:>12,.2f}{pay / toplam_kom * 100:>8.1f}%")
        if k == "E3":
            b_satir = satir

    # --- (c) R-ZONE-08 bolunmus ic validasyon --------------------------------
    baslik("(c) R-ZONE-08 · BOLUNMUS IC VALIDASYON - E3 kolu")
    tr = sorted(trades["E3"], key=lambda t: t.entry_ts)
    kesim = tr[len(tr) // 2].entry_ts
    h1 = [t for t in tr if t.entry_ts < kesim]
    h2 = [t for t in tr if t.entry_ts >= kesim]
    semboller = sorted({t.symbol for t in tr})
    say("  Egitim dilimi zamanda ikiye bolundu; kesim islem sayisini esitleyen an.")
    say(f"  kesim: {kesim:%Y-%m-%d %H:%M} UTC")
    say(f"  ilk yari  {len(h1):>6,} islem  "
        f"{h1[0].entry_ts:%Y-%m-%d} -> {h1[-1].entry_ts:%Y-%m-%d}  "
        f"{len({t.symbol for t in h1})} sembol")
    say(f"  ikinci yari{len(h2):>6,} islem  "
        f"{h2[0].entry_ts:%Y-%m-%d} -> {h2[-1].entry_ts:%Y-%m-%d}  "
        f"{len({t.symbol for t in h2})} sembol")
    say(f"  net bps/islem: ilk yari {statistics.mean([net_bps(t) for t in h1]):+.2f} · "
        f"ikinci yari {statistics.mean([net_bps(t) for t in h2]):+.2f}")
    say("")
    say("  Tutarlilik: sembolun kendi (A - B) farki havuzun isaretiyle ayni mi.")
    say(f"  Olculebilir sembol = her iki grupta en az {a.min_grup} islem; olculemeyen")
    say("  sembol **tutarsiz** sayilir (kotumser taraf).")
    say("  Sembol seviyesindeki ozellikte (tick/leg) sembol-ici karsitlik yoktur:")
    say("  orada olcu, sembolun ortalamasinin havuz ortalamasinin dogru tarafinda")
    say("  olup olmadigidir ve ayni esikle karsilastirilmaz - not olarak okunur.")

    say("")
    say("  --- ILK YARI (esikler buradan kesilir) " + "-" * 60)
    ozs = ozellikler(h1, costs.fees)
    r1 = yari_raporu(h1, ozs, a.min_grup, semboller)
    say("")
    say("  --- IKINCI YARI (ayni esikler, yeniden kesilmedi) " + "-" * 50)
    r2 = yari_raporu(h2, ozs, a.min_grup, semboller)

    baslik("(c) SONUC - hangi ozellik dayanikli")
    say(f"  Dayanikli = iki yarida da isaret ayni **ve** her iki yarida >= {a.esik}/"
        f"{len(semboller)} sembolde tutarli.")
    say("")
    say(f"  {'ozellik':<34}{'H1 bps':>10}{'H1 tut.':>10}{'H2 bps':>10}{'H2 tut.':>10}"
        f"{'isaret':>9}{'dayanikli':>11}")
    dayanikli, c_satir = [], []
    for o in ozs:
        m1, m2 = r1[o.ad], r2[o.ad]
        d1, d2 = m1["delta"], m2["delta"]
        ayni = d1 is not None and d2 is not None and isaret(d1) == isaret(d2) != 0
        gecti = bool(ayni and m1["tutarli"] >= a.esik and m2["tutarli"] >= a.esik
                     and o.sembol_ici)
        t1 = f"{m1['tutarli']}/{len(semboller)}"
        t2 = f"{m2['tutarli']}/{len(semboller)}"
        say(f"  {o.ad:<34}"
            f"{'-' if d1 is None else format(d1, '+.2f'):>10}{t1:>10}"
            f"{'-' if d2 is None else format(d2, '+.2f'):>10}{t2:>10}"
            f"{('ayni' if ayni else 'dondu'):>9}"
            f"{('EVET' if gecti else 'hayir'):>11}"
            + ("" if o.sembol_ici else "  [sembol seviyesi]"))
        if gecti:
            dayanikli.append(f"{o.ad} ({o.a} - {o.b} = "
                             f"{d1:+.2f} / {d2:+.2f} bps)")
        c_satir.append({"ozellik": o.ad, "karsitlik": f"{o.a}-{o.b}",
                        "h1_delta_bps": d1, "h1_tutarli": m1["tutarli"],
                        "h1_olculebilir": m1["olculebilir"],
                        "h2_delta_bps": d2, "h2_tutarli": m2["tutarli"],
                        "h2_olculebilir": m2["olculebilir"],
                        "isaret_ayni": ayni, "dayanikli": gecti,
                        "sembol_ici": o.sembol_ici})
    say("")
    say("  DAYANIKLI OZELLIKLER:")
    for d in dayanikli or ["  (yok - hicbir aday iki yarida da esigi gecmedi)"]:
        say(f"    - {d}" if dayanikli else f"  {d}")
    say("")
    say("  Skor kurulmadi, filtre uygulanmadi. Bu liste `R-ZONE-08` icin bir")
    say("  **girdi adayligidir**, agirlik degil. Ayrilmis %20 okunmadi.")

    # --- ozet ----------------------------------------------------------------
    baslik("OZET")
    e3, e3b = olculer["E3"], olculer["E3B"]
    say(f"  (a) breakeven otelemesi: net {e3['net']:,.2f} -> {e3b['net']:,.2f} "
        f"({e3b['net'] - e3['net']:+,.2f}) · "
        f"maks DD {e3['maxdd_%']:.1f}% -> {e3b['maxdd_%']:.1f}% · "
        f"komisyon {e3b['komisyon'] - e3['komisyon']:+,.2f}")
    neg = [s["sonuc"] for s in b_satir if s["brut_eksi_kom"] < 0]
    say(f"  (b) komisyon-negatif sonuc tipi: {', '.join(neg) if neg else 'yok'}")
    for s in b_satir:
        say(f"      {s['sonuc']:<24} n={s['islem']:>5,}  brut {s['brut_ort']:>9,.2f}  "
            f"kom {s['komisyon_ort']:>8,.2f}  net bps {s['net_bps']:>8.1f}")
    say(f"  (c) dayanikli ozellik: "
        f"{len(dayanikli)}/{sum(1 for o in ozs if o.sembol_ici)} "
        f"(sembol seviyesi adaylari haric)")
    for d in dayanikli:
        say(f"      - {d}")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kol": k, **{x: olculer[k][x] for x in
                                ("aciklama", "islem", "brut_slipsiz", "komisyon",
                                 "slippage", "funding", "net", "net_%", "maxdd_%")}}
                  for k in kollar]).to_csv(a.csv, index=False)
    pd.DataFrame(b_satir).to_csv(a.csv.replace(".csv", "_sonuc.csv"), index=False)
    pd.DataFrame(c_satir).to_csv(a.csv.replace(".csv", "_ozellik.csv"), index=False)
    pd.DataFrame([
        {"kol": k, "symbol": t.symbol, "zone": t.zone_id, "entry_ts": t.entry_ts,
         "exit_ts": t.exit_ts, "side": t.side, "sonuc": sonuc_tipi(t),
         "reason": t.reason, "reached_tp1": t.reached_tp1, "adds": t.adds,
         "reduces": t.reduces, "gross": t.gross, "fees": t.fees,
         "funding": t.funding, "pnl": t.pnl, "taban": taban(t),
         "net_bps": net_bps(t), "had_ob": t.had_ob, "had_fvg": t.had_fvg,
         "entry_bias": t.entry_bias, "bias_uyum": _bias_grubu(t),
         "touch_count": t.touch_count, "leg_pct": t.leg_pct}
        for k in kollar for t in trades[k]
    ]).to_csv(a.csv.replace(".csv", "_islem.csv"), index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
