# HYPOTHESES — ön kayıtlar

İki hipotez, ikisi de aynı ileriye dönük dilimde bir kez bakılır. Güven sınırı iki test
için **tek yönlü %97,5** (iki hipotez, Bonferroni: 0,05 / 2).
H2 keşifte düştü (§8.4); H1'in sınırı yine **%97,5** kalır — bir sonuç görüldükten sonra
gevşetilmez.

| | Konu | Veri | Bölüm |
|---|---|---|---|
| **H1** | Order flow: temastaki emilim | işlem akışı (görülmedi) | §1–§7 |
| **H2** | 4h unmitige OB, 2R, borsa stopu — **ileriye dönük testten çıkarıldı** (keşifte brüt negatif, §8.4) | OHLCV | §8 |

---

# H1 — order flow ön kaydı

| | |
|---|---|
| **Yazıldığı tarih** | 2026-09-30 |
| **Veri durumu** | Bu belge yazılana kadar işlem akışı (`trades/`) ve emir defteri (`book/`) verisinin **içeriğine hiç bakılmadı**. Yalnızca bütünlük denetlendi: boşluk sayısı (`trades_gap`), disk kullanımı, `pull_book` dosya sayısı ve özet sağlaması. Hiçbir fiyat, hacim, delta ya da derinlik değeri okunmadı, çizilmedi, özetlenmedi. |
| **Otorite** | `STRATEGY_SPEC.md` > bu belge. Kod yok. |
| **Durum** | Ön kayıt. Değiştirilirse değişiklik tarihli olarak aşağıya eklenir; eşikler veri görüldükten sonra **değiştirilemez**. |

**Neden.** Spec §8 (2026-09-30): düzeltilmiş zaman damgalarıyla mekanik OTE'nin hiçbir
kolunda brüt edge yok ve OHLCV üzerinde yeni filtre araştırması durduruldu. Order flow,
OHLCV'nin içermediği bilgidir. Tek soru: temastaki akış, fiyatın banttan dönüp dönmeyeceğini
ayırt ediyor mu?

---

## 1. Veri

| Kaynak | Başlangıç | Çözünürlük | Kısıt |
|---|---|---|---|
| İşlem akışı `data/bingx/{sym}/trades/` | 2026-09-27 | her işlem: `id`, `ts` (ms), `price`, `qty`, `side` (agresör) | REST, son 1.000 işlem; boşluk `fillId` ile kesin sayılır (`trades_gap`) |
| Emir defteri `data/bingx/{sym}/book/` | 2026-09-25 | dakikada bir anlık görüntü, ilk 5 kademe | temas anında değil, dakikanın herhangi bir anında; 5 kademe seviyeye uzanmayabilir |
| 1m ve 30m OHLCV | geçmiş | zone tespiti ve sonuç | spec'teki düzeltilmiş kod (`known_at`, `OPEN-41`) |

Semboller: **40** — orijinal 20 (`liquidity.json`) + soğuk 20 (`liquidity_soguk.json`),
sunucudaki listeler (`docs/SERVER.md`). İlk kayıtta 20'ydi; değişiklik §5'te tarihli.

## 2. Olay: zone teması

Zone'lar mevcut koddan gelir (`src/zones/detect.py`, düzeltilmiş `known_at`). **Olay** =
zone'un `PRIMED → TOUCHED` geçişi (0.70 teması, R-ZONE-04). Gösterge kapısı (`R-ENTRY-02`
(3)) **uygulanmaz**: soru akışın kendisi hakkında.

