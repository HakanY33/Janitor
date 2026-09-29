"""`scripts/trades_logger.py` · bosluk sayimi, id tekillestirme, dakika deltasi."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import trades_logger as tl
from src.data import collect


def islem(i, ms, side="buy", qty=1.0):
    return {"info": {"fillId": str(i)}, "timestamp": ms, "price": 100.0, "amount": qty,
            "side": side}


class Borsa:
    def __init__(self, *partiler):
        self.partiler = list(partiler)

    def fetch_trades(self, symbol, limit):
        return self.partiler.pop(0)


def test_trades_logger_kimlik_atlarsa_kacirilan_sayilir():
    ex = Borsa([islem(1, 0), islem(2, 0)], [islem(2, 0), islem(3, 0)], [islem(7, 0)])
    df, son, k = tl.poll(ex, "X", None)
    assert (len(df), son, k) == (2, 2, 0)
    df, son, k = tl.poll(ex, "X", son)
    assert (list(df.id), son, k) == ([3], 3, 0)  # ortusen islem tekrar yazilmaz
    df, son, k = tl.poll(ex, "X", son)
    assert (son, k) == (7, 3)


def test_trades_logger_fillid_yoksa_sessizce_gecilmez():
    with pytest.raises(KeyError):
        tl.rows([{"info": {}, "timestamp": 0, "price": 1, "amount": 1, "side": "buy"}])


def test_trades_logger_yazim_id_ile_tekillesir_ve_son_id_okunur(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "DATA_ROOT", tmp_path)
    tl.flush(tl.rows([islem(1, 0), islem(2, 1)]), "bingx", "X/USDT:USDT")
    tl.flush(tl.rows([islem(2, 1), islem(3, 1)]), "bingx", "X/USDT:USDT")  # ayni ms, farkli id
    d = pd.read_parquet(tmp_path / "bingx" / "X-USDT-USDT" / "trades" / "1970-01-01.parquet")
    assert list(d.id) == [1, 2, 3]
    assert tl.last_id("bingx", "X/USDT:USDT") == 3


def test_trades_logger_dakika_deltasi_ve_kumulatif():
    dk = 60_000
    d = tl.minute_delta(tl.rows([islem(1, 0, "buy", 3), islem(2, 1, "sell", 1),
                                 islem(3, 2 * dk, "sell", 5)]))
    assert list(d.delta) == [2, 0, -5]  # islemsiz dakika 0
    assert list(d.cum_delta) == [2, 2, -3]
    assert list(d.n) == [2, 0, 1]
