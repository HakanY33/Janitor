# v4 · OB aday kuralları — ön kayıt

**Kayıt: 2026-10-06, hesaplamadan önce.** Kaynak: kullanıcının v4 notları (ardışık OB'ler, yer
değiştirme). Bu dosya commit'lendikten sonra hesap yapılır; tanımlar, ölçüt ve seçim kuralı
sonuç görüldükten sonra değişmez.

## Veri

- `docs/inceleme/v4/etiketler.json` (PR #44): motorun gösterdiği OB'lerin `dogru` / `yanlis` etiketleri.
- **Hariç:** r28 ve r29 (kullanıcı notu: gövde çizimi yüzünden yanlış etiketlendi) ve etiketsiz OB'ler.
- OB tanımı spec v0.9 (`src/features/ob.py`, bölge = 1. mumun high–low'u). Kural yalnızca **karar
  anında kapanmış** 30m mumlarını kullanır (CLAUDE.md #3). Ardışıklık ve swing'ler, karar anına
  kadarki **tüm geçmişten** hesaplanır (300 mumluk grafik penceresinden değil); OB'ler `ob_id` ile eşlenir.

## Adaylar

**A · Ardışık OB'ler.** OB'ler 1. mumlarının zamanına göre sıralanır. Bir **seri**, araya ters
yönlü OB girmeden gelen aynı yönlü OB'lerin en uzun dizisidir. Tek OB'lik seri her varyantta geçerlidir.

| | Kural |
|---|---|
| `A0` | taban: hepsi geçerli (bugünkü motor) — yalnızca kıyas için, seçilemez |
| `A1` | serisi ≥ 2 olan OB'lerin hepsi geçersiz |
| `A2` | serinin yalnızca **sonuncusu** geçerli (karar anına kadar bilinen sonuncusu) |
| `A3` | serinin yalnızca **ilki** geçerli |

**B · Yer değiştirme (BoS).** OB yalnızca, ondan başlayan hareket son karşı swing'i kırarsa geçerlidir.
- Swing'ler: `B2` (ATR zigzag, `k = 2`, `scripts/swing_secim.aday_b`), karar anına kadar kapanmış
  30m mumlarından. Zigzag swing'i ancak teyit edildikten sonra üretir, yani bu liste karar anında biliniyor.
- **Son karşı swing:** talep OB'sinde, pivotu 1. mumun açılışından önce olan son **tepe**; arz OB'sinde
  son **dip**. Böyle bir swing yoksa OB geçersiz sayılır.
- **Kırılma:** 2. mumdan başlayarak bir mumun **kapanışı** swing fiyatının ötesine geçer (talepte
  `close > tepe`, arzda `close < dip`). Fitil yetmez. Kayıt anındaki seçim budur; fitil varyantı ölçülmez.
- **"Ondan başlayan hareket":** kırılma, fiyat OB bölgesine ilk dönmeden (mitigasyon mumu hariç,
  bölge v0.9 high–low) ve karar anında ya da daha önce kapanmış bir mumda gerçekleşmelidir.

**C · Birleşim:** `A1+B`, `A2+B`, `A3+B` — OB'nin geçerli olması için iki koşulu da sağlaması gerekir.

Aday sayısı 7: A1, A2, A3, B, A1+B, A2+B, A3+B.

## Ölçüt ve seçim

- **Uyum** = (geçerli ∧ `dogru` + geçersiz ∧ `yanlis`) / etiketli OB sayısı (r28 ve r29 hariç).
- En yüksek uyumlu aday seçilir. Uyum sayısı eşitse **daha az bileşenli** aday (tek kural, birleşimden
  önce), o da eşitse yukarıdaki sırada önce gelen seçilir.
- **Seçilen aday `A0`'ın (taban) uyumunu geçmezse kural seçilmez**, spec değişmez.
- Tablo: her aday için uyum, geçerli sayılan doğru/yanlış sayıları ve geçersiz sayılan doğru/yanlış sayıları.
- **Sınır:** seçim tek bir etiket setine (bir kullanıcı, 28 an) dayanır; örneklem içi bir seçimdir,
  bağımsız doğrulama yoktur. Rapor bunu belirtir.
