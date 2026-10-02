"""Paper bellek kabulü: ısınma + ardışık 3 adet 30m tespiti, RSS düz mü (`SERVER.md` göç sırası).

Üretimdeki yolla aynı: `PaperCore.dakika` iş parçacığında (`scripts/paper.py` `to_thread`),
ardından `bellek_birak()`. Linux'ta `MALLOC_ARENA_MAX=2` ortamda olmalı (birimdeki gibi).

Geçer: ısınmadan sonraki her döngünün RSS'i 1. döngününkinin ±10 MB'ı içinde.
`--iz`: tracemalloc (1 çerçeve) — Python'un canlı tuttuğu bellek
büyüyorsa referans sızıntısı, düz ama RSS büyüyorsa ayırıcı parçalanması.

    MALLOC_ARENA_MAX=2 .venv/bin/python -m scripts.sizinti --symbols <paper ile aynı 20 sembol>

Ağ yok: 30m geçmişi diskten (`collect.read_parquet`), son `--dongu` mum canlı gibi beslenir.
Sonuçta döngü süresi de yazılır (`LIVE.md` artımlı tespit tetiği: > 10 dk).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.paper import F1, bellek_birak, rss_mb
from src.backtest.costs import build_cost_model
from src.data import collect
from src.live.paper import DAKIKA, Durum, PaperCore

BANT_MB = 10.0
KOLON = ["ts", "open", "high", "low", "close", "volume"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--dongu", type=int, default=3)
    p.add_argument("--iz", action="store_true", help="tracemalloc (1 çerçeve)")
    a = p.parse_args()
    if sys.platform.startswith("linux") and os.environ.get("MALLOC_ARENA_MAX") != "2":
        print("MALLOC_ARENA_MAX=2 yok — ölçüm birimdeki koşulu temsil etmez", file=sys.stderr)
        return 2

    d = {s: collect.read_parquet("bingx", s, "30m")[KOLON].reset_index(drop=True)
         for s in a.symbols}
    son = min(d[s].ts.iloc[-1] for s in a.symbols)  # her sembolde ortak son mum
    d = {s: x[x.ts <= son].reset_index(drop=True) for s, x in d.items()}
    gecmis = {s: len(x) - a.dongu for s, x in d.items()}
    bas = son - (a.dongu - 1) * pd.Timedelta("30m")  # ilk canlı dakika = son geçmiş mumun kapanışı

    core = PaperCore.yeni(Durum(Path(tempfile.mkdtemp()) / "f1.db"), a.symbols,
                          build_cost_model(a.symbols, "bingx"), bas, **F1)
    for s in a.symbols:
        core.otuz(s, d[s].iloc[:gecmis[s]])
    is_parcacigi = ThreadPoolExecutor(1)

    def dakika(t, satir: dict[str, pd.Series]) -> float:
        bars = {s: tuple(float(r[c]) for c in ("close",) * 4 + ("volume",))
                for s, r in satir.items()}
        c0 = time.time()
        is_parcacigi.submit(core.dakika, t, bars).result()
        bellek_birak()
        return time.time() - c0

    t0 = np.datetime64(bas.tz_localize(None), "ns")
    sure = dakika(t0, {s: d[s].iloc[gecmis[s] - 1] for s in a.symbols})
    print(f"isinma {sure:.0f} sn  rss {rss_mb():.0f} MB", flush=True)

    if a.iz:
        tracemalloc.start(1)
    rss, onceki = [], (tracemalloc.take_snapshot() if a.iz else None)
    for k in range(a.dongu):
        for s in a.symbols:
            core.otuz(s, d[s].iloc[gecmis[s] + k:gecmis[s] + k + 1])
        kap = np.datetime64((d[a.symbols[0]].ts.iloc[gecmis[a.symbols[0]] + k]
                             + pd.Timedelta("30m")).tz_localize(None), "ns")
        sure = dakika(kap - DAKIKA, {s: d[s].iloc[gecmis[s] + k] for s in a.symbols})
        rss.append(rss_mb())
        satir = f"dongu {k + 1}  {sure:.0f} sn  rss {rss[-1]:.0f} MB"
        if a.iz:
            snap = tracemalloc.take_snapshot()
            fark = sum(st.size_diff for st in snap.compare_to(onceki, "lineno"))
            satir += (f"  traced {tracemalloc.get_traced_memory()[0] / 2**20:.1f} MB"
                      f"  Δ {fark / 2**20:+.2f} MB")
            onceki = snap
        print(satir, flush=True)

    sapma = max(abs(r - rss[0]) for r in rss)
    gecti = sapma <= BANT_MB
    print(f"{'GECTI' if gecti else 'KALDI'}: {a.dongu} döngüde 1. döngüden en büyük RSS sapması "
          f"{sapma:.1f} MB (sınır ±{BANT_MB:.0f})")
    return 0 if gecti else 1


if __name__ == "__main__":
    sys.exit(main())
