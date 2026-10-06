# Sürtünme dökümü — #30 (açıklayıcı)

Paket `logs/inceleme/swing_B2_100_v010_son_supuren.pkl` · parmak izi `ddc097097a39ef92` · spec v0.10 · kod 5b40e53+kirli · 155 işlem. Öneri yok; yalnızca dağılım.

## 1 · Toplam

| kalem | $ |
|---|---:|
| brüt fiyat PnL'i | 0.27 |
| komisyon | 2.16 |
| funding | 0.39 |
| **sürtünme (komisyon + funding)** | **2.55** |
| net | -2.27 |
| (slippage — brütün içinde, ayrıca) | 0.46 |

Defter komisyonu 2.16 = işlem komisyonu 2.16 (eşit).

## 2 · Çıkış tipine göre

| çıkış | işlem | komisyon/işlem $ | komisyon bps (giriş notional'ı) | brüt/işlem $ | net/işlem $ | komisyon payı |
|---|---:|---:|---:|---:|---:|---:|
| TP1 + breakeven | 71 | 0.0135 | 5.5 | 0.2338 | 0.2176 | 44% |
| stop | 58 | 0.0164 | 7.1 | -0.7805 | -0.7992 | 44% |
| nihai TP | 26 | 0.0095 | 4.0 | 1.1131 | 1.1011 | 11% |

## 3 · Maker / taker

| kalem | emir | komisyon $ | pay | slippage $ |
|---|---|---:|---:|---:|
| giris | maker | 0.73 | 34% | 0.00 |
| stop | taker | 0.68 | 31% | 0.27 |
| breakeven | taker | 0.47 | 22% | 0.19 |
| tp1 | maker | 0.20 | 9% | 0.00 |
| tp_nihai | maker | 0.07 | 3% | 0.00 |
| **toplam** | maker 47% · taker 53% | 2.16 | | 0.46 |

Limit emrinin taker'a düşmesi: yok (sayaçlar 0).

## 4 · Leg büyüklüğüne göre (beşte birlik dilimler)

| leg dilimi (%) | işlem | komisyon/işlem $ | brüt/işlem $ | komisyon / brüt kazanç | stop payı |
|---|---:|---:|---:|---:|---:|
| 1.42–4.30 | 31 | 0.0136 | -0.0066 | 16% | 42% |
| 4.47–6.82 | 31 | 0.0135 | 0.0910 | 7% | 29% |
| 6.92–9.95 | 31 | 0.0143 | 0.0335 | 5% | 39% |
| 10.21–14.89 | 31 | 0.0140 | 0.0071 | 4% | 42% |
| 14.95–43.06 | 31 | 0.0142 | -0.1162 | 3% | 35% |

**En çok komisyon ödeyen %10 (15 işlem):** leg medyanı 11.14% (tümü 8.12%), komisyonun 13%'i, çıkış nihai TP 0, TP1 + breakeven 0, stop 15. Komisyon doları giriş notional'ıyla (= bakiye × K) büyür; aşağıdaki ilk 10'da bps de var.

| sembol | giriş | çıkış | leg % | komisyon $ | komisyon bps | brüt $ |
|---|---|---|---:|---:|---:|---:|
| HYPE | 2025-12-26 02:25 | stop | 8.94 | 0.0191 | 7.1 | -0.6820 |
| ORDI | 2025-12-12 22:38 | stop | 12.11 | 0.0190 | 7.2 | -0.8924 |
| ORDI | 2026-03-16 03:09 | stop | 9.60 | 0.0189 | 7.1 | -0.7203 |
| JUP | 2026-02-03 20:17 | stop | 8.15 | 0.0187 | 7.1 | -0.6140 |
| SOL | 2026-02-13 15:26 | stop | 33.06 | 0.0184 | 7.4 | -2.0123 |
| SOL | 2026-03-03 16:24 | stop | 21.80 | 0.0184 | 7.3 | -1.4395 |
| ORDI | 2026-01-17 05:59 | stop | 15.28 | 0.0183 | 6.7 | -1.3984 |
| GALA | 2025-12-01 00:04 | stop | 20.53 | 0.0181 | 6.6 | -1.9624 |
| XRP | 2025-11-22 16:11 | stop | 9.75 | 0.0180 | 7.1 | -0.6974 |
| DOGE | 2025-12-01 00:21 | stop | 16.53 | 0.0180 | 6.7 | -1.5087 |
