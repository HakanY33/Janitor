"""Bilgi anı değişmezi (CLAUDE.md #3) ve spec sözlüğündeki zamanlama kurallarının testleri.

**Değişmez.** Her nesne için `known_at ≥ hesaplamasında kullanılan son mumun kapanışı`.
Sınama yolu: yalnızca `known_at` anına kadar **kapanmış** mumları gören tespit, nesneyi
alan alan aynı üretmelidir. Üretemiyorsa nesne, damgasından sonra kapanan bir mumu
kullanmıştır. `mitigated_at`, `filled_at` ve delinme anı için aynısı.

D0 (`test_parity.py`) önek çıktısını tam çıktının `known_at ≤ kesim` kısmıyla
karşılaştırır: damga ile hesap birlikte bir mum kaysa D0 geçer. Bu dosya damganın
kendisini sınar — 2026-09-29'daki 30m look-ahead bu sınıftaydı.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.features.fvg import BEARISH, BULLISH, FVG, detect_fvgs, replay
from src.features.ob import OrderBlock, detect_order_blocks, pierce_time, replay_obs
from src.features.structure import detect_swings, htf_bias
from src.strategy.entry import fvg_eligible, ob_eligible
from src.zones.detect import detect_zones
from src.zones.model import STATE_BAR, Zone, ZoneState as S
from tests.test_parity import DF, SYM, TF, TD

T0 = pd.Timestamp("2026-01-01", tz="UTC")


def kapanmis(an: pd.Timestamp) -> pd.DataFrame:
    """`an` anına kadar kapanmış mumlar — o anda bilinebilecek verinin tamamı."""
    return DF[DF.ts + TD <= an].reset_index(drop=True)


def _kimlik(nesne) -> dict:
    return {k: v for k, v in vars(nesne).items()}


# --- değişmez: known_at ≥ kullanılan son mumun kapanışı ---------------------

def test_known_at_swing():
    for s in detect_swings(DF, SYM, TF):
        assert s.known_at == s.pivot_confirmed_at + TD
        gorulen = {x.swing_id: x for x in detect_swings(kapanmis(s.known_at), SYM, TF)}
        assert _kimlik(gorulen[s.swing_id]) == _kimlik(s)


def test_known_at_zone():
    zones = detect_zones(DF, SYM, TF)
    assert zones
    for z in zones:
        gorulen = {x.zone_id: x for x in detect_zones(kapanmis(z.known_at), SYM, TF)}
        assert _kimlik(gorulen[z.zone_id]) == _kimlik(z)


def test_known_at_ob_ve_mitigasyon():
    obs = detect_order_blocks(DF, SYM, TF)
    replay_obs(obs, DF)
    assert any(o.mitigated_at is not None for o in obs)
    for o in obs:
        gorulen = {x.ob_id: x for x in detect_order_blocks(kapanmis(o.known_at), SYM, TF)}
        assert (gorulen[o.ob_id].top, gorulen[o.ob_id].bottom, gorulen[o.ob_id].known_at) == \
            (o.top, o.bottom, o.known_at)
        if o.mitigated_at is not None:
            x = [x for x in detect_order_blocks(kapanmis(o.mitigated_at), SYM, TF)
                 if x.ob_id == o.ob_id]
            replay_obs(x, kapanmis(o.mitigated_at))
            assert x[0].mitigated_at == o.mitigated_at


def test_known_at_fvg_mitigasyon_ve_dolum():
    fvgs = detect_fvgs(DF, SYM, TF)
    replay(fvgs, DF)
    assert any(f.filled_at is not None for f in fvgs)
    for f in fvgs:
        assert f.known_at == f.created_at + TD
        for an in [f.known_at, f.mitigated_at, f.filled_at]:
            if an is None:
                continue
            x = [x for x in detect_fvgs(kapanmis(an), SYM, TF) if x.fvg_id == f.fvg_id]
            replay(x, kapanmis(an))
            assert x[0].known_at == f.known_at and x[0].width_ratio == f.width_ratio
            if an == f.mitigated_at:
                assert x[0].mitigated_at == f.mitigated_at
            if an == f.filled_at:
                assert x[0].filled_at == f.filled_at


def test_known_at_delinme():
    obs = detect_order_blocks(DF, SYM, TF)
    delinen = [(o, pierce_time(o, DF)) for o in obs]
    delinen = [(o, p) for o, p in delinen if p is not None]
    assert delinen
    for o, p in delinen:
        assert pierce_time(o, kapanmis(p)) == p


def test_known_at_htf_bias():
    tam = htf_bias(DF, SYM)
    for _, satir in tam.iloc[::7].iterrows():
        onek = htf_bias(kapanmis(satir.known_at), SYM)
        assert onek[onek.ts == satir.ts].bias.iloc[0] == satir.bias


# --- spec §0.1 sözlüğü ve R-ZONE-09: yazılı zamanlama kuralları --------------

def ob_(impulse: int) -> OrderBlock:
    return OrderBlock(ob_id="o", symbol=SYM, timeframe=TF, direction=BEARISH, top=178.0,  # SHORT zone
                      bottom=172.0, created_at=T0 + (impulse - 1) * TD,
                      impulse_at=T0 + impulse * TD)


def short_zone(**kw) -> Zone:
    return Zone.create(symbol=SYM, timeframe=TF, anchor_0_price=100.0, anchor_0_time=T0,
                       anchor_1_price=200.0, anchor_1_time=T0 + TD, **kw)


def test_sozluk_OB_impuls_mumu_kapaninca_bilinir():
    """§0.1 OB: değerlendirme impuls mumunun kapanışından önceye bakamaz."""
    o = ob_(impulse=3)
    z = short_zone()
    assert o.known_at == T0 + 4 * TD
    assert not ob_eligible(o, z, T0 + 3 * TD)  # impuls mumu açıldı, henüz kapanmadı
    assert not ob_eligible(o, z, T0 + 4 * TD - pd.Timedelta("1min"))
    assert ob_eligible(o, z, T0 + 4 * TD)


def test_sozluk_FVG_3_mum_kapaninca_bilinir():
    """§0.1 FVG: "boşluk ancak 3. mum kapanınca bilinir"."""
    f = FVG(fvg_id="f", symbol=SYM, timeframe=TF, direction=BULLISH, top=179.0, bottom=171.0,
            created_at=T0 + 2 * TD, width_ratio=1.0)
    z = short_zone()
    assert f.known_at == T0 + 3 * TD
    assert not fvg_eligible(f, z, T0 + 2 * TD)
    assert fvg_eligible(f, z, T0 + 3 * TD)


def test_sozluk_mitigasyon_ve_dolum_mum_kapanisinda():
    """§0.1 Mitigasyon ve R-ENTRY-05 "karar anında dolmamış": silinme (v0.8: ilk temas, OPEN-65)
    silen mum kapanmadan bilinmez — o mum içinde boşluk hâlâ açık sayılır."""
    df = pd.DataFrame({"ts": [T0 + i * TD for i in range(5)],
                       "open": [100, 110, 120, 120, 100.0], "high": [101, 111, 121, 121, 101.0],
                       "low": [99, 109, 119, 119.5, 99.0], "close": [100, 110, 120, 120, 100.0],
                       "volume": [1.0] * 5})
    f = detect_fvgs(df, SYM, TF)[0]  # 1. mum high 101, 3. mum low 119
    replay([f], df)
    assert f.filled_at == T0 + 5 * TD  # 5. mum (ts=4) kapanışı
    z = short_zone()
    f.top, f.bottom, f.width_ratio = 179.0, 171.0, 1.0  # bantla kesişsin; zaman alanları aynı
    assert fvg_eligible(f, z, T0 + 4 * TD)  # dolduran mum içinde: henüz bilinmiyor
    assert not fvg_eligible(f, z, T0 + 5 * TD)


def test_sozluk_delinme_fitil_yeter_bilgi_teyit_kapanisinda():
    """§0.1 Delinme: fitil yeter (kapanış fiyatı aranmaz); bilgi anı teyit mumlarının
    sonuncusunun kapanışıdır — "geri alma" o mumlar kapanmadan bilinmez."""
    obs = detect_order_blocks(DF, SYM, TF)
    for o in obs:
        p = pierce_time(o, DF)
        if p is not None:
            assert pierce_time(o, kapanmis(p - pd.Timedelta("1min"))) != p
            return
    pytest.fail("delinen OB yok")


def test_R_ZONE_09_watch_from_teyit_mumunun_kapanisi():
    """WATCH_FROM = max(anchor_1 HTF mum kapanışı, pivot teyit mumunun kapanışı)."""
    z = short_zone(pivot_confirmed_at=T0 + 5 * TD)
    assert z.watch_from == z.known_at == T0 + 6 * TD
    with pytest.raises(ValueError, match="look-ahead"):
        z.activate(); z.on_bar(150, 140, T0 + 5 * TD)


def test_R_ZONE_09_1m_gecis_mum_kapanisinda_damgalanir():
    """1m mumdan çıkan durum bilgisi o mum kapanınca bilinir."""
    z = short_zone()
    z.activate()
    t = z.watch_from
    assert z.on_bar(155, 145, t) is S.PRIMED
    assert z.primed_at == z.state_changed_at == t + STATE_BAR


def test_R_ZONE_10_bias_teyit_mumunun_kapanisinda():
    """R-ZONE-10: yön, teyit mumunun kapanışında bilinir (`known_at = ts + 4h`)."""
    b = htf_bias(DF, SYM)
    assert (b.known_at - b.ts == pd.Timedelta("4h")).all()
