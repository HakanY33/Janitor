"""Backtest koşusu ve §8 zorunlu sayaç raporu.

    python -m scripts.backtest                       # liquidity.json'daki 20 sembol
    python -m scripts.backtest --symbols NEAR/USDT:USDT
    python -m scripts.backtest --mmr 0.01 --slippage-bps 5

Spec: §8 (zorunlu sayaçlar, maliyet modeli, intrabar belirsizliği).
CLAUDE.md: "Backtest sonuçları `spec_version` ve `code_version` olmadan raporlanmaz."

**Veri disiplini.** Her sembolün yalnızca en eski %80'i okunur; ayrılmış %20 açılmaz.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import TRAIN_FRAC, run_backtest
from src.data import collect

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line)


def baslik(metin: str) -> None:
    say("")
    say("=" * 78)
    say(metin)
    say("=" * 78)


def spec_version() -> str:
    m = re.search(r"\|\s*\*\*Versiyon\*\*\s*\|\s*(\S+)", Path("docs/STRATEGY_SPEC.md").read_text(encoding="utf-8"))
    return m.group(1) if m else "bilinmiyor"


def code_version() -> str:
    """Git yalnızca **okunur** (CLAUDE.md #11)."""
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, check=True).stdout.strip()
        kirli = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, check=True).stdout.strip()
        return f"{h}{'+kirli' if kirli else ''}"
    except Exception:
        return "bilinmiyor"


def correlation_report(symbols: list[str], exchange: str) -> tuple[float, dict]:
    """§8 · pozisyonlar arası korelasyon → efektif pozisyon sayısı.

    30m kapanış getirileri üzerinden ortalama ikili korelasyon. Efektif sayı
    `k / (1 + (k−1)·ρ)`: yüksek korelasyonda k pozisyon k bağımsız risk değildir.
    """
    seri = {}
    for s in symbols:
        df = collect.read_parquet(exchange, s, "30m")
        if df.empty:
            continue
        df = df.iloc[: int(len(df) * TRAIN_FRAC)]
        seri[s] = pd.Series(np.log(df.close.to_numpy()), index=df.ts).diff()
    if len(seri) < 2:
        return float("nan"), {}
    M = pd.DataFrame(seri).dropna()
    C = M.corr().to_numpy()
    ust = C[np.triu_indices_from(C, k=1)]
    rho = float(np.nanmean(ust))
    return rho, {"min": float(np.nanmin(ust)), "max": float(np.nanmax(ust)), "n": len(ust)}


