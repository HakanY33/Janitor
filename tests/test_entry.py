"""R-ENTRY-05 — OB/FVG giriş uygunluğu testleri.

Kuralın özü nedensellik: her ölçüt `at` anında bilinen bilgiyle değerlendirilir.
Bu yüzden testlerin yarısı "karar anından *sonra* olan bir olay kararı değiştirmemeli"
biçimindedir — spec'in yasakladığı "20 mum dayandı" tipi geriye dönük ölçüt budur.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.features.candles import reference_body
from src.features.fvg import BEARISH, BULLISH, FVG, FvgStore, detect_fvgs, replay
from src.features.ob import OrderBlock, detect_order_blocks, mitigation_time, replay_obs
from src.strategy.entry import (
    MIN_FVG_WIDTH_RATIO,
    band,
    eligible_fvgs,
    eligible_obs,
    fvg_eligible,
    ob_eligible,
)
from src.zones.model import Zone

T0 = pd.Timestamp("2026-01-01", tz="UTC")
SYM = "TEST/USDT:USDT"
TF = "30m"


def ts(i: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(TF) * i


def short_zone() -> Zone:
    """0 = 100 (altta), 1 = 200 (üstte) → SHORT. Giriş bandı 170–179."""
    return Zone.create(SYM, TF, 100.0, ts(0), 200.0, ts(1))


def ob(direction=BEARISH, top=178.0, bottom=172.0, impulse=2, mitigated=None) -> OrderBlock:
    return OrderBlock(
        ob_id="ob1", symbol=SYM, timeframe=TF, direction=direction, top=top, bottom=bottom,
        created_at=ts(impulse - 1), impulse_at=ts(impulse),
        mitigated_at=None if mitigated is None else ts(mitigated),
    )


def fvg(top=178.0, bottom=172.0, created=2, filled=None, ratio=1.0, direction=BEARISH) -> FVG:
    return FVG(
        fvg_id="f1", symbol=SYM, timeframe=TF, direction=direction, top=top, bottom=bottom,
        created_at=ts(created), filled_at=None if filled is None else ts(filled),
        width_ratio=ratio,
    )


def test_R_ZONE_03_band_is_070_to_079_sorted():
    assert band(short_zone()) == (170.0, 179.0)


# --- R-ENTRY-05 · OB unmitige sarti -------------------------------------------


def test_R_ENTRY_05_accepts_unmitigated_ob():
    assert ob_eligible(ob(), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_mitigated_ob():
    """Fiyat bir kez uğradıysa bölge tüketilmiştir."""
    assert not ob_eligible(ob(mitigated=5), short_zone(), ts(10))


def test_R_ENTRY_05_ob_mitigated_after_decision_is_still_eligible():
    """Karar anından sonraki mitigasyon kararı değiştiremez (CLAUDE.md #3)."""
    assert ob_eligible(ob(mitigated=20), short_zone(), ts(10))


def test_R_ENTRY_05_ob_mitigated_exactly_at_decision_is_rejected():
    """Eşitlikte kötümser taraf: aynı anda mitige olan OB aday değildir."""
    assert not ob_eligible(ob(mitigated=10), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_ob_not_yet_known():
    """OB ancak impuls mumu kapanınca bilinir."""
    assert not ob_eligible(ob(impulse=12), short_zone(), ts(10))


def test_R_ENTRY_02_rejects_ob_against_zone_bias():
    """SHORT zone yalnızca BEARISH (arz) OB kabul eder."""
    z = short_zone()
    assert not ob_eligible(ob(direction=BULLISH), z, ts(10))
    assert ob_eligible(ob(direction=BEARISH), z, ts(10))


def test_R_ENTRY_02_long_zone_wants_bullish_ob():
    z = Zone.create(SYM, TF, 200.0, ts(0), 100.0, ts(1))  # 0 üstte → LONG
    assert z.bias == "LONG"
    low, high = band(z)
    assert ob_eligible(ob(direction=BULLISH, top=high, bottom=low), z, ts(10))
    assert not ob_eligible(ob(direction=BEARISH, top=high, bottom=low), z, ts(10))


def test_R_ENTRY_05_rejects_ob_outside_entry_band():
    assert not ob_eligible(ob(top=160.0, bottom=155.0), short_zone(), ts(10))


def test_R_ENTRY_05_ob_touching_band_edge_is_eligible():
    """§0.1 · kesişim yeterlidir, tam kapsama aranmaz."""
    assert ob_eligible(ob(top=170.0, bottom=165.0), short_zone(), ts(10))


# --- R-ENTRY-05 · FVG dolmamis + genislik -------------------------------------


def test_R_ENTRY_05_accepts_wide_unfilled_fvg():
    assert fvg_eligible(fvg(ratio=1.0), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_filled_fvg():
    assert not fvg_eligible(fvg(filled=5), short_zone(), ts(10))


def test_R_ENTRY_05_fvg_filled_after_decision_is_still_eligible():
    assert fvg_eligible(fvg(filled=20), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_narrow_fvg():
    assert not fvg_eligible(fvg(ratio=0.43), short_zone(), ts(10))


def test_R_ENTRY_05_width_threshold_is_inclusive_at_044():
    assert MIN_FVG_WIDTH_RATIO == 0.44
    assert fvg_eligible(fvg(ratio=0.44), short_zone(), ts(10))
    assert not fvg_eligible(fvg(ratio=0.4399), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_fvg_without_width_ratio():
    """Payda tanımsızsa oran yoktur; eşik geçilemez."""
    assert not fvg_eligible(fvg(ratio=None), short_zone(), ts(10))


def test_R_ENTRY_05_rejects_fvg_not_yet_created():
    assert not fvg_eligible(fvg(created=12), short_zone(), ts(10))


def test_R_ENTRY_05_no_direction_filter_for_fvg():
    """R-ENTRY-02 (2) yön demiyor; spec'te olmayan kısıt eklenmez (CLAUDE.md)."""
    z = short_zone()
    assert fvg_eligible(fvg(direction=BULLISH), z, ts(10))
    assert fvg_eligible(fvg(direction=BEARISH), z, ts(10))


def test_R_ENTRY_05_rejects_fvg_outside_band():
    assert not fvg_eligible(fvg(top=160.0, bottom=155.0), short_zone(), ts(10))


# --- toplu suzgecler ----------------------------------------------------------


def test_R_ENTRY_05_eligible_lists_filter_in_place():
    z = short_zone()
    obs = [ob(), ob(mitigated=5), ob(direction=BULLISH)]
    fvgs = [fvg(), fvg(ratio=0.1), fvg(filled=3)]
    assert len(eligible_obs(obs, z, ts(10))) == 1
    assert len(eligible_fvgs(fvgs, z, ts(10))) == 1


# --- mitigasyon olcumu (features/ob.py) ---------------------------------------


def bars(rows) -> pd.DataFrame:
    """(high, low) listesinden mum çerçevesi."""
    return pd.DataFrame({
        "ts": [ts(i) for i in range(len(rows))],
        "open": [h for h, _ in rows], "high": [h for h, _ in rows],
        "low": [low for _, low in rows], "close": [low for _, low in rows],
        "volume": [1.0] * len(rows),
    })


def test_R_ENTRY_05_mitigation_is_touch_not_full_pierce():
    """Mitigasyon gövdeye dokunmaktır; delinme gibi tamamen geçilmesi gerekmez."""
    o = ob(top=178.0, bottom=172.0, impulse=1)
    df = bars([(200, 190), (200, 190), (200, 176), (200, 190)])  # 3. mum gövdeye giriyor
    assert mitigation_time(o, df) == ts(2)


def test_R_ENTRY_05_mitigation_ignores_bars_before_impulse():
    """OB impuls mumundan önce bilinmiyordu; o mumlar mitigasyon sayılmaz."""
    o = ob(top=178.0, bottom=172.0, impulse=2)
    df = bars([(200, 175), (200, 175), (200, 175), (200, 190)])
    assert mitigation_time(o, df) is None


def test_R_ENTRY_05_mitigation_none_when_price_never_returns():
    o = ob(top=178.0, bottom=172.0, impulse=1)
    assert mitigation_time(o, bars([(200, 190)] * 5)) is None


def test_R_ENTRY_05_replay_obs_matches_mitigation_time():
    """Toplu `replay_obs`, tek tek `mitigation_time` ile aynı sonucu vermeli."""
    df = bars([(200, 190), (200, 190), (200, 176), (200, 190), (200, 171)])
    obs = [ob(top=178.0, bottom=172.0, impulse=1), ob(top=196.0, bottom=192.0, impulse=1)]
    beklenen = [mitigation_time(o, df) for o in obs]
    replay_obs(obs, df)
    assert [o.mitigated_at for o in obs] == beklenen


# --- FVG width_ratio ----------------------------------------------------------


def real_df(n: int = 120) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(3)
    p = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "ts": [ts(i) for i in range(n)],
        "open": np.concatenate([[p[0]], p[:-1]]), "high": p * 1.004,
        "low": p * 0.996, "close": p, "volume": np.full(n, 1.0),
    })


def test_R_ENTRY_05_width_ratio_matches_reference_body():
    """Oran = genişlik / son 20 mumun medyan gövdesi — OB ile aynı payda."""
    df = real_df()
    ref = reference_body(df)
    yer = {t: i for i, t in enumerate(df.ts)}
    fvgs = [f for f in detect_fvgs(df, SYM, TF) if f.width_ratio is not None]
    assert fvgs
    for f in fvgs:
        beklenen = (f.top - f.bottom) / ref.iloc[yer[f.created_at]]
        assert f.width_ratio == pytest.approx(beklenen)


def test_R_ENTRY_05_width_ratio_is_none_before_median_defined():
    df = real_df()
    erken = [f for f in detect_fvgs(df, SYM, TF) if f.created_at <= ts(4)]
    assert all(f.width_ratio is None for f in erken)


def test_R_ENTRY_05_width_ratio_survives_store_roundtrip(tmp_path):
    df = real_df()
    f = next(x for x in detect_fvgs(df, SYM, TF) if x.width_ratio is not None)
    store = FvgStore(tmp_path / "s.db")
    store.save(f)
    assert store.get(f.fvg_id).width_ratio == pytest.approx(f.width_ratio)
    store.close()


def test_R_ENTRY_05_filters_reduce_candidate_count_on_real_shape():
    """Süzgeçler gerçekten bağlayıcı: ham liste her zaman aday listesinden büyük."""
    df = real_df(300)
    fvgs = detect_fvgs(df, SYM, TF)
    replay(fvgs, df)
    obs = detect_order_blocks(df, SYM, TF)
    replay_obs(obs, df)
    z = Zone.create(SYM, TF, float(df.low.min()), ts(0), float(df.high.max()), ts(1))
    at = df.ts.iloc[-1]
    assert len(eligible_fvgs(fvgs, z, at)) < len(fvgs)
    assert len(eligible_obs(obs, z, at)) <= len(obs)
