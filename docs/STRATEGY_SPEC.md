# STRATEGY_SPEC

| | |
|---|---|
| **Versiyon** | v0.4 |
| **Durum** | OTE modeli kapalı ve kodlanabilir. Açık parametre kalmadı; eşikler backtest'le kalibre edilecek. |
| **Kapsam** | Kripto vadeli (perpetual), cross marjin, paper trading |
| **Son güncelleme** | 2026-09-10 |

**v0.3'ten değişenler:** `OPEN-15` kapandı (ara derinlik serbest) · `OPEN-17` kapandı
(`R-RISK-05` mesafe bazlı üç bölgeye çevrildi) · `R-RISK-02` netleşti (iç stop daima aktif)

**v0.2'den değişenler:** OTE sırası düzeltildi (0.5 teması ön koşul) · Boyutlandırma
marjin yerine notional bazlı · `R-RISK-05` eklendi · CONFLICT-01/02/03/04 çözüldü ·
Harmonik erteleme gerekçesi düzeltildi

---

## 0. Model

**Likidite süpürme sonrası dönüş.**

Fib, **zaten oluşmuş** bir leg üzerine çizilir. Oluşumu beklemek diye bir şey yok —
`0` ve `1` çapaları geçmişte mevcuttur, biz onların üzerine çekeriz.

```
        1 = süpürülen likidite  ◄── NİHAİ STOP
        │
   0.79 ├─┐
   0.70 ├─┘  ③ GİRİŞ
        │
   0.50 ├──────  ② ÖN KOŞUL (temas) ── sonra ④ İLK TP
        │
        0 = köken likidite      ◄── NİHAİ TP
```

### Zorunlu sıra

| Adım | Olay |
|---|---|
| ① | `0` ve `1` çapaları mevcut, fib çizilir |
| ② | Fiyat **`0.50`'ye temas eder** — bu bir ön koşul, atlanamaz |
| ③ | Fiyat geri döner ve **`0.70–0.79`** bandına gelir → **GİRİŞ** |
| ④ | Fiyat tekrar `0.50`'ye gelir → **İLK TP**, stop maliyete |
| ⑤ | Fiyat `0`'a gider → **NİHAİ TP** |

`0.50` iki kez kullanılıyor: önce ön koşul olarak, sonra ilk TP olarak. Aynı seviye,
farklı roller.

### Bias

| Çizim yönü | Bias |
|---|---|
| Aşağıdan yukarı (0 altta, 1 üstte) | **SHORT** |
| Yukarıdan aşağı (0 üstte, 1 altta) | **LONG** |

**Referans örnek (NEARUSDT.P, 30m):**
`0` = 2.241 · `1` = 2.649 · `0.79` = 2.563 · `0.70` = 2.527 · `0.50` = 2.445
Fiyat 1'den düştü, 0.50'ye (2.445) temas etti, 0.70'e (2.527) geri döndü → short girişi.
İlk TP 2.445, nihai TP 2.241, nihai stop 2.649.

---

## 0.1 Sözlük

Terimler burada tek anlama sabitlenir. Kod aynı isimleri kullanır.