- `t0` = temas mumunun kapanışı. Her özellik yalnızca `≤ t0` veriyle hesaplanır (CLAUDE.md #3).
- Temas mumunda `1` çapasına da ulaşıldıysa (aynı mum) olay dışlanır: karar anı yok.

## 3. Ölçülecek özellikler

Yön işareti: zone'a **karşı** itiş = SHORT zone'da alıcı agresör, LONG zone'da satıcı
agresör. `A(m)` = `m` dakikasında karşı yönlü agresör miktarı, `B(m)` = zone yönünde.

| Özellik | Tanım | Rol |
|---|---|---|
| Dakika deltası | `d(m) = B(m) − A(m)` (baz varlık) | kayıt |
| Kümülatif delta | `Σ d(m)`, zone `PRIMED` anından `t0`'a | kayıt |
| **Emilim** | aşağıda | **birincil** |
| İkinci deneme başarısızlığı | `touch_count ≥ 2` ve bu temasın uç fiyatı ilk temasınkini geçmedi | kayıt |
| Seviyedeki bekleyen emir | `t0` dakikasının defter görüntüsünde, 0.70–0.79 bandı içindeki kademelerde karşı taraf miktarı (SHORT: satış) | kayıt |
| Defter dengesizliği | `(Q_zone − Q_karşı) / (Q_zone + Q_karşı)`, ilk 5 kademe toplamı | kayıt |

### Emilim — sayısal tanım (veri görülmeden sabitlendi)

Pencere `W` = `t0`'da biten son 5 dakika (temas mumu dahil). Taban = `A`'nın `W`'dan önceki
60 dakikadaki medyanı (`A_60`).

Emilim **var** ⇔ ikisi birden:

1. **Agresif hacim yüksek:** `Σ_{m∈W} A(m) ≥ 3 × 5 × A_60`
2. **Fiyat ilerlemiyor:** `W` boyunca bandın içine en derin ilerleme, bant genişliğinin
   yarısını geçmedi. SHORT: `(max high_W − L070) / (L079 − L070) ≤ 0.5`; LONG simetrik.

`A_60 = 0` ise (işlemsiz saat) olay dışlanır. `W` veya 60 dakikalık taban `trades_gap` ile
çakışıyorsa olay dışlanır (boşluklu veriyle emilim ölçülmez).

Eşikler (5 dk, 60 dk, 3×, 0.5) **tahmindir, ayarlanmaz**. Başka değerler bu belgeyle
sınanmaz; sınanacaksa yeni tarihli ön kayıt gerekir.

## 4. Birincil hipotez ve tek başarı ölçütü

**H1.** Emilimli temaslarda, `t0` kapanışından girilen zone yönlü işlemin **ortalama net
R'si sıfırdan büyüktür**.

- Giriş: `t0` kapanış fiyatı, taker (girişin karar anı `t0`; `OPEN-41` bekleyen emri bu
  testin dışında).
- Stop: `1` çapası (`R-RISK-02`; temas → kapanıştan, boşluk → açılıştan).
- Hedef: `0.50` (TP1) seviyesinde **tam** çıkış (tek hedef; breakeven ve nihai TP yok).
- `R` = PnL / |giriş − stop|. **Net** = taker komisyonu gidiş-dönüş + slippage (§8 maliyet
  modeli, `costs.py`) R cinsinden düşülür. Funding ihmal (işlemler dakikalar-saatler).
- Aynı mumda hem hedef hem stop → stop (§8).
- 7 gün içinde ikisi de olmazsa 7. günün sonundaki kapanıştan çıkılır.

**Tek başarı ölçütü:** emilimli temaslarda ortalama net R'nin **tek yönlü %97,5 güven alt
sınırı > 0** (2026-09-30 güncellemesi, ilk kayıtta %95) (t-istatistiği, temaslar arası bağımsızlık varsayımı; aynı sembolde üst üste
binen işlemler bırakılmaz — her temas ayrı gözlem).

Emilimsiz temaslar karşılaştırma için raporlanır ama kabul ölçütü **değildir**.

## 5. Ne kadar veri

- Düzeltilmiş kodla (eğitim dilimi, 20 sembol) 489.087 dakikada **11.380 temas** →
  **ayda ~1.015 temas** (20 sembolün toplamı).
- R'nin dağılımı yaklaşık iki noktalı: kazanç ≈ +0,67 R (0.70'ten 0.50'ye 0,20 leg, stop
  0,30 leg), kayıp ≈ −1 R → standart sapma ≈ 0,8 R.
- Anlamlı etki: ortalama net **+0,10 R**. İlk kayıt (tek yönlü %5, güç %80):
  `n = ((1,645 + 0,842) × 0,8 / 0,10)² ≈ 396` emilimli temas.
- **Geçerli eşik: n ≥ 503** (tek yönlü %97,5, güç %80):
  `n = ((1,960 + 0,842) × 0,8 / 0,10)² ≈ 503` emilimli temas.
