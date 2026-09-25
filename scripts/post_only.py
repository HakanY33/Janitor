"""`OPEN-37` · post-only giris — limit dolmazsa islem acilmaz, kovalama yok.

    python -m scripts.bg scripts.post_only

Taban **F1**. Giris emri post-only: hic taker'a dusmez; dolmazsa emir seviyede bekler,
zone biterse giris kacar (`kacan_giris`). TP1 ve nihai TP degismez (1 tick asim, maker).

(a) Dolus kriteri, yalnizca giris icin (`Backtest.entry_fill`):
    P1 seviye 1 tick gecilmeli (mevcut) · P2 2 tick · P3 1 tick gecilmeli **ve** mum
    seviyenin otesinde kapanmali (ayni mumda geri donen mum doldurmaz).
(b) Her kol: net · brut/surtunme · islem · kacan giris · sonuc dagilimi · kazanan
    sembol · maks DD · yari ayrimi.
(c) Karsilastirma: TG = P1 + giris %100 taker (OPEN-36 (c), −902).

Yari kesimi P1 islemlerinin medyan giris zamani, tum kollarda ayni. Bu olcumde hicbir
parametre veriden secilmedi; ikinci yari yine de ayri verilir.

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
from scripts.f_kollari import TIPLER
from scripts.levers import olc
from scripts.robustness import sonuc_tipi
from scripts.slippage_stres import F1_TABANI
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []
KOLLAR = {  # ad -> (aciklama, Backtest kwarg'lari)
    "P1": ("post-only, 1 tick", {"entry_fill": "tick1"}),
    "P2": ("post-only, 2 tick", {"entry_fill": "tick2"}),
    "P3": ("post-only, geri donen mum dolmaz", {"entry_fill": "kapanis"}),
    "TG": ("giris %100 taker (OPEN-36)", {"taker_frac": 1.0,
                                          "taker_kinds": frozenset({"giris"})}),
}


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 100)
    say(metin)
    say("=" * 100)


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-37 post-only giris (F1)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/post_only.txt")
    p.add_argument("--csv", default="logs/post_only.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s}", file=sys.stderr, flush=True)
    if not data:
        sys.exit("hicbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]

    olculer: dict[str, dict] = {}
    trades: dict[str, list] = {}
    for ad, (aciklama, kw) in KOLLAR.items():
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
                       a.t_rahat, a.t_kritik, False, progress_every=a.progress_every,
                       **F1_TABANI, **kw).run()
        per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in res.trades:
            per[t.symbol] += t.pnl
        trades[ad] = res.trades
        olculer[ad] = {"aciklama": aciklama, **olc(res, a.balance),
                       "kazanan": sum(1 for v in per.values() if v > 0),
                       "kacan": res.counters["kacan_giris"],
                       "dokunulmadi": res.counters["unfilled"],
                       "taker_giris": res.counters["taker_giris"]}
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    p1 = sorted(trades["P1"], key=lambda t: t.entry_ts)
    kesim = p1[len(p1) // 2].entry_ts
    for ad, tr in trades.items():
        m = olculer[ad]
        m["h1"] = sum((t.pnl for t in tr if t.entry_ts < kesim), Decimal("0"))
        m["h2"] = sum((t.pnl for t in tr if t.entry_ts >= kesim), Decimal("0"))
        m["dag"] = {tip: sum(1 for t in tr if sonuc_tipi(t) == tip) for tip in TIPLER}

    def surt(m: dict) -> Decimal:
        return m["komisyon"] + m["slippage"]

    kollar = list(KOLLAR)
    baslik(f"OPEN-37 · POST-ONLY GIRIS · TABAN F1  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol" + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  TP1 / nihai TP her kolda 1 tick asimla, maker. Komisyon borsa, slippage 2 bps.")
    say(f"  yari kesimi (P1 medyan giris): {kesim:%Y-%m-%d %H:%M} UTC")

    baslik("(a)+(b) KOLLAR")
    say(f"  {'olcu':<30}" + "".join(f"{k:>14}" for k in kollar))
    satirlar = [
        ("islem", lambda m: f"{m['islem']:,}"),
        ("kacan giris (dokundu, dolmadi)", lambda m: f"{m['kacan']:,}"),
        ("hedefe hic dokunulmadi", lambda m: f"{m['dokunulmadi']:,}"),
        ("taker'a dusen giris", lambda m: f"{m['taker_giris']:,}"),
        ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.0f}"),
        ("komisyon", lambda m: f"{m['komisyon']:,.0f}"),
        ("slippage", lambda m: f"{m['slippage']:,.0f}"),
        ("NET PnL", lambda m: f"{m['net']:,.0f}"),
        ("brut / surtunme", lambda m: f"{m['brut_slipsiz'] / surt(m):.3f}"),
        ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
        ("kazanan sembol", lambda m: f"{m['kazanan']}/{len(isimler)}"),
        ("H1 net (islem PnL)", lambda m: f"{m['h1']:,.0f}"),
        ("H2 net (islem PnL)", lambda m: f"{m['h2']:,.0f}"),
    ] + [(f"sonuc: {tip}", (lambda tip: lambda m: f"{m['dag'][tip]:,}")(tip)) for tip in TIPLER]
    for ad, f in satirlar:
        say(f"  {ad:<30}" + "".join(f"{f(olculer[k]):>14}" for k in kollar))
    bozuk = [k for k in kollar if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    if bozuk:
        say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. **")

    baslik("(c) POST-ONLY'NIN KACAN ISLEM MALIYETI vs GIRISIN TAKER'A DUSMESI")
    ref, tg = olculer["P1"], olculer["TG"]
    say(f"  TG (giris taker) net {tg['net']:,.0f} · P1'e gore {tg['net'] - ref['net']:,.0f}")
    say(f"  {'kol':<6}{'net':>10}{'TG farki':>12}{'ek kacan (P1e gore)':>22}"
        f"{'ek kacan basina':>18}")
    c_satir = []
    for k in ("P1", "P2", "P3"):
        m = olculer[k]
        ek = m["kacan"] - ref["kacan"]
        fark = m["net"] - ref["net"]
        say(f"  {k:<6}{m['net']:>10,.0f}{m['net'] - tg['net']:>12,.0f}{ek:>22,}"
            f"{(f'{fark / ek:,.2f}' if ek else '-'):>18}")
        c_satir.append((k, m["net"] > tg["net"]))
    say("  TG farki > 0: post-only, giris taker'a dusmesinden ucuz.")
    say("  Not: TG, P1 ile ayni dolus kumesidir (taker yalnizca maliyet); kacan girisleri")
    say("  kovalayip doldurmaz.")

    baslik("OZET")
    for k in kollar:
        m = olculer[k]
        say(f"  {k} {m['aciklama']:<34} net {m['net']:>8,.0f} · brut/surt "
            f"{m['brut_slipsiz'] / surt(m):.3f} · islem {m['islem']:,} · kacan {m['kacan']:,} · "
            f"DD {m['maxdd_%']:.1f}% · kazanan {m['kazanan']}/{len(isimler)} · H2 {m['h2']:,.0f}")
    say("  (c) " + " · ".join(f"{k} {'<' if ucuz else '>='} TG" for k, ucuz in c_satir)
        + "  (post-only maliyeti vs giris taker)")
    say("  Ayrilmis %20 okunmadi.")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kol": k, "aciklama": m["aciklama"], "islem": m["islem"],
                   "kacan_giris": m["kacan"], "dokunulmadi": m["dokunulmadi"],
                   "brut": m["brut_slipsiz"], "komisyon": m["komisyon"],
                   "slippage": m["slippage"], "funding": m["funding"], "net": m["net"],
                   "maxdd_%": m["maxdd_%"], "kazanan": m["kazanan"], "h1": m["h1"],
                   "h2": m["h2"], **{f"sonuc_{t}": m["dag"][t] for t in TIPLER}}
                  for k, m in olculer.items()]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
