"""Strateji inceleme etiketleri — açıklayıcı özet (20 işlem, `docs/inceleme/strateji/etiketler.json`).

    python -m scripts.inceleme_ozet

Not: grafik çıkışı gösteriyordu, yani karar × sonuç ilişkisi sonradan bakış içerebilir —
kanıt değil, yalnızca bağlam. Kaynak dosya `docs/inceleme/strateji/ozet.md`.
"""
from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from pathlib import Path

ETIKET = Path("docs/inceleme/strateji/etiketler.json")
PKL = Path("logs/inceleme/ltf31_31.pkl")
OUT = Path("docs/inceleme/strateji/ozet.md")


def pnl_pct(t) -> float:
    """Net PnL / giriş notional — kaldıraçlı pozisyonun yüzde kâr/zararı."""
    return float(t.pnl) / (float(t.entry_price) * float(t.entry_qty)) * 100


def crosstab(rows: list[dict], a: str, b: str) -> tuple[list[str], list[str], dict]:
    av = sorted({r[a] for r in rows})
    bv = sorted({r[b] for r in rows})
    c = Counter((r[a], r[b]) for r in rows)
    return av, bv, c


def tablo(basliklar: list[str], satirlar: list[list[str]]) -> list[str]:
    s = ["| " + " | ".join(basliklar) + " |", "|" + "---|" * len(basliklar)]
    s += ["| " + " | ".join(r) + " |" for r in satirlar]
    return s


def uret() -> None:
    etiketler = json.loads(ETIKET.read_text(encoding="utf-8"))
    p = pickle.loads(PKL.read_bytes())
    T = {t.zone_id: t for t in p["trades"]}

    rows = []
    for e in etiketler:
        t = T[e["zone_id"]]
        rows.append({**e, "pnl_pct": pnl_pct(t)})

    s = ["# Strateji inceleme etiketleri — açıklayıcı özet", "",
         f"Kaynak: `{ETIKET}` (20 işlem) × `{PKL}` (spec {p['spec_version']}, kod {p['code_version']}, "
         f"parmak izi {p['hash']}). **Not:** grafikler çıkışı gösteriyordu — karar × sonuç ilişkisi "
         "sonradan bakış içerebilir, kanıt olarak kullanılmaz; aşağıdaki tablolar yalnızca bağlam.", ""]

    s += ["## 1. İşlem başına yüzde kâr/zarar", "",
          "PnL / giriş notional × 100 (kaldıraçlı pozisyonun yüzdesi).", ""]
    s += tablo(["#", "Sembol", "Yön", "Karar", "% PnL", "Çıkış", "4h yön"],
               [[f"{r['n']}", r["symbol"].split("/")[0], r["side"], r["karar"],
                 f"{r['pnl_pct']:+.2f}", r["cikis_sebep"], r["bias_4h"]] for r in rows])
    toplam_pct = sum(r["pnl_pct"] for r in rows)
    s += ["", f"Toplam (20 işlem, eşit ağırlık değil — kendi notional'ı): {toplam_pct:+.2f} puan toplamı, "
              f"ortalama {toplam_pct / len(rows):+.2f}.", ""]

    s += ["## 2. Karar × sonuç", ""]
    av, bv, c = crosstab(rows, "karar", "cikis_sebep")
    s += tablo(["Karar \\ Çıkış", *bv, "Toplam"],
               [[a, *[str(c[(a, b)]) for b in bv], str(sum(c[(a, b)] for b in bv))] for a in av])
    s += ["", "**Not:** bu tablo sonradan bakış içerir — grafik çıkışı gösteriyordu. Kanıt değil."]
    s += [""]

    s += ["## 3. Sebep dağılımı (girmezdim)", ""]
    sebepler = Counter(r["sebep"] for r in rows if r["karar"] == "girmezdim")
    s += tablo(["Sebep", "Adet"], [[k, str(v)] for k, v in sebepler.most_common()])
    s += [""]

    s += ["## 4. Karar × 4h yön", ""]
    av, bv, c = crosstab(rows, "karar", "bias_4h")
    s += tablo(["Karar \\ 4h yön", *bv, "Toplam"],
               [[a, *[str(c[(a, b)]) for b in bv], str(sum(c[(a, b)] for b in bv))] for a in av])
    s += [""]

    OUT.write_text("\n".join(s) + "\n", encoding="utf-8")
    print(OUT)


def main() -> int:
    uret()
    return 0


if __name__ == "__main__":
    sys.exit(main())
