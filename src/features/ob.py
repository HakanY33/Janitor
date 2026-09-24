"""OB (Order Block) tespiti, R-ADD-06 delinme kuralı, R-ADD-05 güç bayrakları.

Spec: R-ENTRY-02 (1) (bantta yöne uygun OB varsa OB'den giriş), R-ADD-01 (2)(3),
R-ADD-05 ("güçlü dönüt"), R-ADD-06 (hacim ve delinme).

**Tanım** (kullanıcı, 2026-09-11 — STRATEGY_SPEC'te OB'nin sözlük tanımı yok, bkz.
`OPEN-22`): impuls hareketi öncesi son **ters yönlü** mumun **gövdesi**. Fitil OB'ye
girmez. OB'nin yönü impulsun yönüdür: yukarı impulstan önceki düşüş mumu `BULLISH`
(talep) bloğudur.

**"Normalden büyük gövde"** (R-ADD-06) tek bir ölçütle sayısallaştırıldı: mumun gövdesi,
son `BODY_LOOKBACK` mumun **medyan gövdesinin** `IMPULSE_MULT` katı veya üzeri.
Medyan ortalamadan seçildi; tek bir devasa mum eşiği kendi lehine bozmasın diye.
Aynı ölçüt hem impuls tespitinde hem delinmede kullanılır — spec ikisini de aynı
cümleyle tarif ediyor.

`IMPULSE_MULT = 4.0` spec §0.1'de sabitlendi (`OPEN-21` kapandı): tüm NEAR verisinde
gövde/medyan oranının p95'i, yani mumların %4.5'i. Kalan eşikler (`BODY_LOOKBACK`,
`OB_SEARCH`, `PIERCE_CONFIRM_BARS`) hâlâ başlangıç değeridir, backtest'le kalibre
edilecek. Kod bunları kendi ayarlamaz (CLAUDE.md: self-tuning yasak).

Eşik yoğunluğu düşürür ama **anlamlılığı seçmez** (`OPEN-23`): hangi OB'nin çalıştığını
ayıran ölçüt aranıyor, ölçüm `scripts/measure_ob.py`.

Tespit yalnızca **5m ve üstünde** çalışır (`R-ZONE-09`, `require_detect_tf`).

Look-ahead (CLAUDE.md #3): OB, impuls mumu kapanmadan **bilinemez**. Bu yüzden gövdenin
kendi zamanı (`created_at`) ile OB'nin bilinir olduğu an (`impulse_at`) ayrı alanlardır;
delinme ve güç değerlendirmesi `impulse_at`'ten önceki mumlara bakmaz.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from src.features.fvg import BEARISH, BULLISH, FVG, require_detect_tf

IMPULSE_MULT = 4.0  # spec §0.1 · gövde/medyan oranının p95'i (OPEN-21 kapandı)
BODY_LOOKBACK = 20  # referans gövde medyanının penceresi
OB_SEARCH = 10  # impulstan geriye kaç mum ters yönlü mum aranır
PIERCE_CONFIRM_BARS = 2  # "hemen dönme" kaç mumda ölçülür


@dataclass
class OrderBlock:
    """Bir OB. `top`/`bottom` gövde sınırları (open/close), fitil dışarıda."""

    ob_id: str
    symbol: str
    timeframe: str
    direction: str  # BULLISH = impuls yukarı (talep) · BEARISH = impuls aşağı (arz)
    top: float
    bottom: float
    created_at: datetime  # OB mumunun zamanı
    impulse_at: datetime  # impuls mumunun zamanı — OB ancak burada bilinir


def reference_body(df: pd.DataFrame, lookback: int = BODY_LOOKBACK) -> pd.Series:
    """Geçmiş mumların medyan gövdesi. `shift(1)`: mum kendi eşiğini yükseltemez.

    İlk mumlarda NaN döner; NaN ile yapılan her karşılaştırma False olduğu için
    yetersiz geçmişte impuls de delinme de tespit edilmez.
    """
    body = (df.close - df.open).abs()
    return body.rolling(lookback, min_periods=5).median().shift(1)


def detect_order_blocks(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    body_mult: float = IMPULSE_MULT,
    lookback: int = BODY_LOOKBACK,
    search: int = OB_SEARCH,
) -> list[OrderBlock]:
    """İmpuls mumlarını bulur, her birinin öncesindeki son ters yönlü mumun gövdesini döner.

    Ardışık impulslar aynı bloğu tekrar üretmez: aynı gövde bir kez listelenir.
    """
    require_detect_tf(timeframe)
    body = (df.close - df.open).abs()
    large = body >= body_mult * reference_body(df, lookback)
    rows = list(df.itertuples())
    out: list[OrderBlock] = []

    for i, r in enumerate(rows):
        if not large.iat[i] or r.close == r.open:
            continue
        up = r.close > r.open
        for prev in reversed(rows[max(0, i - search):i]):
            if (prev.close < prev.open) if up else (prev.close > prev.open):
                if not (out and out[-1].created_at == prev.ts):
                    out.append(
                        OrderBlock(
                            ob_id=uuid.uuid4().hex,
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=BULLISH if up else BEARISH,
                            top=max(prev.open, prev.close),
                            bottom=min(prev.open, prev.close),
                            created_at=prev.ts,
                            impulse_at=r.ts,
                        )
                    )
                break
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

    Veri geçişten hemen sonra bitiyorsa delinme sayılır: kapanış beklenmez kuralının
    sonucu ve kötümser taraf (`ADD-REJECT-C` tetiklenir, ekleme yapılmaz).

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
        returned = any(
            (a.high >= ob.top) if ob.direction == BULLISH else (a.low <= ob.bottom)
            for a in after
        )
        if returned:
            entered = None
            continue
        return r.ts
    return None


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
    at = at or ob.impulse_at
    gecmis_fvg = [f for f in fvgs if f.created_at <= at]
    gecmis_ob = sorted(
        (o for o in obs if o.impulse_at <= at and o.ob_id != ob.ob_id),
        key=lambda o: o.impulse_at,
    )
    return AddStrength(
        fvg_inside_unfilled=any(
            (f.filled_at is None or f.filled_at > at) and f.overlaps(ob.top, ob.bottom)
            for f in gecmis_fvg
        ),
        opposite_ob=any(o.direction != ob.direction for o in gecmis_ob),
        consecutive_obs=bool(gecmis_ob) and gecmis_ob[-1].direction == ob.direction,
    )
