"""ccxt tabanlı OHLCV toplayıcı + Parquet yazıcı.

Spec: ARCHITECTURE.md §3 (toplama/saklama), §7 (lokal çalışır).

Saklama düzeni: data/{exchange}/{symbol}/{timeframe}/{yyyy-mm}.parquet
Sembol dizin adında '/' ve ':' güvenli hâle getirilir (NEAR/USDT:USDT -> NEAR-USDT-USDT).

Not: fiyatlar float64 saklanır. ccxt zaten float döndürür, Decimal'e çevirmek olmayan
hassasiyeti uydurmak olur. CLAUDE.md #4 gereği para *hesabı* Decimal ile yapılır;
ham piyasa verisi borsanın verdiği gibi taşınır, ekran metnine çevrilip geri parse edilmez.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ccxt
import pandas as pd

from src.data.validate import validate_ohlcv

DATA_ROOT = Path("data")
LOG_ROOT = Path("logs")
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def exchange(name: str = "bingx") -> ccxt.Exchange:
    """Perpetual (swap) piyasasına ayarlı, rate-limit'li borsa nesnesi. Anahtar gerekmez."""
    ex = getattr(ccxt, name)({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    ex.load_markets()
    return ex


def _safe(symbol: str) -> str:
    return symbol.replace("/", "-").replace(":", "-")


def fetch_ohlcv(
    ex: ccxt.Exchange, symbol: str, timeframe: str, since: int | None = None, until: int | None = None
) -> pd.DataFrame:
    """Sayfalayarak OHLCV çeker. since/until epoch ms, until dahil değil.

    Kapanmamış son mum atılır (CLAUDE.md #3: look-ahead yasak).
    """
    step = int(pd.Timedelta(timeframe).total_seconds() * 1000)
    now = ex.milliseconds()
    until = min(until or now, now)
    closed_until = (now // step) * step  # şu an oluşmakta olan mumun başlangıcı
    cursor = since if since is not None else earliest_timestamp(ex, symbol, timeframe)
    rows: list[list] = []

    while cursor < min(until, closed_until):
        batch = ex.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
        batch = [c for c in batch if cursor <= c[0] < min(until, closed_until)]
        if not batch:
            break
        rows.extend(batch)
        nxt = batch[-1][0] + step
        if nxt <= cursor:  # borsa ilerlemiyor: sonsuz döngüyü kes
            break
        cursor = nxt

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["ts"] = pd.to_datetime(df.ts, unit="ms", utc=True)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def earliest_timestamp(ex: ccxt.Exchange, symbol: str, timeframe: str, floor: str = "2017-01-01") -> int:
    """Borsanın verdiği en eski mumun epoch ms değeri.

    `since=0` kullanılamaz: BingX bunu yok sayıp güncel mumları döndürür, yani sahte bir
    "en eski" verir. Bunun yerine "bu tarihte veri var mı" sorusu üzerinde ikili arama
    yapılır — sınırın dışı boş liste döner.
    """
    step = int(pd.Timedelta(timeframe).total_seconds() * 1000)
    lo = int(pd.Timestamp(floor, tz="UTC").timestamp() * 1000)  # veri yok (invariant)
    hi = ex.milliseconds() - step  # veri var (invariant)
    if not ex.fetch_ohlcv(symbol, timeframe, since=hi, limit=1):
        raise RuntimeError(f"{symbol} {timeframe}: borsa güncel mum döndürmedi")
    if ex.fetch_ohlcv(symbol, timeframe, since=lo, limit=1):
        return ex.fetch_ohlcv(symbol, timeframe, since=lo, limit=1)[0][0]
    while hi - lo > step:
        mid = lo + (hi - lo) // 2
        if ex.fetch_ohlcv(symbol, timeframe, since=mid, limit=1):
            hi = mid
        else:
            lo = mid
    return ex.fetch_ohlcv(symbol, timeframe, since=hi, limit=1)[0][0]


def month_path(exchange_name: str, symbol: str, timeframe: str, period: str) -> Path:
    """data/{exchange}/{symbol}/{timeframe}/{yyyy-mm}.parquet (ARCHITECTURE.md §3)."""
    return DATA_ROOT / exchange_name / _safe(symbol) / timeframe / f"{period}.parquet"


def last_stored_ts(exchange_name: str, symbol: str, timeframe: str) -> pd.Timestamp | None:
    """Diskteki son mumun zamanı. Artımlı toplamanın kaldığı yer; yoksa None.

    Yalnızca en son ay dosyası okunur — artımlı koşu tüm geçmişi açmak zorunda değil.
    """
    files = sorted((DATA_ROOT / exchange_name / _safe(symbol) / timeframe).glob("*.parquet"))
    if not files:
        return None
    ts = pd.read_parquet(files[-1], columns=["ts"]).ts
    return None if ts.empty else ts.max()


def write_parquet(df: pd.DataFrame, exchange_name: str, symbol: str, timeframe: str) -> list[Path]:
    """Aya bölerek Parquet yazar. Mevcut ay dosyasıyla birleştirir, mükerrerleri ayıklar."""
    written = []
    for period, chunk in df.groupby(df.ts.dt.strftime("%Y-%m")):
        path = month_path(exchange_name, symbol, timeframe, period)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            chunk = pd.concat([pd.read_parquet(path), chunk], ignore_index=True)
        chunk = chunk.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
        chunk.to_parquet(path, index=False)
        written.append(path)
    return written


def read_parquet(exchange_name: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """Saklanan tüm ayları tek DataFrame olarak okur."""
    d = DATA_ROOT / exchange_name / _safe(symbol) / timeframe
    files = sorted(d.glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return df.sort_values("ts").reset_index(drop=True)


def snapshot_universe(ex: ccxt.Exchange) -> Path:
    """Borsanın o andaki aktif perpetual listesini tarih damgalı kaydeder.

    test_symbol_survivorship bu anlık görüntüleri kullanır: geçmiş bir pencereyi
    bugünün listesiyle test etmek yasak (ARCHITECTURE.md §3).
    """
    as_of = pd.Timestamp.now("UTC").floor("s")
    symbols = sorted(m["symbol"] for m in ex.markets.values() if m.get("swap") and m.get("active"))
    path = DATA_ROOT / ex.id / "universe" / f"{as_of:%Y-%m-%d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        pd.Series({"as_of": as_of.isoformat(), "symbols": symbols}).to_json(), encoding="utf-8"
    )
    return path


def load_universe(exchange_name: str = "bingx", as_of: str | None = None) -> dict:
    """Tarihli universe anlık görüntüsünü okur; as_of verilmezse en yenisini.

    check_symbol_survivorship'in beklediği şekli döner: {"as_of": Timestamp, "symbols": [...]}.
    """
    d = DATA_ROOT / exchange_name / "universe"
    files = sorted(d.glob("[0-9]*.json"))  # yalnizca tarih adli anlik goruntuler
    path = d / f"{as_of}.json" if as_of else (files[-1] if files else None)
    if path is None or not path.exists():
        raise FileNotFoundError(f"universe anlık görüntüsü yok: {path or d}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"as_of": pd.Timestamp(raw["as_of"]), "symbols": raw["symbols"], "path": path}


def log_event(kind: str, payload: dict) -> Path:
    """logs/{kind}/{yyyy-mm-dd}.jsonl dosyasına bir satır ekler.

    Append-only, ARCHITECTURE.md §4.1 ile aynı biçim. Dosya asla değiştirilmez.
    """
    now = pd.Timestamp.now("UTC")
    path = LOG_ROOT / kind / f"{now:%Y-%m-%d}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now.isoformat(), **payload}, default=str) + "\n")
    return path


def log_earliest(ex: ccxt.Exchange, symbol: str, timeframe: str) -> int:
    """En eski mumu ölçer ve logs/earliest/ altına kaydeder. epoch ms döner.

    Spec: ARCHITECTURE.md §3.2 — BingX'te geçmiş penceresi kayıyor görünüyor. Günlük
    kayıt olmadan bunun gerçekten kaydığı doğrulanamaz ve bugün indirilmeyen geçmiş
    kalıcı olarak kaybolur.
    """
    ms = earliest_timestamp(ex, symbol, timeframe)
    log_event("earliest", {
        "exchange": ex.id, "symbol": symbol, "timeframe": timeframe,
        "earliest": pd.Timestamp(ms, unit="ms", tz="UTC").isoformat(),
    })
    return ms


def collect(symbol: str, timeframe: str, exchange_name: str = "bingx", since: str | None = None) -> dict:
    """Tek sembol/timeframe topla, yaz, doğrulama raporu döndür."""
    ex = exchange(exchange_name)
    since_ms = int(pd.Timestamp(since, tz="UTC").timestamp() * 1000) if since else None
    df = fetch_ohlcv(ex, symbol, timeframe, since=since_ms)
    if df.empty:
        return {"rows": 0, "written": [], "errors": {}, "warnings": {}, "metrics": {}}
    written = write_parquet(df, exchange_name, symbol, timeframe)
    # Ham veri saklanır; doğrulama *kullanımı* kapıda tutar (ARCHITECTURE.md §3).
    report = validate_ohlcv(df, timeframe)
    return {"rows": len(df), "written": written,
            "errors": {k: v for k, v in report["errors"].items() if v},
            "warnings": {k: v for k, v in report["warnings"].items() if v},
            "metrics": report["metrics"], "first": df.ts.min(), "last": df.ts.max()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="OHLCV topla ve Parquet yaz")
    p.add_argument("--symbol", default="NEAR/USDT:USDT")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--since", help="ISO tarih, ör. 2024-01-01")
    p.add_argument("--earliest", action="store_true", help="Sadece en eski mum tarihini raporla")
    a = p.parse_args()

    if a.earliest:
        ex = exchange(a.exchange)
        ms = earliest_timestamp(ex, a.symbol, a.timeframe)
        print(f"{a.symbol} {a.timeframe} en eski mum: {pd.to_datetime(ms, unit='ms', utc=True)}")
    else:
        print(collect(a.symbol, a.timeframe, a.exchange, a.since))
