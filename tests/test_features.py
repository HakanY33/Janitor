"""FVG ve OB tespiti, R-ADD-05 bayrakları, R-ADD-06 delinme kuralı.

Mumlar elle kurulur: leg tespiti (`OPEN-01`) bu dalda yok, çapa/zone gerekmez.

Referans gövde medyanı geçmişe bakar (`reference_body`), bu yüzden her senaryo
`flat_bars()` ile kurulan sakin bir geçmişle başlar: gövde 0.5, yani impuls eşiği
(`IMPULSE_MULT = 4.0`) 2.0'dır.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

from src.features.fvg import BEARISH, BULLISH, FVG, FvgStore, detect_fvgs, replay
from src.features.ob import (
    AddStrength,
    OrderBlock,
    detect_order_blocks,
    evaluate_strength,
    pierce_time,
    reference_body,
)

T0 = pd.Timestamp("2026-01-01", tz="UTC")
Rows = list[tuple[float, float, float, float]]


def candles(rows: Rows) -> pd.DataFrame:
    """(open, high, low, close) satırlarından 30m'lik OHLCV çerçevesi."""
    return pd.DataFrame(
        [
            {
                "ts": T0 + pd.Timedelta(minutes=30 * i),
                "open": o, "high": h, "low": lo, "close": c, "volume": 1.0,
            }
            for i, (o, h, lo, c) in enumerate(rows)
        ]
    )


def flat_bars(n: int = 25, price: float = 100.0) -> Rows:
    """Küçük gövdeli (0.5), çakışan mumlar: FVG üretmez, referans gövdeyi oturtur."""
    return [(price, price + 1, price - 1, price + 0.5)] * n


def fvgs_of(rows: Rows) -> list[FVG]:
    return detect_fvgs(candles(rows), "TEST/USDT:USDT", "30m")


def obs_of(rows: Rows) -> list[OrderBlock]:
    return detect_order_blocks(candles(rows), "TEST/USDT:USDT", "30m")


# --- FVG · tespit ------------------------------------------------------------

def test_FVG_bullish_bosluk_birinci_mumun_tepesi_ile_ucuncunun_dibi_arasi():
    """1. mumun high'ı 3. mumun low'unun altındaysa dokunulmamış boşluk vardır."""
    f, = fvgs_of([(100, 101, 99, 100.5), (101, 110, 100.5, 109), (109, 112, 105, 111)])
    assert (f.direction, f.bottom, f.top) == (BULLISH, 101, 105)


def test_FVG_bearish_bosluk_ters_yonde():
    f, = fvgs_of([(110, 111, 109, 109.5), (109, 110, 100, 101), (101, 104, 99, 100)])
    assert (f.direction, f.bottom, f.top) == (BEARISH, 104, 109)


def test_FVG_sinirlar_govdeden_degil_fitilden_gelir():
    """Gövdeler ayrık ama fitiller çakışıyorsa boşluk yoktur."""
    assert fvgs_of([(100, 106, 99, 105), (105, 110, 104, 109), (109, 112, 105.5, 111)]) == []


def test_FVG_cakisan_mumlarda_bosluk_yok():
    assert fvgs_of(flat_bars(5)) == []


def test_FVG_olusum_zamani_ucuncu_mumdur():
    """Boşluk ancak 3. mum kapanınca bilinir (CLAUDE.md #3: look-ahead yasak)."""
    f, = fvgs_of([(100, 101, 99, 100.5), (101, 110, 100.5, 109), (109, 112, 105, 111)])
    assert f.created_at == T0 + pd.Timedelta(minutes=60)


def test_FVG_ucten_az_mumda_tespit_yok():
    assert fvgs_of([(100, 101, 99, 100.5), (101, 110, 100.5, 109)]) == []


# --- FVG · mitigasyon --------------------------------------------------------

def bullish_fvg() -> FVG:
    """Boşluk 101 – 105."""
    f, = fvgs_of([(100, 101, 99, 100.5), (101, 110, 100.5, 109), (109, 112, 105, 111)])
    return f


def test_FVG_temas_mitigasyon_isaretler_ama_doldurmaz():
    f = bullish_fvg()
    f.on_bar(112, 103, T0)  # boşluğun içine girildi, dibine inilmedi
    assert f.mitigated_at == T0 and f.filled_at is None


