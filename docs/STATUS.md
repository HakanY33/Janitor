# STATUS

Her oturumun **ilk** okuduğu dosya. Kısa tutulur. Oturum sonunda güncellenir.

**Son güncelleme:** 2026-10-05

---

## Şu an

**Görev:** Sunucu **2026-10-12**'de kapanıyor, yeni sunucu yok (kullanıcı 2026-10-05). Kayıtçılar
PC'de, sunucuyla paralel (`göç/pc`), **2026-10-11 son çekim** (`SERVER.md` "Sunucu kapanışı — PC'ye
geçiş"). Paper kapalı kalır. H1 dilimi 10-01 → 12-31, tek bakış 2027-01-01 (kod kilidi).

**2026-10-05 (3. oturum) — eşleştirme kuralı + #28 + v4 OB arayüzü:**
- **R-ZONE-10 seçeneği `son_supuren`** (kullanıcı kuralı: 0 = 1'den önceki, kendisi de likidite almış
  son karşı swing, pencere yok). `detect.py:ANCHOR0`, `zones_from_swings(..., eslestirme=)`;
  **varsayılan `pencere` değişmedi**. `swing_secim.py --eslestirme --adaylar --out`. v3, ön kayıt
  ölçütleri: B2 25/44, B3 23/44 → eşit, yanlış alarm B2 0/6 → **B2 + `son_supuren`** (`adaylar.md`'de
  kesin metin, v4'te < %28 → geçersiz).
- **#28 (örneklem içi):** B2 + `son_supuren` + v0.8 → **96,91 $** (−%3,1), 761 işlem, kazanma %53,7,
  kriter 3 6/11. **Brüt ilk kez pozitif (+7,86)**, sürtünme 10,94 siliyor.
- **OB impuls şartı:** kaldırılmış hâliyle kalır (kullanıcı) — spec §0.1'e not.
- **v4 arayüzü** (etiketler görülmeden): motor çapası yok; önce OTE / "setup yok", sonra "OB'leri
  göster" (OTE kilitlenir), OB'ler karar anında kapanmış 30m'den v0.8 tanımıyla (`inceleme_v3.ob_listesi`,
  test), her OB doğru/yanlış, kaçırılan OB 30m mumuna tıklanarak (1. mum). Alanlar `ob`, `ob_eksik`,
  `ob_acildi`, `ob_liste`. 30 an değişmedi (doğrulandı). Akış başsız Edge'de denendi (kopya, ayrı
  depolama anahtarı); grafiğe tıklayarak OB ekleme otomasyonla denenmedi. **Testler 491.**

**2026-10-05 (2. oturum) — spec v0.8 + #27 + eşleştirme teşhisi + PC kaydı:**
- **Spec v0.8 (kullanıcı kuralları):** `OPEN-64` OB = 3 mumluk yapı, 1. mumun gövdesi; 3. mum 1. mumla
  temas etmez, 2. mum 1. mumun ucunu aşmaz; **impuls eşiği OB'den çıktı** (tarifte yoktu; yalnızca
  delinmede kaldı). `OPEN-65` FVG tek başına giriş sebebi değil: `R-ENTRY-02` (2) ve kapı yalnızca OB,
  FVG emir fiyatı belirlemez, ilk temasta silinir (`filled_at = mitigated_at`). Kod `ob.py`,
  `fvg.py:on_bar`, `engine.py:_hedef`/`order_for`. 12 test yeni/değişti; D1/paper sentetik verisi 20 gün + tohum 6 (yeni OB'yle 10 günde F1 kapısından işlem geçmiyordu) → bu iki dosya ~13 dk. **Testler 486.** **`measure_ob.py` (a)
  `body_mult` parametresi artık yok** (tarihsel ölçüm betiği; git'ten yeniden üretilir).
- **#27** (`SONUCLAR.md`): B3 + v0.8, 100 USDT → **88,42 $** (−%11,6), 523 işlem, kazanma %51,6,
  kriter 3 4/11. **Brüt negatif** (−4,30) → edge yok; iyileşme işlem sayısından.
- **Eşleştirme teşhisi** `docs/inceleme/v3/eslestirme_teshis.md` (`scripts/eslestirme_teshis.py`,
  açıklayıcı): B3'te 22/44, B2'de 32/44 **yanlış 0** — `1` doğru, `0` daha yeni/daha az uç. Kullanıcının
  0'ı motorun `_anchor_0` penceresinin (1'in aştığı aynı tip swing → 1) solunda (B3 19/22, B2 32/32).
  Aday kural "**son süpüren karşı swing**": örneklem içi çift isabet B2 25/44, B3 23/44 (önce 15).
  `adaylar.md`'ye tarihli not: v4 bu kuralı doğrular (eşik < %28 → geçersiz); **kural kullanıcı
  onayıyla v4 etiketleri açılmadan kesinleşir.**
- **PC kaydı:** `pc_kayit.ps1 -Kok` + `collect.DATA_ROOT` ← `JANITOR_DATA_ROOT`. Kayıtçılar 06:37 UTC'den
  beri `göç/pc/data`'ya (ayrık süreç — **yeniden başlatmada durur**, açılış görevi kullanıcıda).
  Paralel doğrulama **40/40 ortak `id`**, çakışma 0 (`docs/measurements/goc.md`). `.gitignore`'da
  bozuk son satır düzeltildi (`/göç/` artık gerçekten yok sayılıyor).

**2026-10-05 — v3 etiketleri → swing seçimi + ilk koşu + v4:**
- **Etiketler** `docs/inceleme/v3/etiketler.json` (50/50). Setup'lı **44** (b03/b04 "setup yok"
  seçili ama çapalı → setup sayıldı; b25 `bot_dogru` → botun çapaları), setup yok 6.
  Doğrulama (`docs/inceleme/v3/swing_secim.md` §1): 12/88 çapa ±2 mumda yerel uç değil (çoğu
  komşu mum); **karar anına kadar R-ZONE-05'e göre ölmüş 3 yapı:** b04 (`1` 03-27 18:14),
  b27 (`1` 02-26 12:02), r06 (`1` 09-25 18:00). Etiketlerden çıkarılmadı.
