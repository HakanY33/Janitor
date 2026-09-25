# Breakeven komisyonu · komisyonun sonuç dağılımı · `R-ZONE-08` iç validasyon

**Koşu:** `python -m scripts.bg scripts.robustness` · 2026-09-24
**Çıktı:** `logs/robustness.txt` · `.csv` · `_sonuc.csv` · `_ozellik.csv` · `_islem.csv`
**Taban:** **E3** = D1 (`R-ENTRY-02` (3) kapalı · limit emri · TP tam seviyede ·
ekleme tavanı 3 · küçültme bir kez) + `ADD-REJECT-E` `L = %3`
**Yapılandırma:** 20 sembol (**sembol çıkarma yok, ORDI dahil**) · eğitim dilimi
(en eski %80) · `K=0.25` · `T_rahat=0.50` · `T_kritik=0.08` · MMR 0.005 ·
`terminate=none` · başlangıç 10.000 · spec v0.4 · kod `b5c68a0+kirli`
**Ayrılmış %20 hiçbir bölümde okunmadı.**

---

## (a) Breakeven komisyonu — `R-EXIT-01`

`R-EXIT-01` iki şey söylüyor: ilk TP'nin alt sınırı "işlem ücretlerini karşılayacak
kadar", ve "sonrasında stop maliyete çekilir". Kod bugüne kadar breakeven'ı **ham**
ortalama maliyete koydu. Orada kapanan yarının brütü **sıfırdır**: ödenen gidiş-dönüş
komisyonu net zarar kalır.

`E3B` kolu seviyeyi o komisyon kadar kâr tarafına öteler — limit kolunda maker giriş
2 bps + taker çıkış 5 bps = **7 bps**. Slippage kapsam dışı: yayınlanan bir oran
değil, varsayım (§8). Öteleme stopu **erken** tetikler, yani kâr yarısını küçültüp
stop yarısını büyütebilir; net etkinin işareti bu iki etkinin toplamıdır.

| ölçü | **E3** ham maliyet | **E3B** ötelenmiş | fark |
|---|---:|---:|---:|
| işlem | 2.221 | 2.237 | +16 |
| brüt fiyat PnL | 5.097,17 | 5.213,91 | **+116,74** |
| komisyon | 4.435,67 | 4.494,12 | +58,44 |
| slippage | 796,67 | 816,89 | +20,22 |
| funding | 41,30 | 36,98 | −4,32 |
| **net PnL** | **−176,47** | **−134,08** | **+42,39** |
| net getiri | −1,8% | −1,3% | |
| maks drawdown | 24,1% | **23,7%** | −0,4 pp |
| brüt / sürtünme | 0,967 | **0,975** | |

Kalemler her iki kolda gerçek PnL'e kapanıyor (fark ~1e-22).

**Sonuç dağılımı nasıl kaydı:**

| sonuç | E3 | E3B | fark |
|---|---:|---:|---:|
| TP1 + breakeven | 995 | 1.065 | **+70** |
| nihai TP | 463 | 414 | **−49** |
| stop | 754 | 756 | +2 |
| stop (TP1 sonrası) | 9 | 2 | −7 |

> Öteleme bedava değil: 49 işlem nihai TP'ye (+136,5 bps) gitmek yerine breakeven'da
> (+28,0 bps) kapandı. Buna rağmen net **+42,39** — çünkü breakeven'da kapanan 1.065
> işlemin her biri artık kendi komisyonunu ödemiyor. Kuyruk tarafında da iyileşme
> var: TP1'den sonra stopa giden işlem 9 → **2** (ötelenmiş stop, boşlukla stopa
> gitmeden önce tetikliyor) ve maks drawdown 24,1% → 23,7%.

**Ölçü bir karar vermiyor, bir okuma öneriyor.** +42,39 başlangıcın **%0,42**'si ve
`brüt/sürtünme` 0,97'den 0,97'ye gidiyor: sonucun işaretini değiştirmiyor. Kararın
değeri paradan değil, kuralın hangi okumasının doğru olduğundan gelir → `OPEN-35`.
Kod varsayılanı **değiştirilmedi** (`breakeven_fees=False`).

