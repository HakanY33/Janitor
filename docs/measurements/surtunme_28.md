# Sürtünme dökümü — #28 (açıklayıcı)

Paket `logs/inceleme/swing_B2_100_v08_son_supuren.pkl` · parmak izi `d95d65d4311d378e` · spec v0.8 · kod 875fa5c+kirli · 761 işlem. Öneri yok; yalnızca dağılım.

## 1 · Toplam

| kalem | $ |
|---|---:|
| brüt fiyat PnL'i | 7.86 |
| komisyon | 9.85 |
| funding | 1.09 |
| **sürtünme (komisyon + funding)** | **10.94** |
| net | -3.09 |
| (slippage — brütün içinde, ayrıca) | 2.13 |

Defter komisyonu 9.85 = işlem komisyonu 9.85 (eşit).

## 2 · Çıkış tipine göre

| çıkış | işlem | komisyon/işlem $ | komisyon bps (giriş notional'ı) | brüt/işlem $ | net/işlem $ | komisyon payı |
|---|---:|---:|---:|---:|---:|---:|
| stop | 321 | 0.0153 | 7.0 | -0.5291 | -0.5454 | 50% |
| TP1 + breakeven | 299 | 0.0123 | 5.5 | 0.1839 | 0.1699 | 37% |
| nihai TP | 140 | 0.0088 | 4.0 | 0.8752 | 0.8651 | 13% |
| diğer (RUN_END) | 1 | 0.0105 | 5.5 | 0.1740 | 0.0638 | 0% |

## 3 · Maker / taker

| kalem | emir | komisyon $ | pay | slippage $ |
|---|---|---:|---:|---:|
| stop | taker | 3.51 | 36% | 1.41 |
| giris | maker | 3.33 | 34% | 0.00 |
| breakeven | taker | 1.81 | 18% | 0.72 |
| tp1 | maker | 0.86 | 9% | 0.00 |
| tp_nihai | maker | 0.34 | 3% | 0.00 |
| cikis | taker | 0.00 | 0% | 0.00 |
| **toplam** | maker 46% · taker 54% | 9.85 | | 2.13 |

Limit emrinin taker'a düşmesi: yok (sayaçlar 0).

## 4 · Leg büyüklüğüne göre (beşte birlik dilimler)

| leg dilimi (%) | işlem | komisyon/işlem $ | brüt/işlem $ | komisyon / brüt kazanç | stop payı |
|---|---:|---:|---:|---:|---:|
| 0.82–3.79 | 152 | 0.0126 | -0.0142 | 19% | 44% |
| 3.80–5.58 | 152 | 0.0128 | -0.0054 | 9% | 46% |
| 5.58–7.53 | 152 | 0.0130 | 0.0213 | 6% | 43% |
| 7.53–11.36 | 152 | 0.0137 | -0.1019 | 7% | 47% |
| 11.38–53.65 | 153 | 0.0128 | 0.1509 | 2% | 31% |

**En çok komisyon ödeyen %10 (76 işlem):** leg medyanı 6.78% (tümü 6.47%), komisyonun 13%'i, çıkış nihai TP 0, TP1 + breakeven 1, stop 75. Komisyon doları giriş notional'ıyla (= bakiye × K) büyür; aşağıdaki ilk 10'da bps de var.

| sembol | giriş | çıkış | leg % | komisyon $ | komisyon bps | brüt $ |
|---|---|---|---:|---:|---:|---:|
| CRV | 2025-08-06 13:55 | stop | 4.97 | 0.0186 | 7.1 | -0.3847 |
| ORDI | 2026-01-15 11:11 | stop | 6.05 | 0.0186 | 7.1 | -0.4631 |
| DOGE | 2026-01-05 16:16 | stop | 10.81 | 0.0186 | 7.2 | -0.7905 |
| CRV | 2026-01-17 04:29 | stop | 7.95 | 0.0186 | 7.1 | -0.5961 |
| DOT | 2025-08-06 15:00 | stop | 9.67 | 0.0185 | 7.1 | -0.7104 |
| HYPE | 2026-01-06 19:06 | stop | 6.67 | 0.0184 | 7.1 | -0.5005 |
| CRV | 2025-08-10 23:04 | stop | 15.11 | 0.0183 | 7.2 | -1.0442 |
| CRV | 2025-08-09 04:00 | stop | 10.15 | 0.0182 | 7.1 | -0.7302 |
| ZEC | 2026-01-21 09:14 | stop | 5.61 | 0.0181 | 7.1 | -0.4201 |
| CRV | 2026-01-23 15:22 | stop | 5.95 | 0.0181 | 7.1 | -0.4437 |
