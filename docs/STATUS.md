# STATUS

Her oturumun **ilk** okuduğu dosya. Kısa tutulur. Oturum sonunda güncellenir.

**Son güncelleme:** 2026-09-24

---

## Şu an

**Görev:** `OPEN-35` kapandı (breakeven ücret dahil, `breakeven_fees=True` varsayılan,
spec `R-EXIT-01`). E3B üzerinde iki kol: **F1** ekleme kapalı, **F2** asgari leg eşiği.
Ölçüm: `docs/measurements/f_kollari.md`.

**Durum:** **F1 ilk kez net pozitif ve brüt/sürtünme > 1 — ama kriter 2 geçilmedi.**

| ölçü | E3B | **F1** | F2 | F1 ×1.5 |
|---|---:|---:|---:|---:|
| net PnL | −134 | **+2.376** | +244 | −206 |
| brüt / sürtünme | 0,982 | **1,535** | 1,075 | 0,970 |
| maks drawdown | %23,7 | **%11,9** | %22,0 | %15,5 |
| kazanan sembol | 13/20 | **15/20** | 13/20 | 12/20 |
| H2 net (örneklem dışı yarı) | −772 | **+690** | −299 | −584 |

Ekleme merdiveni sonuç dağılımını değiştirmiyor (nihai TP 414 → 412), yalnızca stopa
giden pozisyonu büyütüyordu. F2 eşiği (%1,938, ilk yarıdan) hacmi kesiyor, edge
üretmiyor.

**İlgili dosyalar:** `scripts/f_kollari.py` · `src/backtest/engine.py` (`max_adds`
artık `None` = sınırsız, `0` = ekleme yok · `min_leg_pct` · `breakeven_fees=True`) ·
`tests/test_levers.py` (F1/F2 + R-EXIT-01)

---

## Bildiklerimiz (kısa)

| Bulgu | Sonuç |
|---|---|
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

1. **`OPEN-32` — sürtünme varsayımını ölç.** F1 ×1.5 başabaşın altına düşüyor; işaret
   yine `slippage_bps` ve gerçek doluşa bağlı. `scripts/spread_logger.py` sunucuda.
2. **Ekleme kuralı kararı (spec).** F1 her eksende E3B'den iyi. `R-ADD-01..06`
   kaldırılsın mı / `max_adds = 0` spec'e yazılsın mı — kullanıcının çağrısı. Kod
   varsayılanı değişmedi (`max_adds=None`).
3. Sürtünme ölçülüp F1 ×1.5 dayanıklı çıkarsa → ayrılmış %20 (kriter 1).
4. Paper trading → sunucuda

**Uyarı:** Kriter 2 geçilmedi. Ayrılmış %20'ye henüz gidilmez.

## Açık maddeler

`OPEN-27` ekleme çarpanı hedefi (şu an `0.79`) · `OPEN-28` KRİTİK'te yarılama ·
`R-ZONE-08` aday sıralaması (adaylar ölçüldü, dayanıklı çıkan yok) · `ADD-REJECT-A` · `OPEN-31` `R-ENTRY-02` (3) kaldırılsın mı · `OPEN-32` doluş varsayımı spec'te tanımsız · `OPEN-34` boyutu risk tavanından türetme

---

## Harita

| Klasör | İçerik |
|---|---|
| `src/data/` | Toplama, doğrulama, Parquet |
| `src/features/` | `structure.py` swing/bias · `ob.py` · `fvg.py` · `candles.py` |
| `src/zones/` | `model.py` FSM · `store.py` SQLite · `detect.py` leg → zone |
| `src/strategy/` | `entry.py` `R-ENTRY-05` filtreleri |
| `src/backtest/` | `loader.py` sembol hazırlığı + önbellek · `engine.py` olay döngüsü · `portfolio.py` cross equity · `costs.py` kalem defteri |
| `scripts/` | `diagnose.py` · `sweep.py` · `entry_variants.py` · `terminate.py` · `reconcile.py` · `branches.py` · `levers.py` A/B/C/D · `tp_placement.py` D1-D4 TP yerleşimi · `add_reject_e.py` stop kaybı tavanı · `spread_logger.py` canlı emir defteri · `robustness.py` breakeven ücreti + komisyon dağılımı + `R-ZONE-08` iç validasyon · `f_kollari.py` F1/F2 · `bg.py` |
| `docs/measurements/` | Ölçüm tarihçeleri — spec'te yalnızca tek satırlık referans var |

Spec kuralı gerekiyorsa baştan okuma: `grep -n "R-ADD-04" docs/STRATEGY_SPEC.md`
Bir kuralın ölçümü gerekiyorsa: kuralın altındaki `Ölçüm:` satırını izle.

**Uzun koşu:** `python -m scripts.bg <modul>` — terminalden bağımsız, log `logs/`'a,
makineyi uyanık tutar. Doğrudan `python -m scripts.X` çalıştırma, terminal kapanınca ölür.
