"""v4 puanlaması (`scripts/v4_puan.py`) — sentetik etiketler ve sentetik fiyat, ağsız, `data/` yok.

Gerçek v4 etiketlerine bakılmaz: doğrulama bir kez, etiketler gelince yapılır.
"""
import numpy as np
import pandas as pd
import pytest

from scripts.swing_secim import ADAYLAR, ilk_050, z_tip0, zonlar
from scripts.v4_puan import ADAY, ESIK, ESLESTIRME, ob_puan, ote_puan

SYM = "SENT/USDT:USDT"


def _veri(n=3000, tohum=11):
    """30m rastgele yürüyüş + her 30m mumu 30 özdeş 1m mum olarak (ilk_050 ve alarm için yeter)."""
    r = np.random.default_rng(tohum)
    c = 100 + np.cumsum(r.normal(0, 1, n))
    o = np.r_[c[0], c[:-1]]
    ts = pd.date_range("2025-09-01", periods=n, freq="30min", tz="UTC")
    d30 = pd.DataFrame({"ts": ts, "open": o, "high": np.maximum(o, c) + r.uniform(0.1, 1, n),
                        "low": np.minimum(o, c) - r.uniform(0.1, 1, n), "close": c, "volume": 1.0})
    d1 = d30.loc[d30.index.repeat(30)].reset_index(drop=True)
    d1["ts"] = pd.date_range(ts[0], periods=len(d1), freq="1min", tz="UTC")
    return {SYM: (d30, d1)}


def _capa(t, tip, fiyat):
    return {"ts": int(pd.Timestamp(t).timestamp()), "tip": tip, "fiyat": fiyat}


def _etiket(i, z, kaydir=pd.Timedelta(0)):
    t0 = z_tip0(z)
    return {"id": f"r{i:02d}", "tur": "rastgele", "symbol": SYM, "secim": "farkli",
            "karar_ts": (z.known_at + pd.Timedelta("1h")).strftime("%Y-%m-%d %H:%M"),
            "capa_0": _capa(z.anchor_0_time + kaydir, t0, z.anchor_0_price),
            "capa_1": _capa(z.anchor_1_time, "dip" if t0 == "tepe" else "tepe", z.anchor_1_price)}


@pytest.fixture(scope="module")
def durum():
    V = _veri()
    d30, d1 = V[SYM]
    zs = zonlar(d30, SYM, ADAYLAR[ADAY](d30, SYM), ESLESTIRME)
    # zamanında bilinen zone'lar: known_at ≤ etiketli leg'de ilk 0.50 teması
    from scripts.swing_secim import Capa
    iyi = []
    for z in zs:
        t0 = z_tip0(z)
        c0 = Capa(z.anchor_0_time, t0, z.anchor_0_price)
        c1 = Capa(z.anchor_1_time, "dip" if t0 == "tepe" else "tepe", z.anchor_1_price)
        son = ilk_050(d1, c0, c1)
        if son is not None and z.known_at <= son:
            iyi.append(z)
    assert len(iyi) >= 6, "sentetik seri yeterli zone üretmiyor — test boş"
    return V, iyi


def test_v4_motorun_kendi_zonelari_etiketse_gecer(durum):
    V, iyi = durum
    E = [_etiket(i, z) for i, z in enumerate(iyi[:6], 1)]
    a = ote_puan(E, V)
    assert (a["cift"], a["n"], a["karar"]) == (6, 6, "GEÇTİ")


def test_v4_yanlis_0_ile_kalir(durum):
    """0 çapası ±2 mumdan uzağa kayarsa eşleşme yok → oran eşiğin altı → KALDI."""
    V, iyi = durum
    E = [_etiket(i, z, kaydir=pd.Timedelta("-6h")) for i, z in enumerate(iyi[:6], 1)]
    a = ote_puan(E, V)
    assert a["cift"] == 0 and a["karar"] == "KALDI"


def test_v4_esik_sinirda_gecer(durum):
    """Eşik dahil: oran == %28 → GEÇTİ. 25 setup'ta 7 isabet = %28."""
    V, iyi = durum
    dogru = [_etiket(i, iyi[i % len(iyi)]) for i in range(7)]
    yanlis = [_etiket(10 + i, iyi[i % len(iyi)], kaydir=pd.Timedelta("-6h")) for i in range(18)]
    a = ote_puan(dogru + yanlis, V)
    assert a["oran"] == pytest.approx(7 / 25) and ESIK == 0.28 and a["karar"] == "GEÇTİ"


