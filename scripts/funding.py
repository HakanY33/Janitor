"""Funding oranı geçmişi indirici.

Spec: §8 "Funding rate geçmişi zorunlu" (R-EXIT-03 haftalarca taşınan pozisyon).

    python -m scripts.funding --symbols NEAR/USDT:USDT
    python -m scripts.funding                      # liquidity.json'daki 20 sembol

**Borsa sınırı — ölçüldü, varsayılmadı.** BingX `fetch_funding_rate_history` çağrısı en
fazla 1000 kayıt döndürüyor ve `since` parametresini yok sayıyor: hangi başlangıç
verilirse verilsin aynı pencere geliyor (≈1000 × 8s ≈ 333 gün). Yani funding geçmişi
OHLCV geçmişinden **kısa** ve geriye doğru uzatılamıyor. Backtest bu boşluğu
maliyet modelinde açıkça işler ve ölçülen/atanan ayrımını raporlar
(`src/backtest/costs.py`), sessizce sıfır kabul etmez (CLAUDE.md #8).

Veri düzeni OHLCV ile aynı: `data/{exchange}/{symbol}/funding/{yyyy-mm}.parquet`,
kolonlar `ts` (funding anı, UTC) ve `funding_rate`.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import ccxt
import pandas as pd

from src.data.collect import exchange, log_event, write_parquet

TIMEFRAME = "funding"  # depolama düzeninde "zaman dilimi" yuvası


def fetch_funding(ex, symbol: str, limit: int = 1000) -> pd.DataFrame:
    """Borsanın verdiği tüm funding geçmişi. `ts` sıralı, mükerrersiz."""
    rows = ex.fetch_funding_rate_history(symbol, limit=limit)
    df = pd.DataFrame(
        [{"ts": r["timestamp"], "funding_rate": float(r["fundingRate"])} for r in rows]
    )
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df.ts, unit="ms", utc=True)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def write_fees(ex, exchange_name: str, symbols: list[str]) -> Path:
    """Borsanın yayınladığı taker/maker oranlarını ve fiyat adımını yazar (CLAUDE.md #5).

    Komisyon kodda elle yazılmaz; backtest bu dosyayı okur (`src/backtest/costs.py`).
    Dosya yoksa backtest komisyonu tahmin etmez, hata verir.

    `tick` = `precision["price"]`. BingX `precisionMode` TICK_SIZE olduğu için bu değer
    doğrudan fiyat adımıdır; ondalık basamak sayısı değildir. Limit emri kolunun
    "seviyeyi 1 tick geç" kuralı bunu okur — elle yazılmış hassasiyet tablosu yok.
    """
    path = Path("data") / exchange_name / "fees.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if ex.precisionMode != ccxt.TICK_SIZE:
        raise RuntimeError(
            f"{exchange_name}: precisionMode {ex.precisionMode}, TICK_SIZE degil — "
            "precision['price'] fiyat adimi olarak okunamaz"
        )
    fees = {}
    for s in symbols:
        m = ex.market(s)
        fees[s] = {"taker": float(m["taker"]), "maker": float(m["maker"]),
                   "tick": float(m["precision"]["price"])}
    path.write_text(json.dumps(
        {"as_of": pd.Timestamp.now("UTC").isoformat(), "fees": fees}, indent=1
    ), encoding="utf-8")
    print(f"komisyon oranları -> {path}")
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="Funding oranı geçmişi indirme")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--fees-only", action="store_true",
                   help="yalnizca fees.json (komisyon + fiyat adimi); funding indirme")
    a = p.parse_args()

    if a.symbols:
        symbols = a.symbols
    else:
        from scripts.measure_ob import liquidity_symbols
        symbols = liquidity_symbols(20)

    ex = exchange(a.exchange)
    write_fees(ex, a.exchange, symbols)
    if a.fees_only:
        return 0
    failed = []
    for i, symbol in enumerate(symbols, 1):
        try:
            df = fetch_funding(ex, symbol)
            if df.empty:
                print(f"[{i}/{len(symbols)}] {symbol} kayıt yok", file=sys.stderr)
                continue
            write_parquet(df, a.exchange, symbol, TIMEFRAME)
            print(f"[{i}/{len(symbols)}] {symbol} {len(df):,} kayıt "
                  f"{df.ts.iloc[0]:%Y-%m-%d} -> {df.ts.iloc[-1]:%Y-%m-%d}")
        except Exception as exc:  # sembol düşer, koşu devam eder — sessizce değil
            failed.append(symbol)
            log_event("collect", {"job": "funding", "symbol": symbol,
                                  "error": repr(exc), "traceback": traceback.format_exc()})
            print(f"[{i}/{len(symbols)}] {symbol} HATA: {exc!r}", file=sys.stderr)

    print(f"bitti: {len(symbols) - len(failed)}/{len(symbols)} sembol")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
