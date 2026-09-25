# `ADD-REJECT-E` — pozisyon seviyesinde stop kaybı tavanı (`L`)

**Koşu:** `python -m scripts.bg scripts.add_reject_e` · 2026-09-21
**Çıktı:** `logs/add_reject_e.txt` · `.csv` · `_sembol.csv` · `logs/are_e10.txt` (E10 stresi)
**Taban:** **D1** (`docs/measurements/tp_placement.md`) — `R-ENTRY-02` (3) kapalı ·
limit emri · TP tam seviyede · ekleme tavanı 3 · küçültme bir kez
**Yapılandırma:** 20 sembol (**sembol çıkarma yok, ORDI dahil**) · eğitim dilimi
(en eski %80) · `K=0.25` · `T_rahat=0.50` · `T_kritik=0.08` · MMR 0.005 ·
`terminate=none` · başlangıç 10.000 · spec v0.4 · kod `b5c68a0+kirli`

## Kural

```
ekleme sonrası toplam notional × |stop(1) − ortalama maliyet| / ortalama maliyet
        >  L × equity        →  ekleme reddedilir
```

Sol taraf pozisyonun nihai stopa giderse **realize olacak kaybıdır**. Notional
`miktar × maliyet` olduğu için `miktar × |stop − maliyet|`e sadeleşir. **Aynı kısıt
ilk girişe de uygulanır.**

Kuralın gerekçesi `docs/measurements/tp_placement.md`: `R-ADD-03` çarpan merdiveni
çarpımsal (iki ekleme `×4` sonra `×6` = girişin **24 katı**), `R-RISK-01` notional
tavanı equity de düştüğü için hiç bağlamıyor, tek pozisyon hesabın toplam kaybından
fazlasını taşıdı.

---

## Sonuç

| ölçü | **E0** kapalı | **E10** %10 | **E5** %5 | **E3** %3 | E3 ×1.5 maliyet |
|---|---:|---:|---:|---:|---:|
| işlem | 2.208 | 2.211 | 2.217 | 2.221 | 2.221 |
| **brüt fiyat PnL** | **−264** | **+4.894** | **+4.494** | **+5.097** | +4.609 |
| komisyon | 4.184 | 4.298 | 4.403 | 4.436 | 5.874 |
| slippage | 733 | 749 | 776 | 797 | 1.054 |
| funding | 36 | 34 | 42 | 41 | 42 |
| **net PnL** | **−5.218** | **−186** | −727 | **−176** | −2.361 |
| net getiri | −52,2% | −1,9% | −7,3% | **−1,8%** | −23,6% |
| **maks drawdown** | **63,6%** | 27,6% | 26,5% | **24,1%** | 30,7% |
| iflas <%50 | 23,6% | 0,0% | 0,0% | 0,0% | 0,0% |
| kazanan sembol | 10/20 | 12/20 | 12/20 | **13/20** | 8/20 |
| ekleme | 344 | 342 | 337 | 327 | 327 |
| red — ekleme (bar) | 0 | 61 | 229 | 1.103 | 1.103 |
| red — giriş | 0 | 0 | 1 | 2 | 2 |

Her kolda kalemler gerçek PnL'e kapanıyor (fark ~1e-22).

> `red (ekleme, bar)` bir **bar** sayacıdır: reddedilen ekleme OB'yi tüketmez, aynı
> OB'ye dokunulan her mumda yeniden denenir ve yeniden sayılır. Olay sayısı değildir.

### En kötü 5 işlem

