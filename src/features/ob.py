"""OB (Order Block) tespiti, R-ADD-06 delinme kuralı, R-ADD-05 güç bayrakları.

Spec: R-ENTRY-02 (1) (bantta yöne uygun OB varsa OB'den giriş), R-ADD-01 (2)(3),
R-ADD-05 ("güçlü dönüt"), R-ADD-06 (hacim ve delinme).

**Tanım** (kullanıcı, 2026-10-05, spec §0.1, `OPEN-64`): düşüşten önceki **son yükseliş
mumu** (`BEARISH`, arz) ya da yükselişten önceki **son düşüş mumu** (`BULLISH`, talep) —
**1. mum**; bölge mumun **tamamı** (high–low, fitiller dahil; kullanıcı 2026-10-06, v0.9).
Geçerlilik iki komşu mumdan:

```
talep (BULLISH, long)          arz (BEARISH, short)
1. mum düşüş                   1. mum yükseliş
2. mum düşüş değil,            2. mum yükseliş değil,
   low₂ ≥ low₁ (sarkmaz)          high₂ ≤ high₁ (sarkmaz)
3. mum low₃ > high₁            3. mum high₃ < low₁
   (1. mumla temas yok)           (1. mumla temas yok)
```

Büyüklük eşiği yok: 2026-10-05'e kadarki tanım (impuls mumu, gövde ≥ `IMPULSE_MULT` ×
medyan, öncesindeki son ters mum) kullanıcı kuralıyla değişti. `IMPULSE_MULT` yalnızca
delinmede (R-ADD-06) kalır: "normalden büyük gövde" = son `BODY_LOOKBACK` mumun medyan
gövdesinin `IMPULSE_MULT` katı. `PIERCE_CONFIRM_BARS` hâlâ başlangıç değeridir.

Tespit yalnızca **5m ve üstünde** çalışır (`R-ZONE-09`, `require_detect_tf`).

Look-ahead (CLAUDE.md #3): OB, 3. mum **kapanmadan** bilinemez. `created_at` (1. mum) ve
`impulse_at` (3. mum) mumların **açılış** zamanıdır (kimlik); bilgi anı `known_at = impulse_at + TF`.
`mitigated_at` ve `pierce_time` olayın bilindiği mumun **kapanışıdır**. Tüketiciler
yalnızca bunları okur; delinme ve güç değerlendirmesi impuls mumundan önceki mumlara bakmaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.features.candles import BODY_LOOKBACK, reference_body
from src.features.ids import stable_id
from src.features.fvg import BEARISH, BULLISH, FVG, require_detect_tf

IMPULSE_MULT = 4.0  # spec §0.1 · gövde/medyan oranının p95'i (OPEN-21) — yalnızca delinme
PIERCE_CONFIRM_BARS = 2  # "hemen dönme" kaç mumda ölçülür

__all__ = [  # BODY_LOOKBACK/reference_body `candles`'a taşındı, buradan da okunur
    "BODY_LOOKBACK", "IMPULSE_MULT", "PIERCE_CONFIRM_BARS", "AddStrength",
    "OrderBlock", "detect_order_blocks", "evaluate_strength", "mitigation_time",
    "pierce_time", "reference_body", "replay_obs",
]


@dataclass
class OrderBlock:
    """Bir OB. `top`/`bottom` 1. mumun high/low'u — fitiller dahil (spec v0.9)."""

    ob_id: str
    symbol: str
    timeframe: str
    direction: str  # BULLISH = impuls yukarı (talep) · BEARISH = impuls aşağı (arz)
    top: float
    bottom: float
    created_at: datetime  # 1. mumun (OB) açılışı — kimlik
    impulse_at: datetime  # 3. mumun (teyit) açılışı — kimlik, bilgi anı değil
    mitigated_at: datetime | None = None  # bölgeye ilk dönülen mumun kapanışı (R-ENTRY-05)
    known_at: datetime | None = field(default=None)  # 3. mumun kapanışı; boşsa türetilir

    def __post_init__(self) -> None:
        if self.known_at is None:
            self.known_at = self.impulse_at + pd.Timedelta(self.timeframe)


