# `OPEN-32` — slippage ölçümü ve stres testi

**Tarih:** 2026-09-24 · **spec** v0.4 · **kod** 3319b0d+kirli · betik
`scripts/slippage_stres.py` · çıktı `logs/slippage_stres.txt`

Taban **F1** (E3B + ekleme kapalı, v1 varsayılanı). 20 sembol, ORDI dahil, verinin en
eski %80'i. **Ayrılmış %20 okunmadı.**

## (a)–(c) Ölçülen slippage — **yapılamadı, veri yok**

`scripts/spread_logger.py` kaydı:

| sembol | dakika | aralık |
|---|---:|---|
| BTC-USDT-USDT | 2 | 2026-09-21 10:42 → 10:43 |
| ETH-USDT-USDT | 2 | 2026-09-21 10:42 → 10:43 |

Bu, kayıtçının duman testinden kalan kayıt. Süreç şu an çalışmıyor. Hareket
tertillerine göre spread (a), emir yürüme maliyeti (b) ve ölçülen slippage ile
yeniden koşu (c) en az birkaç haftalık, 20 sembollük kayıt gerektiriyor. Özellikle
(a)'nın üst tertili, yani stopların tetiklendiği büyük 1m hareketler, seyrek görülür.
Kayıtçı sunucuda başlatılmadan bu kısım ilerlemez.

## (d) Stres — komisyon sabit, slippage ×1 / ×2 / ×3

Komisyon borsadan gelir ve kesindir; yalnızca slippage ölçeklendi. Limit dolumları
slippage ödemez, bu yüzden ölçek yalnızca piyasa emirlerine uygulanır: stop,
breakeven ve zorunlu çıkışlar.

| ölçü | ×1 (2 bps) | ×2 (4 bps) | ×3 (6 bps) |
|---|---:|---:|---:|
| işlem | 2.251 | 2.251 | 2.251 |
| brüt fiyat PnL | 6.881 | 6.681 | 6.488 |
| komisyon | 3.729 | 3.606 | 3.488 |
| slippage | 754 | 1.457 | 2.114 |
| funding | 23 | 24 | 24 |
| **net PnL** | **+2.376** | **+1.595** | **+862** |
| brüt / sürtünme | 1,535 | 1,320 | 1,158 |
| maks drawdown | %11,9 | %13,1 | %14,4 |
| kazanan sembol | 15/20 | 15/20 | 12/20 |

Doğrusal tahmine göre net PnL **~8,3 bps** slippage'da (×4,15) sıfıra iniyor. Adım
başına düşüş ~760 civarında ve ×3'e kadar doğrusal gidiyor; tahmin tutarlı.

## Okuma

1. **Slippage ×3'te bile F1 artıda.** Net +862, brüt/sürtünme 1,16.
2. **×1.5 testini (`f_kollari.md`) çökerten komisyondu, slippage değil.** O test ikisini
   birlikte ölçekliyordu: net −206. Burada slippage tek başına ×3'te +862 veriyor.
   Komisyon borsadan kesin geldiği için belirsiz değil; yine de ×1.5 komisyon,
   tier/VIP değişimi ya da limit emrin taker'a düşmesi gibi durumların vekili
   sayılabilir. Asıl kırılgan varsayım **maker doluşu**: limit emrinin 1 tick aşımla
   dolduğu ve maker ücreti ödediği varsayımı (`OPEN-32`'nin doluş yarısı).
3. **Kazanan sembol ×3'te 15 → 12'ye düşüyor.** Sonuç birkaç sembolde yoğunlaşıyor.
   Hangi sembollerin düştüğü, (a)–(b) verisi geldiğinde sembol bazında yeniden
   okunmalı.

## Açık kalan

- (a)–(c): kayıtçı sunucuda çalışsın. Veri biriktikten sonra bu dosya güncellenecek.
- Maker doluş varsayımının stresi (limit emirlerin bir kısmının taker'a düşmesi)
  koşulmadı; istenmedi.
