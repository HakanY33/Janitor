"""Piyasa yapısı: swing tespiti, HH/HL/LH/LL etiketleme, BoS ve yön (bias).

Spec: R-ZONE-10 (yapı), R-ZONE-02 (uç tespiti, merdiven), R-ZONE-07 (yön 4h+),
R-ZONE-09 (tespit 5m ve üstü, `pivot_confirmed_at`).

R-ZONE-10 üçünü tek ilkelden türetir: **swing noktası tespiti**. Yön, leg ve likidite
ayrı problem değil, aynı swing listesinin farklı okumalarıdır.

**Swing tespiti.** Fraktal pivot `N = 2` (5 mumluk yapı): `high[i]` kendinden önceki ve
sonraki iki mumun high'ından büyükse `i` bir swing high'tır. Buna `MIN_DISPLACEMENT ×
ATR(14)` yer değiştirme filtresi eklenir — yeni pivot, **son kabul edilen** swing'den
en az bu kadar uzaklaşmamışsa gürültüdür ve kabul edilmez.

Look-ahead (CLAUDE.md #3): bir pivot ancak `N` mum sonra teyitlenir. `ts` pivotun kendi
zamanı, `pivot_confirmed_at` ise **bilinebilir olduğu** andır; ikisi ayrı alandır ve
`R-ZONE-09` `WATCH_FROM` ikincisini kullanır. Kabul listesi **yalnızca büyür**: kabul
edilmiş bir swing sonradan silinmez veya değiştirilmez. Bu, "geçmişi yeniden yazma"
riskini tanım gereği kaldırır ve `test_R_ZONE_10_no_lookahead` bunu ölçer — veriyi
herhangi bir noktadan kesmek, o ana kadar teyitlenmiş swing'leri değiştirmemelidir.

**Ardışık aynı tip swing serbesttir.** Güçlü trendde araya giren dip filtreye takılıp
elenebilir; kalan iki tepe yine HH/LH olarak etiketlenir. Alternatif olan "aynı tipte
daha uçtaki ile değiştir" kuralı kabul edilmiş bir swing'i geriye dönük değiştirirdi.

**İki ölçüm tercihi** (spec ölçütü vermiyor, en muhafazakâr yorum seçildi ve raporlandı):

- *ATR(14)* Wilder yumuşatmasıdır (özgün tanım), basit ortalama değil.
- *Yer değiştirme filtresi* son kabul edilen swing'e göre ölçülür, tipi ne olursa olsun.
  Böylece filtre klasik zigzag eşiğiyle aynı anlama gelir ve tek yönde ilerler.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from src.features.fvg import require_detect_tf

FRACTAL_N = 2  # R-ZONE-10 · 5 mumluk yapı
ATR_PERIOD = 14  # R-ZONE-10
MIN_DISPLACEMENT = 0.5  # R-ZONE-10 · × ATR(14)

HIGH = "HIGH"
LOW = "LOW"

UP = "UP"
DOWN = "DOWN"
NONE = "NONE"

BIAS_TF = "4h"  # R-ZONE-07 · yön 4h ve üstünde hesaplanır


@dataclass
class Swing:
    """Kabul edilmiş bir swing noktası.

    `label` önceki **aynı tip** swing'e göredir (R-ZONE-10); ilk swing'de `None`.
    `swept`, bu swing'in önceki aynı tip swing'i aşmış olmasıdır — `R-ZONE-10`'un
    likidite tanımı ve `R-ZONE-02`'nin "kendinden önceki likiditeyi almış" şartı.
    """

    swing_id: str
    symbol: str
    timeframe: str
    kind: str  # HIGH | LOW
    price: float
    ts: datetime  # pivotun kendi mumu
    pivot_confirmed_at: datetime  # N mum sonra — bilinebilir olduğu an (R-ZONE-09)
    label: str | None = None  # HH | HL | LH | LL
    swept: bool = False  # önceki aynı tip swing'i aştı (BoS)


def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Wilder ATR. Nedensel: `i` konumundaki değer yalnızca `i` ve öncesini kullanır."""
    prev_close = df.close.shift(1)
    tr = pd.concat(
        [df.high - df.low, (df.high - prev_close).abs(), (df.low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _raw_pivots(df: pd.DataFrame, n: int) -> list[tuple[int, str, float]]:
    """Fraktal pivotlar, mum sırasına göre. Teyit `i + n`'de olur.

    Katı eşitsizlik: düz bir tepe (eşit high'lar) pivot sayılmaz — eşitlikte iki komşu
    aynı anda pivot olurdu ve hangisinin uç olduğu tanımsız kalırdı.
    """
    high, low = df.high.to_numpy(), df.low.to_numpy()
    out = []
    for i in range(n, len(df) - n):
        pencere = slice(i - n, i + n + 1)
        if high[i] == high[pencere].max() and (high[pencere] == high[i]).sum() == 1:
            out.append((i, HIGH, float(high[i])))
        elif low[i] == low[pencere].min() and (low[pencere] == low[i]).sum() == 1:
            out.append((i, LOW, float(low[i])))
    return out


def detect_swings(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    n: int = FRACTAL_N,
    min_displacement: float = MIN_DISPLACEMENT,
    atr_period: int = ATR_PERIOD,
) -> list[Swing]:
    """R-ZONE-10 · swing listesi: tespit, yer değiştirme filtresi, etiketleme, BoS.

    `df`: ts, open, high, low, close, volume — `ts` sıralı ve mumlar kapanmış.
    Dönen liste `pivot_confirmed_at`'e göre artan sıradadır (= pivot sırası).
    """
    require_detect_tf(timeframe)  # R-ZONE-09 · 1m yapı tespiti için kullanılmaz
    a = atr(df, atr_period).to_numpy()
    ts = df.ts.to_numpy()
    kabul: list[Swing] = []
    son_ayni: dict[str, Swing] = {}  # tip -> en son kabul edilen o tipteki swing

    for i, kind, price in _raw_pivots(df, n):
        teyit = i + n  # pivot ancak bu mum kapanınca bilinir (R-ZONE-09)
        if kabul:
            esik = min_displacement * a[teyit]
            # ATR tanımsızken (ilk `atr_period` mum) karşılaştırma False → pivot elenir.
            if not (abs(price - kabul[-1].price) >= esik):
                continue

        onceki = son_ayni.get(kind)
        if onceki is None:
            label, swept = None, False
        elif kind == HIGH:
            swept = price > onceki.price
            label = "HH" if swept else "LH"
        else:
            swept = price < onceki.price
            label = "LL" if swept else "HL"

        s = Swing(
            swing_id=uuid.uuid4().hex,
            symbol=symbol,
            timeframe=timeframe,
            kind=kind,
            price=price,
            ts=pd.Timestamp(ts[i]),
            pivot_confirmed_at=pd.Timestamp(ts[teyit]),
            label=label,
            swept=swept,
        )
        kabul.append(s)
        son_ayni[kind] = s
    return kabul


def bias_at(last_high: Swing | None, last_low: Swing | None) -> str:
    """R-ZONE-10 · `HH + HL` → UP · `LH + LL` → DOWN · karışık veya eksik → NONE."""
    if last_high is None or last_low is None:
        return NONE
    if last_high.label == "HH" and last_low.label == "HL":
        return UP
    if last_high.label == "LH" and last_low.label == "LL":
        return DOWN
    return NONE


def bias_series(df: pd.DataFrame, swings: list[Swing]) -> pd.Series:
    """Her mum için, o mum **kapandığında bilinen** yön (R-ZONE-10).

    Bir swing ancak `pivot_confirmed_at`'ten itibaren yöne katkı verir; teyit mumunun
    kendisi dahildir, çünkü o mum kapandığında pivot bilinir.
    """
    out = np.full(len(df), NONE, dtype=object)
    if not swings:
        return pd.Series(out, index=df.index, name="bias")

    teyitler = np.array([s.pivot_confirmed_at for s in swings])
    yerler = df.ts.searchsorted(teyitler, side="left")  # teyit mumunun konumu
    son: dict[str, Swing] = {}
    j = 0
    for i in range(len(df)):
        while j < len(swings) and yerler[j] <= i:
            son[swings[j].kind] = swings[j]
            j += 1
        out[i] = bias_at(son.get(HIGH), son.get(LOW))
    return pd.Series(out, index=df.index, name="bias")


def htf_bias(df: pd.DataFrame, symbol: str, timeframe: str = BIAS_TF) -> pd.DataFrame:
    """R-ZONE-07/R-ZONE-10 · `timeframe` mumlarından yön serisi, `known_at` damgalı.

    `df` daha küçük bir TF'den gelebilir; mumlar yeniden örneklenir. `known_at`,
    yönün **kullanılabilir olduğu** andır: teyit mumunun kapanışı. Aşağı TF'de bir
    karar ancak `known_at <= karar anı` olan son satırı görebilir (CLAUDE.md #3).

    > `OPEN-24` kapandı: eski "4h kapanış > 20 SMA" vekili geçersizdir (R-ZONE-10).
    """
    htf = (
        df.set_index("ts")
        .resample(timeframe, closed="left", label="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
             close=("close", "last"), volume=("volume", "sum"))
        .dropna()
        .reset_index()
    )
    swings = detect_swings(htf, symbol, timeframe)
    bias = bias_series(htf, swings)
    return pd.DataFrame({
        "ts": htf.ts,
        "bias": bias,
        # Yön, mumun kapanışında bilinir; bir sonraki mumun açılışından itibaren kullanılır.
        "known_at": htf.ts + pd.Timedelta(timeframe),
    })
