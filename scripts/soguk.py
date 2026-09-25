"""Sembol soguk testi + kriter 2 (yeni tanim) — F1 dondurulmus, iki sembol kumesi.

    python -m scripts.bg scripts.soguk

**Kumeler.** ORIJINAL: `liquidity.json`'daki 20 sembol (2026-09-11 siralamasi), bugune
kadarki butun olcumler. YENI: `liquidity_soguk.json` — 2026-09-25 hacim siralamasinda
21. siradan baslayip orijinal 20'yi ve kripto disi kontratlari atlayan ilk 20 sembol.
Hicbiri daha once kullanilmadi.

**Donem.** ORIJINAL her zamanki gibi `train_frac = 0.8` (verinin en eski %80'i). 30m
penceresi borsada kaydigi icin (`docs/measurements/earliest.md`) yeni sembollerde ayni
oran daha gec bir tarihte keser; bu, orijinallerin ayrilmis %20'sinin takvimine girerdi.
YENI kume bu yuzden **orijinalin kesim aninda** kesilir (`KESIM`): iki kumenin egitim
donemi takvimde ayni, ayrilmis donem ikisinde de okunmaz.

**Kollar** (F1 hicbir parametresi degismeden):

| kol | komisyon | slippage | giris dolusu |
|---|---|---|---|
| F1 | borsa | 2 bps | 1 tick (P1) |
| K2-eski | x1.5 | x1.5 | 1 tick |
| K2-yeni | borsa (kesin) | x3 | 2 tick (P2, `OPEN-37`) |

K2-yeni, sonuc gorulmeden 2026-09-25'te sabitlendi (STRATEGY_SPEC kriter 2).
Yari kesimi: ORIJINAL F1'in medyan giris ani, iki kumede ayni.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.add_reject_e import olcekli
from scripts.backtest import code_version, spec_version
from scripts.levers import IFLAS_ESIKLERI, olc
from scripts.slippage_stres import F1_TABANI
from src.backtest.costs import CostModel, build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun
from src.data import collect

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []
SOGUK_PATH = Path("data/bingx/liquidity_soguk.json")


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def kesim_frac(symbol: str, exchange: str, kesim: pd.Timestamp) -> float | None:
    """`load_symbol`'un 30m'i tam `kesim` aninda (dahil) bitirecegi `train_frac`."""
    d30 = collect.read_parquet(exchange, symbol, "30m")
    if d30.empty:
        return None
    n = int((d30.ts <= kesim).sum())
    return (n + 0.5) / len(d30)  # int(len * frac) == n


def main() -> int:
    p = argparse.ArgumentParser(description="Sembol soguk testi + kriter 2")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/soguk.txt")
    p.add_argument("--csv", default="logs/soguk.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    kumeler: dict[str, list] = {}
    orij = [load_symbol(s, a.exchange, TRAIN_FRAC) for s in liquidity_symbols(20)]
    kumeler["ORIJINAL"] = [d for d in orij if d is not None]
    # Orijinalin kesimi: 30m'i tam pencere olan sembollerin ortak son mumu (ZEC gec listeli).
    kesim = pd.Timestamp(pd.Series([d.ts[-1] for d in kumeler["ORIJINAL"]]).mode()[0]).tz_localize("UTC")
    yeni_sem = json.loads(SOGUK_PATH.read_text(encoding="utf-8"))["symbols"]
    yeni, atlanan = [], []
    for s in yeni_sem:
        f = kesim_frac(s, a.exchange, kesim)
        sd = load_symbol(s, a.exchange, f) if f else None
        (yeni.append(sd) if sd is not None else atlanan.append(s))
        print(f"  {s} frac={f}", file=sys.stderr, flush=True)
    kumeler["YENI"] = yeni

    kollar = {
        "F1": lambda cm: cm,
        "K2-eski": lambda cm: olcekli(cm, Decimal("1.5")),
        "K2-yeni": lambda cm: CostModel(fees=cm.fees, funding=cm.funding,
                                        slippage_bps=cm.slippage_bps * 3),
    }
    kol_kw = {"F1": {}, "K2-eski": {}, "K2-yeni": {"entry_fill": "tick2"}}

    olculer: dict[tuple[str, str], dict] = {}
    trades: dict[tuple[str, str], list] = {}
    for kume, data in kumeler.items():
        isimler = [d.symbol for d in data]
        temel = build_cost_model(isimler, a.exchange)
        for kol, maliyet in kollar.items():
            reset_for_rerun(data)
            c0 = time.time()
            print(f"  {kume} {kol} basliyor...", file=sys.stderr, flush=True)
            res = Backtest(data, maliyet(temel), a.balance, a.k, a.mmr, a.t_rahat,
                           a.t_kritik, False, progress_every=a.progress_every,
                           **F1_TABANI, **kol_kw[kol]).run()
            per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            for t in res.trades:
                per[t.symbol] += t.pnl
            trades[kume, kol] = res.trades
            olculer[kume, kol] = {**olc(res, a.balance), "n_sembol": len(isimler),
                                  "kazanan": sum(1 for v in per.values() if v > 0),
                                  "kacan": res.counters["kacan_giris"],
                                  "sembol_pnl": dict(per)}
            print(f"  {kume} {kol}: {len(res.trades):,} islem, "
                  f"{(time.time() - c0) / 60:.1f} dk", file=sys.stderr, flush=True)

    o1 = sorted(trades["ORIJINAL", "F1"], key=lambda t: t.entry_ts)
    yari = o1[len(o1) // 2].entry_ts
    for k, tr in trades.items():
        olculer[k]["h1"] = sum((t.pnl for t in tr if t.entry_ts < yari), Decimal("0"))
        olculer[k]["h2"] = sum((t.pnl for t in tr if t.entry_ts >= yari), Decimal("0"))

    def surt(m):
        return m["komisyon"] + m["slippage"]

    sutun = [(ku, ko) for ko in kollar for ku in kumeler]
    say("=" * 110)
    say(f"SEMBOL SOGUK TESTI + KRITER 2 · TABAN F1  spec {spec_version()}  kod {code_version()}")
    say("=" * 110)
    say(f"  ORIJINAL {len(kumeler['ORIJINAL'])} sembol · YENI {len(yeni)}/{len(yeni_sem)} sembol"
        + (f"  atlanan: {', '.join(atlanan)}" if atlanan else ""))
    say(f"  egitim sonu (iki kume): {kesim:%Y-%m-%d %H:%M} UTC — ayrilmis donem okunmadi")
    say(f"  yari kesimi (ORIJINAL F1 medyan giris): {yari:%Y-%m-%d %H:%M} UTC")
    say("  K2-eski: komisyon + slippage x1.5 · K2-yeni: komisyon kesin, slippage x3, giris 2 tick")
    say("")
    say(f"  {'olcu':<26}" + "".join(f"{f'{ku[:4]} {ko}':>14}" for ku, ko in sutun))
    for ad, f in (
        ("islem", lambda m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.0f}"),
        ("komisyon", lambda m: f"{m['komisyon']:,.0f}"),
        ("slippage", lambda m: f"{m['slippage']:,.0f}"),
        ("NET PnL", lambda m: f"{m['net']:,.0f}"),
        ("brut / surtunme", lambda m: f"{m['brut_slipsiz'] / surt(m):.3f}"),
        ("kazanan sembol", lambda m: f"{m['kazanan']}/{m['n_sembol']}"),
        ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
        *[(f"iflas: bar < %{e * 100:.0f}", (lambda e: lambda m: f"{m['iflas'][e]:.1f}%")(e))
          for e in IFLAS_ESIKLERI],
        ("likidasyon", lambda m: f"{m['likidasyon']}"),
        ("H1 net", lambda m: f"{m['h1']:,.0f}"),
        ("H2 net", lambda m: f"{m['h2']:,.0f}"),
        ("kacan giris", lambda m: f"{m['kacan']:,}"),
    ):
        say(f"  {ad:<26}" + "".join(f"{f(olculer[k]):>14}" for k in sutun))
    bozuk = [k for k in sutun if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    if bozuk:
        say(f"  ** UYARI: {bozuk} kalemler kapanmadi **")

    say("")
    say("  YENI kume, sembol basina net (F1):")
    for s, v in sorted(olculer["YENI", "F1"]["sembol_pnl"].items(), key=lambda x: x[1]):
        say(f"    {s:<22}{v:>10,.0f}")

    say("")
    say("OZET")
    for k in sutun:
        m = olculer[k]
        say(f"  {k[0]:<9}{k[1]:<8} net {m['net']:>8,.0f} · brut/surt {m['brut_slipsiz'] / surt(m):.3f}"
            f" · kazanan {m['kazanan']}/{m['n_sembol']} · DD {m['maxdd_%']:.1f}% · "
            f"iflas<%10 {m['iflas'][0.10]:.1f}% · H1 {m['h1']:,.0f} · H2 {m['h2']:,.0f}")
    say("  Ayrilmis %20 okunmadi.")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kume": k[0], "kol": k[1], "islem": m["islem"], "brut": m["brut_slipsiz"],
                   "komisyon": m["komisyon"], "slippage": m["slippage"], "net": m["net"],
                   "kazanan": m["kazanan"], "maxdd_%": m["maxdd_%"], "h1": m["h1"], "h2": m["h2"],
                   **{f"iflas_{e}": m["iflas"][e] for e in IFLAS_ESIKLERI}}
                  for k, m in olculer.items()]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
