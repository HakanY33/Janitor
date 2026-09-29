"""Düzeltilmiş zaman damgası — kaldıraç zinciri yeniden ölçümü. AÇIKLAYICI.

    python -m scripts.bg scripts.damga

2026-09-29'a kadar 30m zone/OB/FVG damgaları mumun açılışıydı ve motor onları bilgi anı
diye kullanıyordu (1 mum look-ahead). Aynı düzeltmede iç stop (`R-RISK-02`, breakeven)
seviyeden değil tetik mumunun kapanışından çıkıyor (bilgi o mum kapanınca oluşur).
Bu betik eski kaldıraç zincirini **yalnızca eğitim diliminde** düzeltilmiş kodla yeniden
koşar. Hiçbir sonuç parametre, kural ya da filtre seçmek için kullanılmaz.

Kollar kümülatiftir, tanımları ölçüldükleri zamanki gibidir:

| kol | tanım |
|---|---|
| A | mevcut hal o zaman: ekleme sınırsız, `ADD-REJECT-E` yok, breakeven ham |
| C | A + ekleme tavanı 3, küçültme bir kez + limit emri (levers B+C) |
| D | C + `R-ENTRY-02` (3) kapalı: yalnızca OB/FVG girişi (gösterge kapısı) |
| E3 | D + `ADD-REJECT-E` `L` = %3 |
| F1 | E3 + breakeven ücret dahil (`OPEN-35`) + ekleme kapalı — v1 varsayılanı |
| F1-kapısız | F1, gösterge kapısı açık (`require_indicator=False`) |

C ve F1-kapısız, "gösterge kapısı hâlâ değer katıyor mu" sorusu için vardır: D − C ve
F1 − F1-kapısız.

**Kriter 3** (spec §8): ay = UTC takvim ayı, işlemin **çıkış** (realize) ayı. Dilimde
günlerinin yarısından azı kalan ay sayılmaz (`OPEN-40`). A1: ayların ≥ %60'ı net pozitif.
A2: hiçbir ay toplam netin %40'ını aşmaz; toplam net ≤ 0 ise A2 geçilemez.
"""
from __future__ import annotations

import argparse
import calendar
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.levers import olc
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ETIKET = "düzeltilmiş zaman damgası — açıklayıcı"
_A = {"max_adds": None, "stop_loss_cap": Decimal("0"), "breakeven_fees": False}
_C = {**_A, "max_adds": 3, "reduce_once": True, "limit_orders": True}
_D = {**_C, "require_indicator": True}
_E3 = {**_D, "stop_loss_cap": Decimal("0.03")}
_F1 = {**_E3, "breakeven_fees": True, "max_adds": 0}
KOLLAR = {"A": _A, "C": _C, "D": _D, "E3": _E3, "F1": _F1,
          "F1-kapisiz": {**_F1, "require_indicator": False}}

# Düzeltme öncesi raporlanan değerler (logs/levers.txt, logs/robustness.txt,
# logs/f_kollari.txt). O günün kodu; yalnızca yön için.
ONCEKI = {"A": Decimal("-9974.03"), "C": Decimal("-9818.52"), "D": Decimal("-5217.50"),
          "E3": Decimal("-176.47"), "F1": Decimal("2376.09")}

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def kriter3(trades, bas: pd.Timestamp, son: pd.Timestamp, ay_alani: str = "exit_ts") -> dict:
    """Spec §8 kriter 3. `bas`/`son`: dilimin ilk ve son anı (UTC)."""
    net: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in trades:
        net[pd.Timestamp(getattr(t, ay_alani)).strftime("%Y-%m")] += t.pnl
    sayilan = []
    for ay in pd.period_range(bas.tz_localize(None), son.tz_localize(None), freq="M"):
        gun = calendar.monthrange(ay.year, ay.month)[1]
        a0 = max(bas, pd.Timestamp(ay.start_time, tz="UTC"))
        a1 = min(son, pd.Timestamp(ay.end_time, tz="UTC"))
        if (a1 - a0) / pd.Timedelta("1D") >= gun / 2:  # yarısından azı kalan ay sayılmaz
            sayilan.append(str(ay))
    aylar = {ay: net.get(ay, Decimal("0")) for ay in sayilan}
    toplam = sum(aylar.values(), Decimal("0"))
    pozitif = sum(1 for v in aylar.values() if v > 0)
    a1 = bool(aylar) and pozitif / len(aylar) >= 0.60
    a2 = toplam > 0 and all(v <= Decimal("0.40") * toplam for v in aylar.values())
    return {"aylar": aylar, "pozitif": pozitif, "n": len(aylar), "A1": a1, "A2": a2,
            "toplam": toplam}


