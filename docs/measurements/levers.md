# Üç kaldıracın katkısı — salınım tavanı, limit emri, gösterge kapısı

**Koşu:** `python -m scripts.bg scripts.levers` · 2026-09-21
**Çıktı:** `logs/levers.txt` · `logs/levers.csv`
**Yapılandırma:** 20 sembol · eğitim dilimi (en eski %80, ayrılmış %20 okunmadı) ·
`K=0.25` · `T_rahat=0.50` · `T_kritik=0.08` · UYARI eklemeyi engellemez · MMR 0.005 ·
`terminate=none` · başlangıç bakiye 10.000 · spec v0.4 · kod `b5c68a0+kirli`

Kollar **kümülatiftir**: her kol bir öncekinin üzerine tek bir değişiklik koyar.

| kol | üzerine koyduğu |
|---|---|
| A | mevcut hâl (referans) |
| B | pozisyon ömrü boyunca en fazla 3 ekleme; küçültme pozisyon başına bir kez, yeniden kurulmaz |
| C | limit emri fiyatlaması: giriş/TP1/TP/ekleme/küçültme maker + sıfır slippage, 1 tick aşım kuralı |
| D | `R-ENTRY-02` (3) kapalı: yalnızca OB ve FVG girişleri |

Üçü de **spec'te yoktur** ve kod varsayılanları kapalıdır. Ölçülen şey birer spec
adayıdır, seçim değil.

---

## Sonuç

| ölçü | A | B | C | D |
|---|---:|---:|---:|---:|
| işlem sayısı | 7.413 | 5.360 | 7.414 | 2.208 |
| **brüt fiyat PnL** (slippage'siz) | **+1.073** | **+475** | **−3.661** | **−264** |
| komisyon | 7.822 | 7.365 | 5.003 | 4.184 |
| slippage | 3.129 | 2.946 | 913 | 733 |
| funding | 96 | 110 | 242 | 36 |
| **net PnL** | **−9.974** | **−9.947** | **−9.819** | **−5.218** |
| net getiri | −99,7% | −99,5% | −98,2% | **−52,2%** |
| maks drawdown | 99,8% | 99,6% | 98,2% | 63,6% |
| likidasyon | 0 | 0 | 0 | 0 |
| dolmayan limit | 0 | 0 | 7.097 | 1.451 |

Her kolda kalemler kapanıyor (uzlaştırma farkı ~1e-23, `Decimal` bölme artığı).

### Marjinal katkı

| kaldıraç | Δ net PnL | Δ komisyon | Δ slippage | Δ işlem | Δ maxDD |
|---|---:|---:|---:|---:|---:|
| A → B · ekleme tavanı + tek küçültme | **+27** | −457 | −183 | −2.053 | −0,2 p.p. |
| B → C · limit emri | **+128** | −2.363 | −2.033 | +2.054 | −1,4 p.p. |
| C → D · gösterge kapısı | **+4.601** | −819 | −180 | −5.206 | −34,6 p.p. |

---

## Okuma

### 1. Sürtünmeyi düşürmek tek başına hiçbir şey kurtarmıyor

B ve C **sürtünmeyi gerçekten düşürüyor** — birlikte komisyonun %36'sını ve
slippage'in %71'ini siliyorlar (7.822 → 5.003 · 3.129 → 913). Buna rağmen net
PnL 10.000'lik hesapta yalnızca **155** iyileşiyor. Neden: her iki kol da aynı
miktarda **brüt fiyat PnL'i de siliyor.**

```
A → B :  sürtünme −640   ·  brüt fiyat PnL −599   →  net +27
B → C : sürtünme −4.396  ·  brüt fiyat PnL −4.135 →  net +128
```

Bu bir tesadüf değil, ölçümün asıl bulgusu: kaybı taşıyan işlemler kârı da taşıyor.
Salınımı kısmak ve maker'a geçmek maliyeti ödeyen işlem hacmini kısıyor; aynı hacim
brüt edge'in de kaynağı.

### 2. Brüt edge, TP'lerin **temasla** dolduğu varsayımına bağlıydı

En sert bulgu bu. `A` kolunda brüt fiyat PnL'i **+1.073** (STATUS'taki +%10,7).
`C` kolunda aynı geometri, aynı veri, tek fark "limit emri seviyeyi 1 tick geçmeden
dolmuş sayılmaz": brüt fiyat PnL'i **−3.661**.

Kaçırılan doluşlar sayıldı: **2.501 bar** boyunca açık bir TP limiti seviyeye
dokunuldu ama 1 tick aşılmadı; **3.775 bar** boyunca giriş limiti aynı şekilde
kaçtı. TP'ye değip dönen fiyat eski modelde kâr yazıyordu; bu modelde pozisyon
açık kalıyor ve çoğu stopa ya da maliyete gidiyor. Komisyon kalemi de bunu
doğruluyor: stop komisyonu 892 → 1.643, breakeven komisyonu 316 → 639.

