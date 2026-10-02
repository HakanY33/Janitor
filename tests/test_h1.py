"""H1 analiz betiği — yalnızca sentetik veri (`docs/HYPOTHESES.md` §6). Ağ ve disk yok."""
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from scripts import h1_test as h1
from src.backtest.costs import CostModel, Fees
from src.zones.model import Zone, ZoneState

SYMS = [f"SYN{i}/USDT:USDT" for i in range(4)]
SYM = SYMS[0]
T0 = pd.Timestamp("2026-10-02 00:00", tz="UTC")
BLOK = 100  # dakika
BAS, SON = h1.DILIM_BAS, h1.DILIM_SON


def maliyet() -> CostModel:
    return CostModel(fees={s: Fees(Decimal("0.0005"), Decimal("0.0002")) for s in SYMS})


def blok(k: int, emilim: bool, kazanc: bool, bosluk: bool, id0: int, sym: str = SYM):
    """Tek SHORT zone (0=100, 1=110): 0.50 → bekleme → 0.70 teması (mum 70) → sonuç.

    Emilimli: W'da agresör alış 5/dk (taban 1/dk), ilerleme %22. Emilimsiz: ilerleme %89.
    """
    t = T0 + pd.Timedelta(minutes=k * BLOK)
    z = Zone.create(sym, "30m", 100.0, t - pd.Timedelta("2h"), 110.0, t - pd.Timedelta("30min"))
    assert z.watch_from == t
    bars = [(105, 105.2, 104.8, 105)] + [(105.8, 106.0, 105.5, 105.8)] * 65 \
        + [(106.5, 106.8, 106.0, 106.5)] * 4 \
        + [(106.6, 107.2 if emilim else 107.8, 106.5, 107.0)]
    bars += [(106, 106, 104.9, 105)] if kazanc else [(107.5, 110.1, 107, 110.1)]
    son = bars[-1][3]
    bars += [(son, son, son, son)] * (BLOK - len(bars))
    d1 = pd.DataFrame(bars, columns=["open", "high", "low", "close"])
    d1.insert(0, "ts", pd.date_range(t, periods=BLOK, freq="min"))
    tr, i = [], id0
    for m in range(71):
        an = t + pd.Timedelta(minutes=m, seconds=10)
        if bosluk and m == 30:
            i += 5  # 4 işlem kayıp
        tr += [(i, an, 1.0, "sell"), (i + 1, an, 5.0 if (emilim and m >= 66) else 1.0, "buy")]
        i += 2
    return z, d1, tr, i