def test_v4_etiketsiz_an_varsa_karar_yok(durum):
    V, iyi = durum
    E = [_etiket(1, iyi[0]), {**_etiket(2, iyi[1]), "secim": None}]
    with pytest.raises(ValueError, match="eksik"):
        ote_puan(E, V)


def test_v4_setup_yok_paydaya_girmez(durum):
    V, iyi = durum
    E = [_etiket(1, iyi[0]), {**_etiket(2, iyi[1]), "secim": "setup_yok"}]
    a = ote_puan(E, V)
    assert (a["n"], a["n_yok"], a["cift"]) == (1, 1, 1)


# --- (b) OB --------------------------------------------------------------------

def _ob(i, yon, t1, mit=None, ust=101.0, alt=100.0):
    return {"id": f"OB{i}", "ob_id": f"x{i}", "yon": yon, "t1": t1, "t3": t1 + 3600,
            "ust": ust, "alt": alt, "mit": mit}


def test_v4_ob_dogruluk_kacirilan_ve_gruplar():
    t = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp())
    E = [
        {"id": "r01", "symbol": SYM, "karar_ts": "2026-01-02 00:00", "ob_acildi": "x",
         "ob_liste": [_ob(1, "talep", t), _ob(2, "arz", t + 1800, mit=t + 9000), _ob(3, "talep", t + 3600)],
         "ob": {"OB1": "dogru", "OB2": "yanlis"},  # OB3 etiketsiz
         "ob_eksik": [{"ts": t + 1800, "yon": "arz"}, {"ts": t + 99000, "yon": "talep"}]},
        {"id": "r02", "symbol": SYM, "karar_ts": "2026-01-02 00:00", "ob_acildi": "x",
         "ob_liste": [_ob(1, "arz", t, mit=t + 5400)], "ob": {"OB1": "yanlis"}, "ob_eksik": []},
        {"id": "r03", "symbol": SYM, "karar_ts": "2026-01-02 00:00", "ob_acildi": None,
         "ob_liste": [_ob(1, "talep", t)], "ob": {"OB1": "dogru"}, "ob_eksik": []},  # açılmadı → sayılmaz
    ]
    b = ob_puan(E)
    assert (b["ob"], b["dogru"], b["yanlis"], b["etiketsiz"]) == (4, 1, 2, 1)
    assert b["dogruluk"] == pytest.approx(1 / 3)
    assert (b["kacirilan"], b["kacirilan_motorda_vardi"]) == (2, 1)
    assert b["acilmadi"] == ["r03"]
    y = b["gruplar"]["yanlis"]
    assert (y["n"], y["talep"], y["mitige"]) == (2, 0, 2)
    # OB2: 3. mum t+5400, mitige eden mum t+7200'de açılır → arada 1 mum · r02 OB1: 0 mum
    assert y["mitigasyona_mum"] == pytest.approx(0.5)
    assert b["gruplar"]["dogru"]["genislik_bps"] == pytest.approx(100.0)


def test_v4_ob_mum_ozellikleri_ve_rapor(durum, tmp_path):
    """OB'ler sayfadaki gibi `ob_listesi`'nden; boşluk tanım gereği > 0, rapor iki bölümü yazar."""
    from scripts.inceleme_v3 import ob_listesi
    from scripts.v4_puan import rapor

    V, iyi = durum
    d30 = V[SYM][0]
    karar = d30.ts.iloc[2500]
    obs = ob_listesi(d30, SYM, karar)
    assert obs, "sentetik pencerede OB yok — test boş"
    r = {**_etiket(1, iyi[0]), "karar_ts": karar.strftime("%Y-%m-%d %H:%M"), "ob_acildi": "x",
         "ob_liste": obs, "ob": {o["id"]: ("dogru" if k % 2 else "yanlis") for k, o in enumerate(obs)},
         "ob_eksik": []}
    b = ob_puan([r], V)
    for g in b["gruplar"].values():
        if g["n"]:
            assert g["bosluk_ref"] > 0 and g["govde2_ref"] is not None
    a = ote_puan([_etiket(1, iyi[0])], V)
    md = rapor(a, b, tmp_path / "etiketler.json")
    assert "GEÇTİ" in md and "(b) OB etiketleri" in md and f"{len(obs)} OB" in md