**Sonuç:** şimdiye kadar ölçülen pozitif brüt edge (+%10,7 ve dal bazında
OB +34,5 bps / FVG +5,0 bps) **sıra önceliği varsayımının ürünü.** Muhafazakâr
doluş kuralıyla o edge yok.

### 3. Tek gerçek kaldıraç seçicilik

`D` net PnL'i 4.601 iyileştiriyor — diğer ikisinin toplamının 30 katı — ve asıl
önemlisi hesabı **canlı tutuyor**:

| iflas eşiği | A | B | C | **D** |
|---|---:|---:|---:|---:|
| equity < başlangıcın %50'si | 93,9% | 94,4% | 84,2% | **23,6%** |
| equity < başlangıcın %25'i | 86,0% | 86,7% | 46,3% | **0,0%** |
| equity < başlangıcın %10'u | 77,7% | 77,3% | 39,7% | **0,0%** |

A/B/C kollarında hesap barların %78–94'ünde ölü; o tablolarda okunan her fark ölü
hesap üzerinde. `D` bunu kırıyor: işlem sayısı 7.414 → 2.208 ve hesap hiçbir barda
başlangıcın %25'inin altına inmiyor.

Yine de `D` **kârlı değil**: net −%52,2 ve brüt fiyat PnL'i −264. Yani gösterge
kapısı ölümü durduruyor, edge üretmiyor.

### 4. 1 tick kuralı sembole göre çok farklı bağlıyor

Borsadan çekilen fiyat adımı (`data/bingx/fees.json`, `scripts.funding --fees-only`):

| sembol | tick bps | | sembol | tick bps |
|---|---:|---|---|---:|
| GALA | 5,78 | | XRP | 0,72 |
| JUP | 4,24 | | BNB | 0,14 |
| NEAR | 4,14 | | SOL | 0,10 |
| CRV | 2,86 | | ETH | 0,04 |
| **medyan** | **1,27** | | BTC | 0,01 |

Maker-taker farkı 3 bps, slippage varsayımı 2 bps. BTC/ETH'te kural neredeyse hiç
bağlamıyor ve `C`'nin kazancı tamamen komisyondan geliyor; GALA/JUP/NEAR'da tick tek
başına maker kazancının üstünde ve doluşları gerçekten kaçırtıyor. Koşu bu iki rejimi
tek sayıda topluyor — sembol bazında ayrıştırma yapılmadı.

---

## Uyarılar

1. **Kollar ayrı koşulardır.** Maliyet equity'yi, equity boyutu (`R-ENTRY-03`), boyut
   risk bölgesini (`R-RISK-05`) değiştirir. İşlem kümeleri birebir tutmaz; satırlar
   birbirinden çıkarılmaz, yan yana okunur. `B`'nin işlem sayısının 2.053 düşmesi ve
   `C`'de 2.054 artması bu yoldan gelir, kuralların kendisinden değil.
2. **`C` kolu iki şeyi birden değiştiriyor.** Doluş kuralına ek olarak eklemenin dolum
   fiyatı da değişiyor: eskiden mumun kapanışı, şimdi OB'nin ilk dokunulan kenarı.
   Brüt fiyat PnL'indeki −4.135'in tamamı tick kuralına atfedilemez. Ayrıştırmak için
   üçüncü bir kol gerekir (yalnızca maker fiyatlama, temas doluşu korunarak).
3. **`add_reject_cap` bir bar sayacıdır**, olay sayacı değil: tavana takılmış bir
   pozisyon uygun bir OB'ye dokunduğu her mumda bir kez sayılır. 102.385 sayısı
   "102.385 ekleme reddedildi" demek değildir.
4. **Ayrılmış %20 hiçbir kolda okunmadı.**
5. Tüm kollar ölü ya da ölmekte olan hesapta ölçüldü (`D` hariç). `D` üzerine
   kurulacak yeni ölçümler `A`'nın değil `D`'nin taban alınmasını gerektirir.

---

## Açtığı sorular

| aday | soru |
|---|---|
| `OPEN-31` | `R-ENTRY-02` (3) kaldırılsın mı? `D` hesabı canlı tutuyor ama edge üretmiyor. Karar ancak `D` tabanlı bir edge ölçümünden sonra verilebilir. |
| `OPEN-32` | Doluş varsayımı spec'e yazılmalı. Bugün kod "temas = dolum" diyor ve ölçülen edge'in tamamı oradan geliyor. `1 tick aşım` mı, `spread kadar aşım` mı, sıra modeli mi — `scripts/spread_logger.py` verisi biriktikçe seçilir. |
| — | `B` ve `C` ölçüldü ve **hiçbiri tek başına kurtarmıyor**; `OPEN-31` adayı olarak tuttuğumuz "küçültmeden koşmak" sorusu bu koşuyla daralıyor: salınımı kısmak brüt edge'i de kısıyor. |
