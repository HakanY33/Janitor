"""`OPEN-32` · slippage stres testi — taban F1, komisyon sabit, slippage x1 / x2 / x3.

    python -m scripts.bg scripts.slippage_stres

Komisyon borsadan gelir ve kesindir (CLAUDE.md #5); belirsiz olan slippage'dir (§8).
Bu yuzden yalnizca slippage olceklenir. Limit dolumlari slippage odemez (motor
kurali); olcek yalnizca piyasa emirlerine (stop, breakeven, zorunlu cikis) isler.

Once emir defteri kaydinin (`scripts/spread_logger.py`) ne kadar biriktigi yazilir:
olculen slippage ile kosu (`OPEN-32` (a)-(c)) ancak o veri varsa yapilabilir.

Taban **F1** = E3B + ekleme kapali (`docs/measurements/f_kollari.md`). Ayrilmis %20
okunmaz. Sembol cikarma yok — ORDI dahil.
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
from scripts.robustness import E3_TABANI
from src.backtest.costs import CostModel, build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []

F1_TABANI = {**E3_TABANI, "max_adds": 0}


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def defter_durumu(exchange: str) -> list[tuple[str, int, str, str]]:
    """Sembol basina biriken emir defteri anlik goruntusu: (sembol, satir, ilk, son)."""
    satirlar = []
    for d in sorted(Path("data", exchange).glob("*/book")):
        df = pd.concat([pd.read_parquet(f, columns=["ts"]) for f in d.glob("*.parquet")])
        satirlar.append((d.parent.name, len(df), f"{df.ts.min():%Y-%m-%d %H:%M}",
                         f"{df.ts.max():%Y-%m-%d %H:%M}"))
    return satirlar


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-32 slippage stres testi (F1)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--katlar", default="1,2,3", help="slippage carpanlari")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/slippage_stres.txt")
    p.add_argument("--csv", default="logs/slippage_stres.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)
    data, skipped = [], []
    for s in symbols:
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
    if not data:
        sys.exit("hicbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    temel = build_cost_model(isimler, a.exchange)

    olculer: dict[str, dict] = {}
    kazanan: dict[str, int] = {}
    for kat in (Decimal(k) for k in a.katlar.split(",")):
        ad = f"slip x{kat}"
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  {ad} basliyor...", file=sys.stderr, flush=True)
        cm = CostModel(fees=temel.fees, funding=temel.funding,
                       slippage_bps=temel.slippage_bps * kat)
        res = Backtest(data, cm, a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik, False,
                       progress_every=a.progress_every, **F1_TABANI).run()
        olculer[ad] = {"kat": kat, "slip_bps": cm.slippage_bps, **olc(res, a.balance)}
        per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for t in res.trades:
            per[t.symbol] += t.pnl
        kazanan[ad] = sum(1 for v in per.values() if v > 0)
        print(f"  {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    say("=" * 100)
    say(f"OPEN-32 · SLIPPAGE STRES TESTI · TABAN F1  spec {spec_version()}  kod {code_version()}")
    say("=" * 100)
    say(f"  {len(data)}/{len(symbols)} sembol" + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say("  komisyon sabit (borsadan) · slippage yalnizca piyasa emirlerinde · limit dolum 0")
    say("")
    say("  EMIR DEFTERI KAYDI (scripts/spread_logger.py):")
    defter = defter_durumu(a.exchange)
    for s, n, ilk, son in defter or [("(yok)", 0, "-", "-")]:
        say(f"    {s:<22}{n:>8,} dakika   {ilk} -> {son}")
    say("")
    kollar = list(olculer)
    say(f"  {'olcu':<30}" + "".join(f"{k:>16}" for k in kollar))
    for ad, f in (
        ("slippage varsayimi (bps)", lambda k, m: f"{m['slip_bps']}"),
        ("islem", lambda k, m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda k, m: f"{m['brut_slipsiz']:,.2f}"),
        ("komisyon", lambda k, m: f"{m['komisyon']:,.2f}"),
        ("slippage", lambda k, m: f"{m['slippage']:,.2f}"),
        ("funding", lambda k, m: f"{m['funding']:,.2f}"),
        ("NET PnL", lambda k, m: f"{m['net']:,.2f}"),
        ("brut / surtunme", lambda k, m: f"{m['brut_slipsiz'] / (m['komisyon'] + m['slippage']):.3f}"),
        ("maks drawdown", lambda k, m: f"{m['maxdd_%']:.1f}%"),
        ("kazanan sembol", lambda k, m: f"{kazanan[k]}/{len(isimler)}"),
    ):
        say(f"  {ad:<30}" + "".join(f"{f(k, olculer[k]):>16}" for k in kollar))
    b = olculer[kollar[0]]
    if b["slippage"] > 0:
        # ponytail: dogrusal tahmin — slippage dolum fiyatini da kaydirdigi icin kaba.
        kat0 = (b["brut_slipsiz"] - b["komisyon"] - b["funding"]) / b["slippage"]
        say("")
        say(f"  tahmini basabas: slippage x{kat0:.2f} = {kat0 * b['slip_bps']:.2f} bps "
            f"(x1 kolundan dogrusal)")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kol": k, "slip_bps": m["slip_bps"], "islem": m["islem"],
                   "brut": m["brut_slipsiz"], "komisyon": m["komisyon"],
                   "slippage": m["slippage"], "funding": m["funding"], "net": m["net"],
                   "maxdd_%": m["maxdd_%"], "kazanan": kazanan[k]}
                  for k, m in olculer.items()]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