- Emilim sıklığı bilinmiyor (veri görülmedi). Planlama varsayımı **%15**.
- **Tahmini ulaşma (40 sembol):** temas oranı sembol başına eşit varsayılırsa (soğuk 20'nin
  temas sayısı düzeltilmiş kodla ölçülmedi) ayda ~2.030 temas → ~305 emilimli/ay →
  503 / 305 ≈ **1,65 ay → ~2026-11-20**. 20 sembolle ~152/ay → 3,3 ay, dilim yetmezdi.
  Boşluk ve dışlamalar için pay: dilim 3 ay (12-31) kalır.

**Değişiklikler (tarihli):**

| Tarih | Değişiklik | Veri durumu |
|---|---|---|
| 2026-09-30 | Güven sınırı %95 → **%97,5** (iki hipotez). Eşik ilk olarak 396'da bırakıldı (güç ~%70) | İşlem akışı verisine hiç bakılmadan önce yapıldı |
| 2026-09-30 | Eşik 396 → **503** (%97,5'te güç %80) | İşlem akışı verisine hiç bakılmadan önce yapıldı |
| 2026-09-30 | Sembol seti 20 → **40** (orijinal 20 + soğuk 20). Soğuk 20'nin işlem akışı kaydı dilimden (10-01) önce başlar | Veri görülmeden önce yapıldı; soğuk 20'nin akışı henüz kaydedilmiyordu |

## 6. Test protokolü

| | |
|---|---|
| Dilim | **2026-10-01 00:00 UTC → 2026-12-31 23:59 UTC** (ön kayıttan sonra başlar; 09-25…09-30 verisi kullanılmaz). Yetersiz örnekte tek seferlik 2027-03-31'e uzar |
| Kaç kez bakılır | **Bir kez**, 2027-01-01'den sonra (yetersiz örnekte o gün yalnızca `n` sayılır, sonuç 2027-04-01'den sonra bir kez). Ara bakış yok: ne özellik dağılımı, ne ara sonuç. İşlem akışı bu sürede yalnızca bütünlük için okunur (boşluk, disk) |
| Kod | Özellik ve sonuç kodu dilime bakmadan, sentetik veriyle test edilerek yazılır ve commit edilir; commit hash'i sonuç raporuna yazılır |
| Ayrılmış veri | Yok — bu dilimin tamamı tek seferlik doğrulamadır; eğitim dilimi yoktur, eşikler önceden sabit |

**Kabul kriterleri (hepsi):**

1. Emilimli temas sayısı **≥ 503**. Yetersiz örnek kuralı aşağıda.
2. Emilimli temaslarda ortalama net R'nin tek yönlü %97,5 alt sınırı **> 0** (birincil ölçüt).
3. Sonuç tek sembole ya da tek aya dayanmıyor: en iyi sembol çıkarıldığında **ve** en iyi ay
   çıkarıldığında ortalama net R hâlâ **> 0** (nokta tahmini).

1 geçer, 2 veya 3 kalırsa: **ret**. Ret sonucu da kaydedilir; eşik değiştirilip aynı dilimde
yeniden bakılmaz.

**Yetersiz örnek kuralı (2026-09-30).** 2027-01-01'deki bakışta **önce yalnızca sayı**
(emilimli temas `n`) hesaplanır; R'ye bakılmaz.

- `n ≥ 503` → kriter 2 ve 3 değerlendirilir, sonuç kesin.
- `n < 503` → sonuç **"kararsız"**. Dilim **bir kez**, **2027-03-31 23:59 UTC**'ye uzar;
  10-01 → 03-31 tek dilim olarak 2027-04-01'den sonra bir kez değerlendirilir. O gün de
  `n < 503` ise sonuç kesin olarak "kararsız"dır; ikinci uzatma yok.

## 7. Kapsam dışı

- Bu hipotezden strateji kuralı türetmek. Kabul edilirse spec değişikliği ayrı karardır.
- Defter özelliklerinin kabul ölçütü olması: dakikada bir, 5 kademe — temas anındaki
  defteri temsil ettiği bilinmiyor. Yalnızca kaydedilir.
