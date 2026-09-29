# Düzeltilmiş zaman damgası — bilgi anı denetimi ve kaldıraç zinciri

**Tarih:** 2026-09-29 · **spec** v0.5 · kod 3fb2ff4 + düzeltme (işlenmemiş) ·
betik `scripts/damga.py` · log `logs/damga.txt`

> **Etiket: düzeltilmiş zaman damgası — açıklayıcı.** Yalnızca eğitim dilimi. Buradaki
> hiçbir sayı parametre, kural ya da filtre seçmek için kullanılmaz.

## Hata

30m tespit TF'sinde nesnelerin damgaları mumun **açılışıydı** ve motor onları "bilinir
oldu" anı gibi kullanıyordu. Zone, OB ve FVG bir 30m mum erken görünüyordu. Tespit
fonksiyonları nedenseldi; hata tüketen taraftaydı. D0 bunu yakalayamazdı: önek çıktısını
damgaya göre süzdüğü için damga ile hesap birlikte kayınca D0 geçiyordu. Yeni değişmez
testi (`tests/test_known_at.py`) damganın kendisini sınar: eski damgalarla sentetik
serideki 144 zone'un, 53 OB'nin ve 141 FVG'nin hepsi kendi damgası anında kapanmış
mumlardan üretilemiyor.