- **Swing seçimi** `scripts/swing_secim.py` (ön kayıt `adaylar.md` değişmedi; iki yorum betikte:
  C'nin "kabul edilmiş swing"i = mevcut N=2 tanımı, yoksa liste boş; yanlış alarm = karar 1m
  mumu canlı zone'un bandına temas). Çift isabet /44: A6 7 · A12 9 · B2 10 · **B3 15** · C96 13 ·
  C336 0 · D 10. B3 ve C96 eşit (≤ 2) → yanlış alarm B3 0/6, C96 3/6 → **seçilen B3 (ATR zigzag,
  `k = 3`)**. Oran %34 — çapaların ~2/3'ü hâlâ zamanında bulunamıyor.
- **İlk koşu** (`SONUCLAR.md` #26): B3 + spec v0.7, 100 USDT → **47,94 $** (−%52,1), 1.609 işlem,
  kazanma %47,9, R +0,76 / −0,94, kriter 3 **3/11**. #25'e (27,92 $) göre daha az kötü, edge yok.
  **Spec v0.7'de "yeni OB kuralı" ve "FVG yalnızca yardımcı" yok** → uygulanmadı (soru aşağıda).
- **v4** `docs/inceleme/v4/index.html` (`inceleme_v3 --v4`): 30 rastgele an, tohum 20261005,
  v3'ün 50 anıyla aynı sembolde ±1 gün çakışmaz, ayrı `localStorage` anahtarı. B3'ün oranı burada
  **bir kez** doğrulanır; %17'nin altı (%34'ün yarısı) → seçim geçersiz.
- `scripts/inceleme.py:kos` artık `yol` alıyor ve pakete `baslangic` yazıyor. Testler 483.

**2026-10-02 (2. oturum) — kararlar + etiket ayrıştırma + v3:**
- **Spec v0.7 (kullanıcı kararları, ölçüm yok):** `OPEN-61` kapandı → teyit penceresinde
  `0.50`'ye ulaşılmışsa (ve `0`/`1` ihlal yoksa) zone `PRIMED` başlar (`detect.py:pencerede_050`,
  `Zone.pencere_050`, `Zone.activate`; `store.py` yeni sütun). `OPEN-62` kapandı → canlıda stop
  akıştan + seviyede piyasa emri, borsada yalnızca felaket stopu; `EXIT` satırına `stop_seviye` /
  `stop_fark` (STOP + BREAKEVEN). `OPEN-63` kapandı → mevcut davranış. **Yeni `R-ENTRY-06`**
  sürtünme tabanı: giriş→TP1 mesafesi < 3 × gidiş-dönüş (2 × (taker + slippage), limit kolunda
  2 × maker) → `rejected_surtunme` (`engine.py:_surtunme_yetersiz`, `SURTUNME_KAT`).
  **Hiçbir koşu yeniden yapılmadı** — `SONUCLAR.md` sayıları v0.6 kodundan.
