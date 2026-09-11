"""R-ZONE-01/03/04/05 — zone modeli, durum makinesi ve kalıcılık testleri.

Her geçiş için hem geçerli hem geçersiz yol denenir. Zone nesneleri elle kurulur:
leg/uç tespiti (R-ZONE-02) adım 3'tür, burada kapsam dışı.

Test zone'u yuvarlak sayılarla: 0 = 100 (altta), 1 = 200 (üstte) → SHORT bias,
0.50 = 150, 0.70 = 170, 0.79 = 179.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

from src.zones.model import InvalidTransition, Zone, ZoneState as S
from src.zones.store import ZoneStore

T0 = pd.Timestamp("2026-01-01", tz="UTC")


def ts(i: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=30 * i)


def short_zone(**kw) -> Zone:
    return Zone.create(
        symbol="TEST/USDT:USDT",
        timeframe="30m",
        anchor_0_price=100.0,
        anchor_0_time=ts(0),
        anchor_1_price=200.0,
        anchor_1_time=ts(1),
        **kw,
    )


def zone_in(state: S) -> Zone:
    """İstenen duruma kadar ilerletilmiş zone. Kestirme yok, gerçek geçişler kullanılır."""
    z = short_zone()
    z.activate(ts(2))
    if state is S.ACTIVE:
        return z
    z.on_bar(155, 145, ts(3))  # 0.50 teması
    if state is S.PRIMED:
        return z
    z.on_bar(175, 165, ts(4))  # 0.70 teması
    if state is S.TOUCHED:
        return z
    z.enter(ts(4))
    if state is S.ENTERED:
        return z
    z.on_bar(155, 145, ts(5))  # ilk TP
    if state is S.TP1_HIT:
        return z
    raise ValueError(state)


# --- R-ZONE-01 · alanlar -----------------------------------------------------

def test_R_ZONE_01_alanlar_spec_ile_birebir():
    assert [f.name for f in fields(Zone)] == [
        "zone_id", "symbol", "timeframe", "bias",
        "anchor_0_price", "anchor_0_time", "anchor_1_price", "anchor_1_time",
        "level_050", "level_070", "level_079", "state",
        "created_at", "state_changed_at", "primed_at", "touch_count", "quality_score",
    ]


def test_R_ZONE_01_bias_cizim_yonunden_gelir():
    assert short_zone().bias == "SHORT"  # 0 altta, 1 üstte
    long_zone = Zone.create(
        symbol="TEST/USDT:USDT", timeframe="30m",
        anchor_0_price=200.0, anchor_0_time=ts(0),
        anchor_1_price=100.0, anchor_1_time=ts(1),
    )
    assert long_zone.bias == "LONG"  # 0 üstte, 1 altta


def test_R_ZONE_01_tz_naive_capa_reddedilir():
    with pytest.raises(ValueError, match="UTC"):
        Zone.create(
            symbol="TEST/USDT:USDT", timeframe="30m",
            anchor_0_price=100.0, anchor_0_time=pd.Timestamp("2026-01-01"),
            anchor_1_price=200.0, anchor_1_time=ts(1),
        )


def test_R_ZONE_01_touch_count_giris_bandi_temaslarini_sayar():
    z = zone_in(S.PRIMED)
    assert z.touch_count == 0
    z.on_bar(175, 165, ts(4))  # 0.70 teması → TOUCHED
    z.on_bar(175, 168, ts(5))  # bant tekrar test edildi
    assert z.touch_count == 2


def test_R_ZONE_01_quality_score_hesaplanmaz():
    assert short_zone().quality_score is None  # R-ZONE-08 TASARLANACAK


# --- R-ZONE-03 · seviyeler ---------------------------------------------------

def test_R_ZONE_03_seviyeler_lineer():
    z = short_zone()
    assert (z.level_050, z.level_070, z.level_079) == (150.0, 170.0, 179.0)


def test_R_ZONE_03_long_biasta_seviyeler_ters_yonde():
    z = Zone.create(
        symbol="TEST/USDT:USDT", timeframe="30m",
        anchor_0_price=200.0, anchor_0_time=ts(0),
        anchor_1_price=100.0, anchor_1_time=ts(1),
    )
    assert (z.level_050, z.level_070, z.level_079) == (150.0, 130.0, 121.0)


# --- R-ZONE-04 · durum makinesi ---------------------------------------------

def test_R_ZONE_04_created_to_active():
    z = short_zone()
    z.activate(ts(2))
    assert z.state is S.ACTIVE and z.state_changed_at == ts(2)


def test_R_ZONE_04_created_durumunda_fiyat_islenmez():
    z = short_zone()
    z.on_bar(155, 145, ts(2))  # izlemeye alınmamış zone (R-ZONE-06) fiyat görmez
    assert z.state is S.CREATED


def test_R_ZONE_04_created_to_primed_gecersiz():
    z = short_zone()
    with pytest.raises(InvalidTransition):
        z.transition(S.PRIMED, ts(2))


def test_R_ZONE_04_active_to_primed_050_temasiyla():
    z = zone_in(S.ACTIVE)
    assert z.on_bar(155, 145, ts(3)) is S.PRIMED
    assert z.primed_at == ts(3)


def test_R_ZONE_04_050_temasi_olmadan_070_giris_uretmez():
    """Ön koşul atlanamaz (§0 ②). Fiyat giriş bandına gelse bile zone silahlı değil."""
    z = zone_in(S.ACTIVE)
    z.on_bar(179, 170, ts(3))  # tam giriş bandı, ama 0.50 hiç görülmedi
    assert z.state is S.ACTIVE
    z.on_bar(175, 168, ts(4))  # tekrar bantta — yine giriş yok
    assert z.state is S.ACTIVE
    assert z.primed_at is None


def test_R_ZONE_04_active_to_entered_gecersiz():
    z = zone_in(S.ACTIVE)
    with pytest.raises(InvalidTransition):
        z.enter(ts(3))


def test_R_ZONE_04_primed_to_touched_070_temasiyla():
    z = zone_in(S.PRIMED)
    assert z.on_bar(172, 168, ts(4)) is S.TOUCHED


def test_R_ZONE_04_primed_070_altinda_kalirsa_touched_olmaz():
    z = zone_in(S.PRIMED)
    z.on_bar(169.9, 160, ts(4))  # banda değmedi
    assert z.state is S.PRIMED


def test_R_ZONE_04_touched_to_entered_stratejinin_karari():
    """Giriş fiyatla değil strateji katmanının onayıyla olur (R-ENTRY-02)."""
    z = zone_in(S.TOUCHED)
    z.on_bar(179, 171, ts(5))  # bantta kalmak tek başına pozisyon açmaz
    assert z.state is S.TOUCHED
    z.enter(ts(5))
    assert z.state is S.ENTERED


def test_R_ZONE_04_entered_to_tp1_050_temasiyla():
    z = zone_in(S.ENTERED)
    assert z.on_bar(160, 150, ts(5)) is S.TP1_HIT


def test_R_ZONE_04_touched_durumunda_050_temasi_tp1_uretmez():
    z = zone_in(S.TOUCHED)
    z.on_bar(155, 145, ts(5))  # pozisyon yokken TP olmaz
    assert z.state is S.TOUCHED


def test_R_ZONE_04_tp1_to_closed_nihai_tp():
    z = zone_in(S.TP1_HIT)
    assert z.on_bar(120, 100, ts(6)) is S.CLOSED


def test_R_ZONE_04_tp1_050_tekrar_temasi_durum_degistirmez():
    z = zone_in(S.TP1_HIT)
    z.on_bar(155, 145, ts(6))
    assert z.state is S.TP1_HIT


@pytest.mark.parametrize("state", [S.CLOSED, S.INVALIDATED])
def test_R_ZONE_04_terminal_durumdan_cikis_yok(state):
    z = zone_in(S.TP1_HIT)
    z.transition(state, ts(6))
    assert z.on_bar(155, 145, ts(7)) is state
    with pytest.raises(InvalidTransition):
        z.transition(S.ACTIVE, ts(7))


def test_R_ZONE_04_tek_mumda_tek_gecis():
    """Mum içi sıra bilinmez: 0.50 ve 0.70'i aynı mumda gören zone yalnızca PRIMED olur."""
    z = zone_in(S.ACTIVE)
    assert z.on_bar(175, 145, ts(3)) is S.PRIMED
    assert z.on_bar(175, 165, ts(4)) is S.TOUCHED


