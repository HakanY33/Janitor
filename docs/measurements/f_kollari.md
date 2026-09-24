# F1 / F2 kolları — ekleme kapalı ve asgari leg eşiği

**Tarih:** 2026-09-24 · **spec** v0.4 · **kod** b5c68a0+kirli · betik `scripts/f_kollari.py`
· çıktı `logs/f_kollari.txt`

Taban **E3B** = E3 (`ADD-REJECT-E` `L = %3`) + breakeven ücret dahil (`OPEN-35` kapandı,
artık motor varsayılanı). 20 sembol, ORDI dahil, verinin en eski %80'i — **ayrılmış %20
okunmadı.**

| kol | tanım |
|---|---|
| E3B | referans |
| F1 | `max_adds = 0` — ekleme yok, dolayısıyla `R-ADD-04` küçültmesi de yok |
| F2 | E3B + asgari leg. Eşik E3B'nin **ilk yarısından** (kesim 2025-12-14 19:15 UTC) en küçük leg tertilinin üst sınırı: **%1,938**. Eşit ve altı zone giriş üretmez |

## Sonuç

| ölçü | E3B | **F1** | F2 | F1 ×1.5 |
|---|---:|---:|---:|---:|
| işlem | 2.237 | 2.251 | 1.418 | 2.254 |
| brüt fiyat PnL | 5.214 | **6.881** | 3.945 | 5.827 |
| komisyon | 4.494 | 3.729 | 3.116 | 4.990 |
| slippage | 817 | 754 | 553 | 1.020 |
| funding | 37 | 23 | 32 | 24 |
| **net PnL** | −134 | **+2.376** | +244 | −206 |
| brüt / sürtünme | 0,982 | **1,535** | 1,075 | 0,970 |
| maks drawdown | %23,7 | **%11,9** | %22,0 | %15,5 |
| iflas (<%50 / <%25 / <%10) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| kazanan sembol | 13/20 | **15/20** | 13/20 | 12/20 |

Sonuç dağılımı (nihai TP / TP1+breakeven / stop / TP1 sonrası stop):

| kol | nihai TP | TP1 + BE | stop | TP1 sonrası stop |
|---|---:|---:|---:|---:|
| E3B | 414 | 1.065 | 756 | 2 |
| F1 | 412 | 1.071 | 766 | 2 |
| F2 | 271 | 641 | 505 | 1 |
| F1 ×1.5 | 369 | 1.117 | 768 | 0 |

Komisyon, sonuç tipi başına toplam (pay):

| kol | nihai TP | TP1 + BE | stop |
|---|---:|---:|---:|
| E3B | 539 (%12,0) | 1.659 (%36,9) | 2.294 (**%51,0**) |
| F1 | 473 (%12,7) | 1.695 (%45,5) | 1.557 (%41,8) |
| F2 | 376 (%12,1) | 1.029 (%33,0) | 1.710 (**%54,9**) |

Yarı ayrımı (işlem PnL'i, girişe göre):

| kol | H1 net | H2 net | H2 kazanan |
|---|---:|---:|---:|
| E3B | +638 | −772 | 10/20 |
| **F1** | +1.686 | **+690** | 11/20 |
| F2 | +543 | −299 | 12/20 |

## Okuma

1. **Ekleme merdiveni net negatiftir.** F1 sonuç dağılımını neredeyse hiç değiştirmiyor
   (nihai TP 414 → 412, stop 756 → 766) ama brüt +1.668 artıyor ve komisyon −765
   düşüyor. Ekleme kazananı büyütmüyor, stopa giden pozisyonu büyütüyordu: stop başına
   komisyon 3,03 → 2,03, stop başına brüt kayıp −30,2 → −29,2. Maks DD yarıya iniyor.
2. **F1 iki yarıda da artıda** (+1.686 / +690). E3B ve F2'nin ikinci yarısı eksi.
3. **F2 kazancı hacim düşüşünden.** İşlem −%37, komisyon −%31 — ama brüt de −%24.
   İşlem başına brüt artıyor (nihai TP 41,7 → 55,3), stop başına kayıp da büyüyor
   (−30,2 → −39,4). Eşik ikinci yarıda E3B'yi düzeltiyor (−772 → −299) ama işareti
   çevirmiyor. Bu, `R-ZONE-08` ölçümündeki "leg etkisi sürtünmedir" bulgusuyla uyumlu.
4. **Dayanıklılık (kriter 2) geçilmedi.** F1 ×1.5: net +2.376 → **−206**, brüt/sürtünme
   1,535 → 0,970, kazanan 15/20 → 12/20. Maks DD yine E3B'nin altında (%15,5). Edge
   ilk kez sürtünmenin 1,5 katı ama maliyet varsayımı %50 kötüleşince başabaşın
   altına düşüyor. `OPEN-32` (gerçek slippage) hâlâ belirleyici.

Not: F1 ×1.5'te sonuç dağılımı değişiyor (TP1+BE 1.071 → 1.117) — breakeven ötelemesi
komisyon oranıyla ölçeklendiği için; beklenen davranış.

## Yapılmadı

- Ayrılmış %20 okunmadı.
- F1 + F2 birleşimi koşulmadı (istenmedi).
- `max_adds = 0` spec'e yazılmadı: `R-ADD-01/03` hâlâ eklemeyi tanımlıyor. Ekleme
  kuralının kaldırılması bir spec kararıdır.
