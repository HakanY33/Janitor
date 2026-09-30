"""Paper kalp atışı + karar logu özeti (`OPEN-55`): gecikme, bellek, kill, DATA.

    python -m scripts.kalp_ozet                 # logs/paper/*.log + logs/decisions/*.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def oku(desen: str) -> list[dict]:
    return [json.loads(x) for f in sorted(Path().glob(desen))
            for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    k = pd.DataFrame(oku("logs/paper/*.log"))
    olay = oku("logs/decisions/*.jsonl")
    canli = k[k["mod"] == "canli"]
    q = lambda s: f"p50 {s.median():.1f} · p95 {s.quantile(.95):.1f} · maks {s.max():.1f}"
    data = Counter(o.get("outcome") for o in olay if o.get("event") == "DATA")
    kill = [o for o in olay if o.get("event") == "KILL"]
    print(f"dakika {len(k)} ({k.dakika.iloc[0]} → {k.dakika.iloc[-1]}) · canlı {len(canli)} · yetişme {len(k) - len(canli)}")
    print(f"gecikme sn (canlı): {q(canli.gecikme_sn)}")
    print(f"işlem sn: {q(k.islem_sn)} · >60 sn {int((k.islem_sn > 60).sum())} dakika")
    print(f"rss_mb: başlangıç {k.rss_mb.iloc[0]:.0f} · son {k.rss_mb.iloc[-1]:.0f} · tepe {k.rss_mb.max():.0f} → MemoryMax ≈ {k.rss_mb.max() * 1.5:.0f} MB")
    print(f"kill olayı {len(kill)} · kalp satırında kill dolu {int(k['kill'].notna().sum())}")
    for o in kill:
        print(f"  {o.get('ts')} {o.get('outcome')}: {o.get('reason')}")
    print(f"DATA olayı {sum(data.values())}: " + ", ".join(f"{a} {n}" for a, n in data.most_common()))
    print(f"işlem {k.islem.iloc[-1]} · açık {k.acik.iloc[-1]} · equity {k.equity.iloc[-1]:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
