"""`scripts/suzgec_31.py` eşik hesapları — S2 (düz piyasa) ve S3 (zayıf zigzag).

Sentetik veri: motor diskten/ağdan bağımsız sınanır (CLAUDE.md "ağa çıkan test yazılmaz").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.suzgec_31 import leg_verimliligi, otuz_dakika_kapanis, vol_block_for


class _SD:
    def __init__(self, ts, close):
        self.ts, self.close = ts, close


class _Zone:
    def __init__(self, a0_time, a0_price, a1_time, a1_price):
        self.anchor_0_time, self.anchor_0_price = a0_time, a0_price
        self.anchor_1_time, self.anchor_1_price = a1_time, a1_price


def test_S2_dusuk_hacimli_gun_girisin_24s_oncesinde_bayrak_acar():
    """35 gün düz hacim (1/dk), 34. gün çok düşük → o günün son dakikası bloklu."""
    idx = pd.date_range("2026-01-01", periods=35 * 24 * 60, freq="1min")
    vol = np.ones(len(idx))
    duz_gun = pd.Timestamp("2026-01-01") + pd.Timedelta(days=33)
    maske = (idx >= duz_gun) & (idx < duz_gun + pd.Timedelta(days=1))
    vol[maske] = 0.01
    ts = idx.values.astype("datetime64[ns]")
    _, blok = vol_block_for(ts, vol)
    assert blok[np.where(maske)[0][-1]]  # düşük hacimli günün sonunda bayrak açık


def test_S2_normal_gunde_ve_ilk_30_gunde_bayrak_kapali():
    idx = pd.date_range("2026-01-01", periods=35 * 24 * 60, freq="1min")
    vol = np.ones(len(idx))
    _, blok = vol_block_for(idx.values.astype("datetime64[ns]"), vol)
    assert not blok[2 * 24 * 60:3 * 24 * 60].any()  # medyan hesaplanamaz → bloklamaz
    gun32 = pd.Timestamp("2026-01-01") + pd.Timedelta(days=32)
    maske32 = (idx >= gun32) & (idx < gun32 + pd.Timedelta(days=1))
    assert not blok[np.where(maske32)[0][-1]]  # normal gün bloklanmaz


def test_S3_duz_yol_tam_verimli():
    idx = pd.date_range("2026-01-01", periods=180, freq="1min")
    sd = _SD(idx.values.astype("datetime64[ns]"), np.linspace(100, 110, 180))
    s30 = otuz_dakika_kapanis(sd)
    z = _Zone(s30.index[0], float(s30.iloc[0]), s30.index[-1], float(s30.iloc[-1]))
    assert leg_verimliligi(sd, z, s30) == 1.0


def test_S3_dolasik_yol_dusuk_verimlilik():
    idx = pd.date_range("2026-01-01", periods=180, freq="1min")
    close = 100 + np.sin(np.linspace(0, 20, 180)) * 5 + np.linspace(0, 10, 180)
    sd = _SD(idx.values.astype("datetime64[ns]"), close)
    s30 = otuz_dakika_kapanis(sd)
    z = _Zone(s30.index[0], float(s30.iloc[0]), s30.index[-1], float(s30.iloc[-1]))
    assert leg_verimliligi(sd, z, s30) < 0.7  # dolaşık yol → düz yoldan belirgin düşük
