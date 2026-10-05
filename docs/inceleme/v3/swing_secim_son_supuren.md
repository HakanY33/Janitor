# Swing seçimi — v3 etiketleri · eşleştirme `son_supuren`

Kaynak: `scripts/swing_secim.py --eslestirme son_supuren`, `docs/inceleme/v3/etiketler.json` (50 an). Ön kayıt `docs/inceleme/v2/adaylar.md` (ölçüt değiştirilmedi). Yorumlar betiğin başında.

## 1 · Etiket doğrulama

Setup'lı **44** (b03, b04 dahil), setup yok **6** (b06, b09, b22, r10, r14, r15).

| an | sembol | karar | 0 | 1 | 0: ±2 mumda daha uç | 1: ±2 mumda daha uç | `1` → karar R-ZONE-05 |
|---|---|---|---|---|---|---|---|
| b01 | XRP | 2026-01-29 14:27 | dip 01-25 19:00 | tepe 01-28 12:00 | 01-25 19:30 1.81 | 01-28 11:30 1.9417 | canlı |
| b02 | SUI | 2025-10-28 05:31 | tepe 10-27 05:30 | dip 10-27 13:30 | 10-27 05:00 2.7173 | — | canlı |
| b03 | BTC | 2025-12-27 05:37 | tepe 12-26 07:00 | dip 12-26 15:00 | — | — | canlı |
| b04 | BTC | 2026-03-29 22:02 | tepe 03-25 11:30 | dip 03-27 17:30 | — | 03-27 18:00 65516.4 | **1** 03-27 18:14 |
| b05 | UNI | 2025-12-09 15:01 | dip 12-09 06:30 | tepe 12-09 13:30 | — | — | canlı |
| b07 | XRP | 2026-01-02 09:11 | tepe 12-29 03:30 | dip 12-31 20:00 | 12-29 04:00 1.9169 | — | canlı |
| b08 | ORDI | 2026-02-23 01:01 | tepe 02-21 09:30 | dip 02-22 22:00 | — | — | canlı |
| b10 | BNB | 2025-12-27 05:45 | tepe 12-26 07:00 | dip 12-26 15:00 | — | — | canlı |
| b11 | CRV | 2026-01-05 10:28 | dip 01-03 07:00 | tepe 01-03 19:00 | 01-03 07:30 0.3963, 01-03 08:00 0.3961 | — | canlı |
| b12 | SOL | 2026-02-13 06:58 | tepe 02-12 11:00 | dip 02-12 20:30 | 02-12 10:30 82.181, 02-12 11:30 82.187 | — | canlı |
| b13 | ORDI | 2025-10-18 01:03 | tepe 10-17 01:00 | dip 10-17 08:00 | — | — | canlı |
| b14 | BNB | 2026-02-14 08:01 | dip 02-11 10:30 | tepe 02-14 01:30 | — | — | canlı |
| b15 | AVAX | 2025-09-23 14:07 | dip 09-22 06:00 | tepe 09-23 03:30 | — | — | canlı |
| b16 | XRP | 2025-10-05 16:45 | tepe 10-02 19:30 | dip 10-04 16:00 | — | — | canlı |
| b17 | ORDI | 2025-10-25 17:12 | tepe 10-21 16:30 | dip 10-22 21:00 | — | — | canlı |
| b18 | DOGE | 2025-09-03 01:54 | tepe 09-01 09:00 | dip 09-01 21:30 | — | — | canlı |
| b19 | RUNE | 2025-10-18 06:06 | tepe 10-13 21:00 | dip 10-17 08:00 | — | — | canlı |
| b20 | BNB | 2026-01-23 00:10 | dip 01-21 12:00 | tepe 01-22 10:30 | — | — | canlı |
| b21 | JUP | 2026-01-30 14:09 | tepe 01-28 12:00 | dip 01-30 06:30 | — | — | canlı |
| b23 | INJ | 2025-10-06 00:03 | tepe 10-03 21:30 | dip 10-04 18:30 | 10-03 22:30 13.612 | — | canlı |
| b24 | BTC | 2026-03-26 14:19 | dip 03-23 07:00 | tepe 03-25 11:30 | — | — | canlı |
| b25 | BNB | 2026-03-12 15:39 | dip 03-12 04:30 | tepe 03-12 12:30 | — | — | canlı |
| b26 | SOL | 2025-08-23 20:57 | dip 08-23 02:30 | tepe 08-23 05:00 | — | — | canlı |
| b27 | BNB | 2026-02-26 14:07 | tepe 02-25 21:30 | dip 02-26 11:30 | — | 02-26 12:00 622.8 | **1** 02-26 12:02 |
| b28 | DOGE | 2025-09-14 03:16 | tepe 09-13 13:00 | dip 09-13 17:00 | — | — | canlı |
| b29 | JUP | 2025-08-10 10:24 | tepe 08-10 04:30 | dip 08-10 08:00 | 08-10 04:00 0.5484 | — | canlı |
| b30 | AAVE | 2026-05-03 13:42 | tepe 05-02 21:30 | dip 05-03 03:00 | — | 05-03 02:00 91.75 | canlı |
| r01 | BTC | 2025-08-06 22:30 | dip 08-05 14:30 | tepe 08-06 18:00 | — | — | canlı |
| r02 | CRV | 2025-08-14 14:00 | dip 08-12 11:00 | tepe 08-13 10:30 | — | — | canlı |
| r03 | NEAR | 2025-08-18 12:00 | tepe 08-17 16:00 | dip 08-18 06:30 | — | — | canlı |
| r04 | BNB | 2025-09-15 05:00 | tepe 09-14 06:00 | dip 09-15 01:00 | — | — | canlı |
| r05 | ORDI | 2025-09-21 14:00 | tepe 09-18 21:00 | dip 09-19 23:30 | — | — | canlı |
| r06 | RUNE | 2025-09-27 06:00 | tepe 09-24 14:30 | dip 09-25 17:30 | — | — | **1** 09-25 18:00 |
| r07 | GALA | 2025-09-28 09:30 | dip 09-26 11:00 | tepe 09-26 18:30 | — | 09-26 18:00 0.01482 | canlı |
| r08 | RUNE | 2025-11-09 17:30 | dip 11-07 14:30 | tepe 11-09 05:00 | — | — | canlı |
| r09 | GALA | 2025-12-02 17:30 | tepe 11-27 21:00 | dip 12-01 15:30 | — | — | canlı |
| r11 | JUP | 2025-12-17 06:00 | dip 12-15 18:30 | tepe 12-16 16:00 | — | — | canlı |
| r12 | HYPE | 2025-12-19 17:00 | tepe 12-17 15:00 | dip 12-19 01:00 | — | — | canlı |
| r13 | ORDI | 2026-01-10 03:30 | tepe 01-06 13:30 | dip 01-08 14:00 | — | — | canlı |
| r16 | AAVE | 2026-02-27 12:30 | tepe 02-25 17:30 | dip 02-26 18:00 | — | — | canlı |
| r17 | CRV | 2026-03-02 10:00 | dip 02-28 10:00 | tepe 03-01 02:00 | — | — | canlı |
| r18 | BTC | 2026-04-19 15:30 | dip 04-16 13:30 | tepe 04-17 16:00 | — | — | canlı |
| r19 | XRP | 2026-04-21 12:00 | tepe 04-17 14:30 | dip 04-19 22:00 | — | — | canlı |
| r20 | ZEC | 2026-05-11 23:30 | dip 05-07 04:00 | tepe 05-09 05:30 | — | — | canlı |

