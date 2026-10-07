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

import numpy as np
import pandas as pd

from src.features.candles import BODY_LOOKBACK, reference_body
from src.features.ids import stable_id
from src.features.fvg import BEARISH, BULLISH, FVG, require_detect_tf
from src.features.structure import HIGH, LOW, Swing

IMPULSE_MULT = 4.0  # spec §0.1 · gövde/medyan oranının p95'i (OPEN-21) — yalnızca delinme
PIERCE_CONFIRM_BARS = 2  # "hemen dönme" kaç mumda ölçülür

__all__ = [  # BODY_LOOKBACK/reference_body `candles`'a taşındı, buradan da okunur
    "BODY_LOOKBACK", "IMPULSE_MULT", "PIERCE_CONFIRM_BARS", "AddStrength",
    "OrderBlock", "bos_time", "detect_order_blocks", "evaluate_strength", "mitigation_time",
    "ob_kurallari", "pierce_time", "pierce_times", "reference_body", "replay_obs", "seri_isaretle",
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
    bos_at: datetime | None = None  # OPEN-66 (B) · yapı kırılmasının bilindiği an; yoksa OB geçersiz
    gecersiz_at: datetime | None = None  # OPEN-66 (A1) · ardışık seriye girdiğinin bilindiği an

    def __post_init__(self) -> None:
        if self.known_at is None:
            self.known_at = self.impulse_at + pd.Timedelta(self.timeframe)


def detect_order_blocks(df: pd.DataFrame, symbol: str, timeframe: str) -> list[OrderBlock]:
    """Spec §0.1 OB (`OPEN-64`) · 3 mumluk yapı, bölge 1. mumun high–low'u. Bilgi anı 3. mumun kapanışı."""
    require_detect_tf(timeframe)
    o, h, l, c, ts = (df[k].to_numpy() for k in ("open", "high", "low", "close", "ts"))
    # Eksik mum (yeniden örneklemede kaynak mumu eksik kova: açılış/kapanış NaN) hiçbir
    # OB'nin parçası olamaz — boşluğu aşan desen yoktur (muhafazakâr, v0.11).
    tam = ~(np.isnan(o.astype(float)) | np.isnan(c.astype(float)))
    out: list[OrderBlock] = []
    for i in range(len(df) - 2):
        j, k = i + 1, i + 2
        if not (tam[i] and tam[j] and tam[k]):
            continue
        # Renk (v0.11, kullanıcı): talebin 1. mumu düşüş (c < o), arzınki yükseliş (c > o).
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



def seri_isaretle(obs: list[OrderBlock]) -> None:
    """`OPEN-66` (A1) · araya ters yönlü OB girmeden gelen aynı yönlü OB'lerin **hepsi** geçersiz.

    Sıra 1. mumun zamanıdır. `gecersiz_at` geçersizliğin **bilindiği** an (CLAUDE.md #3): serinin
    ikinci ve sonraki OB'leri doğduğu anda (`known_at`), ilki ardılı bilindiğinde geçersizdir.
    Tek OB'lik seride `None`. Liste büyüdükçe (canlı) baştan çağrılır; damgalar önekle değişmez.
    """
    s = sorted(obs, key=lambda o: o.created_at)
    for o in s:
        o.gecersiz_at = None
    for p, q in zip(s, s[1:]):
        if p.direction == q.direction:
            p.gecersiz_at = q.known_at if p.gecersiz_at is None else min(p.gecersiz_at, q.known_at)
            q.gecersiz_at = q.known_at


def bos_time(ob: OrderBlock, df: pd.DataFrame, swings: list[Swing]) -> datetime | None:
    """`OPEN-66` (B) · OB'den başlayan hareketin son karşı swing'i kapanışla kırdığı an.

    Karşı swing: talepte **tepe**, arzda **dip**, pivotu 1. mumdan önce. Her mumda, o mumun
    kapanışında **bilinen** (`known_at`) swing'lerin en son pivotlusu ölçülür; böylece canlı önek
    ile tam seri aynı sonucu verir. Kırılma 2. mumdan başlar, kapanışla (fitil yetmez). Fiyat OB
    bölgesine ilk döndüğünde (mitigasyon mumu, 3. mumdan sonra) hareket biter → `None`.
    Dönen an kırılma mumunun kapanışı. Eksik mumun kapanışı (NaN) kırmaz.
    """
    return _bos(ob, _Dizi.of(df), _swing_dizi(swings))


class _Dizi:
    """Bir mum çerçevesinin numpy görünümü — OB başına `itertuples` yerine (5m'de ~80 bin mum)."""

    def __init__(self, df: pd.DataFrame):
        self.ts = df.ts.to_numpy()
        ix = pd.DatetimeIndex(df.ts)
        self.ns = (ix.tz_convert("UTC").tz_localize(None) if ix.tz else ix).as_unit("ns").asi8
        self.open, self.high, self.low, self.close = (
            df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        self.df = df

    @staticmethod
    def of(df) -> "_Dizi":
        return df if isinstance(df, _Dizi) else _Dizi(df)


def _ns(t) -> int:
    t = pd.Timestamp(t)
    return (t.tz_convert("UTC").tz_localize(None) if t.tz else t).as_unit("ns").value


def _swing_dizi(swings: list[Swing]) -> dict:
    """Tip başına: pivot zamanı, bilinme anı, fiyat (liste sırası korunur)."""
    out = {}
    for tip in (HIGH, LOW):
        s = [x for x in swings if x.kind == tip]
        out[tip] = (np.array([_ns(x.ts) for x in s], dtype="int64"),
                    np.array([_ns(x.known_at) for x in s], dtype="int64"),
                    np.array([x.price for x in s], dtype=float))
    return out


def _bos(ob: OrderBlock, d: _Dizi, sw: dict) -> datetime | None:
    pts, kn, fiyat = sw[HIGH if ob.direction == BULLISH else LOW]
    sec = pts < _ns(ob.created_at)
    if not sec.any():
        return None
    pts, kn, fiyat = pts[sec], kn[sec], fiyat[sec]
    # Bilinme anına göre sıralı önek; her önekte en son pivotlunun fiyatı (eşit pivotta önce bilinen).
    sira = np.argsort(kn, kind="stable")
    kn, pk = kn[sira], pts[sira]
    yeni = np.r_[True, pk[1:] > np.maximum.accumulate(pk)[:-1]]
    en_son = sira[np.maximum.accumulate(np.where(yeni, np.arange(len(pk)), 0))]
    td = pd.Timedelta(ob.timeframe).value
    imp = _ns(ob.impulse_at)
    bull = ob.direction == BULLISH
    r0, n = int(np.searchsorted(d.ns, _ns(ob.created_at), side="right")), len(d.ns)
    blok = 64
    while r0 < n:  # parça parça vektörel: ilk olay (dönüş ya da kırılma) bulunana kadar
        r = slice(r0, min(n, r0 + blok))
        ns = d.ns[r]
        donus = (ns > imp) & (d.low[r] <= ob.top) & (d.high[r] >= ob.bottom)
        m = np.searchsorted(kn, ns + td, side="right")
        seviye = np.where(m > 0, fiyat[en_son[np.maximum(m - 1, 0)]], np.nan)
        with np.errstate(invalid="ignore"):
            kirik = (m > 0) & ((d.close[r] > seviye) if bull else (d.close[r] < seviye))
        olay = np.flatnonzero(donus | kirik)
        if len(olay):
            i = int(olay[0])
            if donus[i]:
                return None  # bölgeye döndü: hareket bitti
            return pd.Timestamp(d.ts[r0 + i]) + pd.Timedelta(ob.timeframe)
        r0 += blok
        blok = min(blok * 2, 8192)
    return None


def ob_kurallari(obs: list[OrderBlock], df: pd.DataFrame, swings: list[Swing]) -> None:
    """`OPEN-66` A1 + B damgaları. Kırılması bilinen OB yeniden hesaplanmaz (önek değişmez)."""
    seri_isaretle(obs)
    d, sw = _Dizi(df), _swing_dizi(swings)
    for o in obs:
        if o.bos_at is None:
            o.bos_at = _bos(o, d, sw)


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
    return _pierce(ob, _PierceDizi.of(df, lookback), body_mult, confirm_bars)


class _PierceDizi(_Dizi):
    """`_Dizi` + gövde ve referans gövde (tüm seri üzerinde bir kez; değerler dilimlemeyle aynı:
    `reference_body` yalnızca son `lookback` mumu okur)."""

    def __init__(self, df: pd.DataFrame, lookback: int = BODY_LOOKBACK):
        super().__init__(df)
        self.body = np.abs(self.close - self.open)
        self.ref = reference_body(df, lookback).to_numpy(dtype=float)
        self.lookback = lookback

    @staticmethod
    def of(df, lookback: int = BODY_LOOKBACK) -> "_PierceDizi":
        return df if isinstance(df, _PierceDizi) and df.lookback == lookback             else _PierceDizi(df, lookback)


def _pierce(ob: OrderBlock, d: _PierceDizi, body_mult: float, confirm_bars: int) -> datetime | None:
    """`pierce_time`'ın döngüsü, mum mum yerine olaydan olaya: temas → geçiş → teyit."""
    bull = ob.direction == BULLISH
    temas = (d.low <= ob.top) & (d.high >= ob.bottom)
    gecis = (d.low < ob.bottom) if bull else (d.high > ob.top)
    n = len(d.ns)
    i = int(np.searchsorted(d.ns, _ns(ob.impulse_at), side="right"))  # OB henüz bilinmiyor
    while i < n:
        e = np.flatnonzero(temas[i:])
        if not len(e):
            return None
        entered = i + int(e[0])  # OB'ye ilk temas
        g = np.flatnonzero(gecis[entered:])
        if not len(g):
            return None
        t = entered + int(g[0])
        b = d.body[entered:t + 1]
        b = b[~np.isnan(b)]
        ort = b.mean() if len(b) else np.nan
        if not (ort >= body_mult * d.ref[t]):
            i = t + 1  # sürünerek geçildi; fiyat dönerse yeniden ölçülür
            continue
        if t + confirm_bars >= n:
            return None  # teyit mumları kapanmadı: delinme henüz bilinmiyor
        sonra = slice(t + 1, t + 1 + confirm_bars)
        if ((d.high[sonra] >= ob.top) if bull else (d.low[sonra] <= ob.bottom)).any():
            i = t + 1
            continue
        return pd.Timestamp(d.ts[t + confirm_bars]) + pd.Timedelta(ob.timeframe)  # son teyit mumunun kapanışı
    return None


def pierce_times(obs: list[OrderBlock], df: pd.DataFrame) -> dict[str, datetime | None]:
    """Aynı çerçevedeki her OB için `pierce_time` — dizi hazırlığı bir kez."""
    d = _PierceDizi(df)
    return {o.ob_id: _pierce(o, d, IMPULSE_MULT, PIERCE_CONFIRM_BARS) for o in obs}


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
