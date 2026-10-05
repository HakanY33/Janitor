"""Yapı çıktısından zone üretimi — zone motorunun girdi tarafı.

Spec: R-ZONE-10 (leg seçimi), R-ZONE-02 (uç tespiti, merdiven), R-ZONE-01/03 (zone
nesnesi ve seviyeler), R-ZONE-09 (`WATCH_FROM`, tespit TF'si), §0 (bias).

`src/features/structure.py` swing listesini üretir; burada o listeden **leg** seçilir
ve leg'den `Zone` kurulur:

```
anchor_1 = likiditeyi süpüren swing        (swept=True — önceki aynı tip swing'i aştı)
anchor_0 = o hareketi başlatan karşı swing (R-ZONE-10)
```

Süpüren bir tepe (`HH`) `anchor_1` ise `anchor_0` bir dip olur: `0` altta, `1` üstte →
**SHORT** (§0 bias tablosu). Simetriği `LL` için LONG. Bias'ı `Zone.create` çapa
fiyatlarından türetir, burada tekrar hesaplanmaz.

**`anchor_0` adayları.** R-ZONE-10 "o hareketi başlatan bir önceki karşı yönlü swing"
diyor, R-ZONE-02 "birden fazla aday varsa likiditeyi süpüren seçilir" ve "bakılan
bölgedeki en yüksek/düşük noktalar" diyor. Uygulama sırası:

1. Aday penceresi = `anchor_1`'in aştığı swing ile `anchor_1` arasındaki karşı tip
   swing'ler — yani bu leg'i fiilen başlatabilecek olanlar.
2. Pencerede süpüren aday varsa yalnızca onlar değerlendirilir (R-ZONE-02).
3. Kalanlar arasından **en uçtaki** seçilir (tepe için en düşük dip): leg'in kökeni
   odur ve R-ZONE-02 "bölgedeki en düşük/yüksek nokta" diyor.
4. Pencere boşsa (araya giren dipler filtreye takılmışsa) `anchor_1`'den önceki son
   karşı tip swing'e düşülür; o da yoksa zone kurulmaz.

**Kalite skoru hesaplanmaz.** `R-ZONE-08` `TASARLANACAK` durumunda; merdiven sayımı ve
sıralama oraya aittir. Kod spec'te olmayan bir skor uydurmaz (CLAUDE.md).

**Yön filtresi yoktur.** `R-ZONE-07`'nin 4h yön kuralı işlem *süresi* hakkındadır,
zone oluşturma şartı değil. `R-ZONE-06` "uygun görülen her zone aday sayılır ve
izlemeye alınır" diyor — eleme giriş ve risk katmanlarının işi.
"""
from __future__ import annotations

import pandas as pd

from src.features.fvg import require_detect_tf
from src.features.structure import HIGH, LOW, Swing, detect_swings
from src.zones.model import HYSTERESIS, Zone


def _anchor_0(swings: list[Swing], i: int) -> Swing | None:
    """`swings[i]` süpüren swing iken leg'i başlatan karşı yönlü swing (R-ZONE-10)."""
    anchor_1 = swings[i]
    karsi = LOW if anchor_1.kind == HIGH else HIGH

    # Aştığı aynı tip swing: pencerenin sol ucu. Yoksa pencere tüm geçmiştir.
    sol = 0
    for j in range(i - 1, -1, -1):
        if swings[j].kind == anchor_1.kind:
            sol = j + 1
            break

    adaylar = [s for s in swings[sol:i] if s.kind == karsi]
    if not adaylar:  # araya giren karşı swing'ler filtreye takılmış — son bilinene düş
        adaylar = [s for s in swings[:i] if s.kind == karsi][-1:]
    if not adaylar:
        return None

    supuren = [s for s in adaylar if s.swept]
    adaylar = supuren or adaylar  # R-ZONE-02 · süpüren tercih edilir
    # R-ZONE-02 · bölgedeki uç nokta: tepe için en düşük dip, dip için en yüksek tepe.
    return min(adaylar, key=lambda s: s.price) if karsi == LOW else max(
        adaylar, key=lambda s: s.price
    )


def _anchor_0_son_supuren(swings: list[Swing], i: int) -> Swing | None:
    """R-ZONE-10 seçeneği `son_supuren` (kullanıcı kuralı 2026-10-05): `anchor_1`'den önceki,
    kendisi de likidite almış (`swept`) **son** karşı swing; pencere sınırı yok. Süpüren yoksa
    son karşı swing. v4 doğrulaması bekliyor; varsayılan `pencere`.
    """
    karsi = LOW if swings[i].kind == HIGH else HIGH
    adaylar = [s for s in swings[:i] if s.kind == karsi]
    return ([s for s in adaylar if s.swept] or adaylar or [None])[-1]


ANCHOR0 = {"pencere": _anchor_0, "son_supuren": _anchor_0_son_supuren}  # R-ZONE-10 seçenekleri
ESLESTIRME = "pencere"  # varsayılan; spec R-ZONE-10


