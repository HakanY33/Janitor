# Strateji inceleme etiketleri — açıklayıcı özet

Kaynak: `docs\inceleme\strateji\etiketler.json` (20 işlem) × `logs\inceleme\ltf31_31.pkl` (spec v0.11, kod 6362510+kirli, parmak izi e8c2b0e8922f388a). **Not:** grafikler çıkışı gösteriyordu — karar × sonuç ilişkisi sonradan bakış içerebilir, kanıt olarak kullanılmaz; aşağıdaki tablolar yalnızca bağlam.

## 1. İşlem başına yüzde kâr/zarar

PnL / giriş notional × 100 (kaldıraçlı pozisyonun yüzdesi).

| # | Sembol | Yön | Karar | % PnL | Çıkış | 4h yön |
|---|---|---|---|---|---|---|
| 1 | ORDI | SHORT | girmezdim | -10.48 | STOP | UP |
| 2 | ORDI | LONG | girerdim | +9.26 | FINAL_TP | NONE |
| 3 | AAVE | SHORT | girmezdim | -0.02 | BREAKEVEN | NONE |
| 4 | HYPE | SHORT | girerdim | -5.89 | STOP | NONE |
| 5 | UNI | LONG | girmezdim | -1.63 | STOP | UP |
| 6 | BNB | LONG | girerdim | +1.57 | FINAL_TP | UP |
| 7 | SUI | SHORT | girmezdim | -0.75 | STOP | NONE |
| 8 | GALA | LONG | girerdim | -5.89 | STOP | UP |
| 9 | ZEC | SHORT | girmezdim | -11.46 | STOP | NONE |
| 10 | DOT | SHORT | girmezdim | -1.52 | STOP | DOWN |
| 11 | DOGE | LONG | girmezdim | -11.51 | STOP | NONE |
| 12 | RUNE | LONG | girerdim | +1.27 | FINAL_TP | DOWN |
| 13 | JUP | SHORT | girerdim | -1.25 | STOP | NONE |
| 14 | NEAR | LONG | girmezdim | -9.04 | STOP | NONE |
| 15 | ORDI | LONG | girmezdim | -10.28 | STOP | NONE |
| 16 | ZEC | LONG | girerdim | +1.15 | BREAKEVEN | UP |
| 17 | ORDI | LONG | girmezdim | -8.16 | STOP | NONE |
| 18 | HYPE | SHORT | girerdim | +3.18 | FINAL_TP | DOWN |
| 19 | DOGE | LONG | girmezdim | -6.53 | STOP | UP |
| 20 | JUP | LONG | girmezdim | -10.98 | STOP | DOWN |

Toplam (20 işlem, eşit ağırlık değil — kendi notional'ı): -78.94 puan toplamı, ortalama -3.95.

## 2. Karar × sonuç

| Karar \ Çıkış | BREAKEVEN | FINAL_TP | STOP | Toplam |
|---|---|---|---|---|
| girerdim | 1 | 4 | 3 | 8 |
| girmezdim | 1 | 0 | 11 | 12 |

**Not:** bu tablo sonradan bakış içerir — grafik çıkışı gösteriyordu. Kanıt değil.

## 3. Sebep dağılımı (girmezdim)

| Sebep | Adet |
|---|---|
| düz piyasa | 4 |
| zigzag zayıf (0-1-0.5) | 3 |
| trend ters | 2 |
| diğer | 2 |
| hacim yok | 1 |

## 4. Karar × 4h yön

| Karar \ 4h yön | DOWN | NONE | UP | Toplam |
|---|---|---|---|---|
| girerdim | 2 | 3 | 3 | 8 |
| girmezdim | 2 | 7 | 3 | 12 |

