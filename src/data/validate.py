"""OHLCV doğrulama.

Spec: ARCHITECTURE.md §3 (yedi zorunlu kontrol), §3.1 (eşik tanımları),
R-KILL-01 (veri bütünlüğü).

Her kontrol ihlal listesi döner; boş liste = geçti. Hiçbiri sessizce düzeltme yapmaz.

Eşikler §3.1'de tanımlı: sıfır hacim **uyarı** seviyesindedir (veriyi kullanılamaz
yapmaz, oranı ayrı bir eleme metriğidir), fiyat sıçraması sabit yüzde değil sembolün
kendi getiri standart sapmasına göre ölçülür ve yalnızca **kalıcı olmayan** sıçrama
ihlaldir.
"""
from __future__ import annotations

import pandas as pd

# §3.1 varsayılanları. Kuralın kendisi spec'te kapalı; bunlar onun ayar sabitleri.
ZERO_VOLUME_MAX_RUN = 10
JUMP_SIGMA_MULT = 10.0
JUMP_VOL_WINDOW = 500
JUMP_REVERT_BARS = 2
JUMP_REVERT_FRAC = 0.5

COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def check_utc(df: pd.DataFrame) -> list[str]:
    """Tüm zaman damgaları tz-aware ve UTC mi."""
    tz = df.ts.dt.tz
    if tz is None:
        return ["ts tz-naive"]
    if str(tz) != "UTC":
        return [f"ts tz={tz}, UTC değil"]
    return []


def check_no_duplicates(df: pd.DataFrame) -> list[pd.Timestamp]:
    """Aynı timestamp iki kez var mı."""
    return list(df.ts[df.ts.duplicated()].unique())


def check_no_gaps(df: pd.DataFrame, timeframe: str) -> list[pd.Timestamp]:
    """Timestamp serisinde eksik mum var mı. Eksik olanların listesini döner."""
    if df.empty:
        return []
    step = pd.Timedelta(timeframe)
    expected = pd.date_range(df.ts.min(), df.ts.max(), freq=step)
    return list(expected.difference(pd.DatetimeIndex(df.ts)))


def check_ohlc_sanity(df: pd.DataFrame) -> list[pd.Timestamp]:
    """low <= open,close <= high her satırda geçerli mi."""
    bad = (
        (df.low > df[["open", "close"]].min(axis=1))
        | (df.high < df[["open", "close"]].max(axis=1))
        | (df.low > df.high)
    )
    return list(df.ts[bad])


def check_no_zero_volume_runs(
    df: pd.DataFrame, max_run: int = ZERO_VOLUME_MAX_RUN
) -> list[tuple[pd.Timestamp, int]]:
    """Ardışık sıfır hacim serisi. **Uyarı seviyesi** — veriyi kullanılamaz yapmaz.

    Spec: ARCHITECTURE.md §3.1. Düşük likiditeli bir sembolde art arda birkaç sıfır
    hacimli 1m mumu normaldir, borsa kesintisi değildir; varsayılan eşik 10 mumdur.
    Sembolün genel sağlığı `zero_volume_ratio` ile ayrıca ölçülür.

    max_run'dan uzun her seri için (seri başlangıcı, uzunluk) döner.
    """
    zero = df.volume == 0
    if not zero.any():
        return []
    group = (~zero).cumsum()[zero]
    runs = []
    for _, idx in group.groupby(group).groups.items():
        if len(idx) > max_run:
            runs.append((df.ts[idx[0]], len(idx)))
    return runs


def zero_volume_ratio(df: pd.DataFrame) -> float:
    """Sembolün sıfır hacimli mum oranı — backtest uygunluğu için eleme metriği.

    Spec: ARCHITECTURE.md §3.1. İhlal değil, ölçüm: oranı yüksek sembol zaten
    backtest için uygun değildir.
    """
    return float((df.volume == 0).mean()) if len(df) else 0.0


