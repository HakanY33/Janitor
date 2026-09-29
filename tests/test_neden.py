"""`scripts/neden.py` · ayristirma tutarliligi ve eski emir isareti."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from scripts.neden import Izli, karsi_olgu, ozet
from tests.test_ayrilmis import YOL
from tests.test_backtest import short_zone, symbol_data
from tests.test_levers import free_costs


def tablo(b, f):
    return pd.DataFrame({"notional": [100.0] * len(b), "b": b, "f": f, "pnl": b,
                         "funding": 0.0, "tp1": False, "reason": "STOP", "leg_pct": 0.01})


def test_neden_ayristirma_uclari_gercek_orana_esit():
    e, h = ozet(tablo([3.0, -1.0, 2.0], [1.0, 1.0, 1.0])), ozet(tablo([1.0, -2.0], [2.0, 1.0]))
    k = karsi_olgu(e, h)
    assert k["egitim"] == pytest.approx(e["oran"]) == pytest.approx(4 / 3)
    assert k["ayrilmis"] == pytest.approx(h["oran"]) == pytest.approx(-1 / 3)


def test_neden_kesimden_once_kurulan_emir_eski_isaretlenir():
    z = short_zone()
    kw = dict(k=Decimal("0.2"), limit_orders=True, max_adds=0)
    kesim = pd.Timestamp(z.watch_from) + pd.Timedelta(minutes=2)
    bt = Izli([symbol_data(YOL, z)], free_costs("1"), kesim=kesim, **kw)
    res = bt.run()
    assert len(res.trades) == 1 and res.trades[0].zone_id in bt.eski