- `OPEN-38` (gerçek doluş ölçümü): ayrı konu.

---

# H2 — 4h unmitige OB, sabit 2R

| | |
|---|---|
| **Yazıldığı tarih** | 2026-09-30, keşif koşusundan **önce** |
| **Veri durumu** | OHLCV geçmişi mekanik OTE araştırmasında çok kez görüldü; **bu tanımla** hiçbir koşu yapılmadı. 4h OB'ler üzerinde işlem sonucu hiç ölçülmedi. |
| **Ayar** | Yok. Aşağıdaki her sayı ya mevcut kodun sabitidir ya da tanımın kendisidir. |

## 8.1 Tanım

| | |
|---|---|
| **Nesne** | 4h OB, mevcut tanım (`src/features/ob.py`, `detect_order_blocks`): impuls mumu gövdesi ≥ `IMPULSE_MULT = 4.0` × son `BODY_LOOKBACK` mumun medyan gövdesi; OB = impulstan önceki son ters yönlü mumun gövdesi. 4h mum = 30m'den UTC 00/04/08/12/16/20 hizalı, 8 alt mumu tam olan mum. |
| **Bilgi anı** | `known_at` = impuls 4h mumunun **kapanışı** |
| **Unmitige** | `known_at`'ten sonra fiyat OB gövdesine henüz dokunmadı. İlk temas (`mitigation_time`) OB'yi tüketir |
| **Giriş** | `known_at`'te OB'nin **yakın kenarına** post-only limit: BULLISH (talep) → LONG, `top`'ta; BEARISH (arz) → SHORT, `bottom`'da. Doluş kuralı motorun limit kuralı: seviye **1 tick** geçilmeden dolmaz, maker komisyonu, slippage yok. Emir ilk temasta dolmazsa iptal (OB tüketildi, artık unmitige değil). Kovalama yok |
| **Stop** | Borsaya gönderilen stop-market (hocanın "otomatik stop"u), OB'nin **karşı kenarının 1 tick ötesi**: LONG `bottom − tick`, SHORT `top + tick`. Mum içinde tetiklenir (kapanış beklenmez): 1m `low ≤ stop` (LONG). Doluş stop fiyatından, mum boşlukla açıldıysa açılıştan; taker + slippage (`costs.py`) |
| **TP** | Sabit **2R**, `R = |giriş − stop|`. Reduce-only limit, tek çıkış; doluş kuralı girişle aynı (1 tick, maker) |
| **Ekleme** | Yok |
| **Aynı mum** | Doluş mumunda stop da vurulduysa stop. Doluş mumunda TP aranmaz (sıra bilinmez). Aynı 1m mumda TP ve stop → stop (§8 kuralı) |
| **Süre** | Sınır yok: TP ya da stop. Dilim sonunda açık kalan işlem son kapanıştan değerlenir ve ayrıca sayılır |
| **Boyut** | `ADD-REJECT-E` mantığı: stopta realize olacak kayıp (stop fiyatında komisyon dahil değil) = doluş anındaki realize equity'nin **%3'ü** (`L = STOP_LOSS_CAP`). `qty = 0,03 × equity / |giriş − stop|` |
| **Semboller** | Mevcut 20 sembol (`liquidity_symbols(20)`) |
| **Maliyet** | `costs.py`: `fees.json` oranları, slippage 2 bps (yalnızca taker doluşlarda), funding ölçülen/atanan |
| **Bağımsızlık** | Her OB ayrı gözlem. Aynı sembolde çakışan işlemler bırakılmaz (H1 ile aynı) |

**Net R** = (fiyat PnL − komisyon − funding − slippage) / (`qty × |giriş − stop|`).

**`1 tick` açık madde (`OPEN-58`).** "Karşı kenarın ötesi" mesafe söylemiyor. En küçük
"öte" = 1 tick seçildi (tick borsadan, `fees.json`). **Kullanıcı onayı bekliyor**;
2026-10-01'den önce değişirse bu satır tarihli değişir, sonra değişmez.

## 8.2 Birincil ölçüt ve gereken örnek

**Birincil ölçüt:** ortalama net R'nin **tek yönlü %97,5 alt sınırı > 0** (t-istatistiği).

