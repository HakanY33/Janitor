"""v4 OB aday kuralları (`scripts/ob_adaylar.py`) — sentetik."""
import pandas as pd

from scripts.ob_adaylar import ardisik, bos
from src.features.fvg import BEARISH, BULLISH
from src.features.ob import OrderBlock
from src.features.structure import HIGH, Swing

T = pd.date_range("2026-01-01", periods=12, freq="30min", tz="UTC")


def ob(i, yon=BULLISH, top=100.5, bottom=99.3):
    return OrderBlock(f"o{i}", "X", "30m", yon, top, bottom, T[i], T[i + 2])


def test_ardisik_seri_varyantlari():
    obs = [ob(0), ob(2), ob(4, BEARISH), ob(6)]  # seri: [o0, o2] · [o4] · [o6]
    assert ardisik(obs, "A0") == {"o0", "o2", "o4", "o6"}
    assert ardisik(obs, "A1") == {"o4", "o6"}
    assert ardisik(obs, "A2") == {"o2", "o4", "o6"}
    assert ardisik(obs, "A3") == {"o0", "o4", "o6"}


def _df(kapanis, low=None):
    low = low or [c - 0.2 for c in kapanis]
    return pd.DataFrame({"ts": T[:len(kapanis)], "open": kapanis, "high": [c + 0.2 for c in kapanis],
                         "low": low, "close": kapanis})


def test_bos_kapanisla_kirilma_ve_bolgeye_donus():
    tepe = [Swing("s", "X", "30m", HIGH, 103.0, T[0] - pd.Timedelta("1h"), T[0])]
    # 1. mum T[1], 3. mum T[3]; T[4] kapanış 103.5 > 103 → kırılma
    assert bos(ob(1), _df([100, 100, 101, 102, 103.5]), tepe)
    # yalnızca fitil (high 103.1, kapanış 102.9): kırılma yok
    assert not bos(ob(1), _df([100, 100, 101, 102, 102.9]), tepe)
    # T[4] bölgeye döner (low 100.4 ≤ 100.5), T[5] kırar → hareket bitmişti
    assert not bos(ob(1), _df([100, 100, 101, 102, 101, 104], low=[0, 0, 0, 0, 100.4, 103.8]), tepe)
    assert not bos(ob(1), _df([100, 100, 101, 102, 103.5]), [])  # karşı swing yok