- **`docs/inceleme/v2/capalar.md`** (`scripts/etiket_capalar.py`): 74 çapa elle ayrıştırıldı
  (alan + not + mor öneri), 30m mumu çözüldü: **55 girişten önce, 17 sonra** (kalibrasyon dışı),
  2 zamansız. Setup yok: 11 işlem (#1–#10, #24). Çapa yok: #6, #24.
- **Etiketleme v3** `docs/inceleme/v3/index.html` (`scripts/inceleme_v3.py`): 30 işlem + 20
  rastgele an (tohum 20261002, eğitim dilimi, aynı sembolde işlem giriş−1g…çıkış+1g dışı);
  grafik karar anındaki kapanmış mumlarla biter (açık 30m/4h mumu yok), sonuç gösterilmez;
  lightweight-charts 4.2.0, mumun üst/alt yarısına tıklama → tepe/dip. Edge'de çizim doğrulandı,
  tıklama tarayıcıda denenmedi. Testler 479 + 1.

**2026-10-02 — öncelik tespitin doğruluğu** (kullanıcı 30 işlemi inceledi, `docs/inceleme/notlar.md`:
OTE çapaları 28/30 yanlış, doğru çizilen #25 ve #30 kazandı; OB/FVG tespitinde de hata):
- **Spec v0.6.** `R-RISK-02`: iç stop ve breakeven intrabar, **seviye + slippage** (kullanıcı
  kararı; boşlukta açılıştan). `R-ZONE-05`: pivot teyit penceresinde `0`/`1`'e ulaşılmışsa
  zone kurulmaz. `R-ENTRY-03`: miktar adıma aşağı, asgari miktar/tutar karşılanmazsa red ve sayaç.
  Yeni açıklar `OPEN-61` (teyit penceresinde 0.50/0.70 — işlemlerin %45'i), `OPEN-62` (canlıda
  intrabar stop), `OPEN-63` (asgari altı kısmi TP).
- **Hata avı** `docs/inceleme/v2/hata_avi.md`: #9 gerçek hata (`0` teyit penceresinde kırılmış,
  zone görmüyordu) → `detect.py:izleme_oncesi_oldu`, 96/3.565 işlem. #2, #6 hata değil (30m
  mumunda sıra görünmüyor; #2'nin "0.5→0.7→0.5"'i teyitten önce).
- **`fees.json`** artık `step`/`min_qty`/`min_cost` taşıyor (`scripts/funding.py`); `load_fees`
  bunlar yoksa hata verir. **Sunucuya dağıtımda önce `python -m scripts.funding --fees-only`.**
- **Hesap tabanı 100 USDT** (`SONUCLAR.md` #25): 27,92 $ (−%72,1), 2.987 işlem, kazanma %48,1;
  535 giriş + 247 kısmi TP asgariden reddedildi. 10.000 $ ile aynı kod (#24): −8.305.
- **Etiketleme v2** `docs/inceleme/v2/index.html` (`scripts/inceleme_v2.py`): 4h 14 gün + 30m 300
  mum, doğru 0/1 alanları, `etiketler.json` indirme. **Swing adayları** `docs/inceleme/v2/adaylar.md`
  (ön kayıt: A büyük fraktal, B ATR zigzag, C pencere ucu + süpürme, D 4h çapa; ölçüt çift
  isabet + zamanında). Testler 473 + 11 yeni.

**2026-10-01:**
- **Paper sunucuda durduruldu + `disable`** (14:10 UTC). 11:36 ve 13:06'da `oom-kill`
  (`MemoryMax=700M`). Kural `SERVER.md` §7: sızıntı düzelip 3 tespit döngüsünde bellek düz
  kalana kadar paper hiçbir sunucuda yok; TR-SSD 2'ye ilk kayıtçılar kurulur.
- 15 dk sonra: boş 1.918 MB (önce 1.513), swap 736 → 477 MB; kayıtçılar düz (trades
  ~250 MB rss+swap, spread ~207 MB, 16 saatlik `rss2.log`'da eğim yok). Minecraft java'sı
  13:31'de yeniden başlamış (neden `janitor`'dan görünmüyor).
- **Lokal teşhis** (tracemalloc 1 çerçeve, BTC/ETH/SOL, ısınma + 3 döngü): traced Δ
  +0,03 / +0,02 MB (döngü 2–3) → **referans sızıntısı yok**. Döngü başına geçici tepe
  ~29,5 MB (3 sembol), RSS 196 → 228 → 238 → 236 (Windows). Her döngü tüm geçmişi
  yeniden kuruyor (~207 sn, ısınmayla aynı). Sunucudaki büyüme glibc parçalanmasıyla tutarlı
  (tespit `to_thread` iş parçacığında) — Linux'ta henüz kanıtlanmadı. Artımlı tespit tasarımı
  kullanıcı onayı bekliyor; kod yazılmadı.
- **18:03 UTC kayıtçı teyidi — düz.** `rss2.log` 09-30 21:48 → 10-01 18:02 (1.214 örnek),
  saatlik rss+swap: trades 234–293 MB (tek örnekte 361/380 MB ani tepe, geri döndü), spread
  ~250 → ~195–215 MB (rss swap'a kaydı, toplam artmıyor). Paper durduktan sonra da eğim yok.
  `janitor-paper` inactive + disabled. Bellek: boş 2.657 / kullanılabilir 3.238 MB, **swap
  1.440 MB** (14:25'te 477) — artışın 1,27 GB'ı **Minecraft java**'sında; java **15:37'de
  yeniden başlamış** (bugün ikinci kez, ilki 13:31; paper o sırada kapalıydı). Kayıtçıların
  swap'ı ~147 MB, değişmedi. Minecraft'a dokunulmadı.
- **İki satırlık önlem (kullanıcı):** `scripts/paper.py` `bellek_birak()` — her 30m
  tespitinden sonra `malloc_trim(0)`, yalnızca Linux (test `test_kill_toparlanma.py`);
  birimde `MALLOC_ARENA_MAX=2` (sunucu birimine eklendi, servis kapalı kalır). Testler 464/464.
- **Artımlı tespit ertelendi:** tasarım + D-ART `LIVE.md` §2; şart: H1 kabulü / tarayıcı modu,
  30m döngüsü > 10 dk ya da yeni sunucuda bellek kabulü `KALDI`.
- **`scripts/sizinti.py`** (bellek kabulü, üretim yolu: iş parçacığı + `bellek_birak`).
  **Yeni sunucu sırası** `SERVER.md`: BingX → kayıtçılar + örnekleyici → paralel kayıt
  (ortak `fillId`) → `sizinti.py` 20 sembol 3 döngü → ±10 MB ise paper, değilse artımlı.

- **İnceleme paketi** `docs/inceleme/index.html` (`scripts/inceleme.py`; `--kos` F1 eğitim
  koşusu → `logs/inceleme/f1.pkl`, sonra sayfa): 30 işlem (R'ye göre en kötü 10 kaybeden,
  rastgele 10 kaybeden, rastgele 10 kazanan, tohum 20261001), 30m PNG, not alanı + `notlar.md`.
  Yeniden koşu kayıtlıyla aynı 3.565 giriş/çıkış; net −8.649 (`OPEN-59` funding, Δ −2,46).
  Kazanma %53,2. En kötü 10'un hepsi `STOP`, −2,4…−2,9 R: iç stop tetik mumunun
  kapanışından (R-RISK-02) ve kısa leg (%0,2–3,9) → kayıp stop mesafesinin katları.
  `matplotlib` yalnızca lokal (requirements'ta değil).
- **`docs/SONUCLAR.md`:** test edilen her strateji tek satır (23 satır); güvenilir yalnızca
  F1 dürüst (#22) ve H2 keşif (#23). Her yeni test buraya eklenir.

**2026-09-30 (5. oturum):**
- **H1 kararları (kullanıcı, veri görülmeden, `HYPOTHESES.md` tarihli):** net R'ye funding
  dahil (sembolün gerçek aralığı); kriter 3 "en iyi" = çıkınca kalan ortalamayı en çok düşüren
  grup; **kilit 2027-01-01**. `h1_test.py` + test (12) güncellendi.
- **Sunucu `kalp_ozet`** (10:20 → 12:28, 129 dk, 62 canlı / 67 yetişme): gecikme p95 2,7 sn,
  kill 0, `DATA` 14 (`ws_rest_fark`), 1 işlem, equity 10.004,57. **rss 400 → 626 MB, her 30m
  tespitinde +25–50 MB, düşmüyor; cgroup tepesi 700M = `MemoryMax`.** Bu hızla ~1–2 saatte
  OOM. Karar gerekiyor: `MemoryMax` artışı (makinede ~1,2 GB boş) ya da sızıntı araştırması.
- **OPEN-59 sunucuda:** kod (4 dosya, sha eşit) → `janitor-funding.service` (20/20, `funding_h`
  yazıldı; HYPE/JUP/ORDI 4h) → `restart janitor-paper` (12:34, durumdan geri yüklendi, imleç 12:28).
  Kayıtçılara dokunulmadı. 24 saatlik ölçüm bu yeniden başlatmayla bölündü.
- **`scripts/birlestir.py`** + `tests/test_birlestir.py` (6, sentetik). Göç bölümü TR-SSD 2'ye
  güncellendi; 0. adım API doğrulaması (REST 4 uç + WS el sıkışması, PC'den denendi: 200 / 101).

**2026-09-30 (4. oturum):**
- **Yerel paper durduruldu** (PID 15560, `scripts.bg scripts.paper`, 10:54'ten beri `R-KILL-01`'de).
  Paper yalnızca sunucuda.
- **Spec §6:** kod hatasından doğan `R-KILL-01` kendiliğinden kalkmaz — kullanıcı onayı yazıldı.
- **`OPEN-59` kapandı:** funding anları sembolün borsa aralığıyla (`fundingIntervalHours` →
  `fees.json` `funding_h`); kapsam içinde ölçülen anlar, dışında o aralıkla ızgara. 40'ın 12'si
  4 saatlik. Motor tahsilatı da sembol aralığıyla. Yerel `fees.json` 40 sembolle yenilendi.
  **Sunucuya dağıtımda sıra** `SERVER.md` §6b (önce funding servisi, sonra paper).
- **H1 boşluk kuralı** `HYPOTHESES.md` §5 tarihli: 65 dk pencerede `trades_gap` → dışla, ayrı say.
- **`scripts/h1_test.py`** + `tests/test_h1.py` (11, sentetik): yerleştirilmiş etki KABUL
  (alt sınır +0,27), etkisiz RET (−0,14), boşluk/kapsam/`A_60=0` dışlama, sonuç kuralları,
  olay tespiti `Zone.on_bar` ile 300 rastgele yolda aynı. **Kilit** (5. oturumda 2027-01-01'e
  alındı); `n < 503` → R hesaplanmaz.
- **PC yedek planı** `SERVER.md` + `scripts/pc_kayit.ps1` (kurulmadı).
- Açık sorular 5. oturumda kapandı.

**2026-09-30 (3. oturum):**
- **H1 eşiği 503** (%97,5, güç %80), **sembol seti 40** — ikisi de tarihli, işlem akışına
  bakılmadan. 40 sembolle ~305 emilimli temas/ay varsayımı → 503'e ~1,65 ay.
- **Kayıtçılar 40 sembol** (spread + trades, sunucu 10:19 UTC). 20 sembolde işlem akışı
  ~80 MB/gün, defter ~3 MB/gün; disk 68 GB boş. `pull_book` glob ile 40'ı kapsıyor.
- **`R-KILL-01` toparlanması** (spec §6): REST üstel bekleme ~60 sn; canlıya yetişince 10
  ardışık temiz dakika → `RESUME`. Beklenmeyen kod hatası ve `R-KILL-02/03` insan ister.
  `tests/test_kill_toparlanma.py` (7).
- **Sunucuya kuruldu:** `janitor-paper` (`MemoryMax=700M`, 20 sembol) + `janitor-funding.timer`
  (4 saatte bir, ilk koşu 20/20). Kod `d341574+kirli`. Minecraft'a dokunulmadı.
  Sunucuda ilk tam tespit **2.070 sn** (yerel 1.545); başlangıç 10:20 UTC, sonra REST'ten yetişme.
  Soğuk 20 ilk 35 dk: işlem 2,7 MB (~110 MB/gün kaba, küçük dosya yükü dahil), `trades_gap` 0.
- **Göç planı** (Xeon) `SERVER.md` "Göç planı": önce kurulum, 48 saat örtüşme, ayrı kökte
  çekme + birleştirme, geçiş kapısı. `scripts/birlestir.py` henüz yok.
- `OPEN-59` (4. oturumda kapandı). `OPEN-60`: eski sunucu 48 saatten önce kapanırsa.

**2026-09-30 (2. oturum):**
- **`OPEN-47` kapandı (kullanıcı):** WS yalnızca zamanlama/canlılık, değerler REST'ten; fark
  yalnızca `DATA`, kill değil. Spec §6 + `LIVE.md` §2/§9.
- **`HYPOTHESES.md` → `HYPOTHESES.md`.** H1 güven sınırı %97,5 (iki hipotez); eşik 396
  kaldı (güç ~%70, %80 için 503). Yetersiz örnek: 01-01'de yalnızca `n`; `n < 396` →
  kararsız, dilim bir kez 2027-03-31'e uzar.
- **H2 ön kaydı** (4h unmitige OB, post-only yakın kenar, borsa stopu karşı kenar + 1 tick,
  2R, %3 stop kaybı; gereken n 1.570) → **keşif** (`scripts/h2_kesif.py`, eğitim, sıfır
  ayar): 1.335 işlem, kazanma %27,9, brüt R ort −0,16, net −0,48, brüt −5.727 / net −10.000,
  kriter 3 kaldı. **Brüt negatif → ileriye dönük testten çıkarıldı** (§8.4).
- **Funding:** `scripts/paper.py` eğrileri her 30m kapanışında diskten tazeler, 9 saatten
  bayatsa `DATA funding_bayat`. Sunucuda yazan `janitor-funding.timer` (4 saatte bir,
  `SERVER.md` §6b, kurulmadı). Çalışan yerel süreç eski kodla (yeniden başlatılmadı).
- **Yerel paper'da `R-KILL-01`** 08:58 UTC: REST `NetworkError`, üç deneme (~6 sn) tükendi.
  Kural gereği; o andan beri giriş yok, kalp atışı sürüyor. İlk 2 saat: canlı gecikme p95
  2,5 sn, rss tepe 459 MB, `ws_rest_fark` 26.

**2026-09-30:**
- **Boşluklu stop:** `1` çapası ve breakeven "ulaştı" ile tetiklenir; boşlukta doluş
  açılıştan, temasta kapanıştan. F1 etkisi −0,65 (1m'de nadir).
- **Spec §8 sonuç:** düzeltilmiş damgayla mekanik OTE'de brüt edge yok; ters çevirme de
  karşılamaz; OHLCV üzerinde yeni filtre/parametre araştırması **durduruldu**. Naif tersin
  C kolunda 1,07 çıktığı not edildi (ekleme merdiveni — ölçüm değil).
- **`docs/HYPOTHESES.md`:** birincil hipotez emilim (5 dk agresif karşı hacim ≥ 3×
  60 dk medyanı, bant içi ilerleme ≤ %50). Tek ölçüt: emilimli temaslarda ortalama net R'nin
  tek yönlü %95 alt sınırı > 0. Gereken ≥ 396 emilimli temas (~1.015 temas/ay).
- **Paper döngüsü:** `src/live/paper.py` (`PaperCore`, SQLite `Durum`, `PaperAdapter`,
  karar logu) + `scripts/paper.py` (WS 1m + REST 1m/30m). D2 testi (çökme + geri yükleme)
  geçiyor. Karar logu olayları `ARCHITECTURE.md` §4.1'e işlendi (`OPEN-54`).
- **`OPEN-45` doğrulandı:** WS'te kapanış bayrağı yok. **`OPEN-47` uygulanamıyor** (WS son
  görüntüsü kesin değil) → fark `DATA` olarak yazılıyor, karar bekliyor.
- Bulunan hata: canlı sırada 30m tespiti emir değerlendirmesinden **önce** bitmeli; aksi hâlde
  gösterge önbelleği eski listeyi tutuyordu. `test_paper` yakaladı, düzeltildi.

Önceki durum: 30m look-ahead düzeltildi, `OPEN-41` kodda, D0 ve D1 geçiyor. Kaldıraç zinciri
düzeltilmiş damgayla yeniden ölçüldü (`docs/measurements/damga.md`, açıklayıcı).

**Durum: hiçbir kolda brüt edge yok.** Düzeltilmiş kodla (eğitim dilimi) A −9.998 ·
C −9.936 · D −8.435 · E3 −6.165 · F1 −4.519. Brüt fiyat PnL'i her kolda negatif; kriter 3
her kolda kaldı. Önceki pozitif sonuçlar (F1 +2.376, soğuk küme +4.187, E3 brüt +5.097)
look-ahead'dendi. F1 zaten dondurulmuştu; karar değişmiyor.

**2026-09-29 (3. oturum):**
- **Bilgi anı (CLAUDE.md #3).** Her HTF nesnesi `known_at` = mumun kapanışı taşır (Swing,
  Zone, OB, FVG). `mitigated_at`, `filled_at`, delinme ve 1m zone geçişleri kapanışta
  damgalanır. Denetim tablosu (19 yer) `docs/measurements/damga.md`.
- **İç stop kapanıştan** (`R-RISK-02`, `OPEN-42`): nihai stop ve breakeven tetik mumunun
  kapanışından piyasa emriyle. F1'e etkisi −781.
- **`pierce_time`** artık teyit mumları kapanmadan delinme döndürmüyor (önek-değişmez). D1
  bu farkı ilk koşuda yakaladı.
- **`OPEN-41` kodu.** `Backtest.order_for` (saf: kapanış görüntüsü + o an bilinen
  gösterge), `_kapanis` (gün sınırı + portföy görüntüsü), çapa mumunda dolum + stop,
  boşluklu mum da doldurur. Backtest emri tembel hesaplar (yalnızca fiyat emre ulaşınca);
  sonuç aynı. `window` giriş varyantı silindi (bekleyen emirle tanımsız).
  F1 −4.519 → **−8.646** (+732 giriş): kapıda kalan zone'lar sonradan oluşan OB/FVG ile emir
  alıyor ve kaybettiriyor.
- **Testler:** `tests/test_known_at.py` (değişmez: nesne kendi `known_at`'inde kapanmış
  mumlardan üretilebilmeli; eski damgalarla 144/144 zone kırılıyor) · D0'a delinme eklendi ·
  **D1** `tests/test_parity_d1.py` (sentetik, `src/live/replay.py`, ~2 dk).
- `docs/measurements/` altındaki 17 dosyaya ve spec'e look-ahead uyarısı (commit 3fb2ff4 ve
  öncesi).

**Sunucu:** `janitor-spread-logger` · `janitor-trades-logger` (sürekli) ·
`janitor-earliest.timer` (03:00 UTC) · `janitor-ohlcv30m.timer` (03:30 UTC). Hepsi
`janitor` kullanıcı servisi (`docs/SERVER.md`).

**İlgili dosyalar:** `scripts/damga.py` · `logs/damga.txt` · `docs/measurements/damga.md` ·
`src/live/replay.py` · `tests/test_known_at.py` · `tests/test_parity.py` ·
`tests/test_parity_d1.py` · `logs/f1check/` (F1 parmak izi betiği)

---

## Bildiklerimiz (kısa)

> Aşağıda **"düzeltilmiş"** yazmayan her satır 30m look-ahead hatasını taşır (commit 3fb2ff4
> ve öncesi). Yönleri bile yeniden ölçülmeden kullanılmaz.

| Bulgu | Sonuç |
|---|---|
| **#28 brüt pozitif (örneklem içi)** | B2 + `son_supuren`: +7,86 brüt, net −3,09; kriter 3 6/11. v4 doğrulaması bekliyor |
| **Eşleştirme kaybı `anchor_0`'da** | v3: B3 22/44, B2 32/44 "yanlış 0"; aday "son süpüren karşı swing" örneklem içi 15 → 23–25/44 (v4'te doğrulanacak) |
| **v0.8 OB/FVG kuralları: kayıp küçük, edge yok** | #27 88,42 $, 523 işlem, brüt −4,30; kriter 3 4/11 |
| **Swing B3 seçildi (etiketle, kârla değil)** | çift isabet 15/44 (%34); F1/100 USDT 47,94 $, kriter 3 3/11 — edge yok, kayıp yarıya indi (#25 27,92 $) |
| **Düzeltilmiş: brüt edge yok** | A/C/D/E3/F1 brüt fiyat PnL'i −438 / −5.010 / −4.004 / −1.619 / −488; brüt/sürtünme ≤ −0,05 |
| **Düzeltilmiş: gösterge kapısı kaybı azaltıyor, edge üretmiyor** | D − C net +1.501 (brüt +1.006); F1 − kapısız net +4.301 (brüt +1.331) |
| **Düzeltilmiş: F1 ayrıştırması** | +2.376 → damga −3.738 → iç stop kapanıştan −4.519 → `OPEN-41` −8.646 |
| Düzeltilmiş: kuyruk riski | maks DD D %86,6 → E3 %63,6 → F1 %49,0 (`ADD-REJECT-E` ve ekleme kapatma hâlâ işliyor) |
| Düzeltilmiş: kriter 3 | her kolda kaldı; en iyisi D 4/11 pozitif ay |
| Düzeltilmiş: boşluklu 1m mum | stop artık tetikleniyor, doluş açılıştan (2026-09-30); F1 Δ −0,65 |
| **H2 (4h OB, 2R) brüt negatif** | keşif, eğitim: 1.335 işlem, kazanma %27,9 < %33,3, brüt R 12 ayın 9'unda eksi → ileriye dönük testten çıkarıldı |
| **Mekanik OTE araştırması durduruldu** | spec §8 (2026-09-30). Sıradaki soru order flow, veri görülmeden ön kayıtlı |
| Paper ↔ backtest paritesi | D1 (oynatma ve paper yolu), D2 (çökme) birebir; karar logu motor satırları birebir |
| **VST ≠ gerçek piyasa** | ayrı defter/işlem akışı, DOGE orta fiyat +12 bps, spread 26 bps. Demo doluşu kuyruk ölçümü değil |
| **F1 donduruldu** | olumsuz sonuç kabul edildi 2026-09-27. Doğrulama yalnızca 09-11 sonrası veride |
| Brüt/sürtünme çöküşü paydan | sürtünme 6,9 → 7,0 bps sabit; brüt 10,6 → 1,1 bps. Yarısı isabet (−3 puan), yarısı kazanan küçülmesi (açıklayıcı) |
| Isınma varsayımı önemsiz | kesim öncesi kurulan emir: 3 işlem, −123 |
| İşlem geçmişi yok | BingX yalnızca son 1.000 işlemi veriyor; `fillId` ardışık → boşluk kesin sayılıyor |
| **Kriter 1 KALDI** | ayrılmış dilimde net −1.287 / −851, brüt/sürtünme 0,16 / 0,35, 7/20 kazanan |
| Risk katmanı ayrılmış dilimde tuttu | likidasyon 0, equity ≥ %50, DD ≤ 1,5× eğitim |
| **F1 soğuk kümede ayakta** | 21–43. sıra: net +4.187, brüt/sürtünme 1,92, 15/20 |
| **Yeni kriter 2 iki kümede geçiyor** | orijinal +157 (kıl payı) · soğuk +1.021; eski ×1.5: −206 / +1.443 |
| Yarılar kümeler arasında zıt | orijinalde kâr H1'de, soğukta H2'de — rejim bağımlılığı |
| **30m penceresi kayıyor** | günde 1 gün, sabit 30.239 mum; 1m sabit |
| Post-only sorusu OHLCV ile çözülemez | Kuyruk konumu → `OPEN-38` gerçek doluş ölçümü (kapsam kararı bekliyor) |
| **Post-only kuyruk konumuna bağlı** | 1 tick +2.376 · 2 tick +1.574 · geri dönen mum dolmazsa −1.744 (taker giriş −902) |
| Kaçan giriş pahalı | ~−35 / kaçan vs −1,45 / taker giriş. Dönüş mumu en iyi giriş |
| **F1 maker doluşa bağlı** | %48,5 taker'a düşmede başabaş; slippage ×3'te hâlâ +862 |
| Girişin taker'a düşmesi en pahalı | tek başına net −902; TP'ler pozitif bırakıyor |
| Emir mum hacmine göre büyük | dolumların %30'unda emir > 1m hacmin ¼'ü (vekil) |
| **F1 slippage ×3'te artıda** | net +862, brüt/sürtünme 1,16; başabaş ~8,3 bps |
| ×1.5'i çökerten komisyon | slippage tek başına ×3 bile pozitif; asıl risk maker doluşu varsayımı |
| Defter verisi yok | BTC/ETH × 2 dakika; `OPEN-32` (a)–(c) bekliyor |
| **Ekleme kapalı (F1) net pozitif** | net −134 → **+2.376**, brüt/sürtünme 0,98 → **1,54**, maks DD %23,7 → %11,9, iki yarıda da artı |
| **F1 kriter 2'yi geçmedi** | maliyet ×1.5 → net **−206**, brüt/sürtünme 0,97, kazanan 15 → 12/20 |
| Leg eşiği (F2) hacim kesiyor | işlem −%37, brüt −%24; H2 −772 → −299, işaret dönmüyor |
| `OPEN-35` kapandı | breakeven ücret dahil, varsayılan |
| **Komisyon kaybedende** | İşlemin %33,9'u stop, komisyonun **%51,5'i** onlarda. Stop 6,8 bps / nihai TP 4,0 bps |
| Kâr eden sonuç komisyon-negatif değil | nihai TP +136,5 bps/işlem, komisyonun %13,3'ü. Sorun kazananın ücreti değil |
| **`R-ZONE-08`: dayanıklı aday yok** | Leg büyüklüğü bir sembol farkla kaçırdı (13/20 → 17/20); OB ölçülemedi (akışın %6'sı) |
| Leg etkisi sürtünmedir | Komisyon bps leg'den bağımsız (5,5-5,7); riske göre +31 bps → **+0,04 R** |
| `touch_count` bu kuralla ölü | İşlemlerin %95'i tek temas, işaret de döndü (+24,0 → −9,2) |
| 4h yön uyumu (swing, SMA değil) | +5,9 → +7,0 bps, işaret sabit ama 10-12/20 sembol. Yön `NONE` grubu en iyisi |
| **`ADD-REJECT-E` hesabı kurtarıyor** | brüt **−264 → +5.097** · maks DD %63,6 → **%24,1** · iflas %23,6 → **%0** |
| `L` net PnL'den seçilemez | −176 / −727 / −186 — monoton değil. Seçim maks drawdown'dan: `L` = **%3** |
| **Sürtünme edge'i tam yiyor** | brüt/sürtünme = **0,97**. Net −%1,8 — başabaşın hemen altı |
| **Kriter 2 geçilmedi** | maliyet ×1.5 → net −176 → **−2.361**, kazanan sembol 13/20 → 8/20 |
| Kural giriş tarafında bağlamıyor | 1.103 ekleme-bar'ı reddedildi, yalnızca **2 giriş** |
| En kötü işlem 14 kat küçüldü | E0'da −4.766 (24,0× · net kaybın %91'i) → E3'te −331 |
| **Kayıp tek sembolde: ORDI** | −5.539 = net kaybın **%106'sı**; ORDI'siz `D1` **+322** (19 sembol artıda) |
| **Bitiren şey tek işlem** | −4.792 · tepe/giriş notional **24×** · MAE equity'nin **%86,6'sı** |
| Ekleme merdiveni çarpımsal | `max_adds` sayıyı sınırlar, **boyutu değil** → `ADD-REJECT-E` bağlıyor (`OPEN-33` kapandı) |
| TP yerleşimi | Tam seviye en iyi. 0.02 önde −126, 0.05 önde −113, piyasa emri −321 |
| Öteleme mekanik çalışıyor | TP1 %65,9 → %71,1, stop %34,5 → %29,1 — ama brüt −264 → −670 |
| Temas doluşunun fiyatı | brüt **+570**, uygulama maliyeti **892** → hayalet edge faturalı negatif |
| Tick-PnL ilişkisi | sıra korelasyonu **−0,18** — "yüksek tick sembolleri kaybettiriyor" tezi yanlış |
| **Brüt edge doluş varsayımına bağlı** | TP temasla dolarsa **+1.073**; 1 tick aşım aranırsa **−3.661** |
| **Seçicilik tek gerçek kaldıraç** | `R-ENTRY-02` (3) kapalı → net +4.601, iflas %86 → **%0** (<%25 eşiği) |
| Ekleme tavanı (3) + tek küçültme | net **+27** — sürtünme −640, brüt −599. Wash |
| Limit emri (maker + 1 tick) | net **+128** — sürtünme −4.396, brüt −4.135. Wash |
| `D` kolu bile brüt negatif | −264 — gösterge kapısı ölümü durduruyor, edge üretmiyor |
| Fiyat adımı (tick) | medyan **1,27 bps** (BTC 0,01 · GALA 5,78) — maker farkı 3 bps |
| **Brüt fiyat PnL'i** (temas doluşu) | **+1.073 (+%10,7)** — yalnızca temas varsayımıyla |
| **Kaybın tamamı sürtünme** | komisyon 7.822 (%78,2) · slippage 3.129 (%31,3) · funding 96 |
| **Komisyonun %58,4'ü salınım** | ekleme 2.461 + küçültme 2.109 = 4.569 (başlangıcın %45,7'si) |
| Salınan işlemler | ≥1 tur atan %20,2, net kaybın %59,7'sini ve komisyonun %62,2'sini taşıyor |
| Tepe/giriş notional | ortalama **2,58×** (p90 6,0 · maks 32) — `bps` tabanı bu, giriş değil |
| İflas | equity başlangıcın **%10'u altında barların %77,7'sinde**; likidasyon 0 |
| `OPEN-29` | Dört kol da hesabı sıfırlıyor. `none` en iyi (−1,88 bps). Kapandı, `none` kalır. |
| Mekanik OTE brüt edge | **~0 bps** — giriş seviyesinden bağımsız (0.70/0.75/0.79/pencere/göstergeli) |
| Gidiş-dönüş maliyet | **~14 bps** (komisyon 10 · slippage 4 · funding ~0) |
| Başabaş açığı | brüt 12,61 − maliyet 14,77 = **−2,17 bps/işlem** |
| Girişlerin kaynağı | %81,7 çıplak 0.70 (**−3,9 bps**) · %17,3 FVG (+5,0) · %1,1 OB (+34,5) |
| İşlem sayısı | ~3.100–6.900 / 20 sembol — insan seçiminin çok üstünde, `R-ZONE-08` yok |
| Maliyette çıkış (yanlış) | Eklemeli işlemleri hedefe ulaşmadan öldürüyordu → düzeltildi |
| Maliyette küçültme (`R-ADD-04`) | Ölçüldü: tek sefere indirmek komisyonun %25'ini siliyor, net etkisi **+27** |
| Zombi pozisyon | 202 günlük taşıma görüldü → `OPEN-29` |
| `R-RISK-01` tavanı | Hiç bağlamıyor; bağlayan `R-RISK-05` |
| Koşuların yarıda kalması | Bellek değil (20 sembol ≈ 740 MB / 16 GB). Makine uykusu + terminal bağımlılığı → `scripts/bg.py` |
| Yükleme maliyeti | Sembol başına ~45 sn → önbellekle **0,1 sn** (`data/cache/symbols/`) |

---

## Sıradaki

0. **Kullanıcı:** v4 sayfasında 30 anı etiketle (önce OTE, sonra OB) → `docs/inceleme/v4/etiketler.json`.
   Sonra B2 + `son_supuren` bir kez ölçülür (`swing_secim.py`'ye v4 yolu eklenecek; ölçüt aynı);
   OB etiketleri ayrıca raporlanır (yeni OB tanımının isabeti).
1. **Kullanıcı — yönetici PowerShell:** kayıtçı açılış görevleri `-Kok göç\pc\data` ile
   (`SERVER.md` geçiş tablosu 3. satır); funding / ohlcv30m / earliest için PC görevleri (4. satır).
2. **2026-10-11:** son çekim + birleştirme (`SERVER.md` geçiş tablosu 6. satır), sonuç `goc.md`.
3. H1 kodunun commit hash'i rapora girer; kod artık değişmez. Tek bakış 2027-01-01.
4. H1 sonuç hesabı 1m ister; sunucu yalnızca 30m topluyor — 1m backfill'i 2027-01-01'den önce doğrula.
5. `OPEN-58` kapatılabilir (H2 düştü). Ekleme yolu (`_try_add`) v1'de kapalı (`damga.md` #16).
6. İşlem akışını izle (`trades_gap`, disk). `pull_book` artık `data/`'ya çekmez (PC kaydıyla çakışır) — yalnızca `--root göç/eski`.

**Uyarı:** Ayrılmış %20 harcandı (2026-09-25). 2026-05-08 → 09-11 örneklem içidir.

## Açık maddeler

`OPEN-27` ekleme çarpanı hedefi (şu an `0.79`) · `OPEN-28` KRİTİK'te yarılama ·
`R-ZONE-08` aday sıralaması (adaylar ölçüldü, dayanıklı çıkan yok) · `ADD-REJECT-A` · `OPEN-31` `R-ENTRY-02` (3) kaldırılsın mı · `OPEN-32` doluş varsayımı spec'te tanımsız · `OPEN-34` boyutu risk tavanından türetme · `OPEN-36` maker doluş oranı · `OPEN-37` post-only giriş · `OPEN-38` gerçek doluş ölçümü (ertelendi) · `OPEN-39` kriter 2 bağlayıcı küme

---

## Harita

| Klasör | İçerik |
|---|---|
| `src/data/` | Toplama, doğrulama, Parquet |
| `src/features/` | `structure.py` swing/bias · `ob.py` · `fvg.py` · `candles.py` · `ids.py` deterministik kimlik. Her nesne `known_at` taşır |
| `src/zones/` | `model.py` FSM (`known_at`, `STATE_BAR`) · `store.py` SQLite · `detect.py` leg → zone |
| `src/strategy/` | `entry.py` `R-ENTRY-05` filtreleri |
| `src/backtest/` | `loader.py` `build_from_frames` + önbellek · `engine.py` olay döngüsü (`start`/`step`/`finish`, `order_for`, `add_zones`) · `portfolio.py` cross equity · `costs.py` kalem defteri |
| `src/execution/` | `adapter.py` `ExecutionAdapter` arayüzü, `SimAdapter` (backtest doluş modeli) |
| `src/live/` | `replay.py` artımlı tespit (`kapanis`) + oynatma (`oynat`) — D1 · `paper.py` `PaperCore`, `Durum` (SQLite), `PaperAdapter`, `JsonlGunluk` |
| `scripts/paper.py` | Paper ağ kabuğu: WS 1m (zamanlama), REST (mum), bariyer, kill, kalp atışı |
| `scripts/` | `inceleme.py` v1 paketi + `--kos --bakiye` · `inceleme_v2.py` etiketleme v2 · `inceleme_v3.py` etiketleme v3 (karar anında biten) + `--v4` doğrulama seti · `swing_secim.py` swing adayları (A/B/C/D), etiket doğrulama, `--kos ADAY [--ek _v08]` F1/100 USDT, `--ozet PKL` · `eslestirme_teshis.py` v3 eşleştirme teşhisi (açıklayıcı) · `pc_kayit.ps1 -Kok` PC kayıtçısı · `etiket_capalar.py` v2 etiket → çapa tablosu · `h1_test.py` H1 analizi (kilitli) · `birlestir.py` göç birleştirmesi · `pc_kayit.ps1` PC kayıtçı döngüsü · `h2_kesif.py` H2 keşif · `kalp_ozet.py` paper kalp atışı özeti · `paper.py` `Dongu.izle` R-KILL-01 toparlanması · `damga.py` düzeltilmiş kaldıraç zinciri · `diagnose.py` · `sweep.py` · `entry_variants.py` · `terminate.py` · `reconcile.py` · `branches.py` · `levers.py` A/B/C/D · `tp_placement.py` D1-D4 TP yerleşimi · `add_reject_e.py` stop kaybı tavanı · `spread_logger.py` canlı emir defteri · `robustness.py` breakeven ücreti + komisyon dağılımı + `R-ZONE-08` iç validasyon · `f_kollari.py` F1/F2 · `slippage_stres.py` OPEN-32 (d) · `maker_stres.py` OPEN-36 · `post_only.py` OPEN-37 · `ayrilmis.py` kriter 1 · `neden.py` eğitim/ayrılmış açıklayıcı · `trades_logger.py` işlem akışı · `bg.py` |
| `docs/measurements/` | Ölçüm tarihçeleri — spec'te yalnızca tek satırlık referans var. `damga.md` dışındakiler look-ahead taşır |

Spec kuralı gerekiyorsa baştan okuma: `grep -n "R-ADD-04" docs/STRATEGY_SPEC.md`
Bir kuralın ölçümü gerekiyorsa: kuralın altındaki `Ölçüm:` satırını izle.

**Uzun koşu:** `python -m scripts.bg <modul>` — terminalden bağımsız, log `logs/`'a,
makineyi uyanık tutar. Doğrudan `python -m scripts.X` çalıştırma, terminal kapanınca ölür.
