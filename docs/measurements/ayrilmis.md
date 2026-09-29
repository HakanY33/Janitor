> **UYARI:** Bu ölçüm 30m look-ahead hatası taşır (commit 3fb2ff4 ve öncesi). Mutlak değerler geçersiz. Düzeltilmiş yeniden ölçüm: `docs/measurements/damga.md`.

# Kriter 1 — ayrılmış dilim (tek sefer)

**Tarih:** 2026-09-25 · **HEAD** `6ede38843b8613c1d21f4c8244b2167a11bc58e0` + işlenmemiş
`scripts/ayrilmis.py` (sha256 `ab84d62e846e4cf0`), `tests/test_ayrilmis.py`, spec
kriter metni · `src/backtest/engine.py` sha256 `b04b9395f3c85a7d` · çıktı
`logs/ayrilmis.txt`, `logs/ayrilmis.csv`

Dilim bir kez okundu. Koşu hatasız bitti. Hiçbir parametre değişmedi, düzeltme ya da
yeniden koşu yapılmadı. Kabul kriterleri koşudan önce spec'e yazıldı (§8).

## Kurulum

| | |
|---|---|
| Dilim | 2026-05-08 13:00 → 2026-09-11 13:00 UTC (~4,1 ay) |
| Semboller | orijinal 20 + soğuk 20, iki ayrı portföy, başlangıç 10.000 |
| Isınma | motor tüm geçmişte koşar, kesimden önce giriş dolmaz; kesim öncesi bekleyen emir sonra dolabilir |
| (a) | F1 standart |
| (b) | kriter 2: komisyon kesin · slippage ×3 · giriş P2 |

- **Ön uçuş:** Aynı betik önce yalnızca eğitim verisinde, 2026-01-15 → 05-08 aralığında
  koşuldu. Kod yolu hatasız çalıştı. Ayrılmış veri o koşuda okunmadı.
- **Eksik veri tamamlandı:** 14 Eylül backfill'i DOT'ta (05-31) ve ORDI'de (06-30) yarım
  kalmıştı. İki sembolün 1m verisi koşudan önce tamamlandı.
- **Ortak bitiş:** Soğuk 20'nin verisi 09-25'e kadar gidiyor. Ortak bitiş 09-11 seçildi.
  Orijinallerin 30m'i güncellenseydi `train_frac = 0.8` eğitim kesimi kayardı.

## Sonuçlar

| ölçü | ORİJ (a) | YENİ (a) | ORİJ (b) | YENİ (b) |
|---|---:|---:|---:|---:|
| **net PnL** | **−1.287** | **−851** | −2.182 | −1.763 |
| brüt fiyat PnL | +244 | +460 | −222 | −105 |
| komisyon | 1.268 | 1.089 | 1.201 | 1.017 |
| slippage | 264 | 226 | 759 | 643 |
| brüt / sürtünme | 0,159 | 0,350 | −0,113 | −0,063 |
| kazanan sembol | 7/20 | 7/20 | 5/20 | 5/20 |
| maks drawdown | %14,6 | %16,1 | %23,3 | %20,7 |
| bar: equity < %50 | 0 | 0 | 0 | 0 |
| işlem | 962 | 832 | 952 | 814 |

## Kabul kriterleri

| # | Kriter | Orijinal | Soğuk | Sonuç |
|---|---|---|---|---|
| K1 | (a) net > 0 | −1.287 | −851 | **KALDI** |
| K2 | (b) net > 0 | −2.182 | −1.763 | **KALDI** |
| K3 | (a) ≥ 14/20 kazanan | 7/20 | 7/20 | **KALDI** |
| K4 | (a) DD ≤ 1,5 × eğitim | %14,6 ≤ %17,84 | %16,1 ≤ %19,87 | GEÇTİ |
| K5 | (a) equity ≥ %50 her bar | 0 bar | 0 bar | GEÇTİ |

## Aylık net PnL (çıkış ayına göre)

| ay | ORİJ (a) | YENİ (a) | ORİJ (b) | YENİ (b) |
|---|---:|---:|---:|---:|
| 2026-05 (08'den) | −1.008 | −971 | −1.166 | −1.206 |
| 2026-06 | +190 | +251 | −31 | +37 |
| 2026-07 | −107 | −252 | −324 | −440 |
| 2026-08 | −324 | −71 | −514 | −272 |
| 2026-09 (11'e kadar) | −38 | +192 | −147 | +118 |

## Okuma

1. **Brüt edge ayrılmış dilimde sıfıra yakın.**
   - Eğitimde brüt/sürtünme 1,5–1,9 idi, burada 0,16–0,35.
   - Brüt fiyat PnL işlem başına +0,25 (orijinal) ve +0,55 (soğuk). Sürtünme bunun 3–6
     katı.
   - Kayıp sürtünmeden geliyor. Sürtünmeyi karşılayacak bir edge yok.
2. **Rejime bağlı mı? Kısmen.**
   - İki kümede de kaybın büyük kısmı ilk üç haftada: Mayıs'ta −1.008 ve −971.
   - Mayıs hariç tutulsa bile (a) kolu orijinalde −279, soğukta +120. Başabaşın
     etrafında dolaşıyor.
   - Aylar arasında tutarlı bir kazanç yok. Eğitimde de kâr tek bir aya yığılmıştı
     (Şubat, bkz. ön uçuş).
3. **K4 ve K5 geçti.** Risk katmanı hesabı korudu: likidasyon 0, equity hiç %50'nin
   altına inmedi, DD sınırın içinde. Sorun risk değil, edge.
4. **İki küme aynı sonucu veriyor.** Orijinal ve soğuk kümede 7/20 kazanan var ve
   aylık işaretler çoğunlukla aynı yönde. Sonuç sembol seçimine değil, döneme bağlı.

## Rapor edilen, düzeltilmeyen noktalar

- **Isınma varsayımı:** Kesimden önce kurulan bekleyen emirler kesimden hemen sonra
  dolabiliyor. Mayıs kaybının ne kadarının bu "eski" emirlerden geldiği ayrıştırılmadı.
  Betik işlem listesini saklamıyor, ayrıştırmak için yeniden koşmak gerekir. Bu varsayım
  koşudan önce yazılmıştı.
- **ZEC'in kendi eğitim kesimi 2026-07-06.** ZEC geç listelendiği için `train_frac` onu
  daha geç kesiyor. Dolayısıyla ZEC'in bu dilimdeki ilk 2 ayı eğitimde görülmüş veri. ZEC
  net −47, sonucu değiştirmiyor.
- **Son ay kısmi:** Eylül yalnızca 11 gün. Dilim sonunda açık kalan pozisyonlar
  `RUN_END` ile son fiyattan kapatıldı.
