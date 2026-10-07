"""Strateji inceleme seçimi: en kötü 10 OTE + kalanlardan rastgele 10, ayrık, OB girişi yok."""
from decimal import Decimal
from types import SimpleNamespace as NS

from scripts.inceleme_strateji import sec


def test_sec_en_kotu_10_ve_rastgele_10():
    T = [NS(giris="OTE", pnl=Decimal(i - 50), entry_ts=i) for i in range(100)]
    T += [NS(giris="OB", pnl=Decimal(-999), entry_ts=0)]
    s = sec(T)
    assert len(s) == 20 and all(t.giris == "OTE" for _, t in s)
    assert sorted(t.pnl for g, t in s if g == "kotu") == [Decimal(i - 50) for i in range(10)]
    assert all(t.pnl >= -40 for g, t in s if g == "rastgele")
    assert len({id(t) for _, t in s}) == 20
    assert [t.entry_ts for _, t in sec(T)] == [t.entry_ts for _, t in s]  # tohum sabit
