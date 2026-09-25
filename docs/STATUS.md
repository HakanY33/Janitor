# STATUS

Her oturumun **ilk** okuduğu dosya. Kısa tutulur. Oturum sonunda güncellenir.

**Son güncelleme:** 2026-09-25 (akşam)

---

## Şu an

**Görev:** Sembol soğuk testi + kriter 2'nin yeniden tanımı · sunucuda günlük `earliest` timer.
Ölçüm: `docs/measurements/soguk.md` · `docs/measurements/earliest.md`.

**Durum:** F1 soğuk 20 sembolde ayakta. Yeni kriter 2 iki kümede de geçiyor. Orijinalde
kıl payı geçiyor, yarılar da tutarsız.

| | ORİJ F1 | YENİ F1 | ORİJ K2-yeni | YENİ K2-yeni | ORİJ K2-eski | YENİ K2-eski |
|---|---:|---:|---:|---:|---:|---:|
| net | +2.376 | +4.187 | +157 | +1.021 | −206 | +1.443 |
| brüt/sürtünme | 1,535 | 1,920 | 1,033 | 1,200 | 0,970 | 1,242 |
| H1 / H2 | +1.697 / +679 | +1.157 / +3.030 | +780 / −623 | +19 / +1.001 | +389 / −595 | −58 / +1.502 |

- Kriter 2 yeniden tanımlandı: komisyon kesin · slippage ×3 · giriş P2. Koşudan **önce**
  spec'e yazıldı (§8 Kabul kriterleri). Eşik net > 0. Bağlayıcı küme → `OPEN-39`.
- **30m penceresi kayıyor** (günde 1 gün, 30.239 mum sabit). 1m kaymıyor. Soğuk küme bu
  yüzden takvimle kesildi (2026-05-08 13:00), oranla değil.

**Sunucu:** `janitor-spread-logger` (sürekli) + `janitor-earliest.timer` (her gün
03:00 UTC, 1m + 30m, 20 sembol). İkisi de `janitor` kullanıcı servisi.

**İlgili dosyalar:** `scripts/soguk.py` · `scripts/earliest.py` · `scripts/pull_book.py` ·
`data/bingx/liquidity_soguk.json` · `tests/test_soguk.py` · `docs/SERVER.md`

---

## Bildiklerimiz (kısa)

| Bulgu | Sonuç |
|---|---|
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

1. **`OPEN-39`:** yeni kriter 2'de hangi küme bağlayıcı? İkisi de geçiyor. Karar, kriter
   1'e (ayrılmış %20) gidilip gidilmeyeceğini belirler.
2. Görev Zamanlayıcı'ya `pull_book`'u kaydet (`docs/SERVER.md`).
3. `NON_CRYPTO` filtresi yalnızca `NCCO`'yu eliyor. NCSI/NCFX/NCSK de kripto dışı ama
   bir sonraki `rank`'e sızabilir.
4. 30m günlük artımlı toplama: pencere kaydığı için yerelde olmayan geçmiş her gün
   bir gün kısalıyor.
5. `OPEN-38` kapsam kararı (gerçek doluş ölçümü).

**Uyarı:** Yeni kriter 2 geçildi ama `OPEN-39` açık. Ayrılmış %20'ye kullanıcı kararı olmadan gidilmez.

## Açık maddeler

`OPEN-27` ekleme çarpanı hedefi (şu an `0.79`) · `OPEN-28` KRİTİK'te yarılama ·
`R-ZONE-08` aday sıralaması (adaylar ölçüldü, dayanıklı çıkan yok) · `ADD-REJECT-A` · `OPEN-31` `R-ENTRY-02` (3) kaldırılsın mı · `OPEN-32` doluş varsayımı spec'te tanımsız · `OPEN-34` boyutu risk tavanından türetme · `OPEN-36` maker doluş oranı · `OPEN-37` post-only giriş · `OPEN-38` gerçek doluş ölçümü · `OPEN-39` kriter 2 bağlayıcı küme

---

## Harita

| Klasör | İçerik |
|---|---|
| `src/data/` | Toplama, doğrulama, Parquet |
| `src/features/` | `structure.py` swing/bias · `ob.py` · `fvg.py` · `candles.py` |
| `src/zones/` | `model.py` FSM · `store.py` SQLite · `detect.py` leg → zone |
| `src/strategy/` | `entry.py` `R-ENTRY-05` filtreleri |
| `src/backtest/` | `loader.py` sembol hazırlığı + önbellek · `engine.py` olay döngüsü · `portfolio.py` cross equity · `costs.py` kalem defteri |
| `scripts/` | `diagnose.py` · `sweep.py` · `entry_variants.py` · `terminate.py` · `reconcile.py` · `branches.py` · `levers.py` A/B/C/D · `tp_placement.py` D1-D4 TP yerleşimi · `add_reject_e.py` stop kaybı tavanı · `spread_logger.py` canlı emir defteri · `robustness.py` breakeven ücreti + komisyon dağılımı + `R-ZONE-08` iç validasyon · `f_kollari.py` F1/F2 · `slippage_stres.py` OPEN-32 (d) · `maker_stres.py` OPEN-36 · `post_only.py` OPEN-37 · `bg.py` |
| `docs/measurements/` | Ölçüm tarihçeleri — spec'te yalnızca tek satırlık referans var |

Spec kuralı gerekiyorsa baştan okuma: `grep -n "R-ADD-04" docs/STRATEGY_SPEC.md`
Bir kuralın ölçümü gerekiyorsa: kuralın altındaki `Ölçüm:` satırını izle.

**Uzun koşu:** `python -m scripts.bg <modul>` — terminalden bağımsız, log `logs/`'a,
makineyi uyanık tutar. Doğrudan `python -m scripts.X` çalıştırma, terminal kapanınca ölür.
