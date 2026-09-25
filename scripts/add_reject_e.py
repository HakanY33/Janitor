"""`ADD-REJECT-E` — pozisyon seviyesinde stop kaybi tavani (`L`).

    python -m scripts.bg scripts.add_reject_e

**Neden.** `docs/measurements/tp_placement.md`: hesabin toplam kaybindan fazlasini
**tek bir pozisyon** tasidi (ORDI -5.539 = net kaybin %106'si; o sembolsuz D1 +322).
Bitiren sey `R-ADD-03` carpan merdiveni: carpanlar (1-1, 1-3, 1-5, 1-10) **carpimsal**,
iki ekleme girisin 24 katina cikiyor ve MAE equity'nin %86,6'sina ulasiyor.
`R-RISK-01` (10 x equity) bunu baglamiyor cunku olcu **notional** ve equity de
pozisyonla birlikte dusuyor. `max_adds` tavani ekleme *sayisini* sinirliyor, *boyutu*
degil.

**Kural (`ADD-REJECT-E`).** Ekleme sonrasi

    toplam notional x |stop(1) - ortalama maliyet| / ortalama maliyet  >  L x equity

ise ekleme reddedilir. Sol taraf pozisyonun nihai stopa giderse **realize olacak
kaybidir**; notional `qty x maliyet` oldugu icin `qty x |stop - maliyet|`e sadelesir.
**Ayni kisit ilk girise de uygulanir**: pozisyon daha acilmadan stopta kaybedecegi
tutar tavani asiyorsa hic acilmaz.

Taban **D1** (`docs/measurements/tp_placement.md`): `R-ENTRY-02` (3) kapali, limit
emri, TP tam seviyede, ekleme tavani 3, kucultme bir kez.

| kol | L |
|---|---|
| **E0** | kural kapali (D1 — referans) |
| **E10** | %10 |
| **E5** | %5 |
| **E3** | %3 |

**Dayaniklilik (validasyon kriteri 2).** En iyi kol, komisyon ve slippage **x1.5** ile
yeniden kosulur. Kriter 1 ayrilmis %20'dir ve burada **okunmaz**; bu kol yalnizca
sonucun maliyet varsayimina ne kadar dayandigini olcer.

20 sembol, sembol cikarma yok — ORDI dahil. Ayrilmis %20 hicbir kolda okunmaz.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.levers import IFLAS_ESIKLERI, olc
from src.backtest.costs import CostModel, Fees, build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

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


# D1 tabani — butun kollarda sabit (docs/measurements/tp_placement.md).
D1_TABANI = {"require_indicator": True, "limit_orders": True,
             "max_adds": 3, "reduce_once": True}

KOLLAR = [
    ("E0", "kural kapali (D1)", Decimal("0")),
    ("E10", "L = %10", Decimal("0.10")),
    ("E5", "L = %5", Decimal("0.05")),
    ("E3", "L = %3", Decimal("0.03")),
]


def olcekli(cm: CostModel, kat: Decimal) -> CostModel:
    """Komisyon ve slippage `kat` ile carpilmis yeni maliyet modeli.

    Funding egrileri paylasilir (okunur, degistirilmez); sayaclar sifirdan baslar —
    ayni modeli iki kosuda kullanmak kalem defterini toplardi.
    """
    return CostModel(
        fees={s: Fees(f.taker * kat, f.maker * kat, f.tick) for s, f in cm.fees.items()},
        funding=cm.funding,
        slippage_bps=cm.slippage_bps * kat,
    )


def en_kotu(trades, n: int = 5) -> list[dict]:
    """En cok kaybettiren `n` islem — tek pozisyonun hesabi bitirip bitirmedigi burada."""
    return [
        {"symbol": t.symbol, "pnl": t.pnl, "adds": t.adds,
         "tepe_giris": float(t.qty / t.entry_qty) if t.entry_qty else 1.0,
         "reason": t.reason, "bars": t.bars_held}
        for t in sorted(trades, key=lambda x: x.pnl)[:n]
    ]


def main() -> int:
    p = argparse.ArgumentParser(description="ADD-REJECT-E stop kaybi tavani")
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
    p.add_argument("--stres", type=Decimal, default=Decimal("1.5"),
                   help="dayaniklilik kolunda komisyon/slippage carpani")
    p.add_argument("--kollar", default="E0,E10,E5,E3")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/add_reject_e.txt")
    p.add_argument("--csv", default="logs/add_reject_e.csv")
    a = p.parse_args()

    secili = set(a.kollar.split(","))
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
    print(f"  yukleme {yukleme / 60:.1f} dk", file=sys.stderr, flush=True)
    temel = build_cost_model(isimler, a.exchange)

    olculer: dict[str, dict] = {}
    sembol_pnl: dict[str, dict] = {}

    def kos(ad: str, aciklama: str, cap: Decimal, kat: Decimal = Decimal("1")) -> None:
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(
            data, olcekli(temel, kat), a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik,
            a.uyari_adds == "evet", progress_every=a.progress_every,
            terminate=a.terminate, **D1_TABANI, stop_loss_cap=cap,
        ).run()
        olculer[ad] = {
            "aciklama": aciklama, "L": cap, "kat": kat, **olc(res, a.balance),
            "add_reject_e": res.counters["add_reject_e"],
            "entry_reject_e": res.counters["entry_reject_e"],
            "en_kotu": en_kotu(res.trades),
        }
        per: dict = defaultdict(lambda: Decimal("0"))
        adet: Counter = Counter()
        for t in res.trades:
            per[t.symbol] += t.pnl
            adet[t.symbol] += 1
        sembol_pnl[ad] = {"pnl": dict(per), "adet": adet}
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    for ad, aciklama, cap in KOLLAR:
        if ad in secili:
            kos(ad, aciklama, cap)

    # Dayaniklilik: en iyi kol, komisyon ve slippage x`stres`.
    en_iyi = max(olculer, key=lambda k: olculer[k]["net"])
    stres_ad = f"{en_iyi}x{a.stres}"
    kos(stres_ad, f"{olculer[en_iyi]['aciklama']}, maliyet x{a.stres}",
        olculer[en_iyi]["L"], a.stres)

    kollar = [k for k in olculer if k != stres_ad]
    hepsi = kollar + [stres_ad]

    baslik(f"ADD-REJECT-E · STOP KAYBI TAVANI  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say("  sembol cikarma yok - ORDI dahil")
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  TABAN = D1: R-ENTRY-02 (3) kapali - limit emri - TP tam seviyede - "
        "ekleme tavani 3 - kucultme bir kez")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr} - sonlandirma {a.terminate}")
    say(f"  yukleme {yukleme / 60:.1f} dk")
    say("")
    for k in hepsi:
        say(f"  {k:<8} = {olculer[k]['aciklama']}")

    # --- (a) ana tablo -------------------------------------------------------
    baslik("(a) KOL BASINA PARA")
    say("  Brut fiyat PnL'i slippage **disari cikarilmis** haldir; slippage ayri satirda.")
    say("")
    say(f"  {'olcu':<34}" + "".join(f"{k:>16}" for k in hepsi))
    satirlar = [
        ("islem sayisi", lambda m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.2f}"),
        ("komisyon", lambda m: f"{m['komisyon']:,.2f}"),
        ("slippage", lambda m: f"{m['slippage']:,.2f}"),
        ("funding", lambda m: f"{m['funding']:,.2f}"),
        ("NET PnL", lambda m: f"{m['net']:,.2f}"),
        ("net getiri", lambda m: f"{m['net_%']:.1f}%"),
        ("bitis bakiye", lambda m: f"{m['bitis']:,.2f}"),
        ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
        ("likidasyon", lambda m: f"{m['likidasyon']:,}"),
        ("", lambda m: ""),
        ("ekleme", lambda m: f"{m['adds']:,}"),
        ("ADD-REJECT-E red (ekleme, bar)", lambda m: f"{m['add_reject_e']:,}"),
        ("ADD-REJECT-E red (giris)", lambda m: f"{m['entry_reject_e']:,}"),
        ("kucultme", lambda m: f"{m['reduces']:,}"),
        ("uzlasma farki", lambda m: f"{m['uzlasma_farki']:.2E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<34}" + "".join(f"{f(olculer[k]):>16}" for k in hepsi))
    say("")
    say("  `red (ekleme, bar)` bir **bar** sayacidir: reddedilen ekleme OB'yi tuketmez,")
    say("  ayni OB'ye dokunulan her mumda yeniden denenir ve yeniden sayilir. Olay")
    say("  sayisi degildir; kuralin ne kadar sik bagladiginin gostergesidir.")
    bozuk = [k for k in hepsi if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    say("")
    say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. **" if bozuk
        else "  (uzlasma farki Decimal bolme artigi; her kolda kalemler kapaniyor)")

    # --- (b) en kotu 5 islem -------------------------------------------------
    baslik("(b) EN KOTU 5 ISLEM - kuralin var olma nedeni")
    say("  D1'de tek bir pozisyon hesabin toplam kaybindan fazlasini tasiyordu.")
    say("  `tepe/giris` = pozisyonun ulastigi en buyuk miktar / giris miktari.")
    for k in hepsi:
        say("")
        say(f"  {k} ({olculer[k]['aciklama']})  -  net {olculer[k]['net']:,.2f}")
        say(f"    {'#':>2} {'sembol':<20}{'kayip':>14}{'tepe/giris':>12}{'ekleme':>8}"
            f"{'neden':>12}{'tasima (gun)':>14}{'net payi':>10}")
        for i, t in enumerate(olculer[k]["en_kotu"], 1):
            pay = t["pnl"] / olculer[k]["net"] * 100 if olculer[k]["net"] else Decimal("0")
            say(f"    {i:>2} {t['symbol']:<20}{t['pnl']:>14,.2f}{t['tepe_giris']:>12.2f}"
                f"{t['adds']:>8}{t['reason']:>12}{t['bars'] / 1440:>14.1f}{pay:>9.1f}%")

    # --- (c) iflas metrigi ---------------------------------------------------
    baslik("(c) IFLAS METRIGI - equity baslangicin altinda gecen bar orani")
    say(f"  {'esik':<20}" + "".join(f"{k:>16}" for k in hepsi))
    for e in IFLAS_ESIKLERI:
        say(f"  {f'baslangicin < %{e * 100:.0f}':<20}"
            + "".join(f"{olculer[k]['iflas'][e]:>15.1f}%" for k in hepsi))

    # --- (d) sembol bazinda --------------------------------------------------
    baslik("(d) SEMBOL BASINA NET PnL")
    say("  Cross marjin: sembol PnL'leri toplami hesabin net PnL'ine esittir, ama")
    say("  sembolun boyutu o anki portfoy equity'sinden gelir - semboller birbirini tasir.")
    say("")
    tum_sembol = sorted({s for m in sembol_pnl.values() for s in m["pnl"]})
    say(f"  {'sembol':<20}" + "".join(f"{k:>16}" for k in hepsi))
    for sym in sorted(tum_sembol,
                      key=lambda x: sembol_pnl[hepsi[0]]["pnl"].get(x, Decimal("0"))):
        say(f"  {sym.split('/')[0]:<20}"
            + "".join(f"{sembol_pnl[k]['pnl'].get(sym, Decimal('0')):>16,.2f}"
                      for k in hepsi))
    say(f"  {'-' * 20}" + "".join(f"{'-' * 16}" for _ in hepsi))
    say(f"  {'TOPLAM':<20}"
        + "".join(f"{sum(sembol_pnl[k]['pnl'].values(), Decimal('0')):>16,.2f}"
                  for k in hepsi))
    say(f"  {'KAZANAN SEMBOL':<20}"
        + "".join(f"{sum(1 for v in sembol_pnl[k]['pnl'].values() if v > 0):>13}/"
                  f"{len(sembol_pnl[k]['pnl']):<2}" for k in hepsi))
    say(f"  {'EN AGIR SEMBOLSUZ':<20}"
        + "".join(
            f"{sum(sembol_pnl[k]['pnl'].values(), Decimal('0')) - min(sembol_pnl[k]['pnl'].values()):>16,.2f}"
            if sembol_pnl[k]["pnl"] else f"{'-':>16}" for k in hepsi))

    # --- (e) dayaniklilik ----------------------------------------------------
    baslik(f"(e) DAYANIKLILIK (validasyon kriteri 2) - {en_iyi} maliyet x{a.stres}")
    say("  Kriter 1 ayrilmis %20'dir ve burada okunmadi. Bu kol yalnizca sonucun")
    say("  maliyet varsayimina ne kadar dayandigini olcer: komisyon ve slippage x1.5.")
    say("")
    t, u = olculer[en_iyi], olculer[stres_ad]
    say(f"  {'olcu':<28}{en_iyi:>16}{stres_ad:>16}{'fark':>16}")
    for ad, anahtar, bicim in (
        ("net PnL", "net", ",.2f"), ("brut fiyat PnL", "brut_slipsiz", ",.2f"),
        ("komisyon", "komisyon", ",.2f"), ("slippage", "slippage", ",.2f"),
        ("net getiri %", "net_%", ".1f"), ("maks drawdown %", "maxdd_%", ".1f"),
        ("islem", "islem", ",d"),
    ):
        say(f"  {ad:<28}{format(t[anahtar], bicim):>16}{format(u[anahtar], bicim):>16}"
            f"{format(u[anahtar] - t[anahtar], bicim):>16}")
    say("")
    say(f"  kazanan sembol {sum(1 for v in sembol_pnl[en_iyi]['pnl'].values() if v > 0)}"
        f"/{len(sembol_pnl[en_iyi]['pnl'])}  ->  "
        f"{sum(1 for v in sembol_pnl[stres_ad]['pnl'].values() if v > 0)}"
        f"/{len(sembol_pnl[stres_ad]['pnl'])}")
    say("  Karar: isaret x1.5 maliyette de korunuyorsa sonuc maliyet varsayimina")
    say("  dayanikli; donuyorsa sonuc surtunme esiginin hemen kenarinda demektir.")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"kol": k, "aciklama": m["aciklama"], "L": m["L"], "maliyet_kat": m["kat"],
         "islem": m["islem"], "brut_fiyat_pnl": m["brut_slipsiz"],
         "komisyon": m["komisyon"], "slippage": m["slippage"], "funding": m["funding"],
         "net_pnl": m["net"], "net_getiri_%": m["net_%"], "maxdd_%": m["maxdd_%"],
         "adds": m["adds"], "add_reject_e": m["add_reject_e"],
         "entry_reject_e": m["entry_reject_e"],
         "kazanan_sembol": sum(1 for v in sembol_pnl[k]["pnl"].values() if v > 0),
         **{f"iflas_{int(e * 100)}_%": m["iflas"][e] for e in IFLAS_ESIKLERI}}
        for k, m in olculer.items()
    ]).to_csv(a.csv, index=False)
    pd.DataFrame([
        {"kol": k, "symbol": sym, "net_pnl": sembol_pnl[k]["pnl"].get(sym, Decimal("0")),
         "islem": sembol_pnl[k]["adet"].get(sym, 0)}
        for k in hepsi for sym in tum_sembol
    ]).to_csv(a.csv.replace(".csv", "_sembol.csv"), index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
