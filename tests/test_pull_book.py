"""`scripts/pull_book.py` — ag yok; indirme karari ve guvenli yazma."""
from __future__ import annotations

import hashlib
import io

import pandas as pd
import pytest

from scripts.pull_book import install, parse_sums, plan


def parquet(minutes: list[int]) -> bytes:
    b = io.BytesIO()
    pd.DataFrame({"ts": pd.to_datetime(minutes, unit="m", utc=True), "bid": 1.0}).to_parquet(b)
    return b.getvalue()


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_plan_ayni_ozeti_atlar_farkliyi_ve_eksigi_indirir(tmp_path):
    ayni, eski = parquet([1]), parquet([1])
    (tmp_path / "a.parquet").write_bytes(ayni)
    (tmp_path / "b.parquet").write_bytes(eski)
    remote = parse_sums(f"{h(ayni)}  a.parquet\n{h(parquet([1, 2]))}  b.parquet\n"
                        f"{h(ayni)} *c.parquet\n")
    assert plan(remote, tmp_path) == ["b.parquet", "c.parquet"]


def test_install_ozet_tutmazsa_yazmaz(tmp_path):
    with pytest.raises(ValueError):
        install(parquet([1]), tmp_path / "x.parquet", "0" * 64)
    assert not (tmp_path / "x.parquet").exists()


def test_install_ust_kumeyi_yazar(tmp_path):
    d = tmp_path / "x.parquet"
    d.write_bytes(parquet([1]))
    yeni = parquet([1, 2])
    install(yeni, d, h(yeni))
    assert d.read_bytes() == yeni


def test_install_yerel_dakikayi_kaybettirmez(tmp_path):
    d = tmp_path / "x.parquet"
    d.write_bytes(parquet([1, 5]))
    yeni = parquet([1, 2])
    with pytest.raises(RuntimeError):
        install(yeni, d, h(yeni))
    assert len(pd.read_parquet(d)) == 2  # dokunulmadi
