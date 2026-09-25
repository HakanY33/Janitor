"""`scripts/soguk.py` · yeni kume orijinalin kesim aninda kesilir (ayrilmis donem okunmaz)."""
from __future__ import annotations

import pandas as pd

from scripts import soguk


def test_kesim_frac_tam_kesim_aninda_biter(monkeypatch):
    ts = pd.date_range("2025-01-03 07:30", periods=30_239, freq="30min", tz="UTC")
    monkeypatch.setattr(soguk.collect, "read_parquet", lambda *a: pd.DataFrame({"ts": ts}))
    kesim = pd.Timestamp("2026-05-08 13:00", tz="UTC")
    f = soguk.kesim_frac("X", "bingx", kesim)
    tr = ts[: int(len(ts) * f)]  # loader._build_symbol ile ayni dilimleme
    assert tr[-1] == kesim and (tr <= kesim).all()
