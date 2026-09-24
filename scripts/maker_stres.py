"""`OPEN-36` · maker dolus stresi — limit emirlerin bir kismi taker'a duser.

    python -m scripts.bg scripts.maker_stres

Taban **F1** (v1 varsayilani: ekleme kapali). Komisyon ve slippage **sabit** (borsa
oranlari, 2 bps). Dusen emir ayni mumda dolar, taker komisyonu + slippage oder;
dolum zamanlamasi degismez (`Backtest._taker_mi`).

(a) Rastgele: dusme orani %0/10/25/50/100. Dusme (zone, emir turu) hash'iyle
    deterministik ve ic icedir. Basabas orani iki komsu kol arasindan dogrusal.
(b) Kosullu: emir miktari dolum mumunun 1m hacminin `θ` oranini asarsa duser.
    **1m hacim, defterdeki kuyrugun vekilidir** — defter verisi yok (`OPEN-32`).
(c) Tur: yalnizca giris / yalnizca TP1 / yalnizca nihai TP %100 duser. Maliyet,
    %0 kolundan net fark; emir basina maliyet = fark / dusen emir.

Ayrilmis %20 okunmaz. Sembol cikarma yok — ORDI dahil.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.levers import olc
from scripts.slippage_stres import F1_TABANI
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []
TURLER = ("giris", "tp1", "tp_nihai")


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 108)
    say(metin)
    say("=" * 108)


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-36 maker dolus stresi (F1)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--oranlar", default="0,0.10,0.25,0.50,1.0")
    p.add_argument("--hacim-esikleri", default="0.001,0.005,0.01,0.05,0.10,0.25")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/maker_stres.txt")
    p.add_argument("--csv", default="logs/maker_stres.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)
    t0 = time.time()
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        c0 = time.time()
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s:<24} {time.time() - c0:>6.1f} sn",
              file=sys.stderr, flush=True)
    if not data:
        sys.exit("hicbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme = time.time() - t0

    olculer: dict[str, dict] = {}

    def kos(ad: str, aciklama: str, **kw) -> None:
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
                       a.t_rahat, a.t_kritik, False, progress_every=a.progress_every,
                       **F1_TABANI, **kw).run()
        per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in res.trades:
            per[t.symbol] += t.pnl
        # dusebilecek emir sayisi: her islemin girisi + TP1'e ulasan + nihai TP
        aday = {"giris": len(res.trades),
                "tp1": sum(t.reached_tp1 for t in res.trades),
                "tp_nihai": sum(t.reason == "FINAL_TP" for t in res.trades)}
        olculer[ad] = {"aciklama": aciklama, **olc(res, a.balance),
                       "kazanan": sum(1 for v in per.values() if v > 0),
                       "dusen": {k: res.counters[f"taker_{k}"] for k in TURLER},
                       "aday": aday}
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    oranlar = [float(x) for x in a.oranlar.split(",")]
    esikler = [float(x) for x in a.hacim_esikleri.split(",")]
    for o in oranlar:
        kos(f"R{o * 100:.0f}", f"rastgele %{o * 100:.0f} taker'a duser", taker_frac=o)
    for e in esikler:
        kos(f"V{e * 100:g}", f"emir > 1m hacmin %{e * 100:g}'i ise duser", taker_vol_frac=e)
    for tur in TURLER:
        kos(f"T-{tur}", f"yalnizca {tur} %100 duser", taker_frac=1.0,
            taker_kinds=frozenset({tur}))

    def surt(m: dict) -> Decimal:
        return m["komisyon"] + m["slippage"]

    def tablo(kollar: list[str]) -> None:
        say(f"  {'olcu':<28}" + "".join(f"{k:>13}" for k in kollar))
        for ad, f in (
            ("islem", lambda m: f"{m['islem']:,}"),
            ("dusen emir", lambda m: f"{sum(m['dusen'].values()):,}"),
            ("dusen / aday", lambda m: f"{sum(m['dusen'].values()) / max(1, sum(m['aday'].values())) * 100:.1f}%"),
            ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.0f}"),
            ("komisyon", lambda m: f"{m['komisyon']:,.0f}"),
            ("slippage", lambda m: f"{m['slippage']:,.0f}"),
            ("NET PnL", lambda m: f"{m['net']:,.0f}"),
            ("brut / surtunme", lambda m: f"{m['brut_slipsiz'] / surt(m):.3f}"),
            ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
            ("kazanan sembol", lambda m: f"{m['kazanan']}/{len(isimler)}"),
        ):
            say(f"  {ad:<28}" + "".join(f"{f(olculer[k]):>13}" for k in kollar))

    baslik(f"OPEN-36 · MAKER DOLUS STRESI · TABAN F1  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol" + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  komisyon ve slippage sabit (borsa oranlari, 2 bps) · dusen emir ayni mumda dolar,")
    say("  taker + slippage oder · dolum zamanlamasi degismez (iyimser taraf)")
    say(f"  yukleme {yukleme / 60:.1f} dk")

    ra = [f"R{o * 100:.0f}" for o in oranlar]
    baslik("(a) RASTGELE DUSME ORANI")
    tablo(ra)
    basabas = None
    for k1, k2, o1, o2 in zip(ra, ra[1:], oranlar, oranlar[1:]):
        n1, n2 = olculer[k1]["net"], olculer[k2]["net"]
        if n1 > 0 >= n2:
            basabas = o1 + float(n1 / (n1 - n2)) * (o2 - o1)
            break
    say("")
    say(f"  basabas orani: %{basabas * 100:.1f} (komsu iki kol arasi dogrusal)" if basabas
        is not None else "  basabas: hicbir oranda net sifirin altina inmedi"
        if olculer[ra[-1]]["net"] > 0 else "  basabas: %0'da bile net negatif")

    va = [f"V{e * 100:g}" for e in esikler]
    baslik("(b) KOSULLU - emir miktari > θ x dolum mumunun 1m hacmi -> taker")
    say("  **VEKIL:** 1m islem hacmi, emrin onundeki defter kuyrugunun yerine kullanildi.")
    say("  Defter verisi yok (OPEN-32). Olcu kuyrugu degil, emrin mumun hacmine oranini")
    say("  sinar: buyuk emir, sakin mumda pasif dolmaz varsayimi.")
    say("")
    tablo([ra[0]] + va)
    say("")
    say(f"  {'tur basina dusen / aday':<28}" + "".join(f"{k:>13}" for k in va))
    for tur in TURLER:
        say(f"  {tur:<28}" + "".join(
            f"{olculer[k]['dusen'][tur]:>6,}/{olculer[k]['aday'][tur]:<6,}" for k in va))

    ta = [f"T-{t}" for t in TURLER]
    baslik("(c) EMIR TURUNE GORE - yalnizca o tur %100 taker'a duser")
    tablo([ra[0]] + ta)
    say("")
    taban = olculer[ra[0]]["net"]
    say(f"  {'tur':<12}{'dusen emir':>12}{'net farki':>14}{'emir basina':>14}")
    tur_satir = []
    for tur, k in zip(TURLER, ta):
        n = olculer[k]["dusen"][tur]
        fark = olculer[k]["net"] - taban
        say(f"  {tur:<12}{n:>12,}{fark:>14,.0f}{(fark / n if n else 0):>14,.2f}")
        tur_satir.append({"tur": tur, "dusen": n, "net_farki": fark})
    en = min(tur_satir, key=lambda r: r["net_farki"])
    say("")
    say(f"  en pahali tur (toplam): {en['tur']}")

    baslik("OZET")
    say("  (a) " + " · ".join(f"%{o * 100:.0f} -> {olculer[k]['net']:,.0f}"
                            for o, k in zip(oranlar, ra)))
    say(f"      basabas orani: " + (f"%{basabas * 100:.1f}" if basabas is not None else "-"))
    say("  (b) " + " · ".join(f"θ %{e * 100:g} -> {olculer[k]['net']:,.0f} "
                            f"({sum(olculer[k]['dusen'].values()) / max(1, sum(olculer[k]['aday'].values())) * 100:.0f}% duser)"
                            for e, k in zip(esikler, va)) + "  [1m hacim vekil]")
    say("  (c) " + " · ".join(f"{r['tur']} {r['net_farki']:,.0f}" for r in tur_satir))
    say("  Ayrilmis %20 okunmadi.")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kol": k, "aciklama": m["aciklama"], "islem": m["islem"],
                   "brut": m["brut_slipsiz"], "komisyon": m["komisyon"],
                   "slippage": m["slippage"], "funding": m["funding"], "net": m["net"],
                   "maxdd_%": m["maxdd_%"], "kazanan": m["kazanan"],
                   **{f"dusen_{t}": m["dusen"][t] for t in TURLER},
                   **{f"aday_{t}": m["aday"][t] for t in TURLER}}
                  for k, m in olculer.items()]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