def test_FVG_karsi_sinir_gecilince_dolar():
    f = bullish_fvg()
    f.on_bar(112, 100.9, T0)  # 101'in altına inildi → boşluk kapandı
    assert f.filled_at == T0 and f.mitigated_at == T0


def test_FVG_boslugu_kesmeyen_mum_durumu_degistirmez():
    f = bullish_fvg()
    f.on_bar(120, 106, T0)
    assert (f.mitigated_at, f.filled_at) == (None, None)


def test_FVG_dolmus_bosluk_tekrar_temasla_degismez():
    f = bullish_fvg()
    f.on_bar(112, 100, T0)
    f.on_bar(112, 95, T0 + pd.Timedelta(minutes=30))
    assert f.filled_at == T0  # ilk dolum anı korunur


def test_FVG_bearish_bosluk_yukaridan_dolar():
    f, = fvgs_of([(110, 111, 109, 109.5), (109, 110, 100, 101), (101, 104, 99, 100)])
    f.on_bar(106, 99, T0)  # boşluk 104 – 109
    assert (f.mitigated_at, f.filled_at) == (T0, None)
    f.on_bar(109.5, 99, T0)
    assert f.filled_at == T0


def test_FVG_replay_olusumdan_onceki_mumlari_islemez():
    """Boşluk oluşmadan önceki mumlar mitigasyon sayılmaz (look-ahead'in aynası)."""
    rows = [(100, 101, 99, 100.5), (101, 110, 100.5, 109), (109, 112, 105, 111)]
    df = candles(rows)
    f, = detect_fvgs(df, "TEST/USDT:USDT", "30m")
    replay([f], df)  # 2. mum 100.5'e kadar iniyor ama boşluk henüz yoktu
    assert (f.mitigated_at, f.filled_at) == (None, None)


def test_FVG_sqlite_round_trip(tmp_path):
    store = FvgStore(tmp_path / "state.db")
    f = bullish_fvg()
    f.on_bar(112, 103, T0)
    store.save(f)
    assert store.get(f.fvg_id) == f


def test_FVG_store_yalnizca_dolmamislari_dondurur(tmp_path):
    store = FvgStore(tmp_path / "state.db")
    acik, dolu = bullish_fvg(), bullish_fvg()
    dolu.fvg_id, dolu.filled_at = "dolu", T0
    for f in (acik, dolu):
        store.save(f)
    assert [f.fvg_id for f in store.unfilled()] == [acik.fvg_id]


# --- OB · tespit -------------------------------------------------------------

def test_OB_impuls_oncesi_son_ters_yonlu_mum_govdesi():
    """Yukarı impulstan önceki son düşüş mumunun gövdesi talep bloğudur."""
    rows = flat_bars() + [(100, 100.5, 99.3, 99.6), (99.6, 106, 99.6, 105)]
    ob, = obs_of(rows)
    assert (ob.direction, ob.top, ob.bottom) == (BULLISH, 100, 99.6)


def test_OB_sinirlar_govdeden_gelir_fitil_disarida():
    rows = flat_bars() + [(100, 103, 90, 99.6), (99.6, 106, 99.6, 105)]
    ob, = obs_of(rows)
    assert (ob.top, ob.bottom) == (100, 99.6)  # 103 / 90 fitilleri OB'ye girmez


def test_OB_bearish_impuls_oncesi_son_yukselis_mumu():
    rows = flat_bars() + [(100, 100.7, 99.5, 100.4), (100.4, 100.4, 94, 95)]
    ob, = obs_of(rows)
    assert (ob.direction, ob.top, ob.bottom) == (BEARISH, 100.4, 100)


def test_OB_normal_govdeli_hareket_ob_uretmez():
    """İmpuls yoksa OB yok: eşik referans gövdenin `IMPULSE_MULT` (4.0) katı."""
    rows = flat_bars() + [(100, 100.5, 99, 99.5), (99.5, 100.3, 99.5, 100.2)]
    assert obs_of(rows) == []


