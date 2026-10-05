"""Giriş seviyesi varyantları — `EntryRule` davranış testleri.

Varyantlar `R-ENTRY-02`'nin **tetiğini** değiştirir, kuralını değil: zone'un
`TOUCHED`'a geçmesi (0.70 teması) her varyantta ön koşuldur ve `R-ZONE-04` durum
makinesi hiç değişmez. Test edilen şey dolumun hangi fiyatta olduğu ve derinleşen
varyantta girişin **kaybedilebilmesi**.

Referans zone: `0 = 100` (altta), `1 = 200` (üstte) → SHORT.
`0.50 = 150` · `0.70 = 170` · `0.75 = 175` · `0.79 = 179`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.backtest.engine import (
    ENTRY_070,
    ENTRY_075,
    ENTRY_079,
    ENTRY_IND,
    Backtest,
)
import pandas as pd

from tests.test_backtest import SYM, bearish_ob, costs, short_zone, symbol_data

PRIMED = (152, 148)  # 0.50 teması → PRIMED


def kos(bars, rule, obs=(), **kw):
    """Varyantı sıfır slippage ile koşar.

    Bu dosyanın sorusu "dolum hangi **seviyede**"; slippage fiyatı baz puanlarla
    kaydırıp seviye karşılaştırmasını bulanıklaştırıyor. Slippage'in kendisi
    `tests/test_backtest_sanity.py` içinde sabit fiyatlarla ayrıca sınanır.
    """
    return Backtest([symbol_data(bars, short_zone(), obs)], costs(Decimal("0")),
                    entry_rule=rule, **kw).run()


# --- seviye varyantlari -------------------------------------------------------


def test_variant_070_fills_at_first_band_touch():
    res = kos([PRIMED, (172, 168), (202, 198)], ENTRY_070)
    assert res.counters["entries"] == 1
    assert res.trades[0].entry_price == Decimal("170")


def test_variant_075_waits_for_deeper_price():
    """0.70'e dokunmak yetmez; 175 görülene kadar beklenir."""
    res = kos([PRIMED, (172, 168), (176, 174), (202, 198)], ENTRY_075)
    assert res.counters["entries"] == 1
    assert res.trades[0].entry_price == Decimal("175")


def test_variant_079_waits_for_band_top():
    res = kos([PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)], ENTRY_079)
    assert res.counters["entries"] == 1
    assert res.trades[0].entry_price == Decimal("179")


def test_variant_075_misses_entry_when_price_never_reaches():
    """Derinleşen varyant girişi kaybedebilir — asıl ölçülen etki bu."""
    res = kos([PRIMED, (172, 168), (173, 171), (102, 98)], ENTRY_075)  # 0 çapası: ölür
    assert res.counters["entries"] == 0
    assert res.counters["armed"] == 0  # emir fiyatına hiç ulaşılmadı
    assert res.counters["unfilled"] == 1
    assert res.trades == []


def test_deeper_variant_never_enters_more_often():
    """0.70 ⊇ 0.75 ⊇ 0.79: derinleştikçe giriş sayısı artamaz."""
    bars = [PRIMED, (172, 168), (176, 174), (202, 198)]
    sayilar = [kos(bars, r).counters["entries"] for r in (ENTRY_070, ENTRY_075, ENTRY_079)]
    assert sayilar == sorted(sayilar, reverse=True)
    assert sayilar[0] >= sayilar[-1]


def test_variant_entry_is_never_outside_band():
    for rule in (ENTRY_070, ENTRY_075, ENTRY_079):
        res = kos([PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)], rule)
        for t in res.trades:
            assert Decimal("170") <= t.entry_price <= Decimal("179")


# --- bant ici konum -----------------------------------------------------------


def test_band_pos_is_zero_at_070_and_one_at_079():
    a = kos([PRIMED, (172, 168), (202, 198)], ENTRY_070)
    b = kos([PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)], ENTRY_079)
    assert a.trades[0].band_pos == pytest.approx(0.0, abs=1e-9)
    assert b.trades[0].band_pos == pytest.approx(1.0, abs=1e-9)


def test_band_pos_midway_for_075():
    """175, 170–179 bandının (175−170)/9 = 0.5556'sı."""
    res = kos([PRIMED, (172, 168), (176, 174), (202, 198)], ENTRY_075)
    assert res.trades[0].band_pos == pytest.approx(5 / 9, abs=1e-6)


