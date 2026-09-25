"""R-ZONE-10 / R-ZONE-02 — yapıdan zone üretimi (leg seçimi) testleri.

`tests/test_zones.py` zone'un *durum makinesini* elle kurulmuş çapalarla sınar;
burada sınanan, çapaların **yapıdan doğru seçilmesi**.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.features.structure import HIGH, LOW, Swing, detect_swings
from src.zones.detect import _anchor_0, detect_zones, zones_from_swings
from src.zones.model import Zone
from tests.test_structure import bars, ramp, warmup

SYM = "TEST/USDT:USDT"
TF = "30m"
T0 = pd.Timestamp("2026-01-01", tz="UTC")


def swing(kind: str, price: float, i: int, label=None, swept=False) -> Swing:
    """Elle kurulmuş swing — leg seçimi mantığını izole sınamak için."""
    ts = T0 + pd.Timedelta(TF) * i
    return Swing(
        swing_id=f"s{i}", symbol=SYM, timeframe=TF, kind=kind, price=price, ts=ts,
        pivot_confirmed_at=ts + pd.Timedelta(TF) * 2, label=label, swept=swept,
    )


# --- R-ZONE-10 · anchor secimi ------------------------------------------------


def test_R_ZONE_10_anchor_1_is_the_sweeping_swing():
    """Süpüren her swing bir zone'un `anchor_1`'idir; süpürmeyen zone üretmez."""
    swings = [
        swing(HIGH, 130, 0),
        swing(LOW, 110, 2, "HL", swept=False),
        swing(HIGH, 150, 4, "HH", swept=True),
    ]
    zones = zones_from_swings(swings, SYM, TF)
    assert len(zones) == 1
    assert zones[0].anchor_1_price == 150 and zones[0].anchor_0_price == 110


def test_R_ZONE_10_swept_high_yields_short_zone():
    """`0` altta, `1` üstte → SHORT (§0 bias tablosu)."""
    swings = [swing(HIGH, 130, 0), swing(LOW, 110, 2, "HL"), swing(HIGH, 150, 4, "HH", True)]
    assert zones_from_swings(swings, SYM, TF)[0].bias == "SHORT"


def test_R_ZONE_10_swept_low_yields_long_zone():
    swings = [swing(LOW, 100, 0), swing(HIGH, 120, 2, "LH"), swing(LOW, 90, 4, "LL", True)]
    z = zones_from_swings(swings, SYM, TF)[0]
    assert z.bias == "LONG" and z.anchor_0_price == 120 and z.anchor_1_price == 90


def test_R_ZONE_02_prefers_sweeping_candidate_for_anchor_0():
    """Pencerede birden fazla dip varsa süpüren seçilir — daha uçta olan bile olsa."""
    swings = [
        swing(HIGH, 130, 0),
        swing(LOW, 105, 2, "LL", swept=True),  # süpüren ama daha yüksek
        swing(LOW, 100, 4, "LL", swept=False),  # daha uçta ama süpürmüyor
        swing(HIGH, 150, 6, "HH", swept=True),
    ]
    assert _anchor_0(swings, 3).price == 105


def test_R_ZONE_02_picks_most_extreme_when_no_candidate_swept():
    swings = [
        swing(HIGH, 130, 0),
        swing(LOW, 108, 2, "HL", swept=False),
        swing(LOW, 100, 4, "LL", swept=False),
        swing(HIGH, 150, 6, "HH", swept=True),
    ]
    assert _anchor_0(swings, 3).price == 100


def test_R_ZONE_10_anchor_0_window_starts_after_the_swept_swing():
    """Pencere, aşılan aynı tip swing'den sonra başlar: daha eski dipler leg'i başlatmadı."""
    swings = [
        swing(LOW, 50, 0),  # çok eski dip — pencere dışı
        swing(HIGH, 130, 2),
        swing(LOW, 110, 4, "HL"),
        swing(HIGH, 150, 6, "HH", swept=True),
    ]
    assert _anchor_0(swings, 3).price == 110


def test_R_ZONE_10_falls_back_to_last_opposite_swing_when_window_empty():
    """Ardışık aynı tip swing'lerde araya dip girmemişse son bilinen dibe düşülür."""
    swings = [
        swing(LOW, 100, 0),
        swing(HIGH, 130, 2),
        swing(HIGH, 150, 4, "HH", swept=True),  # araya dip girmedi
    ]
    assert _anchor_0(swings, 2).price == 100


def test_R_ZONE_10_no_zone_without_opposite_swing():
    swings = [swing(HIGH, 130, 0), swing(HIGH, 150, 2, "HH", swept=True)]
    assert zones_from_swings(swings, SYM, TF) == []


