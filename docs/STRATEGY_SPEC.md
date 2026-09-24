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
| **Stop kaybı tavanı (`L`)** | Bir pozisyonun nihai stopa giderse realize edeceği kaybın equity'ye oranı tavanı. **`STOP_LOSS_CAP = 0.03`** (`L` = %3, `OPEN-33` kapandı). Ölçü notional değil, **stopta realize olacak kayıptır**; `R-ADD-02 · ADD-REJECT-E` hem eklemeye hem ilk girişe uygular. `0` = kural kapalı. |
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

Ölçüm: `docs/measurements/zones.md`

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

Ölçüm: `docs/measurements/zones.md`

### R-ZONE-10 · Piyasa yapısı — yön, leg ve likidite `SETTLED (parametreler kalibre edilecek)`

Yön, leg ve likidite tek bir ilkelden türer: **swing noktası tespiti**. Üçü ayrı problem değil.

**Swing tespiti.** Fraktal pivot `N = 2` (5 mumluk yapı) + minimum yer değiştirme filtresi
`0.5 × ATR(14)`. İkisi de parametredir, backtest süpürecek. Bir swing ancak teyitlendiği
mumda bilinir ve `pivot_confirmed_at` taşır (`R-ZONE-09` `WATCH_FROM` bunu kullanır).

**Etiketleme.** Her swing önceki aynı tip swing'e göre HH / HL / LH / LL etiketlenir.

**Yön (bias).** `HH + HL` → `UP` · `LH + LL` → `DOWN` · karışık → `NONE`.
4h ve üstünde hesaplanır (`R-ZONE-07`).

Ölçüm: `docs/measurements/zones.md`

**Likidite süpürmesi.** Bir swing, önceki aynı tip swing'i aşmışsa likidite alınmıştır
(BoS). `R-ZONE-02`'nin "kendinden önceki likiditeyi almış olmalı" şartının karşılığı.

**Leg seçimi.** `anchor_1` = likiditeyi süpüren swing. `anchor_0` = o hareketi başlatan
bir önceki karşı yönlü swing. Birden fazla aday varsa süpüren tercih edilir (`R-ZONE-02`).

### R-ZONE-08 · Aday sıralaması `TASARLANACAK`

Sıralama yalnızca **bütçe sıkıştığında** devreye girer: `R-RISK-01` tavanına yaklaşılmışsa
ve birden fazla zone aynı anda giriş sinyali veriyorsa, hangisine girilecek.

Girdiler: merdiven durumu · 4h+ yön uyumu · giriş bandında OB/FVG varlığı ·
leg netliği · mevcut pozisyonlarla korelasyon.

Ağırlıklar backtest'le kalibre edilir, elle atanmaz.

**Girdi adaylarının dayanıklılığı ölçüldü — hiçbiri eşiği geçmedi.** Eğitim dilimi
zamanda ikiye bölündü; bir özellik ancak iki yarıda da **aynı işareti** verir ve
**≥14/20 sembolde tutarlı** olursa ağırlık adayı sayılır
(`docs/measurements/robustness.md`):

| aday | H1 → H2 (net bps/işlem) | sembol tutarlılığı | sonuç |
|---|---|---|---|
| leg büyüklüğü (üst − alt tertil) | +31,5 → +33,3 | 13/20 → 17/20 | işaret sabit, eşiği **bir sembol** farkla kaçırdı |
| giriş dalı (OB − FVG) | +25,6 → +22,7 | 4/20 → 5/20 | işaret sabit ama OB akışın %6'sı — sembol düzeyinde **ölçülemedi** |
| 4h yön uyumu (`R-ZONE-10`) | +5,9 → +7,0 | 10/20 → 12/20 | en iyi ölçülen ama en zayıf ayrım |
| `touch_count` (1 − 2+) | +24,0 → −9,2 | 1/20 → 4/20 | **işaret döndü**; işlemlerin %95'i tek temas — bu giriş kuralıyla ölü |
| tick/leg oranı (sembol) | −4,7 → −0,9 | 12/20 → 11/20 | etki eriyor, gürültü seviyesinde |

> Leg büyüklüğü etkisi ayrıştırıldığında komisyon **bps'i leg'den bağımsız** (her
> tertilde 5,5-5,7 bps) ve fark tamamen brütte; riske göre normalize edilince
> +31 bps yalnızca **+0,04 R**'ye düşüyor. Yani "büyük leg daha iyi" bir edge
> cümlesi değil, bir **sürtünme** cümlesidir: küçük leg'in sabit komisyonu payını
> tamamen yiyor. Buradan çıkan aday bir sıralama ağırlığı değil, **asgari leg
> büyüklüğü** eşiğidir — bu bir `R-ENTRY` filtresi olur ve ölçülmedi.

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

