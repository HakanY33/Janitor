"""Günlük artımlı toplama + universe anlık görüntüsü.

Spec: ARCHITECTURE.md §3.2 (günlük cron), §3 (survivorship).

    python -m scripts.daily                       # tüm aktif perpetual listesi
    python -m scripts.daily --symbols NEAR/USDT:USDT --timeframe 1m

Sıra: önce universe anlık görüntüsü (tarihli, data/{exchange}/universe/{gün}.json),
sonra her sembol için diskteki son mumdan bugüne kadarki mumlar.

Survivorship geçmişi satın alınamaz, bugünden itibaren birikir: anlık görüntü
alınmayan gün kalıcı olarak kayıptır. Bu yüzden toplama başarısız olsa bile
anlık görüntü alınır.

Kesinti güvenli: kaldığı yer diskteki son mumdur, ayrı durum dosyası yoktur.
Yarıda kalan koşu tekrar başlatıldığında yalnızca eksiği çeker.
"""
from __future__ import annotations

import argparse
import sys
import traceback

import pandas as pd

from src.data.collect import (
    exchange,
    fetch_ohlcv,
    last_stored_ts,
    log_earliest,
    log_event,
    snapshot_universe,
    write_parquet,
)
from src.data.validate import validate_ohlcv


def update_symbol(ex, symbol: str, timeframe: str, exchange_name: str) -> dict:
    """Diskteki son mumdan itibaren yeni mumları çeker, yazar, doğrular."""
    step = int(pd.Timedelta(timeframe).total_seconds() * 1000)
    # §3.2: pencere kayıyor mu — toplama için gerekmez, kaydı zorunlu olan ölçüm.
    first_ms = log_earliest(ex, symbol, timeframe)
    last = last_stored_ts(exchange_name, symbol, timeframe)
    since = int(last.timestamp() * 1000) + step if last is not None else first_ms

    df = fetch_ohlcv(ex, symbol, timeframe, since=since)
    if df.empty:
        return {"rows": 0, "errors": {}, "warnings": {}, "metrics": {}}
    write_parquet(df, exchange_name, symbol, timeframe)
    # Yalnızca yeni dilim doğrulanır; eski aylar zaten yazıldığında doğrulandı.
    report = validate_ohlcv(df, timeframe)
    return {"rows": len(df), "last": df.ts.max(),
            "errors": {k: v for k, v in report["errors"].items() if v},
            "warnings": {k: v for k, v in report["warnings"].items() if v},
            "metrics": report["metrics"]}


def main() -> int:
    p = argparse.ArgumentParser(description="Günlük artımlı OHLCV toplama")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--symbols", nargs="+", help="Verilmezse bugünün anlık görüntüsü")
    p.add_argument("--limit", type=int, help="Yalnızca ilk N sembol")
    a = p.parse_args()

    ex = exchange(a.exchange)
    snapshot = snapshot_universe(ex)  # her koşuda, toplamadan önce
    print(f"universe anlık görüntüsü: {snapshot}")

    symbols = a.symbols or sorted(
        m["symbol"] for m in ex.markets.values() if m.get("swap") and m.get("active")
    )
    symbols = symbols[: a.limit] if a.limit else symbols

    failed = []
    for i, symbol in enumerate(symbols, 1):
        try:
            r = update_symbol(ex, symbol, a.timeframe, a.exchange)
            log_event("collect", {"job": "daily", "symbol": symbol, "timeframe": a.timeframe,
                                  "rows": r["rows"], "errors": r["errors"],
                                  "warnings": r["warnings"], "metrics": r["metrics"]})
            flag = " !" if r["errors"] else ""
            print(f"[{i}/{len(symbols)}] {symbol} +{r['rows']} satır{flag}")
        except Exception as exc:  # sembol düşer, koşu devam eder — ama sessizce değil
            failed.append(symbol)
            log_event("collect", {"job": "daily", "symbol": symbol, "timeframe": a.timeframe,
                                  "error": repr(exc), "traceback": traceback.format_exc()})
            print(f"[{i}/{len(symbols)}] {symbol} HATA: {exc!r} (logs/collect/)", file=sys.stderr)

    print(f"bitti: {len(symbols) - len(failed)}/{len(symbols)} sembol, {len(failed)} hata")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
