# TP yerleşimi — `R-EXIT-01` / `R-EXIT-02` tam seviyede mi, önce mi

**Koşu:** `python -m scripts.bg scripts.tp_placement` · 2026-09-21
**Çıktı:** `logs/tp_placement.txt` · `logs/tp_placement.csv` · `logs/tp_placement_sembol.csv`
**Taban:** **D** (`docs/measurements/levers.md`) — `R-ENTRY-02` (3) kapalı · limit emri ·
ekleme tavanı 3 · küçültme bir kez
**Yapılandırma:** 20 sembol · eğitim dilimi (en eski %80) · `K=0.25` · `T_rahat=0.50` ·
`T_kritik=0.08` · UYARI eklemeyi engellemez · MMR 0.005 · `terminate=none` ·
başlangıç 10.000 · spec v0.4 · kod `b5c68a0+kirli`

**Tek değişken TP yerleşimi.** Giriş, ekleme, küçültme ve stop dört kolda da aynıdır.

| kol | TP |
|---|---|
| D1 | tam seviyede, 1 tick aşım kuralı (referans) |
| D2 | seviyenin **0.02 leg** önünde |
| D3 | seviyenin **0.05 leg** önünde |
| D4 | temasla tetiklenen **piyasa emri** (taker + slippage, aşım aranmaz) |

Öteleme fib oranında yapılır (`0.50 → 0.50 + offset`, `0 → 0 + offset`); fiyatta
SHORT'ta yukarı, LONG'da aşağı — ikisi de **erken çıkıştır**. `D2`/`D3` spec'ten sapar
(`R-EXIT-01/02` tam seviye der, `SETTLED`); ölçülen bir spec adayıdır, seçim değil.

---

## Sonuç — D1 kazanıyor, öteleme de piyasa emri de kötüleştiriyor

| ölçü | **D1** | D2 (0.02) | D3 (0.05) | D4 (piyasa) |
|---|---:|---:|---:|---:|
| işlem | 2.208 | 2.220 | 2.261 | 2.207 |
| brüt fiyat PnL | −264 | −510 | −670 | **+306** |
| komisyon | 4.184 | 4.088 | 3.950 | 4.671 |
| slippage | 733 | 714 | 685 | 1.138 |
| funding | 36 | 32 | 26 | 36 |
| **net PnL** | **−5.218** | −5.343 | −5.331 | −5.539 |
| net getiri | **−52,2%** | −53,4% | −53,3% | −55,4% |
| maks drawdown | 63,6% | 63,0% | 64,5% | 64,0% |
| TP1'e ulaşan | 65,9% | 67,7% | **71,1%** | 66,7% |
| nihai TP ile kapanan | 21,0% | 20,8% | 19,2% | 21,0% |
| stop ile kapanan | 34,5% | 32,6% | **29,1%** | 33,6% |
| breakeven ile kapanan | 44,6% | 46,6% | 51,7% | 45,4% |
| dolmayan TP limiti (bar) | 553 | 453 | 452 | **0** |

D1'e göre fark:

| kol | Δ net | Δ brüt | Δ komisyon | Δ TP1 oranı | Δ stop oranı |
|---|---:|---:|---:|---:|---:|
| D2 | −126 | −245 | −97 | +1,8 p.p. | −1,9 p.p. |
| D3 | −113 | −406 | −234 | +5,3 p.p. | −5,4 p.p. |
| D4 | −321 | **+570** | +487 | +0,8 p.p. | −0,8 p.p. |

Her kolda kalemler gerçek PnL'e kapanıyor (fark ~1e-23).

---

## Okuma

### 1. Öteleme mekanik olarak çalışıyor, para kazandırmıyor

`D3` istenen her şeyi yapıyor: TP1'e ulaşan işlem %65,9 → **%71,1**, stopla kapanan
%34,5 → **%29,1**, dolmayan TP limiti 553 → 452, komisyon 234 düşüyor. Buna rağmen
net **−113 daha kötü.**

Nedeni brüt fiyat PnL'inde: −264 → **−670**. Erken çıkmak iki şey birden yapıyor —
kaçan TP'lerin bir kısmını kurtarıyor ve **zaten dolacak olan TP'leri daha kötü
fiyattan dolduruyor.** İkincisi birinciyi yiyor: kurtarılan işlem sayısı az (TP1
oranında +5,3 p.p.), fiyat kaybı ise **her** TP'de ödeniyor.

0.02 ile 0.05 arasında net fark yok (−126 vs −113); yani bu bir "doğru öteleme
miktarı" arama problemi değil, yönün kendisi yanlış. Daha fazla ızgara denemesi
yapılmadı — optimizasyon yasak (CLAUDE.md).

### 2. `D4` hayalet edge'in fiyatını tam olarak ölçüyor

`levers.md`'nin bulgusu buydu: ölçülen brüt edge, TP'lerin temasla dolduğu
varsayımından geliyordu. `D4` o varsayımı geri getiriyor ve sonuç birebir görünüyor:

```
brüt fiyat PnL   −264  →  +306   (+570)   ← temas doluşunun "kazandırdığı"
komisyon        4.184  → 4.671   (+487)   ← tp1 340→832, tp_nihai 109→264 (taker)
slippage          733  → 1.138   (+405)   ← TP'ler artık piyasa emri
                                  ------
net                              −321
```

