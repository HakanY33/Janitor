"""`scripts/bootstrap_fark.py` — eşleşik bootstrap, sentetik."""
from scripts.bootstrap_fark import bootstrap


def test_esit_kosularda_fark_sifir_ve_ortak_gurultu_duser():
    a = {("X", f"2026-{m:02d}"): v for m, v in enumerate([5, -7, 3, -1, 9, -4], 1)}
    r = bootstrap(a, dict(a), n=500)
    assert r["fark"] == 0 and r["fark_ara"] == (0, 0)  # eşleşik: aynı bloklar
    assert r["a_ara"][0] < 0 < r["a_ara"][1]


def test_tutarli_kayma_sifiri_kapsamaz_eksik_blok_sifirdir():
    a = {("X", f"m{i}"): float(i % 5 - 2) for i in range(40)}
    b = {k: v + 1 for k, v in a.items()}
    del b[("X", "m0")]
    a[("Y", "m0")] = 0.0
    r = bootstrap(a, b, n=500)
    assert r["fark_ara"][0] > 0 and r["blok"] == 41
