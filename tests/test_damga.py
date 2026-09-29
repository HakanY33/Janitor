"""`scripts/damga.py` kriter 3 (spec §8, `OPEN-40`) hesabı."""
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd

from scripts.damga import kriter3


def t(ay_gun: str, pnl: str):
    ts = pd.Timestamp(ay_gun, tz="UTC")
    return SimpleNamespace(exit_ts=ts, entry_ts=ts, pnl=Decimal(pnl))


BAS, SON = pd.Timestamp("2026-01-20", tz="UTC"), pd.Timestamp("2026-05-10", tz="UTC")


def test_kriter3_kismi_aylar_sayilmaz():
    """Ocak'ın 11 günü (< 15,5) ve Mayıs'ın 9 günü dilimde: ikisi de sayılmaz."""
    k = kriter3([t("2026-01-25", "999"), t("2026-02-10", "10")], BAS, SON)
    assert list(k["aylar"]) == ["2026-02", "2026-03", "2026-04"]
    assert k["aylar"]["2026-03"] == 0  # işlemsiz ay sayılır, pozitif değildir


def test_kriter3_A1_A2():
    k = kriter3([t("2026-02-10", "30"), t("2026-03-10", "30"), t("2026-04-10", "-5")], BAS, SON)
    assert (k["pozitif"], k["n"], k["A1"]) == (2, 3, True)  # 2/3 ≥ %60
    assert k["A2"] is False  # 30 > 0,40 × 55
    k = kriter3([t("2026-02-10", "10"), t("2026-03-10", "10"), t("2026-04-10", "10")], BAS, SON)
    assert k["A2"] is True
    k = kriter3([t("2026-02-10", "-10")], BAS, SON)
    assert k["A2"] is False  # toplam ≤ 0: A2 geçilemez
