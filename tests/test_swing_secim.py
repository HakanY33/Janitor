"""Swing adayları (`scripts/swing_secim.py`, ön kayıt `adaylar.md`) — sentetik, ağsız."""
import numpy as np
import pandas as pd

from scripts.swing_secim import ADAYLAR
from src.features.structure import HIGH, LOW


def _seri(n=1500, tohum=7):
    r = np.random.default_rng(tohum)
    c = 100 + np.cumsum(r.normal(0, 1, n))
    ts = pd.date_range("2026-01-01", periods=n, freq="30min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": c, "high": c + r.uniform(0.1, 1, n),
                         "low": c - r.uniform(0.1, 1, n), "close": c, "volume": 1.0})


def test_adaylar_nedensel_ve_onek_degismez():
    """CLAUDE.md #3 · veriyi kesmek, o ana kadar bilinen swing'leri değiştirmez."""
    d = _seri()
    kes = d.ts.iloc[1000]
    for ad, fn in ADAYLAR.items():
        tam = fn(d, "X")
        assert tam, ad
        assert all(s.known_at > s.ts for s in tam), ad
        assert all(a.ts <= b.ts for a, b in zip(tam, tam[1:])), ad
        bilinen = [(s.ts, s.kind, s.price) for s in tam if s.known_at <= kes]
        kisa = [(s.ts, s.kind, s.price) for s in fn(d[d.ts < kes].reset_index(drop=True), "X")
                if s.known_at <= kes]
        if ad != "D":  # D: kesimdeki 4h mumu kısmi; yalnızca ondan önceki teyitler aynı olmalı
            assert bilinen == kisa, ad


def test_zigzag_yon_degistirir():
    d = _seri()
    s = ADAYLAR["B2"](d, "X")
    assert all(a.kind != b.kind for a, b in zip(s, s[1:]))
    assert {x.kind for x in s} == {HIGH, LOW}


def test_C_pencere_ucu_ve_supurme():
    d = _seri()
    h = d.high.to_numpy()
    for s in ADAYLAR["C96"](d, "X"):
        i = int(d.ts.searchsorted(s.ts))
        if s.kind == HIGH:
            assert h[i] == h[i - 96: i + 5].max()