### R-ENTRY-05 · OB ve FVG uygunluğu `SETTLED`

**OB:** yalnızca **unmitige** olanlar aday. Fiyat bir kez uğradıysa bölge tüketilmiş
sayılır. Bu ölçüt yoğunluğu kendiliğinden sınırlar — her OB yalnızca ilk temasa kadar canlıdır.

**FVG:** **karar anında dolmamış** olmalı **ve** genişlik ≥ `0.44 × medyan gövde (20 mum)`.

> Her iki ölçüt de nedenseldir: mitigasyon ve dolum durumu karar anında bilinir, FVG
> genişliği oluşum anında bilinir. "20 mum dayandı" gibi geriye dönük bir ölçüt
> **kullanılamaz** — karar anında bilinemez, look-ahead üretir.

Ölçüm: `docs/measurements/ob_fvg.md`

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
| `ADD-REJECT-E` | Ekleme sonrası pozisyonun **stopta kaybedeceği tutar** `L × equity`'yi aşacaksa |

#### `ADD-REJECT-E` · Pozisyon seviyesinde stop kaybı tavanı `SETTLED`

```
ekleme sonrası toplam notional × |stop(1) − ortalama maliyet| / ortalama maliyet
        >  L × equity          →  ekleme reddedilir
```

Sol taraf, pozisyon nihai stopa (`1`) giderse **realize olacak kayıptır**. Notional
`miktar × ortalama maliyet` olduğu için ifade `miktar × |stop − maliyet|`e sadeleşir;
kod sadeleşmiş hâli kullanır (`Backtest._stop_loss`).

**Aynı kısıt ilk girişe de uygulanır.** Pozisyon daha açılmadan stopta kaybedeceği
tutar tavanı aşıyorsa açılmaz. Bu, kuralı bir "ekleme freni" olmaktan çıkarıp
pozisyon seviyesinde bir risk tavanı yapar: `R-ENTRY-03`'ün `K × equity` notional'i
leg geometrisine göre çok farklı stop mesafeleri üretir ve tek başına risk ölçüsü değildir.

**`L` = %3** — `OPEN-33` ile kapandı. Kod sabiti `STOP_LOSS_CAP = 0.03`
(`src/backtest/engine.py`). Ölçüm: `docs/measurements/add_reject_e.md`.

> **Değer net PnL'e göre seçilmedi.** Net üç `L` adayında ayırt edilemiyor ve
> sıralama monoton bile değil: %10'da −186, %5'te −727, %3'te −176. Aralarındaki
> fark tek bir işlemin sonucuyla yer değiştirecek büyüklükte, yani gürültü; bir
> parametreyi buna göre seçmek 20 sembollük eğitim dilimine uydurmak olurdu.
>
> Seçim, kuralın **var olma nedeni** olan kuyruk riskine göre yapıldı — maks
> drawdown `L`'de monoton: kapalı %63,6 → %10'da %27,6 → %5'te %26,5 → %3'te
> **%24,1**, ve komisyon/slippage ×1.5 stresinde de monoton kalıyor (%39,8 → %30,7).
> Aynı yönde: başlangıcın yarısının altında geçen bar oranı %23,6 → **%0**, en kötü
> tek işlem −4.766 → −331 (14 kat), kazanan sembol 10/20 → 13/20. Dört ölçünün
> dördü de `L` küçüldükçe iyileşiyor; net ise bir şey söylemiyor.

> **Neden `R-RISK-01` yetmedi.** `R-RISK-01` tavanı **notional** cinsindendir ve
> ekleme *boyutunu* bağlamaz: `R-ADD-03` çarpan merdiveni çarpımsaldır (iki ekleme
> `×4` sonra `×6` = girişin **24 katı**) ve equity pozisyonla birlikte düştüğü için
> `10 × equity` tavanına hiç değilmez. Ölçümde tek bir pozisyon hesabın toplam
> kaybından fazlasını taşıdı (ORDI −4.792, MAE equity'nin %86,6'sı).
> `ADD-REJECT-E` tavanı notional'a değil **stopta realize olacak kayba** koyar.

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

Ortalama maliyet güncellenir · Nihai stop `1`'de kalır.

**Maliyete dönüşte küçültme — çıkış değil, durum geçişi.** Ekleme sonrası fiyat ortalama
maliyete döndüğünde pozisyon `K` tabanına indirilir. Kalan kısım yoluna devam eder:

| | |
|---|---|
| Nihai stop | `1` |
| İlk TP | `0.50` (R-EXIT-01) |
| Nihai TP | `0` (R-EXIT-02) |

Küçültme **ortalama maliyeti değiştirmez** — kalan kısmın maliyet tabanı, hedefleri ve
stopu küçültme öncesiyle aynıdır. Pozisyon kapanmaz; raporda çıkış nedeni olarak değil
`REDUCED` durumu olarak sayılır (kaç işlem küçültüldü, küçültmeden sonra ne oldu).

Her ekleme tetiği yeniden kurar: küçültmeden sonra yeni bir ekleme yapılırsa, fiyatın
**yeni** ortalama maliyete dönmesi tekrar küçültme üretir.

> Küçültme hedefi `K × equity` notional'dir (R-ENTRY-03'ün standart giriş boyutu) ve
> equity küçültme anında ölçülür. Hedef mevcut boyutun üstündeyse hiçbir şey yapılmaz —
> kural küçültmedir, büyütme değil.

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

**Bu tavan ekleme boyutunu sınırlamıyordu — `ADD-REJECT-E` sınırlıyor.** Ölçümde
`R-RISK-01` hiç bağlamadı: `R-ADD-03` çarpanları çarpımsal olduğu için iki ekleme
girişin 24 katına çıkabiliyor, ama equity de pozisyonla birlikte düştüğünden
`10 × equity` tavanına erişilmiyor. Tek bir pozisyon hesabın toplam kaybından
fazlasını taşıdı. Boyutu bağlayan kural, notional yerine **stopta realize olacak
kaybı** ölçen `ADD-REJECT-E`'dir (`R-ADD-02`).

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

**Eşikler süpürülecek, sabitlenmeyecek.** İlk değerler (`T_rahat = %50`,
`T_kritik = %15`) tahmindi ve ölçümde fazla sıkı çıktı.

Ölçüm: `docs/measurements/risk05_sweep.md`

Backtest `T_rahat` ve `T_kritik` üzerinde ızgara süpürmesi yapar ve her ayar için
**hem getiri hem likidasyon sayacı** raporlanır. Takas o tablodan okunur.

**Kısıt: `T_kritik < T_rahat`.** Aksi hâlde UYARI bandı ters döner ve sonuç koşulların
değerlendirilme sırasına bağlı bir artefakt olur. Bu kısıtı sağlamayan ızgara hücreleri
çalıştırılmaz ve raporda "atlandı" olarak görünür.

**KRİTİK davranışı.** Pozisyon **yarılanır** (`OPEN-28`). Yarılama `equity/notional`
oranını ikiye katladığı için bölgeden sınırlı adımda çıkılır; eşiği tam hedefleyen bir
küçültme sınırda salınıma girer.

> **Yapısal maliyet.** Bu strateji zarardayken ekleyerek maliyet düşürür. KRİTİK bölgede
> zorla küçültmek, aleyhte hareketin dibinde satmak demektir — pozisyon yarılanır, sonra
> fiyat döner ve kalan yarım pozisyonla dönüşe katılınır. `R-RISK-05` bu stratejiye karşı
> yapısal olarak pahalıdır; alternatifi likidasyondur. Izgaranın ölçtüğü asıl takas budur.
>
> Rapor, kaldıraç azaltma olaylarında **realize edilen zararı ayrı kalem** olarak verir.

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
Sonrasında stop **işlem ücreti dahil** maliyete çekilir.

**Maliyet tanımı (`OPEN-35` kapandı).** Breakeven seviyesi, ortalama maliyetin kalan
miktarın gidiş-dönüş **komisyonu** kadar kâr tarafına ötelenmiş hâlidir: giriş oranı
(limit girişte maker, aksi hâlde taker) + çıkış oranı (breakeven piyasa emridir,
taker). Slippage kapsam dışıdır — yayınlanan oran değil, varsayım (§8). Öteleme ilk TP
seviyesini geçemez. Ham ortalama maliyet yanlış uygulamaydı: kuralın kendi "işlem
ücretlerini karşılayacak kadar" ifadesine aykırı, breakeven'da kapanan yarı komisyon
kadar zarar bırakıyordu. Kod: `Backtest._breakeven`, `breakeven_fees=True` varsayılan.