| Terim | Tanım |
|---|---|
| **Leg (Bacak)** | Bir swing low'dan swing high'a (veya tersi) uzanan hareket. Fib'in çizildiği aralık. Uç tespiti `R-ZONE-02`. |
| **Likidite bölgesi** | Leg'in başladığı/bittiği, önceki swing'in aşıldığı bölge. |
| **İmpuls** | Normalden belirgin büyük gövdeli, tek yönlü hareket mumu. Ölçüt: gövde > `IMPULSE_MULT` × son 20 mumun **medyan** gövdesi. **`IMPULSE_MULT = 4.0`** (`OPEN-21` kapandı). OB tanımı buna dayanır. |
| **OB (Order Block)** | İmpuls hareketi öncesindeki **son ters yönlü mumun gövdesi**. İki zaman damgası taşır: `created_at` (gövdenin zamanı) ve `impulse_at` (OB'nin bilinebilir olduğu an). Değerlendirme `impulse_at`'ten önceye bakamaz. |
| **FVG** | Üç mumluk yapıda 1. mumun high'ı ile 3. mumun low'u arasındaki dokunulmamış boşluk (ters yön için simetrik). `created_at` = 3. mumun zamanı — boşluk ancak o mum kapanınca bilinir. |
| **Mitigasyon** | Fiyatın bir FVG/OB bölgesine ilk temas etmesi. **Dolum** ise karşı sınırın geçilmesidir; ikisi ayrı kaydedilir. |
| **"OB içinde FVG"** | Kesişim yeterlidir, tam kapsama aranmaz (`R-ADD-05`). |
| **Delinme** | OB'nin impuls mumlarıyla tamamen geçilmesi. Mum kapanışı beklenmez. Geçişin geçersiz sayılması için fiyatın OB'yi **tamamen geri alması** gerekir; yalnızca dokunmak yetmez — aksi hâlde "kapanış beklenmez" kuralıyla çelişir (`R-ADD-06`). |
| **Equity** | Bakiye + tüm açık pozisyonların gerçekleşmemiş PnL'i. Tüm risk hesapları buna göre. |
| **Zone object** | Kalıcı seviye nesnesi. Bir kez oluşturulur, durum makinesiyle takip edilir, her mumda yeniden hesaplanmaz. |

---

## 1. Zone modeli

### R-ZONE-01 · Zone bir nesnedir `SETTLED`

Kalıcı kayıt, durum makinesiyle takip edilir, her mumda yeniden hesaplanmaz.

Alanlar: `zone_id, symbol, timeframe, bias, anchor_0_price, anchor_0_time,
anchor_1_price, anchor_1_time, level_050, level_070, level_079, state,
created_at, state_changed_at, primed_at, touch_count, quality_score`

**`touch_count` tanımı:** fiyatın giriş bandına (`0.70–0.79`) **bant dışından her girişi**
bir temastır. Bant içinde geçen ardışık mumlar sayacı artırmaz — sayılan mum değil, olaydır.

İki kısıt:

- **Yalnızca `PRIMED`'den itibaren sayılır.** Fiyat `1`'den `0.50`'ye inerken bandın
  içinden zorunlu olarak geçer; bu temas her zone'da yapısı gereği vardır, bilgi taşımaz.
- **Histerezis zorunlu.** Yeni bir temas sayılması için fiyatın banttan belirgin şekilde
  çıkmış olması gerekir. Varsayılan pay: bant genişliğinin **%25**'i. Aksi hâlde 1m
  çözünürlükte bant sınırındaki titreşim sayacı şişirir.

**Ölçüm (NEAR §0 referans zone'u):** 30m = 3 · 1m histerezissiz = 13 · 1m histerezis 0.25 = **8**

> 30m sayısı doğru cevap değil, farklı çözünürlükte bir ölçüm. 30m'de bir "temas", yarım
> saatlik mumun aralığının bandı kesmesidir; fiyat o mum içinde üç kez girip çıksa bile
> tek sayılır. Kalibrasyon çapası 30m değil, **elle etiketlenmiş gözlem** olacak.
> Sabit `R-ZONE-08` tasarlanırken etiketli veriyle ayarlanır; o zamana kadar hem ham hem
> histerezisli sayı kaydedilir.

Amacı "bu zone kaç kez denendi" bilgisidir; tekrar tekrar denenen zone zayıflar.
`R-ZONE-08` kalite skorunun girdisidir.

### R-ZONE-02 · Uç tespiti `SETTLED`

- Geçerli uç, **kendinden önceki likiditeyi almış** olmalı (önceki swing'i aşmış)
- Minimum boy şartı **yok**
- Bakılan bölgedeki en yüksek/düşük noktalar. ATH/ATL değil.
- Birden fazla aday varsa **likiditeyi süpüren** seçilir

**Merdiven:** birden fazla likidite birikmiş ama geçilememişse merdiven sayılır.
Biri alınırsa sonrakinin alınma ihtimali yükselir → `R-ZONE-08` girdisi.

> `IMPL-01` — pivot teyidi N mum gecikme yaratır. Çapalar geçmişte olduğu için bu
> zone oluşturmayı geciktirir, girişi değil. Giriş zaten ②'den sonra geliyor,
> yani teyit için yeterli zaman var. **v0.2'de düşündüğümden daha küçük bir sorun.**

### R-ZONE-03 · Seviyeler `SETTLED`

Ön koşul **0.50** · Giriş **0.70–0.79** · İlk TP **0.50** · Nihai TP **0** · Nihai stop **1**

Fib hesabı **lineer** (log scale kapalı).

### R-ZONE-04 · Durum makinesi `SETTLED`

```
CREATED ──► ACTIVE ──► PRIMED ──► TOUCHED ──► ENTERED ──► TP1_HIT ──► CLOSED
               │          │           │
               └──────────┴───────────┴──► INVALIDATED
```

`INVALIDATED` yalnızca **pozisyon açılmadan önce** geçerlidir. `ENTERED` veya `TP1_HIT`
durumundayken `1`'e temas bir geçersizlik değil, bir **işlem sonucudur** (stop) → `CLOSED`.

| Durum | Giriş koşulu |
|---|---|
| `CREATED` | Çapalar belirlendi, seviyeler hesaplandı |
| `ACTIVE` | 0.50 teması bekleniyor |
| `PRIMED` | **0.50'ye temas edildi** — zone artık silahlı |
| `TOUCHED` | Fiyat 0.70'e geri döndü |
| `ENTERED` | Pozisyon açıldı |
| `TP1_HIT` | 0.50'ye ulaşıldı, kısmi kâr, stop maliyete |
| `CLOSED` | Nihai TP (0) veya stop (1) |
| `INVALIDATED` | R-ZONE-05 |

### R-ZONE-05 · Geçersizlik `SETTLED`

**Sıralama bozulursa zone ölür.**

| Durum | Geçersizlik |
|---|---|
| `ACTIVE` (0.50 bekleniyor) | `0`'a veya `1`'e temas |
| `PRIMED` (0.70 bekleniyor) | `0`'a veya `1`'e temas |
| `ENTERED` | `1`'e temas → nihai stop |

**Zaman aşımı yok.** Sadece bölge aşımı. Bir zone günlerce beklenebilir.

**Ara derinlik serbest.** `PRIMED` durumunda fiyat 0.50'yi geçip 0.40'a, 0.30'a inebilir;
zone geçerliliğini korur. Zone'u yalnızca `0` veya `1` teması öldürür.

`0.50`'ye temas etmeden `0`'a ulaşılırsa pozisyon zaten açılmamış olur — zarar yok.
Bu durum ya OTE'nin çalışmadığı ya da yanlış çizildiği anlamına gelir ve
`R-ZONE-08` kalibrasyonu için loglanır.

### R-ZONE-06 · Eşzamanlı zone `SETTLED` — CONFLICT-04 çözüldü

Pozisyon sayısına ayrı sınır **yok**. Sınır `R-RISK-01` (toplam notional tavanı) ve
`R-RISK-05` (likidasyon tamponu) tarafından dolaylı olarak konur.

Uygun görülen her zone aday sayılır ve izlemeye alınır. İzlenen zone sayısına sınır yok
(izlemek risk üretmez, yalnızca pozisyon açmak üretir).

### R-ZONE-07 · Zaman dilimi `SETTLED`

Sabit ana zaman dilimi yok.

| İşlem tipi | Zaman dilimleri |
|---|---|
| Yön tespiti | 4h ve üstü |
| Swing | 4h |
| Day trade / scalp arası | 30m, 15m |
| Scalp | 1m, 5m, bazen 15m |

Coinin genel yönü 4h+ ile belirlenir. **Yöne ters açılan işlemde uzun beklenmez.**

### R-ZONE-09 · Geometri HTF'den, temas 1m'den `SETTLED`

Zone'un **geometrisi** (leg, çapalar, seviyeler) tespit edildiği zaman diliminden gelir.
Zone'un **durum geçişleri** (0.50 teması, 0.70 teması, çapa teması) **1m mumlarla**
değerlendirilir.

Gerekçe: `R-ENTRY-02` "temas anında girilir, mum kapanışı beklenmez" diyor. Durum makinesi
30m mumla beslenirse temas tespiti yarım saat gecikir ve bu kural fiilen ölür.

**Mum içi belirsizlik.** Bir mumda hem ilerleme hem çapa teması varsa öldürme kazanır;
bir mumda birden fazla ilerleme varsa yalnızca ilki uygulanır. 1m'de bu durumlar nadirdir,
ama **kaç kez tetiklendiği sayaçta tutulur** — oran yüksek çıkarsa kural yeniden ele alınır.

**İzleme başlangıcı (`WATCH_FROM`).** Zone, kendi geçmişiyle beslenmez. HTF çapasının
tepesi HTF mumunun *içindedir*; o mumun 1m'lerini beslemek çapanın kendisine dokunur ve
zone'u doğduğu anda öldürür. Ayrıca bir swing'in uç olduğu ancak pivot teyidiyle bilinir
(`R-ZONE-02`, `IMPL-01`).

```
WATCH_FROM = max(anchor_1 HTF mumunun kapanışı, pivot teyit zamanı)
```

Leg tespiti elle yapıldığı sürece ilk terim taban olarak iş görür. **Tespit
otomatikleştiğinde ikinci terim asıl kısıt olur** ve atlanırsa doğrudan look-ahead bias
üretir.

**Tespit zaman dilimi.** 1m yalnızca **durum geçişleri** içindir. OB, FVG ve impuls
tespiti **5m ve üstünde** çalışır (`R-ZONE-07`'deki alt TF listesi: 4h, 30m, 15m, 5m).
Gerekçe: 1m'de gövde büyüklükleri tick sınırlarına oturduğu için gövde/medyan oranı
ayrık değerler alıyor ve eşik okuması kırılganlaşıyor — özellikle düşük fiyatlı
sembollerde.

**Ölçüm (NEAR, 2026-09):** aynı zone 30m yerine 1m ile beslendiğinde giriş teması
**25 dakika önce** yakalanıyor. Kazanç daha iyi fiyat değil — seviye aynı. Kazanç
**kaçırılmayan giriş**: 30m'de fiyat bant içine girip mum kapanmadan çıkarsa temas hiç
görünmez.

### R-ZONE-08 · Aday sıralaması `TASARLANACAK`

Sıralama yalnızca **bütçe sıkıştığında** devreye girer: `R-RISK-01` tavanına yaklaşılmışsa
ve birden fazla zone aynı anda giriş sinyali veriyorsa, hangisine girilecek.

Girdiler: merdiven durumu · 4h+ yön uyumu · giriş bandında OB/FVG varlığı ·
leg netliği · mevcut pozisyonlarla korelasyon.

Ağırlıklar backtest'le kalibre edilir, elle atanmaz.

---

## 2. Giriş

### R-ENTRY-01 · Marjin modu `SETTLED`
Cross. İzole yasak.

### R-ENTRY-02 · Tetik `SETTLED`

**Temas anında girilir. Mum kapanışı beklenmez.** Ön koşul: zone `PRIMED` durumunda olmalı.

1. Giriş bandında yöne uygun **OB** varsa → OB'den giriş (limit emir konabilir)
2. Bantta **FVG** varsa → doldurulması beklenebilir
3. Gösterge yoksa → **0.70 teması** geçerli giriştir
4. **Hacimliyse** → kaçırmamak için doğrudan 0.70 teması, bekleme yok

### R-ENTRY-03 · Boyutlandırma `SETTLED` — CONFLICT-01 çözüldü

**Ölçü birimi notional, marjin değil.**

Gerekçe: kaldıraç her zaman coinin desteklediği maksimum. Bu değer coinden coine
değişiyor (BTC 125x, yeni altcoin 20x). Sabit marjin yüzdesi bu yüzden coinden coine
farklı risk üretir. Notional sabit tutulunca sorun kalkar:

| Coin | Kaldıraç | Marjin | Notional |
|---|---|---|---|
| BTC | 125x | %0.8 | 1.0 × equity |
| Altcoin | 20x | %5.0 | 1.0 × equity |

İkisi **aynı risk**. Marjin yüzdesi yanıltıcı, notional değil.

```
notional = equity × K
marjin   = notional / kaldıraç      (türetilmiş değer, hedef değil)
```

| Durum | K (notional katsayısı) |
|---|---|
| Standart | **1.0** |
| Riskli görünüm | **0.5** |
| Yön tek tarafa hızlı ve kesinse | **5.0**'a kadar, maks 1-1 ekleme sonrası çıkılır |

> Bu tablo eski "%1 / %0.5 / %5" ifadesinin birebir karşılığı — BTC'de 125x kaldıraçla
> %1 marjin zaten 1.25 kat notional demekti. Zihinsel modelin değişmiyor, birim değişiyor.

### R-ENTRY-04 · Kaldıraç `SETTLED`

**Her zaman coinin desteklediği maksimum. Asla düşürülmez.**
Risk ayarı gerekiyorsa notional (`K`) üzerinden yapılır, kaldıraç üzerinden değil.

---

## 3. Ekleme

### R-ADD-01 · İzin koşulları `SETTLED`
1. Fiyat giriş bandının ötesinde (pozisyon eksi bölgede)
2. Alt TF'lerin birinde yöne uygun **OB** tespit edildi
3. OB'den dönüt alındı (R-ADD-05)
4. Nihai stop (`1`) henüz ihlal edilmedi
5. `R-RISK-05` likidasyon tamponu ihlal edilmiyor

### R-ADD-02 · Red koşulları `SETTLED`

| Kod | Koşul |
|---|---|
| `ADD-REJECT-A` | Ekleme sonrası, öngörülen dönüş noktasına kadar risk artacaksa |
| `ADD-REJECT-B` | Toplam notional `R-RISK-01` tavanını aşacaksa |
| `ADD-REJECT-C` | Dönüş beklenen OB hacimle delindi (R-ADD-06) |
| `ADD-REJECT-D` | `R-RISK-05` likidasyon tamponu ihlal edilecekse |

### R-ADD-03 · Ekleme boyutu `SETTLED` — CONFLICT-02 çözüldü

Çarpanlar: **1-1, 1-3, 1-5, 1-10** (mevcut pozisyonun katları).

Çarpan, maliyeti "fiyatın en fazla gideceği tahmin edilen nokta"nın ötesine çekecek
şekilde seçilir. Temkinli taraf tercih edilir.

| Senaryo | Maks ekleme | Ulaşılan notional |
|---|---|---|
| K=1.0 başlangıç, 1-1 ekleme | 3 kez | 8.0 × equity |
| K=1.0 başlangıç, 1-10 ekleme | 1 kez | 11.0 × equity |

**Tavan aşımı bilinçli olarak kabul edildi.** 1-10 ekleme maliyeti düşürmek için gerekli;
9x ekleme istenen seviyeye çıkarmayabilir. `R-RISK-01` tavanı bu senaryoda esnetilir,
`R-RISK-05` esnetilmez.

### R-ADD-04 · Ekleme sonrası `SETTLED`
Ortalama maliyet güncellenir · Nihai stop `1`'de kalır · Notional `K=1.0` tabanına dönülür.

### R-ADD-05 · "Güçlü dönüt" `SETTLED`

OB'ye temas dönüt habercisidir. **Tek OB tek başına yeterlidir.**

- **Gücü artıran:** OB içinde doldurulacak FVG; ters yönlü OB bulunmaması
- **Gücü azaltan:** ardı ardına gelen OB'ler → çalışma oranı düşer

### R-ADD-06 · Hacim ve delinme `SETTLED`

**Hacimli mum:** normalden kat kat büyük **gövdeli** mum. İğne atıp geri çekilen değil.
Hacmin özü: kısa sürede çok işlem.

**Bölgesel hacim göstergesi:** bölgedeki zigzag yoğunluğu.

**Hacimli delinen OB:**
- Normalden büyük mumlarla OB'nin içinden geçilmesi
- Tek mum şart değil; tek muma yakınlık hacmi artırır
- **Mum kapanışı beklenmez** — OB'nin tamamen geçilmesi yeterli
- Altına inip hemen dönme → grafik hatası / geç tepki, delinme sayılmaz

**Stop yerleşimi:** OB'nin kendi çizgisine.

---

## 4. Risk

### R-RISK-01 · Toplam notional tavanı `SETTLED`

Normal koşulda **10 × equity**. 1-10 ekleme senaryosunda **11 × equity**'ye kadar esner.

> Bu tavan, eski "%10 toplam marjin" kuralının notional karşılığı.
> BTC'de 125x kaldıraçla %10 marjin zaten 12.5 kat notional demekti.

### R-RISK-02 · Nihai stop `SETTLED`

**Her zaman `1` seviyesi.** Borsaya emir olarak gönderilmez, bot içinde tutulur ve
**pozisyon açıldığı andan itibaren daima aktiftir.**

> İnsan pratiğinde "likidasyon fiyatı görünmüyorken SL koymam" kuralı vardı. Bu kural
> **borsaya gönderilen** stop emri hakkındaydı — botta zaten öyle bir emir yok.
> Botun içindeki stop `1` seviyesi olarak her zaman bilindiği ve borsada iz bırakmadığı
> için sürekli aktif tutulur. Maliyeti sıfır, faydası pozisyonun hiçbir anda tanımsız
> riskte kalmaması.

### R-RISK-03 · Günlük kayıp sınırı `SETTLED` — CONFLICT-03 çözüldü

**Strateji önce gelir.** Günlük limit pozisyon kapatmaz. Görevi:

- Gün içi zarar eşiği aşılırsa **yeni pozisyon açmayı durdurur**
- Mevcut pozisyonlar TP/stop bekler
- Açık zarar, uygun ekleme ile çevrilmeye çalışılır

Eşik `OPEN-16`. Gerçek durdurucu bu değil, `R-RISK-05`.

### R-RISK-04 · Kâr hedefi `SETTLED`
Yok. Kazancın ucu açık. Yalnızca garantiye alma devreye girebilir (R-EXIT-02).

### R-RISK-05 · Likidasyon tamponu `SETTLED (eşikler kalibre edilecek)` — **gerçek sert sınır**

İnsan kuralı: *"liq fiyatı yaklaşmadıkça devam."* Sistemdeki tek esnetilemez sınır bu.

**Neden mesafe olarak tanımlandı.** Cross marjinde likidasyon fiyatı matematiksel olarak
her zaman vardır; borsa yalnızca göstermeyebilir. Long'da hesaplanan likidasyon fiyatı
sıfırın altına düşüyorsa ekranda görünmez. Short'ta fiyatın üst sınırı olmadığı için
likidasyon fiyatı **her zaman sonlu ve görünür**. Yani "liq fiyatı görünmüyor" kuralı
short'larda hiç devreye girmez — bot için kullanılamaz.

```
liq_mesafe = |likidasyon_fiyatı − mark_fiyat| / mark_fiyat
```

| Bölge | Koşul | Davranış |
|---|---|---|
| **RAHAT** | `liq_mesafe > T_rahat` | Normal çalışma. İnsan pratiğindeki "liq fiyatı yok" hâlinin karşılığı. |
| **UYARI** | `T_kritik < liq_mesafe ≤ T_rahat` | Yeni pozisyon açılmaz · ekleme reddedilir (`ADD-REJECT-D`) · maliyette marj düşürme devreye girer |
| **KRİTİK** | `liq_mesafe ≤ T_kritik` | Pozisyon küçültülür · `R-KILL-04` |

**Eşikler backtest ve paper trading ile kalibre edilir.** Başlangıç değerleri sırasıyla
`T_rahat = %50`, `T_kritik = %15` olarak alınır ve §9'daki "likidasyona en yakın mesafe"
sayacına göre revize edilir.

Bu üç bölge, insan pratiğindeki üç davranışın birebir karşılığı: uzakken serbest çalışma,
yaklaşınca stop ve marj düşürme, kritikte müdahale.

> **Ölçek notu.** `R-RISK-01` tavanında (10 × equity notional), piyasa aleyhine
> **%1 hareket ettiğinde hesap %10 hareket eder**. Cross marjinde likidasyon yaklaşık
> **%8–10'luk** aleyhte bir hareketle gelir. Altcoinler yüksek korelasyonlu olduğu için
> 10 ayrı pozisyon, genel bir düşüşte 10 ayrı olay değil tek bir olaydır.
>
> Bu bir itiraz değil, spec'in aritmetik sonucu. Paper trading'in ölçeceği ilk şey bu
> olacak (bkz. §9 sayaçlar).

---

## 5. Çıkış

### R-EXIT-01 · İlk TP `SETTLED`
**0.50 seviyesinde, pozisyonun ~%50'si.** Alt sınır: işlem ücretlerini karşılayacak kadar.
Sonrasında stop maliyete çekilir.

### R-EXIT-02 · Nihai TP `SETTLED`
**`0` seviyesi.**

**Garantici mod:** likidite alınmadan önce çıkılabilir. Tanım: işlem ücretinin üstüne konan
en küçük kâr da garanticiliktir. Hedef dışında bile kârdaysan uygulanabilir.
→ Tetikleyici koşul `OPEN-13`.

### R-EXIT-03 · Süre `SETTLED`
Zaman sınırı yok. Günler, haftalar (3 haftaya kadar gözlem var).
Funding maliyeti backtest'te zorunlu olarak modellenir.

---

## 6. Kill switch

`R-KILL-01` veri bütünlüğü · `R-KILL-02` borsa iletişimi · `R-KILL-03` tutarlılık ·
`R-KILL-04` `R-RISK-05` ihlali · `R-KILL-05` anormal piyasa (`DEFERRED`, loglanır) ·
`R-KILL-06` manuel durdurma

Tüm kill switch'ler ve risk kuralları arayüzde **açık/kapalı switch** olarak sunulacak.
Varsayılan: hepsi açık.

---

## 7. Açık maddeler

| ID | Konu | Not |
|---|---|---|
| `OPEN-23` | **OB/FVG anlamlılık ölçütü** | **Öncelikli** — aşağıya bakın |
| `OPEN-13` | "Garantici mod" tetikleyicisi | Açık — v1'de kapalı, sonra eklenir |
| `OPEN-16` | Günlük yeni-pozisyon durdurma eşiği | Backtest'le kalibre (başlangıç %10) |
| `OPEN-17` | Likidasyon tamponu eşikleri | Backtest'le kalibre (başlangıç %50 / %15) |
| `OPEN-12` | Harmonik oran tablosu + stop kanadı | v2 modülü |
| `OPEN-14` | Yeni listelenen coin stratejisi | Ayrı model, v2 |

### OPEN-23 — OB/FVG anlamlılık ölçütü

**Ölçüm (NEAR 30m, 09-08 13:30 → 09-10 12:00, ≈92 mum):** 17 OB, 21 FVG tespit edildi.
Giriş bandında (2.527–2.563) 3 OB ve 2 FVG.

Ortalama her 5 mumda bir OB, mevcut tanımın fazla geçirgen olduğunu gösteriyor.
Sonucu şu: `R-ENTRY-02`'nin "bantta OB varsa OB'den gir" kuralı neredeyse her zaman
tetikleniyor — OB bir **filtre** olmaktan çıkıp sabit davranışa dönüşüyor.

İnsan pratiği bu sorunu zaten biliyor: *"OB'ler ardı ardına olunca çalışma oranları düşer"*
(`R-ADD-05`). Trader görsel olarak anlamlı olanı seçiyor; motor hepsini buluyor.

**Kapatma yöntemi:** NEAR listesi grafikte elle karşılaştırılır — bu 17'nin kaçı gerçekten
OB sayılırdı? Aradaki fark anlamlılık ölçütünü verir. Aday girdiler: impuls büyüklüğü,
OB sonrası hareketin menzili, kümelenme cezası, HTF yön uyumu.

**`OPEN-21` kapandı, ama sorunu çözmüyor.** Ölçüm (tüm NEAR verisi, 30m 30.240 mum /
1m 585.495 mum): gövde/medyan oranı `2.0` = p78 (mumların %22'si), `3.0` = p91,
`4.0` = p95. Eşik **4.0**'a çıkarıldı — %4.5'lik oran "normalden kat kat büyük"
tanımına uyan tek seviye. Dağılım iki TF'de neredeyse aynı; medyan normalizasyonu
sembol ve TF başına ayrı eşik gerektirmiyor.

**Ama eşik anlamlılığı seçmiyor.** Ölçüm: impuls büyüklüğü, OB sonrası menzili
öngörmüyor — 2.2x impuls %1.3 menzil üretirken 4.1x %15.6, 3.6x ise %5.6 üretiyor.
Eşiği yükseltmek yoğunluğu azaltır, iyi OB'yi seçmez.

**Test edilecek hipotezler** (hepsi mevcut kurallardan):

| Hipotez | Kaynak |
|---|---|
| İçinde dolmamış FVG olan OB daha geniş menzil üretir | `R-ADD-05` |
| Ters yönlü OB varlığı menzili düşürür | `R-ADD-05` |
| Ardışık OB serisi menzili düşürür | `R-ADD-05` |
| 4h+ yön ile uyumlu OB daha geniş menzil üretir | `R-ZONE-07` |
| Likidite süpürmesi sonrası oluşan OB daha güçlüdür | `R-ZONE-02` |

**Aşırı uyum koruması:** ölçüt çok sembolde ve geniş dönemde aranır; verinin en yeni
**%20'si ayrılır ve dokunulmaz**. Bulunan ölçüt ancak ayrılmış bölümde de çalışırsa
geçerli sayılır.

---

### Harmonik — erteleme gerekçesi (düzeltildi)

v0.2'de yöntemi yanlış tarif etmiştim. Doğrusu: X-A-B-C-D noktaları işaretlenir,
her bacağa ayrı retracement çekilir (X→A, A→B, ...), oranların hedef seviyelere denk
gelip gelmediğine bakılır. **Bu deterministik bir yöntem, look-ahead bias içermiyor.**

Erteleme sebebi metodoloji değil, **eksik parametre**: oran tablosu doldurulmadı,
stop kanadının yeri belirsiz.

**Plan:** fib ve XABCD fonksiyonları v1'de yazılır (zaten OTE için gereken altyapının
üzerine oturuyor), formasyon tanımları netleştiğinde deneysel modül olarak açılır,
başarısı backtest'le ölçülür. Bot çalışır hâle geldikten sonraki aşama.

---

## 8. Backtest edilebilirlik

### Veri gereksinimi

| Kural | Gereken veri |
|---|---|
| R-ENTRY-02 (temas girişi) | 1m OHLCV minimum |
| R-ADD-06 (hacimli delinme) | 1m + hacim |
| R-RISK-05 (likidasyon takibi) | 1m mark price |
| R-EXIT-03 (haftalarca pozisyon) | **Funding rate geçmişi zorunlu** |

### Intrabar belirsizliği

Doğru kural "önce dokunulan sayılır". Ancak OHLCV verisinde bir mum içindeki **sıralama
bilgisi yoktur** — bu bir tercih değil, veri sınırı.

**Yaklaşım:** 1m veriyle çalışılır. Bir 1m mumunda hem TP hem SL seviyesine dokunulmuşsa:
- İşlem `ambiguous` olarak işaretlenir
- Muhafazakâr varsayımla (SL önce) hesaplanır
- **Ayrı sayaçta raporlanır**

| Belirsiz işlem oranı | Yorum |
|---|---|
| < %5 | Sonuç güvenilir |
| %5–20 | Dikkatli yorumlanır, duyarlılık analizi yapılır |
| > %20 | **Sonuç kullanılamaz** — tick/trade verisine geçilir |

Böylece varsayım tartışması ölçüme dönüşür.

### Maliyet modeli — zorunlu

Taker/maker komisyonu + funding + slippage. Oranlar borsanın yayınladığı listelerden
alınır, tahmin edilmez.

### Zorunlu sayaçlar

Her backtest ve paper trading koşusu şunları raporlar:

| Sayaç | Neden |
|---|---|
| Maksimum drawdown | Temel risk ölçüsü |
| **Likidasyona en yakın mesafe** | `R-RISK-05` kalibrasyonu |
| **"Gerçek parada likide olurduk" sayacı** | Cross + max kaldıraç + korelasyon etkisi |
| Eşzamanlı açık pozisyon dağılımı | `R-RISK-01` tavanının ne sıklıkla bağladığı |
| Pozisyonlar arası korelasyon | Efektif pozisyon sayısı |
| Belirsiz (`ambiguous`) işlem oranı | Sonuç güvenilirliği |
| Toplam funding maliyeti | Uzun taşınan pozisyonların gerçek maliyeti |
