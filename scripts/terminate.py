"""`OPEN-29` · pozisyon sonlandırma kuralı adaylarının karşılaştırması.

    python -m scripts.terminate

**Soru.** `R-ADD-04` küçültmesi maliyete dönüşte pozisyonu kapatmayı bıraktığından beri
bir pozisyonun tek sonlandırıcısı nihai stop (`1`) veya nihai TP (`0`). Fiyat ortalama
maliyet etrafında salınan pozisyonlar ekle → küçült → ekle döngüsüne giriyor ve
aylarca açık kalabiliyor (ölçüldü: 202 gün, 123 ekleme, 85 küçültme).

`R-EXIT-03` **zaman sınırı tanımıyor** ("günler, haftalar, 3 haftaya kadar gözlem
var"). Yani hiçbir sonlandırma kuralı spec'te yok; bu betik üç adayı ölçer, seçmez.
Varsayılan kol `none` — spec'in yazılı hâli.

| kol | kapatma koşulu |
|---|---|
| `none` | yok (mevcut davranış) |
| `time` | taşıma süresi 21 günü aştı → piyasa emri |
| `structure` | 4h yapısal yön pozisyon açıkken karşı tarafa **döndü** (`R-ZONE-10`) |
| `funding` | birikmiş funding > %10 × nihai TP'ye kalan potansiyel kâr |

**Dört kol aynı veriyi paylaşır.** Semboller bir kez yüklenir, her kol öncesinde
`reset_for_rerun` ile durum sıfırlanır. Maliyet modeli her kolda gerçek (NET) —
`funding` kolu zaten funding olmadan anlamsızdır.

**Optimizasyon değildir.** Eşik aranmıyor: 21 gün spec'in kendi gözlem üst sınırı,
%10 tek bir başlangıç değeri. Kolların karşılaştırılması bir seçim önerisi üretir,
kodun kendisi hiçbir kolu varsayılan yapmaz (CLAUDE.md: self-tuning yasak).
"""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.diagnose import bps, dagilim
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
    say("=" * 96)
    say(metin)
    say("=" * 96)


