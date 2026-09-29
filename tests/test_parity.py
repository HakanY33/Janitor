"""Parite testleri — `docs/LIVE.md` §5.

D0 · önek değişmezliği: her kesim `k` için `f(seri[:k])`, `f(seri)`'nin `k`. mumun
kapanışında **bilinen** kısmına alan alan eşittir. CLAUDE.md #3'ün makinece sınanmış
hâli. Kimlik deterministik olduğu için (Ö3) eşleştirme kimlikle yapılır.

"Bilinen" = nesnenin kendi `known_at` alanı; olay damgaları (`mitigated_at`, `filled_at`)
zaten mumun kapanışıdır. Kesim anı önekin son mumunun kapanışıdır. Nesnenin damgasının
gerçekten "hesaplamada kullanılan son mumun kapanışı"ndan önce olmadığı ayrıca
`tests/test_known_at.py`'de sınanır — D0 yalnızca ikisi tutarlıysa anlamlıdır.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.fvg import detect_fvgs, replay
from src.features.ids import stable_id
from src.features.ob import detect_order_blocks, pierce_time, replay_obs
from src.features.structure import htf_bias
from src.zones.detect import detect_zones

SYM, TF = "TEST/USDT:USDT", "30m"
TD = pd.Timedelta(TF)


def seri(n: int = 1200, seed: int = 7) -> pd.DataFrame:
    """Tohumlu rastgele yürüyüş, ara ara büyük gövdeli mum (OB/FVG/süpürme üretsin)."""
    rng = np.random.default_rng(seed)
    adim = rng.normal(0, 1, n) * np.where(rng.random(n) < 0.06, 6, 1)
    close = 1000 + np.cumsum(adim)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.random(n) * 1.5
    low = np.minimum(open_, close) - rng.random(n) * 1.5
    ts = pd.date_range("2026-01-01", periods=n, freq="30min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": open_, "high": high, "low": low,
                         "close": close, "volume": rng.random(n) * 100})


DF = seri()
KESIMLER = sorted({int(k) for k in np.random.default_rng(1).integers(200, len(DF), 12)})


def _zone(z):
    return (z.zone_id, z.bias, z.anchor_0_price, z.anchor_0_time, z.anchor_1_price,
            z.anchor_1_time, z.pivot_confirmed_at, z.known_at, z.level_050, z.level_070, z.level_079)


def _ob(o):
    return (o.ob_id, o.direction, o.top, o.bottom, o.created_at, o.impulse_at, o.known_at)


def _fvg(f):
    return (f.fvg_id, f.direction, f.top, f.bottom, f.created_at, f.width_ratio, f.known_at)


def test_veri_uretiyor():
    """Sentetik seri testin konusunu gerçekten üretiyor — boş eşitlik test değildir."""
    assert len(detect_zones(DF, SYM, TF)) >= 10
    assert len(detect_order_blocks(DF, SYM, TF)) >= 10
    assert len(detect_fvgs(DF, SYM, TF)) >= 10


@pytest.mark.parametrize("k", KESIMLER)
def test_D0_zone_onek_degismez(k):
    kesim = DF.ts.iloc[k - 1] + TD  # önekin son mumunun kapanışı
    tam = [_zone(z) for z in detect_zones(DF, SYM, TF) if z.known_at <= kesim]
    onek = [_zone(z) for z in detect_zones(DF.iloc[:k], SYM, TF)]
    assert onek == tam


@pytest.mark.parametrize("k", KESIMLER)
def test_D0_ob_onek_degismez(k):
    kesim = DF.ts.iloc[k - 1] + TD
    tam_l = detect_order_blocks(DF, SYM, TF)
    replay_obs(tam_l, DF)
    onek_l = detect_order_blocks(DF.iloc[:k], SYM, TF)
    replay_obs(onek_l, DF.iloc[:k])
    tam = [(*_ob(o), o.mitigated_at if o.mitigated_at is not None and o.mitigated_at <= kesim
            else None) for o in tam_l if o.known_at <= kesim]
    assert [(*_ob(o), o.mitigated_at) for o in onek_l] == tam


@pytest.mark.parametrize("k", KESIMLER)
def test_D0_fvg_onek_degismez(k):
    kesim = DF.ts.iloc[k - 1] + TD
    tam_l = detect_fvgs(DF, SYM, TF)
    replay(tam_l, DF)
    onek_l = detect_fvgs(DF.iloc[:k], SYM, TF)
    replay(onek_l, DF.iloc[:k])

    def durum(f, tam: bool):
        kes = (lambda x: x if x is not None and x <= kesim else None) if tam else (lambda x: x)
        return (*_fvg(f), kes(f.mitigated_at), kes(f.filled_at))

    assert [durum(f, False) for f in onek_l] == \
        [durum(f, True) for f in tam_l if f.known_at <= kesim]


@pytest.mark.parametrize("k", KESIMLER)
def test_D0_htf_bias_onek_degismez(k):
    kesim = DF.ts.iloc[k - 1] + TD
    tam = htf_bias(DF, SYM)
    onek = htf_bias(DF.iloc[:k], SYM)
    tam, onek = tam[tam.known_at <= kesim], onek[onek.known_at <= kesim]
    pd.testing.assert_frame_equal(onek.reset_index(drop=True), tam.reset_index(drop=True))


def test_O3_kimlik_deterministik():
    """Ö3 · aynı girdi aynı kimlik, iki ayrı tespit koşusunda."""
    assert [z.zone_id for z in detect_zones(DF, SYM, TF)] == \
        [z.zone_id for z in detect_zones(DF, SYM, TF)]
    assert stable_id("zone", SYM, 1.0) == stable_id("zone", SYM, 1.0)
    assert stable_id("zone", SYM, 1.0) != stable_id("zone", SYM, 1.0000000001)


@pytest.mark.parametrize("k", KESIMLER)
def test_D0_delinme_onek_degismez(k):
    """R-ADD-06 · delinme anı, son teyit mumunun kapanışında bilinir; önekte erken görünmez."""
    kesim = DF.ts.iloc[k - 1] + TD
    obs = [o for o in detect_order_blocks(DF, SYM, TF) if o.known_at <= kesim]
    tam = [pierce_time(o, DF) for o in obs]
    assert [pierce_time(o, DF.iloc[:k]) for o in obs] == \
        [p if p is not None and p <= kesim else None for p in tam]
