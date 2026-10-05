"""D1 · oynatma paritesi — `docs/LIVE.md` §5.

Aynı mumlar iki yoldan geçer:

* **backtest** — feature'lar tüm seride bir kez tespit edilir, `Backtest.run`
* **canlı oynatma** — 30m mumu yalnızca kapanışında verilir, feature'lar her kapanışta
  o ana kadarki önekte yeniden tespit edilir (`src/live/replay.py`), karar `Backtest.step`

İşlemler (her alan, `Decimal` eşitliği), zorunlu sayaçlar ve equity eğrisi **birebir**
aynı olmalı. Tolerans yok. Fark = look-ahead ya da mantık hatası.

Veri sentetik ve tohumlu (ağ yok, `data/` gerekmez): 1m rastgele yürüyüş, oynaklık
patlamalarıyla; 30m, 1m'den toplanır. Karar logu henüz yazılmıyor (`OPEN-54`); o
yazılınca bu test onu da karşılaştırır.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.backtest.costs import CostModel, Fees
from src.backtest.engine import Backtest
from src.backtest.loader import build_from_frames
from src.live.replay import bos_sembol, oynat

SYM = "SENT/USDT:USDT"


# Tohum 6 (2026-10-05): v0.8 OB tanımı (3 mumluk yapı, OPEN-64) rastgele yürüyüşte seyrek; F1
# kapısı (yalnızca OB) tohum 3'le 20 günde 0 işlem veriyordu. 1–14 taramasında ≥ 5 veren ilk tohum.
def mumlar(gun: int = 20, seed: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n = gun * 1440
    oynaklik = np.repeat(np.where(rng.random(n // 30) < 0.08, 5.0, 1.0), 30)
    close = 1000 + np.cumsum(rng.normal(0, 0.35, n) * oynaklik)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.random(n) * 0.2
    low = np.minimum(open_, close) - rng.random(n) * 0.2
    ts = pd.date_range("2026-03-01", periods=n, freq="1min", tz="UTC")
    d1 = pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low, "close": close,
                       "volume": rng.random(n) * 50 + 1})
    d30 = (d1.set_index("ts").resample("30min", closed="left", label="left")
           .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum")).reset_index())
    return d30, d1


D30, D1 = mumlar()
MALIYET = {SYM: Fees(Decimal("0.0005"), Decimal("0.0002"), Decimal("0.01"))}

F1 = dict(k=Decimal("0.25"), t_kritik=Decimal("0.08"), uyari_blocks_adds=False,
          require_indicator=True, limit_orders=True, max_adds=0,
          stop_loss_cap=Decimal("0.03"), breakeven_fees=True)
EKLEMELI = dict(k=Decimal("0.25"), t_kritik=Decimal("0.08"), uyari_blocks_adds=False,
                limit_orders=True, max_adds=3, reduce_once=True, stop_loss_cap=Decimal("0"))


def kos(kw: dict, canli: bool):
    cm = CostModel(fees=MALIYET, funding={}, slippage_bps=Decimal("2"))
    if canli:
        return oynat(Backtest([bos_sembol(SYM)], cm, **kw), {SYM: D30}, {SYM: D1})
    return Backtest([build_from_frames(SYM, D30, D1)], cm, **kw).run()


@pytest.mark.parametrize("ad,kw", [("F1", F1), ("eklemeli", EKLEMELI)])
def test_D1_oynatma_backtest_ile_birebir(ad, kw):
    bt, cn = kos(kw, canli=False), kos(kw, canli=True)
    assert len(bt.trades) >= 5, "sentetik veri işlem üretmiyor — test boş"
    assert [asdict(t) for t in cn.trades] == [asdict(t) for t in bt.trades]
    assert cn.counters == bt.counters
    assert cn.equity_curve == bt.equity_curve
    assert cn.portfolio.balance == bt.portfolio.balance
