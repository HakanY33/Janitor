> **UYARI:** Bu ölçüm 30m look-ahead hatası taşır (commit 3fb2ff4 ve öncesi). Mutlak değerler geçersiz. Düzeltilmiş yeniden ölçüm: `docs/measurements/damga.md`.

# F1 neden kaybetti — eğitim ve ayrılmış dilim karşılaştırması

> **YALNIZCA AÇIKLAYICI. AYAR İÇİN KULLANILMAZ.** Ayrılmış dilim 2026-09-25'te okundu ve
> harcandı. Buradaki hiçbir sayı bir parametreyi, filtreyi ya da kuralı seçmek için
> kullanılamaz. Yeni doğrulama yalnızca 2026-09-11 sonrası veride yapılabilir.

**Tarih:** 2026-09-27 · **HEAD** `6ede388` + işlenmemiş `scripts/neden.py`,
`tests/test_neden.py` · çıktı `logs/neden.txt`, işlem listesi `logs/neden_islemler.csv`

## Kurulum

- F1 standart, (a) kolu. İki küme var: orijinal 20 ve soğuk 20.
- Eğitim koşusu `soguk.py` ile aynı, 2026-05-08 13:00'e kadar. Ayrılmış koşu `ayrilmis.py`
  ile aynı, kesimden 2026-09-11 13:00'e kadar.
- Dört koşunun neti raporlananla **birebir** aynı: +2.376 · −1.287 · +4.187 · −851.
- Oranlar **bps** cinsinden, dönemin ortalama giriş notional'ına göre hesaplandı. Böylece
  equity'nin büyümesinden gelen boyut farkı karşılaştırmaya girmez.
- Slippage işlem başına tutulmuyor. Toplam slippage işlemlere notional'la orantılı
  dağıtıldı; toplamlar tutuyor.

## İşlem profili

| ölçü | ORİJ eğitim | ORİJ ayrılmış | SOĞUK eğitim | SOĞUK ayrılmış |
|---|---:|---:|---:|---:|
| işlem | 2.251 | 962 | 2.261 | 832 |
| aylık işlem (ort.) | 188 | 192 | 226 | 166 |
| kazanma oranı (net > 0) | %65,7 | %62,8 | %63,5 | %60,2 |
| TP1'e ulaşma | %65,8 | %63,1 | %63,7 | %61,3 |
| çıkış: stop | %34,1 | %37,0 | %36,3 | %39,1 |
| çıkış: nihai TP | %18,3 | %16,0 | %19,6 | %18,4 |
| çıkış: TP1 + breakeven | %47,6 | %47,0 | %44,1 | %42,5 |
| ortalama leg büyüklüğü | %3,25 | %2,88 | %3,64 | %3,59 |

## Brüt/sürtünme 1,53 → 0,16: çöküş nereden geliyor?

| bileşen | ORİJ eğitim | ORİJ ayrılmış | SOĞUK eğitim | SOĞUK ayrılmış |
|---|---:|---:|---:|---:|
| p · brüt-kazanan oranı | %65,9 | %63,0 | %63,7 | %60,9 |
| W · kazanan ort. brüt (bps) | +67,6 | +54,6 | +80,5 | +73,8 |
| L · kaybeden ort. brüt (bps) | −99,6 | −90,0 | −104,5 | −108,8 |
| **b · işlem başı brüt (bps)** | **+10,59** | **+1,12** | **+13,30** | **+2,45** |
| **f · işlem başı sürtünme (bps)** | **6,90** | **7,02** | 6,92 | 7,01 |
| brüt / sürtünme | 1,535 | 0,159 | 1,920 | 0,350 |

Aşağıdaki tablo eğitimden başlar ve her satırda yalnızca bir bileşeni ayrılmış dilimdeki
değeriyle değiştirir:

| | ORİJ | SOĞUK |
|---|---:|---:|
| eğitim | 1,535 | 1,920 |
| yalnız isabet (p) | 0,835 | 1,186 |
| yalnız büyüklük (W, L) | 0,767 | 1,079 |
| yalnız sürtünme (f) | 1,508 | 1,898 |
| ayrılmış | 0,159 | 0,350 |

1. **Sürtünme değişmedi.** İşlem başına 6,9 bps'den 7,0 bps'e çıktı. Çöküşün tamamı
   paydan geliyor: işlem başı brüt 10,6 bps'den 1,1 bps'e düştü (soğukta 13,3 → 2,5).
2. **İsabet ve büyüklük kabaca eşit pay taşıyor.** Tek başına her biri oranı yarıya
   indiriyor. İkisi birlikte sıfıra yaklaştırıyor.
   - İsabet: 3 puanlık düşüş. Kazanan ile kaybeden arasındaki fark ~165 bps olduğu için
     bu, işlem başına ~−5 bps demek.
   - Büyüklük: orijinalde kazananlar %19 küçüldü (67,6 → 54,6). Kaybedenler de küçüldü
     (−99,6 → −90,0) ama daha az. Leg %3,25'ten %2,88'e indi. Hedef ve stop leg'e göre
     ölçeklendiği için bu uyumlu bir tablo, ama tek başına açıklamıyor.
   - Soğukta leg aynı kaldı (%3,64 → %3,59). Buna rağmen kazananlar küçüldü, kaybedenler
     büyüdü.
3. **İşlem sayısı oranı değiştiremez.** Pay ile paydada aynı anda durur. Net'teki fark,
   dönemin kısa olmasından geliyor (4,1 ay, eğitim ~9 ay). Aylık hız orijinalde aynı
   (188 → 192). Soğukta %27 düştü (226 → 166).
   - Orijinal: net −3.663 farkın −1.361'i işlem sayısından, −2.302'si işlem başı
     sonuçtan geliyor.
   - Soğuk: −2.646 işlem sayısından, −2.392 işlem başı sonuçtan.
   - İşlem sayısı etkisi kârlı bir işlemin daha az tekrarlanmasıdır. Kaybın
     **nedeni değil**.

