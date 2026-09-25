"""Teşhis koşusu — tek yapılandırma, yalnızca ölçüm.

    python -m scripts.diagnose

Yapılandırma sabittir ve değiştirilmez: `K=0.25`, `T_rahat=0.50`, `T_kritik=0.08`,
UYARI eklemeyi **engellemez**. 20 sembol, verinin en eski %80'i, ayrılmış %20 açılmaz.

**Optimizasyon yok, parametre araması yok.** Bu betik hiçbir eşiği aramaz ve hiçbir
sonucu "iyileştirmez" (CLAUDE.md: self-tuning yasak). Tek işi, stratejinin maliyetler
olmadan ne ürettiğini ve maliyetlerin bunun neresini aldığını ölçmektir.

**İki koşu, tek veri.** Aynı hazırlanmış veri üzerinde:

| Koşu | Komisyon | Funding | Slippage | Ne verir |
|---|---|---|---|---|
| **BRÜT** | 0 | 0 | 0 | Sürtünmesiz PnL — stratejinin ham çıktısı |
| **NET** | borsa oranı | gerçek geçmiş | varsayım | Gerçekçi sonuç ve maliyet kalemleri |

İki koşunun **işlem kümesi aynı değildir**: maliyet equity'yi değiştirir, equity
boyutu değiştirir (R-ENTRY-03), boyut risk bölgesini değiştirir (R-RISK-05). Bu yüzden
brüt koşunun işlem sayısı net koşununkinden farklı çıkabilir ve iki tablo yan yana
okunur, birbirinden çıkarılmaz.

**Baz puan tabanı.** İşlem başına getiri, o işlemin **giriş notional'i** üzerinden
ölçülür: `bps = PnL / (qty × giriş fiyatı) × 10.000`. `qty` eklemeler sonrası ulaşılan
en büyük miktardır; taban bu yüzden işlemin gördüğü en büyük sermayedir.
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
from src.backtest.costs import CostModel, Fees, build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

K = Decimal("0.25")
T_RAHAT = Decimal("0.50")
T_KRITIK = Decimal("0.08")
UYARI_BLOCKS_ADDS = False

# Konsol Windows'ta cp1254 olabiliyor; rapor metni UTF-8. Dosyaya yazim zaten UTF-8,
# ekrana basarken kodlanamayan karakter kosuyu dusurmesin diye degistirilir.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # yeniden yonlendirilmis cikti
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


def bps(trade, alan: str = "gross") -> float:
    """İşlemin getirisi, giriş notional'i üzerinden baz puan."""
    taban = trade.qty * trade.entry_price
    return float(getattr(trade, alan) / taban * 10000) if taban else 0.0


def zero_costs(symbols: list[str]) -> CostModel:
    """Sürtünmesiz maliyet modeli: komisyon 0, funding yok, slippage 0."""
    return CostModel(
        fees={s: Fees(Decimal("0"), Decimal("0")) for s in symbols},
        funding={},  # sembol bulunamayınca funding_cost 0 döner
        slippage_bps=Decimal("0"),
    )


def dagilim(values: list[float], kenarlar: list[float]) -> list[tuple[str, int, float]]:
    """Histogram: (etiket, adet, pay%)."""
    n = len(values) or 1
    out_ = []
    for lo, hi in zip([-np.inf] + kenarlar, kenarlar + [np.inf]):
        adet = sum(1 for v in values if lo <= v < hi)
        # .2f: kovalar hem bps (yuzler) hem leg orani (0.1, 0.25) icin kullaniliyor;
        # tam sayi bicimi kesirli sinirlari hepsini "0" yapip etiketleri okunmaz kiliyordu.
        etiket = (f"      < {hi:>8.2f}" if lo == -np.inf else
                  f"   >= {lo:>8.2f}" if hi == np.inf else
                  f"{lo:>8.2f} .. {hi:>8.2f}")
        out_.append((etiket, adet, adet / n * 100))
    return out_


