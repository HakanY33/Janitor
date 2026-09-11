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

from src.zones.model import HYSTERESIS, InvalidTransition, Zone, ZoneState as S
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
    z.activate()  # WATCH_FROM = anchor_1 (ts(1)) + 30m = ts(2)
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
    """Spec alanları, spec'teki sırayla ve en başta. Sonrası uygulama durumu."""
    spec = [
        "zone_id", "symbol", "timeframe", "bias",
        "anchor_0_price", "anchor_0_time", "anchor_1_price", "anchor_1_time",
        "level_050", "level_070", "level_079", "state",
        "created_at", "state_changed_at", "primed_at", "touch_count", "quality_score",
    ]
    names = [f.name for f in fields(Zone)]
    assert names[:len(spec)] == spec
    assert names[len(spec):] == [
        "pivot_confirmed_at", "hysteresis", "in_band", "kill_wins", "skipped_progress",
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


def test_R_ZONE_01_touch_count_bant_disindan_her_girisi_sayar():
    """Sayılan olay: bant dışından banda giriş. Bant 0.70–0.79 = 170–179.

    Histerezis payı: 0.25 * 9 = 2.25 → yeni temas için 167.75'in altına inilmeli.
    """
    z = zone_in(S.PRIMED)
    assert z.touch_count == 0
    z.on_bar(175, 165, ts(4))    # bant dışından girildi → 1. temas
    assert z.touch_count == 1
    z.on_bar(167, 160, ts(5))    # bandı belirgin şekilde terk etti
    z.on_bar(172, 171, ts(6))    # geri gelindi → 2. temas
    assert z.touch_count == 2


def test_R_ZONE_01_touch_count_primed_oncesi_sayilmaz():
    """Yalnızca PRIMED'den itibaren sayılır (R-ZONE-01).

    ACTIVE durumunda fiyat 1'den 0.50'ye inerken banttan zorunlu olarak geçer; bu temas
    her zone'da yapısı gereği vardır, bilgi taşımaz.
    """
    z = zone_in(S.ACTIVE)
    z.on_bar(178, 171, ts(3))  # bantta, ama zone henüz silahlı değil
    z.on_bar(167, 160, ts(4))  # banttan belirgin çıkış
    z.on_bar(178, 171, ts(5))  # tekrar bantta
    assert (z.state, z.touch_count) == (S.ACTIVE, 0)
    z.on_bar(155, 145, ts(6))  # 0.50 teması → PRIMED
    z.on_bar(175, 165, ts(7))  # ilk anlamlı temas
    assert z.touch_count == 1


def test_R_ZONE_01_primeden_bant_icinde_cikan_zone_ayni_temasi_tekrar_saymaz():
    """0.50 ve bant aynı mumda görülürse zone PRIMED olur ama o temas sayılmaz.

    Bant içinde kalmaya devam etmek de yeni bir olay değildir — sayılan olay, girişin
    kendisidir (R-ZONE-01).
    """
    z = zone_in(S.ACTIVE)
    assert z.on_bar(175, 145, ts(3)) is S.PRIMED  # geçişteki zorunlu bant teması
    z.on_bar(178, 171, ts(4))                     # hâlâ bant içinde
    assert z.touch_count == 0


# --- R-ZONE-01 · histerezis --------------------------------------------------

def test_R_ZONE_01_histerezis_sig_cikis_yeni_temas_saymaz():
    """Bant sınırındaki titreşim sayacı şişirmez: çıkış payın altında kalırsa temas yok."""
    z = zone_in(S.PRIMED)
    z.on_bar(175, 171, ts(4))
    assert z.touch_count == 1
    for i in range(5, 15):
        z.on_bar(169.9, 168, ts(i))  # bandın hemen altı — pay (2.25) aşılmadı
        z.on_bar(175, 171, ts(i))    # geri bantta
    assert z.touch_count == 1


def test_R_ZONE_01_histerezis_orani_yapilandirilabilir():
    """Aynı mum dizisi, iki farklı oran: 0 = kapalı, varsayılan = 0.25."""
    def temas(hysteresis: float) -> int:
        z = short_zone(hysteresis=hysteresis)
        z.activate()
        z.on_bar(155, 145, ts(3))     # PRIMED
        for i in range(4, 10):
            z.on_bar(175, 171, ts(i))    # bantta
            z.on_bar(169.9, 168, ts(i))  # bandın hemen altı: sığ çıkış
        return z.touch_count

    assert temas(0.0) == 6      # histerezissiz her dönüş yeni temas
    assert temas(HYSTERESIS) == 1
    assert short_zone().hysteresis == HYSTERESIS


def test_R_ZONE_01_touch_count_bant_icindeki_ardisik_mumlar_artirmaz():
    """Sayılan mum değil, olay: bant içinde geçen mumlar sayacı artırmaz (R-ZONE-01)."""
    z = zone_in(S.PRIMED)
    z.on_bar(175, 165, ts(4))  # banda giriş
    for i in range(5, 15):
        z.on_bar(178, 171, ts(i))  # bant içinde kalındı
    assert z.touch_count == 1


def test_R_ZONE_01_touch_count_bandin_ustunden_gecis_de_temastir():
    """0.79'un üstüne taşan mum bandı kesiyorsa temastır — 0.70'e değmesi şart değil."""
    z = zone_in(S.PRIMED)
    z.on_bar(185, 175, ts(4))  # bant içinde başlayıp üstüne taştı
    assert z.touch_count == 1


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
    z.activate()
    assert z.state is S.ACTIVE and z.state_changed_at == ts(2)  # = WATCH_FROM


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


@pytest.mark.parametrize("state", [S.ENTERED, S.TP1_HIT])
def test_R_ZONE_04_pozisyon_acikken_invalidated_gecersiz(state):
    """R-ZONE-04: INVALIDATED yalnızca pozisyon açılmadan önce geçerlidir.

    ENTERED/TP1_HIT durumunda çapa teması geçersizlik değil, işlem sonucudur → CLOSED.
    """
    z = zone_in(state)
    with pytest.raises(InvalidTransition):
        z.transition(S.INVALIDATED, ts(6))
    assert z.state is state  # başarısız geçiş durumu bozmaz


@pytest.mark.parametrize("state", [S.CLOSED, S.INVALIDATED])
def test_R_ZONE_04_terminal_durumdan_cikis_yok(state):
    z = zone_in(S.TP1_HIT if state is S.CLOSED else S.TOUCHED)
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


# --- R-ZONE-09 · WATCH_FROM --------------------------------------------------

def test_R_ZONE_09_watch_from_anchor_1_htf_mum_kapanisi():
    """Pivot teyidi verilmezse taban tek başına iş görür: anchor_1 mumunun kapanışı."""
    z = short_zone()  # anchor_1 = ts(1), timeframe = 30m
    assert z.watch_from == ts(1) + pd.Timedelta("30m") == ts(2)
    assert z.pivot_confirmed_at is None


def test_R_ZONE_09_watch_from_gec_olan_terimi_secer():
    """WATCH_FROM = max(HTF mum kapanışı, pivot teyit zamanı)."""
    gec = short_zone(pivot_confirmed_at=ts(5))
    assert gec.watch_from == ts(5)  # pivot teyidi HTF kapanışından sonra
    erken = short_zone(pivot_confirmed_at=T0)
    assert erken.watch_from == ts(2)  # taban kazanır


def test_R_ZONE_09_watch_from_oncesi_mum_reddedilir():
    """Zone kendi geçmişiyle beslenmez: erken mum look-ahead'dir, sessizce yutulmaz."""
    z = zone_in(S.ACTIVE)
    with pytest.raises(ValueError, match="look-ahead"):
        z.on_bar(155, 145, ts(1))
    assert z.state is S.ACTIVE


def test_R_ZONE_09_pivot_teyidi_izlemeyi_geciktirir():
    """Pivot teyidi geç ise arada kalan mumlar zone'a hiç gösterilmez."""
    z = short_zone(pivot_confirmed_at=ts(5))
    z.activate()
    assert z.state_changed_at == ts(5)
    with pytest.raises(ValueError, match="look-ahead"):
        z.on_bar(200, 190, ts(4))  # teyitten önceki çapa teması zone'u öldürmemeli
    assert z.on_bar(155, 145, ts(5)) is S.PRIMED


# --- R-ZONE-09 · mum içi çakışma sayaçları ----------------------------------

def test_R_ZONE_09_oldurme_kazandi_sayilir():
    """Aynı mumda hem ilerleme hem çapa teması: öldürme kazanır, sayaç artar."""
    z = zone_in(S.ACTIVE)
    assert z.on_bar(200, 145, ts(3)) is S.INVALIDATED  # 0.50 de 1 de bu mumda
    assert z.kill_wins == 1


def test_R_ZONE_09_ilerlemesiz_capa_temasi_sayaci_artirmaz():
    z = zone_in(S.ACTIVE)
    z.on_bar(200, 190, ts(3))  # yalnızca çapa; atlanan ilerleme yok
    assert z.kill_wins == 0


def test_R_ZONE_09_oldurme_kazandi_pozisyon_acikken_de_sayilir():
    z = zone_in(S.ENTERED)
    assert z.on_bar(200, 145, ts(5)) is S.CLOSED  # ilk TP mi nihai stop mu belli değil
    assert z.kill_wins == 1


def test_R_ZONE_09_atlanan_ikinci_ilerleme_sayilir():
    """0.50 ve 0.70 aynı mumda: yalnızca PRIMED uygulanır, atlanan geçiş sayılır."""
    z = zone_in(S.ACTIVE)
    assert z.on_bar(175, 145, ts(3)) is S.PRIMED
    assert z.skipped_progress == 1
    assert z.kill_wins == 0


def test_R_ZONE_09_tek_ilerlemede_atlama_sayilmaz():
    z = zone_in(S.ACTIVE)
    z.on_bar(155, 145, ts(3))  # yalnızca 0.50
    assert z.skipped_progress == 0


def test_R_ZONE_09_sayaclar_zone_basina_ve_toplamda(tmp_path):
    """Sayaçlar zone alanlarında tutulur, diske yazılır ve toplamı sorgulanabilir."""
    store = ZoneStore(tmp_path / "state.db")
    atlayan = zone_in(S.ACTIVE)
    atlayan.on_bar(175, 145, ts(3))  # atlanan ilerleme
    olen = zone_in(S.ACTIVE)
    olen.on_bar(200, 145, ts(3))  # öldürme kazandı
    for z in (atlayan, olen):
        store.save(z)

    assert (atlayan.kill_wins, atlayan.skipped_progress) == (0, 1)
    assert (olen.kill_wins, olen.skipped_progress) == (1, 0)
    assert store.get(atlayan.zone_id) == atlayan  # sayaçlar round-trip'te korunur
    assert store.conflict_totals() == {"kill_wins": 1, "skipped_progress": 1}


def test_R_ZONE_09_sayac_toplami_bos_tabloda_sifir(tmp_path):
    assert ZoneStore(tmp_path / "state.db").conflict_totals() == {
        "kill_wins": 0, "skipped_progress": 0,
    }


# --- Kalıcılık (ARCHITECTURE.md §4.2) ---------------------------------------

def test_R_ZONE_01_sqlite_round_trip(tmp_path):
    store = ZoneStore(tmp_path / "state.db")
    z = zone_in(S.PRIMED)
    z.pivot_confirmed_at, z.hysteresis = ts(2), 0.4  # opsiyonel alanlar da dönmeli
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

NEAR_30M = Path("data/bingx/NEAR-USDT-USDT/30m/2026-09.parquet")
NEAR_1M = Path("data/bingx/NEAR-USDT-USDT/1m/2026-09.parquet")
NO_DATA = "data/ gitignore'da — scripts/backfill.py ile toplanir"

# §0 referans örneği: 0 = 2.241 (2026-09-08 13:30) · 1 = 2.649 (2026-09-09 17:00) → SHORT.
ANCHOR_0 = (2.241, pd.Timestamp("2026-09-08 13:30", tz="UTC"))
ANCHOR_1 = (2.649, pd.Timestamp("2026-09-09 17:00", tz="UTC"))
# İzleme WATCH_FROM'dan başlar (R-ZONE-09) — zone kendisi hesaplar. Pivot teyit zamanı
# yok: leg tespiti (R-ZONE-02) elle yapıldığı sürece taban terim, yani anchor_1'in 30m
# mumunun kapanışı iş görür.


def run_near(path: Path, hysteresis: float = HYSTERESIS) -> tuple[Zone, list[tuple[S, pd.Timestamp]]]:
    """Referans zone'u verilen mum dosyasıyla besler, durum geçişi geçmişini döner."""
    z = Zone.create(
        symbol="NEAR/USDT:USDT", timeframe="30m",  # geometri 30m'den (R-ZONE-09)
        anchor_0_price=ANCHOR_0[0], anchor_0_time=ANCHOR_0[1],
        anchor_1_price=ANCHOR_1[0], anchor_1_time=ANCHOR_1[1],
        hysteresis=hysteresis,
    )
    z.activate()
    watch_from = z.watch_from
    history = []
    for row in pd.read_parquet(path).query("ts >= @watch_from").itertuples():
        before = z.state
        after = z.on_bar(row.high, row.low, row.ts)
        if after is not before:
            history.append((after, row.ts))
        if after is S.TOUCHED:
            z.enter(row.ts)  # R-ENTRY-02 (3): bantta gösterge yok, 0.70 teması geçerli giriş
            history.append((S.ENTERED, row.ts))
    return z, history


@pytest.mark.skipif(not NEAR_30M.exists(), reason=NO_DATA)
def test_R_ZONE_04_near_referans_ornegi_beklenen_sirayi_uretir():
    """STRATEGY_SPEC §0 referans örneği, gerçek 30m veri üzerinde.

    Fiyat 1'den düştü, 0.50'ye (2.445) temas etti, 0.70'e (2.527) döndü → giriş,
    sonra 0.50'ye geri geldi → ilk TP. Veri bitene kadar 0'a da 1'e de değmedi.
    """
    z, history = run_near(NEAR_30M)
    assert z.watch_from == ANCHOR_1[1] + pd.Timedelta("30m")  # pivot teyidi yok → taban
    assert z.bias == "SHORT"
    assert (round(z.level_050, 3), round(z.level_070, 3), round(z.level_079, 3)) == (2.445, 2.527, 2.563)
    assert history == [
        (S.PRIMED, pd.Timestamp("2026-09-09 21:30", tz="UTC")),
        (S.TOUCHED, pd.Timestamp("2026-09-10 03:00", tz="UTC")),
        (S.ENTERED, pd.Timestamp("2026-09-10 03:00", tz="UTC")),
        (S.TP1_HIT, pd.Timestamp("2026-09-10 06:00", tz="UTC")),
    ]
    assert z.state is S.TP1_HIT  # nihai TP (2.241) de stop (2.649) da görülmedi


@pytest.mark.skipif(not (NEAR_1M.exists() and NEAR_30M.exists()), reason=NO_DATA)
def test_R_ZONE_09_near_1m_beslemesi_30m_ile_ayni_siralamayi_uretir(capsys):
    """R-ZONE-09 · aynı zone, bir kez 30m bir kez 1m mumlarla beslenir.

    Beklenen: durum *sırası* aynı, zamanlar farklı. 30m damgası mumun **açılışıdır**;
    o mum 30 dakika sonra kapanır, yani 30m beslemeli bir makine olayı ancak kapanışta
    öğrenebilir. Gerçek gecikme bu yüzden `30m mum kapanışı − 1m olay zamanı`. Fark
    raporlanır (`pytest -s`), yön ise doğrulanır: 1m hiçbir olayı geç görmez.

    Ayrıca R-ZONE-01 histerezisinin 1m'deki etkisi ölçülür: aynı zone histerezissiz ve
    varsayılan oranla beslenir, iki `touch_count` yan yana raporlanır.
    """
    z30, h30 = run_near(NEAR_30M)
    z1, h1 = run_near(NEAR_1M)
    z1_ham, _ = run_near(NEAR_1M, hysteresis=0.0)

    assert z1.timeframe == "30m"  # geometrinin TF'si; beslenen mum onu değiştirmez
    assert [state for state, _ in h1] == [state for state, _ in h30]

    lines = [f"{'durum':<8} {'30m mum':<26} {'30m kapanış':<26} {'1m':<26} kazanç"]
    for (state, t30), (_, t1) in zip(h30, h1):
        close30 = t30 + pd.Timedelta("30m")
        lines.append(f"{state.value:<8} {t30!s:<26} {close30!s:<26} {t1!s:<26} {close30 - t1}")
        assert t1 <= close30, f"{state.value}: 1m olayı 30m mumunun kapanışından geç"
    assert z1.touch_count <= z1_ham.touch_count  # histerezis yalnızca temas eler
    lines.append(
        f"touch_count: 30m={z30.touch_count}  "
        f"1m histerezissiz={z1_ham.touch_count}  1m hist={HYSTERESIS}={z1.touch_count}"
    )
    lines.append(
        f"mum içi çakışma: 30m kill={z30.kill_wins}/skip={z30.skipped_progress} "
        f"1m kill={z1.kill_wins}/skip={z1.skipped_progress}"
    )
    with capsys.disabled():
        print()
        for line in lines:
            print(line)
