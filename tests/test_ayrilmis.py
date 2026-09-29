"""`scripts/ayrilmis.py` · kesimden once giris dolmaz, zone isinir."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from scripts.ayrilmis import Ayrilmis
from src.backtest.engine import Backtest
from tests.test_backtest import short_zone, symbol_data
from tests.test_levers import free_costs

# 0.50 -> PRIMED, 0.70 teması (dolar), sonra fiyat 0.70 civarinda, sonra nihai TP.
YOL = [(152, 148), (172, 168), (160, 150), (172, 168), (152, 148), (102, 98)]


def kos(kesim_dk: int | None):
    z = short_zone()
    sd = symbol_data(YOL, z)
    kw = dict(k=Decimal("0.2"), limit_orders=True, max_adds=0)
    if kesim_dk is None:
        return Backtest([sd], free_costs("1"), **kw).run()
    kesim = pd.Timestamp(z.watch_from) + pd.Timedelta(minutes=kesim_dk)
    return Ayrilmis([sd], free_costs("1"), kesim=kesim, **kw).run()


def test_ayrilmis_kesimden_once_giris_dolmaz_sonra_bekleyen_emir_dolar():
    ref = kos(None)
    res = kos(2)  # 2. mum (i=1) kesimden once
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.entry_ts >= pd.Timestamp(short_zone().watch_from) + pd.Timedelta(minutes=2)
    assert t.entry_price == Decimal("170")  # kesim oncesi kurulan limit
    assert pd.Timestamp(ref.trades[0].entry_ts) < pd.Timestamp(t.entry_ts)


def test_ayrilmis_kesim_basta_ise_motorla_ayni():
    a, b = kos(None), kos(0)
    assert [(t.entry_ts, t.pnl) for t in a.trades] == [(t.entry_ts, t.pnl) for t in b.trades]