def test_OB_impuls_aninda_bilinir():
    """OB, impuls mumu kapanmadan bilinemez — `impulse_at` bu yüzden ayrı alandır."""
    rows = flat_bars() + [(100, 100.5, 99.3, 99.6), (99.6, 106, 99.6, 105)]
    ob, = obs_of(rows)
    ts = candles(rows).ts
    assert (ob.created_at, ob.impulse_at) == (ts.iloc[-2], ts.iloc[-1])


def test_OB_ardisik_impuls_ayni_bloku_tekrar_uretmez():
    rows = flat_bars() + [
        (100, 100.5, 99.3, 99.6), (99.6, 106, 99.6, 105), (105, 112, 105, 111),
    ]
    assert len(obs_of(rows)) == 1


@pytest.mark.parametrize("tf,kabul", [("1m", False), ("5m", True), ("30m", True), ("4h", True)])
def test_R_ZONE_09_tespit_5m_ve_ustunde_calisir(tf, kabul):
    """1m yalnızca durum geçişleri içindir; tespit sessizce kabul etmez, hata verir."""
    df = candles(flat_bars() + [(100, 100.5, 99.3, 99.6), (99.6, 106, 99.6, 105)])
    for detect in (detect_order_blocks, detect_fvgs):
        if kabul:
            detect(df, "TEST/USDT:USDT", tf)
        else:
            with pytest.raises(ValueError, match="R-ZONE-09"):
                detect(df, "TEST/USDT:USDT", tf)


def test_OB_referans_govde_kendi_mumunu_saymaz():
    """`reference_body` shift(1)'lidir: büyük mum kendi eşiğini yükseltemez."""
    df = candles(flat_bars() + [(100, 110, 100, 109)])
    assert reference_body(df).iloc[-1] == 0.5


# --- R-ADD-06 · hacimli delinme ---------------------------------------------

PIERCE_HEAD = flat_bars() + [
    (100, 100.5, 99.3, 99.6),  # OB gövdesi 99.6 – 100
    (99.6, 106, 99.6, 105),  # impuls
]


def pierced(tail: Rows):
    """OB'yi kurar, kuyruk mumlarıyla delinme zamanını arar. İlk kuyruk mumu = ts[len(HEAD)].

    Kuyruktaki büyük gövdeli geçiş mumu kendi ters yönlü OB'sini üretir; ölçülen,
    listenin ilki olan talep bloğudur (99.6 – 100).
    """
    rows = PIERCE_HEAD + tail
    df = candles(rows)
    ob = detect_order_blocks(df, "TEST/USDT:USDT", "30m")[0]
    return pierce_time(ob, df), df.ts


def test_R_ADD_06_buyuk_govdeli_mumla_tam_gecis_delinmedir():
    when, ts = pierced([(105, 105, 99, 99.5), (99.5, 99.6, 98, 98.5), (98.5, 99, 98, 98.2)])
    assert when == ts.iloc[len(PIERCE_HEAD)]


def test_R_ADD_06_kucuk_govdeli_gecis_delinme_degil():
    """Sürünerek geçiş hacim değildir: geçiş mumlarının ortalama gövdesi eşiğin altında."""
    tail = [(100.4, 100.5, 100, 100.1), (100.1, 100.2, 99.8, 99.9), (99.9, 100, 99.5, 99.6)]
    assert pierced(tail)[0] is None


def test_R_ADD_06_kismi_giris_delinme_degil():
    """OB'nin içine girmek yetmez, tamamen geçilmesi gerekir."""
    assert pierced([(105, 105, 99.7, 99.8), (99.8, 99.9, 99.65, 99.7)])[0] is None


def test_R_ADD_06_altina_inip_hemen_donme_delinme_degil():
    """Grafik hatası / geç tepki: fiyat OB'yi geri alırsa delinme sayılmaz."""
    assert pierced([(105, 105, 99, 99.5), (99.5, 100.5, 99.4, 100.2)])[0] is None


def test_R_ADD_06_mum_kapanisi_beklenmez():
    """Kapanış OB'nin içinde kalsa da fitil tamamen geçtiyse ve dönüş yoksa delinmedir."""
    when, ts = pierced([(105, 105, 99, 99.8), (99.8, 99.9, 99, 99.2), (99.2, 99.5, 98, 98.5)])
    assert when == ts.iloc[len(PIERCE_HEAD)]


