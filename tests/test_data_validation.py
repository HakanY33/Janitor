"""ARCHITECTURE.md §3 — zorunlu veri doğrulama testleri.

Yedi kontrolün her biri için: temiz veri geçer, bozuk veri yakalanır.
Ağa çıkılmaz; tüm veri sentetiktir.
"""
from __future__ import annotations

import numpy as np
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
    zero_volume_ratio,
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


def noisy_frame(n=300, seed=0, sigma=0.001, price=100.0):
    """Gerçekçi oynaklığa sahip seri — sabit eşik yerine sigma katı test edilebilsin."""
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": close, "high": close * 1.001,
                         "low": close * 0.999, "close": close, "volume": 5.0})


def test_no_zero_volume_runs_varsayilan_esik_10():
    """§3.1: düşük likiditede birkaç sıfır hacimli mum normaldir, eşik 10."""
    df = frame(30)
    df.loc[list(range(4, 14)), "volume"] = 0.0  # 10 ardışık: eşiğe eşit, ihlal değil
    assert check_no_zero_volume_runs(df) == []

    df.loc[14, "volume"] = 0.0  # 11 ardışık: uyarı
    assert check_no_zero_volume_runs(df) == [(df.ts[4], 11)]


def test_no_zero_volume_runs():
    df = frame(10)
    assert check_no_zero_volume_runs(df, max_run=3) == []

    # 3 ardışık sıfır: eşiğe eşit, henüz ihlal değil
    df.loc[[4, 5, 6], "volume"] = 0.0
    assert check_no_zero_volume_runs(df, max_run=3) == []

    # 4 ardışık sıfır: ihlal, serinin başlangıcı raporlanır
    df.loc[7, "volume"] = 0.0
    assert check_no_zero_volume_runs(df, max_run=3) == [(df.ts[4], 4)]


def test_zero_volume_ratio_metrik_olarak_doner():
    """§3.1: oran ihlal değil, sembol eleme metriğidir."""
    df = frame(10)
    assert zero_volume_ratio(df) == 0.0
    df.loc[[1, 3], "volume"] = 0.0
    assert zero_volume_ratio(df) == pytest.approx(0.2)


def test_price_jumps_kotu_tick_yakalanir_gercek_hareket_yakalanmaz():
    """§3.1: ayırt edici olan büyüklük değil kalıcılık."""
    df = noisy_frame()
    assert check_price_jumps(df) == []

    # Kötü tick: tek mum sıçrar, hemen geri döner
    tick = df.copy()
    tick.loc[200, ["open", "high", "low", "close"]] *= 1.15
    flagged = check_price_jumps(tick)
    assert [ts for ts, _, _ in flagged] == [tick.ts[200]]
    _, pct, z = flagged[0]
    assert pct == pytest.approx(15.0, abs=0.1) and z > 10

    # Aynı büyüklükte gerçek hareket: yeni seviyede kalır, ihlal değil
    real = df.copy()
    real.loc[200:, ["open", "high", "low", "close"]] *= 1.15
    assert check_price_jumps(real) == []


def test_price_jumps_esik_sembolun_kendi_oynakligina_gore():
    """§3.1: BTC ile memecoin aynı eşikle ölçülmez — sabit yüzde yok."""
    # %2'lik kötü tick: sakin seride ihlal, oynak seride gürültü
    calm = noisy_frame(sigma=0.0005)
    calm.loc[200, ["open", "high", "low", "close"]] *= 1.02
    assert len(check_price_jumps(calm)) == 1

    wild = noisy_frame(sigma=0.01)
    wild.loc[200, ["open", "high", "low", "close"]] *= 1.02
    assert check_price_jumps(wild) == []


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


def test_validate_ohlcv_hata_uyari_metrik_ayrisir():
    """§3.1: sıfır hacim veriyi kullanılamaz yapmaz, hata listesine girmez."""
    df = frame(30)
    df.loc[3, "low"] = 999.0
    df.loc[list(range(10, 25)), "volume"] = 0.0
    result = validate_ohlcv(df.drop(index=[6]).reset_index(drop=True), "1m")

    assert result["errors"]["ohlc_sanity"] and result["errors"]["no_gaps"]
    assert result["errors"]["utc"] == [] and result["errors"]["no_duplicates"] == []
    assert result["warnings"]["zero_volume_runs"]  # uyarı, hata değil
    assert "zero_volume_runs" not in result["errors"]
    assert result["metrics"]["zero_volume_ratio"] == pytest.approx(15 / 29)
