# LIVE — canlı döngü tasarımı

| | |
|---|---|
| **Durum** | Tasarım taslağı, 2026-09-29. Kod yok. |
| **Otorite** | `STRATEGY_SPEC.md` > `ARCHITECTURE.md` > bu belge. Çelişkide üstteki kazanır. |
| **Aşama** | CLAUDE.md çalışma sırası adım 7 (PaperAdapter + canlı döngü). Adım 5 (`src/risk/`) ve 6 bitmeden kod yazılmaz. |

Bu belge kural uydurmaz. Karar gerektiren her nokta §9'da `OPEN-XX` olarak durur.

---

## 1. Tek kod yolu

### İlke

Zone, feature, strateji ve risk kodu backtest ile **aynı fonksiyonlardır**. Canlıda farklı
olan yalnızca iki şeydir:

1. **Veri kaynağı.** Parquet yerine WebSocket ve REST.
2. **`ExecutionAdapter`.** Motorun içindeki doluş simülasyonu yerine `PaperAdapter` ya da
   `LiveAdapter` kullanılır.

`if paper_mode:` ya da `if live:` dalı strateji/risk kodunda bulunmaz (CLAUDE.md #9).

### Bugünkü kod bu ilkeyi henüz sağlamıyor

`src/backtest/engine.py` üç katmanı tek sınıfta taşıyor: strateji (`_arm_entry`, `_try_add`),
risk (`_risk05_zone`, `_deleverage`, `_daily_loss_hit`) ve doluş simülasyonu
(`_limit_filled`, `_entry_filled`, `_taker_mi`). Canlı döngü yazılmadan önce üç ön koşul var:

| # | Ön koşul | Neden |
|---|---|---|
| Ö1 | `Backtest.run` içindeki dakika gövdesi (`for gi in range(len(grid))` içi) tek bir `step(t, bars)` fonksiyonuna çıkarılır. Backtest bu fonksiyonu ızgarada döngüyle, canlı döngü her kapanan dakikada çağırır. | İki ayrı döngü iki ayrı mantık demektir. |
| Ö2 | Doluş kararı (`_limit_filled`, `_entry_filled`, `_taker_mi`) `ExecutionAdapter` arkasına taşınır. Backtest `PaperAdapter(P1)` ile koşar. | Backtest'in doluş modeli ile paper'ınki aynı nesne olur. |
| Ö3 | `zone_id` ve `ob_id` deterministik olur (`uuid4` → sembol, TF, çapa zamanları ve fiyatlarından `uuid5`). | Şu an her koşuda rastgele. Canlıda yeniden tespit edilen zone'un "zaten bilinen" olduğu anlaşılamaz. Parite testi kimlikle eşleştiremez. |

### Ayrıştıkları yerler — tam liste

Bu tablonun dışında kalan her fark bir hatadır.

| # | Konu | Backtest | Canlı | Parite testinde |
|---|---|---|---|---|
| A1 | Mum kaynağı | Parquet (REST'ten toplanmış) | WS kline + REST uzlaştırma (§2) | Oynatmada Parquet mum mum beslenir → fark yok. Gölge testte (§5 D3) ölçülür. |
| A2 | Feature üretimi | Tüm 30m serisi tek seferde. Görünürlük `watch_from`, `pivot_confirmed_at`, `known_at`, `pierce_at` damgalarıyla sınırlanır. | Her 30m kapanışında büyüyen seri üzerinde yeniden tespit. Yeni kimlikler eklenir. | **Merkez test** (§5 D0). Önek değişmezliği. |
| A3 | Karar zamanlaması | Mum `t` işlenirken mumun tamamı elde | Mum `t`, kapanışı teyit edildikten sonra işlenir. Tüm semboller için dakika bariyeri (§2). | Aynı: kararlar yalnızca kapanmış mumda. |
| A4 | Giriş emrinin konması | `TOUCHED` olan mumda hedef hesaplanır ve **aynı mumda** doluş aranır. | Temas ancak mum kapanınca bilinir. Aynı mumda dolum için emir **önceden** defterde olmalıdır. | **Fark var** → `OPEN-41`. |
| A5 | Nihai stop (`R-RISK-02`) ve breakeven | Mum `low/high` seviyeye değerse **seviyeden** kapanır (+ slippage modeli). | Stop borsada yok, bot içinde. Kapanmış mumda görülürse piyasa emri ≤ 60 sn geç gider. | **Fark var** → `OPEN-42`. |
| A6 | İşaret fiyatı (equity, `R-RISK-05` likidasyon mesafesi) | 1m kapanışı | Borsanın `markPrice`'ı ve gerçek likidasyon fiyatı | Paper, pariteyi korumak için 1m kapanışı kullanır, `markPrice`'ı yanına loglar → `OPEN-43`. |
| A7 | Funding | 8 saatlik takvimde maliyet modeli | Paper: aynı model. Live: borsanın gerçek funding kaydı. | Paper'da fark yok. |
| A8 | Komisyon ve slippage | `costs.py` modeli | Paper: aynı model. Live: doluş yanıtındaki gerçek ücret ve fiyat. | Paper'da fark yok. |
| A9 | Koşu sonu | Açık pozisyon `RUN_END` ile kapatılır | Koşu sonu yok | Oynatmada `RUN_END` satırları karşılaştırma dışı. |
| A10 | Veri penceresi | `train_frac` kesimi (`loader.py`) | Kesim yok | Oynatma, kesilmemiş Parquet ile yapılır. |
| A11 | Borsa parametreleri (`tickSize`, `stepSize`, ücret) | Önbellek | API'den çekilip önbelleklenir (CLAUDE.md #5) | Oynatmada aynı önbellek. |
| A12 | Şüpheli mum (`ARCHITECTURE.md` §3.1) | Şu an uygulanmıyor (`src/`'da `suspect` yok) | Canlıda **bilinemez**: tanım sonraki N mumu istiyor | → `OPEN-44`. |

---

## 2. Veri akışı

### Kaynaklar

| Akış | Kanal | Kullanan |
|---|---|---|
| 1m kline | WS (sembol başına) | `step` — durum geçişleri, doluş, risk |
| 30m kline | REST, her 30m kapanışından sonra | Feature tespiti (A2). Borsanın 30m'i kullanılır, 1m'den türetilmez; backtest de öyle. |
| İşlem akışı | WS `trade` | Yalnızca `PaperAdapter` doluş kaydı (§4). Karar girdisi değil. |
| Defter | WS derinlik, yalnızca açık simüle emri olan semboller | Yalnızca `PaperAdapter` doluş kaydı |
| Uzlaştırma | REST `klines`, periyodik | Mum doğrulama |

WS uç noktası, sıkıştırma, ping/pong ve kline'da "kapandı" bayrağının olup olmadığı BingX
belgesinden ve deneme bağlantısıyla doğrulanacak → `OPEN-45`.

### Kapanış ve dakika bariyeri

Backtest bir dakikayı tüm semboller için birlikte işler. Portföy düzeyindeki kararlar
(`R-RISK-01` tavanı, equity, `R-RISK-03` günlük kayıp) sembol sırasına bağlıdır. Bu yüzden
canlıda:

1. Mum `m`, sembol için kapanmış sayılır: kapanış bayrağı geldiğinde ya da `m+1`'in ilk
   güncellemesi geldiğinde (`OPEN-45`'e bağlı).
2. Dakika `m`, **tüm** semboller kapanınca işlenir. Semboller backtest'teki sırayla işlenir.
3. Bariyer süresi dolmadan bir sembol gelmezse o sembol için REST'ten `m` istenir.

### Tespit ve `R-KILL-01` bağlantısı

| Durum | Tespit | Eylem |
|---|---|---|
| **Gecikmiş mum** | Bariyer süresi `B` dolduğunda sembolün `m` mumu yok | REST'ten çek. Gelirse devam, `late_bar` sayacı artar. Gelmezse → eksik. |
| **Eksik mum** | Dakika dizisinde atlama (`m-1`'den sonra `m+1`) ya da REST'te de yok | REST'ten doldur. Borsada da yoksa (işlemsiz dakika) → `OPEN-46`. Doldurulamazsa → **`R-KILL-01`**. |
| **Bağlantı kopması** | `P` saniye boyunca mesaj yok ya da ping yanıtsız | Yeniden bağlan. Arada kalan dakikalar REST'ten alınır ve **sırayla** `step`'ten geçer (§3 "yetişme"). Kopma süresi eşiği aşarsa → **`R-KILL-01`**. |
| **WS ≠ REST** | Periyodik uzlaştırmada aynı dakikanın OHLCV'si farklı | → **`R-KILL-01`**. Eşik (tam eşitlik mi, tolerans mı) → `OPEN-47`. |
| **Yapısal bozukluk** | `low ≤ open,close ≤ high`, mükerrer damga, UTC dışı (§3.1 "her bulgu hata") | → **`R-KILL-01`** |
| **İşlem akışında boşluk** | `fillId` atlaması (`trades_logger` ile aynı yöntem) | Kill **değil**: karar girdisi değil. O aralıktaki doluş kayıtları `incomplete` işaretlenir. |

`B`, `P` ve kopma süresi eşiği spec'te tanımlı değil → `OPEN-48`. `R-KILL-01`
tetiklendiğinde botun ne yaptığı (yeni girişi durdurmak mı, emir iptali mi, pozisyon
kapatmak mı) spec'te tanımlı değil → `OPEN-49`. Bu, `R-KILL-02..06` için de geçerlidir.

---

## 3. Durum ve yeniden başlatma

### SQLite'ta ne tutulur

`ARCHITECTURE.md` §4.2'deki tablolar (`zones`, `positions`, `orders`, `daily_reference`,
`kill_events`) yetmez. Motor bugün şunları da bellekte tutuyor ve hepsi kurtarılmalı:

| Ek durum | Motordaki karşılığı |
|---|---|
| Bekleyen giriş (hedef, bant, pencere sayacı, gösterge bayrakları) | `self.pending` |
| Pozisyon bayrakları | `tp1_done`, `reduce_armed`, `last_funding_at`, `min_liq_dist`, excursion |
| OB kullanım durumu | `ob_alive` (ekleme için kullanılan OB düşer) |
| Gün referansı ve blok | `_day_start_equity`, `_day_blocked` |
| İşlenen son dakika | **imleç** — yeniden başlatmanın başlangıç noktası |
| Sayaçlar | `counters` (zorunlu sayaçlar, spec §8) |

**Yazma kuralı:** bir dakikanın tüm değişiklikleri ve imleç **tek transaction**'da yazılır.
Çökme ya dakikanın tamamını ya da hiçbirini kaybettirir. Yarım dakika olmaz.

### Emir önce yazılır, sonra gönderilir

1. `orders` tablosuna `INTENT` durumunda satır yazılır. `client_order_id` deterministiktir:
   `zone_id`, olay türü ve sıra numarasından.
2. Emir gönderilir.
3. Teyit gelince `ACKED`, doluşla `FILLED`.

Teyitsiz kalan emir **`R-KILL-02`**'dir (CLAUDE.md #8). Yeniden başlatmada `INTENT` ya da
`SENT` durumundaki her emir `client_order_id` ile borsaya sorulur. Aynı kimlikle ikinci
gönderimde BingX'in ne yaptığı (red mi, mevcut emri mi döndürür) doğrulanacak → `OPEN-50`.

### Yeniden başlatma sırası

1. SQLite'tan durum ve imleç yüklenir.
2. Borsa parametreleri yenilenir.
3. **Uzlaştırma (`R-KILL-03`).** Borsadaki açık pozisyonlar ve açık emirler (bizim
   `client_order_id` önekimizle) SQLite ile karşılaştırılır. Paper'da borsa tarafı yoktur.
   Bu adım yalnızca `LiveAdapter`'da anlamlıdır. **Herhangi bir fark → `R-KILL-03`.**
   Otomatik düzeltme yapılmaz. Hangi tarafın doğru olduğuna insan karar verir.
4. **Yetişme.** İmleçten şimdiye kadarki 30m ve 1m mumları REST'ten çekilir ve sırayla
   `step`'ten geçer. Paper'da bu, kesintisiz koşuyla aynı sonucu verir: P1 mumla çalışır.
   Live'da geçmiş bir mumda emir verilemez. Yetişme sırasında doğan girişlerin ne olacağı
   tanımsız → `OPEN-51`.
5. WS'e bağlanılır, bariyer başlar.

**Süreç kapalıyken stop yoktur.** `R-RISK-02` stopu borsaya göndermiyor. Paper'da bu
yalnızca bir kayıttır. Live'da süreç kapalı kaldığı her dakika pozisyon stopsuzdur →
`OPEN-52`.

---

## 4. PaperAdapter

### Doluş modeli

Backtest'teki **P1**'in aynısı. Nesne de aynıdır (Ö2): `entry_fill="tick1"`. Limit emir,
fiyat seviyeyi 1 tick geçmeden dolmaz. Seviyeye değip dönen mum doldurmaz. Paper'ın ürettiği
işlemler bu yüzden **tanım gereği** backtest'inkilerdir. Paper doluş sorusunu çözmez
(`OPEN-37`). Görevi o soruyu çözecek veriyi toplamaktır.

### Her emir için kayıt

`logs/fills/{yyyy-mm-dd}.jsonl`. Emir başına bir satır, emir kapandığında (doldu, iptal,
zone bitti) yazılır. Yalnızca dolanlar değil: **seviyeye değip P1'e göre dolmayan** emirler
de yazılır. Karşılaştırma iki yönlü olmalı.

| Alan | Kaynak | Amaç |
|---|---|---|
| `client_order_id`, `zone_id`, tür (giriş/TP1/nihai TP/ekleme/küçültme), taraf, seviye, miktar | motor | eşleştirme |
| `placed_at`, emir anındaki defter (ilk 20 kademe) | WS derinlik | **önümüzdeki kuyruk**: seviyedeki miktar |
| Ömrü boyunca seviyede ve ötesinde basılan her işlem (fiyat, miktar, agresör, `fillId`) | WS işlem | seviyede işlem gören hacim |
| `p1_filled_at` ya da `null` | motor | simüle karar |
| Alternatif hükümler: `touch`, `p2`, `queue` (seviyedeki kümülatif hacim ≥ önümüzdeki kuyruk + miktar) | kayıttan hesap | P1'in doğru, iyimser ya da kötümser olduğu |
| Doluş anındaki defter | WS derinlik | slippage (`OPEN-32`) |
| `markPrice` | REST | A6 |
| `incomplete` | işlem akışı boşluğu | güvenilmez satırı ayırmak |

Bot içi stop ve breakeven tetiklendiğinde de satır yazılır. Tetik anındaki defterde bizim
miktarın ortalama doluş fiyatı hesaplanır. Böylece stopun "seviyeden" kapanma varsayımı
(A5) ölçülür.

**Bu veriyi değerlendirmek bir spec kararı değildir.** Kayıt yalnızca biriktirir. P1'in
değiştirilmesi yeni spec sürümü olarak yapılır (ARCHITECTURE §6).

---

## 5. Parite testi — tasarımın merkezi

**İddia:** canlı döngü, geçmiş veriyle mum mum "canlıymış gibi" beslendiğinde backtest
motoruyla **birebir aynı** işlemleri ve karar logunu üretir. Tolerans yoktur. Canlı ile
backtest arasındaki her fark ya bir look-ahead ya da bir mantık hatasıdır. Tek istisna
§1'deki A-listesidir. A-listesi büyüdükçe parite testi zayıflar. Bu yüzden listeye ekleme
kullanıcı onayı ister.

### D0 — Önek değişmezliği (feature)

Her feature fonksiyonu (`detect_zones`, `detect_order_blocks`, `detect_fvgs`, `htf_bias`,
`pierce_time`) için:

> Rastgele seçilen her kesim `k` için, `f(seri[:k])` çıktısı, `f(seri)` çıktısının
> `known_at ≤ t_k` olan kısmına **alan alan eşittir**.

Bu CLAUDE.md #3'ün ("bu değer T anında biliniyor muydu") makinece sınanmış hâlidir.
Tespit edilen bir leg'in çapası sonradan uzuyorsa, önekte başka çapalı bir zone görünür ve
test kırılır. Bu tam olarak aranan hata sınıfıdır. Ö3 olmadan (deterministik kimlik) bu test
yazılamaz.

Canlıda tespit tüm geçmişte değil **kayan bir pencerede** koşarsa (maliyet için), aynı test
pencere başlangıcı için de yapılır. Pencere uzunluğu → `OPEN-53`.

### D1 — Oynatma

`ReplayFeed`, Parquet'teki 1m ve 30m mumları, canlıdaki sırayla ve 30m'i yalnızca kapanışta
vererek `LiveLoop`'a besler (`PaperAdapter(P1)`, boş SQLite). Aynı veride `Backtest.run`
koşulur. Karşılaştırılan:

- `trades`: her alan, `Decimal` eşitliği
- Karar logu: `decision_id` ve `code_version` dışında satır satır
- Zorunlu sayaçlar

Ö1 ve Ö2'den sonra iki taraf aynı `step`'i ve aynı adaptörü kullanır. D1'in yakaladığı fark
**yalnızca** feature'ların artımlı üretimi (A2) ve besleme sırasıdır (A3). Bu kasıtlıdır:
farkın kaynağı daralır.

### D2 — Çökme oynatması

D1'in aynısı, ama süreç rastgele dakikalarda öldürülür ve SQLite'tan yeniden başlatılır
(§3). Sonuç D1 ile birebir aynı olmalıdır. Yeniden başlatma yolunun tek testi budur.

### D3 — Gölge

Paper sunucuda N gün koştuktan sonra aynı dönemin verisi `pull_book` ile çekilir ve backtest
o dönemde koşulur. D1 geçtiği için buradaki farklar veri farkıdır (WS ↔ REST, gecikmiş mum,
yetişme). Her fark tek tek açıklanır ve raporlanır. Açıklanamayan fark bir hatadır.

### Ne zaman koşar

D0 ve D1 her değişiklikte test suite'inde koşar (sabit bir sembol, sabit bir ay, ağsız).
D2 aynı veriyle, daha seyrek. D3 paper aşamasında haftalık.

---

## 6. Karar logu

Şema `ARCHITECTURE.md` §4.1. Backtest ve canlı **aynı yazıcıyı** kullanır. Canlı
`logs/decisions/{yyyy-mm-dd}.jsonl`'e, backtest `logs/decisions/backtest/{run_id}/`'ye yazar.
D1 bu iki çıktıyı karşılaştırır.

- `decision_id`: şema "uuid" diyor. Parite için deterministik `uuid5` (sembol, zone,
  dakika, olay) önerilir. Hâlâ bir uuid'dir, şema değişmez.
- `inputs`: kararın alındığı dakikadaki feature anlık görüntüsü. Canlıda buna `markPrice`
  ve veri durumu (`late_bar`, yetişme modunda mı) eklenir.
- `spec_version`, `code_version`: zorunlu.

Şemanın `event` listesinde giriş reddi, simüle doluş, uzlaştırma ve veri olayı yok. Motor
bugün giriş reddini yalnızca sayaçta tutuyor (`no_indicator_skipped`, `leg_skipped`).
Listenin genişletilmesi ve `NO_ACTION`'ın hangi dakikalarda yazılacağı (her sembol her dakika
= günde ~28.800 satır) → `OPEN-54`.

---

## 7. Nerede çalışır

| Aşama | Makine | Anahtar | Not |
|---|---|---|---|
| Paper | Minecraft sunucusu (`janitor@179.61.147.81`) | **Yok.** Yalnızca herkese açık uçlar. | `janitor` kullanıcı servisi (`janitor-paper`), mevcut kayıtçılarla aynı yapı (`docs/SERVER.md`). Minecraft'a ve sisteme dokunulmaz. |
| Live | Xeon | Alt hesap, sıfır bakiye | Anahtar yalnızca ortam değişkeni (CLAUDE.md #10), IP kısıtlı. |

Paper'ın bellek bütçesi ölçülmedi. Backtest 20 sembolde ~740 MB tutuyor. Sunucuda Minecraft
ve iki kayıtçı zaten çalışıyor → `OPEN-55`.

**Sıfır bakiye ve LiveAdapter çelişiyor.** Sıfır bakiyeli hesapta her emir "yetersiz
marjin" ile reddedilir. Bu aşama yalnızca kimlik doğrulama, red yolu, `R-KILL-02`/`03` ve
uzlaştırma kodunu sınayabilir. Doluş üretemez → `OPEN-56`. Xeon'un kendisi (adres, işletim
sistemi, başka ne çalıştığı) bu repoda tanımlı değil → `OPEN-57`.

Demo (VST) bu tabloda yok: ayrı bir piyasa (`docs/measurements/vst.md`).

---

## 8. Kapsam dışı

- Mum içi karar. Tek istisna aday `OPEN-42`.
- Birden fazla süreç ya da sembol başına süreç.
- Arayüz (CLAUDE.md "yapılmayacaklar").

---

## 9. Açık sorular

| ID | Soru | Neden karar gerekiyor |
|---|---|---|
| `OPEN-41` | Giriş emri ne zaman borsaya konur? Backtest temas mumunda hedefi hesaplayıp aynı mumda dolduruyor (A4). | Canlıda temas mum kapanınca bilinir. Seçenekler: zone izlemeye girince emri koymak ve her kapanan mumda hedefi yeniden fiyatlamak (backtest'in de buna göre değişmesi gerekir), ya da temas sonrası koymak (backtest'ten farklı bir strateji). İkisi de spec değişikliği. |
| `OPEN-42` | Nihai stop ve breakeven kapanmış mumda mı, işlem akışında anlık mı izlenir (A5)? | Kapanmış mum pariteyi korur ama ≤ 60 sn gecikir. Anlık izleme tek mum içi mantık olur ve backtest'te karşılığı yok. |
| `OPEN-43` | Live'da risk hesabı (`R-RISK-05`) 1m kapanışından mı, borsanın `markPrice`'ından mı? | Likidasyonu borsa `markPrice` ile yapar. Backtest kapanışla ölçüldü. |
| `OPEN-44` | Şüpheli mum karantinası canlıda nasıl uygulanır (A12)? | §3.1 tanımı sonraki N mumu istiyor. Karar anında kullanılırsa look-ahead olur. Kullanılmazsa backtest ile canlı aynı veriyi farklı görür. |
| `OPEN-45` | BingX swap WS: uç noktası, sıkıştırma, ping/pong, kline "kapandı" bayrağı var mı? | Kapanış tespiti (§2) buna bağlı. Belge ve deneme bağlantısıyla doğrulanacak. |
| `OPEN-46` | İşlemsiz dakika: borsa mum döndürmüyorsa eksik mum mu, sıfır hacimli mum mu? | Backtest verisinde bu dakikalar nasıl temsil ediliyor, doğrulanmalı. Canlı aynısını yapmalı. |
| `OPEN-47` | WS ↔ REST mum uzlaştırmasında tam eşitlik mi, tolerans mı? | `R-KILL-01` eşiği. |
| `OPEN-48` | Bariyer süresi `B`, sessizlik süresi `P`, kopma süresi eşiği | Spec'te `R-KILL-01`'in sayısal tanımı yok. |
| `OPEN-49` | `R-KILL-01..06` tetiklenince ne olur: yeni giriş durur mu, emirler iptal mi, pozisyon kapanır mı? Hangisi kendiliğinden, hangisi insanla kalkar? | Spec §6 yalnızca adları listeliyor. Ayrıca §6 "tüm kill switch'ler açık/kapalı switch" diyor. `R-KILL-04` (`R-RISK-05`) CLAUDE.md #2'ye göre kapatılamaz. Çelişki. |
| `OPEN-50` | Aynı `client_order_id` ile ikinci gönderimde BingX ne yapar? | İdempotentlik (CLAUDE.md #6) buna dayanıyor. Borsa yanıtı fixture olarak saklanacak. |
| `OPEN-51` | Live'da yetişme sırasında (kesinti sonrası) doğan giriş/çıkış sinyali ne olur? | Geçmiş mumda emir verilemez. Çıkış sinyali (stop) kaçırılmışsa şimdiki fiyattan mı kapatılır? |
| `OPEN-52` | Süreç kapalıyken live pozisyon stopsuz (`R-RISK-02`). Borsaya felaket stopu eklensin mi? | Spec değişikliği. `R-RISK-02` gerekçesiyle çelişir. |
| `OPEN-53` | Canlı tespit tüm geçmişte mi, kayan pencerede mi? Pencereyse uzunluğu? | Maliyet ↔ önek değişmezliği (D0). Tespit süresi ölçülmedi. |
| `OPEN-54` | Karar logu `event` listesinin genişletilmesi (giriş reddi, doluş, uzlaştırma, veri) ve `NO_ACTION` sıklığı | Şema ARCHITECTURE'da. Değişiklik oraya yazılmalı. |
| `OPEN-55` | Paper'ın Minecraft sunucusundaki bellek/CPU bütçesi | Ölçülmeden kurulum yapılmaz. |
| `OPEN-56` | Sıfır bakiyeli alt hesapta LiveAdapter aşamasının amacı ne? Doluş ölçülecekse bakiye ve kayıp tavanı gerekir (`OPEN-38`). | Gerçek para kapsam dışı (CLAUDE.md). |
| `OPEN-57` | Xeon makinesi: adres, işletim sistemi, erişim, başka ne çalışıyor | Repoda tanımı yok. |
