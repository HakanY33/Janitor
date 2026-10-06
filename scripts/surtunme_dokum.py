"""Bir koşunun sürtünme dökümü — açıklayıcı, öneri yok.

    python -m scripts.surtunme_dokum logs/inceleme/swing_B2_100_v08_son_supuren.pkl
        → docs/measurements/surtunme_28.md (--out ile değişir)

Paket `scripts.inceleme.kos` çıktısıdır ve kalem defterini (`defter`, 2026-10-05'ten beri)
taşımalıdır; yoksa hata. Gösterilen:

1. Toplam: komisyon, funding, slippage (slippage fiyatın içindedir, brüte gömülü; ayrıca
   gösterilir, sürtünme toplamına eklenmez — toplam = komisyon + funding, SONUCLAR ile aynı).
2. Çıkış tipine göre (nihai TP / TP1 + breakeven / stop): işlem başına komisyon, brüt, net.
3. Maker / taker: kalem → emir tipi `engine.MAKER_REASONS` ile (limit kolunda giriş, TP1,
   nihai TP maker; stop, breakeven ve diğer kapanışlar taker). Koşuda limit emrinin taker'a
   düşmesi (`taker_*` sayaçları) sıfır değilse ayrıca yazılır.
4. Leg büyüklüğü: dilimlere göre komisyon/işlem, brüt/işlem ve komisyonun brüte oranı; en çok
   komisyon ödeyen işlemlerin leg'i. Komisyon doları bakiyeyle büyür; baz puan (komisyon /
   giriş notional'ı) ayrıca verilir.
"""
from __future__ import annotations

import argparse
import pickle
import statistics
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

OUT = Path("docs/measurements/surtunme_28.md")
CIKIS = {"FINAL_TP": "nihai TP", "BREAKEVEN": "TP1 + breakeven", "STOP": "stop"}
MAKER_KALEM = {"komisyon_giris", "komisyon_tp1", "komisyon_tp_nihai", "komisyon_kucultme"}


def leg(t, Z) -> float:
    z = Z[t.zone_id]
    return abs(z.anchor_1_price - z.anchor_0_price) / z.anchor_0_price * 100


