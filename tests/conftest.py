"""Test genelinde `ADD-REJECT-E` kapalidir ve ekleme **aciktir**.

v1 varsayilani `MAX_ADDS = 0` (ekleme kapali). `R-ADD-*` kurallari yerinde durdugu
icin testleri ekleme yolunu sinar; fixture sabiti `None` (sinirsiz) yapar. F1'in
kendi testi `max_adds=0`'i acikca verir.

---


Testlerin referans zone'u okunakli olsun diye asiridir: `0 = 100`, `1 = 200`, yani
leg fiyatin **%59'u**. Gercek piyasada leg fiyatin birkac yuzdesidir. Bu geometride
0.70 girisinin stop mesafesi `30/170 = %17,6`; `K = 1.0` ile tek islem equity'nin
%17,6'sini riske atar ve `ADD-REJECT-E`'nin her makul `L` degeri **hicbir pozisyonun
acilmasina izin vermez**.

Bu yuzden kural burada gecici olarak sifirlanir: diger kurallarin testleri kendi
konularini olcer. `ADD-REJECT-E`'nin kendi testleri (`tests/test_levers.py`) `L`
degerini **acikca** vererek kosar ve bu fixture'dan etkilenmez.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.backtest import engine


@pytest.fixture(autouse=True)
def _add_reject_e_kapali(monkeypatch):
    monkeypatch.setattr(engine, "STOP_LOSS_CAP", Decimal("0"))
    monkeypatch.setattr(engine, "MAX_ADDS", None)
