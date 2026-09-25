"""R-ZONE-10 — swing tespiti, etiketleme, BoS ve yön testleri.

Look-ahead testi (`test_R_ZONE_10_no_lookahead`) bu dosyanın asıl sebebidir: yapı
tespiti geleceğe bakmaya en açık katmandır, çünkü bir pivot tanımı gereği kendinden
sonraki mumlarla teyitlenir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.structure import (
    ATR_PERIOD,
    DOWN,
    FRACTAL_N,
    HIGH,
    LOW,
    NONE,
    UP,
    atr,
    bias_at,
    bias_series,
    detect_swings,
    htf_bias,
)

T0 = pd.Timestamp("2026-01-01", tz="UTC")
SYM = "TEST/USDT:USDT"
TF = "30m"


def bars(prices, spread: float = 0.5, tf: str = TF) -> pd.DataFrame:
    """Fiyat yolundan mum çerçevesi. `spread` her mumun yarı aralığı — ATR'yi besler."""
    p = np.asarray(prices, dtype=float)
    return pd.DataFrame({
        "ts": T0 + pd.Timedelta(tf) * np.arange(len(p)),
        "open": np.concatenate([[p[0]], p[:-1]]),
        "high": p + spread,
        "low": p - spread,
        "close": p,
        "volume": np.full(len(p), 100.0),
    })


def warmup(n: int = 24) -> list[float]:
    """ATR'nin oturması için pivot üretmeyen giriş: ardışık eşit uçlar pivot sayılmaz."""
    return [100.0 + (i % 2) for i in range(n)]


def ramp(a: float, b: float, steps: int) -> list[float]:
    return list(np.linspace(a, b, steps + 1))[1:]


def labels(swings) -> list[tuple[str, str | None]]:
    return [(s.kind, s.label) for s in swings]


# --- R-ZONE-10 · fraktal pivot ------------------------------------------------


def test_R_ZONE_10_pivot_needs_n_bars_each_side():
    """Kenardaki mumlar pivot olamaz: solda/sağda N mum yoksa yapı tamamlanmaz."""
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 110, 5))
    swings = detect_swings(df, SYM, TF)
    assert swings, "tepe tespit edilmeliydi"
    for s in swings:
        i = int(df.ts.searchsorted(s.ts))
        assert FRACTAL_N <= i < len(df) - FRACTAL_N


def test_R_ZONE_10_pivot_confirmed_at_is_n_bars_later():
    """`pivot_confirmed_at` pivotun N mum sonrası — R-ZONE-09 WATCH_FROM bunu kullanır."""
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 110, 5))
    for s in detect_swings(df, SYM, TF):
        assert s.pivot_confirmed_at - s.ts == pd.Timedelta(TF) * FRACTAL_N
        assert s.pivot_confirmed_at > s.ts


def test_R_ZONE_10_flat_top_is_not_a_pivot():
    """Eşit iki tepe uçtur ama hangisinin uç olduğu tanımsız — pivot sayılmaz."""
    df = bars(warmup() + [110, 120, 120, 110, 100] + warmup(10))
    assert not [s for s in detect_swings(df, SYM, TF) if s.kind == HIGH and s.price > 119]


# --- R-ZONE-10 · yer degistirme filtresi --------------------------------------


def test_R_ZONE_10_displacement_filter_rejects_small_swings():
    """0.5 × ATR(14) altındaki salınım gürültüdür, swing üretmez."""
    df = bars(warmup() + ramp(100, 130, 6) + [129.9, 130.05, 129.9] + ramp(130, 105, 6))
    kucuk = [s for s in detect_swings(df, SYM, TF) if 129.0 < s.price < 130.1]
    assert not kucuk, "ATR'nin altındaki tepecik swing sayılmamalı"


def test_R_ZONE_10_displacement_filter_accepts_large_swings():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 105, 6) + ramp(105, 140, 8))
    swings = detect_swings(df, SYM, TF)
    assert [s.kind for s in swings][:2] == [HIGH, LOW]
    assert swings[0].price == pytest.approx(130.5, abs=0.6)


