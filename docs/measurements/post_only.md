# `OPEN-37` — post-only giriş

**Tarih:** 2026-09-25 · **spec** v0.4 · **kod** 75518a4+kirli · betik
`scripts/post_only.py` · çıktı `logs/post_only.txt`, `logs/post_only.csv`

Taban **F1**. 20 sembol, ORDI dahil, verinin en eski %80'i. **Ayrılmış %20 okunmadı.**
Komisyon borsa oranında, slippage 2 bps.

**Model.** Giriş emri post-only: hiçbir zaman taker'a düşmez. Dolmazsa seviyede bekler,
kovalanmaz. Zone biterse giriş **kaçar** (`kacan_giris`: hedefe dokunuldu ama emir
dolmadı). TP1 ve nihai TP değişmedi: 1 tick aşım, maker. Doluş kriteri yalnızca giriş
için değişiyor (`Backtest.entry_fill`):

| kol | giriş dolar, eğer |
|---|---|
| **P1** | seviye 1 tick geçildiyse (mevcut) |
| **P2** | seviye 2 tick geçildiyse |
| **P3** | seviye 1 tick geçildiyse **ve** mum seviyenin ötesinde kapandıysa. Aynı mumda geri dönen mum doldurmaz |
| **TG** | P1 + girişin %100'ü taker'a düşer (`OPEN-36` (c)) — karşılaştırma tabanı |

## Sonuçlar

| ölçü | P1 | P2 | P3 | TG |
|---|---:|---:|---:|---:|
| **net PnL** | **+2.376** | +1.574 | **−1.744** | −902 |
| brüt fiyat PnL | 6.881 | 5.917 | 1.764 | 5.739 |
| komisyon + slippage | 4.483 | 4.321 | 3.473 | 6.616 |
| brüt / sürtünme | 1,535 | 1,369 | 0,508 | 0,867 |
| işlem | 2.251 | 2.230 | 2.156 | 2.254 |
| kaçan giriş | 31 | 56 | 137 | 31 |
| maks drawdown | %11,9 | %14,8 | %26,9 | %18,6 |
| kazanan sembol | 15/20 | 12/20 | 7/20 | 9/20 |
| H1 net | +1.697 | +1.495 | −1.150 | −22 |
| **H2 net** | +679 | +79 | −594 | −879 |
| nihai TP | 412 | 404 | 359 | 388 |
| TP1 + breakeven | 1.071 | 1.042 | 963 | 1.096 |
| stop | 766 | 782 | 830 | 768 |
| stop (TP1 sonrası) | 2 | 2 | 3 | 2 |

Yarı kesimi, P1'in medyan giriş zamanı (2025-12-14 14:34 UTC). Kesim bütün kollarda
aynı. Bu ölçümde hiçbir parametre veriden seçilmedi. H1/H2, işlem PnL'i toplamıdır.
Cross marjinde iki yarı bağımsız değildir.

## (c) Post-only mu, girişin taker'a düşmesi mi?

| kol | net | TG'ye göre | P1'e göre ek kaçan | ek kaçan başına |
|---|---:|---:|---:|---:|
| P1 | +2.376 | **+3.278** | — | — |
| P2 | +1.574 | **+2.476** | 25 | −32 |
| P3 | −1.744 | **−842** | 106 | −39 |

**P1 ve P2'de post-only, taker'a düşmekten ucuz. P3'te değil.**

- Taker'a düşmenin maliyeti emir başına **−1,45**. Kaçan bir girişin maliyeti ise P1'e
  göre **−32 ile −39**. Yani kaçan bir giriş, taker'a düşen bir girişten ~25 kat pahalı.
  Post-only'nin avantajı tamamen **kaçanın az olmasından** geliyor: P1'de 31, P2'de 56.
- **P3 ters seçilimi gösteriyor.** 95 işlem kaybetmek brütü 6.881'den 1.764'e düşürüyor.
  Seviyeyi delip aynı mumda geri dönen mum, OTE dönüşünün ta kendisi. Modelin en iyi
  girişleri bu mumlarda. Bu mumda dolmayan emir, işlemi ya tamamen kaçırıyor ya da
  fiyat seviyenin ötesinde kapandığında, yani dönüş başarısız olduğunda doluyor
  (stop 766 → 830, nihai TP 412 → 359).
- "Ek kaçan başına" sütunu yalnızca bir üst sınır okumasıdır. P2 ve P3 sadece giriş
  kaçırmıyor, girişi **geciktirip** daha kötü mumlara da kaydırıyor. Fark bu ikisinin
  toplamı.
- TG, P1 ile aynı doluş kümesidir: taker yalnızca maliyeti değiştirir. Kaçan girişleri
  kovalayıp doldurmaz. "Dolmazsa kovala" kolu bu ölçümde yok.

## Okuma

Post-only'nin sonucu, **dönüş mumunda kuyrukta ne kadar önde olunduğuna** bağlı.
Seviyeyi 1–2 tick delip dönen mumda emir doluyorsa (P1/P2) post-only doğru seçim.
Kuyruğun arkasında kalıyor ve yalnızca fiyat seviyeyi geçip orada kaldığında doluyorsa
(P3), F1 negatife dönüyor ve taker'a düşmekten de kötü. Gerçek davranış bu ikisinin
arasında. Hangisine yakın olduğu yalnızca defter verisiyle ölçülebilir (`OPEN-32`,
`scripts/spread_logger.py`).
