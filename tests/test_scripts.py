"""Toplu indirme ve günlük artımlı toplama — kesintiden devam davranışı.

Ağa çıkılmaz; sahte borsa kullanılır (CLAUDE.md test kuralları).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import backfill, daily, measure_ob, spread_logger
from src.data import collect
from src.features.ob import detect_order_blocks, pierce_time

MINUTE = 60_000
START = int(pd.Timestamp("2026-01-15", tz="UTC").timestamp() * 1000)
N = 70 * 24 * 60  # ~2.3 ay: ocak/şubat/mart dosyaları oluşsun


class FakeExchange:
    """Sabit mum serisi tutan, sayfalayan sahte borsa. Çağrı sayısını sayar."""

    id = "fake"

    def __init__(self, start_ms: int = START, n: int = N):
        self.candles = [[start_ms + i * MINUTE, 1.0, 2.0, 0.5, 1.5, 10.0] for i in range(n)]
        self.now = start_ms + n * MINUTE
        self.calls = 0

    def milliseconds(self):
        return self.now

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        self.calls += 1
        return [c for c in self.candles if since is None or c[0] >= since][:limit]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(collect, "LOG_ROOT", tmp_path / "logs")
    return tmp_path


def _rows(sandbox, tf="1m"):
    return len(collect.read_parquet("fake", "NEAR/USDT:USDT", tf))


def test_backfill_tamamlanan_aylari_atlar_ve_kaldigi_yerden_devam_eder(sandbox):
    ex = FakeExchange()
    first = backfill.backfill_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")
    assert first["rows"] == N and first["skipped"] == 0
    assert _rows(sandbox) == N

    # İkinci koşu: her ay diskte tam, hiçbir mum tekrar inmez
    ex.calls = 0
    again = backfill.backfill_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")
    assert again["rows"] == 0 and again["skipped"] == again["months"]
    assert _rows(sandbox) == N

    # Kesinti benzetimi: bir ay dosyası yarım kalmış
    path = collect.month_path("fake", "NEAR/USDT:USDT", "1m", "2026-02")
    full = pd.read_parquet(path)
    full.head(len(full) - 500).to_parquet(path, index=False)  # son 500 mum inmemiş

    ex.calls = 0
    resumed = backfill.backfill_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")
    assert resumed["skipped"] == resumed["months"] - 1  # yalnızca o ay yeniden indi
    assert _rows(sandbox) == N  # mükerrer satır yok, eksik kapandı
    # Yarım ay baştan inmez: şubatın tamamı ~40k mum, yalnızca eksik 500'ü çekilir
    assert resumed["rows"] == 500 and ex.calls <= 5  # earliest probe + tek sayfa


def test_backfill_earliest_her_kosuda_loglanir(sandbox):
    ex = FakeExchange()
    backfill.backfill_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")
    backfill.backfill_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")

    logs = list((sandbox / "logs" / "earliest").glob("*.jsonl"))
    assert len(logs) == 1  # gün başına bir dosya, append-only
    lines = logs[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert pd.Timestamp("2026-01-15", tz="UTC").isoformat() in lines[0]


def test_daily_diskteki_son_mumdan_devam_eder(sandbox):
    ex = FakeExchange()
    half = N // 2
    collect.write_parquet(
        collect.fetch_ohlcv(ex, "NEAR/USDT:USDT", "1m", since=START, until=START + half * MINUTE),
        "fake", "NEAR/USDT:USDT", "1m",
    )
    assert _rows(sandbox) == half

    r = daily.update_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")
    assert r["rows"] == N - half  # yalnızca eksik kuyruk çekildi
    assert _rows(sandbox) == N
    assert r["errors"] == {} and r["metrics"]["zero_volume_ratio"] == 0.0

    # Güncel koşu: çekecek yeni mum yok
    assert daily.update_symbol(ex, "NEAR/USDT:USDT", "1m", "fake")["rows"] == 0


# --- measure_ob · OPEN-23 ölçüm scripti -------------------------------------

def _walk(n: int = 600, seed: int = 7) -> pd.DataFrame:
    """Rastgele yürüyüşten 30m mumlar. Ölçüm kısayollarını sınamaya yeter."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    open_ = np.r_[100.0, close[:-1]]
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="30min", tz="UTC"),
        "open": open_, "close": close,
        "high": np.maximum(open_, close) + rng.random(n) * 0.3,
        "low": np.minimum(open_, close) - rng.random(n) * 0.3,
        "volume": 1.0,
    })


def test_measure_pierce_within_genis_ufukta_pierce_time_ile_ayni():
    """Ufuk penceresi yalnızca hızlandırmadır: sonuç üretim fonksiyonuyla birebir olmalı.

    Pencere `BODY_LOOKBACK` mum geriden başlıyor; kısalması `reference_body` medyanını
    kaydırsaydı delinme kararı sessizce değişirdi.
    """
    df = _walk()
    obs = detect_order_blocks(df, "TEST/USDT:USDT", "30m")
    idx = {ts: i for i, ts in enumerate(df.ts)}
    assert obs
    assert [measure_ob.pierce_within(ob, df, idx[ob.impulse_at], len(df)) for ob in obs] == [
        pierce_time(ob, df) for ob in obs
    ]


def test_measure_htf_yon_bilinme_ani_4h_mumun_kapanisidir():
    """4h kapanış, `known_at`ten **önceki** 30m mumlardan gelmeli (CLAUDE.md #3)."""
    df = _walk(n=600)
    kapanis = df.set_index("ts").close
    for row in measure_ob.htf_yon(df).itertuples():
        pencere = kapanis[(kapanis.index >= row.known_at - pd.Timedelta("4h"))
                          & (kapanis.index < row.known_at)]
        assert row.close == pencere.iloc[-1]


# --- emir defteri kayitcisi ---------------------------------------------------

TS = pd.Timestamp("2026-01-01 12:00", tz="UTC")
BOOK = {"bids": [[99.0, 5.0], [98.0, 7.0], [97.0, 9.0]],
        "asks": [[101.0, 4.0], [102.0, 6.0], [103.0, 8.0], [104.0, 2.0],
                 [105.0, 1.0], [106.0, 3.0]]}


def test_spread_logger_satiri_spread_ve_kademeleri_tasir():
    """mid 100, spread 2 -> 200 bps. Kademeler sirayla, 5'ten fazlasi atilir."""
    r = spread_logger.row("TEST/USDT:USDT", BOOK, TS)
    assert (r["bid"], r["ask"], r["mid"]) == (99.0, 101.0, 100.0)
    assert r["spread_bps"] == pytest.approx(200.0)
    assert (r["bid_p1"], r["bid_q1"]) == (99.0, 5.0)
    assert (r["ask_p5"], r["ask_q5"]) == (105.0, 1.0)
    assert "ask_p6" not in r  # DEPTH kadar kademe, daha fazlasi degil


def test_spread_logger_sig_defterde_eksik_kademe_nan_kalir():
    """Sifir yazmak 'derinlik yok' ile 'kademe gelmedi'yi karistirirdi."""
    r = spread_logger.row("TEST/USDT:USDT", BOOK, TS)
    assert np.isnan(r["bid_p4"]) and np.isnan(r["bid_q4"])  # alis tarafi 3 kademe


def test_spread_logger_bos_defter_sessizce_gecilmez():
    with pytest.raises(ValueError, match="emir defteri bos"):
        spread_logger.row("TEST/USDT:USDT", {"bids": [], "asks": BOOK["asks"]}, TS)
