# v2 etiketlerinden çapalar

Üreten: `python -m scripts.etiket_capalar` (2026-10-02). Kaynak `etiketler.json`: yapılandırılmış alanlar (**alan**) ve serbest notlar (**not**) elle okundu; mor ipucu noktaları (**öneri**) v2 sayfasındaki konumlarından çözüldü. Aday karşılaştırması yok.

- **Not zamanı**: kullanıcının yazdığı (UTC, yıl girişten tamamlandı). Tek an ±1 saat, aralık tümüyle taranır; tepe → en yüksek high, dip → en düşük low (fiyat hedefi varsa ona en yakın mum).
- **Rol** kurgunun yönünden: SHORT `0` önce dip / `1` sonra tepe, LONG tersi. `?` = notta yön yok.
- **Girişe göre**: çapa mumu girişten önce **kapanmışsa** önce. *Sonra* olanlar sonradan bakıştır — v2 grafiği girişten sonrasını da gösteriyordu — **kalibrasyonda kullanılmaz**.

Toplam 74 çapa: önce 55, sonra 17, zamansız 2.

| # | İşlem | Kurgu | Yön | Rol | Tip | Not zamanı | Not fiyatı | 30m mumu | Değer | Girişe göre | Kaynak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | XRP LONG | A | LONG | 0 | tepe | 01-23 17:30 | 1.95 üstü | 2026-01-23 17:30 | 1.9648 | **önce** | alan |
| 1 | XRP LONG | A | LONG | 1 | dip | 01-30 01:30 | 1.70–1.75 | 2026-01-30 01:30 | 1.71 | **sonra** | alan |
| 1 | XRP LONG | B | LONG | 0 | tepe | 01-28 00:00/01-29 14:00 | ~12:00 en high | 2026-01-28 11:30 | 1.9417 | **önce** | not |
| 2 | SUI LONG | A | LONG | 0 | tepe | 10-27 05:00 | 2.70 üzeri | 2025-10-27 05:00 | 2.7173 | **önce** | alan |
| 2 | SUI LONG | A | LONG | 1 | dip | 10-28 21:00 | 2.45 üzeri | 2025-10-28 21:00 | 2.4593 | **sonra** | alan |
| 2 | SUI LONG | B | SHORT | 0 | dip | 10-22 05:00 | iğne | 2025-10-22 05:00 | 2.3292 | **önce** | not |
| 2 | SUI LONG | B | SHORT | 1 | tepe | 10-27 05:00 | A'nın tepesi | 2025-10-27 05:00 | 2.7173 | **önce** | not |
| 3 | BTC SHORT | A | LONG | 0 | tepe | 12-22 12:30 | 90000 üstü | 2025-12-22 12:30 | 90555 | **önce** | alan |
| 3 | BTC SHORT | A | LONG | 1 | dip | 12-24 14:30 | 87000 altı | 2025-12-24 14:30 | 86367 | **önce** | alan |
| 3 | BTC SHORT | B | ? | ? | tepe | 12-26 00:00/12-27 05:00 | gün ortasından biraz geride | 2025-12-26 07:00 | 89531.6 | **önce** | not |
| 3 | BTC SHORT | B | ? | ? | dip | 12-26 00:00/12-27 05:00 | aynı aralıkta en dip | 2025-12-26 15:00 | 86618.6 | **önce** | not |
| 4 | BTC LONG | A | SHORT | 0 | dip | 03-29 22:30 | 65000 altı | 2026-03-29 22:30 | 64914.5 | **sonra** | alan |
| 4 | BTC LONG | A | SHORT | 1 | tepe | 03-30 13:00 | 68000 üstü | 2026-03-30 13:00 | 68145 | **sonra** | alan |
| 4 | BTC LONG | B | LONG | 0 | tepe | 03-25 00:00/03-26 23:30 | 72K | 2026-03-25 11:30 | 71988.7 | **önce** | not |
| 4 | BTC LONG | B | LONG | 1 | dip | 03-29 00:00/03-30 23:30 | 65K altı | 2026-03-29 22:30 | 64914.5 | **sonra** | not |
| 5 | UNI SHORT | A | LONG | 0 | tepe | 12-03 00:00/12-05 00:00 | 6.2'nin biraz altı | 2025-12-04 01:00 | 6.192 | **önce** | not |
| 5 | UNI SHORT | A | LONG | 1 | dip | 12-07 11:00/12-08 13:00 | 5.4 altı, öğleye yakın | 2025-12-07 14:00 | 5.31 | **önce** | not |
| 7 | XRP SHORT | A | SHORT | 0 | dip | 12-31 20:00 | — | 2025-12-31 20:00 | 1.8111 | **önce** | not |
| 7 | XRP SHORT | A | SHORT | 1 | tepe | 01-03 00:00/01-04 00:00 | 2.05 üzeri | 2026-01-03 04:00 | 2.0549 | **sonra** | not |
| 8 | ORDI LONG | A | LONG | 0 | tepe | 02-21 00:00/02-22 23:30 | 2.8'e en yakın | 2026-02-21 09:30 | 2.784 | **önce** | not |
| 9 | NEAR SHORT | A | SHORT | 0 | dip | 03-29 22:00/03-29 23:00 | alt iğne | 2026-03-29 22:30 | 1.13 | **önce** | not |
| 9 | NEAR SHORT | A | SHORT | 1 | tepe | 03-30 00:00/03-31 23:30 | 1.225'e yakın | 2026-03-30 08:30 | 1.224 | **sonra** | not |
| 10 | BNB SHORT | A | LONG | 0 | tepe | 12-22 00:00/12-23 23:30 | 870 üstü | 2025-12-22 12:30 | 870.7 | **önce** | not |
| 10 | BNB SHORT | A | LONG | 1 | dip | 12-26 00:00/12-27 05:30 | 820'ye en yakın | 2025-12-26 15:00 | 820.59 | **önce** | not |
| 11 | CRV LONG | A | LONG | 0 | tepe | bot_0 | bot 0 doğru | 2026-01-05 01:30 | 0.434 | **önce** | not |
| 11 | CRV LONG | A | LONG | 1 | dip | öneri 13:30 | — | 2026-01-05 13:30 | 0.4173 | **sonra** | not + öneri |
| 12 | SOL SHORT | A | LONG | 0 | tepe | 02-06 22:30 | — | 2026-02-06 22:30 | 89.751 | **önce** | not |
| 12 | SOL SHORT | A | LONG | 1 | dip | 02-12 20:30 | — | 2026-02-12 20:30 | 76.545 | **önce** | not |
| 13 | ORDI SHORT | A | LONG | 0 | tepe | 10-13 21:00 | — | 2025-10-13 21:00 | 6.079 | **önce** | not |
| 13 | ORDI SHORT | A | LONG | 1 | dip | 10-17 08:00 | — | 2025-10-17 08:00 | 4.648 | **önce** | not |
| 13 | ORDI SHORT | B | SHORT | 0 | dip | 10-17 08:00 | — | 2025-10-17 08:00 | 4.648 | **önce** | not |
| 13 | ORDI SHORT | B | SHORT | 1 | tepe | 10-18 07:00 | “şimdilik” | 2025-10-18 07:00 | 5.109 | **sonra** | not |
| 14 | BNB SHORT | A | SHORT | 0 | dip | 02-14 05:00 | — | 2026-02-14 05:00 | 615.6 | **önce** | not |
| 14 | BNB SHORT | A | SHORT | 1 | tepe | 02-15 07:30 | — | 2026-02-15 07:30 | 642.21 | **sonra** | not |
| 14 | BNB SHORT | B | SHORT | 0 | dip | 02-11 10:30 | örnek, çalışmış | 2026-02-11 10:30 | 586.85 | **önce** | not |
| 14 | BNB SHORT | B | SHORT | 1 | tepe | 02-12 11:30 | örnek, çalışmış | 2026-02-12 11:30 | 620.62 | **önce** | not |
| 15 | AVAX SHORT | A | SHORT | 0 | dip | 09-22 00:00/09-22 23:30 | 09-22'nin en alt ucu | 2025-09-22 06:00 | 28.82 | **önce** | not |
| 15 | AVAX SHORT | A | SHORT | 1 | tepe | 09-23 15:00 | stop yerinin üstü | 2025-09-23 15:00 | 36.14 | **sonra** | not |
| 16 | XRP LONG | A | LONG | 0 | tepe | 10-05 08:00 | — | 2025-10-05 08:00 | 3.0711 | **önce** | not |
| 16 | XRP LONG | A | LONG | 1 | dip | 10-05 20:00 | — | 2025-10-05 20:00 | 2.9459 | **sonra** | not |
| 16 | XRP LONG | B | SHORT | 0 | dip | 10-01 03:30 | — | 2025-10-01 03:30 | 2.8127 | **önce** | not |
| 16 | XRP LONG | B | SHORT | 1 | tepe | 10-02 19:30 | 3.10 | 2025-10-02 19:30 | 3.0993 | **önce** | not |
| 17 | ORDI SHORT | A | SHORT | 0 | dip | — | bot 0'dan sonraki dip (“yine yetersiz”) | — | — | **zamansız** | not |
| 17 | ORDI SHORT | B | LONG | 0 | tepe | 10-21 16:30 | — | 2025-10-21 16:30 | 5.484 | **önce** | not |
| 17 | ORDI SHORT | B | LONG | 1 | dip | 10-22 21:00 | — | 2025-10-22 21:00 | 4.731 | **önce** | not |
| 18 | DOGE SHORT | A | LONG | 0 | tepe | 09-01 09:00 | — | 2025-09-01 09:00 | 0.21979 | **önce** | not |
| 18 | DOGE SHORT | A | LONG | 1 | dip | 09-01 21:30 | grafiğin nihai lowu | 2025-09-01 21:30 | 0.2046 | **önce** | not |
| 18 | DOGE SHORT | B | SHORT | 0 | dip | öneri 12:30 | 0.79 altına sarkmış | 2025-09-02 12:30 | 0.2065 | **önce** | not + öneri |
| 19 | RUNE SHORT | A | SHORT | 0 | dip | 10-17 00:00/10-17 23:30 | 0.8 veya altı | 2025-10-17 08:00 | 0.799 | **önce** | not |
| 19 | RUNE SHORT | A | SHORT | 1 | tepe | 10-18 00:00/10-18 23:30 | 10-18 high'ı | 2025-10-18 07:00 | 0.853 | **sonra** | not |
| 19 | RUNE SHORT | B | LONG | 0 | tepe | 10-13 20:30 | 0.96 | 2025-10-13 21:00 | 0.96 | **önce** | not |
| 19 | RUNE SHORT | B | LONG | 1 | dip | 10-17 00:00/10-17 23:30 | 0.8 | 2025-10-17 08:00 | 0.799 | **önce** | not |
| 20 | BNB SHORT | A | LONG | 0 | tepe | 01-22 10:30 | “öneri 13:30'un erkeni” | 2026-01-22 10:30 | 897.43 | **önce** | not |
| 20 | BNB SHORT | A | LONG | 1 | dip | öneri 15:00 | öneri lowu | 2026-01-22 15:00 | 878.13 | **önce** | not + öneri |
| 21 | JUP SHORT | A | SHORT | 0 | dip | 01-25 20:00 | — | 2026-01-25 19:30 | 0.1816 | **önce** | not |
| 21 | JUP SHORT | A | SHORT | 1 | tepe | 01-28 12:00 | — | 2026-01-28 12:00 | 0.2324 | **önce** | not |
| 22 | RUNE SHORT | A | SHORT | 0 | dip | — | 1.24'e en yakın lowlardan biri | — | — | **zamansız** | not |
| 22 | RUNE SHORT | A | SHORT | 1 | tepe | 09-19 00:00/09-19 06:00 | 1.38 üstü, ilk saatler | 2025-09-19 01:00 | 1.39 | **sonra** | not |
| 23 | INJ LONG | A | SHORT | 0 | dip | bot_1 | bot 1 doğru | 2025-10-05 20:00 | 12.502 | **önce** | not + öneri |
| 23 | INJ LONG | A | SHORT | 1 | tepe | öneri 01:30 | — | 2025-10-06 01:30 | 13.565 | **sonra** | not + öneri |
| 23 | INJ LONG | B | LONG | 0 | tepe | 10-03 22:00 | 13.5 üzeri | 2025-10-03 22:30 | 13.612 | **önce** | not |
| 23 | INJ LONG | B | LONG | 1 | dip | 10-04 18:30 | alt iğne | 2025-10-04 18:30 | 12.095 | **önce** | not |
| 25 | BNB SHORT | A | SHORT | 0 | dip | bot_0 | bot çapaları doğru | 2026-03-12 04:30 | 641.39 | **önce** | not |
| 25 | BNB SHORT | A | SHORT | 1 | tepe | bot_1 | bot çapaları doğru | 2026-03-12 12:30 | 657.47 | **önce** | not |
| 26 | SOL SHORT | A | LONG | ? | ? | 08-24 19:00/08-24 20:00 | tek mum hacmi, iki mum arası | 2025-08-24 19:00 | — | **sonra** | not |
| 27 | BNB LONG | A | SHORT | 0 | dip | 02-24 15:00 | — | 2026-02-24 14:30 | 576.69 | **önce** | not |
| 27 | BNB LONG | A | SHORT | 1 | tepe | 02-25 21:00 | 640 üstü | 2026-02-25 21:30 | 640.96 | **önce** | not |
| 28 | DOGE LONG | A | LONG | 0 | tepe | öneri -3 | “önerdiğim high” (−3/−4 mum) | 2025-09-13 13:30 | 0.30642 | **önce** | not + öneri |
| 28 | DOGE LONG | A | LONG | 1 | dip | bot_1 | low değişmiyor (örtük) | 2025-09-13 17:00 | 0.28074 | **önce** | not |
| 29 | JUP LONG | A | LONG | 0 | tepe | öneri 04:00 | “öneri high doğru” (04:00/04:30) | 2025-08-10 04:00 | 0.5484 | **önce** | not + öneri |
| 29 | JUP LONG | A | LONG | 1 | dip | bot_1 | low değişmiyor (örtük) | 2025-08-10 08:00 | 0.5054 | **önce** | not |
| 30 | AAVE LONG | A | LONG | 0 | tepe | bot_0 | doğru çizim | 2026-05-02 21:30 | 93.89 | **önce** | not |
| 30 | AAVE LONG | A | LONG | 1 | dip | bot_1 | doğru çizim | 2026-05-03 02:00 | 91.75 | **önce** | not |
| 30 | AAVE LONG | B | LONG | 1 | dip | 05-04 10:00 | “yeni low” | 2026-05-04 10:00 | 90.95 | **sonra** | not |

