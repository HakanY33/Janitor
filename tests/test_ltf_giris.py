"""Spec v0.11 — 5m/30m/4h OB, OB girişi ve stopu, emir ömrü, ekleme (1-1, en fazla 3), OB rengi,
yeniden örnekleme ve boşluk kuralı.

Spec: §0.1 OB (kaynaklar, renk, boşluk), R-ENTRY-02 (OB/OTE girişi, emir ömrü), R-RISK-02
(OB girişinin stopu), R-ADD-01 (giriş ile `1` arasındaki OB), R-ADD-03 (1-1, en fazla 3).
Motor senaryoları `tests/test_backtest.py`'nin referans zone'unu kullanır: 0 = 100, 1 = 200
(SHORT), 0.50 = 150, bant 170–179.
"""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.backtest import loader
from src.backtest.costs import CostModel, Fees
from src.backtest.engine import ENTRY_OB_070, Backtest
from src.backtest.loader import build_from_frames, ornekle
from src.features.ob import OrderBlock, bos_time, detect_order_blocks
from src.features.structure import HIGH, Swing
from tests.test_backtest import SYM, short_zone, symbol_data, ts

T0 = pd.Timestamp("2026-01-01", tz="UTC")


def bedava() -> CostModel:
    return CostModel(fees={SYM: Fees(Decimal("0"), Decimal("0"))}, funding={},
                     slippage_bps=Decimal("0"))


def arz_ob(top: float, bottom: float, tf: str = "5m", mitig=None) -> OrderBlock:
    """Hemen bilinen, yapıyı kırmış arz (SHORT) OB'si."""
    return OrderBlock(ob_id=f"ob{tf}{top}", symbol=SYM, timeframe=tf, direction="BEARISH",
                      top=top, bottom=bottom, created_at=ts(-60), impulse_at=ts(-50),
                      bos_at=ts(-40), mitigated_at=mitig)


def kos(bars, obs=(), **kw):
    z = short_zone()
    sd = symbol_data(bars, z, obs)
    if obs and any(o.mitigated_at for o in obs):
        uzak = np.datetime64("2262-01-01")
        sd.ob_mitig = np.array([uzak if o.mitigated_at is None
                                else np.datetime64(o.mitigated_at.tz_localize(None)) for o in obs],
                               dtype="datetime64[ns]")
    kw = {"entry_rule": ENTRY_OB_070, "add_carpan": Decimal("1"), "t_rahat": Decimal("0.10"),
          "t_kritik": Decimal("0.01"), "k": Decimal("0.1"), **kw}
    return Backtest([sd], bedava(), **kw).run()


# --- R-ENTRY-02 / R-RISK-02 · OB girişi ----------------------------------------

def test_R_ENTRY_02_OB_girisi_oncelikli_stop_OB_otesinde():
    """Bantta arz OB'si 172–176: emir 0.70 (170) yerine OB'nin alt kenarında (172), stop OB'nin
    üstünde (176) — `1` (200) değil."""
    r = kos([(152, 148), (171, 169), (173, 171), (177, 175)], obs=(arz_ob(176, 172),))
    t = r.trades[0]
    assert (t.giris, t.entry_price, t.stop_price, t.reason) == ("OB", Decimal("172"), 176, "STOP")
    assert t.exit_price == Decimal("176") and r.counters["entries_ob"] == 1


def test_R_ENTRY_02_OB_yoksa_OTE_girisi_stop_1():
    r = kos([(152, 148), (171, 169), (202, 198)])
    t = r.trades[0]
    assert (t.giris, t.entry_price, t.stop_price, t.reason) == ("OTE", Decimal("170"), None, "STOP")
    assert t.exit_price == Decimal("200")


def test_R_RISK_02_OB_girisi_ayni_mumda_dolum_ve_stop():
    """Doluş mumu OB'yi de geçti (171–177): dolum 172, aynı mumda stop 176 (§8 stop önce)."""
    t = kos([(152, 148), (171, 169), (177, 171)], obs=(arz_ob(176, 172),)).trades[0]
    assert (t.entry_price, t.reason, t.exit_price) == (Decimal("172"), "STOP", Decimal("176"))


def test_R_RISK_02_OB_stopu_1in_otesindeyse_stop_1():
    """OB 172–210 `1`'i (200) aşıyor: stop `1`'de kalır."""
    t = kos([(152, 148), (171, 169), (173, 171), (202, 198)], obs=(arz_ob(210, 172),)).trades[0]
    assert t.stop_price is None and t.exit_price == Decimal("200")


