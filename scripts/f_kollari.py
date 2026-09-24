"""F1 / F2 kollari — E3B tabani uzerinde ekleme kapali ve asgari leg esigi.

    python -m scripts.bg scripts.f_kollari

Taban **E3B** = E3 (`scripts/robustness.py`) + breakeven ucret dahil (`OPEN-35`
kapandi, motor varsayilani). Referans olarak ayni kosuda yeniden olculur.

| kol | ne |
|---|---|
| **E3B** | referans |
| **F1** | `max_adds = 0`: ekleme yok, dolayisiyla `R-ADD-04` kucultmesi de yok. Tek giris, TP1, breakeven, nihai TP, stop |
| **F2** | E3B + asgari leg esigi. Esik E3B'nin **ilk yarisindan** kesilir (en kucuk leg tertilinin ust siniri), ikinci yarida aynen kalir. Esik alti zone giris uretmez |

F2'de esik ilk yaridan kesildigi icin ilk yari **orneklem ici**dir; ikinci yari ayri
satirda verilir. En iyi kol (net) icin komisyon ve slippage x1.5 dayaniklilik kolu.

Ayrilmis %20 hicbir kolda okunmaz (`train_frac`). Sembol cikarma yok — ORDI dahil.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.add_reject_e import olcekli
from scripts.backtest import code_version, spec_version
from scripts.levers import IFLAS_ESIKLERI, olc
from scripts.robustness import E3_TABANI, sonuc_tipi, taban
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, Trade, load_symbol, reset_for_rerun

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


TIPLER = ["nihai TP", "TP1 + breakeven", "stop", "stop (TP1 sonrasi)", "digeri"]


def leg_esigi(trades: list[Trade]) -> float:
    """En kucuk leg tertilinin ust siniri — `robustness.ozellikler` ile ayni kesim."""
    legler = sorted(t.leg_pct for t in trades if t.leg_pct > 0)
    if len(legler) < 3:
        raise ValueError("leg tertili icin yeterli islem yok")
    return legler[len(legler) // 3]


def main() -> int:
    p = argparse.ArgumentParser(description="F1 / F2 kollari")
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
    p.add_argument("--stres", type=Decimal, default=Decimal("1.5"))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/f_kollari.txt")
    p.add_argument("--csv", default="logs/f_kollari.csv")
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
    temel = build_cost_model(isimler, a.exchange)

    olculer: dict[str, dict] = {}
    trades: dict[str, list[Trade]] = {}

    def kos(ad: str, aciklama: str, kat: Decimal = Decimal("1"), **kw) -> None:
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(
            data, olcekli(temel, kat), a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik,
            a.uyari_adds == "evet", progress_every=a.progress_every,
            terminate=a.terminate, **{**E3_TABANI, **kw},
        ).run()
        olculer[ad] = {"aciklama": aciklama, "kw": kw, "kat": kat, **olc(res, a.balance),
                       "leg_skipped": res.counters["leg_skipped"]}
        trades[ad] = res.trades
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    kos("E3B", "referans: E3 + breakeven ucret dahil")

    # Zaman kesimi E3B'den: islem sayisini esitleyen an (robustness (c) ile ayni).
    tr = sorted(trades["E3B"], key=lambda t: t.entry_ts)
    kesim = tr[len(tr) // 2].entry_ts
    esik = leg_esigi([t for t in tr if t.entry_ts < kesim])

    kos("F1", "ekleme kapali (max_adds = 0)", max_adds=0)
    kos("F2", f"E3B + asgari leg > {esik * 100:.3f}%", min_leg_pct=esik)

    en_iyi = max(("F1", "F2"), key=lambda k: olculer[k]["net"])
    stres_ad = f"{en_iyi}x{a.stres}"
    kos(stres_ad, f"{olculer[en_iyi]['aciklama']}, maliyet x{a.stres}", a.stres,
        **olculer[en_iyi]["kw"])

    kollar = ["E3B", "F1", "F2"]
    hepsi = kollar + [stres_ad]

    def sembol_pnl(k: str) -> dict[str, Decimal]:
        per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in trades[k]:
            per[t.symbol] += t.pnl
        return per

    def kazanan(k: str) -> str:
        per = sembol_pnl(k)
        return f"{sum(1 for v in per.values() if v > 0)}/{len(isimler)}"

    def surtunme(m: dict) -> Decimal:
        return m["komisyon"] + m["slippage"]

    baslik(f"F1 / F2 KOLLARI · TABAN E3B  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say("  sembol cikarma yok - ORDI dahil")
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  TABAN = E3B: R-ENTRY-02 (3) kapali - limit emri - TP tam seviyede - ekleme "
        "tavani 3 - kucultme bir kez - ADD-REJECT-E L = %3 - breakeven ucret dahil")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr} - sonlandirma {a.terminate}")
    say(f"  yukleme {yukleme / 60:.1f} dk")
    say(f"  zaman kesimi (E3B islem sayisini esitleyen an): {kesim:%Y-%m-%d %H:%M} UTC")
    say(f"  F2 leg esigi (E3B ilk yarisi, alt tertil ust siniri): {esik * 100:.3f}%  "
        f"- esit ve alti giris uretmez")
    say("")
    for k in hepsi:
        say(f"  {k:<10} = {olculer[k]['aciklama']}")

    # --- (a) ana tablo -------------------------------------------------------
    baslik("(a) KOL BASINA PARA")
    say("  Brut fiyat PnL'i slippage **disari cikarilmis** haldir. Surtunme = komisyon + slippage.")
    say("")
    say(f"  {'olcu':<34}" + "".join(f"{k:>16}" for k in hepsi))
    satirlar = [
        ("islem sayisi", lambda k, m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda k, m: f"{m['brut_slipsiz']:,.2f}"),
        ("komisyon", lambda k, m: f"{m['komisyon']:,.2f}"),
        ("slippage", lambda k, m: f"{m['slippage']:,.2f}"),
        ("funding", lambda k, m: f"{m['funding']:,.2f}"),
        ("NET PnL", lambda k, m: f"{m['net']:,.2f}"),
        ("net getiri", lambda k, m: f"{m['net_%']:.2f}%"),
        ("brut / surtunme", lambda k, m: f"{m['brut_slipsiz'] / surtunme(m):.3f}"
         if surtunme(m) else "-"),
        ("maks drawdown", lambda k, m: f"{m['maxdd_%']:.1f}%"),
        ("likidasyon", lambda k, m: f"{m['likidasyon']:,}"),
        ("kazanan sembol", lambda k, m: kazanan(k)),
        ("ekleme", lambda k, m: f"{m['adds']:,}"),
        ("kucultme", lambda k, m: f"{m['reduces']:,}"),
        ("leg esigiyle atlanan zone", lambda k, m: f"{m['leg_skipped']:,}"),
        ("uzlasma farki", lambda k, m: f"{m['uzlasma_farki']:.2E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<34}" + "".join(f"{f(k, olculer[k]):>16}" for k in hepsi))
    for e in IFLAS_ESIKLERI:
        say(f"  {f'iflas: bar, baslangicin < %{e * 100:.0f}':<34}"
            + "".join(f"{olculer[k]['iflas'][e]:>15.1f}%" for k in hepsi))
    bozuk = [k for k in hepsi if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    say("")
    say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. **" if bozuk
        else "  (uzlasma farki Decimal bolme artigi; her kolda kalemler kapaniyor)")

    # --- (b) sonuc dagilimi ve komisyon --------------------------------------
    baslik("(b) SONUC DAGILIMI VE KOMISYON - sonuc tipine gore")
    say("  `kom bps` tabani tepe notional = tepe miktar x giris fiyati.")
    b_satir = []
    for k in hepsi:
        say("")
        toplam_kom = sum((t.fees for t in trades[k]), Decimal("0")) or Decimal("1")
        n_top = len(trades[k]) or 1
        say(f"  {k} ({olculer[k]['aciklama']})")
        say(f"    {'sonuc':<22}{'islem':>8}{'pay':>8}{'brut/islem':>12}{'kom/islem':>11}"
            f"{'kom toplam':>12}{'kom payi':>10}{'kom bps':>9}{'net/islem':>11}")
        for tip in TIPLER:
            g = [t for t in trades[k] if sonuc_tipi(t) == tip]
            if not g:
                continue
            n = len(g)
            brut = sum((t.gross for t in g), Decimal("0")) / n
            kom = sum((t.fees for t in g), Decimal("0"))
            net = sum((t.pnl for t in g), Decimal("0")) / n
            kb = sum(float(t.fees / taban(t) * 10_000) for t in g if taban(t) > 0) / n
            say(f"    {tip:<22}{n:>8,}{n / n_top * 100:>7.1f}%{brut:>12,.2f}{kom / n:>11,.2f}"
                f"{kom:>12,.2f}{kom / toplam_kom * 100:>9.1f}%{kb:>9.1f}{net:>11,.2f}")
            b_satir.append({"kol": k, "sonuc": tip, "islem": n, "brut_ort": brut,
                            "komisyon_toplam": kom, "komisyon_ort": kom / n,
                            "komisyon_payi_%": kom / toplam_kom * 100,
                            "komisyon_bps": kb, "net_ort": net})

    # --- (c) F2 yari ayrimi --------------------------------------------------
    baslik("(c) YARI AYRIMI - F2 esigi ilk yaridan kesildi, ikinci yari orneklem disi")
    say(f"  {'kol':<12}{'H1 net':>14}{'H1 islem':>10}{'H2 net':>14}{'H2 islem':>10}"
        f"{'H2 kazanan sembol':>20}")
    for k in hepsi:
        h1 = [t for t in trades[k] if t.entry_ts < kesim]
        h2 = [t for t in trades[k] if t.entry_ts >= kesim]
        per2: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in h2:
            per2[t.symbol] += t.pnl
        say(f"  {k:<12}{sum((t.pnl for t in h1), Decimal('0')):>14,.2f}{len(h1):>10,}"
            f"{sum((t.pnl for t in h2), Decimal('0')):>14,.2f}{len(h2):>10,}"
            f"{sum(1 for v in per2.values() if v > 0):>17}/{len(isimler)}")
    say("  Yari toplamlari islem PnL'idir (komisyon ve funding dahil, girise gore); cross")
    say("  marjinde yarilar birbirinin equity'sinden boyut aldigi icin bagimsiz degildir.")

    # --- (d) dayaniklilik ----------------------------------------------------
    baslik(f"(d) DAYANIKLILIK - en iyi kol {en_iyi}, komisyon ve slippage x{a.stres}")
    t_, u = olculer[en_iyi], olculer[stres_ad]
    say(f"  {'olcu':<28}{en_iyi:>16}{stres_ad:>16}{'fark':>16}")
    for ad, anahtar, bicim in (
        ("net PnL", "net", ",.2f"), ("brut fiyat PnL", "brut_slipsiz", ",.2f"),
        ("komisyon", "komisyon", ",.2f"), ("slippage", "slippage", ",.2f"),
        ("net getiri %", "net_%", ".2f"), ("maks drawdown %", "maxdd_%", ".1f"),
        ("islem", "islem", ",d"),
    ):
        say(f"  {ad:<28}{format(t_[anahtar], bicim):>16}{format(u[anahtar], bicim):>16}"
            f"{format(u[anahtar] - t_[anahtar], bicim):>16}")
    say(f"  {'brut / surtunme':<28}{t_['brut_slipsiz'] / surtunme(t_):>16.3f}"
        f"{u['brut_slipsiz'] / surtunme(u):>16.3f}")
    say(f"  {'kazanan sembol':<28}{kazanan(en_iyi):>16}{kazanan(stres_ad):>16}")

    # --- ozet ----------------------------------------------------------------
    baslik("OZET")
    for k in hepsi:
        m = olculer[k]
        dag = {tip: sum(1 for t in trades[k] if sonuc_tipi(t) == tip) for tip in TIPLER}
        say(f"  {k:<10} net {m['net']:>10,.2f} · brut {m['brut_slipsiz']:>10,.2f} · "
            f"kom {m['komisyon']:>9,.2f} · slip {m['slippage']:>8,.2f} · "
            f"brut/surt {m['brut_slipsiz'] / surtunme(m):.3f} · islem {m['islem']:,} · "
            f"maks DD {m['maxdd_%']:.1f}% · iflas<%10 {m['iflas'][0.10]:.1f}% · "
            f"kazanan {kazanan(k)}")
        say(f"  {'':<10} nihai TP {dag['nihai TP']:,} · TP1+BE {dag['TP1 + breakeven']:,} · "
            f"stop {dag['stop']:,} · stop(TP1 sonrasi) {dag['stop (TP1 sonrasi)']:,} · "
            f"digeri {dag['digeri']:,}")
    say(f"  F2 esigi {esik * 100:.3f}% (E3B ilk yarisi). Ayrilmis %20 okunmadi.")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"kol": k, "aciklama": m["aciklama"], "maliyet_kat": m["kat"], "islem": m["islem"],
         "brut_fiyat_pnl": m["brut_slipsiz"], "komisyon": m["komisyon"],
         "slippage": m["slippage"], "funding": m["funding"], "net_pnl": m["net"],
         "net_getiri_%": m["net_%"], "maxdd_%": m["maxdd_%"], "adds": m["adds"],
         "reduces": m["reduces"], "leg_skipped": m["leg_skipped"],
         "kazanan_sembol": kazanan(k), "leg_esigi": esik,
         **{f"iflas_{int(e * 100)}_%": m["iflas"][e] for e in IFLAS_ESIKLERI}}
        for k, m in olculer.items()
    ]).to_csv(a.csv, index=False)
    pd.DataFrame(b_satir).to_csv(a.csv.replace(".csv", "_sonuc.csv"), index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
