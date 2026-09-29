# LIVE — canlı döngü tasarımı

| | |
|---|---|
| **Durum** | 2026-09-29. §9 kapandı (spec v0.5). Ö1–Ö3, `OPEN-41` ve 30m look-ahead düzeltmesi kodda. D0 ve D1 geçiyor (`tests/test_parity.py`, `tests/test_parity_d1.py`). WS/REST, SQLite durum ve PaperAdapter kodu yok. |
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
| Ö2 | Doluş kararı (`_limit_filled`, `_entry_filled`, `_taker_mi`) `ExecutionAdapter` arkasına taşınır. Backtest'in bugünkü davranışı `SimAdapter`'dır. | Backtest'in doluş modeli ile paper'ınki aynı nesne olur: `PaperAdapter` = `SimAdapter` + kayıt. |
| Ö3 | `zone_id` ve `ob_id` deterministik olur (`uuid4` → sembol, TF, çapa zamanları ve fiyatlarından `uuid5`). | Şu an her koşuda rastgele. Canlıda yeniden tespit edilen zone'un "zaten bilinen" olduğu anlaşılamaz. Parite testi kimlikle eşleştiremez. |

### Ayrıştıkları yerler — tam liste

Bu tablonun dışında kalan her fark bir hatadır.

| # | Konu | Backtest | Canlı | Parite testinde |
|---|---|---|---|---|
| A1 | Mum kaynağı | Parquet (REST'ten toplanmış) | WS kline + REST uzlaştırma (§2) | Oynatmada Parquet mum mum beslenir → fark yok. Gölge testte (§5 D3) ölçülür. |
| A2 | Feature üretimi | Tüm 30m serisi tek seferde. Görünürlük `watch_from`, `pivot_confirmed_at`, `known_at`, `pierce_at` damgalarıyla sınırlanır. | Her 30m kapanışında büyüyen seri üzerinde yeniden tespit. Yeni kimlikler eklenir. | **Merkez test** (§5 D0). Önek değişmezliği. |
| A3 | Karar zamanlaması | Mum `t` işlenirken mumun tamamı elde | Mum `t`, kapanışı teyit edildikten sonra işlenir. Tüm semboller için dakika bariyeri (§2). | Aynı: kararlar yalnızca kapanmış mumda. |
| A4 | Giriş emrinin konması | `PRIMED` kapanışında bekleyen limit, her kapanışta yeniden hesap (`R-ENTRY-02`, `OPEN-41`) | Aynı | Fark yok. |
| A5 | Nihai stop (`R-RISK-02`) ve breakeven | Mum `low/high` seviyeye değerse **seviyeden** kapanır (+ slippage modeli). | Stop borsada yok, bot içinde. Kapanmış mumda görülürse piyasa emri ≤ 60 sn geç gider. | Backtest artık tetik mumunun **kapanışından** çıkar (spec `R-RISK-02`). Paper, kapanıştaki defterle gerçek çıkış fiyatını kaydeder (§4). |
| A6 | İşaret fiyatı (equity, `R-RISK-05` likidasyon mesafesi) | 1m kapanışı | Borsanın `markPrice`'ı ve gerçek likidasyon fiyatı | Paper 1m kapanışı kullanır, `markPrice`'ı loglar. Live ikisinden **küçük** mesafeyi kullanır (`OPEN-43`). |
| A7 | Funding | 8 saatlik takvimde maliyet modeli | Paper: aynı model. Live: borsanın gerçek funding kaydı. | Paper'da fark yok. |
| A8 | Komisyon ve slippage | `costs.py` modeli | Paper: aynı model. Live: doluş yanıtındaki gerçek ücret ve fiyat. | Paper'da fark yok. |
| A9 | Koşu sonu | Açık pozisyon `RUN_END` ile kapatılır | Koşu sonu yok | Oynatmada `RUN_END` satırları karşılaştırma dışı. |
| A10 | Veri penceresi | `train_frac` kesimi (`loader.py`) | Kesim yok | Oynatma, kesilmemiş Parquet ile yapılır. |
| A11 | Borsa parametreleri (`tickSize`, `stepSize`, ücret) | Önbellek | API'den çekilip önbelleklenir (CLAUDE.md #5) | Oynatmada aynı önbellek. |
| A12 | Şüpheli mum (`ARCHITECTURE.md` §3.1) | Şu an uygulanmıyor (`src/`'da `suspect` yok) | Canlıda **bilinemez**: tanım sonraki N mumu istiyor | İkisinde de karar girdisi değil; yalnızca sonradan işaretlenir (`OPEN-44`). |

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

`B = 10 sn`, `P = 30 sn`, kopma eşiği `60 sn` (`OPEN-48`). `R-KILL-*` eylemleri spec §6
tablosunda (`OPEN-49`).

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
   Live'da geçmiş bir mumda emir verilemez: yetişmede doğan **giriş** atılır ve loglanır;
   kaçırılmış **çıkış** (stop/TP seviyesi geçilmiş) yetişme biter bitmez piyasa emriyle
   kapatılır (`OPEN-51`).
5. WS'e bağlanılır, bariyer başlar.

**Süreç kapalıyken iç stop yoktur.** Live'da borsadaki felaket stopu korur
(`R-RISK-02`, `OPEN-52`). Paper'da emir gönderilmez, seviyesi kaydedilir.

---

## 4. PaperAdapter

### Doluş modeli

Backtest'teki **P1**'in aynısı. Nesne de aynıdır (Ö2): `PaperAdapter`, `SimAdapter`'ı
(`entry_fill="tick1"`) sarar ve üstüne kayıt ekler. Limit emir,
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

Canlı tespit **tüm geçmişte** koşar (`OPEN-53`): pencere başlangıcı testi gerekmez.

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

**Uygulama (2026-09-29).** `src/live/replay.py`: `kapanis` her 30m kapanışında önekte
yeniden tespit eder, yeni kimlikleri ekler (`Backtest.add_zones`); `oynat` 30m'i yalnızca
kapanışında verir. Veri sentetik ve tohumlu (ağsız, `data/` gerekmez), 20 gün, iki
yapılandırma (F1 ve eklemeli). İşlemler, sayaçlar, equity eğrisi ve bakiye birebir. İlk
koşuda eklemeli yapılandırma **kırıldı**: `pierce_time` veri geçişten hemen sonra bitince
delinme sayıyordu, önekte tam seriden erken. Düzeltildi. Karar logu henüz yazılmıyor
(`OPEN-54`); yazılınca D1'e eklenir. Süre ~2 dk: her kapanışta tüm geçmiş yeniden
tespit ediliyor (`OPEN-53`).

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
`OPEN-54` kapandı: `event` listesine `ENTRY_REJECTED`, `ORDER` (koy/iptal/yenile),
`FILL`, `RECONCILE`, `DATA` eklenir. `NO_ACTION` yalnızca bir kararın **değerlendirildiği**
dakikada yazılır: sembolde `PRIMED`/`TOUCHED` zone ya da açık pozisyon varsa. Boşta
dakika yazılmaz. Şema değişikliği `ARCHITECTURE.md` §4.1'e log kodu yazılınca işlenir.

---

## 7. Nerede çalışır

| Aşama | Makine | Anahtar | Not |
|---|---|---|---|
| Paper | Minecraft sunucusu (`janitor@179.61.147.81`) | **Yok.** Yalnızca herkese açık uçlar. | `janitor` kullanıcı servisi (`janitor-paper`), mevcut kayıtçılarla aynı yapı (`docs/SERVER.md`). Minecraft'a ve sisteme dokunulmaz. |
| Live | Xeon | Alt hesap, sıfır bakiye | Anahtar yalnızca ortam değişkeni (CLAUDE.md #10), IP kısıtlı. |

Paper'ın bellek bütçesi ölçülmedi. Backtest 20 sembolde ~740 MB tutuyor. Sunucuda Minecraft
ve iki kayıtçı zaten çalışıyor. `OPEN-55`: kurulumdan önce yerelde ölçülür; servis
`MemoryMax` ile sınırlanır.

**API anahtarı `OPEN-38`'e kadar gerekmiyor (`OPEN-56`).** Sıfır bakiyeli LiveAdapter
aşaması yapılmaz. Live satırı ve Xeon (`OPEN-57`) `OPEN-38` açılınca tanımlanır.

Demo (VST) bu tabloda yok: ayrı bir piyasa (`docs/measurements/vst.md`).

---

## 8. Kapsam dışı

- Mum içi karar. Tek istisna aday `OPEN-42`.
- Birden fazla süreç ya da sembol başına süreç.
- Arayüz (CLAUDE.md "yapılmayacaklar").

---

## 9. Kararlar (eski açık sorular)

Hepsi 2026-09-29'da kapandı. `OPEN-41`, `OPEN-49`, `OPEN-52`, `OPEN-56` kullanıcı kararı;
diğerleri en muhafazakâr varsayılan.

| ID | Soru | Karar |
|---|---|---|
| `OPEN-41` | Giriş emri ne zaman konur (A4) | `PRIMED` mumunun kapanışında, o anda bilinen bilgiyle bekleyen limit. Her kapanışta yeniden hesap; değiştiyse iptal + yenile. Zone'u `1` çapasıyla öldüren mum emri geçtiyse dolum + aynı mumda stop. Backtest birebir uygular (spec `R-ENTRY-02`). |
| `OPEN-42` | Stop/breakeven kapanmış mumda mı, anlık mı (A5) | Kapanmış 1m mumda; tetikte hemen piyasa emri. Mum içi mantık yok. Gecikmenin maliyeti paper kaydında ölçülür. |
| `OPEN-43` | Live `R-RISK-05`: kapanış mı `markPrice` mı | İkisiyle de hesaplanır, **küçük** mesafe kullanılır. Paper kapanışla (parite), `markPrice` loglanır. |
| `OPEN-44` | Şüpheli mum karantinası canlıda (A12) | Karar girdisi değil (ikisinde de). Yalnızca sonradan işaretlenir; yapısal bozukluk `R-KILL-01`. |
| `OPEN-45` | BingX WS ayrıntıları | Kapanış bayrağına güvenilmez: `m`, `m+1`'in ilk mesajı gelince kapanmış sayılır, REST ile uzlaştırılır (`OPEN-47`). Uç nokta/ping ayrıntısı doğrulama işi, karar değil. |
| `OPEN-46` | İşlemsiz dakika | Sentetik mum üretilmez; sembol o dakikada `step`'e girmez — backtest ızgarasıyla aynı. REST de yoksa kill değil, `DATA` olayı loglanır. |
| `OPEN-47` | WS ↔ REST uzlaştırma eşiği | Tam eşitlik. Her fark `R-KILL-01`. |
| `OPEN-48` | `B`, `P`, kopma eşiği | `B = 10 sn`, `P = 30 sn`, kopma `60 sn` → `R-KILL-01`. |
| `OPEN-49` | Kill eylemleri | Spec §6 tablosu. `R-RISK-05`, `R-KILL-02`, `R-KILL-03` kapatılamaz. `R-KILL-01`: yeni giriş durur, bekleyen girişler iptal, pozisyonlar felaket stopunda. `R-KILL-02/03`: tüm faaliyet durur, insan. |
| `OPEN-50` | Aynı `client_order_id` ile ikinci gönderim | Aynı kimlik körlemesine yeniden gönderilmez: önce kimlikle sorgulanır. Sorgu cevapsızsa `R-KILL-02`. BingX'in davranışı fixture ile belgelenir. |
| `OPEN-51` | Yetişmede doğan sinyaller | Giriş atılır ve loglanır. Kaçırılmış çıkış yetişme sonunda piyasa emriyle kapanır. |
| `OPEN-52` | Felaket stopu | İç stop birincil. Canlıda borsaya `reduceOnly` felaket stopu, `1`'in `FELAKET_MESAFE` (başlangıç 0.10 leg) ötesinde. Paper'da gönderilmez, kaydedilir (spec `R-RISK-02`). |
| `OPEN-53` | Canlı tespit: tüm geçmiş mi, pencere mi | Tüm geçmiş. Maliyet `OPEN-55` ölçümünde görülür. |
| `OPEN-54` | Karar logu olayları, `NO_ACTION` sıklığı | §6: yeni olaylar eklenir; `NO_ACTION` yalnızca kararın değerlendirildiği dakikada. |
| `OPEN-55` | Sunucu bütçesi | Kurulumdan önce yerelde ölçülür; servis `MemoryMax` ile sınırlı. |
| `OPEN-56` | Sıfır bakiyeli LiveAdapter | API anahtarı `OPEN-38`'e kadar gerekmiyor; bu aşama yapılmaz. |
| `OPEN-57` | Xeon | `OPEN-38` açılınca tanımlanır. |
