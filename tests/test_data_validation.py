"""ARCHITECTURE.md §3 — zorunlu veri doğrulama testleri.

Yedi kontrolün her biri için: temiz veri geçer, bozuk veri yakalanır.
Ağa çıkılmaz; tüm veri sentetiktir.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data.validate import (
    check_no_gaps,
    check_no_duplicates,
    check_no_zero_volume_runs,
    check_ohlc_sanity,
    check_price_jumps,
    check_symbol_survivorship,
    check_utc,
    validate_ohlcv,
)


def frame(n=10, start="2026-01-01", timeframe="1m", price=100.0, volume=5.0):
    ts = pd.date_range(start, periods=n, freq=pd.Timedelta(timeframe), tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": volume,
        }
    )


def test_no_gaps():
    df = frame(10)
    assert check_no_gaps(df, "1m") == []

    gapped = df.drop(index=[4, 5]).reset_index(drop=True)
    missing = check_no_gaps(gapped, "1m")
    assert missing == [df.ts[4], df.ts[5]]


def test_utc():
    assert check_utc(frame()) == []

    naive = frame()
    naive["ts"] = naive.ts.dt.tz_localize(None)
    assert check_utc(naive) == ["ts tz-naive"]

    istanbul = frame()
    istanbul["ts"] = istanbul.ts.dt.tz_convert("Europe/Istanbul")
    assert check_utc(istanbul) == ["ts tz=Europe/Istanbul, UTC değil"]


def test_no_duplicates():
    df = frame(5)
    assert check_no_duplicates(df) == []

    dupe = pd.concat([df, df.iloc[[2]]], ignore_index=True).sort_values("ts")
    assert check_no_duplicates(dupe) == [df.ts[2]]


def test_ohlc_sanity():
    df = frame(5)
    assert check_ohlc_sanity(df) == []

    # low > close: geçersiz mum
    bad = frame(5)
    bad.loc[3, "low"] = bad.loc[3, "close"] + 10
    assert check_ohlc_sanity(bad) == [bad.ts[3]]

    # high < open: geçersiz mum
    bad2 = frame(5)
    bad2.loc[1, "high"] = bad2.loc[1, "open"] - 10
    assert check_ohlc_sanity(bad2) == [bad2.ts[1]]


def test_no_zero_volume_runs():
    df = frame(10)
    assert check_no_zero_volume_runs(df, max_run=3) == []

    # 3 ardışık sıfır: eşiğe eşit, henüz ihlal değil
    df.loc[[4, 5, 6], "volume"] = 0.0
    assert check_no_zero_volume_runs(df, max_run=3) == []

    # 4 ardışık sıfır: ihlal, serinin başlangıcı raporlanır
    df.loc[7, "volume"] = 0.0
    assert check_no_zero_volume_runs(df, max_run=3) == [(df.ts[4], 4)]


def test_price_jumps():
    df = frame(5)
    assert check_price_jumps(df, max_pct=10.0) == []

    # Tek mumluk kötü tick: hem sıçrama hem geri dönüş yakalanır
    df.loc[3, ["open", "high", "low", "close"]] = 200.0
    assert check_price_jumps(df, max_pct=10.0) == [
        (df.ts[3], pytest.approx(100.0)),
        (df.ts[4], pytest.approx(50.0)),
    ]


def test_symbol_survivorship():
    universe = {"as_of": pd.Timestamp("2024-01-01", tz="UTC"), "symbols": ["NEAR/USDT:USDT"]}

    # Liste, pencere başlangıcında zaten mevcut → geçerli
    assert check_symbol_survivorship(universe, "NEAR/USDT:USDT", pd.Timestamp("2024-06-01", tz="UTC")) == []

    # Bugünün listesiyle geçmişi test etmek → survivorship bias
    assert check_symbol_survivorship(universe, "NEAR/USDT:USDT", pd.Timestamp("2023-01-01", tz="UTC")) == [
        "universe as_of=2024-01-01 00:00:00+00:00 > pencere başlangıcı 2023-01-01 00:00:00+00:00"
    ]

    # Sembol o tarihteki listede yok
    assert check_symbol_survivorship(universe, "FTT/USDT:USDT", pd.Timestamp("2024-06-01", tz="UTC")) == [
        "FTT/USDT:USDT, as_of=2024-01-01 00:00:00+00:00 listesinde yok"
    ]


def test_validate_ohlcv_toplar_tum_ihlalleri():
    df = frame(10)
    df.loc[3, "low"] = 999.0
    result = validate_ohlcv(df.drop(index=[6]).reset_index(drop=True), "1m")
    assert result["ohlc_sanity"] and result["no_gaps"]
    assert result["utc"] == [] and result["no_duplicates"] == []
