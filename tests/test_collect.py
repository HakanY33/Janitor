"""Toplayıcı ve Parquet yazıcı testleri. Ağa çıkılmaz — sahte borsa kullanılır."""
from __future__ import annotations

import pandas as pd

from src.data import collect
from src.data.collect import fetch_ohlcv, read_parquet, write_parquet

MINUTE = 60_000


class FakeExchange:
    """Sabit bir mum serisi tutan, sayfalayan sahte borsa."""

    def __init__(self, start_ms: int, n: int, now_ms: int):
        self.candles = [[start_ms + i * MINUTE, 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n)]
        self.now = now_ms
        self.calls = 0

    def milliseconds(self):
        return self.now

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        self.calls += 1
        return [c for c in self.candles if since is None or c[0] >= since][:limit]


def test_fetch_kapanmamis_mumu_atar():
    """CLAUDE.md #3: karar anında kapanmamış mum veriye girmez."""
    start = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp() * 1000)
    # 10 mum var, şu an 9. mumun ortası: o mum henüz kapanmadı
    ex = FakeExchange(start, 10, now_ms=start + 9 * MINUTE + 30_000)
    df = fetch_ohlcv(ex, "NEAR/USDT:USDT", "1m", since=start)
    assert len(df) == 9
    assert df.ts.max() == pd.Timestamp("2026-01-01 00:08:00", tz="UTC")


def test_fetch_sayfalar_ve_sonsuz_donguye_girmez():
    start = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp() * 1000)
    ex = FakeExchange(start, 2500, now_ms=start + 3000 * MINUTE)
    df = fetch_ohlcv(ex, "NEAR/USDT:USDT", "1m", since=start)
    assert len(df) == 2500  # borsa veriyi tüketince döngü durur
    assert df.ts.is_monotonic_increasing and not df.ts.duplicated().any()


def test_parquet_aya_boler_ve_birlestirirken_mukerrer_yazmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "DATA_ROOT", tmp_path)
    ts = pd.date_range("2026-01-31 23:55", periods=10, freq="1min", tz="UTC")
    df = pd.DataFrame({"ts": ts, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 3.0})

    assert len(write_parquet(df, "bingx", "NEAR/USDT:USDT", "1m")) == 2  # ocak + şubat
    write_parquet(df, "bingx", "NEAR/USDT:USDT", "1m")  # aynı veri ikinci kez

    back = read_parquet("bingx", "NEAR/USDT:USDT", "1m")
    assert len(back) == 10
    assert back.ts.tolist() == list(ts)