def zones_from_swings(
    swings: list[Swing],
    symbol: str,
    timeframe: str,
    hysteresis: float = HYSTERESIS,
    eslestirme: str = ESLESTIRME,
) -> list[Zone]:
    """Süpüren her swing için bir zone. Sıra: `anchor_1` teyit zamanına göre artan.

    `eslestirme`: `anchor_0` kuralı, `ANCHOR0` anahtarı (R-ZONE-10 seçenek tablosu).
    """
    secici = ANCHOR0[eslestirme]
    out: list[Zone] = []
    gorulen: set[tuple] = set()

    for i, anchor_1 in enumerate(swings):
        if not anchor_1.swept:  # leg'in ucu likidite almış olmalı (R-ZONE-02)
            continue
        anchor_0 = secici(swings, i)
        if anchor_0 is None or anchor_0.price == anchor_1.price:
            continue

        kimlik = (anchor_0.ts, anchor_1.ts)
        if kimlik in gorulen:  # aynı leg iki kez zone üretmez
            continue
        gorulen.add(kimlik)

        out.append(
            Zone.create(
                symbol=symbol,
                timeframe=timeframe,
                anchor_0_price=anchor_0.price,
                anchor_0_time=anchor_0.ts,
                anchor_1_price=anchor_1.price,
                anchor_1_time=anchor_1.ts,
                # Zone, iki pivotu da teyitlenmeden bilinemez (R-ZONE-09).
                pivot_confirmed_at=max(
                    anchor_0.pivot_confirmed_at, anchor_1.pivot_confirmed_at
                ),
                hysteresis=hysteresis,
            )
        )
    return out


def _pencere(z: Zone, df: pd.DataFrame) -> pd.DataFrame:
    """`anchor_1` mumunun kapanışı → `watch_from` arasındaki HTF mumları (pivot teyidi)."""
    i0, i1 = df.ts.searchsorted([z.anchor_1_time + pd.Timedelta(z.timeframe), z.watch_from])
    return df.iloc[i0:i1]  # `ts` sıralı (`detect_swings` sözleşmesi); maske her zone'da O(n)


def pencerede_050(z: Zone, df: pd.DataFrame) -> bool:
    """OPEN-61 (kullanıcı kararı 2026-10-02) · teyit penceresinde `0.50`'ye ulaşıldı mı.

    Ulaşıldıysa zone doğrudan PRIMED başlar (`Zone.activate`). "Ulaştı" = temas ya da
    ötesi; `0`/`1` ihlali ayrıca `izleme_oncesi_oldu` ile elenir.
    """
    p = _pencere(z, df)
    if z.bias == "SHORT":
        return bool((p.low <= z.level_050).any())
    return bool((p.high >= z.level_050).any())


def izleme_oncesi_oldu(z: Zone, df: pd.DataFrame) -> bool:
    """R-ZONE-05 · `0` veya `1` çapasına izleme başlamadan ulaşıldı mı.

    Pencere `anchor_1` mumunun kapanışı → `watch_from` (pivot teyidi). O mumlar
    `watch_from`'da kapanmıştır: bilgi anında bilinir, look-ahead değil (CLAUDE.md #3).
    Eskiden pencere görülmüyordu ve sırası çoktan bozulmuş zone ACTIVE doğuyordu
    (inceleme #9, NEAR 2026-03-29: `0` teyit mumunda kırıldı, sonra işlem açıldı).
    "Ulaştı" = temas ya da ötesi (R-RISK-02 ölçütü). `1` fraktal teyidi gereği bu
    pencerede aşılamaz; simetri için yine bakılır.
    """
    p = _pencere(z, df)
    if z.bias == "SHORT":
        return bool((p.low <= z.anchor_0_price).any() or (p.high >= z.anchor_1_price).any())
    return bool((p.high >= z.anchor_0_price).any() or (p.low <= z.anchor_1_price).any())


def detect_zones(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    hysteresis: float = HYSTERESIS,
    eslestirme: str = ESLESTIRME,
) -> list[Zone]:
    """HTF mumlarından zone listesi: swing tespiti + leg seçimi + zone kurulumu.

    `df` **tespit** zaman dilimidir (R-ZONE-09: 5m ve üstü). Durum geçişleri ayrıdır
    ve 1m mumlarla beslenir — bu fonksiyon zone'u yalnızca kurar, ilerletmez.

    İzleme başlamadan çapası alınmış zone kurulmaz (`izleme_oncesi_oldu`, R-ZONE-05).
    Penceresinde `0.50`'ye ulaşılmış zone PRIMED başlar (`pencerede_050`, OPEN-61).
    """
    require_detect_tf(timeframe)
    zones = zones_from_swings(detect_swings(df, symbol, timeframe), symbol, timeframe, hysteresis,
                              eslestirme)
    zones = [z for z in zones if not izleme_oncesi_oldu(z, df)]
    for z in zones:
        z.pencere_050 = pencerede_050(z, df)
    return zones