**Kural (CLAUDE.md #3):** her HTF nesnesi `known_at` = mumun kapanışı taşır. Tüketiciler
yalnızca `known_at`'i okur. Olay damgaları (`mitigated_at`, `filled_at`, delinme) olayın
bilindiği mumun kapanışıdır. 1m durum geçişleri de öyle: bir mumdan çıkan hiçbir bilgi, o
mum kapanmadan kullanılamaz.

## Denetim — zaman damgasını bilgi anı olarak kullanan her yer

| # | Yer | Önce | Durum |
|---|---|---|---|
| 1 | Swing (`structure.detect_swings`) | `pivot_confirmed_at` = teyit mumunun açılışı, bilgi anı sanılıyordu | **Düzeltildi** — `known_at = pivot_confirmed_at + TF` |
| 2 | Zone `WATCH_FROM` (`Zone.watch_from`) | `max(anchor_1 kapanışı, pivot_confirmed_at)` → 1 mum erken izleme | **Düzeltildi** — `Zone.known_at = max(anchor_1 kapanışı, teyit kapanışı)` |
| 3 | OB oluşumu (`ob_eligible`, `evaluate_strength`, `loader.ob_known` → `_try_add`) | `impulse_at` (açılış) | **Düzeltildi** — `OrderBlock.known_at` |
| 4 | OB mitigasyonu (`replay_obs`, `mitigation_time`) | mitigasyon mumunun açılışı | **Düzeltildi** — kapanış |
| 5 | FVG oluşumu (`fvg_eligible`, `evaluate_strength`) | `created_at` (3. mumun açılışı) | **Düzeltildi** — `FVG.known_at` (SQLite şemasına kolon eklendi) |
| 6 | FVG mitigasyon/dolum (`replay`, `FVG.on_bar`) | olay mumunun açılışı | **Düzeltildi** — kapanış |
| 7 | Delinme (`pierce_time`) | geçiş mumunun açılışı; veri geçişten hemen sonra bitince delinme sayılıyordu (önekte tam seriden farklı) | **Düzeltildi** — son teyit mumunun kapanışı; teyit mumları yoksa henüz bilinmiyor. Artık önek-değişmez (D0'a eklendi) |
| 8 | `htf_bias` / `bias_series` | `known_at = ts + 4h` | **Zaten doğruydu** |
| 9 | Motor `_bias_now` (giriş yönü, `OPEN-29`) | `bias_known ≤` 1m mumun açılışı | **Zaten doğruydu** (kötümser) |
| 10 | Zone 1m geçiş damgaları (`primed_at`, `state_changed_at`) | mumun açılışı | **Düzeltildi** — kapanış (`STATE_BAR`). Hiçbir karar bu damgaları okumuyordu |
| 11 | Giriş kurma (`_arm_entry`) | `TOUCHED` mumunda hedef ve aynı mumda dolum. Boyut ve risk o mumun **kapanış** fiyatlarıyla (sembol sırasına göre kısmen) | **Düzeltildi** — `OPEN-41`: emir önceki kapanışta, boyut/risk/gün bloğu kapanış görüntüsünden (`order_for`, `_kapanis`) |
| 12 | İç stop: nihai stop ve breakeven (`R-RISK-02`) | seviyeden, tetik mumunun içinde dolum | **Düzeltildi** — tetik mumunun kapanışından piyasa emri |
| 13 | TP1 / nihai TP | seviyeden dolum | **Zaten doğruydu** — borsada bekleyen limit; giriş mumunda tetiklenemez (tek ilerleme + giriş `on_bar`'dan sonra) |
| 14 | `R-RISK-03` günlük kayıp | dolum anındaki kısmi marklarla | **Düzeltildi** — her kapanışta (`_kapanis`) |
| 15 | `R-RISK-05` küçültme/likidasyon, `OPEN-29` sonlandırma | kapanış markıyla karar ve çıkış | **Zaten doğruydu** |
| 16 | Ekleme (`_try_add`, `R-ADD-01`) | "fiyat bant ötesinde" bu mumun kapanışıyla okunuyor, aynı mumda OB kenarında dolum | **Düzeltilmedi** — v1'de ekleme kapalı (`MAX_ADDS = 0`). Açılmadan önce `OPEN-41` kalıbıyla (bekleyen emir) yeniden yazılmalı. OB bilgi anı (#3) ve delinme (#7) düzeltildi |
| 17 | `R-ADD-04` küçültme | ekleme anında kurulan maliyet limiti | Ekleme kapalı; #16 ile birlikte |
| 18 | Dolum modelleri: `entry_fill="kapanis"`, `OPEN-36` hacim kolu | dolum mumunun kapanış/hacmi | Karar değil dolum modeli (ölçüm kolları); değişmedi |
| 19 | `scripts/measure_fvg.py` doğrulaması | `mitigated_at` açılış indeksi | Kapanışa göre düzeltildi (`an − TF`) |

**Ayrı bulgu (düzeltilmedi, ayrı karar):** zone çapa teması ve breakeven tetiği `low ≤
seviye ≤ high` (temas). Önceki kapanıştan seviyenin ötesine **boşlukla** açılan 1m mumu
stopu tetiklemez. 1m'de nadir ama iyimser taraf. Bekleyen giriş emri için "ulaştı"
ölçütüne geçildi (`OPEN-41`).

## Sonuçlar — kaldıraç zinciri (eğitim dilimi)

Kollar ölçüldükleri zamanki tanımlarıyla (`scripts/damga.py` başlığı). Düzeltilmiş kod =
bilgi anı düzeltmesi + iç stop kapanıştan. `OPEN-41` bu tabloda **yok** (ayrı satır, aşağıda).
Önceki rapor o günün kodudur, yalnızca yön için.

| ölçü | A | C | D | E3 | F1 | F1 kapısız |
|---|---|---|---|---|---|---|
| **net (düzeltilmiş)** | −9.998 | −9.936 | −8.435 | −6.165 | **−4.519** | −8.820 |
| net (önceki rapor) | −9.974 | −9.819 | −5.218 | −176 | +2.376 | – |
| brüt fiyat PnL | −438 | −5.010 | −4.004 | −1.619 | −488 | −1.818 |
| sürtünme | 9.473 | 4.686 | 4.351 | 4.459 | 3.964 | 6.895 |
| **brüt / sürtünme** | −0,05 | −1,07 | −0,92 | −0,36 | **−0,12** | −0,26 |
| işlem | 6.560 | 6.387 | 2.741 | 2.769 | 2.833 | 9.239 |
| maks DD | %100 | %99,4 | %86,6 | %63,6 | %49,0 | %88,3 |
| kriter 3 pozitif ay | 0/11 | 1/11 | 4/11 | 3/11 | 3/11 | 0/11 |
| kriter 3 (A1 / A2) | kaldı / kaldı | kaldı / kaldı | kaldı / kaldı | kaldı / kaldı | kaldı / kaldı | kaldı / kaldı |

Kriter 3: ay = çıkış ayı (UTC); giriş ayıyla sayılar aynı. Dilimin son iki ayında
(2026-05, 06) sembollerin çoğunun verisi bitmiş durumda; ay sayılıyor ama az sembol taşıyor.

**Okuma.**

1. **Hiçbir kolda brüt edge yok.** Brüt fiyat PnL'i her kolda negatif. Önceki raporlardaki
   pozitif brüt (D'de −264'ten E3'te +5.097'ye, F1'de +6.881) look-ahead'den geliyordu.
2. **Gösterge kapısı hâlâ kaybı azaltıyor ama edge üretmiyor.** D − C: net **+1.501**, brüt
   +1.006, 3.646 daha az işlem. F1 − F1 kapısız: net **+4.301**, brüt +1.331, 6.406 daha az
   işlem. Kapı kötü işlemleri eliyor; kalan işlemler de brüt negatif.
3. `ADD-REJECT-E` (D → E3) ve ekleme kapatma (E3 → F1) kuyruk riskini düşürmeye devam
   ediyor: maks DD %86,6 → %63,6 → %49,0.

## F1 ayrıştırması

| adım | net | işlem |
|---|---|---|
| önceki rapor | +2.376 | 2.251 |
| + bilgi anı (damga) düzeltmesi | −3.738 | 2.833 |
| + iç stop tetik mumunun kapanışından | −4.519 | 2.833 |
| + `OPEN-41` bekleyen giriş emri | **−8.646** | 3.565 |

`OPEN-41` farkı (−4.127, +732 giriş) sayaçlardan: emri en az bir kez aktif olan zone
3.088 → 3.600 (+512). Eski kod emri **bir kez**, `TOUCHED` mumunda kuruyordu; gösterge
kapısında o an kalan zone bir daha denenmiyordu. `OPEN-41` her kapanışta yeniden
değerlendirir: temastan **sonra** bantta oluşan OB/FVG ile kapıyı geçen zone'lar emir
alıyor ve bu geç girişler kaybettiriyor. Çapa mumunda dolum + stop yalnızca 26 işlem.
Sembol meşgulken reddedilen zone da artık sonra girebiliyor (eskiden tek şans). F1
zaten dondurulmuş: karar değişmiyor. Kod `4cac1eb9` parmak izli işlem listesi
`logs/f1check/f1_open41_trades.txt`.
