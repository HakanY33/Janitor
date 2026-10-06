# Sürtünme dökümü — #29 (açıklayıcı)

Paket `logs/inceleme/swing_B2_100_v09_son_supuren.pkl` · parmak izi `86fa613afa4ae23c` · spec v0.9 · kod 50dd420+kirli · 843 işlem. Öneri yok; yalnızca dağılım.

## 1 · Toplam

| kalem | $ |
|---|---:|
| brüt fiyat PnL'i | -1.52 |
| komisyon | 10.06 |
| funding | 1.02 |
| **sürtünme (komisyon + funding)** | **11.08** |
| net | -12.60 |
| (slippage — brütün içinde, ayrıca) | 2.20 |

Defter komisyonu 10.06 = işlem komisyonu 10.06 (eşit).

## 2 · Çıkış tipine göre

| çıkış | işlem | komisyon/işlem $ | komisyon bps (giriş notional'ı) | brüt/işlem $ | net/işlem $ | komisyon payı |
|---|---:|---:|---:|---:|---:|---:|
| stop | 368 | 0.0141 | 7.0 | -0.4639 | -0.4787 | 51% |
| TP1 + breakeven | 319 | 0.0114 | 5.5 | 0.1594 | 0.1464 | 36% |
| nihai TP | 156 | 0.0081 | 4.0 | 0.7586 | 0.7492 | 13% |

## 3 · Maker / taker

| kalem | emir | komisyon $ | pay | slippage $ |
|---|---|---:|---:|---:|
| stop | taker | 3.70 | 37% | 1.48 |
| giris | maker | 3.38 | 34% | 0.00 |
| breakeven | taker | 1.81 | 18% | 0.72 |
| tp1 | maker | 0.84 | 8% | 0.00 |
| tp_nihai | maker | 0.34 | 3% | 0.00 |
| **toplam** | maker 45% · taker 55% | 10.06 | | 2.20 |

Limit emrinin taker'a düşmesi: yok (sayaçlar 0).

## 4 · Leg büyüklüğüne göre (beşte birlik dilimler)

| leg dilimi (%) | işlem | komisyon/işlem $ | brüt/işlem $ | komisyon / brüt kazanç | stop payı |
|---|---:|---:|---:|---:|---:|
| 0.82–3.69 | 168 | 0.0118 | -0.0197 | 21% | 47% |
| 3.69–5.36 | 169 | 0.0118 | -0.0058 | 10% | 46% |
| 5.37–7.29 | 168 | 0.0120 | 0.0081 | 7% | 44% |
| 7.30–10.85 | 169 | 0.0124 | -0.0938 | 7% | 47% |
| 10.89–53.65 | 169 | 0.0118 | 0.1022 | 2% | 34% |

**En çok komisyon ödeyen %10 (84 işlem):** leg medyanı 6.45% (tümü 6.18%), komisyonun 13%'i, çıkış nihai TP 0, TP1 + breakeven 2, stop 82. Komisyon doları giriş notional'ıyla (= bakiye × K) büyür; aşağıdaki ilk 10'da bps de var.

| sembol | giriş | çıkış | leg % | komisyon $ | komisyon bps | brüt $ |
|---|---|---|---:|---:|---:|---:|
| JUP | 2025-08-06 14:55 | stop | 14.53 | 0.0188 | 7.2 | -1.0359 |
| CRV | 2025-08-06 13:55 | stop | 4.97 | 0.0184 | 7.1 | -0.3807 |
| CRV | 2025-08-10 23:04 | stop | 15.11 | 0.0180 | 7.2 | -1.0322 |
| ORDI | 2025-08-04 20:36 | stop | 5.71 | 0.0180 | 7.1 | -0.4241 |
| DOGE | 2025-08-04 20:33 | stop | 5.12 | 0.0180 | 7.1 | -0.3819 |
| CRV | 2025-08-09 04:00 | stop | 10.15 | 0.0179 | 7.1 | -0.7194 |
| SOL | 2025-08-06 14:54 | stop | 10.23 | 0.0179 | 7.1 | -0.7219 |
| NEAR | 2025-08-07 00:30 | stop | 11.60 | 0.0178 | 7.2 | -0.8061 |
| AAVE | 2025-08-02 20:00 | TP1 + breakeven | 4.45 | 0.0174 | 7.0 | 0.0124 |
| JUP | 2025-08-12 17:20 | stop | 13.12 | 0.0172 | 7.2 | -0.8695 |
