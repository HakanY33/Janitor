"""R-KILL-01 toparlanması ve REST üstel beklemesi (`scripts/paper.py`, spec §6). Ağ yok."""
from types import SimpleNamespace

import numpy as np
import pytest

import scripts.paper as paper
from scripts.paper import REST_BEKLE, TEMIZ_DAKIKA, Dongu

T = np.datetime64("2026-10-01T00:00")


def dongu(kill=None):
    olay = []
    core = SimpleNamespace(semboller=["X"], bt=SimpleNamespace(kill=kill))
    return Dongu(core, None, None, olay.append, None), olay


def test_R_KILL_01_resumes_after_clean_minutes():
    d, olay = dongu()
    d.kill("REST: NetworkError")
    for i in range(TEMIZ_DAKIKA - 1):
        d.izle(T + i, True)
    assert d.core.bt.kill is not None
    d.izle(T + TEMIZ_DAKIKA, True)
    assert d.core.bt.kill is None
    assert [o["event"] for o in olay] == ["KILL", "RESUME"]


def test_R_KILL_01_dirty_minute_resets_counter():
    d, _ = dongu()
    d.kill("ws kopuk")
    for i in range(TEMIZ_DAKIKA - 1):
        d.izle(T + i, True)
    d.izle(T + 20, False)
    for i in range(TEMIZ_DAKIKA - 1):
        d.izle(T + 30 + i, True)
    assert d.core.bt.kill is not None


def test_R_KILL_01_new_kill_during_recovery_resets_counter():
    d, _ = dongu()
    d.kill("REST")
    for i in range(TEMIZ_DAKIKA - 1):
        d.izle(T + i, True)
    d.kill("REST tekrar")
    d.izle(T + 20, True)
    assert d.core.bt.kill is not None


@pytest.mark.parametrize("kill", ["R-KILL-02: teyitsiz emir", "R-KILL-03: tutarsızlık"])
def test_R_KILL_02_03_never_auto_resume(kill):
    d, olay = dongu(kill)
    for i in range(3 * TEMIZ_DAKIKA):
        d.izle(T + i, True)
    assert d.core.bt.kill == kill and not olay


def test_R_KILL_01_unexpected_error_needs_human():
    d, _ = dongu()
    d.kill("beklenmeyen hata", toparlanir=False)
    for i in range(3 * TEMIZ_DAKIKA):
        d.izle(T + i, True)
    assert d.core.bt.kill is not None


def test_R_KILL_01_rest_backoff_60s(monkeypatch):
    uyku = []
    monkeypatch.setattr(paper.time, "sleep", uyku.append)
    hata = iter([True] * len(REST_BEKLE))

    class Ex:
        def fetch_ohlcv(self, *a, **k):
            if next(hata, False):
                raise ConnectionError
            return [[1, 1, 1, 1, 1, 1]]

    assert paper.rest(Ex(), "X", "1m", T) == [[1, 1, 1, 1, 1, 1]]
    assert uyku == list(REST_BEKLE) and sum(uyku) == 60

    class Olu:
        def fetch_ohlcv(self, *a, **k):
            raise ConnectionError

    with pytest.raises(ConnectionError):
        paper.rest(Olu(), "X", "1m", T)