def test_R_ZONE_10_same_leg_does_not_create_two_zones():
    swings = [
        swing(HIGH, 130, 0), swing(LOW, 110, 2, "HL"),
        swing(HIGH, 150, 4, "HH", swept=True), swing(HIGH, 150, 4, "HH", swept=True),
    ]
    assert len(zones_from_swings(swings, SYM, TF)) == 1


def test_R_ZONE_10_equal_anchor_prices_produce_no_zone():
    """`Zone.create` sıfır boy leg'i reddeder; burada sessizce atlanır."""
    swings = [swing(HIGH, 130, 0), swing(LOW, 150, 2, "HL"), swing(HIGH, 150, 4, "HH", True)]
    assert zones_from_swings(swings, SYM, TF) == []


# --- R-ZONE-03 · seviyeler ----------------------------------------------------


def test_R_ZONE_03_levels_match_manual_fib():
    """Seviyeler lineer fib; detect yalnızca çapaları seçer, hesabı Zone.create yapar."""
    swings = [swing(HIGH, 130, 0), swing(LOW, 100, 2, "HL"), swing(HIGH, 200, 4, "HH", True)]
    z = zones_from_swings(swings, SYM, TF)[0]
    assert z.level_050 == pytest.approx(150.0)
    assert z.level_070 == pytest.approx(170.0)
    assert z.level_079 == pytest.approx(179.0)


# --- R-ZONE-09 · WATCH_FROM ---------------------------------------------------


def test_R_ZONE_09_watch_from_respects_pivot_confirmation():
    """`WATCH_FROM = max(anchor_1 HTF kapanışı, pivot teyidi)` — teyit asıl kısıt."""
    swings = [swing(HIGH, 130, 0), swing(LOW, 110, 2, "HL"), swing(HIGH, 150, 4, "HH", True)]
    z = zones_from_swings(swings, SYM, TF)[0]
    bar = pd.Timedelta(TF)
    assert z.pivot_confirmed_at == z.anchor_1_time + 2 * bar
    assert z.watch_from == z.anchor_1_time + 2 * bar  # teyit, HTF kapanışından sonra
    assert z.watch_from > z.anchor_1_time + bar


def test_R_ZONE_09_watch_from_never_precedes_anchor_1_bar_close():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5) + ramp(112, 150, 7))
    for z in detect_zones(df, SYM, TF):
        assert z.watch_from >= z.anchor_1_time + pd.Timedelta(TF)
        assert z.watch_from >= z.pivot_confirmed_at


def test_R_ZONE_09_detect_zones_rejects_1m():
    df = bars(warmup() + ramp(100, 130, 6), tf="1m")
    with pytest.raises(ValueError, match="R-ZONE-09"):
        detect_zones(df, SYM, "1m")


# --- uctan uca ----------------------------------------------------------------


def test_R_ZONE_10_end_to_end_uptrend_produces_short_zones():
    """Yükselen yapıda süpürülen tepeler SHORT zone üretir (likidite sonrası dönüş)."""
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 170, 8))
    zones = detect_zones(df, SYM, TF)
    assert zones, "süpüren tepe olmalı"
    assert any(z.bias == "SHORT" for z in zones)
    for z in zones:
        assert isinstance(z, Zone)
        assert min(z.anchor_0_price, z.anchor_1_price) <= z.level_050 <= max(
            z.anchor_0_price, z.anchor_1_price
        )


def test_R_ZONE_10_zones_ordered_by_confirmation():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 170, 8))
    zones = detect_zones(df, SYM, TF)
    assert [z.pivot_confirmed_at for z in zones] == sorted(z.pivot_confirmed_at for z in zones)


def test_R_ZONE_10_detect_zones_no_lookahead():
    """Veriyi kesmek, o ana kadar teyitlenmiş zone'ları değiştirmemeli."""
    from tests.test_structure import rastgele_yol

    df = bars(rastgele_yol(600))
    tam = detect_zones(df, SYM, TF)

    def imza(zones):
        return [(z.anchor_0_price, z.anchor_1_price, z.anchor_0_time, z.anchor_1_time,
                 z.bias, z.watch_from) for z in zones]

    for k in (200, 350, 500):
        parca = df.iloc[:k].reset_index(drop=True)
        son_ts = parca.ts.iloc[-1]
        beklenen = [z for z in tam if z.pivot_confirmed_at <= son_ts]
        assert imza(detect_zones(parca, SYM, TF)) == imza(beklenen), f"kesim {k}"
