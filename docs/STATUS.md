# STATUS

Her oturumun **ilk** okuduğu dosya. Kısa tutulur. Oturum sonunda güncellenir.

**Son güncelleme:** 2026-09-29

---

## Şu an

**Görev:** Canlı döngü ön koşulları (`docs/LIVE.md` Ö1–Ö3) yapıldı, F1 birebir korundu.
D0 yazıldı. **D1 ve `OPEN-41` kodu kullanıcı kararını bekliyor: motorda look-ahead bulundu.**

**2026-09-29 (2. oturum):**
- `OPEN-41`…`OPEN-57` kapandı, spec **v0.5** (`R-ENTRY-02` emir anı, `R-RISK-02` felaket
  stopu, §6 kill eylemleri). Karar satırları `docs/LIVE.md` §9.
- Ö3 deterministik kimlik (`src/features/ids.py`, `uuid5`) · Ö1 `Backtest.start/step/finish`
  · Ö2 `src/execution/adapter.py` (`ExecutionAdapter`, `SimAdapter`). Her adımdan sonra F1
  eğitim: net **2.376,0853**, 2.251 işlem, işlem parmak izi ve tüm sayaçlar birebir aynı.
- **Look-ahead (CLAUDE.md #3).** 30m damgaları mumun **açılışı**; motor bunları "bilinir
  oldu" anı gibi kullanıyor: zone `pivot_confirmed_at` (→ `watch_from`), OB `impulse_at`,
  FVG `created_at` bir 30m mum erken görünüyor. `htf_bias` doğru (`known_at = ts + TF`).
  Damgalar kapanışa kaydırılınca (yalnızca ölçüm, `src` değişmedi) F1 eğitim
  **+2.376 → −3.721**, işlem 2.251 → 2.832. Tespit fonksiyonları nedensel (D0 geçiyor);
  hata tüketen tarafta. D1 bu hatayla geçemez.
  Ayrıştırma: yalnızca zone damgası → **+1.973** (1.946 işlem); yalnızca OB/FVG damgaları →
  **−3.930** (3.219 işlem). Gösterge kaydırması iki yönlü: oluşum geç görünür (iyimserlik
  kalkar) **ve** `filled_at`/`mitigated_at` geç görünür (açılış damgasının kötümserliği
  kalkar, kapı daha çok zone geçirir). İkisi ayrı ölçülmedi. Betik: `logs/f1check/`.

**Durum: F1 donduruldu.** Kriter 1 kaldı (K1–K3), sonuç kabul edildi (spec §8).
2026-05-08 → 09-11 dilimi artık örneklem içi. **Yeni doğrulama yalnızca 2026-09-11
sonrası veride yapılabilir.** `OPEN-38` ertelendi.

- **Neden** (`docs/measurements/neden.md`, yalnızca açıklayıcı): sürtünme sabit kaldı
  (6,9 → 7,0 bps). İşlem başı brüt 10,6'dan 1,1 bps'e düştü. Kaybın yarısı isabetten,
  yarısı kazanan işlemin küçülmesinden. İşlem sayısı oranı etkilemiyor. Eğitimin son iki
  ayı zaten eksiydi.
- **Isınma varsayımı:** 3 işlem, −123. Sonucu açıklamıyor.
- **İşlem akışı:** `janitor-trades-logger` 2026-09-27'de kuruldu, 20 sembol. BingX
  işlem geçmişi vermiyor, yalnızca son 1.000 işlem geliyor. İlk 2,5 saatte 0 boşluk,
  ~85 MB/gün.

**2026-09-29:**
- `pull_book` işlem verisini de çekiyor (`trades/`, üzerine yazma koruması `id` ile). İlk
  tam çekim: 80 dosya, 0 hata, 45 sn.
- Spec §8'e **kriter 3** (aylık dağılım ön kapısı) eklendi. `OPEN-40` kapandı: UTC takvim
  ayı, dilimde günlerinin yarısından azı kalan ay sayılmaz.
- **`docs/LIVE.md`** canlı döngü tasarımı (kod yok). Ön koşullar: `step` çıkarımı,
  doluşun `ExecutionAdapter` arkasına alınması, deterministik `zone_id`/`ob_id`. Merkez:
  parite testi D0–D3. Açık sorular `OPEN-41`…`OPEN-57`.
- **VST demo `OPEN-37`'yi cevaplayamaz** (`docs/measurements/vst.md`). Ayrı defter, ayrı
  işlem akışı, ortak `fillId` 0. DOGE'de orta fiyat 12 bps ayrışıyor. Demo anahtarının
  gerçek hesaba erişip erişmediği doğrulanamadı. Demo doluş testi yapılmadı.

**Sunucu:** `janitor-spread-logger` · `janitor-trades-logger` (sürekli) ·
`janitor-earliest.timer` (03:00 UTC) · `janitor-ohlcv30m.timer` (03:30 UTC). Hepsi
`janitor` kullanıcı servisi (`docs/SERVER.md`).

**İlgili dosyalar:** `scripts/neden.py` · `tests/test_neden.py` · `scripts/trades_logger.py` ·
`tests/test_trades_logger.py` · `docs/measurements/neden.md`

---

## Bildiklerimiz (kısa)

| Bulgu | Sonuç |
|---|---|
| **F1 eğitim edge'i look-ahead'den** | damgalar kapanışa alınınca +2.376 → **−3.721**. Önceki tüm backtest sayıları aynı hatayı taşıyor |
| `pierce_time` önek-değişmez değil | tasarım gereği (veri geçişten hemen sonra biterse delinme sayılır, kötümser); D0 dışında |
| **Backtest girişi temas mumunda kurup dolduruyor** | canlıda emir önceden defterde olmalı → `OPEN-41` |
| Zone/OB kimliği `uuid4` | canlı ↔ backtest eşleştirilemez; deterministik kimlik ön koşul |
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

1. **Karar kullanıcının:** F1 donduruldu. Sonraki strateji değişikliği yalnızca
   2026-09-11 sonrası veride doğrulanabilir. Bu veri birikiyor.
2. İşlem akışını birkaç gün izle: `trades_gap` sayısı ve disk kullanımı. Boşluk
   çıkarsa `--cycle` kısaltılır ya da yoklama paralelleştirilir.
3. **Karar kullanıcının:** look-ahead düzeltmesi (damga + TF'yi "bilinir" anı yap). F1
   sayısı değişir. Sonra: `OPEN-41` kodu + F1 fark raporu, D1 (`ReplayFeed` + artımlı
   tespit), `ARCHITECTURE.md` §4.1 olay listesi (`OPEN-54`).
4. Görev Zamanlayıcı'ya `pull_book`'u kaydet.

**Uyarı:** Ayrılmış %20 harcandı (2026-09-25). 2026-05-08 → 09-11 örneklem içidir.

## Açık maddeler

`OPEN-27` ekleme çarpanı hedefi (şu an `0.79`) · `OPEN-28` KRİTİK'te yarılama ·
`R-ZONE-08` aday sıralaması (adaylar ölçüldü, dayanıklı çıkan yok) · `ADD-REJECT-A` · `OPEN-31` `R-ENTRY-02` (3) kaldırılsın mı · `OPEN-32` doluş varsayımı spec'te tanımsız · `OPEN-34` boyutu risk tavanından türetme · `OPEN-36` maker doluş oranı · `OPEN-37` post-only giriş · `OPEN-38` gerçek doluş ölçümü (ertelendi) · `OPEN-39` kriter 2 bağlayıcı küme

---

## Harita

| Klasör | İçerik |
|---|---|
| `src/data/` | Toplama, doğrulama, Parquet |
| `src/features/` | `structure.py` swing/bias · `ob.py` · `fvg.py` · `candles.py` · `ids.py` deterministik kimlik |
| `src/zones/` | `model.py` FSM · `store.py` SQLite · `detect.py` leg → zone |
| `src/strategy/` | `entry.py` `R-ENTRY-05` filtreleri |
| `src/backtest/` | `loader.py` sembol hazırlığı + önbellek · `engine.py` olay döngüsü (`start`/`step`/`finish`) · `portfolio.py` cross equity · `costs.py` kalem defteri |
| `src/execution/` | `adapter.py` `ExecutionAdapter` arayüzü, `SimAdapter` (backtest doluş modeli) |
| `scripts/` | `diagnose.py` · `sweep.py` · `entry_variants.py` · `terminate.py` · `reconcile.py` · `branches.py` · `levers.py` A/B/C/D · `tp_placement.py` D1-D4 TP yerleşimi · `add_reject_e.py` stop kaybı tavanı · `spread_logger.py` canlı emir defteri · `robustness.py` breakeven ücreti + komisyon dağılımı + `R-ZONE-08` iç validasyon · `f_kollari.py` F1/F2 · `slippage_stres.py` OPEN-32 (d) · `maker_stres.py` OPEN-36 · `post_only.py` OPEN-37 · `ayrilmis.py` kriter 1 · `neden.py` eğitim/ayrılmış açıklayıcı · `trades_logger.py` işlem akışı · `bg.py` |
| `docs/measurements/` | Ölçüm tarihçeleri — spec'te yalnızca tek satırlık referans var |

Spec kuralı gerekiyorsa baştan okuma: `grep -n "R-ADD-04" docs/STRATEGY_SPEC.md`
Bir kuralın ölçümü gerekiyorsa: kuralın altındaki `Ölçüm:` satırını izle.

**Uzun koşu:** `python -m scripts.bg <modul>` — terminalden bağımsız, log `logs/`'a,
makineyi uyanık tutar. Doğrudan `python -m scripts.X` çalıştırma, terminal kapanınca ölür.