**Yerel uç değil:** 12 çapa (2 × 44 içinde). **Karar anına kadar ölmüş yapı:** 3/44 (etiketlerden çıkarılmadı; ilk ihlal edilen çapa ve 1m zamanı). Ölüm penceresi `1` mumunun kapanışı → karar.

## 2 · Adaylar

Setup'lı 44 an; setup yok 3 bot + 3 rastgele. 0.50 teması eğitim diliminde bulunmayan setup: 0 (—) — son tarih yok sayıldı.

| aday | çift isabet (/44) | 0 geri çağırma | 1 geri çağırma | yanlış alarm bot (/3) | yanlış alarm rastgele (/3) | teyit gecikmesi medyanı (saat) | swing / sembol-ay | zone / sembol-ay |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B2 | 25 (57%) | 42 (95%) | 43 (98%) | 0 | 0 | 2.0 | 155 | 70 |
| B3 | 23 (52%) | 39 (89%) | 42 (95%) | 1 | 1 | 3.5 | 70 | 32 |

## 3 · Seçim

En yüksek çift isabet 25/44. Fark ≤ 2 → eşit: B2, B3. İkincil sıra: yanlış alarm (bot + rastgele) ↓, tek çapa geri çağırma (0 + 1) ↑, teyit gecikmesi ↓.

**Seçilen: B2.** İsabet eden anlar: b02, b03, b04, b08, b10, b11, b12, b15, b17, b18, b20, b23, b25, b28, b29, b30, r02, r03, r04, r07, r11, r12, r13, r17, r18.

