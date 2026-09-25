# Ölçüm · R-RISK-05 eşik ızgarası

Kural metni: `docs/STRATEGY_SPEC.md` — `R-RISK-05`, `R-RISK-01`, `R-ADD-03`, `OPEN-17`, `OPEN-28`.
Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır.

---

## İlk eşikler neden fazla sıkı çıktı

İlk değerler (`T_rahat = %50`, `T_kritik = %15`) tahmindi. Likidasyon mesafesi
≈ `equity / notional` olduğundan `T_rahat = %50` notional'ı fiilen **2× ile
sınırlıyor**. Bu, `R-RISK-01` (10-11×) ve `R-ADD-03` (üç eklemeyle 8×) ile aritmetik
olarak çelişir — ve `R-RISK-05` sert sınır olduğu için ekleme stratejisi tam devreye
girmesi gereken anda kapanır.

**Ölçüm:** `K=1.0`'da tek 1-1 eklemeden sonra `liq_distance = 0.363` → UYARI → ikinci
ekleme reddediliyor (`ADD-REJECT-D`).

İnsan pratiği bu eşiği desteklemiyor: *"ekleme yapınca liq fiyatı gözükmesi normal,
SL ve maliyette marj düşürme emirlerimizi o zaman koyuyoruz"* — yani likidasyon fiyatı
görünür olduğunda durulmuyor, **davranış değiştiriliyor**.

## Izgara koşusu — durum

48 hücre (`K` × `T_rahat` × `T_kritik` × UYARI-ekleme kolu), 20 sembol.
Koşu **tamamlanmadı**: makine uykusu yüzünden ilk hücreden sonra kesildi.

| Hücre | Sonuç |
|---|---|
| `K=1.0 T_rahat=0.50 T_kritik=0.15 UYARI_ekleme_engel=True` | getiri **−99.8%** · 3.122 işlem · 474 ekleme |

Tek hücre bir tablo değildir; kalibrasyon okuması için ızgaranın tamamı gerekir.
Ham çıktı: `logs/sweep.csv`, `logs/sweep_run.log`.

---

**Üreten betik:** `scripts/sweep.py`