# --- gosterge varyanti --------------------------------------------------------


def test_indicator_variant_uses_ob_edge_when_present():
    """Bantta unmitige OB varsa fiyatın **ilk dokunacağı** kenarından girilir.

    SHORT bandı aşağıdan yukarı kat eder → OB'nin alt kenarı (174).
    """
    ob = bearish_ob(178.0, 174.0)
    bars = [PRIMED, (172, 168), (176, 173), (202, 198)]
    res = kos(bars, ENTRY_IND, obs=(ob,))
    assert res.counters["entries"] == 1
    assert res.trades[0].entry_price == Decimal("174")
    assert res.trades[0].had_ob


def test_indicator_variant_falls_back_to_079_without_indicator():
    bars = [PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)]
    res = kos(bars, ENTRY_IND)
    assert res.counters["entries"] == 1
    assert res.trades[0].entry_price == Decimal("179")
    assert not res.trades[0].had_ob and not res.trades[0].had_fvg


def test_OPEN_65_indicator_variant_fvg_does_not_set_price():
    """v0.8 · FVG emir fiyatını belirlemez: bantta yalnızca FVG varsa 0.79'a düşülür."""
    from src.features.fvg import BEARISH, FVG

    z = short_zone()
    sd = symbol_data([PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)], z)
    sd.fvgs = [FVG(fvg_id="f", symbol=SYM, timeframe="30m", direction=BEARISH, top=178.0,
                   bottom=174.0, created_at=z.watch_from - pd.Timedelta("1h"), width_ratio=1.0)]
    res = Backtest([sd], costs(Decimal("0")), entry_rule=ENTRY_IND).run()
    assert res.trades[0].entry_price == Decimal("179")
    assert res.trades[0].had_fvg and not res.trades[0].had_ob


def test_indicator_variant_ob_outside_band_is_ignored():
    """Bandı kesmeyen OB aday değildir (R-ENTRY-05) → 0.79'a düşülür."""
    ob = bearish_ob(165.0, 160.0)
    bars = [PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)]
    res = kos(bars, ENTRY_IND, obs=(ob,))
    assert res.trades[0].entry_price == Decimal("179")


def test_indicator_variant_mitigated_ob_is_ignored():
    """R-ENTRY-05 · mitige OB aday değil; süzgeç varyant içinde de geçerli."""
    ob = bearish_ob(178.0, 174.0)
    ob.mitigated_at = short_zone().watch_from  # girişten önce uğranmış
    bars = [PRIMED, (172, 168), (176, 174), (180, 178), (202, 198)]
    res = kos(bars, ENTRY_IND, obs=(ob,))
    assert res.trades[0].entry_price == Decimal("179")


# --- her varyantta degismeyenler ---------------------------------------------


def test_all_variants_require_050_precondition():
    """Ön koşul atlanamaz: 0.50 görülmeden hiçbir varyant giriş üretmez (§0)."""
    bars = [(172, 168), (176, 174), (180, 178)]
    for rule in (ENTRY_070, ENTRY_075, ENTRY_079, ENTRY_IND):
        assert kos(bars, rule).counters["entries"] == 0, rule.name


def test_R_ENTRY_02_OPEN_41_capa_mumu_bekleyen_emri_doldurur_ve_stoplar():
    """Emir `PRIMED` kapanışından beri defterde. `1` çapasına giden mum emri de geçer:
    dolum + aynı mumda iç stop (§8 stop önce). Zone yine `INVALIDATED` (R-ZONE-05)."""
    bars = [PRIMED, (172, 168), (202, 198)]
    for rule in (ENTRY_075, ENTRY_079, ENTRY_IND):
        res = kos(bars, rule)
        assert res.counters["entries"] == 1 and res.counters["kill_bar_fills"] == 1, rule.name
        t = res.trades[0]
        assert t.reason == "STOP" and t.ambiguous, rule.name
        assert t.exit_price == Decimal("200")  # tetik mumunun kapanışı (iç stop)


def test_R_ENTRY_02_OPEN_41_capa_mumu_emir_yoksa_giris_yok():
    """Gösterge kapısı kapalıyken emir yok: çapa mumu hiçbir şey doldurmaz."""
    res = kos([PRIMED, (172, 168), (202, 198)], ENTRY_079, require_indicator=True)
    assert res.counters["entries"] == 0
