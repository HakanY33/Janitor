"""Kriter 1 · ayrilmis dilim — TEK SEFER. F1 dondurulmus, 40 sembol.

    python -m scripts.bg scripts.ayrilmis
    python -m scripts.ayrilmis --kesim 2026-01-15 --son "2026-05-08 13:00"   # on ucus (egitim ici)

**Dilim.** Takvimle `KESIM` (2026-05-08 13:00 UTC, orijinalin %80 kesimi) ve sonrasi,
`SON`'a kadar. `SON` = orijinal 20'nin 30m verisinin ortak sonu (2026-09-11 13:00). Soguk
20'nin verisi 09-25'e kadar gidiyor ama iki kume ayni takvimde olculur.

**Isinma.** Motor butun gecmis uzerinde kosar: zone'lar ve durumlari dogal olusur.
`KESIM`'den once hicbir giris dolmaz (`Ayrilmis._try_fill`), bakiye o ana kadar
10.000'de sabit kalir. Bot `KESIM` aninda, zone hafizasiyla acilmis gibi davranir.
Kesimden once kurulmus bekleyen emir kesimden sonra dolabilir; karar kesim oncesi
veriyle verilmisti (CLAUDE.md #3). Ozellikler nedenseldir (`candles.py` kayan medyan,
`shift(1)`), yani gecmisin uzamasi zone'lari degistirmez.

**Kollar.** (a) F1 standart · (b) kriter 2: komisyon kesin, slippage x3, giris P2.
Kumeler ayri portfoylerde, egitimdeki gibi.

**Kabul kriterleri** (STRATEGY_SPEC §8, kosudan once sabitlendi): K1 (a) net > 0 ·
K2 (b) net > 0 · K3 (a) >= 14/20 kazanan · K4 (a) maks DD <= 1.5 x egitim DD'si ·
K5 (a) equity hicbir barda baslangicin %50'sinin altinda degil. Her kume ayri;
ozet: iki kumede de gectiyse GECTI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.levers import olc
from scripts.slippage_stres import F1_TABANI
from scripts.soguk import SOGUK_PATH, kesim_frac
from src.backtest.costs import CostModel, build_cost_model
from src.backtest.engine import Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

KESIM = "2026-05-08 13:00"
SON = "2026-09-11 13:00"
# Egitim diliminin maks DD'si, F1 (logs/soguk.txt, 2026-09-25) — K4'un tabani.
EGITIM_DD = {"ORIJINAL": 11.895086, "YENI": 13.248415}
out: list[str] = []


class Ayrilmis(Backtest):
    """`kesim`'den once giris dolmaz; zone'lar ve bekleyen emirler isinir."""

    def __init__(self, *a, kesim: pd.Timestamp, **kw):
        super().__init__(*a, **kw)
        self.kesim = kesim

    def _try_fill(self, z, sd, ts, *a, **kw):
        if ts < self.kesim:
            return
        super()._try_fill(z, sd, ts, *a, **kw)


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Kriter 1 · ayrilmis dilim (tek sefer)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--kesim", default=KESIM)
    p.add_argument("--son", default=SON)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/ayrilmis.txt")
    p.add_argument("--csv", default="logs/ayrilmis.csv")
    a = p.parse_args()
    kesim = pd.Timestamp(a.kesim, tz="UTC")
    son = pd.Timestamp(a.son, tz="UTC")

    from scripts.measure_ob import liquidity_symbols
    kumeler_sem = {"ORIJINAL": liquidity_symbols(20),
                   "YENI": json.loads(SOGUK_PATH.read_text(encoding="utf-8"))["symbols"]}
    kumeler, atlanan = {}, []
    for kume, ss in kumeler_sem.items():
        kumeler[kume] = []
        for s in ss:
            f = kesim_frac(s, a.exchange, son)
            sd = load_symbol(s, a.exchange, f) if f else None
            (kumeler[kume].append(sd) if sd is not None else atlanan.append(s))
            print(f"  {kume} {s} frac={f}", file=sys.stderr, flush=True)

    kollar = {"a-F1": ({}, lambda cm: cm),
              "b-K2": ({"entry_fill": "tick2"},
                       lambda cm: CostModel(fees=cm.fees, funding=cm.funding,
                                            slippage_bps=cm.slippage_bps * 3))}
    m: dict[tuple[str, str], dict] = {}
    for kume, data in kumeler.items():
        isimler = [d.symbol for d in data]
        temel = build_cost_model(isimler, a.exchange)
        for kol, (kw, maliyet) in kollar.items():
            reset_for_rerun(data)
            c0 = time.time()
            print(f"  {kume} {kol} basliyor...", file=sys.stderr, flush=True)
            res = Ayrilmis(data, maliyet(temel), a.balance, a.k, a.mmr, a.t_rahat,
                           a.t_kritik, False, progress_every=a.progress_every,
                           kesim=kesim, **F1_TABANI, **kw).run()
            erken = [t for t in res.trades if t.entry_ts < kesim]
            if erken:  # isinma sizintisi: kosu gecersiz, sonuc raporlanmaz
                sys.exit(f"HATA: {kume} {kol} kesimden once {len(erken)} giris — kosu gecersiz")
            per: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            ay: dict[str, list] = defaultdict(lambda: [Decimal("0"), 0])
            for t in res.trades:
                per[t.symbol] += t.pnl
                k = f"{pd.Timestamp(t.exit_ts):%Y-%m}"
                ay[k][0] += t.pnl
                ay[k][1] += 1
            m[kume, kol] = {**olc(res, a.balance), "n": len(isimler),
                            "kazanan": sum(1 for v in per.values() if v > 0),
                            "ruin50": res.portfolio.ruin_bars[0.50],
                            "kacan": res.counters["kacan_giris"],
                            "sembol": dict(per), "ay": dict(ay)}
            print(f"  {kume} {kol}: {len(res.trades):,} islem, "
                  f"{(time.time() - c0) / 60:.1f} dk", file=sys.stderr, flush=True)

    betik = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    motor = hashlib.sha256(Path("src/backtest/engine.py").read_bytes()).hexdigest()[:16]
    kirli = git("status", "--porcelain")
    say("=" * 100)
    say("KRITER 1 · AYRILMIS DILIM · TEK SEFER · F1 DONDURULMUS")
    say("=" * 100)
    say(f"  HEAD {git('rev-parse', 'HEAD')}")
    say(f"  calisma agaci: {'temiz' if not kirli else 'KIRLI:'}")
    for line in kirli.splitlines():
        say(f"    {line}")
    say(f"  sha256 scripts/ayrilmis.py {betik} · src/backtest/engine.py {motor}")
    say(f"  dilim: {kesim:%Y-%m-%d %H:%M} -> {son:%Y-%m-%d %H:%M} UTC  (giris yalnizca kesimden sonra)")
    say(f"  ORIJINAL {len(kumeler['ORIJINAL'])}/20 · YENI {len(kumeler['YENI'])}/20"
        + (f"  atlanan: {', '.join(atlanan)}" if atlanan else ""))

    sutun = [(ku, ko) for ko in kollar for ku in kumeler]
    say("")
    say(f"  {'olcu':<28}" + "".join(f"{f'{ku[:4]} {ko}':>14}" for ku, ko in sutun))
    for ad, f in (
        ("islem", lambda x: f"{x['islem']:,}"),
        ("brut fiyat PnL", lambda x: f"{x['brut_slipsiz']:,.0f}"),
        ("komisyon", lambda x: f"{x['komisyon']:,.0f}"),
        ("slippage", lambda x: f"{x['slippage']:,.0f}"),
        ("funding", lambda x: f"{x['funding']:,.0f}"),
        ("NET PnL", lambda x: f"{x['net']:,.0f}"),
        ("brut / surtunme", lambda x: f"{x['brut_slipsiz'] / (x['komisyon'] + x['slippage']):.3f}"),
        ("kazanan sembol", lambda x: f"{x['kazanan']}/{x['n']}"),
        ("maks drawdown", lambda x: f"{x['maxdd_%']:.1f}%"),
        ("bar: equity < %50", lambda x: f"{x['ruin50']:,}"),
        ("likidasyon", lambda x: f"{x['likidasyon']}"),
        ("kacan giris", lambda x: f"{x['kacan']:,}"),
    ):
        say(f"  {ad:<28}" + "".join(f"{f(m[k]):>14}" for k in sutun))
    bozuk = [k for k in sutun if abs(m[k]["uzlasma_farki"]) > Decimal("0.01")]
    if bozuk:
        say(f"  ** UYARI: {bozuk} kalemler kapanmadi **")

    say("")
    say("KABUL KRITERLERI (kosudan once sabitlendi)")
    kriterler = [
        ("K1 net PnL > 0 (a)", "a-F1", lambda x, ku: x["net"] > 0, lambda x, ku: f"{x['net']:,.0f}"),
        ("K2 kriter 2 net > 0 (b)", "b-K2", lambda x, ku: x["net"] > 0, lambda x, ku: f"{x['net']:,.0f}"),
        ("K3 >= 14/20 kazanan (a)", "a-F1", lambda x, ku: x["kazanan"] >= 14,
         lambda x, ku: f"{x['kazanan']}/{x['n']}"),
        ("K4 DD <= 1.5 x egitim (a)", "a-F1",
         lambda x, ku: float(x["maxdd_%"]) <= 1.5 * EGITIM_DD[ku],
         lambda x, ku: f"{x['maxdd_%']:.1f}% / {1.5 * EGITIM_DD[ku]:.2f}%"),
        ("K5 equity >= %50 her bar (a)", "a-F1", lambda x, ku: x["ruin50"] == 0,
         lambda x, ku: f"{x['ruin50']} bar"),
    ]
    say(f"  {'kriter':<32}" + "".join(f"{ku:>26}" for ku in kumeler) + f"{'SONUC':>10}")
    sonuc = {}
    for ad, kol, test, goster in kriterler:
        g = {ku: test(m[ku, kol], ku) for ku in kumeler}
        sonuc[ad] = all(g.values())
        say(f"  {ad:<32}" + "".join(
            f"{('GECTI ' if g[ku] else 'KALDI ') + goster(m[ku, kol], ku):>26}" for ku in kumeler)
            + f"{'GECTI' if sonuc[ad] else 'KALDI':>10}")

    say("")
    say("AYLIK NET PnL (cikis ayina gore, islem PnL'i)")
    aylar = sorted({k for x in m.values() for k in x["ay"]})
    say(f"  {'ay':<10}" + "".join(f"{f'{ku[:4]} {ko}':>18}" for ku, ko in sutun))
    for ay in aylar:
        say(f"  {ay:<10}" + "".join(
            f"{m[k]['ay'].get(ay, [0, 0])[0]:>11,.0f} ({m[k]['ay'].get(ay, [0, 0])[1]:>3})"
            for k in sutun))

    say("")
    say("SEMBOL BASINA NET (a)")
    for ku in kumeler:
        s = sorted(m[ku, "a-F1"]["sembol"].items(), key=lambda x: x[1])
        say(f"  {ku}: " + " · ".join(f"{k.split('/')[0]} {v:,.0f}" for k, v in s))

    say("")
    say("OZET: " + " · ".join(f"{ad.split()[0]} {'GECTI' if v else 'KALDI'}"
                             for ad, v in sonuc.items()))

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"kume": k[0], "kol": k[1], "islem": x["islem"], "brut": x["brut_slipsiz"],
                   "komisyon": x["komisyon"], "slippage": x["slippage"], "net": x["net"],
                   "kazanan": x["kazanan"], "maxdd_%": x["maxdd_%"], "ruin50": x["ruin50"]}
                  for k, x in m.items()]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
