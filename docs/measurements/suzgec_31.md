# Piyasa süzgeçleri S1/S2/S3 — #31 üstüne (ön kayıt `docs/adaylar_piyasa.md`)

Kaynak: `scripts/suzgec_31.py`, spec v0.11, kod 6362510+kirli. 20 sembol, eğitim dilimi, 100 USDT, #31 kurgusu (B2 + `son_supuren`, A1+B, OB/OTE girişi, ekleme 1-1 × 3, K = 0,25, limit, ADD-REJECT-E %3). Sıralama net PnL'e göre (taban hariç).

| Kol | 100 $ → | İşlem | Kazanma | R kaz. / kayb. | Brüt | Sürtünme | Net | Kriter 3 |
|---|---:|---:|---:|---|---:|---:|---:|---|
| S1+S2+S3 | 68,12 $ | 1029 | %48,5 | +0,76 / -1,02 | -18,78 | 13,10 (12,51 + 0,59) | -31,88 | 4/11 KALDI |
| S1+S2 | 65,65 $ | 1476 | %48,4 | +0,80 / -0,99 | -16,32 | 18,03 (16,85 + 1,18) | -34,35 | 4/11 KALDI |
| S2+S3 | 61,24 $ | 1390 | %49,2 | +0,76 / -1,00 | -22,35 | 16,40 (15,53 + 0,87) | -38,76 | 4/11 KALDI |
| S1+S3 | 58,21 $ | 1779 | %49,0 | +0,78 / -1,03 | -22,48 | 19,31 (18,54 + 0,77) | -41,79 | 4/11 KALDI |
| S1 (belirsiz trend) | 49,18 $ | 2559 | %47,9 | +0,82 / -1,01 | -24,25 | 26,58 (24,74 + 1,84) | -50,82 | 3/11 KALDI |
| S2 (düz piyasa) | 48,70 $ | 1978 | %47,7 | +0,82 / -0,99 | -29,61 | 21,69 (20,15 + 1,54) | -51,30 | 3/11 KALDI |
| S3 (zayıf zigzag) | 46,98 $ | 2446 | %48,6 | +0,79 / -1,02 | -30,13 | 22,89 (21,87 + 1,02) | -53,02 | 3/11 KALDI |
| #31 (taban) | 36,90 $ | 3317 | %48,3 | +0,81 / -1,03 | -32,97 | 30,13 (28,09 + 2,04) | -63,10 | 3/11 KALDI |

## Madde 3 — 20 etiketli işlemle tutarlılık (kalibrasyon değil, rapor)

Kullanıcının 12 "girmezdim" ve 8 "girerdim"inden kaçını bu kombinasyon elerdi.

| Kol | girmezdim elenen (12) | girerdim yanlış elenen (8) |
|---|---:|---:|
| S1+S2+S3 | 10/12 | 7/8 |
| S1+S2 | 9/12 | 7/8 |
| S2+S3 | 7/12 | 6/8 |
| S1+S3 | 8/12 | 5/8 |
| S1 (belirsiz trend) | 7/12 | 3/8 |
| S2 (düz piyasa) | 4/12 | 5/8 |
| S3 (zayıf zigzag) | 4/12 | 4/8 |

**Not:** S1+S2+S3 ve S1+S2'nin yüksek "girmezdim" örtüşmesi (10/12, 9/12) seçici bir isabetten değil,
genel olarak çok fazla işlemi elemesinden gelebilir — aynı kombinasyonlar "girerdim"in de 7/8'ini
yanlışlıkla eliyor. Tek başına en iyi örtüşen S1 (7/12 girmezdim, 3/8 yanlış) daha seçici duruyor.

## Özet

- **Hiçbir kol veya kombinasyon kriter 3'ü geçmedi** (en iyisi 4/11, eşik GEÇTİ için ikisi de pozitif
  gerekiyor). Taban #31'e göre hepsi net kaybı azaltıyor (en çok S1+S2+S3: −63,10 $ → −31,88 $) ama
  brüt hâlâ negatif (−18,78 … −30,13) — edge yok, yalnızca en kötü işlemlerin bir kısmı elenmiş.
- **Sıralama (net PnL, en iyiden):** S1+S2+S3 > S1+S2 > S2+S3 > S1+S3 > S1 > S2 > S3 > #31 (taban).
  Üçlü kombinasyon en iyi net PnL'i veriyor ama işlem sayısını da 3317 → 1029'a (%69) düşürüyor.
- **Madde 3 (tutarlılık):** en seçici tekil süzgeç S1 (belirsiz trend) — kullanıcının 12
  "girmezdim"inden 7'sini eliyor, 8 "girerdim"den yalnızca 3'ünü yanlışlıkla elemiş. S2 ve S3 tek
  başına daha az örtüşüyor (4/12). Kombinasyonlar örtüşmeyi büyütüyor ama bunun bir kısmı "her şeyi
  eleme" etkisi (yukarıdaki not).
- **En iyi kol S1+S2+S3**, doğrulama coinlerinde × eğitim dönemi koşulacaktı (ön kayıt) — bu adım
  `OPEN-69` yüzünden koşulmadı (aşağıda).
- **`OPEN-69` (çözülmedi):** doğrulama coinlerinin (`dogrulama_coinleri_2026-10-07.md`) diskte verisi
  yok, `DogrulamaKilidi` erişimi durduruyor, ve kilit açılsa da planlı çekim eğitim dönemini değil
  2026-09-11 sonrasını kapsıyor — eğitim takvim aralığı için bu 20 sembolde hiç geçmiş veri yok.
  Doğrulama adımı kullanıcı onayı bekliyor.
