"""Göç birleştirmesi — sentetik iki kaynak (`docs/SERVER.md` "Veri birleştirme")."""
import pandas as pd

from scripts import birlestir as b

SEM = "BTC-USDT-USDT"
GECIS = pd.Timestamp("2026-10-08 12:00", tz="UTC")


def yaz(kok, tur, ad, df):
    p = kok / "data" / "bingx" / SEM / tur / f"{ad}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


def islem(ids, fiyat=100.0):
    return pd.DataFrame({"id": ids, "ts": pd.to_datetime([1_790_000_000_000 + i * 1000 for i in ids],
                                                         unit="ms", utc=True),
                         "price": fiyat, "qty": 1.0, "side": "buy"})


def defter(dakikalar, mid, saniye=0):
    ts = [GECIS + pd.Timedelta(minutes=m, seconds=saniye) for m in dakikalar]
    return pd.DataFrame({"ts": ts, "mid": mid})


def kur(tmp_path):
    return {"eski": tmp_path / "eski", "xeon": tmp_path / "xeon"}, tmp_path / "hedef"


def test_trades_union_fills_gap_and_reports(tmp_path):
    k, h = kur(tmp_path)
    yaz(k["eski"], "trades", "2026-10-08", islem([1, 2, 3, 6, 7]))  # 4-5 kayıp
    yaz(k["xeon"], "trades", "2026-10-08", islem([2, 3, 4, 5, 6]))
    s = b.birlestir(k, h, GECIS)
    out = pd.read_parquet(h / "data/bingx" / SEM / "trades/2026-10-08.parquet")
    assert out.id.tolist() == [1, 2, 3, 4, 5, 6, 7] and not s.hata
    r = s.trades[SEM]
    assert r["eksik"] == {"eski": 2, "xeon": 0, "birlesim": 0}
    assert r["tek_kaynak"] == {"eski": 2, "xeon": 2}
    assert r["ortak"] == 3  # 2, 3, 6: paralel kayıt kanıtı


def test_trades_conflict_is_error_and_file_not_written(tmp_path):
    k, h = kur(tmp_path)
    yaz(k["eski"], "trades", "2026-10-08", islem([1, 2]))
    yaz(k["xeon"], "trades", "2026-10-08", islem([2, 3], fiyat=101.0))
    s = b.birlestir(k, h, GECIS)
    assert list(s.hata) and not (h / "data/bingx" / SEM / "trades/2026-10-08.parquet").exists()


def test_existing_target_rows_are_kept(tmp_path):
    k, h = kur(tmp_path)
    yaz(h, "trades", "2026-10-08", islem([1]))  # yalnızca hedefte (eski çekimden)
    yaz(k["eski"], "trades", "2026-10-08", islem([2]))
    yaz(k["xeon"], "trades", "2026-10-08", islem([3]))
    s = b.birlestir(k, h, GECIS)
    assert pd.read_parquet(h / "data/bingx" / SEM / "trades/2026-10-08.parquet").id.tolist() == [1, 2, 3]
    assert s.trades[SEM]["ortak"] == 0  # hedefteki kopya paralel kayıt sayılmaz


def test_book_priority_flips_at_cutover_and_tags_host(tmp_path):
    k, h = kur(tmp_path)
    yaz(k["eski"], "book", "2026-10", defter([-2, -1, 0, 1], 1.0, saniye=5))
    yaz(k["xeon"], "book", "2026-10", defter([-1, 0, 1, 2], 2.0, saniye=40))
    s = b.birlestir(k, h, GECIS)
    out = pd.read_parquet(h / "data/bingx" / SEM / "book/2026-10.parquet")
    assert out.host.tolist() == ["eski", "eski", "xeon", "xeon", "xeon"]
    assert out.mid.tolist() == [1.0, 1.0, 2.0, 2.0, 2.0]
    assert s.ikili_dakika == 3 and not s.hata


def test_ohlcv_and_funding_conflict_is_error(tmp_path):
    k, h = kur(tmp_path)
    ts = pd.to_datetime(["2026-10-08 00:00", "2026-10-08 00:30"], utc=True)
    yaz(k["eski"], "30m", "2026-10", pd.DataFrame({"ts": ts, "close": [1.0, 2.0]}))
    yaz(k["xeon"], "30m", "2026-10", pd.DataFrame({"ts": ts[1:], "close": [2.5]}))
    yaz(k["eski"], "funding", "2026-10", pd.DataFrame({"ts": ts[:1], "funding_rate": [1e-4]}))
    yaz(k["xeon"], "funding", "2026-10", pd.DataFrame({"ts": ts, "funding_rate": [1e-4, 2e-4]}))
    s = b.birlestir(k, h, GECIS)
    assert list(s.hata) == ["data/bingx/BTC-USDT-USDT/30m/2026-10.parquet"]
    f = pd.read_parquet(h / "data/bingx" / SEM / "funding/2026-10.parquet")
    assert f.funding_rate.tolist() == [1e-4, 2e-4]


def test_second_run_is_noop_and_dry_run_writes_nothing(tmp_path):
    k, h = kur(tmp_path)
    yaz(k["eski"], "trades", "2026-10-08", islem([1, 2]))
    yaz(k["xeon"], "book", "2026-10", defter([0], 2.0))
    kuru = b.birlestir(k, h, GECIS, kuru=True)
    assert len(kuru.yazilan) == 2 and not (h / "data").exists()
    assert len(b.birlestir(k, h, GECIS).yazilan) == 2
    s = b.birlestir(k, h, GECIS)
    assert s.yazilan == [] and s.ayni == 2