def main() -> int:
    p = argparse.ArgumentParser(description="OTE backtest + zorunlu sayaçlar")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--k", type=Decimal, default=Decimal("1.0"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--slippage-bps", type=Decimal, default=None)
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--out", default="logs/backtest.txt")
    p.add_argument("--trades-csv", default="logs/backtest_trades.csv")
    a = p.parse_args()

    if a.symbols:
        symbols = a.symbols
    else:
        from scripts.measure_ob import liquidity_symbols
        symbols = liquidity_symbols(a.limit)

    res, skipped = run_backtest(
        symbols, a.exchange, a.train_frac, a.balance, a.k, a.mmr, a.slippage_bps,
    )
    pf, c, tr = res.portfolio, res.costs, res.trades

    baslik(f"BACKTEST  ·  spec {spec_version()}  ·  kod {code_version()}")
    say(f"  sembol: {len(symbols) - len(skipped)}/{len(symbols)}"
        + (f"  ·  atlanan (1m veri yok): {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i  ·  ayrılmış %20 okunmadı")
    say(f"  geometri/tespit 30m · durum geçişleri 1m (R-ZONE-09)")
    say(f"  başlangıç bakiye {a.balance}  ·  K={a.k} (R-ENTRY-03)  ·  MMR={a.mmr}")

    # --- sonuc ---------------------------------------------------------------
    son = pf.balance
    getiri = (son / pf.start_balance - 1) * 100
    baslik("SONUC")
    say(f"  {'bitiş bakiyesi':<34} {son:>14,.2f}")
    say(f"  {'getiri':<34} {getiri:>13.1f}%")
    say(f"  {'işlem sayısı':<34} {len(tr):>14,}")
    if tr:
        kazanan = [t for t in tr if t.pnl > 0]
        say(f"  {'kazanan oranı':<34} {len(kazanan) / len(tr) * 100:>13.1f}%")
        say(f"  {'ortalama işlem PnL':<34} {sum(t.pnl for t in tr) / len(tr):>14,.2f}")
        say(f"  {'toplam brüt PnL':<34} {sum(t.gross for t in tr):>14,.2f}")

    # --- zorunlu sayaclar (§8) ------------------------------------------------
    baslik("ZORUNLU SAYACLAR (§8)")
    say(f"  {'maksimum drawdown':<34} {pf.max_drawdown * 100:>13.1f}%")

    say("")
    say("  Likidasyona en yakın mesafe (R-RISK-05 kalibrasyonu)")
    oran = pf.min_equity_ratio
    if oran is None:
        say("    pozisyon açılmadı — mesafe tanımsız")
    else:
        say(f"    {'min(equity / toplam notional)':<32} {oran * 100:>13.2f}%   <- MMR'siz ölçü")
        say(f"    {'min likidasyon mesafesi (MMR=' + str(a.mmr) + ')':<32} {pf.min_liq_distance * 100:>13.2f}%")
        bolge = ("KRITIK" if pf.min_liq_distance <= Decimal("0.15")
                 else "UYARI" if pf.min_liq_distance <= Decimal("0.50") else "RAHAT")
        say(f"    {'en kötü anda R-RISK-05 bölgesi':<32} {bolge:>14}")

    say("")
    say('  "Gerçek parada likide olurduk" sayacı')
    say(f"    {'koşu içi likidasyon olayı':<32} {pf.liquidation_events:>14}")
    if oran is not None:
        say("    MMR duyarlılığı — min oran bu eşiğin altına indiyse likidasyon:")
        for mmr in (Decimal("0.004"), Decimal("0.005"), Decimal("0.01"), Decimal("0.025")):
            say(f"      MMR {mmr * 100:>5.2f}%  ->  {'LIKIDE' if oran <= mmr else 'hayatta':>8}"
                f"   (marj {(oran - mmr) * 100:>7.2f} puan)")
        say("    Not: MMR borsadan çekilemedi (kimlik doğrulama ister), bu yüzden tek")
        say("    sabit yerine duyarlılık verilir. Birincil ölçü MMR'siz olan min orandır.")

    say("")
    say("  Eşzamanlı açık pozisyon dağılımı (R-RISK-01 tavanı ne sıklıkla bağlıyor)")
    toplam_bar = sum(pf.concurrent_hist.values()) or 1
    for k in sorted(pf.concurrent_hist):
        pay = pf.concurrent_hist[k] / toplam_bar * 100
        if pay >= 0.01:
            say(f"    {k:>2} pozisyon  {pf.concurrent_hist[k]:>12,} mum  {pay:>6.2f}%")
    say(f"    {'maksimum eşzamanlı':<32} {max(pf.concurrent_hist, default=0):>14}")

    rho, detay = correlation_report([s for s in symbols if s not in skipped], a.exchange)
    say("")
    say("  Pozisyonlar arası korelasyon (efektif pozisyon sayısı)")
    if detay:
        say(f"    {'ortalama ikili korelasyon (30m)':<32} {rho:>14.3f}")
        say(f"    {'aralık':<32} {detay['min']:>7.3f} .. {detay['max']:.3f}  ({detay['n']} çift)")
        for k in (2, 5, 10):
            eff = k / (1 + (k - 1) * rho) if rho > -1 else float(k)
            say(f"    {k:>2} pozisyon  ->  efektif {eff:>5.2f} bağımsız pozisyon")
    else:
        say("    tek sembol — korelasyon tanımsız")

    say("")
    belirsiz = sum(1 for t in tr if t.ambiguous)
    pay = belirsiz / len(tr) * 100 if tr else 0.0
    yorum = ("sonuç güvenilir" if pay < 5 else
             "dikkatli yorumlanır, duyarlılık analizi gerekir" if pay <= 20 else
             "SONUC KULLANILAMAZ — tick verisine geçilmeli")
    say(f"  {'belirsiz (ambiguous) işlem oranı':<34} {pay:>13.2f}%   {yorum}")
    say(f"  {'belirsiz mum olayı':<34} {res.counters['ambiguous_bars']:>14,}")

    say("")
    say(f"  {'toplam funding maliyeti':<34} {c.total_funding:>14,.2f}")
    say(f"    {'ölçülen funding':<32} {c.funding_measured:>14,.2f}")
    say(f"    {'atanan funding (kapsam dışı)':<32} {c.funding_imputed:>14,.2f}")
    say(f"    {'funding kapsama oranı':<32} {c.funding_coverage * 100:>13.1f}%")
    say("    Kapsam dışı anlarda oran sıfır değil, sembolün |oran| medyanı aleyhte atanır.")

    # --- maliyet modeli -------------------------------------------------------
    baslik("MALIYET MODELI (§8 — zorunlu)")
    say(f"  {'toplam komisyon (taker)':<34} {c.total_fees:>14,.2f}")
    say(f"  {'toplam funding':<34} {c.total_funding:>14,.2f}")
    say(f"  {'toplam slippage':<34} {c.total_slippage:>14,.2f}")
    say(f"  {'maliyet toplamı':<34} {c.total_fees + c.total_funding + c.total_slippage:>14,.2f}")
    say(f"  Komisyon borsanın yayınladığı orandan (data/{a.exchange}/fees.json).")
    say(f"  Slippage {c.slippage_bps} bps — borsa yayını DEĞİL, varsayım; ayrı raporlanır.")

    # --- kural akisi ----------------------------------------------------------
    baslik("KURAL AKISI")
    k = res.counters
    say(f"  {'üretilen zone':<34} {k['zones_total']:>14,}")
    say(f"  {'0.50 gördü (PRIMED)':<34} {k['zones_primed']:>14,}")
    say(f"  {'0.70 gördü (TOUCHED = aday)':<34} {k['zones_touched']:>14,}")
    say(f"  {'giriş':<34} {k['entries']:>14,}")
    say(f"    {'R-RISK-01 reddi (notional tavanı)':<32} {k['rejected_risk01']:>14,}")
    say(f"    {'R-RISK-05 reddi (liq tamponu)':<32} {k['rejected_risk05']:>14,}")
    say(f"    {'R-RISK-03 reddi (günlük zarar)':<32} {k['rejected_risk03']:>14,}")
    say("")
    say(f"  {'ekleme (R-ADD-03, 1-1)':<34} {k['adds']:>14,}")
    for kod, ad in (("a", "ADD-REJECT-A (0.50 kâr bırakmıyor)"),
                    ("b", "ADD-REJECT-B (notional tavanı)"),
                    ("c", "ADD-REJECT-C (OB delinmiş)"),
                    ("d", "ADD-REJECT-D (liq tamponu)")):
        say(f"    {ad:<32} {k['add_reject_' + kod]:>14,}")
    say("    (red sayaçları mum başına değerlendirmedir, ayrı ekleme fırsatı değil)")
    say("")
    say("  R-ENTRY-05 · girişte gösterge var mıydı")
    say(f"    {'uygun OB ile giriş':<32} {k['entries_with_ob']:>14,}")
    say(f"    {'uygun FVG ile giriş':<32} {k['entries_with_fvg']:>14,}")
    say("    R-ENTRY-02 (3) gereği gösterge girişi kapılamaz — bu sayılar girişin")
    say("    niteliğini gösterir, sayısını değil.")
    say("")
    say(f"  {'mum içi çakışma: öldürme kazandı':<34} {k['kill_wins']:>14,}")
    say(f"  {'mum içi çakışma: ilerleme atlandı':<34} {k['skipped_progress']:>14,}")

    if tr:
        baslik("CIKIS NEDENLERI")
        say(f"  {'neden':<14} {'adet':>7} {'pay':>7} {'toplam PnL':>14} {'ort PnL':>12}")
        for neden, adet in Counter(t.reason for t in tr).most_common():
            grup = [t for t in tr if t.reason == neden]
            top = sum(t.pnl for t in grup)
            say(f"  {neden:<14} {adet:>7,} {adet / len(tr) * 100:>6.1f}% {top:>14,.2f} "
                f"{top / adet:>12,.2f}")

        baslik("SEMBOL BAZINDA")
        say(f"  {'sembol':<24} {'işlem':>7} {'PnL':>14} {'kazanan':>9}")
        for s in sorted({t.symbol for t in tr}):
            grup = [t for t in tr if t.symbol == s]
            kaz = sum(1 for t in grup if t.pnl > 0)
            say(f"  {s:<24} {len(grup):>7,} {sum(t.pnl for t in grup):>14,.2f} "
                f"{kaz / len(grup) * 100:>8.1f}%")

        pd.DataFrame([t.__dict__ for t in tr]).to_csv(a.trades_csv, index=False)
        say("")
        say(f"  işlem dökümü -> {a.trades_csv}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