def check_price_jumps(
    df: pd.DataFrame,
    *,
    sigma_mult: float = JUMP_SIGMA_MULT,
    window: int = JUMP_VOL_WINDOW,
    revert_bars: int = JUMP_REVERT_BARS,
    revert_frac: float = JUMP_REVERT_FRAC,
) -> list[tuple[pd.Timestamp, float, float]]:
    """Kalıcı olmayan fiyat sıçraması (kötü tick) tespiti.

    Spec: ARCHITECTURE.md §3.1. Kötü tick ile gerçek hareketi ayıran şey büyüklük değil
    kalıcılıktır, o yüzden iki koşul birlikte aranır:

      1. Kapanış getirisi sembolün kendi oynaklığını aşıyor:
         |r_t| > sigma_mult * std(r), std yalnızca geçmiş `window` mumdan hesaplanır.
      2. Hareketin `revert_frac`'ten fazlası sonraki `revert_bars` mum içinde geri alınıyor.

    Eşik sabit yüzde değildir: BTC ile bir memecoin aynı ölçüyle değerlendirilmez.
    Sabit %20 gibi bir eşik likidasyon kaskadlarında ve yeni listelemelerde yanlış
    pozitif üretir.

    Bu bir veri kalitesi kontrolüdür, feature değildir: ileriye bakması kasıtlıdır ve
    karar hattında kullanılmaz (CLAUDE.md #3 karar anını bağlar, offline denetimi değil).

    Döner: (ts, getiri %, kaç sigma) üçlüleri.
    """
    if len(df) < 2:
        return []
    ret = df.close.pct_change()
    sigma = ret.rolling(window, min_periods=30).std().shift(1)
    z = ret.abs() / sigma  # sigma=0 ve ret!=0 -> inf: düz seride tek tick yine yakalanır
    move = df.close.diff()
    retraced = pd.concat(
        [(df.close - df.close.shift(-k)) / move for k in range(1, revert_bars + 1)], axis=1
    ).max(axis=1)
    bad = (z > sigma_mult) & (retraced > revert_frac)
    return list(zip(df.ts[bad], ret[bad] * 100, z[bad]))


def check_symbol_survivorship(
    universe: dict, symbol: str, window_start: pd.Timestamp
) -> list[str]:
    """Sembol listesi tarihsel mi, bugünün listesi mi.

    universe: {"as_of": Timestamp, "symbols": [...]} — belirli bir andaki borsa listesi.
    Test penceresi as_of'tan önce başlıyorsa liste geleceğe bakıyordur: o tarihte borsadan
    düşmüş semboller hiç görünmez ve sonuçlar yapay olarak iyileşir.
    """
    violations = []
    as_of = universe["as_of"]
    if as_of > window_start:
        violations.append(f"universe as_of={as_of} > pencere başlangıcı {window_start}")
    if symbol not in universe["symbols"]:
        violations.append(f"{symbol}, as_of={as_of} listesinde yok")
    return violations


def validate_ohlcv(
    df: pd.DataFrame,
    timeframe: str,
    *,
    max_zero_volume_run: int = ZERO_VOLUME_MAX_RUN,
    jump_sigma_mult: float = JUMP_SIGMA_MULT,
) -> dict[str, dict]:
    """Altı OHLCV kontrolünü çalıştırır. Survivorship ayrı, universe gerektiriyor.

    Döner: {"errors": {...}, "warnings": {...}, "metrics": {...}}
    `errors` boş değilse veri kullanılamaz. `warnings` kullanımı engellemez (§3.1).
    """
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"eksik kolon: {missing}")
    return {
        "errors": {
            "utc": check_utc(df),
            "no_duplicates": check_no_duplicates(df),
            "no_gaps": check_no_gaps(df, timeframe),
            "ohlc_sanity": check_ohlc_sanity(df),
            "price_jumps": check_price_jumps(df, sigma_mult=jump_sigma_mult),
        },
        "warnings": {
            "zero_volume_runs": check_no_zero_volume_runs(df, max_zero_volume_run),
        },
        "metrics": {
            "rows": len(df),
            "zero_volume_ratio": zero_volume_ratio(df),
        },
    }