| kol | 1. | 2. | 3. | 4. | 5. |
|---|---|---|---|---|---|
| **E0** | **ORDI −4.766** (24,0× · 3 ekleme) | DOGE −554 (11,0×) | RUNE −487 (16,0×) | CRV −484 (16,0×) | CRV −302 (22,0×) |
| E10 | DOGE −554 (11,0×) | ORDI −506 (2,0×) | RUNE −487 (16,0×) | CRV −484 (16,0×) | CRV −302 (22,0×) |
| E5 | RUNE −487 (16,0×) | CRV −484 (16,0×) | ORDI −427 (1,0×) | CRV −322 (22,0×) | INJ −282 (11,0×) |
| **E3** | CRV −331 (22,0×) | CRV −297 (8,0×) | UNI −290 (4,0×) | INJ −286 (11,0×) | UNI −282 (6,0×) |

E0'ın en kötü işlemi tek başına net kaybın **%91,3'ü**. `E3`'te en kötü işlem −331 —
**14 kat küçük.** Kural tam hedeflediği şeyi kesiyor.

---

## Okuma

### 1. Kural hesabı kurtarıyor: brüt −264 → +5.097

En sert rakam bu. `E0`'da brüt fiyat PnL'i **negatif** (−264): ölçülen "edge" yok.
Kural açılınca brüt **+4.500 ile +5.100 arasına** çıkıyor — başlangıç sermayesinin
yarısı kadar. Tek bir kural bunu nasıl yapıyor:

Katastrofik pozisyonlar yalnızca kendi kayıplarını yazmıyor, **hesabı küçültüyor**.
`R-ENTRY-03` boyutu `K × equity` olarak tanımladığı için equity düşünce sonraki her
pozisyon küçülüyor; hesap barların %23,6'sında başlangıcın yarısının altında geçiyor
ve o dönemdeki kazançlar da küçük tabanla ölçülüyor. 24×'lik tek bir pozisyonu
kesmek, ardından gelen **iki bin işlemin** boyutunu düzeltiyor.

Maks drawdown %63,6 → %24,1 ve iflas metriği %23,6 → **%0**.

### 2. `L`'nin değeri net PnL'den seçilemez — kuyruk riskinden seçilir

Net PnL üç adayda ayırt edilemiyor ve **sıralama monoton bile değil**:

```
L = %10  →  −186        L = %5  →  −727        L = %3  →  −176
```

10.000'lik hesapta −176 ile −186 arasındaki fark gürültüdür; `%5`'in ikisinden de
kötü çıkması bunun yol bağımlılığı olduğunu kanıtlar. **Net PnL'e göre seçim yapmak
bu veride overfit olurdu** (CLAUDE.md: otomatik parametre optimizasyonu yasak).

Maks drawdown ise `L`'de **monoton**:

| | kapalı | %10 | %5 | %3 |
|---|---:|---:|---:|---:|
| maks drawdown | 63,6% | 27,6% | 26,5% | **24,1%** |
| ×1.5 maliyet stresinde | — | 39,8% | — | **30,7%** |
| kazanan sembol | 10/20 | 12/20 | 12/20 | **13/20** |

Bu ilişki mekanik ve beklenen: daha sıkı tavan → daha küçük kuyruk. Seçim bu metrikte
yapıldı, çünkü kuralın **var olma nedeni** kuyruk riski.

**Seçilen: `L = %3`.** Sıkılaştırmanın brüt edge'e maliyeti yok (5.097 > 4.894), ekleme
sayısı yalnızca 344 → 327 düşüyor, drawdown her iki maliyet rejiminde de en düşük.

### 3. Giriş tarafı neredeyse hiç bağlamıyor

`L = %3`'te **1.103 ekleme-bar'ı** reddedilirken yalnızca **2 giriş** reddedildi.
Sebep geometrik: girişin stop kaybı `K × 0.30 × (leg / fiyat)`; `K = 0.25` ve tipik
leg fiyatın birkaç yüzdesi olduğu için bu ~%0,1–1 civarında kalıyor. Kural pratikte
bir **ekleme freni**; girişe uygulanması bir emniyet kemeri, bağlayıcı kısıt değil.
Yine de yazılı kuralın parçası — aşırı geniş legli bir zone'da bağlar.

### 4. Validasyon kriteri 2 (maliyet ×1.5): **geçilmedi**