def test_R_ADD_06_ob_olusmadan_onceki_mumlar_delinme_saymaz():
    """OB, impuls mumundan önce delinemez — geçmiş mumlar kapsam dışı (look-ahead)."""
    df = candles(PIERCE_HEAD)
    ob, = detect_order_blocks(df, "TEST/USDT:USDT", "30m")
    assert pierce_time(ob, df) is None


# --- R-ADD-05 · güç bayrakları ----------------------------------------------

def ob_with_fvg() -> tuple[OrderBlock, list[FVG]]:
    """OB 98–100; içine denk gelen, doldurulmamış bir bullish FVG (98.5 – 99.5)."""
    ob = OrderBlock(
        ob_id="ob", symbol="TEST/USDT:USDT", timeframe="30m", direction=BULLISH,
        top=100.0, bottom=98.0, created_at=T0, impulse_at=T0 + pd.Timedelta(minutes=30),
    )
    fvg = FVG(
        fvg_id="f", symbol="TEST/USDT:USDT", timeframe="30m", direction=BULLISH,
        top=99.5, bottom=98.5, created_at=T0,
    )
    return ob, [fvg]


def test_R_ADD_05_ob_icindeki_doldurulmamis_fvg_bayrak_kaldirir():
    ob, fvgs = ob_with_fvg()
    assert evaluate_strength(ob, fvgs).fvg_inside_unfilled is True


def test_R_ADD_05_dolmus_fvg_bayrak_kaldirmaz():
    ob, fvgs = ob_with_fvg()
    fvgs[0].filled_at = T0
    assert evaluate_strength(ob, fvgs).fvg_inside_unfilled is False


def test_R_ADD_05_ob_disindaki_fvg_sayilmaz():
    ob, fvgs = ob_with_fvg()
    fvgs[0].top, fvgs[0].bottom = 120.0, 119.0
    assert evaluate_strength(ob, fvgs).fvg_inside_unfilled is False


def test_R_ADD_05_sonradan_dolan_fvg_degerlendirme_aninda_aciktir():
    """Bayraklar değerlendirme anına göre kurulur; sonraki dolum geriye işlemez."""
    ob, fvgs = ob_with_fvg()
    fvgs[0].filled_at = T0 + pd.Timedelta(days=1)
    assert evaluate_strength(ob, fvgs).fvg_inside_unfilled is True


def test_R_ADD_05_ters_yonlu_ob_bayrak_kaldirir():
    ob, _ = ob_with_fvg()
    ters = OrderBlock(
        ob_id="x", symbol="TEST/USDT:USDT", timeframe="30m", direction=BEARISH,
        top=105.0, bottom=104.0, created_at=T0, impulse_at=T0,
    )
    assert evaluate_strength(ob, obs=[ters]).opposite_ob is True
    assert evaluate_strength(ob, obs=[]).opposite_ob is False


def test_R_ADD_05_sonraki_ob_degerlendirmeye_girmez():
    """Değerlendirme anından sonra oluşan OB bilinemez (look-ahead)."""
    ob, _ = ob_with_fvg()
    sonraki = OrderBlock(
        ob_id="x", symbol="TEST/USDT:USDT", timeframe="30m", direction=BEARISH,
        top=105.0, bottom=104.0, created_at=T0, impulse_at=T0 + pd.Timedelta(days=1),
    )
    assert evaluate_strength(ob, obs=[sonraki]).opposite_ob is False


def test_R_ADD_05_ardisik_ayni_yonlu_ob_serisi_bayrak_kaldirir():
    ob, _ = ob_with_fvg()
    onceki = OrderBlock(
        ob_id="x", symbol="TEST/USDT:USDT", timeframe="30m", direction=BULLISH,
        top=95.0, bottom=94.0, created_at=T0, impulse_at=T0 - pd.Timedelta(minutes=30),
    )
    assert evaluate_strength(ob, obs=[onceki]).consecutive_obs is True


def test_R_ADD_05_araya_ters_ob_girerse_seri_bozulur():
    ob, _ = ob_with_fvg()
    eski = OrderBlock(
        ob_id="a", symbol="TEST/USDT:USDT", timeframe="30m", direction=BULLISH,
        top=95.0, bottom=94.0, created_at=T0, impulse_at=T0 - pd.Timedelta(hours=2),
    )
    ters = OrderBlock(
        ob_id="b", symbol="TEST/USDT:USDT", timeframe="30m", direction=BEARISH,
        top=96.0, bottom=95.0, created_at=T0, impulse_at=T0 - pd.Timedelta(minutes=30),
    )
    assert evaluate_strength(ob, obs=[eski, ters]).consecutive_obs is False


