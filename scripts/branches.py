"""`R-ENTRY-02` dal analizi — hangi dal kar ediyor, gosterge kapisi ne yapiyor.

    python -m scripts.bg scripts.branches --terminate structure

Ikisi birden olculur:

* **(b)** Secilen `OPEN-29` sonlandirma kuraliyla dal basina brut/net beklenti,
  kazanma orani ve **sembol tutarliligi**.
* **(c)** `R-ENTRY-02` (3) kapali varyant: yalnizca bantta uygun OB veya FVG bulunan
  zone'lara girilir. Bu **spec'ten sapar** — spec "gosterge yoksa 0.70 temasi gecerli
  giristir" der. Olculen sey bir spec adayidir, secim degil.

**Sembol tutarliligi neden.** Kripto sembolleri yuksek korelasyonlu; havuzlanmis
ortalama bagimsiz gozlem sayisini sisirir (`docs/measurements/hypotheses.md`, not 1).
Durust olcu, dalin isaretinin kac sembolde ayni oldugudur.

**Brut ve net ayri kosulardir.** Sifir maliyetli kosu farkli bir yol izler (maliyet
cikislari ve likidasyonu degistirir), bu yuzden islem sayilari birebir tutmaz. Iki
sutun yan yana okunur, satir satir cikarilmaz.

Ayrilmis %20 hicbir kolda okunmaz.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.diagnose import bps, zero_costs
from src.backtest.costs import build_cost_model
from src.backtest.engine import (
    TERMINATION_RULES,
    TRAIN_FRAC,
    Backtest,
    load_symbol,
    reset_for_rerun,
)

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
    say("=" * 100)
    say(metin)
    say("=" * 100)


DALLAR = ("(1) OB'den", "(2) FVG'den", "(3) ciplak 0.70")


def dal_of(t) -> str:
    """R-ENTRY-02 onceligi: OB varsa OB, yoksa FVG, o da yoksa ciplak."""
    return DALLAR[0] if t.had_ob else DALLAR[1] if t.had_fvg else DALLAR[2]


def grupla(trades) -> dict:
    g = {d: [] for d in DALLAR}
    for t in trades:
        g[dal_of(t)].append(t)
    return g


def tutarlilik(trades, alan: str, min_islem: int = 10):
    """Dalin isareti kac sembolde havuzlanmis isaretle ayni.

    `min_islem`'den az islemi olan sembol sayilmaz — 2 islemli bir sembolun isareti
    bilgi degil gurultudur. Donen: (ayni isaretli sembol, degerlendirilen sembol).
    """
    if not trades:
        return 0, 0
    havuz = np.sign(np.mean([bps(t, alan) for t in trades]))
    per = defaultdict(list)
    for t in trades:
        per[t.symbol].append(bps(t, alan))
    gecerli = {s: v for s, v in per.items() if len(v) >= min_islem}
    ayni = sum(1 for v in gecerli.values() if np.sign(np.mean(v)) == havuz)
    return ayni, len(gecerli)


def main() -> int:
    p = argparse.ArgumentParser(description="R-ENTRY-02 dal analizi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--terminate", choices=TERMINATION_RULES, required=True,
                   help="OPEN-29 kosusunda secilen sonlandirma kurali")
    p.add_argument("--min-islem", type=int, default=10,
                   help="sembol tutarliliginda sayilmak icin gereken islem sayisi")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/branches.txt")
    p.add_argument("--csv", default="logs/branches.csv")
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

    def kos(costs, etiket: str, require_indicator: bool = False):
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  {etiket} basliyor...", file=sys.stderr, flush=True)
        r = Backtest(data, costs, a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik,
                     a.uyari_adds == "evet", progress_every=a.progress_every,
                     terminate=a.terminate, require_indicator=require_indicator).run()
        print(f"  {etiket}: {len(r.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)
        return r

    brut = kos(zero_costs(isimler), "BRUT")
    net = kos(build_cost_model(isimler, a.exchange), "NET")
    kapi = kos(build_cost_model(isimler, a.exchange), "KAPI (R-ENTRY-02 (3) kapali)",
               require_indicator=True)

    baslik(f"R-ENTRY-02 DAL ANALIZI  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr}")
    say(f"  OPEN-29 sonlandirma kurali: {a.terminate}")
    say(f"  yukleme {yukleme / 60:.1f} dk")

    # --- (b) dal kirilimi ----------------------------------------------------
    gb, gn = grupla(brut.trades), grupla(net.trades)
    baslik("(b) DAL BASINA BRUT VE NET - secilen sonlandirma kuraliyla")
    say("  BRUT ve NET ayri kosulardir; islem sayilari birebir tutmaz.")
    say(f"  tutarlilik = dalin isaretinin ayni oldugu sembol / >= {a.min_islem} "
        f"islemi olan sembol")
    say("")
    say(f"  {'dal':<18} {'NET islem':>10} {'pay':>7} {'BRUT bps':>10} {'NET bps':>9} "
        f"{'kazanan':>9} {'TP1':>7} {'toplam net':>13} {'tutarlilik':>12}")
    n_net = len(net.trades) or 1
    satirlar = []
    for d in DALLAR:
        b, nn = gb[d], gn[d]
        if not nn:
            say(f"  {d:<18} {0:>10} {'-':>7} {'-':>10} {'-':>9} {'-':>9} {'-':>7} "
                f"{'-':>13} {'-':>12}")
            continue
        brut_bps = float(np.mean([bps(t, "gross") for t in b])) if b else float("nan")
        net_bps = float(np.mean([bps(t, "pnl") for t in nn]))
        ayni, gecerli = tutarlilik(nn, "pnl", a.min_islem)
        kazanan = sum(1 for t in nn if t.pnl > 0) / len(nn) * 100
        toplam = sum((t.pnl for t in nn), Decimal("0"))
        say(f"  {d:<18} {len(nn):>10,} {len(nn) / n_net * 100:>6.1f}% "
            f"{brut_bps:>10.1f} {net_bps:>9.1f} {kazanan:>8.1f}% "
            f"{sum(1 for t in nn if t.reached_tp1) / len(nn) * 100:>6.1f}% "
            f"{toplam:>13,.2f} {f'{ayni}/{gecerli}':>12}")
        satirlar.append({"dal": d, "net_islem": len(nn), "brut_islem": len(b),
                         "brut_bps": brut_bps, "net_bps": net_bps,
                         "kazanan_%": kazanan, "toplam_net": toplam,
                         "tutarlilik": f"{ayni}/{gecerli}"})
    say("")
    say("  Not: dal girisin niteligidir, on kosulu degil. R-ENTRY-02 (3) geregi")
    say("  gosterge girisi kapilamaz - uc dalin toplami tum girislere esittir.")

    # --- (c) gosterge kapisi -------------------------------------------------
    def ozet(r, ad: str) -> dict:
        pf, c = r.portfolio, r.costs
        return {"kol": ad, "islem": len(r.trades),
                "net_getiri_%": float((pf.balance / pf.start_balance - 1) * 100),
                "maxdd_%": float(pf.max_drawdown * 100),
                "maliyet": c.total_fees + c.total_funding + c.total_slippage,
                "komisyon": c.total_fees, "funding": c.total_funding,
                "slippage": c.total_slippage,
                "likidasyon": r.counters["liquidations"],
                "atlanan_ciplak": r.counters["no_indicator_skipped"]}

    tam = ozet(net, "R-ENTRY-02 tam (spec)")
    kapali = ozet(kapi, "R-ENTRY-02 (3) kapali")
    baslik("(c) GOSTERGE KAPISI - yalnizca OB/FVG girisleri")
    say("  SPEC ADAYI: spec (3) maddesiyle ciplak 0.70 temasini gecerli giris sayar.")
    say("  Bu kol o maddeyi kapatir ve olcer; hicbir esik aranmadi.")
    say("")
    say(f"  {'kol':<24} {'islem':>9} {'net getiri':>12} {'maxDD':>8} {'maliyet':>13} "
        f"{'likidasyon':>11} {'atlanan ciplak':>15}")
    for m in (tam, kapali):
        say(f"  {m['kol']:<24} {m['islem']:>9,} {m['net_getiri_%']:>11.1f}% "
            f"{m['maxdd_%']:>7.1f}% {m['maliyet']:>13,.2f} {m['likidasyon']:>11,} "
            f"{m['atlanan_ciplak']:>15,}")
    say("")
    say(f"  {'kol':<24} {'komisyon':>13} {'funding':>12} {'slippage':>13} "
        f"{'islem basina':>13}")
    for m in (tam, kapali):
        say(f"  {m['kol']:<24} {m['komisyon']:>13,.2f} {m['funding']:>12,.2f} "
            f"{m['slippage']:>13,.2f} "
            f"{(m['maliyet'] / m['islem'] if m['islem'] else 0):>13,.2f}")

    pd.DataFrame(satirlar).to_csv(a.csv, index=False)
    pd.DataFrame([tam, kapali]).to_csv(a.csv.replace(".csv", "_kol.csv"), index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