> Ölçüm (`docs/measurements/robustness.md`, taban E3, 20 sembol): öteleme 7 bps,
> net **−176 → −134**, maks drawdown %24,1 → **%23,7**, TP1 sonrası stop 9 → **2**.

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
| `OPEN-24` | 4h+ "yön" ölçütü | **Kapandı** — `R-ZONE-10` |
| `OPEN-26` | FVG anlamlılık ölçütü | **Kapandı** — `R-ENTRY-05` |
| `OPEN-01` | Leg / likidite tespiti | **Kapandı** — `R-ZONE-10` |
| `OPEN-25` | `evaluate_strength` komşuluk penceresi | **Kapandı** — 50 mum sabitlendi |
| `OPEN-23` | OB anlamlılık ölçütü | **Kapatıldı** — aranmayacak (`docs/measurements/ob_fvg.md`) |
| `OPEN-28` | KRİTİK bölgede küçültme oranı | **Basitleştirildi** — yarılama seçildi (sonlanma garantisi, salınım yok). Spec'te tanımlı değildi. |
| `OPEN-27` | Ekleme çarpanı seçim kuralı (`R-ADD-03`) | **Basitleştirildi** — ilk backtest daima 1-1 ekliyor. "Fiyatın gideceği tahmin edilen nokta" hiç sayısallaşmadı; `ADD-REJECT-A` ile birlikte açık. |
| `OPEN-29` | Pozisyon sonlandırma kuralı | **Açık** — `R-EXIT-03` zaman sınırı tanımıyor. `R-ADD-04` küçültmesinden sonra bir pozisyonun tek sonlandırıcısı nihai stop/TP; ölçümde 202 gün açık kalan pozisyon var. Üç aday `scripts/terminate.py` ile ölçülüyor; kod varsayılanı `none` (spec'in hâli). |
| `OPEN-35` | `R-EXIT-01` breakeven'in "maliyet"i ücret dahil mi | **Kapandı** — ücret dahil (gidiş-dönüş komisyonu, slippage hariç). `R-EXIT-01`. Ölçüm `docs/measurements/robustness.md`. |
| `OPEN-33` | Ekleme merdiveninin boyut tavanı | **Kapandı** — `ADD-REJECT-E` (`R-ADD-02`). Tavan notional'da değil, stopta realize olacak kayıpta. |
| `OPEN-13` | "Garantici mod" tetikleyicisi | Açık — v1'de kapalı, sonra eklenir |
| `OPEN-16` | Günlük yeni-pozisyon durdurma eşiği | Backtest'le kalibre (başlangıç %10) |
| `OPEN-17` | Likidasyon tamponu eşikleri | Backtest'le kalibre (başlangıç %50 / %15) |
| `OPEN-12` | Harmonik oran tablosu + stop kanadı | v2 modülü |
| `OPEN-14` | Yeni listelenen coin stratejisi | Ayrı model, v2 |

### Ölçüm tarihçeleri

Kurallar bu dosyada, onları üreten ölçümler ayrı dosyalarda:

| Konu | Dosya |
|---|---|
| `OPEN-23` OB/FVG anlamlılığı · `IMPULSE_MULT` · FVG genişliği · delinme ufku | `docs/measurements/ob_fvg.md` |
| `R-ADD-05` / `R-ZONE-02` / `R-ZONE-07` hipotez testleri ve metodoloji | `docs/measurements/hypotheses.md` |
| Giriş seviyesi varyantları (`R-ENTRY-02`) | `docs/measurements/entry_variants.md` |
| `R-RISK-05` eşik ızgarası | `docs/measurements/risk05_sweep.md` |
| Tanı koşusu — brüt/net beklenti, çıkış nedenleri | `docs/measurements/diagnose.md` |
| Zone çözünürlüğü — `touch_count`, 1m temas, bias vekili | `docs/measurements/zones.md` |
| Salınım tavanı · limit emri doluşu · gösterge kapısı (A/B/C/D kolları) | `docs/measurements/levers.md` |
| TP yerleşimi (`R-EXIT-01/02`) · öteleme · piyasa emri · sembol yoğunlaşması | `docs/measurements/tp_placement.md` |
| `ADD-REJECT-E` stop kaybı tavanı (`L`) · dayanıklılık (maliyet ×1.5) | `docs/measurements/add_reject_e.md` |
| Breakeven komisyonu (`OPEN-35`) · komisyonun sonuç dağılımı · `R-ZONE-08` bölünmüş iç validasyon | `docs/measurements/robustness.md` |
| F1 ekleme kapalı · F2 asgari leg eşiği · dayanıklılık (taban E3B) | `docs/measurements/f_kollari.md` |

**Aşırı uyum koruması:** verinin en yeni **%20'si ayrılmıştır ve okunmaz**. Ölçüm
betikleri bu tarih aralığını reddeder. Bulunan her ölçüt ancak ayrılmış bölümde de
çalışırsa geçerli sayılır.

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