# --- R-ZONE-05 · geçersizlik -------------------------------------------------

@pytest.mark.parametrize("state", [S.ACTIVE, S.PRIMED, S.TOUCHED])
@pytest.mark.parametrize("anchor", [100.0, 200.0])
def test_R_ZONE_05_capa_temasi_giris_oncesi_zone_u_oldurur(state, anchor):
    z = zone_in(state)
    assert z.on_bar(anchor, anchor, ts(6)) is S.INVALIDATED


@pytest.mark.parametrize("state", [S.ENTERED, S.TP1_HIT])
@pytest.mark.parametrize("anchor", [100.0, 200.0])
def test_R_ZONE_05_capa_temasi_pozisyon_varken_kapatir(state, anchor):
    """Pozisyon açıkken 1 = nihai stop, 0 = nihai TP. İkisi de CLOSED (R-ZONE-04 tablosu)."""
    z = zone_in(state)
    assert z.on_bar(anchor, anchor, ts(6)) is S.CLOSED


def test_R_ZONE_05_primed_ara_derinlik_serbest():
    """PRIMED'de 0.50'nin altına inmek zone'u öldürmez — yalnızca 0 veya 1 öldürür."""
    z = zone_in(S.PRIMED)
    for i, low in enumerate([140, 130, 120, 110, 100.1], start=4):
        z.on_bar(low + 5, low, ts(i))
    assert z.state is S.PRIMED
    assert z.on_bar(175, 165, ts(10)) is S.TOUCHED


