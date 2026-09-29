"""Canlı döngünün veri yarısı ve oynatma beslemesi — `docs/LIVE.md` §1 A2, §5 D1.

Canlıda feature'lar tüm seride bir kez değil, **her 30m kapanışında** o ana kadar kapanmış
mumlar üzerinde yeniden tespit edilir; yeni kimlikler (`uuid5`, Ö3) eklenir, bilinenler
güncellenir (mitigasyon, dolum, delinme). `oynat`, Parquet mumlarını canlıdaki sırayla
verir: 30m mumu yalnızca kapanışında, 1m mumu kendi dakikasında. Karar kodu backtest'in
`Backtest.step`'idir — iki ayrı mantık yoktur (Ö1).

D1 parite testi bu yolu `Backtest.run` ile karşılaştırır. Tek fark artımlı tespit ve
besleme sırasıdır; bir fark varsa ya look-ahead ya mantık hatasıdır.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.engine import Backtest, Result
from src.backtest.loader import DETECT_TF, SymbolData, set_bias, set_ob_arrays
from src.features.fvg import detect_fvgs, replay
from src.features.ob import detect_order_blocks, replay_obs
from src.zones.detect import detect_zones

TD = pd.Timedelta(DETECT_TF)


def bos_sembol(symbol: str) -> SymbolData:
    """Canlı döngünün başlangıç durumu: hiçbir feature bilinmiyor."""
    bos = np.array([], dtype="datetime64[ns]")
    return SymbolData(symbol=symbol, ts=bos, high=np.array([]), low=np.array([]),
                      close=np.array([]), zones=[], obs=[], fvgs=[], pierce_at={})


def kapanis(bt: Backtest, symbol: str, d30: pd.DataFrame, baslangic: pd.Timestamp) -> None:
    """30m kapanışı: `d30` o ana kadar kapanmış mumlardır. Yeni nesneler eklenir.

    `baslangic`: canlı döngünün ilk 1m mumu. Ondan önce izlemeye girmesi gereken zone
    hiç izlenmez — backtest'in `watch_from` süzgeciyle aynı.
    """
    sd = bt.data[symbol]
    bilinen = {z.zone_id for z in sd.zones}
    bt.add_zones(symbol, [z for z in detect_zones(d30, symbol, DETECT_TF)
                          if z.zone_id not in bilinen and z.watch_from >= baslangic])
    eski = {o.ob_id for o in sd.obs}
    sd.obs.extend(o for o in detect_order_blocks(d30, symbol, DETECT_TF) if o.ob_id not in eski)
    replay_obs([o for o in sd.obs if o.mitigated_at is None], d30)
    eski = {f.fvg_id for f in sd.fvgs}
    sd.fvgs.extend(f for f in detect_fvgs(d30, symbol, DETECT_TF) if f.fvg_id not in eski)
    replay([f for f in sd.fvgs if f.filled_at is None], d30)
    set_ob_arrays(sd, d30)
    set_bias(sd, d30)


def oynat(bt: Backtest, d30: dict[str, pd.DataFrame], d1: dict[str, pd.DataFrame]) -> Result:
    """Mumları canlıdaki sırayla besler. `bt`, `bos_sembol` verileriyle kurulmuş olmalı.

    Dakika `t` işlenmeden önce kapanışı `≤ t` olan her 30m mumu tespite verilir: `t`
    açılışlı 1m mumun kararları o anda bilinen her şeyi görür, fazlasını görmez.
    """
    bt.start()
    semboller = list(bt.data)
    ts1 = {s: d1[s].ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy() for s in semboller}
    hlcv = {s: d1[s][["high", "low", "close", "volume"]].to_numpy(dtype=float) for s in semboller}
    kapanis30 = {s: (d30[s].ts + TD).dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
                 for s in semboller}
    grid = np.unique(np.concatenate([ts1[s] for s in semboller]))
    baslangic = pd.Timestamp(grid[0], tz="UTC")
    k = {s: 0 for s in semboller}
    ptr = {s: 0 for s in semboller}
    for gi, t in enumerate(grid):
        for s in semboller:
            n = int(np.searchsorted(kapanis30[s], t, side="right"))
            if n > k[s]:
                k[s] = n
                kapanis(bt, s, d30[s].iloc[:n].reset_index(drop=True), baslangic)
        bars = {}
        for s in semboller:
            i = ptr[s]
            if i < len(ts1[s]) and ts1[s][i] == t:
                ptr[s] = i + 1
                h, lo, c, v = hlcv[s][i]
                bars[s] = (float(h), float(lo), float(c), float(v))
        bt.step(t, bars)
        if gi % 1440 == 0:
            bt.equity_curve.append((pd.Timestamp(t, tz="UTC"), bt.pf.equity_f(bt.marks)))
    return bt.finish(pd.Timestamp(grid[-1], tz="UTC"))
