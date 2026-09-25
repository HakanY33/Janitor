# 1m geçmiş penceresi kayıyor mu

**Tarih:** 2026-09-25 · kaynak `logs/earliest/*.jsonl` (`collect.log_earliest`, ikili arama)

`ARCHITECTURE.md` §3.2, BingX 1m penceresinin kaydığını tahmin ediyordu. Kayıtlar günlük
tutulmamış: 1m için yalnızca **2026-09-14**'te bir ölçüm var (20 sembol, 22 satır).
30m için de yalnızca 2026-09-11'de. İkinci noktayı 2026-09-25 06:43–06:46 UTC'de aynı
fonksiyonla ölçtüm.

| sembol | ilk kayıt (09-14) | son kayıt (09-25) | aralık | kayıp |
|---|---|---|---:|---:|
| ZEC | 2025-10-10 10:00 | 2025-10-10 10:00 | 10,9 gün | 0 dk/gün |
| diğer 19 sembol | 2025-07-31 16:00 | 2025-07-31 16:00 | 10,8–10,9 gün | 0 dk/gün |

Diğer 19 sembol: BTC, ETH, SOL, UNI, XRP, AVAX, BNB, GALA, CRV, NEAR, HYPE, SUI, AAVE,
JUP, DOGE, INJ, RUNE, ORDI, DOT. Yereldeki ilk 1m mum her sembolde borsanın en eski
mumuyla aynı.

**Sonuç: 10,8 günde kayma yok.** Sabit uzunlukta kayan bir pencere olsaydı her sembol
~15.600 dakika kaybederdi. Başlangıç sabit bir tarihe bağlı görünüyor (2025-07-31 16:00;
ZEC'te 2025-10-10).

**Sınır:** Yalnızca iki nokta var. Aylık gibi basamaklı bir budama bu aralıkta
görünmeyebilir. Ölçümü sürdürmek için günlük kayıt gerekiyor.

## 30m — pencere kayıyor (ek, 2026-09-25)

Aynı gün 30m için de ölçüldü: sunucu kaydı (`janitor-earliest`) ve 20 yeni sembolün
backfill'i. **30m penceresi günde tam 1 gün kayıyor.**

| sembol | 2026-09-11 | 2026-09-25 | aralık | kayıp |
|---|---|---|---:|---:|
| 18 sembol | 2024-12-20 14:00 | 2025-01-03 07:30 | 13,7 gün | **1.440 dk/gün** |
| NEAR | 2024-12-20 07:00 | 2025-01-03 07:30 | 14,0 gün | 1.440 dk/gün |
| ZEC | 2025-10-10 10:00 | 2025-10-10 10:00 | 13,7 gün | 0 (liste tarihi pencere içinde) |
| yeni 20 sembol | — | 2025-01-03 07:30 | — | hepsinde tam 30.239 mum |

Pencerenin uzunluğu sabit: **30.239 mum ≈ 630 gün**. Yerelde zaten inmiş olan 30m
geçmişi kaybolmaz. Ancak bugün indirilen bir sembol, 2024-12-20'den önceye değil,
2025-01-03'ten önceye hiç gidemez. **1m ise kaymıyor** (başlangıç 2025-07-31 16:00'da
sabit).

Sonuç: `ARCHITECTURE.md` §3.2'deki uyarı 1m için değil, **30m için** doğru. Günlük
artımlı 30m toplama, her gün pencereden bir günlük geçmişin düşmesini engeller.