def detect_order_blocks(df: pd.DataFrame, symbol: str, timeframe: str) -> list[OrderBlock]:
    """Spec §0.1 OB (`OPEN-64`) · 3 mumluk yapı, bölge 1. mumun high–low'u. Bilgi anı 3. mumun kapanışı."""
    require_detect_tf(timeframe)
    o, h, l, c, ts = (df[k].to_numpy() for k in ("open", "high", "low", "close", "ts"))
    out: list[OrderBlock] = []
    for i in range(len(df) - 2):
        j, k = i + 1, i + 2
        if c[i] < o[i] and not c[j] < o[j] and l[j] >= l[i] and l[k] > h[i]:
            direction = BULLISH  # son düşüş mumu, ardından yükseliş
        elif c[i] > o[i] and not c[j] > o[j] and h[j] <= h[i] and h[k] < l[i]:
            direction = BEARISH  # son yükseliş mumu, ardından düşüş
        else:
            continue
        out.append(OrderBlock(
            ob_id=stable_id("ob", symbol, timeframe, ts[i], ts[k]), symbol=symbol,
            timeframe=timeframe, direction=direction, top=float(h[i]),
            bottom=float(l[i]), created_at=pd.Timestamp(ts[i]),
            impulse_at=pd.Timestamp(ts[k])))
    return out


def pierce_time(
    ob: OrderBlock,
    df: pd.DataFrame,
    body_mult: float = IMPULSE_MULT,
    lookback: int = BODY_LOOKBACK,
    confirm_bars: int = PIERCE_CONFIRM_BARS,
) -> datetime | None:
    """R-ADD-06 · OB hacimle delindi mi. Delinme anını döner, delinme yoksa `None`.

    Delinme dört koşulun birlikte sağlanmasıdır:

    1. OB **tamamen** geçilir — içine girmek yetmez (bullish OB'de `low < bottom`)
    2. **Mum kapanışı beklenmez** — fitil yeter, `close` kullanılmaz
    3. Geçişi yapan mumların **ortalama gövdesi** normalin `body_mult` katı. Tek mum
       şart değil (spec); sürünerek geçiş ortalamayı düşürür ve delinme sayılmaz
    4. Geçişten sonraki `confirm_bars` mumda fiyat OB'yi **tamamen geri almaz** —
       "altına inip hemen dönme grafik hatası / geç tepkidir, delinme sayılmaz".
       Ölçüt OB'ye dokunmak değil karşı sınırı geri almaktır (bullish OB'de
       `high >= top`): geçiş mumunun kapanışı OB'nin içinde kalabilir ve o mumun
       kapanışı zaten beklenmiyor — dokunma ölçütü bu iki kuralı çelişkiye sokardı

    Dönen an, son teyit mumunun **kapanışıdır**: "geri alma" o mumlar kapanmadan bilinmez
    (CLAUDE.md #3). Teyit mumları henüz yoksa delinme **henüz bilinmiyor**dur (`None`).
    2026-09-29'a kadar veri geçişten hemen sonra bitince delinme sayılıyordu; bu, önekte
    tam seriden farklı sonuç veriyordu (canlı ↔ backtest paritesi, D1).

    ponytail: hacim ölçütü yalnızca gövde büyüklüğü. R-ADD-06'nın "bölgesel hacim =
    zigzag yoğunluğu" göstergesi leg tespiti (`OPEN-01`) geldiğinde eklenir.
    """
    # Yalnızca impulstan sonrası değerlendirilir; öncesinden gereken tek şey referans
    # gövde medyanının penceresidir. Tüm geçmiş üzerinde rolling hesaplamak sonucu
    # değiştirmez, sadece her çağrıyı O(veri) yapar — ölçüm koşusunda bu O(n²) demek.
    df = df.iloc[max(0, int(df.ts.searchsorted(ob.impulse_at)) - lookback):]
    body = (df.close - df.open).abs()
    ref = reference_body(df, lookback)
    rows = list(df.itertuples())
    entered: int | None = None

    for i, r in enumerate(rows):
        if r.ts <= ob.impulse_at:  # OB henüz bilinmiyor
            continue
        if entered is None:
            if r.low <= ob.top and r.high >= ob.bottom:  # OB'ye ilk temas
                entered = i
            else:
                continue
        through = r.low < ob.bottom if ob.direction == BULLISH else r.high > ob.top
        if not through:
            continue
        if not (body.iloc[entered:i + 1].mean() >= body_mult * ref.iat[i]):
            entered = None  # sürünerek geçildi; fiyat dönerse yeniden ölçülür
            continue
        after = rows[i + 1:i + 1 + confirm_bars]
        if len(after) < confirm_bars:
            return None  # teyit mumları kapanmadı: delinme henüz bilinmiyor
        returned = any(
            (a.high >= ob.top) if ob.direction == BULLISH else (a.low <= ob.bottom)
            for a in after
        )
        if returned:
            entered = None
            continue
        return rows[i + confirm_bars].ts + pd.Timedelta(ob.timeframe)  # son teyit mumunun kapanışı
    return None


