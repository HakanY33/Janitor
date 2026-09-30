"""Paper çekirdeği — `docs/LIVE.md` §5 D1 (paper yolundan) ve D2 (çökme + yeniden başlatma).

Üç koşu aynı sentetik mumlarla (`tests/test_parity_d1.py`, ağsız):

1. backtest (`Backtest.run`, tüm seride tespit)
2. paper, kesintisiz (`PaperCore`, SQLite durum, artımlı tespit)
3. paper, rastgele bir dakikada "çöker": nesne atılır, SQLite'tan `geri_yukle`, devam

İşlemler, sayaçlar birebir; karar logunun motor satırları (`ENTRY`, `ENTRY_REJECTED`,
`EXIT`) backtest'le birebir; çöken koşunun logu tekilleştirilince kesintisizle birebir.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.backtest.costs import CostModel
from src.backtest.engine import Backtest
from src.backtest.loader import build_from_frames
from src.live.paper import Durum, PaperCore
from tests.test_parity_d1 import F1, MALIYET, SYM, mumlar

D30, D1 = mumlar(gun=10)
MOTOR = {"ENTRY", "ENTRY_REJECTED", "EXIT"}


def maliyet():
    return CostModel(fees=MALIYET, funding={}, slippage_bps=Decimal("2"))


def dakikalar():
    ts = D1.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    ohlcv = D1[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    for t, r in zip(ts, ohlcv):
        yield t, {SYM: tuple(float(x) for x in r)}


def json_satir(satir: dict) -> str:
    return json.dumps(satir, sort_keys=True, default=str)


def paper(yol, cokme: int | None = None):
    """Paper koşusu; `cokme` verilirse o dakikadan sonra nesne atılır ve geri yüklenir."""
    log: list[dict] = []
    baslangic = pd.Timestamp(D1.ts.iloc[0])
    core = PaperCore.yeni(Durum(yol), [SYM], maliyet(), baslangic, karar=log.append, **F1)
    core.otuz(SYM, D30)  # geleceğin 30m mumları da tamponda: tespite yalnızca kapanışta girer
    for i, (t, bars) in enumerate(dakikalar()):
        if cokme is not None and i == cokme:
            del core
            core = PaperCore.geri_yukle(Durum(yol), karar=log.append)
            assert core.durum.imlec() == t - np.timedelta64(1, "m")
        core.dakika(t, bars)
    return core.bt.finish(pd.Timestamp(D1.ts.iloc[-1])), log


@pytest.fixture(scope="module")
def kosular(tmp_path_factory):
    bt_log: list[dict] = []
    bt = Backtest([build_from_frames(SYM, D30, D1)], maliyet(), **F1)
    bt.log = bt_log.append
    res_bt = bt.run()
    d = tmp_path_factory.mktemp("paper")
    res_p, log_p = paper(d / "surekli.db")
    res_c, log_c = paper(d / "cokme.db", cokme=len(D1) // 2 + 7)
    return (res_bt, bt_log), (res_p, log_p), (res_c, log_c)


def test_D1_paper_yolu_backtest_ile_birebir(kosular):
    (bt, bt_log), (p, p_log), _ = kosular
    assert len(bt.trades) >= 5, "sentetik veri işlem üretmiyor — test boş"
    assert [asdict(t) for t in p.trades] == [asdict(t) for t in bt.trades]
    assert p.counters == bt.counters
    assert [json_satir(x) for x in p_log if x["event"] in MOTOR] == \
        [json_satir(x) for x in bt_log]


def test_D2_cokme_ve_geri_yukleme_kesintisizle_birebir(kosular):
    _, (p, p_log), (c, c_log) = kosular
    assert [asdict(t) for t in c.trades] == [asdict(t) for t in p.trades]
    assert c.counters == p.counters
    tekil = list(dict.fromkeys(json_satir(x) for x in c_log))
    assert tekil == list(dict.fromkeys(json_satir(x) for x in p_log))


def test_OPEN_54_emir_olaylari_yaziliyor(kosular):
    _, (_, p_log), _ = kosular
    olaylar = {x["event"] for x in p_log}
    assert {"ORDER", "NO_ACTION", "ENTRY", "EXIT"} <= olaylar
    assert {x["outcome"] for x in p_log if x["event"] == "ORDER"} >= {"KOY", "IPTAL"}