def test_R_ENTRY_02_emir_050_donusunde_iptal_olmaz():
    """0.70 teması (TOUCHED), OB kenarına (172) gelinmeden 0.50'ye dönüş, sonra 172: emir yaşıyor."""
    r = kos([(152, 148), (171, 169), (152, 148), (173, 171)], obs=(arz_ob(176, 172),))
    assert r.counters["entries"] == 1 and r.trades[0].entry_price == Decimal("172")


def test_R_ENTRY_02_emir_zone_olunce_biter():
    """0.70 teması, sonra `0` (100): zone öldü, emir yok — sonra 172'ye gelinse de giriş yok."""
    r = kos([(152, 148), (171, 169), (102, 98), (173, 171)], obs=(arz_ob(176, 172),))
    assert r.counters["entries"] == 0


# --- R-ADD-01 / R-ADD-03 · ekleme --------------------------------------------

ADD_OBS = tuple(arz_ob(b + 2, b, "30m") for b in (181, 185, 189, 193))
ADD_BARS = [(152, 148), (171, 169), (183, 181), (187, 185), (191, 189), (195, 193)]


def test_R_ADD_03_bir_bir_en_fazla_uc_ekleme():
    """OTE girişi 170; giriş ile 1 arasında dört OB. 1-1: miktar her eklemede ikiye katlanır;
    dördüncü OB tavana takılır."""
    r = kos(ADD_BARS, obs=ADD_OBS, max_adds=3)
    t = r.trades[0]
    assert r.counters["adds"] == 3 and r.counters["adds_by_mult"] == {"1-1": 3}
    assert r.counters["add_reject_cap"] == 1
    assert t.qty == pytest.approx(t.entry_qty * 8)


def test_R_ADD_01_OB_girisli_pozisyona_ekleme_yok():
    """OB girişi (172–190, stop 190); giriş ile 1 arasında 180–184 OB'sine temas: ekleme yok."""
    r = kos([(152, 148), (171, 169), (173, 171), (184, 180)],
            obs=(arz_ob(190, 172), arz_ob(184, 180, "30m")))
    assert r.trades[0].giris == "OB"
    assert r.counters["adds"] == 0 and r.counters["add_reject_giris"] == 1


def test_R_ADD_01_giris_ile_1_disindaki_OB_ekleme_degil():
    """Girişin kâr tarafındaki (160–165) OB'ye temas: ekleme noktası değil."""
    r = kos([(152, 148), (171, 169), (165, 160)], obs=(arz_ob(165, 160, "4h"),))
    assert r.counters["adds"] == 0


def test_R_ADD_01_mitige_OB_ekleme_degil():
    r = kos(ADD_BARS[:3], obs=(arz_ob(183, 181, "30m", mitig=ts(-30)),))
    assert r.counters["adds"] == 0


def test_R_ADD_02_E_her_eklemede():
    """ADD-REJECT-E açık: ilk giriş geçer, ilk 1-1 ekleme stop kaybını tavanın üstüne çıkarır."""
    r = kos(ADD_BARS, obs=ADD_OBS, max_adds=3, stop_loss_cap=Decimal("0.02"))  # giriş %1,8 · 1-1 sonrası %2,8
    assert r.counters["entries"] == 1 and r.counters["adds"] == 0
    assert r.counters["add_reject_e"] >= 1


# --- §0.1 OB · renk, boşluk, zaman dilimleri ---------------------------------

def mumlar(rows, tf="5m", t0=T0) -> pd.DataFrame:
    return pd.DataFrame([{"ts": t0 + i * pd.Timedelta(tf), "open": o, "high": h, "low": lo,
                          "close": c, "volume": 1.0} for i, (o, h, lo, c) in enumerate(rows)])


TALEP = [(100, 100.5, 99, 99.2), (99.2, 99.8, 99.1, 99.7), (101, 103, 100.8, 102.5)]


def test_OB_renk_talebin_ilk_mumu_dusus():
    assert [o.direction for o in detect_order_blocks(mumlar(TALEP), SYM, "5m")] == ["BULLISH"]
    yukselis = [(99, 100.5, 99, 100.2)] + TALEP[1:]  # 1. mum yükseliş: talep OB'si değil
    doji = [(100, 100.5, 99, 100)] + TALEP[1:]
    assert detect_order_blocks(mumlar(yukselis), SYM, "5m") == []
    assert detect_order_blocks(mumlar(doji), SYM, "5m") == []