## Aylık tablo ve oynaklık rejimi

Tablo işlemleri giriş ayına göre gruplar. ATR, 30m ATR(14) / kapanış (bps) değerinin
kümedeki ortalamasıdır.

| ay | dönem | ORİJ işlem | ORİJ kazanma | ORİJ net | ORİJ ATR | SOĞUK net | SOĞUK ATR | BTC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2025-08 | eğitim | 256 | %68 | +192 | 87,8 | −190 | 103,9 | −%6,5 |
| 2025-09 | eğitim | 177 | %63 | +114 | 71,6 | −439 | 85,6 | +%5,8 |
| 2025-10 | eğitim | 344 | %69 | +969 | 111,7 | +1.123 | 120,0 | −%3,9 |
| 2025-11 | eğitim | 248 | %69 | +185 | 116,0 | +968 | 124,3 | −%17,5 |
| 2025-12 | eğitim | 256 | %67 | +586 | 81,6 | −71 | 89,7 | −%0,8 |
| 2026-01 | eğitim | 248 | %59 | −661 | 80,0 | +1.139 | 93,5 | −%10,3 |
| 2026-02 | eğitim | 183 | %65 | +1.610 | 105,6 | +3.328 | 107,2 | −%15,3 |
| 2026-03 | eğitim | 233 | %61 | −233 | 79,9 | −679 | 91,0 | +%2,2 |
| 2026-04 | eğitim | 235 | %64 | −452 | 73,2 | −1.059 | 87,3 | +%12,3 |
| 2026-05 | ayrılmış* | 231 | %61 | −830 | 80,4 | −1.070 | 91,2 | −%3,7 |
| 2026-06 | ayrılmış | 253 | %69 | +175 | 107,1 | +417 | 115,4 | −%20,7 |
| 2026-07 | ayrılmış | 213 | %59 | −195 | 67,1 | −245 | 82,7 | +%7,7 |
| 2026-08 | ayrılmış | 240 | %65 | −263 | 74,2 | −75 | 88,0 | +%24,8 |
| 2026-09 | ayrılmış | 96 | %60 | −109 | 88,8 | +189 | 103,7 | −%1,7 |

\* Mayıs satırında 1–8 Mayıs arasındaki eğitim işlemleri de var.

- **ATR ortalaması** ayrılmış dilimde biraz daha düşük: orijinalde 88,5 → 83,5, soğukta
  99,4 → 96,2. Fark küçük.
- **BTC'nin aylık mutlak getirisi** ayrılmış dilimde daha yüksek. Haziran–Ağustos ortalaması
  %13,7, eğitimde %8,3. Güçlü trend ayları bunlar: Haziran −%20,7, Ağustos +%24,8.
- **Kâr yüksek ATR aylarında yığılıyor.** Eğitimde en iyi aylar Ekim ve Şubat (ATR 105–112).
  Ayrılmış dilimdeki tek artı ay Haziran, onun ATR'si de 107. ATR'nin 80'in altında kaldığı
  aylarda orijinalin neti Mart, Nisan, Temmuz ve Ağustos'ta eksi.
  - Karşı örnekler var. Eylül 2025'te ATR 71,6, orijinal yine de +114. Ocak'ta ATR 80,
    orijinal −661 ama soğuk +1.139. Yani bu bir eğilim,
    kural değil. **Sıralama bu veride yapılmış bir gözlemdir. Filtre olarak kullanılamaz.**
- **Düşüş kesimden önce başladı.** Eğitimin son iki ayı iki kümede de eksi. Orijinal Mart
  −233, Nisan −452. Soğuk Mart −679, Nisan −1.059. Ayrılmış dilim bu gidişi sürdürüyor.
  Eğitim kârı birkaç aya yığılmıştı: Ekim ve Şubat, orijinalin netinin %109'u.

## Bekleyen emir notu (ısınma varsayımı)

`_arm_entry` kesimden önce çağrılıp kesimden sonra dolan emirlere bakıldı:

| | işlem | net | Mayıs neti | eski emir | yeni emir | eski emirler hariç dilim |
|---|---:|---:|---:|---:|---:|---:|
| ORİJ | 1 / 962 | −42 | −973 | −42 | −931 | −1.245 |
| SOĞUK | 2 / 832 | −81 | −1.137 | −81 | −1.055 | −770 |

**Isınma varsayımı sonucu açıklamıyor.** Kesimden önce kurulan emirlerin hepsi
kesimin ilk saatlerinde doldu (05-08 13:00–17:33). Mayıs kaybının %4–7'si bu
emirlerden geliyor. Kaybın kalanı kesimden sonra kurulan emirlerden. Bu emirler
çıkarılsa bile K1 iki kümede de kalıyor.

Mayıs neti burada giriş ayına göre −973. `ayrilmis.md`'de çıkış ayına göre −1.008
yazıyordu; fark ay sınırını geçen işlemlerden geliyor.

## Özet okuma

- Sürtünme sabit kaldı. İşlem başı brüt edge yaklaşık %90 eridi.
- Bunun kabaca yarısı isabetten geliyor: kazanma −3 puan, stop +3 puan. Yarısı da kazanan
  işlemlerin küçülmesinden.
- İşlem sayısı brüt/sürtünme oranını açıklamıyor.
- Oynaklık rejimi açık bir kırılma göstermiyor. Kâr hem eğitimde hem ayrılmış dilimde
  yüksek ATR'li birkaç aya yığılmış. Eğitimin son iki ayı zaten eksiydi.
- Isınma varsayımının etkisi ihmal edilebilir: 3 işlem, −123.
