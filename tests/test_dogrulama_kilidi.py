"""Doğrulama coinleri geliştirme sırasında okunamaz/indirilemez (docs/dogrulama_coinleri_2026-10-07.md)."""
import json

import pytest

from src.data import collect


def test_liste_20_ve_kullanilanlarla_cakismaz():
    s = collect.dogrulama_sembolleri()
    assert len(s) == 20
    kullanilan = set()
    for f in ("liquidity.json", "liquidity_soguk.json"):
        p = collect.DATA_ROOT / "bingx" / f
        if p.exists():
            kullanilan |= set(json.loads(p.read_text(encoding="utf-8"))["symbols"])
    assert not s & kullanilan
    assert not any(x.startswith(("NCCO", "NCSI", "NCFX", "NCSK")) for x in s)


def test_okuma_yazma_cekim_reddedilir():
    with pytest.raises(collect.DogrulamaKilidi):
        collect.read_parquet("bingx", "BCH/USDT:USDT", "30m")
    with pytest.raises(collect.DogrulamaKilidi):
        collect.month_path("bingx", "NMR/USDT:USDT", "1m", "2026-09")
    with pytest.raises(collect.DogrulamaKilidi):
        collect.fetch_ohlcv(None, "BITLIGHT/USDT:USDT", "1m")  # ağdan önce durur
    assert collect._safe("BTC/USDT:USDT") == "BTC-USDT-USDT"


def test_liste_bozuksa_her_erisim_durur(tmp_path, monkeypatch):
    bos = tmp_path / "x.md"
    bos.write_text("liste yok", encoding="utf-8")
    monkeypatch.setattr(collect, "DOGRULAMA_LISTESI", bos)
    with pytest.raises(collect.DogrulamaKilidi):
        collect._safe("BTC/USDT:USDT")
