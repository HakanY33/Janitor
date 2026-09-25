# Ölçüm · Zone çözünürlüğü

Kural metni: `docs/STRATEGY_SPEC.md` — `R-ZONE-01`, `R-ZONE-09`, `R-ZONE-10`.
Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır.

---

## `touch_count` — histerezisin etkisi (`R-ZONE-01`)

**Ölçüm (NEAR §0 referans zone'u):** 30m = 3 · 1m histerezissiz = 13 · 1m histerezis 0.25 = **8**

> 30m sayısı doğru cevap değil, farklı çözünürlükte bir ölçüm. 30m'de bir "temas", yarım
> saatlik mumun aralığının bandı kesmesidir; fiyat o mum içinde üç kez girip çıksa bile
> tek sayılır. Kalibrasyon çapası 30m değil, **elle etiketlenmiş gözlem** olacak.
> Sabit `R-ZONE-08` tasarlanırken etiketli veriyle ayarlanır; o zamana kadar hem ham hem
> histerezisli sayı kaydedilir.

## 1m temas tespiti neden gerekli (`R-ZONE-09`)

**Ölçüm (NEAR, 2026-09):** aynı zone 30m yerine 1m ile beslendiğinde giriş teması
**25 dakika önce** yakalanıyor. Kazanç daha iyi fiyat değil — seviye aynı. Kazanç
**kaçırılmayan giriş**: 30m'de fiyat bant içine girip mum kapanmadan çıkarsa temas hiç
görünmez.

## Bias vekili geçersiz (`R-ZONE-10`)

Önceki ölçümlerde kullanılan "4h kapanış > 20 SMA" vekili **geçersizdir**.
`docs/measurements/hypotheses.md` tablosundaki "4h+ yön uyumu" satırı bu uyarıyla okunmalı.

**Swing tabanlı tanımla yeniden ölçüldü** (HH+HL → `UP`, LH+LL → `DOWN`, karışık →
`NONE`; `docs/measurements/robustness.md` (c)): giriş anında bilinen yön pozisyonla
uyumluysa işlem başına net **+12,8 bps**, karşıysa **+7,0** (ilk yarı); ikinci yarıda
+10,0 / +3,0. Karşıtlık **+5,9 → +7,0 bps**, işaret iki yarıda da aynı ama sembol
tutarlılığı yalnızca 10/20 → 12/20.

> Yön işlemlerin %37-40'ında `NONE` (yapı karışık) ve o grup **en iyisini** yapıyor
> (+15,3 / +10,4 bps). Yani "yön uyumu" ölçülebilir ama zayıf bir ayrımdır; bir kapı
> olarak kullanılması bu ölçümle desteklenmiyor.