def main() -> int:
    p = argparse.ArgumentParser(description="Düzeltilmiş zaman damgası — kaldıraç zinciri")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--kollar", default=",".join(KOLLAR))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/damga.txt")
    p.add_argument("--csv", default="logs/damga.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    data = [d for d in (load_symbol(s, a.exchange, TRAIN_FRAC)
                        for s in liquidity_symbols(a.limit)) if d is not None]
    isimler = [d.symbol for d in data]
    bas = min(pd.Timestamp(d.ts[0], tz="UTC") for d in data)
    son = max(pd.Timestamp(d.ts[-1], tz="UTC") for d in data)

    olculer: dict[str, dict] = {}
    for ad in a.kollar.split(","):
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} basliyor...", file=sys.stderr, flush=True)
        res = Backtest(data, build_cost_model(isimler, a.exchange), a.balance,
                       k=Decimal("0.25"), mmr=Decimal("0.005"), t_rahat=Decimal("0.50"),
                       t_kritik=Decimal("0.08"), uyari_blocks_adds=False,
                       progress_every=a.progress_every, **KOLLAR[ad]).run()
        m = olc(res, a.balance)
        m["k3"] = kriter3(res.trades, bas, son)
        m["k3_giris"] = kriter3(res.trades, bas, son, "entry_ts")
        olculer[ad] = m
        print(f"  kol {ad}: {m['islem']:,} islem, net {m['net']:,.0f}, "
              f"{(time.time() - c0) / 60:.1f} dk", file=sys.stderr, flush=True)

    say(f"KALDIRAÇ ZİNCİRİ · {ETIKET} · spec {spec_version()} · kod {code_version()}")
    say(f"  {len(data)} sembol · eğitim dilimi (en eski %{TRAIN_FRAC * 100:.0f}) "
        f"{bas:%Y-%m-%d} → {son:%Y-%m-%d} · ayrılmış okunmadı")
    say("")
    kollar = list(olculer)
    say(f"  {'ölçü':<30}" + "".join(f"{k:>14}" for k in kollar))

    def surt(m):
        return m["komisyon"] + m["slippage"]

    satirlar = [
        ("net PnL (düzeltilmiş)", lambda k, m: f"{m['net']:,.0f}"),
        ("net PnL (önceki rapor)", lambda k, m: f"{ONCEKI[k]:,.0f}" if k in ONCEKI else "-"),
        ("brüt fiyat PnL", lambda k, m: f"{m['brut_slipsiz']:,.0f}"),
        ("sürtünme", lambda k, m: f"{surt(m):,.0f}"),
        ("brüt / sürtünme", lambda k, m: f"{m['brut_slipsiz'] / surt(m):.3f}" if surt(m) else "-"),
        ("işlem", lambda k, m: f"{m['islem']:,}"),
        ("maks DD", lambda k, m: f"{m['maxdd_%']:.1f}%"),
        ("K3 pozitif ay (çıkış)", lambda k, m: f"{m['k3']['pozitif']}/{m['k3']['n']}"),
        ("K3 A1 ≥%60", lambda k, m: "GEÇTİ" if m["k3"]["A1"] else "kaldı"),
        ("K3 A2 ay ≤ %40 toplam", lambda k, m: "GEÇTİ" if m["k3"]["A2"] else "kaldı"),
        ("K3 pozitif ay (giriş ayı)", lambda k, m: f"{m['k3_giris']['pozitif']}/{m['k3_giris']['n']}"),
        ("uzlaşma farkı", lambda k, m: f"{m['uzlasma_farki']:.1E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<30}" + "".join(f"{f(k, olculer[k]):>14}" for k in kollar))
    say("")
    say("  aylık net (çıkış ayı)")
    aylar = sorted({ay for m in olculer.values() for ay in m["k3"]["aylar"]})
    for ay in aylar:
        say(f"  {ay:<30}" + "".join(f"{olculer[k]['k3']['aylar'].get(ay, 0):>14,.0f}" for k in kollar))
    for x, y in (("D", "C"), ("F1", "F1-kapisiz")):
        if x in olculer and y in olculer:
            say(f"  gösterge kapısı {x} − {y}: net {olculer[x]['net'] - olculer[y]['net']:+,.0f} · "
                f"brüt {olculer[x]['brut_slipsiz'] - olculer[y]['brut_slipsiz']:+,.0f} · "
                f"işlem {olculer[x]['islem'] - olculer[y]['islem']:+,}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    pd.DataFrame([{"kol": k, "etiket": ETIKET, "net": m["net"], "brut": m["brut_slipsiz"],
                   "surtunme": surt(m), "islem": m["islem"], "maxdd_%": m["maxdd_%"],
                   "k3_pozitif": m["k3"]["pozitif"], "k3_n": m["k3"]["n"],
                   "k3_A1": m["k3"]["A1"], "k3_A2": m["k3"]["A2"]}
                  for k, m in olculer.items()]).to_csv(a.csv, index=False)
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