## “Setup yok” işaretli işlemler (11)

| # | İşlem | Giriş | Not (özet) |
|---|---|---|---|
| 1 | XRP LONG | 2026-01-29 14:27 | Tam zamanları yakalayamıyorum mouse ile seçim yapamadığım için ama burda setup yok işaretliyorum çünkü low ve … |
| 2 | SUI LONG | 2025-10-28 05:31 | yine setup göremem burada çünkü 0-1-ardınan 0.5 teması görmüyorum ki 0.7 bekleyeyim 0.5 teması gelirse sonra g… |
| 3 | BTC SHORT | 2025-12-27 05:37 | 12-26 ve 12-27 günleri arasındaki uzun mumlar manipülasyon yada şirketler gibi büyük balinaların hacimleridir … |
| 4 | BTC LONG | 2026-03-29 22:02 | düşen dipleri kırmış yükseliyor fakat yine de short OTE gördüm o setupı yazdım ama asıl büyük OTE 03-25 03-26 … |
| 5 | UNI SHORT | 2025-12-09 15:01 | OTE yanlış çizilmiş  eğer 6.2 fiyatından biraz aşağıdaki 12-04lere yakın tepeyi high 12-07 12-08 arasını öğle … |
| 6 | ORDI LONG | 2025-10-16 09:33 | işlem alınabilecek bi durum yok büyük kırmızı düşüş mumundan sonra fiyat düz ilerlemiş hiç işlem alınmamalı… |
| 7 | XRP SHORT | 2026-01-02 09:11 | OTE yok düz ilerleyen bi sistem var ancak alınabilecek beklenilecek OTE 12-31 ile 01-01 arasındaki 20.00 yakın… |
| 8 | ORDI LONG | 2026-02-23 01:01 | OTE yanlış doğru high noktası 02-21 ile 02-22 aralığındaki 2.8 fiyatına en yakın tepe noktası olacaktı … |
| 9 | NEAR SHORT | 2026-03-30 00:17 | Yanlış OTE ote yok burada 03-30 öncesi 22:00 23:00 arasındaki alt iğneyi 0 olarak kabul edip 03-30 ile 03-31 a… |
| 10 | BNB SHORT | 2025-12-27 05:45 | Yanlış OTE doğru fiyatlandırmalar high 870 üstündeki 12-22 ile 12-23 aralığındaki mum olacaktı low ise 820 sev… |
| 24 | BTC LONG | 2026-03-26 14:19 | düşük bir timeline içinde çizilen ve kazanan OTE olmuş genişten 30m bakınca dip geçilmiş burda çizebileceğim b… |

Çapa çıkmayan işlemler: #6, #24.