def main() -> int:
    p = argparse.ArgumentParser(description="Teşhis koşusu — sadece ölçüm")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=K)
    p.add_argument("--t-rahat", type=Decimal, default=T_RAHAT)
    p.add_argument("--t-kritik", type=Decimal, default=T_KRITIK)
    p.add_argument("--uyari-adds", choices=["evet", "hayir"],
                   default="evet" if UYARI_BLOCKS_ADDS else "hayir",
                   help="UYARI bandi eklemeyi de engellesin mi (R-RISK-05)")
    p.add_argument("--progress-every", type=int, default=50_000,
                   help="kac mumda bir ilerleme satiri (stderr); 0 = kapali")
    p.add_argument("--out", default="logs/diagnose.txt")
    p.add_argument("--csv", default="logs/diagnose_trades.csv")
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
              f"{'hazir' if sd is not None else 'ATLANDI':<8} {time.time() - c0:>6.1f} sn"
              + (f"  1m {len(sd.ts):>9,}  zone {len(sd.zones):>4}" if sd else ""),
              file=sys.stderr, flush=True)
    if not data:
        sys.exit("hiçbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme_sn = time.time() - t0
    print(f"  yukleme toplam: {yukleme_sn / 60:.1f} dk", file=sys.stderr, flush=True)

    # Faz zamanlari ayri tutulur: "hazirlik" etiketi eskiden tum kosuyu olcuyordu ve
    # yavaslamanin yuklemede mi motorda mi oldugu raporda gorunmuyordu.
    sureler: dict[str, float] = {"yukleme": yukleme_sn}

    def kos(costs: CostModel, etiket: str):
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  {etiket} basliyor...", file=sys.stderr, flush=True)
        r = Backtest(data, costs, a.balance, a.k, a.mmr, a.t_rahat, a.t_kritik,
                     a.uyari_adds == "evet", progress_every=a.progress_every).run()
        sureler[etiket] = time.time() - c0
        print(f"  {etiket}: {len(r.trades):,} islem, {sureler[etiket] / 60:.1f} dk",
              file=sys.stderr, flush=True)
        return r

    brut = kos(zero_costs(isimler), "BRUT")
    net = kos(build_cost_model(isimler, a.exchange), "NET")

    baslik(f"TESHIS KOSUSU  ·  spec {spec_version()}  ·  kod {code_version()}")
    say(f"  yapılandırma: K={a.k} · T_rahat={a.t_rahat} · T_kritik={a.t_kritik} · "
        f"UYARI eklemeyi engeller={a.uyari_adds}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  ·  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i · ayrılmış %20 okunmadı")
    say(f"  başlangıç bakiye {a.balance} · MMR={a.mmr}")
    say(f"  süre: yükleme {sureler['yukleme'] / 60:.1f} dk · BRÜT koşu "
        f"{sureler['BRUT'] / 60:.1f} dk · NET koşu {sureler['NET'] / 60:.1f} dk · "
        f"toplam {(time.time() - t0) / 60:.1f} dk")
    say("  OPEN-27 (daraltıldı): ekleme çarpanı 1-1/1-3/1-5/1-10 arasından,")
    say("    maliyeti 0.79'un ötesine çeken en küçüğü; hiçbiri çekmezse ekleme yok.")
    say("  OPEN-28: KRİTİK'te yarılama.")
    say("  R-ADD-04: maliyete dönüş çıkış değil — pozisyon K tabanına indirilir,")
    say("    kalan kısım stop 1 / ilk TP 0.50 / nihai TP 0 ile devam eder (bölüm 10).")
    say("  Optimizasyon yapılmadı; hiçbir eşik aranmadı.")

    # --- 1. maliyetler oncesi brut PnL ---------------------------------------
    baslik("1. MALIYETLER ONCESI BRUT PnL  (komisyon = funding = slippage = 0)")
    bt, nt = brut.trades, net.trades
    b_top = sum((t.pnl for t in bt), Decimal("0"))
    say(f"  {'işlem sayısı':<34} {len(bt):>16,}")
    say(f"  {'brüt PnL toplam':<34} {b_top:>16,.2f}")
    say(f"  {'başlangıç bakiyeye oran':<34} {b_top / a.balance * 100:>15.1f}%")
    say(f"  {'bitiş bakiyesi (sürtünmesiz)':<34} {brut.portfolio.balance:>16,.2f}")
    say("")
    say("  Sembol başına brüt PnL:")
    say(f"  {'sembol':<24} {'işlem':>7} {'brüt PnL':>15} {'işlem başına':>14} {'bps':>9}")
    for s in isimler:
        g = [t for t in bt if t.symbol == s]
        if not g:
            say(f"  {s:<24} {0:>7} {'-':>15} {'-':>14} {'-':>9}")
            continue
        tot = sum((t.pnl for t in g), Decimal("0"))
        say(f"  {s:<24} {len(g):>7,} {tot:>15,.2f} {tot / len(g):>14,.2f} "
            f"{np.mean([bps(t, 'pnl') for t in g]):>9.1f}")

    # --- 2. maliyet kalemleri -------------------------------------------------
    c = net.costs
    toplam_maliyet = c.total_fees + c.total_funding + c.total_slippage
    baslik("2. MALIYET KALEMLERI (NET kosu)")
    say(f"  {'komisyon (taker, borsa oranı)':<34} {c.total_fees:>16,.2f}")
    say(f"  {'funding':<34} {c.total_funding:>16,.2f}")
    say(f"    {'ölçülen':<32} {c.funding_measured:>16,.2f}")
    say(f"    {'atanan (kapsam dışı)':<32} {c.funding_imputed:>16,.2f}")
    say(f"    {'kapsama oranı':<32} {c.funding_coverage * 100:>15.1f}%")
    say(f"  {'slippage (varsayım, ' + str(c.slippage_bps) + ' bps)':<34} "
        f"{c.total_slippage:>16,.2f}")
    say(f"  {'TOPLAM MALIYET':<34} {toplam_maliyet:>16,.2f}")
    say(f"  {'başlangıç bakiyeye oran':<34} {toplam_maliyet / a.balance * 100:>15.1f}%")
    say("")
    say(f"  {'NET bitiş bakiyesi':<34} {net.portfolio.balance:>16,.2f}")
    say(f"  {'NET getiri':<34} "
        f"{(net.portfolio.balance / a.balance - 1) * 100:>15.1f}%")
    say(f"  {'NET işlem sayısı':<34} {len(nt):>16,}")

    # --- 3. islem basina beklenti, bps ---------------------------------------
    baslik("3. ISLEM BASINA BEKLENTI (baz puan, giris notional'i uzerinden)")
    b_bps = [bps(t, "pnl") for t in bt]
    n_gross_bps = [bps(t, "gross") for t in nt]
    n_net_bps = [bps(t, "pnl") for t in nt]
    notional_net = sum((t.qty * t.entry_price for t in nt), Decimal("0"))
    rt_bps = float(toplam_maliyet / notional_net * 10000) if notional_net else 0.0

    say(f"  {'BRÜT koşu · işlem başına beklenti':<44} {np.mean(b_bps):>10.2f} bps")
    say(f"  {'NET koşu · brüt beklenti (slippage dahil)':<44} {np.mean(n_gross_bps):>10.2f} bps")
    say(f"  {'NET koşu · net beklenti':<44} {np.mean(n_net_bps):>10.2f} bps")
    say("")
    say(f"  {'gidiş-dönüş maliyeti (ölçülen, notional üzerinden)':<44} {rt_bps:>10.2f} bps")
    say(f"    {'komisyon payı':<42} "
        f"{float(c.total_fees / notional_net * 10000) if notional_net else 0:>10.2f} bps")
    say(f"    {'funding payı':<42} "
        f"{float(c.total_funding / notional_net * 10000) if notional_net else 0:>10.2f} bps")
    say(f"    {'slippage payı':<42} "
        f"{float(c.total_slippage / notional_net * 10000) if notional_net else 0:>10.2f} bps")
    say("")
    fark = np.mean(b_bps) - rt_bps
    say(f"  {'BRUT beklenti - gidis-donus maliyeti':<44} {fark:>10.2f} bps")
    say(f"  -> {'maliyet brüt beklentiyi YIYOR' if fark <= 0 else 'brüt beklenti maliyeti karsiliyor'}")

    # --- 4. oranlar -----------------------------------------------------------
    baslik("4. SONUC ORANLARI (NET kosu)")
    n = len(nt) or 1
    tp1 = sum(1 for t in nt if t.reached_tp1)
    final_tp = sum(1 for t in nt if t.reason == "FINAL_TP")
    stop = sum(1 for t in nt if t.reason == "STOP")
    kazanan = sum(1 for t in nt if t.pnl > 0)
    say(f"  {'kazanma oranı (net PnL > 0)':<40} {kazanan:>8,} {kazanan / n * 100:>9.1f}%")
    say(f"  {'TP1 (0.50) ulaşma oranı':<40} {tp1:>8,} {tp1 / n * 100:>9.1f}%")
    say(f"  {'nihai TP (0) ulaşma oranı':<40} {final_tp:>8,} {final_tp / n * 100:>9.1f}%")
    say(f"  {'stop (çapa 1) oranı':<40} {stop:>8,} {stop / n * 100:>9.1f}%")
    say("")
    say("  Çıkış nedenine göre:")
    say(f"  {'neden':<14} {'adet':>8} {'pay':>8} {'toplam net':>14} {'ort bps':>10}")
    for neden, adet in Counter(t.reason for t in nt).most_common():
        g = [t for t in nt if t.reason == neden]
        say(f"  {neden:<14} {adet:>8,} {adet / n * 100:>7.1f}% "
            f"{sum((t.pnl for t in g), Decimal('0')):>14,.2f} "
            f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f}")

    # --- 5. histogram ---------------------------------------------------------
    baslik("5. ISLEM SONUCLARI DAGILIMI (baz puan)")
    kenarlar = [-500.0, -200.0, -100.0, -50.0, -20.0, 0.0, 20.0, 50.0, 100.0, 200.0, 500.0]
    for etiket, kolon in (("BRÜT (sıfır maliyet)", b_bps), ("NET (gerçek maliyet)", n_net_bps)):
        say("")
        say(f"  {etiket} — n={len(kolon):,}  medyan {np.median(kolon):.1f} bps  "
            f"ortalama {np.mean(kolon):.1f} bps")
        say(f"  {'aralık (bps)':<22} {'adet':>8} {'pay':>8}")
        for et, adet, pay in dagilim(kolon, kenarlar):
            say(f"  {et:<22} {adet:>8,} {pay:>7.1f}%")

    # --- 6. basabas islem sayisi ---------------------------------------------
    baslik("6. BASABAS ISLEM SAYISI")
    say("  Soru: mevcut brüt beklentiyle, maliyetler kârı kaç işlemde yer?")
    say("")
    brut_ort = np.mean(b_bps)
    say(f"  {'brüt beklenti / işlem':<46} {brut_ort:>10.2f} bps")
    say(f"  {'gidiş-dönüş maliyeti / işlem':<46} {rt_bps:>10.2f} bps")
    say(f"  {'net beklenti / işlem':<46} {brut_ort - rt_bps:>10.2f} bps")
    say("")
    if brut_ort <= 0:
        say("  Brüt beklenti zaten sıfır veya negatif: maliyet olmasa da strateji kaybediyor.")
        say("  Başabaş işlem sayısı tanımsız — sorun maliyet değil, kenar yokluğu.")
    elif brut_ort > rt_bps:
        say("  Brüt beklenti maliyeti aşıyor: kümülatif kâr işlem sayısıyla büyür.")
        say(f"  Gerekli minimum brüt beklenti {rt_bps:.2f} bps; mevcut {brut_ort:.2f} bps.")
    else:
        # Her islem brut_ort kazandirip rt_bps goturuyor; birikmis brut kar,
        # kac islemlik maliyete denk geliyor?
        n_esit = float(sum(b_bps)) / rt_bps if rt_bps else float("inf")
        say(f"  Toplam brüt kazanç {sum(b_bps):,.0f} bps; her işlem {rt_bps:.2f} bps maliyet.")
        say(f"  {'birikmiş brüt kârı tüketen işlem sayısı':<46} {n_esit:>10,.0f}")
        say(f"  {'fiilen yapılan işlem sayısı':<46} {len(nt):>10,}")
        say(f"  -> maliyetler brüt kârın tamamını "
            f"{'YEDI' if len(nt) >= n_esit else 'yemedi'}")
        say("")
        say(f"  Başabaş için gereken brüt beklenti: {rt_bps:.2f} bps/işlem")
        say(f"  Mevcut: {brut_ort:.2f} bps/işlem  ->  açık {brut_ort - rt_bps:.2f} bps")

    # --- 7. R-ENTRY-02 dal kirilimi ------------------------------------------
    baslik("7. GIRISLERIN R-ENTRY-02 DALINA GORE KIRILIMI (NET kosu)")
    say("  R-ENTRY-02 sırası: (1) bantta yöne uygun OB → OB'den giriş ·")
    say("  (2) bantta FVG → doldurulması beklenebilir · (3) gösterge yok → çıplak 0.70.")
    say("  Dal ataması bu önceliğe göre: OB varsa OB, yoksa FVG, o da yoksa çıplak.")
    say("  (R-ENTRY-05 süzgeçlerinden geçen göstergeler sayılır.)")
    say("")
    dallar = {
        "(1) OB'den": [t for t in nt if t.had_ob],
        "(2) FVG'den": [t for t in nt if not t.had_ob and t.had_fvg],
        "(3) çıplak 0.70": [t for t in nt if not t.had_ob and not t.had_fvg],
    }
    say(f"  {'dal':<18} {'adet':>8} {'pay':>8} {'toplam net':>14} {'ort bps':>10} "
        f"{'kazanan':>9} {'TP1':>8}")
    for ad, g in dallar.items():
        if not g:
            say(f"  {ad:<18} {0:>8} {0.0:>7.1f}% {'-':>14} {'-':>10} {'-':>9} {'-':>8}")
            continue
        say(f"  {ad:<18} {len(g):>8,} {len(g) / n * 100:>7.1f}% "
            f"{sum((t.pnl for t in g), Decimal('0')):>14,.2f} "
            f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f} "
            f"{sum(1 for t in g if t.pnl > 0) / len(g) * 100:>8.1f}% "
            f"{sum(1 for t in g if t.reached_tp1) / len(g) * 100:>7.1f}%")
    say("")
    say("  Not: R-ENTRY-02 (3) gereği gösterge girişi kapılamaz — dal, girişin")
    say("  niteliğidir, ön koşulu değil. Üç dalın toplamı tüm girişlere eşittir.")

    # --- 8. ekleme sayisina gore dagilim -------------------------------------
    baslik("8. ISLEMLERIN EKLEME SAYISINA GORE DAGILIMI (NET kosu)")
    say(f"  kullanılan çarpanlar: {net.counters['adds_by_mult'] or '(ekleme yok)'}")
    say(f"  {'çarpan bulunamadığı için reddedilen ekleme':<44} "
        f"{net.counters['add_reject_mult']:>10,}")
    say("")
    say(f"  {'ekleme':<10} {'işlem':>8} {'pay':>8} {'toplam net':>14} {'ort bps':>10} "
        f"{'ort MAE (leg)':>14}")
    ekleme_sayilari = sorted({t.adds for t in nt})
    for k_ in ekleme_sayilari:
        g = [t for t in nt if t.adds == k_]
        say(f"  {k_:<10} {len(g):>8,} {len(g) / n * 100:>7.1f}% "
            f"{sum((t.pnl for t in g), Decimal('0')):>14,.2f} "
            f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f} "
            f"{np.mean([t.mae_leg for t in g]):>14.3f}")

    # --- 9. ekleme sayisina gore sonuc ---------------------------------------
    baslik("9. EKLEME SAYISINA GORE SONUC DAGILIMI (NET kosu)")
    nedenler = sorted({t.reason for t in nt})
    say(f"  {'ekleme':<10} {'işlem':>8} " + "".join(f"{r[:12]:>13}" for r in nedenler))
    for k_ in ekleme_sayilari:
        g = [t for t in nt if t.adds == k_]
        satir = "".join(
            f"{sum(1 for t in g if t.reason == r) / len(g) * 100:>12.1f}%" for r in nedenler)
        say(f"  {k_:<10} {len(g):>8,} " + satir)
    say("")
    say("  BREAKEVEN = ilk TP alındıktan sonra stop maliyete çekilmişti (R-EXIT-01).")
    say("  R-ADD-04 küçültmesi burada görünmez: çıkış nedeni değil, durum geçişi.")

    # --- 10. kucultme (R-ADD-04) ---------------------------------------------
    baslik("10. KUCULTME · R-ADD-04 (NET kosu)")
    say("  Ekleme sonrası fiyat ortalama maliyete döndüğünde pozisyon K tabanına")
    say("  indirilir. Çıkış değil, durum geçişi: kalan kısım nihai stop (1), ilk TP")
    say("  (0.50) ve nihai TP (0) ile devam eder. Ortalama maliyet küçültmeden")
    say("  etkilenmez, bu yüzden kalan kısmın hedefleri ve stopu aynı yerdedir.")
    say("  Hedef boyut: küçültme anındaki equity üzerinden K × equity notional.")
    say("")
    kucuk = [t for t in nt if t.reduces > 0]
    buyuk = [t for t in nt if t.reduces == 0]
    ekli = [t for t in nt if t.adds > 0]
    say(f"  {'küçültme olayı (toplam)':<44} {net.counters['reduce_events']:>10,}")
    say(f"  {'küçültülen işlem':<44} {len(kucuk):>10,} {len(kucuk) / n * 100:>8.1f}%")
    say(f"  {'ekleme yapılan işlem':<44} {len(ekli):>10,} {len(ekli) / n * 100:>8.1f}%")
    if ekli:
        say(f"  {'eklenenlerin küçültülme oranı':<44} "
            f"{len(kucuk) / len(ekli) * 100:>9.1f}%")
    say("")
    if not kucuk:
        say("  Hiçbir işlem küçültülmedi — ya ekleme olmadı ya da fiyat ekleme sonrası")
        say("  ortalama maliyete hiç dönmedi.")
    else:
        def sure_ort(g, alan):
            return str(pd.Timedelta(minutes=float(np.mean([getattr(t, alan) for t in g]))))

        say(f"  {'işlem başına küçültme (küçültülenlerde)':<44} "
            f"{np.mean([t.reduces for t in kucuk]):>10.2f}")
        say(f"  {'ortalama taşıma · küçültülen':<44} {sure_ort(kucuk, 'bars_held'):>20}")
        if buyuk:
            say(f"  {'ortalama taşıma · küçültülmeyen':<44} "
                f"{sure_ort(buyuk, 'bars_held'):>20}")
        say(f"  {'ortalama taşıma · küçültmeden sonra':<44} "
            f"{sure_ort(kucuk, 'bars_after_reduce'):>20}")
        say(f"  {'medyan taşıma · küçültmeden sonra':<44} "
            f"{str(pd.Timedelta(minutes=float(np.median([t.bars_after_reduce for t in kucuk])))):>20}")
        say("")
        say("  Küçültmeden sonra ne oldu (çıkış nedeni):")
        say(f"  {'sonuç':<14} {'adet':>8} {'pay':>8} {'toplam net':>14} {'ort bps':>10} "
            f"{'kazanan':>9}   açıklama")
        aciklama = {
            "FINAL_TP": "nihai TP (0)", "STOP": "nihai stop (1)",
            "BREAKEVEN": "başabaş (TP1 sonrası)", "RUN_END": "hâlâ açık (koşu sonu)",
            "LIQUIDATION": "likidasyon", "DELEVERAGE": "KRİTİK küçültme (R-RISK-05)",
        }
        for neden, adet in Counter(t.reason for t in kucuk).most_common():
            g = [t for t in kucuk if t.reason == neden]
            say(f"  {neden:<14} {adet:>8,} {adet / len(kucuk) * 100:>7.1f}% "
                f"{sum((t.pnl for t in g), Decimal('0')):>14,.2f} "
                f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f} "
                f"{sum(1 for t in g if t.pnl > 0) / len(g) * 100:>8.1f}%   "
                f"{aciklama.get(neden, '')}")
        say("")
        say("  RUN_END = koşu bittiğinde hâlâ açıktı, son fiyattan kapatıldı.")
        say("")
        say("  Küçültülen / küçültülmeyen karşılaştırması:")
        say(f"  {'küme':<20} {'adet':>8} {'toplam net':>14} {'ort bps':>10} "
            f"{'kazanan':>9} {'ort MAE (leg)':>14}")
        for ad, g in (("küçültülen", kucuk), ("küçültülmeyen", buyuk)):
            if not g:
                continue
            say(f"  {ad:<20} {len(g):>8,} "
                f"{sum((t.pnl for t in g), Decimal('0')):>14,.2f} "
                f"{np.mean([bps(t, 'pnl') for t in g]):>10.1f} "
                f"{sum(1 for t in g if t.pnl > 0) / len(g) * 100:>8.1f}% "
                f"{np.mean([t.mae_leg for t in g]):>14.3f}")

    # --- 11. MAE -------------------------------------------------------------
    baslik("11. MAKSIMUM ALEYHTE SAPMA (MAE)")
    say("  MAE = pozisyonun ortalama maliyetine göre gördüğü en kötü sapma.")
    say("  leg oranı = sapma / |çapa1 − çapa0| · equity % = sapma × qty / o anki equity")
    say("")
    for etiket, kolon, kenarlar in (
        ("leg oranı", [t.mae_leg for t in nt], [0.1, 0.25, 0.5, 0.75, 1.0, 1.5]),
        ("equity %", [t.mae_equity * 100 for t in nt], [1.0, 5.0, 10.0, 25.0, 50.0, 100.0]),
    ):
        if not kolon:
            continue
        say(f"  {etiket}: medyan {np.median(kolon):.3f} · ortalama {np.mean(kolon):.3f} · "
            f"p90 {np.percentile(kolon, 90):.3f} · maks {max(kolon):.3f}")
        for et, adet, pay in dagilim(kolon, kenarlar):
            say(f"    {et:<22} {adet:>8,} {pay:>7.1f}%")
        say("")

    # --- 12. en kotu 10 islem ------------------------------------------------
    baslik("12. EN KOTU 10 ISLEM")
    say(f"  {'sembol':<16} {'zarar':>12} {'bps':>9} {'ekleme':>7} {'küçült':>7} "
        f"{'taşıma':>12} {'MAE leg':>9} {'liq mesafe':>11} {'neden':<12}")
    for t in sorted(nt, key=lambda x: x.pnl)[:10]:
        sure = pd.Timedelta(minutes=t.bars_held)
        liq = f"{t.min_liq_dist * 100:.2f}%" if t.min_liq_dist is not None else "-"
        say(f"  {t.symbol.split('/')[0]:<16} {t.pnl:>12,.2f} {bps(t, 'pnl'):>9.1f} "
            f"{t.adds:>7} {t.reduces:>7} {str(sure):>12} {t.mae_leg:>9.3f} "
            f"{liq:>11} {t.reason:<12}")

    # --- 13. likidasyon ------------------------------------------------------
    baslik("13. LIKIDASYON (§8 zorunlu sayaclar)")
    pf = net.portfolio
    oran = pf.min_equity_ratio
    say(f"  {'koşu içi likidasyon olayı':<44} {net.counters['liquidations']:>10,}")
    say(f"  {'R-RISK-05 KRİTİK küçültme olayı':<44} {net.counters['deleverage_events']:>10,}")
    say(f"  {'küçültmelerde realize PnL':<44} {net.deleverage_realized:>10,.2f}")
    if oran is None:
        say("  pozisyon açılmadı — likidasyon mesafesi tanımsız")
    else:
        say(f"  {'min(equity / toplam notional)':<44} {oran * 100:>9.2f}%   <- MMR'siz")
        say(f"  {'min likidasyon mesafesi (MMR=' + str(a.mmr) + ')':<44} "
            f"{pf.min_liq_distance * 100:>9.2f}%")
        say("")
        say('  "Gerçek parada likide olurduk" — MMR duyarlılığı:')
        for mmr in (Decimal("0.004"), Decimal("0.005"), Decimal("0.01"), Decimal("0.025")):
            say(f"    MMR {mmr * 100:>5.2f}%  ->  {'LIKIDE' if oran <= mmr else 'hayatta':>8}"
                f"   (marj {(oran - mmr) * 100:>7.2f} puan)")
        say("  MMR borsadan çekilemedi (kimlik doğrulama ister); birincil ölçü MMR'siz orandır.")

    # --- 14. eszamanli acik pozisyon -----------------------------------------
    baslik("14. ESZAMANLI ACIK POZISYON (§9)")
    say("  Her 1m mumda kaç pozisyon açıktı. Cross marjinde eşzamanlılık doğrudan")
    say("  risktir: 10 pozisyon genel bir düşüşte 10 olay değil, tek olaydır.")
    say("  Ayrıca motorun mum başına işi bu sayıyla doğru orantılıdır (koşu süresi).")
    say("")
    hist = pf.concurrent_hist
    toplam_mum = sum(hist.values()) or 1
    agirlikli = sum(k * v for k, v in hist.items()) / toplam_mum
    say(f"  {'tepe eşzamanlı pozisyon':<44} {max(hist) if hist else 0:>10,}")
    say(f"  {'ortalama (mum ağırlıklı)':<44} {agirlikli:>10.2f}")
    say(f"  {'pozisyonlu mum oranı':<44} "
        f"{net.counters['bars_with_position'] / (net.counters['bars_total'] or 1) * 100:>9.1f}%")
    say(f"  {'toplam pozisyon-mum (motor iş yükü)':<44} "
        f"{sum(k * v for k, v in hist.items()):>10,}")
    say("")
    say(f"  {'açık':>6} {'mum':>12} {'pay':>8}")
    for k_ in sorted(hist):
        say(f"  {k_:>6} {hist[k_]:>12,} {hist[k_] / toplam_mum * 100:>7.1f}%")
    say("")
    kucuk_dk = sum(t.bars_after_reduce for t in nt)
    tum_dk = sum(t.bars_held for t in nt) or 1
    say(f"  Bunun {kucuk_dk:,} pozisyon-mumu (%{kucuk_dk / tum_dk * 100:.1f}) küçültme")
    say("  SONRASINDA geçti: R-ADD-04 artık maliyette kapatmadığı için pozisyonlar")
    say("  daha uzun yaşıyor. Karşılığı bölüm 10'daki taşıma süresi farkıdır.")

    pd.DataFrame([t.__dict__ for t in nt]).to_csv(a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