def test_R_ZONE_10_higher_displacement_filters_more():
    """Eşik büyüdükçe swing sayısı azalır — filtre gerçekten bağlayıcı."""
    yol = warmup() + ramp(100, 112, 5) + ramp(112, 104, 4) + ramp(104, 116, 5)
    df = bars(yol)
    sayilar = [len(detect_swings(df, SYM, TF, min_displacement=m)) for m in (0.0, 0.5, 5.0)]
    assert sayilar[0] >= sayilar[1] >= sayilar[2]
    assert sayilar[0] > sayilar[2]


def test_R_ZONE_10_threshold_is_atr_relative_not_absolute():
    """Aynı mutlak geri çekilme, oynak rejimde gürültü; sakin rejimde swing.

    Filtre fiyat cinsinden sabit bir sayı olsaydı iki rejim aynı sonucu verirdi.
    """
    kuyruk = ramp(100, 140, 8) + ramp(140, 135, 3) + ramp(135, 150, 6)
    sakin = detect_swings(bars([100.0 + (i % 2) for i in range(40)] + kuyruk), SYM, TF)
    oynak = detect_swings(bars([100.0 + 30 * (i % 2) for i in range(40)] + kuyruk), SYM, TF)
    geri_cekilme = [s for s in sakin if s.kind == LOW and 134 < s.price < 136]
    assert geri_cekilme, "sakin rejimde 5 birimlik geri çekilme swing olmalı"
    assert not [s for s in oynak if s.kind == LOW and 134 < s.price < 136]


# --- R-ZONE-10 · etiketleme ve BoS --------------------------------------------


def test_R_ZONE_10_labels_hh_and_hl_in_uptrend():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 160, 6))
    etiket = labels(detect_swings(df, SYM, TF))
    assert (HIGH, "HH") in etiket and (LOW, "HL") in etiket


def test_R_ZONE_10_labels_lh_and_ll_in_downtrend():
    df = bars(warmup() + ramp(100, 70, 6) + ramp(70, 88, 5)
              + ramp(88, 55, 7) + ramp(55, 72, 5) + ramp(72, 45, 6))
    etiket = labels(detect_swings(df, SYM, TF))
    assert (LOW, "LL") in etiket and (HIGH, "LH") in etiket


def test_R_ZONE_10_first_swing_of_each_kind_is_unlabeled():
    """Etiket önceki *aynı tip* swing'e göredir; ilkinde karşılaştırma yok."""
    swings = detect_swings(
        bars(warmup() + ramp(100, 130, 6) + ramp(130, 110, 5) + ramp(110, 145, 6)),
        SYM, TF,
    )
    ilk_high = next(s for s in swings if s.kind == HIGH)
    ilk_low = next(s for s in swings if s.kind == LOW)
    assert ilk_high.label is None and ilk_low.label is None
    assert not ilk_high.swept and not ilk_low.swept


def test_R_ZONE_10_swept_means_previous_same_kind_taken():
    """BoS = önceki aynı tip swing'in aşılması. HH ve LL süpürür, LH ve HL süpürmez."""
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 160, 6))
    for s in detect_swings(df, SYM, TF):
        assert s.swept == (s.label in ("HH", "LL"))


# --- R-ZONE-10 · yon ----------------------------------------------------------


def test_R_ZONE_10_bias_at_combinations():
    """`HH + HL` → UP · `LH + LL` → DOWN · karışık veya eksik → NONE."""
    def sw(kind, label):
        return type("S", (), {"kind": kind, "label": label})()

    assert bias_at(sw(HIGH, "HH"), sw(LOW, "HL")) == UP
    assert bias_at(sw(HIGH, "LH"), sw(LOW, "LL")) == DOWN
    assert bias_at(sw(HIGH, "HH"), sw(LOW, "LL")) == NONE
    assert bias_at(sw(HIGH, "LH"), sw(LOW, "HL")) == NONE
    assert bias_at(None, sw(LOW, "HL")) == NONE
    assert bias_at(sw(HIGH, "HH"), None) == NONE


def test_R_ZONE_10_bias_series_is_none_before_any_swing():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 110, 5))
    seri = bias_series(df, detect_swings(df, SYM, TF))
    assert (seri.iloc[: ATR_PERIOD] == NONE).all()


