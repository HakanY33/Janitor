"""Gunluk `earliest_timestamp` kaydi — borsanin en eski mumu kayiyor mu (ARCHITECTURE.md §3.2).

    python -m scripts.earliest --symbols BTC/USDT:USDT ETH/USDT:USDT
    python -m scripts.earliest                    # liquidity.json'daki 20 sembol

Sunucuda `janitor-earliest.timer` gunde bir calistirir. Her (sembol, zaman dilimi) bir
satir olarak `logs/earliest/{tarih}.jsonl`'e yazilir (`collect.log_earliest`). Bir sembol
duserse digerleri surer; hata `logs/collect/`'e yazilir ve cikis kodu 1 olur.
"""
from __future__ import annotations

import argparse
import sys
import traceback

from src.data.collect import exchange, log_earliest, log_event


def main() -> int:
    p = argparse.ArgumentParser(description="Gunluk en eski mum kaydi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--timeframes", nargs="+", default=["1m", "30m"])
    a = p.parse_args()

    if a.symbols:
        symbols = a.symbols
    else:
        from scripts.measure_ob import liquidity_symbols
        symbols = liquidity_symbols(20)

    ex = exchange(a.exchange)
    hata = 0
    for s in symbols:
        for tf in a.timeframes:
            try:
                log_earliest(ex, s, tf)
            except Exception as exc:  # sembol duser, kayit surer — sessizce degil
                hata += 1
                log_event("collect", {"job": "earliest", "symbol": s, "timeframe": tf,
                                      "error": repr(exc), "traceback": traceback.format_exc()})
                print(f"{s} {tf} HATA: {exc!r}", file=sys.stderr)
    print(f"{len(symbols) * len(a.timeframes) - hata} kayit · {hata} hata")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
