# Zaman dilimi ızgarası — ön kayıt (2026-10-07)

**Durum: yazıldı, koşulmadı.** Koşu, strateji inceleme etiketleri (`docs/inceleme/strateji/`)
geldikten sonra yapılır. Bu dosya koşudan önce sabitlenir; sonuç görüldükten sonra hücre, kural ya da
karar ölçütü değiştirilmez — değişirse tarihli not olarak eklenir.

## Soru

OTE zone'u ve onu destekleyen OB hangi zaman diliminde tespit edilmeli? #30 30m × 30m'de.

## Hücreler

Zaman dilimi merdiveni: **4h → 1h → 30m → 15m → 5m → 1m**. "Bir alt / iki alt" bu merdivende.

| # | OTE (zone) | OB desteği: aynı | bir alt | iki alt |
|---|---|---|---|---|
| 1–3 | 4h | 4h | 1h | 30m |
| 4–6 | 1h | 1h | 30m | 15m |
| 7–9 | 30m | **30m (= #30)** | 15m | 5m |
| 10–12 | 15m | 15m | 5m | 1m |

**Toplam 12 hücre.** 30m × 30m hücresi #30'un kendisidir → parite kapısı (aşağıda).

## Her hücrede sabit — #30'un kuralları

#30 kurgusu (`SONUCLAR.md` #30, spec v0.10, parmak izi `ddc097097a39ef92`): swing `B2` (ATR zigzag,
k = 2) + eşleştirme `son_supuren`; OB A1+B (ardışık hepsi geçersiz + yapı kırılımı, kendi diliminin
B2 swing'leriyle); giriş 0.70 (`ENTRY_070`) + OB kapısı (`require_indicator`, OB yalnızca destek, giriş
fiyatı değil); limit emirleri; ekleme kapalı (`max_adds = 0`, F1 tabanı); `reduce_once`; ADD-REJECT-E
%3; K = 0,25; 100 USDT; eğitim dilimi; aynı 20 sembol (`liquidity.json`); durum makinesi 1m'de;
4h yön (R-ZONE-10 bias) değişmez. **v0.11'in OB girişi, 5m/4h OB kaynakları ve 1-1 eklemesi yok.**

Hücreler arasında değişen yalnızca iki şey: zone'ların tespit dilimi ve OB kapısının dilimi. Swing
parametreleri (k = 2, ATR 14) her dilimde aynı — dilime göre ayar yok (CLAUDE.md: self-tuning yasak).

Zone dilimi 30m değilse: 1h ve 4h mumları 30m'den, 15m mumları 1m'den `loader.ornekle` ile
(UTC sınırlı, eksik kaynak mumu → açılış/kapanış `NaN`, v0.11 boşluk kuralı). OB dilimleri aynı
şekilde: 1h/4h ← 30m, 15m/5m ← 1m, 1m olduğu gibi. Her nesnenin `known_at`'i kendi diliminin
mum kapanışı (look-ahead yok).

## Parite kapısı

Önce 30m × 30m hücresi bugünkü kodla koşulur. **#30'un parmak izini (`ddc097097a39ef92`) birebir
vermezse ızgara koşulmaz**; fark (hangi işlemler, hangi kod değişikliği) raporlanır, kullanıcıya
sorulur. Gerekçe: v0.11 kodu (renk, emir ömrü, OB dizileri) v0.10 davranışını değiştirmiş olabilir;
ızgara "#30'un kuralları" iddiasını ancak bu kapıyla taşır.

## Raporlanan (her hücre)

100 $ → bitiş, işlem, işlem/sembol-ay, kazanma, R kaz./kayb., brüt, sürtünme (komisyon + funding),
net, kriter 3, maks DD, leg medyanı, zone sayısı, kapıdan geçen / temas eden zone, parmak izi.
Brüt farkı vs #30: sembol-ay eşleşik bootstrap (`scripts/bootstrap_fark.py`, 10.000, tohum
20261006). Komisyon, funding ve slippage hepsinde modelli.

## Karar ölçütü (öneri — kullanıcı onayı koşudan önce)

12 karşılaştırma var; birinin şansla iyi görünmesi beklenir. Öneri: bir hücre #30'un yerine ancak
**brüt farkı Bonferroni düzeltmeli %99,6 bootstrap aralığında sıfırı dışlarsa** aday olur
(%95 / 12). Aksi hâlde taban #30 kalır, tablo yalnızca açıklayıcıdır. Örneklem içidir;
aday hücre doğrulama coinlerinde (`dogrulama_coinleri_2026-10-07.md`) ayrıca sınanmadan taban olmaz.

## Gereken kod (koşudan önce, ayrı PR)

- `loader`: zone dilimi parametresi (şu an `DETECT_TF = "30m"` sabit; zone, FVG ve `watch_from`
  bundan). Bias 4h kalır.
- `ob_cerceveleri`: 1h, 15m, 1m kaynakları (şu an yalnızca 5m ← 1m, 4h ← 30m).
- Betik `scripts/izgara_tf.py`: `--hazirla` (zone dilimi başına bir veri paketi, OB dilimi başına
  tespit bir kez), `--hucre N` (ayrı süreç, `scripts.bg`), `--rapor`. `ltf_31.py` iskeleti.
- Testler: her yeni dilimde `known_at` = kendi mum kapanışı; 30m × 30m'de #30 paritesi.

## Süre tahmini

Ölçü #31 (bu makine, 16 çekirdek, 15,4 GB RAM): veri hazırlığı ~5 dk (20 sembol, OB 5m + 30m + 4h);
tek backtest ~10 dk (1m döngüsü, 489.087 mum — zone dilimi süreyi az değiştirir); paket ~440 MB.

| adım | tahmin |
|---|---|
| hazırlık: 4 zone dilimi + 6 OB dilimi (1m OB en pahalısı, ~10 M mum) | 20–30 dk |
| parite koşusu (30m × 30m) | ~10 dk |
| 11 hücre, 4'er paralel (RAM: süreç başı ~2–3 GB) → 3 dalga | 30–40 dk |
| rapor + 11 bootstrap | ~5 dk |
| **toplam koşu** | **~1–1,5 saat** |

Kod + testler ayrıca (yukarıdaki liste). Paralellik RAM'le sınırlı; 4h/1h hücrelerinde işlem az
olacağı için onlar daha kısa sürer.