def test_R_ZONE_10_bias_series_matches_swings_known_at_that_bar():
    """Her mumdaki yön, yalnızca o mumda **teyitlenmiş** swing'lerden türemeli."""
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 160, 6))
    swings = detect_swings(df, SYM, TF)
    seri = bias_series(df, swings)
    for i, ts in enumerate(df.ts):
        bilinen = [s for s in swings if s.pivot_confirmed_at <= ts]
        son = {}
        for s in bilinen:
            son[s.kind] = s
        assert seri.iloc[i] == bias_at(son.get(HIGH), son.get(LOW))


def test_R_ZONE_10_uptrend_structure_yields_up_bias():
    df = bars(warmup() + ramp(100, 130, 6) + ramp(130, 112, 5)
              + ramp(112, 150, 7) + ramp(150, 128, 5) + ramp(128, 160, 6))
    assert UP in set(bias_series(df, detect_swings(df, SYM, TF)))


# --- look-ahead (ZORUNLU) -----------------------------------------------------


def rastgele_yol(n: int = 600, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0, 0.004, n))))


def test_R_ZONE_10_no_lookahead():
    """Veriyi herhangi bir noktadan kesmek, o ana kadar teyitlenmiş swing'leri değiştirmez.

    Bu, R-ZONE-10'un nedensellik testidir: tespit `pivot_confirmed_at`'ten sonraki
    hiçbir mumu kullanamaz. Kabul listesi yalnızca büyüdüğü için eşitlik birebir olmalı.
    """
    df = bars(rastgele_yol())
    tam = detect_swings(df, SYM, TF)

    def imza(swings):
        return [(s.kind, s.price, s.ts, s.pivot_confirmed_at, s.label, s.swept)
                for s in swings]

    for k in (80, 150, 240, 333, 480, 599):
        parca = df.iloc[:k].reset_index(drop=True)
        son_ts = parca.ts.iloc[-1]
        beklenen = [s for s in tam if s.pivot_confirmed_at <= son_ts]
        assert imza(detect_swings(parca, SYM, TF)) == imza(beklenen), f"kesim {k}"


def test_R_ZONE_10_bias_series_no_lookahead():
    """Aynı test yön serisi için: kesilen veride yön, tam veridekiyle aynı olmalı."""
    df = bars(rastgele_yol())
    tam = bias_series(df, detect_swings(df, SYM, TF))
    for k in (120, 300, 500):
        parca = df.iloc[:k].reset_index(drop=True)
        kesik = bias_series(parca, detect_swings(parca, SYM, TF))
        assert list(kesik) == list(tam.iloc[:k]), f"kesim {k}"


def test_R_ZONE_10_atr_is_causal():
    df = bars(rastgele_yol(200))
    tam = atr(df)
    for k in (50, 120, 199):
        assert atr(df.iloc[:k].reset_index(drop=True)).to_numpy() == pytest.approx(
            tam.iloc[:k].to_numpy(), nan_ok=True
        )


# --- R-ZONE-09 · tespit TF siniri ---------------------------------------------


def test_R_ZONE_09_structure_detection_rejects_1m():
    """Yapı tespiti de bir tespittir: 1m yalnızca durum geçişleri içindir."""
    df = bars(warmup() + ramp(100, 130, 6), tf="1m")
    with pytest.raises(ValueError, match="R-ZONE-09"):
        detect_swings(df, SYM, "1m")


# --- R-ZONE-07 · 4h yon serisi ------------------------------------------------


def test_R_ZONE_07_htf_bias_known_at_follows_bar_close():
    """Yön, mumun kapanışında bilinir; `known_at` bir sonraki mumun açılışıdır."""
    df = bars(rastgele_yol(800), tf="30m")
    h = htf_bias(df, SYM, "4h")
    assert (h.known_at - h.ts == pd.Timedelta("4h")).all()
    assert set(h.bias) <= {UP, DOWN, NONE}


def test_R_ZONE_07_htf_bias_lookup_never_sees_future():
    """Aşağı TF'deki bir karar yalnızca `known_at <= karar anı` satırını görebilir."""
    df = bars(rastgele_yol(800), tf="30m")
    h = htf_bias(df, SYM, "4h")
    for ts in df.ts[::50]:
        gorulen = h[h.known_at <= ts]
        if len(gorulen):
            assert gorulen.ts.iloc[-1] + pd.Timedelta("4h") <= ts