def mitigation_time(ob: OrderBlock, df: pd.DataFrame) -> datetime | None:
    """R-ENTRY-05 · fiyatın OB bölgesine **ilk temas** ettiği an; temas yoksa `None`.

    Mitigasyon §0.1'de "bölgeye ilk temas" olarak tanımlı — delinme (`pierce_time`)
    değildir: delinme bölgenin tamamen geçilmesi, mitigasyon ise yalnızca dokunulması.
    R-ENTRY-05 "fiyat bir kez uğradıysa bölge tüketilmiş sayılır" der, bu yüzden
    girişte aranan ölçüt dokunmadır.

    Yalnızca `impulse_at`'ten **sonraki** mumlar sayılır: OB o ana kadar bilinmiyordu
    ve impuls mumunun kendisi zaten bölgeden çıkan harekettir (CLAUDE.md #3).
    """
    for r in df.itertuples():
        if r.ts <= ob.impulse_at:
            continue
        if r.low <= ob.top and r.high >= ob.bottom:
            return r.ts + pd.Timedelta(ob.timeframe)  # mumun kapanışı
    return None


def replay_obs(obs: list[OrderBlock], df: pd.DataFrame) -> None:
    """Her OB'nin `mitigated_at`'ini doldurur — `fvg.replay` ile aynı kalıp.

    Zaman damgası mumun **kapanışıdır**: mitigasyon ancak o mum kapanınca bilinir
    (CLAUDE.md #3). Eski açılış damgası mitigasyonu erken görüyordu.
    """
    rows = list(df.itertuples())
    for ob in obs:
        td = pd.Timedelta(ob.timeframe)
        for i in range(int(df.ts.searchsorted(ob.impulse_at, side="right")), len(rows)):
            r = rows[i]
            if r.low <= ob.top and r.high >= ob.bottom:
                ob.mitigated_at = r.ts + td
                break


@dataclass
class AddStrength:
    """R-ADD-05 bayrakları. Skor yok: ağırlıklandırma R-ZONE-08'in işi (TASARLANACAK).

    `fvg_inside_unfilled` ve `opposite_ob`'un yokluğu gücü **artırır**, `consecutive_obs`
    gücü **azaltır**. Bayrakların nasıl tartılacağını bu katman bilmez.
    """

    fvg_inside_unfilled: bool
    opposite_ob: bool
    consecutive_obs: bool


def evaluate_strength(
    ob: OrderBlock,
    fvgs: list[FVG] = (),
    obs: list[OrderBlock] = (),
    at: datetime | None = None,
) -> AddStrength:
    """R-ADD-05 · "güçlü dönüt" bayrakları. Tek OB tek başına yeterlidir; bunlar ek sinyal.

    Değerlendirme anı `at` (varsayılan: OB'nin bilinir olduğu an). O andan **sonra**
    oluşan FVG/OB'ler hesaba katılmaz ve o anda henüz dolmamış bir boşluk açık sayılır —
    aksi hâlde bayraklar geleceği görür (CLAUDE.md #3).

    Pencereyi çağıran seçer: `fvgs` ve `obs` listelerinin kapsamı (hangi TF, ne kadar
    geçmiş) bu fonksiyonun kararı değildir.
    """
    at = at or ob.known_at
    gecmis_fvg = [f for f in fvgs if f.known_at <= at]
    gecmis_ob = sorted(
        (o for o in obs if o.known_at <= at and o.ob_id != ob.ob_id),
        key=lambda o: o.known_at,
    )
    return AddStrength(
        fvg_inside_unfilled=any(
            (f.filled_at is None or f.filled_at > at) and f.overlaps(ob.top, ob.bottom)
            for f in gecmis_fvg
        ),
        opposite_ob=any(o.direction != ob.direction for o in gecmis_ob),
        consecutive_obs=bool(gecmis_ob) and gecmis_ob[-1].direction == ob.direction,
    )