| | E3 | E3 ×1.5 | E10 | E10 ×1.5 |
|---|---:|---:|---:|---:|
| net PnL | −176 | **−2.361** | −186 | **−2.365** |
| net getiri | −1,8% | −23,6% | −1,9% | −23,7% |
| maks drawdown | 24,1% | 30,7% | 27,6% | 39,8% |
| kazanan sembol | 13/20 | 8/20 | 12/20 | 7/20 |

İşaret korunmuyor — zaten negatifti, ama ×1.5'te **on üç kat** daha negatif oluyor.
Neden görünür: brüt ile sürtünme neredeyse tam olarak eşit.

| kol | brüt | sürtünme (komisyon + slippage) | brüt / sürtünme |
|---|---:|---:|---:|
| E0 | −264 | 4.917 | **−0,05** |
| E10 | 4.894 | 5.047 | 0,97 |
| E5 | 4.494 | 5.179 | 0,87 |
| E3 | 5.097 | 5.232 | **0,97** |
| E3 ×1.5 | 4.609 | 6.928 | 0,67 |

**Model artık gerçek bir brüt edge üretiyor ve o edge sürtünmenin %97'sini karşılıyor.**
Başabaşın hemen altında duruyor; maliyet varsayımı %50 kötüleşince sonuç çöküyor.
Yani sonuç maliyet varsayımına **dayanıklı değil** ve bu varsayımın kendisi hâlâ
ölçülmemiş bir parametre (`slippage_bps = 2`, `OPEN-32`).

### 5. Sembol tablosu artık dengeli

`E0`'da ORDI −5.539 ile net kaybın %106'sıydı. `E3`'te ORDI −970; en ağır sembol
çıkarıldığında hesap **+794**. Kazanan sembol 10/20 → 13/20, medyan sembol PnL'i
+4 → **+79**.

---

## Uyarılar

1. **Kollar ayrı koşulardır.** Tavan equity yolunu, equity boyutu (`R-ENTRY-03`),
   boyut risk bölgesini (`R-RISK-05`) değiştirir; işlem kümeleri birebir tutmaz.
2. **`%3` test edilen en sıkı değerdir** — aralığın kenarı. Daha düşük değerler
   denenmedi ve ızgara taranmadı (CLAUDE.md: self-tuning yasak). Daha sıkıya inmek
   ancak kuyruk riski gerekçesiyle ve yeni bir ölçümle yapılabilir, net PnL'le değil.
3. `red (ekleme, bar)` olay değil **bar** sayacıdır (yukarıdaki not).
4. **Kriter 1 (ayrılmış %20) okunmadı** ve bu koşu onu geçtiğini iddia etmiyor.
   Kriter 2 geçilmedi; ayrılmış dilime gitmek için henüz erken.
5. Test paketi `ADD-REJECT-E`'yi kapatır (`tests/conftest.py`): sentetik zone
   geometrisi (leg = fiyatın %59'u) hiçbir makul `L`'de pozisyon açtırmaz. Kuralın
   kendi testleri `L`'yi açıkça verir.

---

## Açtığı sorular

| aday | soru |
|---|---|
| `OPEN-32` | **Doluş ve slippage varsayımı artık tek belirleyici.** Brüt/sürtünme = 0,97; sonucun işareti tamamen `slippage_bps` ve komisyon varsayımına bağlı. `scripts/spread_logger.py` verisi birikmeden ileri gidilemez. |
| `OPEN-34` | `K = 0.25` sabit. `ADD-REJECT-E` risk tavanını pozisyon başına koyuyor; boyutu doğrudan risk tavanından türetmek (`K` yerine "stopta %L riske at") aynı kuralın doğal devamı ve sürtünmeyi düşürebilir. Ölçülmedi. |
| — | `OPEN-33` **kapandı**: `ADD-REJECT-E`, `L = %3` (`R-ADD-02`). |
