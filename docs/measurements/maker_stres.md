# `OPEN-36` — maker doluş stresi

**Tarih:** 2026-09-24 · **spec** v0.4 · **kod** 2153a63+kirli · betik
`scripts/maker_stres.py` · çıktı `logs/maker_stres.txt`

Taban **F1** (v1 varsayılanı, ekleme kapalı). Komisyon ve slippage sabit: borsa
oranları ve 2 bps. 20 sembol, ORDI dahil, verinin en eski %80'i. **Ayrılmış %20
okunmadı.**

**Model** (`Backtest._taker_mi`): taker'a düşen limit emri **aynı mumda** dolar; taker
komisyonu ve slippage öder. Dolum zamanlaması değişmez. Bu **iyimser** bir
varsayım: gerçekte kaçan emir de olur, burada hiçbir emir kaçmıyor. Rastgele kolda
düşme, (zone, emir türü) hash'iyle deterministik ve iç içe belirleniyor: %10'da düşen
her emir %25'te de düşüyor.

## (a) Rastgele düşme oranı

| düşme oranı | %0 | %10 | %25 | %50 | %100 |
|---|---:|---:|---:|---:|---:|
| **net PnL** | **+2.376** | +1.793 | +1.055 | **−69** | −1.904 |
| brüt / sürtünme | 1,535 | 1,374 | 1,202 | 0,993 | 0,744 |
| maks drawdown | %11,9 | %12,6 | %13,7 | %15,6 | %26,5 |
| kazanan sembol | 15/20 | 15/20 | 14/20 | 12/20 | 8/20 |

**Başabaş: limit emirlerin ~%48,5'i taker'a düştüğünde** (%25 ile %50 kolları
arasında doğrusal). Her %10'luk düşme neti yaklaşık 430 azaltıyor.

## (b) Koşullu düşme — 1m hacim vekili

> **Vekil.** Emrin önündeki defter kuyruğu bilinmiyor (defter verisi yok, `OPEN-32`).
> Kural: emir miktarı dolum mumunun 1m işlem hacminin `θ` oranını aşarsa emir taker'a
> düşer. Ölçülen şey kuyruk değil, **emrin mumun hacmine oranı**. Arkadaki
> varsayım: büyük bir emir sakin bir mumda pasif olarak dolmaz.

| θ | %0,1 | %0,5 | %1 | %5 | %10 | %25 |
|---|---:|---:|---:|---:|---:|---:|
| düşen / aday | %95,5 | %86,5 | %81,1 | %62,2 | %49,3 | %29,9 |
| **net PnL** | −1.750 | −1.463 | −1.251 | −472 | **+114** | +918 |
| brüt / sürtünme | 0,762 | 0,796 | 0,824 | 0,932 | 1,022 | 1,167 |
| maks drawdown | %25,2 | %23,0 | %21,2 | %16,9 | %16,3 | %14,9 |
| kazanan sembol | 8/20 | 8/20 | 9/20 | 10/20 | 12/20 | 15/20 |

**Asıl bulgu, düşen emir oranı.** Emirlerin **%30'u**, dolduğu dakikanın hacminin
**dörtte birinden büyük**. %49'u da o hacmin onda birini aşıyor. Limit emirler en
sakin mumlarda doluyor, çünkü fiyat seviyeye tam bu mumlarda değip dönüyor. Bu
dolumlar 10.000 başlangıç ve `K = 0,25` ile, yani ~2.500 notional'da bile büyük
kalıyor. Equity büyüdükçe oran daha da kötüleşir. Koşullu kol, rastgele kolla aynı
başabaş bölgesine düşüyor: %49 düşmede +114, rastgele %50'de −69.

## (c) Emir türüne göre

Her kolda yalnızca o türdeki emirlerin %100'ü taker'a düşüyor. Maliyet, %0 kolundan
net farkı olarak ölçüldü.

| tür | düşen emir | net farkı | emir başına | kalan net |
|---|---:|---:|---:|---:|
| **giriş** | 2.256 | **−3.278** | **−1,45** | **−902** |
| TP1 | 1.482 | −1.092 | −0,74 | +1.284 |
| nihai TP | 412 | −315 | −0,76 | +2.061 |

**En pahalı olan giriş**, hem toplamda hem emir başına. Tek başına neti negatife
çeviriyor. Nedenleri:

- Giriş, pozisyonun **tamamında** ödeniyor. TP1 yarıda, nihai TP kalan yarıda.
- Kötü giriş fiyatı, pozisyonun bütün çıkışlarına taşınıyor.
- Breakeven ötelemesi girişi maker oranıyla hesaplıyor (`R-EXIT-01`). Giriş taker'a
  düşünce öteleme 3 bps eksik kalıyor.
- Etki bileşik: equity düşünce sonraki pozisyonlar küçülüyor (`K × equity`). Brüt
  6.881'den 5.739'a iniyor. Kolun kendi komisyon ve slippage artışı (+2.133) net
  farkı tek başına açıklamıyor.

## Okuma

1. **F1'in kârı maker doluşa bağlı; slippage'a değil.** Slippage ×3 (`slippage.md`)
   neti +862'ye indiriyordu. Limit emirlerin yarısının taker'a düşmesi ise neti
   sıfırlıyor.
2. **Girişte maker kalmak kritik.** TP'lerin taker'a düşmesi neti pozitif bırakıyor,
   giriş düşünce net negatife geçiyor. Canlıda girişin post-only emir olması ve
   dolmazsa **kovalanmaması** kural adayı. İşlem kaçırmak, taker girişten ucuz. Bu,
   spec'te tanımsız.
3. **Emir boyutu mumun hacmine göre büyük.** 1m vekili kaba bir ölçü. Yine de
   dolumların üçte birinde emir, dakikanın hacminin dörtte birini aşıyor. Gerçek
   kuyruk defter verisiyle ölçülmeli (`OPEN-32` (b)). Kayıtçı 2026-09-24 16:00'dan beri
   20 sembolde çalışıyor.

## Açık kalan

- Kaçan emir modellenmedi. Burada düşen emir daima doluyor; gerçekte bir kısmı hiç
  dolmaz, bu da işlemin kendisini kaybettirir.
- Breakeven ötelemesi, düşen girişte gerçek oranı kullanmıyor (3 bps eksik).