def sure(dakika: float) -> str:
    """Dakikayı okunur süreye çevirir."""
    return str(pd.Timedelta(minutes=float(dakika))).replace("0 days ", "")


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-29 sonlandırma kuralı karşılaştırması")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--max-hold-days", type=int, default=21)
    p.add_argument("--funding-cap", type=Decimal, default=Decimal("0.10"))
    p.add_argument("--progress-every", type=int, default=50_000)
    p.add_argument("--out", default="logs/terminate.txt")
    p.add_argument("--csv", default="logs/terminate_trades.csv")
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
        sys.exit("hiçbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme = time.time() - t0
    print(f"  yukleme toplam: {yukleme / 60:.1f} dk", file=sys.stderr, flush=True)

    sonuc: dict[str, object] = {}
    sureler: dict[str, float] = {}
    for kol in TERMINATION_RULES:
        reset_for_rerun(data)
        c0 = time.time()
        print(f"\n  === {kol} basliyor ===", file=sys.stderr, flush=True)
        r = Backtest(
            data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
            a.t_rahat, a.t_kritik, a.uyari_adds == "evet",
            progress_every=a.progress_every, terminate=kol,
            max_hold_bars=a.max_hold_days * 1440, funding_cap_ratio=a.funding_cap,
        ).run()
        sureler[kol] = time.time() - c0
        sonuc[kol] = r
        print(f"  {kol}: {len(r.trades):,} islem, {sureler[kol] / 60:.1f} dk",
              file=sys.stderr, flush=True)

    # --- rapor ---------------------------------------------------------------
    baslik(f"OPEN-29 · SONLANDIRMA KURALI ADAYLARI  ·  spec {spec_version()}  ·  "
           f"kod {code_version()}")
    say(f"  yapılandırma: K={a.k} · T_rahat={a.t_rahat} · T_kritik={a.t_kritik} · "
        f"UYARI eklemeyi engeller={a.uyari_adds}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  ·  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i · ayrılmış %20 okunmadı")
    say(f"  eşikler: süre sınırı {a.max_hold_days} gün · funding tavanı "
        f"%{a.funding_cap * 100:.0f} (aranmadı, tek başlangıç değeri)")
    say(f"  süre: yükleme {yukleme / 60:.1f} dk · "
        + " · ".join(f"{k} {v / 60:.1f} dk" for k, v in sureler.items()))
    say("")
    say("  R-EXIT-03 zaman sınırı tanımıyor: dört kolun hiçbiri spec kuralı değildir.")
    say("  `none` mevcut davranıştır ve kodun varsayılanı olarak kalır.")

    # --- 1. ana tablo ---------------------------------------------------------
    baslik("1. KOLLARIN KARSILASTIRMASI")
    say(f"  {'kol':<12} {'işlem':>8} {'beklenti':>10} {'net PnL':>12} {'bitiş bak.':>12} "
        f"{'kazanan':>9} {'sonlandı':>9}")
    for kol in TERMINATION_RULES:
        r = sonuc[kol]
        tr = r.trades
        n = len(tr) or 1
        say(f"  {kol:<12} {len(tr):>8,} "
            f"{np.mean([bps(t, 'pnl') for t in tr]):>9.2f}b "
            f"{sum((t.pnl for t in tr), Decimal('0')):>12,.2f} "
            f"{r.portfolio.balance:>12,.2f} "
            f"{sum(1 for t in tr if t.pnl > 0) / n * 100:>8.1f}% "
            f"{r.counters['terminated']:>9,}")
    say("")
    say("  beklenti = işlem başına net baz puan, giriş notional'i üzerinden.")

    # --- 2. tasima suresi -----------------------------------------------------
    baslik("2. TASIMA SURESI")
    say(f"  {'kol':<12} {'ortalama':>14} {'medyan':>12} {'p90':>12} {'p99':>14} "
        f"{'maks':>14} {'>21 gün':>8}")
    for kol in TERMINATION_RULES:
        tr = sonuc[kol].trades
        h = np.array([t.bars_held for t in tr]) if tr else np.array([0])
        say(f"  {kol:<12} {sure(h.mean()):>14} {sure(np.median(h)):>12} "
            f"{sure(np.percentile(h, 90)):>12} {sure(np.percentile(h, 99)):>14} "
            f"{sure(h.max()):>14} {int((h > 21 * 1440).sum()):>8,}")
    say("")
    say(f"  {'kol':<12} {'toplam pozisyon-dakika':>24} {'küçültme':>10} {'ekleme':>10} "
        f"{'funding':>12}")
    for kol in TERMINATION_RULES:
        r = sonuc[kol]
        tr = r.trades
        say(f"  {kol:<12} {sum(t.bars_held for t in tr):>24,} "
            f"{r.counters['reduce_events']:>10,} {r.counters['adds']:>10,} "
            f"{r.costs.total_funding:>12,.2f}")

    # --- 3. cikis nedenleri ---------------------------------------------------
    baslik("3. CIKIS NEDENI DAGILIMI")
    nedenler = sorted({t.reason for kol in TERMINATION_RULES for t in sonuc[kol].trades})
    say(f"  {'kol':<12} " + "".join(f"{r[:12]:>13}" for r in nedenler))
    for kol in TERMINATION_RULES:
        tr = sonuc[kol].trades
        n = len(tr) or 1
        say(f"  {kol:<12} " + "".join(
            f"{sum(1 for t in tr if t.reason == r) / n * 100:>12.1f}%" for r in nedenler))

    # --- 4. MAE ---------------------------------------------------------------
    baslik("4. MAKSIMUM ALEYHTE SAPMA (MAE · leg oranı)")
    say("  MAE = pozisyonun ortalama maliyetine göre gördüğü en kötü sapma / leg boyu.")
    say("")
    say(f"  {'kol':<12} {'medyan':>9} {'ortalama':>10} {'p90':>9} {'p99':>9} {'maks':>9}")
    for kol in TERMINATION_RULES:
        m = [t.mae_leg for t in sonuc[kol].trades] or [0.0]
        say(f"  {kol:<12} {np.median(m):>9.3f} {np.mean(m):>10.3f} "
            f"{np.percentile(m, 90):>9.3f} {np.percentile(m, 99):>9.3f} {max(m):>9.3f}")
    kenarlar = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5]
    for kol in TERMINATION_RULES:
        m = [t.mae_leg for t in sonuc[kol].trades]
        if not m:
            continue
        say("")
        say(f"  {kol} — n={len(m):,}")
        for et, adet, pay in dagilim(m, kenarlar):
            say(f"    {et:<22} {adet:>8,} {pay:>7.1f}%")

    # --- 5. sonlanan islemler -------------------------------------------------
    baslik("5. SONLANDIRMA KURALIYLA KAPANAN ISLEMLER")
    say("  Kural fiilen neyi kapattı: kapattığı işlemlerin profili.")
    say("")
    say(f"  {'kol':<12} {'adet':>8} {'pay':>8} {'toplam net':>13} {'ort bps':>10} "
        f"{'ort taşıma':>14} {'ort ekleme':>11}")
    for kol in TERMINATION_RULES:
        tr = sonuc[kol].trades
        g = [t for t in tr if t.reason in ("TIME_STOP", "STRUCT_FLIP", "FUNDING_CAP")]
        if not g:
            say(f"  {kol:<12} {0:>8} {'-':>8} {'-':>13} {'-':>10} {'-':>14} {'-':>11}")
            continue
        say(f"  {kol:<12} {len(g):>8,} {len(g) / len(tr) * 100:>7.1f}% "
            f"{sum((t.pnl for t in g), Decimal('0')):>13,.2f} "
            f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f} "
            f"{sure(np.mean([t.bars_held for t in g])):>14} "
            f"{np.mean([t.adds for t in g]):>11.1f}")

    # --- 6. likidasyon / esazamanlilik ---------------------------------------
    baslik("6. RISK SAYACLARI")
    say(f"  {'kol':<12} {'likidasyon':>11} {'KRİTİK küç.':>12} {'min eq/notional':>16} "
        f"{'tepe eşzamanlı':>15} {'maks DD':>9}")
    for kol in TERMINATION_RULES:
        r = sonuc[kol]
        oran = r.portfolio.min_equity_ratio
        say(f"  {kol:<12} {r.counters['liquidations']:>11,} "
            f"{r.counters['deleverage_events']:>12,} "
            f"{(f'{oran * 100:.2f}%' if oran is not None else '-'):>16} "
            f"{max(r.portfolio.concurrent_hist or [0]):>15,} "
            f"{r.portfolio.max_drawdown * 100:>8.1f}%")

    satirlar = []
    for kol in TERMINATION_RULES:
        for t in sonuc[kol].trades:
            satirlar.append({"kol": kol, **t.__dict__})
    pd.DataFrame(satirlar).to_csv(a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