def test_R_ADD_05_skor_degil_bayrak_doner():
    """Skorlaştırma R-ZONE-08'e ait (TASARLANACAK) — burada yalnızca bayrak vardır."""
    assert [f.type for f in fields(AddStrength)] == ["bool", "bool", "bool"]
    ob, fvgs = ob_with_fvg()
    assert evaluate_strength(ob, fvgs) == AddStrength(
        fvg_inside_unfilled=True, opposite_ob=False, consecutive_obs=False
    )


# --- NEAR raporu -------------------------------------------------------------

NEAR_30M = Path("data/bingx/NEAR-USDT-USDT/30m/2026-09.parquet")
NO_DATA = "data/ gitignore'da — scripts/backfill.py ile toplanir"
# STRATEGY_SPEC §0 referans örneğinin penceresi: çapa 0'dan ilk TP'ye kadar.
PENCERE = (pd.Timestamp("2026-09-08 13:30", tz="UTC"), pd.Timestamp("2026-09-10 12:00", tz="UTC"))
BANT = (2.527, 2.563)  # giriş bandı 0.70 – 0.79


def _saat(t) -> str:
    return t.strftime("%m-%d %H:%M") if t is not None else "-"


@pytest.mark.skipif(not NEAR_30M.exists(), reason=NO_DATA)
def test_NEAR_ob_ve_fvg_listesi_raporlanir(capsys):
    """NEAR 30m referans penceresinde tespit edilen OB ve FVG'ler (`pytest -s`).

    Doğrulanan: sınırlar tutarlı, nesneler pencere içinde, OB impuls mumundan önce
    bilinmiyor. Liste gözle karşılaştırmak içindir — grafikteki bölgelerle örtüşmeli.
    """
    df = pd.read_parquet(NEAR_30M)
    df = df[(df.ts >= PENCERE[0]) & (df.ts <= PENCERE[1])].reset_index(drop=True)
    fvgs = detect_fvgs(df, "NEAR/USDT:USDT", "30m")
    replay(fvgs, df)
    obs = detect_order_blocks(df, "NEAR/USDT:USDT", "30m")
    assert fvgs and obs  # referans pencerede en az birer tane bulunmalı

    def bantta(top: float, bottom: float) -> str:
        return "  <- giris bandi" if bottom <= BANT[1] and top >= BANT[0] else ""

    lines = [f"NEAR/USDT:USDT 30m | {_saat(PENCERE[0])} -> {_saat(PENCERE[1])}", ""]
    lines.append(f"FVG ({len(fvgs)})   yön      alt      üst     oluşum      mitigasyon  dolum")
    for f in fvgs:
        assert f.top > f.bottom and PENCERE[0] <= f.created_at <= PENCERE[1]
        lines.append(
            f"         {f.direction:<8} {f.bottom:>7.4f}  {f.top:>7.4f}  "
            f"{_saat(f.created_at):<11} {_saat(f.mitigated_at):<11} {_saat(f.filled_at):<11}"
            f"{bantta(f.top, f.bottom)}"
        )

    lines += ["", f"OB ({len(obs)})    yön      alt      üst     gövde       impuls      delinme     R-ADD-05"]
    for ob in obs:
        assert ob.top > ob.bottom and ob.impulse_at >= ob.created_at
        güç = evaluate_strength(ob, fvgs, obs)
        lines.append(
            f"         {ob.direction:<8} {ob.bottom:>7.4f}  {ob.top:>7.4f}  "
            f"{_saat(ob.created_at):<11} {_saat(ob.impulse_at):<11} "
            f"{_saat(pierce_time(ob, df)):<11} "
            f"fvg={int(güç.fvg_inside_unfilled)} ters={int(güç.opposite_ob)} "
            f"seri={int(güç.consecutive_obs)}{bantta(ob.top, ob.bottom)}"
        )

    with capsys.disabled():
        print()
        for line in lines:
            print(line)
