# Piyasa süzgeç adayları — ön kayıt (2026-10-13)

**Durum: yazıldı, koşulmadı.** Bu dosya koşudan önce sabitlenir; sonuç görüldükten sonra eşik,
formül ya da karar ölçütü değiştirilmez — değişirse tarihli not olarak eklenir (`docs/izgara_tf.md`
ile aynı disiplin).

## Kaynak

`docs/inceleme/strateji/etiketler.json` (20 işlem, kullanıcı etiketleri, `docs/inceleme/strateji/ozet.md`).
**Not:** grafikler çıkışı gösterdiği için karar × sonuç ilişkisi sonradan bakış içerir (`12 girmezdim`
→ `11 STOP`), kanıt olarak kullanılmaz. Kullanılan yalnızca kullanıcının **sebep** alanı
(`trend ters`, `düz piyasa`, `zigzag zayıf (0-1-0.5)`, `hacim yok`, `setup yok`, `bekleyecektim`,
`diğer`).

## Süzgeçler

Üçü de **giriş filtresi**: koşul doğruysa o zone/an için giriş emri üretilmez
(`src/backtest/engine.py:Backtest.order_for`, R-ENTRY-02 aşamasında ek kapı). Hiçbiri spec kuralı
değil — F2 (`min_leg_pct`) ve ADD-REJECT-E gibi, ölçmek için eklenen aday parametreler.

### S1 — Belirsiz trend
4h yapısal yön (`R-ZONE-10` bias) giriş anında `NONE` ise giriş yok. Zaten hesaplanıyor
(`Backtest._bias_now`, `Trade.entry_bias` ile aynı değer) — yeni veri gerekmez.

### S2 — Düz piyasa
Girişten önceki 24 saatin hacmi, son 30 günün günlük hacim medyanının **altında** ise giriş yok.
**Nedensel (CLAUDE.md #3):** iki pencere de girişten **önceki** veri; "24 saat" = `[giriş−24s, giriş]`
dakikalık hacim toplamı; "son 30 gün" = girişin takvim gününden önceki 30 **tam** gün (kısmi/bugünkü
gün sayılmaz), her günün toplam hacmi, bunların medyanı. Gün = UTC takvim günü (00:00–24:00).
Sembolün geçmişinde 30 günden az varsa eldeki günlerin medyanı kullanılır; hiç gün yoksa süzgeç o
an bloklamaz (veri yoksa reddetmek yerine geçirmek — muhafazakâr hata yönü, F1'deki "veri bayatsa
DATA" mantığıyla aynı yönde: eksik veri bir red üretmez).

### S3 — Zayıf zigzag
Leg verimliliği = `|capa_1 − capa_0| / Σ|30m kapanış farkları|` (capa_0'dan capa_1'e, uçlar dahil).
Düşük değer = kırık/dolaşık yol — kullanıcının "zigzag zayıf (0-1-0.5)" sezgisiyle örtüşmesi
beklenir. Tüm zone'ların (20 sembol, eğitim dilimi, `logs/inceleme/ltf31_veri.pkl`) medyanının
**altında veya eşit** ise giriş yok. Capa'lar zone oluşumunda sabitlenir — karar anında zaten
bilinir, look-ahead yok. Aralarında 30m kapanış farkı olmayan (tek nokta) leg verimlilik `1.0`
sayılır (bölen sıfır olamaz; tek adımlık yol kendi başına tam verimlidir).

**Eşikler veriden (medyan), performanstan değil** — CLAUDE.md "otomatik parametre optimizasyonu /
self-tuning yasak". Sayısal medyan değerleri performans görülmeden, aşağıya tarihli not olarak
eklenir (ayrı adım, "Hesaplanan eşikler" bölümü).

## Kombinasyonlar

S1, S2, S3, S1+S2, S1+S3, S2+S3, S1+S2+S3 — yedi kol, hepsinde #31'in kurgusu değişmeden üstüne
eklenir (B2 + `son_supuren`, A1+B, OB/OTE girişi v0.11, ekleme 1-1 × 3, K = 0,25, limit emirleri,
ADD-REJECT-E %3, stop kaybı tavanı, 100 USDT, eğitim dilimi, 20 sembol). Taban #31 zaten koşulu
(`logs/inceleme/ltf31_31.pkl`, parmak izi görülecek), **yeniden koşulmaz**. Kombinasyonda bir
işlem, aktif süzgeçlerden **herhangi biri** reddederse elenir (VE değil, OR — her süzgeç bağımsız
bir kapı).

## Tutarlılık (madde 3 — kalibrasyon değil, rapor)

20 etiketli işlemin her biri için üç süzgeç koşulu da hesaplanır (S1: `bias_4h == "NONE"` —
etikette zaten var; S2/S3: bu 20 işlemin kendi zone/giriş zamanı için ayrıca hesaplanır). Her
kombinasyon için: kullanıcının 12 "girmezdim"inden kaçını da eler (örtüşme) ve 8 "girerdim"inden
kaçını yanlışlıkla eler (yanlış red). Performans ölçütü değildir, yalnızca kullanıcının yargısıyla
örtüşme raporu.

## Raporlanan (her kol, eğitim koşusu)

100 $ → bitiş, işlem, kazanma, R kaz./kayb., brüt, sürtünme (komisyon + funding), net, kriter 3.
Sıralama **net PnL'e göre**.

## Doğrulama (en iyi kol, bir kez — koşulmadan önce sabit)

En iyi kol (net PnL'e göre sıralamada 1.) doğrulama coinlerinde (`dogrulama_coinleri_2026-10-07.md`,
20 sembol) × **eğitim dönemiyle aynı takvim aralığı** bir kez koşulur. Geçme şartı: **net > 0 VE
kriter 3 GEÇTİ VE ≥ 12/20 kazanan sembol**. Sonuç ne çıkarsa çıksın raporlanır, tekrar koşulmaz,
eşik/kural geriye dönük değiştirilmez.

**Blokaj (`OPEN-69`):** `dogrulama_coinleri_2026-10-07.md`'ye göre bu 20 sembolün diskte hiç verisi
yok ve `DogrulamaKilidi` bu sembollerde her veri erişimini (disk + borsa çekimi) durduruyor; kilit
"o koşudan önce ayrı bir PR'la" açılır (STATUS 2026-10-07 kararı). Kilit açılsa da mevcut plan tek
çekim **2026-09-11 sonrası** içindi (eğitim dönemi değil) — eğitim takvim aralığı için bu 20
sembolde hiç geçmiş veri yok, borsadan yeniden (geçmişe dönük) çekilmesi gerekir. **Doğrulama adımı
bu yüzden kullanıcı onayı bekliyor** — aşağıda ayrıca soruluyor; eğitim koşuları (adım 2–4) bu
onayı beklemeden yapılır.

## Hesaplanan eşikler (2026-10-13, performans görülmeden)

`python -m scripts.suzgec_31 --esikler` (`logs/inceleme/ltf31_veri.pkl`, 20 sembol, eğitim dilimi):

- **S3 medyanı:** leg verimliliği, **13.067 zone** üzerinden (tüm zone popülasyonu, girilmiş olsun
  olmasın) → **medyan 0,5220**. 6.534 zone (≈ yarısı, tanıma göre) eşiğin altında veya eşit.
- **S2:** sembol başına eşik sabit bir sayı değil (girişin kendi günüyle kayan 30 günlük medyan);
  hesaplama `scripts/suzgec_31.py:vol_block_for`, girdi yalnızca o sembolün kendi hacim geçmişi.
