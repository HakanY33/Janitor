"""Etiketleme v3 grafiği karar anında biter (CLAUDE.md #3)."""
import pandas as pd

from scripts.inceleme_v3 import kapanmis


def test_v3_grafik_yalnizca_kapanmis_mumlari_gosterir():
    ts = pd.date_range("2026-01-01", periods=1000, freq="30min", tz="UTC")
    d30 = pd.DataFrame({"ts": ts, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5})
    karar = pd.Timestamp("2026-01-15 10:24", tz="UTC")  # 10:00 mumu ve 08:00 4h mumu açık
    h4, m30 = kapanmis(d30, karar)
    assert len(m30) == 300 and m30[-1][0] == pd.Timestamp("2026-01-15 09:30", tz="UTC").timestamp()
    assert h4[-1][0] == pd.Timestamp("2026-01-15 04:00", tz="UTC").timestamp()
    assert h4[0][0] >= (karar - pd.Timedelta("14D")).timestamp()


def test_v4_ob_listesi_karar_aninda_bilineni_gosterir():
    """v4 OB kutuları: yalnızca karar anında kapanmış mumlar (CLAUDE.md #3, OPEN-64)."""
    from scripts.inceleme_v3 import ob_listesi

    ts = pd.date_range("2026-01-01", periods=8, freq="30min", tz="UTC")
    # 0–1 düz · 2: düşüş mumu (1. mum) · 3: yükseliş · 4: 1. mumdan ayrık (3. mum) · 5: uzak ·
    # 6: 1. mumun gövdesine döner (mitigasyon) · 7: yeni bir talep için 3. mum adayı
    o = [100, 100, 100, 99.6, 101, 103, 103, 100]
    h = [101, 101, 100.5, 101, 103, 104, 103.5, 101]
    lo = [99, 99, 99.3, 99.5, 100.8, 102, 99.8, 99]
    c = [100.5, 100.5, 99.6, 100.9, 102.5, 103.5, 100, 100.5]
    d30 = pd.DataFrame({"ts": ts, "open": o, "high": h, "low": lo, "close": c, "volume": 1.0})
    once = ob_listesi(d30, "X", ts[6])  # 6. mum henüz açık: temas bilinmiyor
    assert [(x["yon"], x["alt"], x["ust"], x["mit"]) for x in once] == [("talep", 99.6, 100, None)]
    sonra = ob_listesi(d30, "X", ts[7])
    assert sonra[0]["mit"] == int(ts[7].timestamp())  # 6. mumun kapanışı
    assert ob_listesi(d30, "X", ts[4]) == []  # 3. mum (4) kapanmadan OB yok