def dokum(p: dict) -> list[str]:
    if "defter" not in p:
        raise KeyError("paket kalem defteri taşımıyor — koşu 2026-10-05 öncesi; yeniden koş")
    T, Z, D = p["trades"], p["zones"], p["defter"]
    kom = sum((t.fees for t in T), Decimal(0))
    fun = sum((t.funding for t in T), Decimal(0))
    bru = sum((t.gross for t in T), Decimal(0))
    d_kom = sum((v for k, v in D.items() if k.startswith("komisyon_")), Decimal(0))
    slip = {k[9:]: v for k, v in D.items() if k.startswith("slippage_")}
    f = lambda v, n=2: f"{float(v):,.{n}f}"
    s = [f"# Sürtünme dökümü — #{p.get('_no', '?')} (açıklayıcı)", "",
         f"Paket `{p.get('_yol', '')}` · parmak izi `{p['hash']}` · spec {p['spec_version']} · "
         f"kod {p['code_version']} · {len(T)} işlem. Öneri yok; yalnızca dağılım.", "",
         "## 1 · Toplam", "",
         "| kalem | $ |", "|---|---:|",
         f"| brüt fiyat PnL'i | {f(bru)} |", f"| komisyon | {f(kom)} |", f"| funding | {f(fun)} |",
         f"| **sürtünme (komisyon + funding)** | **{f(kom + fun)}** |", f"| net | {f(bru - kom - fun)} |",
         f"| (slippage — brütün içinde, ayrıca) | {f(sum(slip.values(), Decimal(0)))} |", "",
         f"Defter komisyonu {f(d_kom)} = işlem komisyonu {f(kom)} "
         f"({'eşit' if abs(d_kom - kom) < Decimal('0.0001') else 'FARK — kapanmamış pozisyon/koşu sonu'}).", ""]

    # 2 · çıkış tipi
    g = defaultdict(list)
    for t in T:
        g[CIKIS.get(t.reason, "diğer (" + t.reason + ")")].append(t)
    s += ["## 2 · Çıkış tipine göre", "",
          "| çıkış | işlem | komisyon/işlem $ | komisyon bps (giriş notional'ı) | brüt/işlem $ | net/işlem $ | komisyon payı |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for ad, L in sorted(g.items(), key=lambda x: -len(x[1])):
        k = sum((t.fees for t in L), Decimal(0))
        bps = statistics.median(float(t.fees / (t.entry_qty * t.entry_price)) * 1e4 for t in L)
        s.append(f"| {ad} | {len(L)} | {f(k / len(L), 4)} | {bps:.1f} | "
                 f"{f(sum((t.gross for t in L), Decimal(0)) / len(L), 4)} | "
                 f"{f(sum((t.pnl for t in L), Decimal(0)) / len(L), 4)} | {float(k / kom):.0%} |")

    # 3 · maker / taker
    mk = sum((v for k, v in D.items() if k in MAKER_KALEM), Decimal(0))
    s += ["", "## 3 · Maker / taker", "",
          "| kalem | emir | komisyon $ | pay | slippage $ |", "|---|---|---:|---:|---:|"]
    for k, v in sorted(((k, v) for k, v in D.items() if k.startswith("komisyon_")), key=lambda x: -x[1]):
        s.append(f"| {k[9:]} | {'maker' if k in MAKER_KALEM else 'taker'} | {f(v)} | "
                 f"{float(v / d_kom):.0%} | {f(slip.get(k[9:], 0))} |")
    s += [f"| **toplam** | maker {float(mk / d_kom):.0%} · taker {float(1 - mk / d_kom):.0%} | "
          f"{f(d_kom)} | | {f(sum(slip.values(), Decimal(0)))} |"]
    dus = {k: v for k, v in p["counters"].items() if k.startswith("taker_") and v}
    s += ["", f"Limit emrinin taker'a düşmesi: {dus or 'yok (sayaçlar 0)'}.", ""]

    # 4 · leg
    sirali = sorted(T, key=lambda t: leg(t, Z))
    n = len(sirali)
    s += ["## 4 · Leg büyüklüğüne göre (beşte birlik dilimler)", "",
          "| leg dilimi (%) | işlem | komisyon/işlem $ | brüt/işlem $ | komisyon / brüt kazanç | stop payı |",
          "|---|---:|---:|---:|---:|---:|"]
    for i in range(5):
        L = sirali[i * n // 5:(i + 1) * n // 5]
        k = sum((t.fees for t in L), Decimal(0))
        b = sum((t.gross for t in L), Decimal(0))
        kaz = sum((t.gross for t in L if t.gross > 0), Decimal(0))
        s.append(f"| {leg(L[0], Z):.2f}–{leg(L[-1], Z):.2f} | {len(L)} | {f(k / len(L), 4)} | "
                 f"{f(b / len(L), 4)} | {float(k / kaz):.0%} | "
                 f"{sum(t.reason == 'STOP' for t in L) / len(L):.0%} |")
    ust = sorted(T, key=lambda t: t.fees, reverse=True)
    on = ust[:max(1, n // 10)]
    s += ["", f"**En çok komisyon ödeyen %10 ({len(on)} işlem):** leg medyanı "
          f"{statistics.median(leg(t, Z) for t in on):.2f}% (tümü {statistics.median(leg(t, Z) for t in T):.2f}%), "
          f"komisyonun {float(sum((t.fees for t in on), Decimal(0)) / kom):.0%}'i, çıkış "
          + ", ".join(f"{CIKIS.get(r, r)} {sum(t.reason == r for t in on)}" for r in CIKIS) + ". "
          "Komisyon doları giriş notional'ıyla (= bakiye × K) büyür; aşağıdaki ilk 10'da bps de var.", "",
          "| sembol | giriş | çıkış | leg % | komisyon $ | komisyon bps | brüt $ |", "|---|---|---|---:|---:|---:|---:|"]
    for t in ust[:10]:
        s.append(f"| {t.symbol.split('/')[0]} | {t.entry_ts:%Y-%m-%d %H:%M} | {CIKIS.get(t.reason, t.reason)} | "
                 f"{leg(t, Z):.2f} | {f(t.fees, 4)} | {float(t.fees / (t.entry_qty * t.entry_price)) * 1e4:.1f} | "
                 f"{f(t.gross, 4)} |")
    return s + [""]


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("pkl", type=Path)
    a.add_argument("--out", type=Path, default=OUT)
    x = a.parse_args()
    p = pickle.loads(x.pkl.read_bytes())
    p["_yol"] = x.pkl.as_posix()
    p["_no"] = x.out.stem.rsplit("_", 1)[-1]  # surtunme_29.md → 29
    x.out.write_text("\n".join(dokum(p)), encoding="utf-8")
    print(x.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
