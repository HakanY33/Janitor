"""Toplu geçmiş indirme — kesintiye dayanıklı.

Spec: ARCHITECTURE.md §3.2 (veri penceresi zaman duyarlı).

    python -m scripts.backfill --timeframe 1m              # tüm universe (~9 GB)
    python -m scripts.backfill --limit 10                  # önce küçük bir dilim dene
    python -m scripts.backfill --symbols NEAR/USDT:USDT

İlerleme diskte tutulur, ayrı bir durum dosyası yoktur: her sembol ay ay indirilir ve
her ay yazıldıktan sonra tamamlanmış sayılır. Ctrl-C veya kopan bağlantıdan sonra aynı
komut kaldığı yerden devam eder — tamamlanmış aylar tekrar indirilmez. 9 GB tek seferde
inmek zorunda değildir.

Her sembolde `earliest_timestamp` ölçülür ve logs/earliest/ altına yazılır: pencerenin
gerçekten kaydığı ancak günlük kayıtla doğrulanabilir.

Doğrulama burada çalışmaz (toplu indirme yeterince uzun); veri kalitesi kontrolü
ayrı koşulur.
"""
from __future__ import annotations

import argparse
import sys
import traceback

import pandas as pd

from src.data.collect import (
    exchange,
    fetch_ohlcv,
    load_universe,
    log_earliest,
    log_event,
    month_path,
    write_parquet,
)


def _stored_last(path) -> pd.Timestamp | None:
    """Ay dosyasındaki son mumun zamanı; dosya yoksa None.

    ponytail: yalnızca kuyruk bakılır. Ortadaki boşluklar (borsa kesintisi) ayı "eksik"
    saymaz — yoksa gappy her sembol her koşuda baştan inerdi. Boşluk raporlamak
    validate.check_no_gaps'in işi.
    """
    if not path.exists():
        return None
    ts = pd.read_parquet(path, columns=["ts"]).ts
    return None if ts.empty else ts.max()


def backfill_symbol(ex, symbol: str, timeframe: str, exchange_name: str) -> dict:
    """Bir sembolün tüm geçmişini ay ay indirir. Tamamlanmış ayları atlar."""
    step = int(pd.Timedelta(timeframe).total_seconds() * 1000)
    first_ms = log_earliest(ex, symbol, timeframe)
    last_ms = (ex.milliseconds() // step) * step - step  # son *kapanmış* mum
    months = pd.period_range(
        pd.Timestamp(first_ms, unit="ms", tz="UTC").strftime("%Y-%m"),
        pd.Timestamp(last_ms, unit="ms", tz="UTC").strftime("%Y-%m"),
        freq="M",
    )

    rows, done = 0, 0
    for m in months:
        m_start = int(pd.Timestamp(m.start_time, tz="UTC").timestamp() * 1000)
        m_end = int(pd.Timestamp((m + 1).start_time, tz="UTC").timestamp() * 1000)
        want_first, want_last = max(m_start, first_ms), min(m_end - step, last_ms)
        stored = _stored_last(month_path(exchange_name, symbol, timeframe, str(m)))
        if stored is not None and stored >= pd.Timestamp(want_last, unit="ms", tz="UTC"):
            done += 1
            continue
        # Yarım kalan ay baştan inmez: diskteki son mumdan devam edilir.
        since = max(want_first, int(stored.timestamp() * 1000) + step) if stored is not None else want_first
        df = fetch_ohlcv(ex, symbol, timeframe, since=since, until=m_end)
        if df.empty:
            continue
        write_parquet(df, exchange_name, symbol, timeframe)  # ay bitince diske: kesinti güvenli
        rows += len(df)
    return {"rows": rows, "months": len(months), "skipped": done,
            "earliest": pd.Timestamp(first_ms, unit="ms", tz="UTC")}


def main() -> int:
    p = argparse.ArgumentParser(description="Universe için toplu OHLCV indirme")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--symbols", nargs="+", help="Verilmezse universe anlık görüntüsü kullanılır")
    p.add_argument("--as-of", help="Kullanılacak universe günü (yyyy-mm-dd), varsayılan en yenisi")
    p.add_argument("--limit", type=int, help="Yalnızca ilk N sembol")
    a = p.parse_args()

    ex = exchange(a.exchange)
    if a.symbols:
        symbols = a.symbols
    else:
        universe = load_universe(a.exchange, a.as_of)
        symbols = universe["symbols"]
        print(f"universe {universe['path']} — {len(symbols)} sembol")
    symbols = symbols[: a.limit] if a.limit else symbols

    failed = []
    for i, symbol in enumerate(symbols, 1):
        try:
            r = backfill_symbol(ex, symbol, a.timeframe, a.exchange)
            print(f"[{i}/{len(symbols)}] {symbol} +{r['rows']} satır "
                  f"({r['skipped']}/{r['months']} ay zaten vardı, en eski {r['earliest']:%Y-%m-%d})")
        except Exception as exc:  # sembol düşer, koşu devam eder — ama sessizce değil
            failed.append(symbol)
            log_event("collect", {"job": "backfill", "symbol": symbol, "timeframe": a.timeframe,
                                  "error": repr(exc), "traceback": traceback.format_exc()})
            print(f"[{i}/{len(symbols)}] {symbol} HATA: {exc!r} (logs/collect/)", file=sys.stderr)

    print(f"bitti: {len(symbols) - len(failed)}/{len(symbols)} sembol, {len(failed)} hata")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
