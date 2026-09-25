"""Giriş seviyesi varyantlarının karşılaştırması — aynı yedi kalem, beş varyant.

    python -m scripts.entry_variants

Sabit yapılandırma (teşhis koşusuyla aynı): `K=1.0`, `T_rahat=0.50`, `T_kritik=0.08`,
UYARI eklemeyi engeller. 20 sembol, verinin en eski %80'i, ayrılmış %20 açılmaz.

**Karşılaştırma, optimizasyon değil.** Hiçbir eşik aranmaz, hiçbir varyant "seçilmez"
(CLAUDE.md: self-tuning yasak). Beş varyant aynı veride koşar, aynı kalemler yan yana
konur; hangisinin spec'e gireceği insan kararıdır.

Her varyant **iki kez** koşar: maliyetler sıfırken (BRÜT) ve gerçek maliyetle (NET).
Böylece "varyant kenarı mı değiştiriyor, yoksa yalnızca maliyeti mi" ayrılabilir.

**Varyant derinleştikçe giriş kaybedilir.** Zone `TOUCHED`'a gelip hedefe hiç
dokunulmadan geçersizleşirse giriş olmaz; `armed` (hedef kuruldu) ile `giriş`
(dolduruldu) arasındaki fark bunu ölçer.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.diagnose import bps, dagilim, zero_costs
from src.backtest.costs import CostModel, build_cost_model
from src.backtest.engine import (
    ENTRY_VARIANTS,
    TRAIN_FRAC,
    Backtest,
    load_symbol,
    reset_for_rerun,
)

K = Decimal("1.0")
T_RAHAT = Decimal("0.50")
T_KRITIK = Decimal("0.08")
UYARI_BLOCKS_ADDS = True

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str, ch: str = "=") -> None:
    say("")
    say(ch * 100)
    say(metin)
    say(ch * 100)


def ozet(res, balance: Decimal) -> dict:
    """Bir koşunun karşılaştırma satırı."""
    tr, c = res.trades, res.costs
    notional = sum((t.qty * t.entry_price for t in tr), Decimal("0"))
    maliyet = c.total_fees + c.total_funding + c.total_slippage
    n = len(tr) or 1
    return {
        "armed": res.counters["armed"],
        "giris": res.counters["entries"],
        "unfilled": res.counters["unfilled"],
        "islem": len(tr),
        "band_pos": float(np.mean([t.band_pos for t in tr])) if tr else float("nan"),
        "bps": float(np.mean([bps(t, "pnl") for t in tr])) if tr else float("nan"),
        "gross_bps": float(np.mean([bps(t, "gross") for t in tr])) if tr else float("nan"),
        "rt_bps": float(maliyet / notional * 10000) if notional else 0.0,
        "getiri": (res.portfolio.balance / balance - 1) * 100,
        "bakiye": res.portfolio.balance,
        "maxdd": res.portfolio.max_drawdown * 100,
        "komisyon": c.total_fees, "funding": c.total_funding, "slippage": c.total_slippage,
        "kazanan": sum(1 for t in tr if t.pnl > 0) / n * 100,
        "tp1": sum(1 for t in tr if t.reached_tp1) / n * 100,
        "final_tp": sum(1 for t in tr if t.reason == "FINAL_TP") / n * 100,
        "stop": sum(1 for t in tr if t.reason == "STOP") / n * 100,
        "toplam_pnl": sum((t.pnl for t in tr), Decimal("0")),
    }


def variant_detail(ad: str, brut, net, balance: Decimal, isimler: list[str]) -> None:
    """Bir varyant için yedi kalem."""
    b, n = ozet(brut, balance), ozet(net, balance)
    bt, nt = brut.trades, net.trades
    baslik(f"VARYANT: {ad}", "-")

    say("  1. MALIYETLER ONCESI BRUT PnL (komisyon = funding = slippage = 0)")
    say(f"     {'işlem':<30} {b['islem']:>14,}")
    say(f"     {'brüt PnL toplam':<30} {b['toplam_pnl']:>14,.2f}")
    say(f"     {'başlangıç bakiyeye oran':<30} {b['toplam_pnl'] / balance * 100:>13.1f}%")
    en_iyi = sorted(((s, sum((t.pnl for t in bt if t.symbol == s), Decimal("0")))
                     for s in isimler), key=lambda x: x[1])
    say(f"     en kötü 3 sembol: " + " · ".join(f"{s.split('/')[0]} {v:,.0f}" for s, v in en_iyi[:3]))
    say(f"     en iyi 3 sembol : " + " · ".join(f"{s.split('/')[0]} {v:,.0f}" for s, v in en_iyi[-3:]))

    say("")
    say("  2. MALIYET KALEMLERI (NET)")
    say(f"     {'komisyon':<30} {n['komisyon']:>14,.2f}")
    say(f"     {'funding':<30} {n['funding']:>14,.2f}")
    say(f"     {'slippage':<30} {n['slippage']:>14,.2f}")
    say(f"     {'TOPLAM':<30} "
        f"{n['komisyon'] + n['funding'] + n['slippage']:>14,.2f}")

    say("")
    say("  3. ISLEM BASINA BEKLENTI (bps, giris notional'i uzerinden)")
    say(f"     {'BRÜT beklenti':<30} {b['bps']:>14.2f}")
    say(f"     {'NET beklenti':<30} {n['bps']:>14.2f}")
    say(f"     {'gidiş-dönüş maliyeti':<30} {n['rt_bps']:>14.2f}")
    say(f"     {'BRÜT − maliyet':<30} {b['bps'] - n['rt_bps']:>14.2f}")

    say("")
    say("  4. SONUC ORANLARI (NET)")
    say(f"     {'kazanma':<30} {n['kazanan']:>13.1f}%")
    say(f"     {'TP1 (0.50) ulaşma':<30} {n['tp1']:>13.1f}%")
    say(f"     {'nihai TP (0) ulaşma':<30} {n['final_tp']:>13.1f}%")
    say(f"     {'stop (çapa 1)':<30} {n['stop']:>13.1f}%")
    for neden, adet in Counter(t.reason for t in nt).most_common():
        if neden not in ("STOP", "FINAL_TP"):
            say(f"     {neden.lower():<30} {adet / max(len(nt), 1) * 100:>13.1f}%")

    say("")
    say("  5. ISLEM SONUCLARI DAGILIMI (bps)")
    kenarlar = [-200.0, -100.0, -50.0, -20.0, 0.0, 20.0, 50.0, 100.0, 200.0]
    for etiket, kolon in (("BRÜT", [bps(t, "pnl") for t in bt]),
                          ("NET ", [bps(t, "pnl") for t in nt])):
        if not kolon:
            say(f"     {etiket}: işlem yok")
            continue
        satir = " ".join(f"{adet:>5,}" for _, adet, _ in dagilim(kolon, kenarlar))
        say(f"     {etiket} medyan {np.median(kolon):>7.1f}  ort {np.mean(kolon):>7.1f}  |{satir}")
    say("           kova sınırları (bps): " + " ".join(f"{k:>5.0f}" for k in kenarlar))

    say("")
    say("  6. BASABAS ISLEM SAYISI")
    if b["bps"] <= 0:
        say("     brüt beklenti ≤ 0 → maliyet olmasa da kaybediyor; başabaş tanımsız.")
    elif b["bps"] > n["rt_bps"]:
        say(f"     brüt beklenti ({b['bps']:.2f}) maliyeti ({n['rt_bps']:.2f}) aşıyor.")
    else:
        toplam_brut = float(sum(bps(t, "pnl") for t in bt))
        n_esit = toplam_brut / n["rt_bps"] if n["rt_bps"] else float("inf")
        say(f"     birikmiş brüt kâr {toplam_brut:,.0f} bps · işlem maliyeti "
            f"{n['rt_bps']:.2f} bps")
        say(f"     {'brüt kârı tüketen işlem sayısı':<34} {n_esit:>10,.0f}")
        say(f"     {'fiilen yapılan işlem':<34} {len(nt):>10,}")

    say("")
    say("  7. R-ENTRY-02 DAL KIRILIMI (NET)")
    dallar = {
        "(1) OB'den": [t for t in nt if t.had_ob],
        "(2) FVG'den": [t for t in nt if not t.had_ob and t.had_fvg],
        "(3) çıplak": [t for t in nt if not t.had_ob and not t.had_fvg],
    }
    for dal, g in dallar.items():
        if not g:
            say(f"     {dal:<16} {0:>7} {0.0:>7.1f}%")
            continue
        say(f"     {dal:<16} {len(g):>7,} {len(g) / max(len(nt), 1) * 100:>6.1f}% "
            f"ort {np.mean([bps(t, 'pnl') for t in g]):>7.1f} bps "
            f"kazanan {sum(1 for t in g if t.pnl > 0) / len(g) * 100:>5.1f}%")

    say("")
    say("  EK: giris uretimi ve bant ici konum")
    say(f"     {'hedef kuruldu (armed)':<34} {n['armed']:>10,}")
    say(f"     {'giriş (dolduruldu)':<34} {n['giris']:>10,}")
    say(f"     {'dolum oranı':<34} "
        f"{n['giris'] / max(n['armed'], 1) * 100:>9.1f}%")
    say(f"     {'hedefe hiç dokunulmadan öldü':<34} {n['unfilled']:>10,}")
    say(f"     {'ortalama bant içi konum (0=0.70, 1=0.79)':<34} {n['band_pos']:>10.3f}")


def main() -> int:
    p = argparse.ArgumentParser(description="Giriş varyantları karşılaştırması")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--out", default="logs/entry_variants.txt")
    p.add_argument("--csv", default="logs/entry_variants.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)

    t0 = time.time()
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s:<24} "
              f"{'hazir' if sd is not None else 'ATLANDI'}", file=sys.stderr, flush=True)
    if not data:
        sys.exit("hiçbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme = time.time() - t0

    def kos(rule, costs: CostModel):
        reset_for_rerun(data)
        return Backtest(data, costs, a.balance, K, a.mmr, T_RAHAT, T_KRITIK,
                        UYARI_BLOCKS_ADDS, rule).run()

    sonuclar = []
    for i, rule in enumerate(ENTRY_VARIANTS, 1):
        c0 = time.time()
        brut = kos(rule, zero_costs(isimler))
        net = kos(rule, build_cost_model(isimler, a.exchange))
        sonuclar.append((rule, brut, net))
        # Varyant biter bitmez diske: koşu uzun, yarıda kesilirse bitenler kaybolmasın.
        pd.DataFrame([{"varyant": r.name, **ozet(n, a.balance)}
                      for r, _, n in sonuclar]).to_csv(a.csv, index=False)
        print(f"  [{i}/{len(ENTRY_VARIANTS)}] {rule.name:<36} "
              f"giris {net.counters['entries']:>6,}  "
              f"brut {ozet(brut, a.balance)['bps']:>7.2f} bps  "
              f"net {ozet(net, a.balance)['bps']:>7.2f} bps  "
              f"({time.time() - c0:.0f} sn)", file=sys.stderr, flush=True)

    baslik(f"GIRIS SEVIYESI VARYANTLARI  ·  spec {spec_version()}  ·  kod {code_version()}")
    say(f"  yapılandırma: K={K} · T_rahat={T_RAHAT} · T_kritik={T_KRITIK} · "
        f"UYARI eklemeyi engeller={UYARI_BLOCKS_ADDS}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  ·  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i · ayrılmış %20 okunmadı")
    say(f"  hazırlık {yukleme:.0f} sn · her varyant iki kez koştu (BRÜT + NET)")
    say("  OPEN-27: ekleme daima 1-1 · OPEN-28: KRİTİK'te yarılama")
    say("  Karşılaştırma; hiçbir eşik aranmadı, hiçbir varyant seçilmedi.")
    say("")
    say("  Not: 'bant içi 3 mum' varyantı nedensel uygulanır — pencerede görülen en iyi")
    say("  fiyata limit konur ve fiyat oraya geri gelirse dolar. Geçmişe dönük dolum")
    say("  look-ahead olurdu (CLAUDE.md #3); dolmayan girişler sayaçta görünür.")

    # --- karsilastirma tablosu ----------------------------------------------
    baslik("KARSILASTIRMA — brut ve net beklenti yan yana")
    say(f"  {'varyant':<34} {'armed':>7} {'giriş':>7} {'dolum':>7} {'bant':>6} "
        f"{'BRÜT bps':>10} {'NET bps':>9} {'maliyet':>9} {'NET getiri':>11} {'maxDD':>8}")
    for rule, brut, net in sonuclar:
        b, n = ozet(brut, a.balance), ozet(net, a.balance)
        say(f"  {rule.name:<34} {n['armed']:>7,} {n['giris']:>7,} "
            f"{n['giris'] / max(n['armed'], 1) * 100:>6.1f}% {n['band_pos']:>6.3f} "
            f"{b['bps']:>10.2f} {n['bps']:>9.2f} {n['rt_bps']:>9.2f} "
            f"{n['getiri']:>10.1f}% {n['maxdd']:>7.1f}%")
    say("")
    say("  armed = zone 0.70'e gelip hedef kuruldu · giriş = hedef dolduruldu")
    say("  bant  = dolumun ortalama bant içi konumu (0.0 = 0.70 · 1.0 = 0.79)")
    say("  BRÜT bps = sıfır maliyetli koşunun işlem başına beklentisi")

    for rule, brut, net in sonuclar:
        variant_detail(rule.name, brut, net, a.balance, isimler)

    pd.DataFrame([{"varyant": r.name, **ozet(n, a.balance)} for r, _, n in sonuclar]).to_csv(
        a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
