"""`load_symbol` disk onbellegi — anahtarin **kapsami** ve **dustugu yer**.

Bayat onbellek sessiz hata uretir: kod degisir, sonuc degismez, kimse fark etmez.
Bu yuzden burada onbellegin hizlandirdigi degil, dogru yerde dustugu test edilir.

Iki ayri soru var ve ikisi de onemli:

1. **Kapsam** — anahtar neye bakiyor. `src/features/ob.py` girdiyi uretir, dusurmeli;
   `src/backtest/engine.py` yalnizca girdiyi **tuketir**, dusurmemeli. Yanlis kapsam
   ya 17 dakikalik gereksiz yeniden kuruluma ya da bayat veriye mal olur.
2. **Mekanizma** — kapanistaki bir dosyanin icerigi degisince anahtar gercekten
   degisiyor mu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest import loader
from src.data import collect

# --- 1. kapsam: gercek repoda kapanis dogru dosyalari iceriyor mu --------------


def gercek_kapanis() -> set[str]:
    return {p.name for p in loader._src_closure(loader.SEED, loader.SRC_ROOT)}


def test_closure_includes_the_modules_that_build_symboldata():
    """Girdiyi ureten her sey kapanista olmali."""
    kapanis = gercek_kapanis()
    for gerekli in ("loader.py", "ob.py", "fvg.py", "structure.py", "candles.py",
                    "detect.py", "model.py", "collect.py"):
        assert gerekli in kapanis, f"{gerekli} kapanista yok — onbellek bayatlayabilir"


def test_closure_excludes_engine_and_strategy():
    """Motor ve strateji yalnizca tuketici: degismeleri onbellegi dusurmemeli."""
    kapanis = gercek_kapanis()
    assert "engine.py" not in kapanis
    assert "entry.py" not in kapanis
    assert "portfolio.py" not in kapanis
    assert "costs.py" not in kapanis


# --- 2. mekanizma: sahte bir src/ agacinda anahtarin davranisi -----------------


@pytest.fixture
def sahte(tmp_path, monkeypatch):
    """Sahte `data/` + `src/` agaci. Kapanis: loader -> features/ob. engine disarida."""
    veri, src = tmp_path / "data", tmp_path / "src"
    for tf in (loader.DETECT_TF, loader.STATE_TF):
        d = veri / "bingx" / "BTC-USDT-USDT" / tf
        d.mkdir(parents=True)
        (d / "2025-01.parquet").write_bytes(b"x" * 10)

    (src / "features").mkdir(parents=True)
    (src / "backtest").mkdir(parents=True)
    (src / "features" / "ob.py").write_text("IMPULSE_MULT = 4.0")
    seed = src / "backtest" / "loader.py"
    seed.write_text("from src.features.ob import IMPULSE_MULT")
    # Motor loader'i import eder; loader motoru etmez -> kapanisin disinda.
    (src / "backtest" / "engine.py").write_text("from src.backtest.loader import x")

    monkeypatch.setattr(collect, "DATA_ROOT", veri)
    monkeypatch.setattr(loader, "SRC_ROOT", src)
    monkeypatch.setattr(loader, "SEED", seed.resolve())
    loader._src_closure.cache_clear()
    yield veri, src
    loader._src_closure.cache_clear()


def anahtar() -> str:
    return loader._cache_key("BTC/USDT:USDT", "bingx", loader.TRAIN_FRAC)


def test_cache_key_is_stable_for_same_inputs(sahte):
    assert anahtar() == anahtar()


def test_cache_key_drops_when_feature_code_changes(sahte):
    """`src/features/ob.py` degisti -> onbellek dusmeli."""
    onceki = anahtar()
    (sahte[1] / "features" / "ob.py").write_text("IMPULSE_MULT = 2.0")
    assert anahtar() != onceki


def test_cache_key_survives_engine_change(sahte):
    """`src/backtest/engine.py` degisti -> onbellek **isabet etmeli**."""
    onceki = anahtar()
    (sahte[1] / "backtest" / "engine.py").write_text("from src.backtest.loader import x\nY = 1")
    assert anahtar() == onceki


def test_cache_key_drops_when_source_data_changes(sahte):
    onceki = anahtar()
    p = sahte[0] / "bingx" / "BTC-USDT-USDT" / loader.STATE_TF / "2025-01.parquet"
    p.write_bytes(b"x" * 11)  # boyut + mtime
    assert anahtar() != onceki


def test_cache_key_separates_train_frac(sahte):
    assert loader._cache_key("BTC/USDT:USDT", "bingx", 0.80) != \
           loader._cache_key("BTC/USDT:USDT", "bingx", 0.60)


def test_relative_import_raises_instead_of_silently_narrowing(sahte, monkeypatch):
    """Goreli import cozulemez; sessizce atlamak bayat onbellek demek (CLAUDE.md #8)."""
    (sahte[1] / "backtest" / "loader.py").write_text("from . import ob")
    loader._src_closure.cache_clear()
    with pytest.raises(loader.RelativeImportError):
        anahtar()


# --- 3. onbellek dosya yasam dongusu ------------------------------------------


def test_cache_writes_reads_and_deletes_stale_key(tmp_path, monkeypatch):
    """Isabet `_build_symbol`'u hic cagirmamali; eski anahtarli dosya kalmamali."""
    monkeypatch.setattr(loader, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(loader, "_cache_key", lambda *a: "AAAA")
    cagri = []
    monkeypatch.setattr(loader, "_build_symbol",
                        lambda *a: cagri.append(a) or "SAHTE-VERI")
    (tmp_path / "BTC-USDT-USDT-ESKI.pkl").write_bytes(b"bayat")

    assert loader.load_symbol("BTC/USDT:USDT") == "SAHTE-VERI"
    assert loader.load_symbol("BTC/USDT:USDT") == "SAHTE-VERI"
    assert len(cagri) == 1, "ikinci cagri onbellekten gelmeliydi"
    assert not (tmp_path / "BTC-USDT-USDT-ESKI.pkl").exists(), "eski anahtar silinmedi"
    assert not list(tmp_path.glob("*.tmp")), "yarim yazma dosyasi kaldi"
