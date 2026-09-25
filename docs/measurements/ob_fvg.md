# Ölçüm · OB / FVG anlamlılığı

Kural metni: `docs/STRATEGY_SPEC.md` — `R-ENTRY-05`, `R-ADD-05`, `R-ADD-06`, `OPEN-23`.
Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır; hiçbir kural burada tanımlanmaz.

---

## OPEN-23 — OB/FVG anlamlılık ölçütü

**Ölçüm (NEAR 30m, 09-08 13:30 → 09-10 12:00, ≈92 mum):** 17 OB, 21 FVG tespit edildi.
Giriş bandında (2.527–2.563) 3 OB ve 2 FVG.

Ortalama her 5 mumda bir OB, mevcut tanımın fazla geçirgen olduğunu gösteriyor.
Sonucu şu: `R-ENTRY-02`'nin "bantta OB varsa OB'den gir" kuralı neredeyse her zaman
tetikleniyor — OB bir **filtre** olmaktan çıkıp sabit davranışa dönüşüyor.

İnsan pratiği bu sorunu zaten biliyor: *"OB'ler ardı ardına olunca çalışma oranları düşer"*
(`R-ADD-05`). Trader görsel olarak anlamlı olanı seçiyor; motor hepsini buluyor.

**Kapatma yöntemi:** NEAR listesi grafikte elle karşılaştırılır — bu 17'nin kaçı gerçekten
OB sayılırdı? Aradaki fark anlamlılık ölçütünü verir. Aday girdiler: impuls büyüklüğü,
OB sonrası hareketin menzili, kümelenme cezası, HTF yön uyumu.

**`OPEN-21` kapandı, ama sorunu çözmüyor.** Ölçüm (tüm NEAR verisi, 30m 30.240 mum /
1m 585.495 mum): gövde/medyan oranı `2.0` = p78 (mumların %22'si), `3.0` = p91,
`4.0` = p95. Eşik **4.0**'a çıkarıldı — %4.5'lik oran "normalden kat kat büyük"
tanımına uyan tek seviye. Dağılım iki TF'de neredeyse aynı; medyan normalizasyonu
sembol ve TF başına ayrı eşik gerektirmiyor.

**Ama eşik anlamlılığı seçmiyor.** Ölçüm: impuls büyüklüğü, OB sonrası menzili
öngörmüyor — 2.2x impuls %1.3 menzil üretirken 4.1x %15.6, 3.6x ise %5.6 üretiyor.
Eşiği yükseltmek yoğunluğu azaltır, iyi OB'yi seçmez.

**Karar: anlamlılık ölçütü aranmayacak.** Eşik değişikliği yoğunluk sorununu çözdü
(5.8 → 24.6 mum/OB; 20 mumluk pencerede delinme %10). Kalan "hangi OB iyi" sorusuna
elimizdeki kanıt cevap vermiyor, ve 0.1 sd'lik etkilerden skor kurmak aşırı uyumdur.
`R-ZONE-08` minimal kalır; OB ikili varlık sinyali olarak kullanılır. Skor, backtest
gerçek işlem sonuçları ürettikten sonra o veriyle kurulur.

---

## FVG genişliği — `R-ENTRY-05` eşiğinin dayanağı

**Ölçüm (20 sembol, 30m, en eski %80, 92.439 FVG):** genişlik, dolum hızını
monotonik öngörüyor — en dar yarı 20 mumda %81 dolarken en geniş %5 yalnızca %39.7.
Ham yoğunluk 5.1 mum/FVG; "dolmamış" şartı tek başına 19.1 mum/FVG veriyor
(OB tabanı: 23.5 mum/OB). Genişlik eşiği oradan ince ayardır.

---

## Delinme, ufka göre

| Ufuk (mum) | 5 | 10 | 20 | 50 | ∞ |
|---|---|---|---|---|---|
| Delinme oranı | %4.9 | %8.2 | %10.2 | %15.6 | %79.3 |

Yatay ufuklu oran bilgi taşımaz. `ADD-REJECT-C` için ilgili pencere 20 mum civarı,
orada oran %10 — yani delinme seyrek bir olay ve kullanılabilir bir red sinyali.

---

**Üreten betik:** `scripts/measure_ob.py`, `scripts/measure_fvg.py`