---

## (b) Komisyon nereye gidiyor

İşlem başına ortalamalar, `E3` kolu. `bps` tabanı **tepe notional** = tepe miktar ×
giriş fiyatı. Brüt burada işlem başına fiyat PnL'idir ve slippage dolum fiyatının
içindedir (işlem başına ayrıştırılamaz; kol toplamı (a)'da ayrı satırda).

| sonuç | işlem | pay | brüt | komisyon | net | komisyon bps | net bps | komisyon payı |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| TP1 + breakeven | 995 | 44,8% | 8,67 | 1,56 | +7,10 | 5,5 | +25,4 | 35,0% |
| **nihai TP** | 463 | 20,8% | **39,80** | **1,27** | **+38,53** | **4,0** | **+136,5** | 13,3% |
| **stop** | 754 | 33,9% | **−30,14** | **3,03** | **−33,21** | **6,8** | **−87,4** | **51,5%** |
| stop (TP1 sonrası) | 9 | 0,4% | −3,33 | 1,45 | −4,73 | 5,5 | −18,1 | 0,3% |
| tüm işlemler | 2.221 | 100% | 1,94 | 2,00 | −0,08 | | | 100% |

**Komisyon-negatif olan: iki stop tipi.** Brütleri negatif olduğu için bu tanım gereği
doğrudur ve tek başına bir şey söylemez. Söyleyen şey dağılımın kendisi:

- **Komisyon kaybedende yoğunlaşıyor.** İşlemlerin %33,9'u stopla kapanıyor ama
  komisyonun **%51,5'ini** o işlemler ödüyor. Stop başına komisyon 3,03 = **6,8 bps**;
  nihai TP başına 1,27 = **4,0 bps**. Kaybeden işlem, kazanandan **2,4 kat** komisyon
  ödüyor. Sebep ekleme: kaybeden pozisyon merdiveni tırmanıyor, her basamak komisyon
  yazıyor ve sonra hepsi birlikte stopa gidiyor.
- **Kâr eden hiçbir sonuç tipi komisyon-negatif değil.** TP1+breakeven brütü kendi
  komisyonunun 5,6 katı, nihai TP 31 katı. Yani sorun "kazananlar ücreti
  karşılayamıyor" değil; sorun kaybedenlerin ücret faturası.
- Nihai TP tek başına **+136,5 bps/işlem** getiriyor ve komisyonun yalnızca %13,3'ünü
  ödüyor. Model kâr üretiyor; onu ödeyen kalem stop tarafındaki ekleme komisyonu.

> Bu, `OPEN-34`'ün (boyutu risk tavanından türetme) tek satırlık gerekçesidir:
> komisyon notional'ın sabit bir oranı, ekleme merdiveni ise notional'ı kaybeden
> pozisyonda büyütüyor.

---

## (c) `R-ZONE-08` — bölünmüş iç validasyon

**Yöntem.** Eğitim dilimi zamanda ikiye bölündü (kesim işlem sayısını eşitleyen an:
**2025-12-14 16:25 UTC**; ilk yarı 1.110 işlem, ikinci yarı 1.111 işlem, her ikisinde
20 sembol). Her aday özellik için **işlem başına net bps** gruplandı. Tertil ve sembol
eşikleri **yalnızca ilk yarıdan** kesildi ve ikinci yarıda aynen kullanıldı — eşiğin
kendisi de modelin parçasıdır.

Ölçülen özellik: giriş dalı (OB/FVG) · 4h yapı bias uyumu (`R-ZONE-10`, **SMA vekili
değil**, HH+HL/LH+LL swing tanımı) · `touch_count` · leg büyüklüğü tertili · sembol
başına tick/leg oranı.

**Tutarlılık tanımı:** sembolün kendi `A − B` farkı havuzun işaretiyle aynı mı. Ölçülebilir
sembol = her iki grupta en az 5 işlem; ölçülemeyen sembol **tutarsız** sayıldı (kötümser
taraf). Net bps/işlem: ilk yarı **+12,11** · ikinci yarı **+8,06**.

### İlk yarı

| özellik | grup | işlem | net bps | karşıtlık | sembol tutarlılığı |
|---|---|---:|---:|---:|---:|
| giriş dalı | FVG / **OB** | 1.041 / 69 | +10,51 / **+36,13** | **+25,61** | 4/20 (ölçülebilir 6) |
| 4h bias | uyumlu / karşı / yön yok | 389 / 310 / 411 | +12,83 / +6,95 / +15,31 | +5,88 | 10/20 (19) |
| `touch_count` | 1 / 2+ | 1.071 / 39 | +12,95 / −11,04 | +23,99 | 1/20 (1) |
| leg tertili | alt / orta / **üst** | 371 / 370 / 369 | +2,09 / +0,73 / **+33,59** | **+31,50** | 13/20 (17) |
| tick/leg | yüksek / düşük | 556 / 554 | +9,76 / +14,46 | −4,70 | 12/20 (20) |

Kesimler: leg tertili alt ≤ %1,95 < orta ≤ %3,65 < üst · tick/leg sembol eşiği 0,00183.

### İkinci yarı (aynı eşikler)

| özellik | grup | işlem | net bps | karşıtlık | sembol tutarlılığı |
|---|---|---:|---:|---:|---:|
| giriş dalı | FVG / **OB** | 1.034 / 77 | +6,49 / **+29,17** | **+22,68** | 5/20 (ölçülebilir 7) |
| 4h bias | uyumlu / karşı / yön yok | 335 / 328 / 448 | +9,97 / +3,00 / +10,35 | +6,97 | 12/20 (20) |
| `touch_count` | 1 / 2+ | 1.044 / 67 | +7,51 / +16,70 | **−9,19** | 4/20 (6) |
| leg tertili | alt / orta / **üst** | 448 / 362 / 301 | −1,37 / −0,09 / **+31,92** | **+33,30** | 17/20 (19) |
| tick/leg | yüksek / düşük | 523 / 588 | +7,60 / +8,47 | −0,87 | 11/20 (20) |

### Dayanıklılık

Ölçüt: **iki yarıda da işaret aynı** ve **≥14/20 sembolde tutarlı**.

| özellik | H1 bps | H1 tut. | H2 bps | H2 tut. | işaret | dayanıklı |
|---|---:|---:|---:|---:|---|---|
| giriş dalı (OB − FVG) | +25,61 | 4/20 | +22,68 | 5/20 | aynı | hayır |
| 4h bias (uyumlu − karşı) | +5,88 | 10/20 | +6,97 | 12/20 | aynı | hayır |
| `touch_count` (1 − 2+) | +23,99 | 1/20 | −9,19 | 4/20 | **döndü** | hayır |
| **leg tertili (üst − alt)** | **+31,50** | 13/20 | **+33,30** | **17/20** | aynı | **hayır** (H1'de bir sembol eksik) |
| tick/leg (yüksek − düşük) | −4,70 | 12/20 | −0,87 | 11/20 | aynı | hayır (sembol seviyesi) |

**Eşiği geçen özellik yok.** Neden geçmediği özellik başına farklı ve fark önemli:

- **leg büyüklüğü — tek ciddi aday, bir sembol farkla kaçırdı.** İşaret iki yarıda da
  aynı ve büyük (+31,5 / +33,3 bps), ikinci yarıda 17/20 tutarlı; eşiği **ilk yarıdaki
  13/20** ile kaçırıyor. Gevşek okuma (yarılardan birinde ≥14/20) geçirir. Karar
  kullanıcıya bırakıldı; eşik ölçümden sonra değiştirilmedi.
- **giriş dalı (OB) — sinyal değil, örneklem sorunu.** İşaret iki yarıda da aynı ve
  etki en büyüklerden (+25,6 / +22,7 bps), ama OB girişleri akışın yalnızca %6'sı:
  20 sembolün yalnızca 6-7'sinde her iki grupta 5 işlem birikiyor. Ölçülebilenlerin
  4/6 ve 5/7'si hemfikir. Yani sonuç "tutarsız" değil, **ölçülemedi**.
- **4h bias uyumu — işaret sabit, etki küçük.** 19-20 sembolde ölçülebiliyor (en iyi
  ölçülen özellik) ve işaret iki yarıda da pozitif, ama etki +5,9 / +7,0 bps ve
  sembollerin ancak yarısı hemfikir. `OPEN-24`'ten kalan SMA vekili sorusu bununla
  **kapanıyor**: swing tabanlı `R-ZONE-10` yönü ölçülebilir ama zayıf bir ayrımdır.
- **`touch_count` — yapısı gereği ölçülemez.** İşlemlerin %94-96'sı `touch_count = 1`.
  Giriş zaten bandın **ilk** temasında silahlanıp dolduğu için ikinci temas ancak
  dolum kaçarsa oluşuyor. İşaret de döndü. Bu özellik bu giriş kuralıyla ölü.
- **tick/leg — etki eriyor.** −4,70 → −0,87 bps. "Yüksek tick sembolleri
  kaybettiriyor" tezinin sıra korelasyonu daha önce −0,18 ölçülmüştü
  (`docs/measurements/tp_placement.md`); bu ölçüm onu doğruluyor: işaret aynı ama
  büyüklük gürültü seviyesinde.

### Leg etkisi gerçek mi, metrik artefaktı mı

`net bps` tabanı notional olduğu için büyük leg **mekanik olarak** daha çok bps
taşır. Ayrıştırma (`logs/robustness_islem.csv`, aynı tertiller):

| yarı | tertil | brüt bps | komisyon bps | net bps | brüt R* | ekleme |
|---|---|---:|---:|---:|---:|---:|
| H1 | alt | 7,88 | 5,56 | +2,28 | 0,191 | 0,05 |
| H1 | üst | 39,24 | 5,52 | +33,47 | 0,228 | 0,24 |
| H2 | alt | 4,31 | 5,66 | −1,34 | 0,112 | 0,06 |
| H2 | üst | 37,37 | 5,63 | +31,92 | 0,180 | 0,35 |

\* `brüt R` = brüt bps / stop mesafesi; stop mesafesi ≈ 0,30 × leg (giriş 0,70, stop
1,0). Ekleme sonrası maliyet kayması ihmal edildi — yalnızca tanısal.

**Komisyon bps leg'den bağımsız: her tertilde 5,5-5,7 bps.** Fark tamamen brütte.
Ama riske göre normalize edildiğinde brüt fark +31/+33 bps'ten **+0,04 / +0,07 R**'ye
düşüyor, yani büyük leg'in *birim riske* düşen edge'i yalnızca bir tık daha iyi.
Sonuç dağılımı da tertiller arasında neredeyse aynı (stop payı %31,5 / %37,9 / %32,6):
büyük leg daha az stoplanmıyor.

> Okuma: **"büyük leg daha iyi" cümlesi bir edge cümlesi değil, bir sürtünme
> cümlesidir.** Komisyon notional'ın sabit bir oranı olduğu için küçük leg'in ödemesi
> onu tamamen yiyor (0,14 R vs 0,03 R); büyük leg aynı edge'i taşıyıp faturayı
> seyreltiyor. Buradan çıkan aday `R-ZONE-08` ağırlığı değil, **asgari leg büyüklüğü**
> eşiğidir — ve o bir giriş filtresi olur, sıralama değil. Ölçülmedi, uygulanmadı.

**Skor kurulmadı, filtre uygulanmadı, ayrılmış %20 okunmadı.** Bu bölüm `R-ZONE-08`
için girdi adaylığıdır, ağırlık değildir.
