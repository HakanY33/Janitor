"""H2 işlem kuralları (`docs/HYPOTHESES.md` §8.1), sentetik 1m. Ağ yok."""
import numpy as np
import pandas as pd

from scripts.h2_kesif import islem
from src.features.fvg import BULLISH
from src.features.ob import OrderBlock

T0 = pd.Timestamp("2026-01-01 04:00", tz="UTC")
OB = OrderBlock("ob", "X", "4h", BULLISH, top=100.0, bottom=99.0,
                created_at=T0 - pd.Timedelta("8h"), impulse_at=T0 - pd.Timedelta("4h"))
TICK = 0.1  # giriş 100 · stop 98.9 · R 1.1 · TP 102.2


def kos(bars, kapanis=105.0):
    ts = np.array([np.datetime64((T0 + pd.Timedelta(minutes=i)).tz_localize(None)) for i in range(len(bars))])
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*bars))
    return islem(OB, kapanis, TICK, ts, o, h, l, c)


def test_H2_tp_after_fill():
    x = kos([(104, 104, 103, 103.5), (101, 101, 99.8, 100.5), (101, 102.4, 100.5, 102)])
    assert x.neden == "TP" and x.cikis == x.tp and abs(x.tp - 102.2) < 1e-9


def test_H2_touch_without_tick_cancels():
    assert kos([(101, 101, 100.0, 100.5), (100.5, 100.5, 95, 96)]) == "dolmadi"


def test_H2_fill_and_stop_same_bar_is_stop():
    x = kos([(101, 101, 98.0, 98.5), (98.5, 110, 98, 109)])
    assert x.neden == "STOP" and x.cikis_i == 0


def test_H2_tp_and_stop_same_bar_is_stop():
    x = kos([(101, 101, 99.8, 100.5), (100.5, 103, 98, 100)])
    assert x.neden == "STOP"


def test_H2_gap_stop_fills_at_open():
    x = kos([(101, 101, 99.8, 100.5), (97, 97.5, 96, 97)])
    assert x.neden == "STOP" and x.cikis == 97


def test_H2_post_only_rejected_when_price_already_at_edge():
    assert kos([(100, 101, 99.5, 100)], kapanis=100.0) == "post_only_red"


def test_H2_open_at_end():
    x = kos([(101, 101, 99.8, 100.5), (100.5, 101, 100, 100.8)])
    assert x.neden == "ACIK" and x.cikis == 100.8
