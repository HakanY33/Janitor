# #31 ve çıkarma kolları — spec v0.11

Kaynak: `scripts/ltf_31.py`, kod `6362510+kirli`. 20 sembol, eğitim dilimi, 100 USDT, #30 kurgusu (B2 + `son_supuren`, A1+B, K = 0,25, limit, ADD-REJECT-E %3). Brüt = fiyat PnL'i (slippage içinde), sürtünme = komisyon + funding. R: net PnL / ilk girişin stopta riski (OB girişinde OB'nin ötesi). Bootstrap: brüt farkı (kol − #31), sembol-ay eşleşik, 10.000 yineleme, tohum 20261006 (`scripts/bootstrap_fark.py`).

| Kol | 100 $ → | İşlem | Kazanma | R kaz. / kayb. | Brüt | Sürtünme | Net | Kriter 3 | Brüt farkı vs #31 (%95) |
|---|---:|---:|---:|---|---:|---:|---:|---|---|
| #31 (hepsi) | 36,90 $ | 3317 | %48,3 | +0,81 / -1,03 | -32,97 | 30,13 (28,09 + 2,04) | -63,10 | 3/11 KALDI | — |
| (a) ekleme kapalı | 42,43 $ | 3431 | %47,8 | +0,82 / -0,99 | -26,78 | 30,79 (28,67 + 2,13) | -57,57 | 3/11 KALDI | +6,19 (-5,44 … +18,46) sıfırı kapsıyor |
| (b) 4h OB kapalı | 36,89 $ | 3326 | %48,3 | +0,81 / -1,03 | -32,83 | 30,28 (28,25 + 2,03) | -63,11 | 3/11 KALDI | +0,13 (-1,84 … +2,11) sıfırı kapsıyor |
| (c) 5m OB kapalı | 41,30 $ | 3355 | %49,1 | +0,78 / -0,95 | -27,27 | 31,43 (29,06 + 2,37) | -58,70 | 3/11 KALDI | +5,70 (-13,11 … +26,45) sıfırı kapsıyor |
| (d) OTE girişi kapalı | 82,97 $ | 656 | %12,8 | +7,02 / -1,61 | -7,89 | 9,13 (9,42 + -0,29) | -17,03 | 1/11 KALDI | +25,07 (-12,55 … +62,71) sıfırı kapsıyor |

| Kol | OB girişi | OB dilimi | Eklemeli işlem | Ekleme | Maks DD | Likidasyon | Parmak izi |
|---|---:|---|---:|---:|---:|---:|---|
| #31 (hepsi) | 188 | {'5m': 128, '30m': 57, '4h': 3} | 314 | 375 | %70,4 | 0 | `e8c2b0e8922f388a` |
| (a) ekleme kapalı | 197 | {'5m': 135, '30m': 59, '4h': 3} | 0 | 0 | %66,4 | 0 | `b813540ef80bf7ca` |
| (b) 4h OB kapalı | 187 | {'5m': 131, '30m': 56} | 311 | 372 | %70,4 | 0 | `d0be6f83c2a374d7` |
| (c) 5m OB kapalı | 69 | {'30m': 65, '4h': 4} | 77 | 79 | %67,4 | 0 | `f1ec583eb8a468b7` |
| (d) OTE girişi kapalı | 656 | {'5m': 516, '30m': 134, '4h': 6} | 0 | 0 | %18,8 | 0 | `77594b024921db4f` |

#31 sayaçları (ret): `add_reject_cap` 19, `add_reject_e` 165, `add_reject_giris` 689, `entry_reject_e` 21, `rejected_min_close` 290, `rejected_min_order` 747, `rejected_risk03` 7, `rejected_risk05` 552, `rejected_surtunme` 5

**OB rengi (§0.1 (e)):** tespit 1. mumun rengini v0.8'den beri şart koşuyor (talep c < o, arz c > o, doji yok). v4'ün 363 OB'sinde ihlal **0** (147 doğru, 84 yanlış, 132 etiketsiz — hepsi kurala uyuyor): v4'te yanlış denen OB'lerin nedeni renk değil.