def veri(n: int, p_emilim: float, p_emilimsiz: float, seed: int = 0, bosluk_k=(),
         semboller: int = 1):
    """n emilimli + n emilimsiz temas; kazanma olasılıkları sınıfa göre.

    Bloklar sembollere sırayla dağılır (kriter 3 en az iki sembol ister)."""
    rng = np.random.default_rng(seed)
    s = {x: ([], [], []) for x in SYMS[:semboller]}
    ids = dict.fromkeys(s, 0)  # fillId sembol başına ardışık
    for k in range(2 * n):
        em = k % 2 == 0
        sym = SYMS[(k // 2) % semboller]
        z, d1, tr, ids[sym] = blok(k, em, rng.random() < (p_emilim if em else p_emilimsiz),
                                   k in bosluk_k, ids[sym], sym)
        s[sym][0].append(z)
        s[sym][1].append(d1)
        s[sym][2].extend(tr)
    return [(x, z, pd.concat(d, ignore_index=True),
             pd.DataFrame(t, columns=["id", "ts", "qty", "side"]).sort_values("id"))
            for x, (z, d, t) in s.items()]


# --- kilit -----------------------------------------------------------------------

def test_H1_lock_refuses_trade_data_before_2027_01_01():
    with pytest.raises(h1.KilitHatasi):
        h1.veri_kilidi(pd.Timestamp("2026-12-31 23:59", tz="UTC"))
    with pytest.raises(h1.KilitHatasi):
        h1.islem_akisi_oku(SYM, BAS, SON, simdi=pd.Timestamp("2026-10-15", tz="UTC"))
    h1.veri_kilidi(pd.Timestamp("2027-01-01 00:00", tz="UTC"))  # kalkar


def test_H1_insufficient_n_reports_only_count_no_R():
    r = h1.analiz(veri(100, 0.9, 0.5), maliyet(), BAS, SON)
    assert r["n_emilimli"] == 100 and r["degerlendirme"]["sonuc"] == "KARARSIZ"
    assert "tablo" not in r, "n < 503 iken R hesaplanmamalı"


# --- etki var / yok ----------------------------------------------------------------

def test_H1_finds_planted_effect():
    r = h1.analiz(veri(600, 0.85, 0.6, semboller=4), maliyet(), BAS, SON)
    d = r["degerlendirme"]
    assert r["n_emilimli"] == 600 and d["kriter1"]
    assert d["alt_sinir"] > 0 and d["kriter3"] and d["sonuc"] == "KABUL"
    assert r["sayac"]["yok"] == 600


def test_H1_rejects_when_no_effect():
    r = h1.analiz(veri(600, 0.6, 0.6, seed=1, semboller=4), maliyet(), BAS, SON)
    d = r["degerlendirme"]
    assert d["kriter1"] and not d["kriter2"] and d["sonuc"] == "RET"


# --- boşluk kuralı (2026-09-30) ------------------------------------------------------

def test_H1_gap_in_window_excludes_touch_and_is_counted():
    r = h1.analiz(veri(10, 0.9, 0.5, bosluk_k=(0, 2, 3)), maliyet(), BAS, SON)
    assert r["sayac"]["dislandi_bosluk"] == 3
    assert r["n_emilimli"] == 8  # 0 ve 2 emilimliydi


def test_H1_touch_before_trade_coverage_is_excluded():
    (s, zones, d1, tr), = veri(3, 0.9, 0.5)
    tr = tr[tr.ts >= T0 + pd.Timedelta("20min")]  # ilk blokta 65 dk pencere kapsanmıyor
    r = h1.analiz([(s, zones, d1, tr)], maliyet(), BAS, SON)
    assert r["sayac"]["dislandi_bosluk"] == 1


def test_H1_zero_base_volume_excluded():
    (s, zones, d1, tr), = veri(1, 0.9, 0.5)
    tr = tr[tr.ts >= T0 + pd.Timedelta("66min")]
    tr = pd.concat([pd.DataFrame([(-1, T0, 1.0, "sell")], columns=tr.columns), tr])
    tr["id"] = range(len(tr))  # boşluk yok, yalnızca alış tabanı sıfır
    r = h1.analiz([(s, zones, d1, tr)], maliyet(), BAS, SON)
    assert r["sayac"]["dislandi_a60"] >= 1


# --- sonuç --------------------------------------------------------------------------

def _tek(bars):
    d = pd.DataFrame(bars, columns=["open", "high", "low", "close"])
    ts = pd.date_range(T0, periods=len(d), freq="min").tz_localize(None).to_numpy()
    return [ts] + [d[k].to_numpy(float) for k in d.columns]


def test_H1_outcome_stop_gap_fills_at_open_touch_at_close():
    z = Zone.create(SYM, "30m", 100.0, T0, 110.0, T0)
    ts, o, h, l, c = _tek([(107, 107, 107, 107), (111, 112, 110.5, 111.5)])  # boşluk
    assert h1.sonuc(z, 0, ts, o, h, l, c, Decimal("0"), maliyet())["cikis"] == 111
    ts, o, h, l, c = _tek([(107, 107, 107, 107), (108, 110.2, 108, 109)])  # temas
    x = h1.sonuc(z, 0, ts, o, h, l, c, Decimal("0"), maliyet())
    assert x["neden"] == "STOP" and x["cikis"] == 109


def test_H1_outcome_same_bar_is_stop_and_R_is_two_point():
    z = Zone.create(SYM, "30m", 100.0, T0, 110.0, T0)
    ts, o, h, l, c = _tek([(107, 107, 107, 107), (107, 110, 104, 107)])
    assert h1.sonuc(z, 0, ts, o, h, l, c, Decimal("0"), maliyet())["neden"] == "STOP"
    ts, o, h, l, c = _tek([(107, 107, 107, 107), (106, 106, 104.9, 105)])
    x = h1.sonuc(z, 0, ts, o, h, l, c, Decimal("0"), maliyet())
    assert x["neden"] == "TP" and x["R_brut"] == pytest.approx(2 / 3)
    assert x["R_net"] < x["R_brut"]  # slippage


def test_H1_outcome_time_exit_after_7_days_and_open_if_short_data():
    z = Zone.create(SYM, "30m", 100.0, T0, 110.0, T0)
    b = [(107, 107.5, 106.5, 107)] * (h1.TUTMA + 1)
    assert h1.sonuc(z, 0, *_tek(b), Decimal("0"), maliyet())["neden"] == "SURE"
    assert h1.sonuc(z, 0, *_tek(b[:100]), Decimal("0"), maliyet())["neden"] == "ACIK"


# --- olay tespiti Zone.on_bar ile aynı -------------------------------------------------

def test_H1_touch_event_matches_zone_fsm():
    rng = np.random.default_rng(7)
    for _ in range(300):
        long = rng.random() < 0.5
        a0, a1 = (110.0, 100.0) if long else (100.0, 110.0)
        n = 400
        mid = 106 + np.cumsum(rng.normal(0, 0.6, n))
        w = rng.uniform(0, 1.5, n)
        h, l = mid + w, mid - w
        ts = pd.date_range(T0, periods=n, freq="min")
        z = Zone.create(SYM, "30m", a0, T0 - pd.Timedelta("1h"), a1, T0 - pd.Timedelta("30min"))
        q, _ = h1.ilk_temas(z, ts.tz_localize(None).to_numpy(), h, l)
        f = Zone.create(SYM, "30m", a0, T0 - pd.Timedelta("1h"), a1, T0 - pd.Timedelta("30min"))
        f.activate()
        beklenen = None
        for i in range(n):
            if f.on_bar(h[i], l[i], ts[i]) is ZoneState.TOUCHED:
                beklenen = i
                break
            if f.state is ZoneState.INVALIDATED:
                break
        assert q == beklenen


def test_H1_net_R_includes_funding_at_symbol_interval():
    """§4 (2026-09-30): funding net R'ye girer; 4 saatlik sembolde 1 günde 6 an."""
    from src.backtest.costs import FundingCurve
    z = Zone.create(SYM, "30m", 100.0, T0, 110.0, T0)
    b = [(107, 107, 107, 107)] + [(107, 107.5, 106.5, 107)] * 1439 + [(106, 106, 104.9, 105)]
    c = maliyet()
    x0 = h1.sonuc(z, 0, *_tek(b), Decimal("0"), c)
    c.funding = {SYM: FundingCurve(np.array([], "datetime64[ns]"), np.array([]), 0.0001,
                                   pd.Timedelta("4h"))}
    x = h1.sonuc(z, 0, *_tek(b), Decimal("0"), c)
    assert c.funding_events == 6  # 04, 08, 12, 16, 20, 24
    # SHORT'a atanan oran aleyhte: maliyet = 6 × 1e-4 × 107 / 3 (R)
    assert x0["R_net"] - x["R_net"] == pytest.approx(6 * 1e-4 * 107 / 3)