**Gereken n.** H1'le aynı yöntem ve aynı anlamlı etki (+0,10 R, güç %80). 2R işlemin R'si
iki noktalı (+2 / −1); başabaşta (`p = 1/3`) standart sapma `3 × √(p(1−p)) ≈ 1,41 R`:
`n = ((1,960 + 0,842) × 1,41 / 0,10)² ≈` **1.570 işlem** (dolan giriş).

**Kabul kriterleri** H1'in yapısı (§6): (1) `n ≥ 1.570`, (2) birincil ölçüt, (3) en iyi
sembol ve en iyi ay çıkarıldığında ortalama net R hâlâ > 0.

**Yetersiz örnek kuralı** H1'le aynı: 2027-01-01'de yalnızca `n`; `n < 1.570` →
"kararsız", dilim bir kez 2027-03-31'e uzar; orada da azsa kesin "kararsız".

## 8.3 Protokol

| | |
|---|---|
| Dilim | H1'le aynı: `known_at` **2026-10-01 00:00 UTC → 2026-12-31 23:59 UTC** olan OB'ler (uzarsa 2027-03-31). İşlem dilim sonrasına taşarsa sonucu 7 gün beklenir, sonra son kapanıştan değerlenir |
| Keşif | Eğitim diliminde (30m'in en eski %80'i, 1m'in kapsadığı kısım) **bir** koşu, bu tanımla, sıfır ayar. Etiket: **"keşif — onay değil"**. Eğitimde **brüt** negatifse H2 ileriye dönük pencereden çıkar ve gerekçe §8.4'e yazılır. Pozitifse hiçbir şey değişmeden ileriye dönük teste kalır |
| Kod | `scripts/h2_kesif.py`; ileriye dönük değerlendirme aynı kodla |

## 8.4 Keşif sonucu — **keşif, onay değil** (2026-09-30)

`scripts/h2_kesif.py` · `logs/h2_kesif.txt` / `.csv` · spec v0.5 · kod `d341574+kirli` ·
eğitim dilimi, 1m 2025-07-31 → 2026-07-06, 20 sembol. Tek koşu, sıfır ayar.

| | |
|---|---|
| OB (1m kapsamında) | 1.853 · post-only red 100 · temas yok 202 · dokundu dolmadı 215 |
| İşlem | **1.335 kapanan** (TP 373 · STOP 962) + 1 açık · kazanma **%27,9** (2R başabaşı %33,3) |
| R (boyuttan bağımsız) | brüt ort **−0,160** · net ort **−0,481** · %97,5 alt sınır **−0,582** |
| R toplamı | brüt **−214 R** · sürtünme 429 R → brüt/sürtünme **−0,50** |
| USD (%3 boyut, bileşik) | brüt **−5.727** · sürtünme 4.273 (komisyon 3.336 · slippage 831 · funding +106) · net **−10.000** · brüt/sürtünme −1,34 |
| Kriter 3 | **KALDI** — A1 5/11 (hesap 2025-09'da sıfırlandı, sonraki aylar ~0), A2 kaldı |
| Ay bazında brüt R | 12 ayın **9'unda negatif** |

**Karar: H2 ileriye dönük pencereden çıkarıldı.** Protokol (§8.3): eğitimde brüt negatif.

**Gerekçe.** Brüt negatiflik sürtünmeden ya da boyuttan gelmiyor: kazanma oranı (%27,9)
sürtünmesiz başabaşın (%33,3) 5 puan altında ve brüt R 12 ayın 9'unda eksi. USD sonucu
yola bağlıdır (eşzamanlı çok pozisyon × %3, hesap ilk iki ayda sıfırlandı), R sonucu değil;
ikisi de aynı işarette. Ek not: 4h OB gövdesi dar olduğunda (medyan R genişliği fiyatın
%0,68'i) komisyon tek işlemde −32 R'ye kadar çıkıyor — tanımın kendisi, ayar değil.

`OPEN-58` (stopun "1 tick ötesi") bu sonucu değiştirmez: mesafe büyüdükçe R başına
sürtünme azalır ama brüt işareti kazanma oranından gelir; bu yorumdur, ölçülmedi ve
yeni ölçüm yapılmayacak (sonuç görüldükten sonra tanım değişmez).