Yani temas doluşunun değeri **+570**, gerçekten piyasa emriyle uygulamanın maliyeti
**892**. Hayalet edge sadece gerçek değil, faturası kesilince **negatif**. Bu, doluş
varsayımının bir modelleme detayı değil, ölçülen edge'in kaynağı olduğunu doğruluyor.

### 3. Kayıp yüksek-tick sembollerde değil — **tek bir işlemde**

Soru "kayıp GALA/JUP/NEAR gibi yüksek-tick sembollerde mi yoğunlaşıyor" idi.
**Hayır.** Fiyat adımı ile net PnL arasında sıra korelasyonu `D1`'de **−0,18**,
diğer kollarda −0,14 / −0,04 — ilişki yok. En yüksek tick'li sembol NEAR (6,44 bps)
ikinci **en kârlı** sembol (+595); GALA (2,46 bps) +209; JUP (4,71 bps) −4.

Gerçek tablo:

| kol | toplam net | en ağır sembol | payı | o sembolsüz | kazanan sembol |
|---|---:|---|---:|---:|---:|
| D1 | −5.218 | **ORDI** | **106,2%** | **+322** | 10/20 |
| D2 | −5.343 | ORDI | 103,5% | +188 | 9/20 |
| D3 | −5.331 | ORDI | 92,9% | −380 | 11/20 |
| D4 | −5.539 | ORDI | 95,3% | −262 | 9/20 |

**ORDI tek başına hesabın tüm kaybından fazlasını taşıyor.** Çıkarılınca `D1` net
**+322'ye** dönüyor — yani 19 sembolde model artıda.

"Yüksek tick yarısı −6.248, düşük tick yarısı +1.031" tablosu bu yüzden yanıltıcı:
ORDI o yarıda ve −5.539'u tek başına o taşıyor. ORDI çıkarıldığında yüksek-tick
yarısı −709'a iniyor ve dilimler arası fark bir aykırı değer hikâyesi hâline geliyor.

### 4. ORDI'yi bitiren şey ekleme merdiveni

ORDI tek başına koşuldu (cross paylaşımı yok, gösterge amaçlı): 129 işlem, net −5.589.

| ölçü | değer |
|---|---|
| kazanan işlem | 71/129 · medyan **+2,73** |
| **en kötü tek işlem** | **−4.792** — ORDI kaybının %86'sı, hesabın toplam kaybının ~%92'si |
| en kötü 5 işlem | net'in %94,2'si |
| tepe/giriş notional | ortalama 1,55× · **maks 24,0×** |
| MAE (equity %) | medyan %0,1 · p90 %0,5 · **maks %86,6** |
| taşıma | medyan 0,0 gün · maks 8,2 gün |

Model ORDI'de de **kazanıyor** — 129 işlemin 71'i artıda, medyan pozitif. Hesabı
bitiren tek bir pozisyon: `R-ADD-03` çarpan merdiveni (1-1, 1-3, 1-5, 1-10)
**çarpımsaldır**, iki ekleme `×4` sonra `×6` ile girişin **24 katına** çıkarıyor,
pozisyon equity'nin %86,6'sı kadar aleyhte sapıyor ve stopa gidiyor.

`max_adds = 3` tavanı bunu **engellemiyor**: tavan ekleme *sayısını* sınırlıyor,
*boyutu* değil. İki ekleme 24× yapmaya yetiyor.

---

## Uyarılar

1. **Kollar ayrı koşulardır.** TP yerleşimi equity yolunu, equity boyutu
   (`R-ENTRY-03`), boyut risk bölgesini (`R-RISK-05`) değiştirir. İşlem kümeleri
   birebir tutmaz; satırlar birbirinden çıkarılmaz.
2. **ORDI teşhisi ayrı bir koşudur** (tek sembol, cross marjin paylaşımı yok).
   20 sembollü koşudaki ORDI dilimi −5.539, tek başına −5.589; tablo aynı ama
   rakamlar birebir değil.
3. `tp_offset` **her iki TP'ye** birden uygulandı (kısmi ve nihai). Yalnızca birine
   uygulamak ölçülmedi.
4. `D2`/`D3` yalnızca iki öteleme değerinde ölçüldü. Izgara taranmadı — bulunan şey
   "yön yanlış", "doğru değer şu" değil.
5. **Ayrılmış %20 hiçbir kolda okunmadı.**

---

## Açtığı sorular

| aday | soru |
|---|---|
| `OPEN-33` | **Ekleme merdiveni boyut tavanı.** `R-ADD-03` çarpanları çarpımsal; iki ekleme 24× üretebiliyor. `R-RISK-01` (10 × equity) bunu bağlamıyor çünkü equity de düşüyor. Tavan *sayıda* değil *notional*'da olmalı — ama bu spec'te yok. Sıradaki ölçüm bu. |
| `OPEN-32` | Doluş varsayımı — `D4` bunun fiyatını ölçtü (+570 brüt, 892 maliyet). `scripts/spread_logger.py` verisi birikince `1 tick` yerine ölçülen kural gelir. |
| — | `R-EXIT-01/02` **değişmiyor**: TP tam seviyede kalır (`tp_offset = 0`). Öteleme ölçüldü ve her iki değerde de kötü. |
