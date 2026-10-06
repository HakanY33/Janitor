"""İki koşunun brüt PnL farkı gürültü mü — sembol-ay blokları üzerinden eşleşik bootstrap.

    python -m scripts.bootstrap_fark A.pkl B.pkl --out docs/measurements/fark_28_29.md

Blok = (sembol, giriş ayı). Her yinelemede blok kümesi iadeli çekilir; **aynı** çekiliş iki
koşuya uygulanır (eşleşik), böylece ortak piyasa gürültüsü farktan düşer. Bir blokta bir koşunun
işlemi yoksa o koşu için 0'dır. %95 aralık = yüzdelik (2,5 / 97,5). Tohum sabit.
Açıklayıcıdır; kural değiştirmez.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

TOHUM, N = 20261006, 10_000


def bloklar(pkl: Path) -> dict[tuple[str, str], float]:
    """(sembol, giriş ayı) → brüt fiyat PnL'i ($)."""
    b: dict = defaultdict(float)
    for t in pickle.loads(pkl.read_bytes())["trades"]:
        b[(t.symbol, pd.Timestamp(t.entry_ts).strftime("%Y-%m"))] += float(t.gross)
    return b


def bootstrap(a: dict, b: dict, n: int = N, tohum: int = TOHUM) -> dict:
    anahtar = sorted(set(a) | set(b))
    x = np.array([a.get(k, 0.0) for k in anahtar])
    y = np.array([b.get(k, 0.0) for k in anahtar])
    i = np.random.default_rng(tohum).integers(0, len(anahtar), size=(n, len(anahtar)))
    ara = lambda v: tuple(np.percentile(v, [2.5, 97.5]))
    xa, ya = x[i].sum(1), y[i].sum(1)
    return {"blok": len(anahtar), "a": x.sum(), "b": y.sum(), "fark": y.sum() - x.sum(),
            "a_ara": ara(xa), "b_ara": ara(ya), "fark_ara": ara(ya - xa)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("a", type=Path); p.add_argument("b", type=Path)
    p.add_argument("--out", type=Path, required=True)
    x = p.parse_args()
    r = bootstrap(bloklar(x.a), bloklar(x.b))
    sifir = r["fark_ara"][0] <= 0 <= r["fark_ara"][1]
    f = lambda v: f"{v:+.2f}"
    x.out.write_text("\n".join([
        f"# Brüt PnL farkı — eşleşik blok bootstrap", "",
        f"A `{x.a.as_posix()}` · B `{x.b.as_posix()}` · {r['blok']} sembol-ay bloğu · "
        f"{N:,} yineleme · tohum {TOHUM} · `scripts/bootstrap_fark.py`.", "",
        "| | brüt $ | %95 aralık |", "|---|---:|---|",
        f"| A | {f(r['a'])} | {f(r['a_ara'][0])} … {f(r['a_ara'][1])} |",
        f"| B | {f(r['b'])} | {f(r['b_ara'][0])} … {f(r['b_ara'][1])} |",
        f"| **B − A** | **{f(r['fark'])}** | **{f(r['fark_ara'][0])} … {f(r['fark_ara'][1])}** |", "",
        ("**Fark sıfırı kapsıyor → gürültüden ayırt edilemiyor.**" if sifir
         else "**Fark sıfırı kapsamıyor.**"), ""]), encoding="utf-8")
    print(x.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