def test_R_ZONE_05_zaman_asimi_yok():
    z = zone_in(S.PRIMED)
    for i in range(4, 504):
        z.on_bar(169, 120, ts(i))
    assert z.state is S.PRIMED


def test_R_ZONE_05_oldurme_ilerlemeye_baskin():
    """Aynı mumda hem 0.50 hem 1 görülürse kötümser davranılır: zone ölür."""
    z = zone_in(S.ACTIVE)
    assert z.on_bar(200, 145, ts(3)) is S.INVALIDATED


def test_R_ZONE_05_capaya_degmeyen_mum_oldurmez():
    z = zone_in(S.ACTIVE)
    z.on_bar(199.9, 100.1, ts(3))
    assert z.state is S.PRIMED  # 0.50 görüldü, çapalara değilmedi


# --- Kalıcılık (ARCHITECTURE.md §4.2) ---------------------------------------

def test_R_ZONE_01_sqlite_round_trip(tmp_path):
    store = ZoneStore(tmp_path / "state.db")
    z = zone_in(S.PRIMED)
    store.save(z)
    assert store.get(z.zone_id) == z


def test_R_ZONE_01_kayitli_zone_kaldigi_yerden_devam_eder(tmp_path):
    """Zone her mumda yeniden hesaplanmaz: çökme sonrası durum diskten gelir."""
    store = ZoneStore(tmp_path / "state.db")
    store.save(zone_in(S.PRIMED))
    store.close()

    z = ZoneStore(tmp_path / "state.db").open_zones()[0]
    assert z.state is S.PRIMED
    assert z.on_bar(175, 165, ts(9)) is S.TOUCHED


def test_R_ZONE_06_open_zones_terminalleri_haric_tutar(tmp_path):
    store = ZoneStore(tmp_path / "state.db")
    watched = [zone_in(S.ACTIVE), zone_in(S.PRIMED), zone_in(S.ENTERED)]
    dead = zone_in(S.TP1_HIT)
    dead.transition(S.CLOSED, ts(9))
    for z in watched + [dead]:
        store.save(z)
    assert {z.zone_id for z in store.open_zones()} == {z.zone_id for z in watched}
    assert store.open_zones(symbol="YOK/USDT") == []


# --- Entegrasyon: §0 referans örneği ----------------------------------------

NEAR = Path("data/bingx/NEAR-USDT-USDT/30m/2026-09.parquet")


@pytest.mark.skipif(not NEAR.exists(), reason="data/ gitignore'da — scripts/backfill.py ile toplanir")
def test_R_ZONE_04_near_referans_ornegi_beklenen_sirayi_uretir():
    """STRATEGY_SPEC §0 referans örneği, gerçek 30m veri üzerinde.

    0 = 2.241 (2026-09-08 13:30) · 1 = 2.649 (2026-09-09 17:00) → SHORT.
    Fiyat 1'den düştü, 0.50'ye (2.445) temas etti, 0.70'e (2.527) döndü → giriş,
    sonra 0.50'ye geri geldi → ilk TP. Veri bitene kadar 0'a da 1'e de değmedi.
    """
    df = pd.read_parquet(NEAR)
    z = Zone.create(
        symbol="NEAR/USDT:USDT", timeframe="30m",
        anchor_0_price=2.241, anchor_0_time=pd.Timestamp("2026-09-08 13:30", tz="UTC"),
        anchor_1_price=2.649, anchor_1_time=pd.Timestamp("2026-09-09 17:00", tz="UTC"),
    )
    assert z.bias == "SHORT"
    assert (round(z.level_050, 3), round(z.level_070, 3), round(z.level_079, 3)) == (2.445, 2.527, 2.563)

    # Zone yalnızca 1 çapasından sonraki mumları görür (geçmişe bakmak look-ahead olurdu).
    z.activate(z.anchor_1_time)
    history = []
    for row in df[df.ts > z.anchor_1_time].itertuples():
        before = z.state
        after = z.on_bar(row.high, row.low, row.ts)
        if after is not before:
            history.append((after, row.ts))
        if after is S.TOUCHED:
            z.enter(row.ts)  # R-ENTRY-02 (3): bantta gösterge yok, 0.70 teması geçerli giriş
            history.append((S.ENTERED, row.ts))

    assert history == [
        (S.PRIMED, pd.Timestamp("2026-09-09 21:30", tz="UTC")),
        (S.TOUCHED, pd.Timestamp("2026-09-10 03:00", tz="UTC")),
        (S.ENTERED, pd.Timestamp("2026-09-10 03:00", tz="UTC")),
        (S.TP1_HIT, pd.Timestamp("2026-09-10 06:00", tz="UTC")),
    ]
    assert z.state is S.TP1_HIT  # nihai TP (2.241) de stop (2.649) da görülmedi