def test_OB_renk_arzin_ilk_mumu_yukselis():
    arz = [(100, 101, 99.5, 100.8), (100.8, 100.9, 100.2, 100.3), (99, 99.2, 97, 97.5)]
    assert [o.direction for o in detect_order_blocks(mumlar(arz), SYM, "5m")] == ["BEARISH"]
    dusus = [(101, 101, 99.5, 100.2)] + arz[1:]
    assert detect_order_blocks(mumlar(dusus), SYM, "5m") == []


def test_OB_bosluk_eksik_mum_desene_girmez():
    eksik = [TALEP[0], (np.nan, 99.8, 99.1, np.nan), TALEP[2]]
    assert detect_order_blocks(mumlar(eksik), SYM, "5m") == []


def test_ornekle_eksik_kova_nan_son_eksik_kova_atilir():
    d1 = mumlar([(100, 101, 99, 100.5)] * 12, "1m")
    d1 = d1.drop(index=[3]).reset_index(drop=True)  # 00:03 eksik
    d5 = ornekle(d1, "5m", "1m")
    assert list(d5.ts) == [T0, T0 + pd.Timedelta("5m")]  # 00:10 kovası kapanmadı
    assert np.isnan(d5.open[0]) and np.isnan(d5.close[0]) and d5.high[0] == 101
    assert not np.isnan(d5.close[1])


def test_ornekle_4h_utc_sinirli():
    d30 = mumlar([(100, 101, 99, 100.5)] * 20, "30m", T0 + pd.Timedelta("2h"))
    d4 = ornekle(d30, "4h", "30m")
    assert list(d4.ts) == [T0, T0 + pd.Timedelta("4h"), T0 + pd.Timedelta("8h")]
    assert np.isnan(d4.close[0]) and not np.isnan(d4.close[1])  # 00:00 kovası yarım


def test_OB_known_at_kendi_zaman_diliminin_kapanisi():
    o = detect_order_blocks(mumlar(TALEP, "4h"), SYM, "4h")[0]
    assert o.known_at == T0 + 3 * pd.Timedelta("4h")


def test_OPEN_66_B_eksik_mumun_kapanisi_kirmaz():
    df = mumlar(TALEP + [(102.5, 106, 102, np.nan), (102.5, 104, 102, 103)])
    tepe = Swing(swing_id="s", symbol=SYM, timeframe="5m", kind=HIGH, price=105.0,
                 ts=T0 - pd.Timedelta("1h"), pivot_confirmed_at=T0 - pd.Timedelta("30m"))
    ob = detect_order_blocks(df, SYM, "5m")[0]
    assert bos_time(ob, df, [tepe]) is None  # 106'lık fitil var ama kapanış NaN


def test_build_from_frames_uc_zaman_dilimi(monkeypatch):
    monkeypatch.setattr(loader, "OB_TFS", ("5m", "30m", "4h"))
    rng = np.random.default_rng(3)
    n = 3 * 24 * 60
    fiyat = 100 + np.cumsum(rng.normal(0, 0.05, n))
    d1 = pd.DataFrame({"ts": T0 + pd.to_timedelta(np.arange(n), "m"), "open": fiyat,
                       "high": fiyat + 0.08, "low": fiyat - 0.08,
                       "close": np.r_[fiyat[1:], fiyat[-1]], "volume": 1.0})
    d30 = ornekle(d1, "30m", "1m")
    sd = build_from_frames(SYM, d30, d1)
    assert {o.timeframe for o in sd.obs} == {"5m", "30m"} | ({"4h"} & {o.timeframe for o in sd.obs})
    assert all(o.known_at == o.impulse_at + pd.Timedelta(o.timeframe) for o in sd.obs)
    assert len(sd.ob_mitig) == len(sd.obs)


def test_canli_oynatma_5m_OB_yokken_hata_verir(monkeypatch):
    from src.live.replay import bos_sembol, kapanis
    monkeypatch.setattr(loader, "OB_TFS", ("5m", "30m", "4h"))
    bt = Backtest([bos_sembol(SYM)], bedava())
    with pytest.raises(NotImplementedError):
        kapanis(bt, SYM, mumlar(TALEP, "30m"), T0)


def test_B2_swing_known_at_zaman_dilimine_gore():
    from scripts.swing_secim import aday_b
    rng = np.random.default_rng(5)
    f = 100 + np.cumsum(rng.normal(0, 1, 300))
    df = mumlar([(a, a + 1.5, a - 1.5, a + 0.2) for a in f], "4h")
    sw = aday_b(df, SYM, 2, "4h")
    assert sw and all(s.known_at == s.pivot_confirmed_at + pd.Timedelta("4h") for s in sw)
