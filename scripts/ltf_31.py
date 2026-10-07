"""#31 — spec v0.11 (5m/30m/4h OB, OB/OTE girişi, ekleme 1-1 × 3) + dört çıkarma kolu.

    python -m scripts.ltf_31 --hazirla                  # 20 sembol, veri → logs/inceleme/ltf31_veri.pkl
    python -m scripts.bg scripts.ltf_31 --kol 31        # her kol ayrı süreç: 31 a b c d
    python -m scripts.ltf_31 --rapor --out docs/measurements/ltf_31.md

Kurgu #30 ile aynı (B2 + `son_supuren`, A1+B, 100 USDT, eğitim dilimi, 20 sembol, K = 0,25,
limit emirleri, ADD-REJECT-E %3); değişen yalnızca v0.11 kuralları. Kollar yalnızca bir parçayı
kapatır: (a) ekleme · (b) 4h OB · (c) 5m OB · (d) OTE girişi (yalnızca OB girişi).
Boyut: kullanıcı kuralı (%1 marjin × maks kaldıraç) uygulanamadı — BingX maks kaldıracı anahtarsız
uçta vermiyor (`quote/contracts` v2/v3, `tradingRules`; kademe ucu `maintMarginRatio` kimlikli).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import statistics
import sys
from decimal import Decimal
from functools import partial
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

KOK = Path("logs/inceleme")
VERI = KOK / "ltf31_veri.pkl"
BAKIYE = Decimal("100")
KOLLAR = {
    "31": ("#31 (hepsi)", {}, None),
    "a": ("(a) ekleme kapalı", {"max_adds": 0}, None),
    "b": ("(b) 4h OB kapalı", {}, "4h"),
    "c": ("(c) 5m OB kapalı", {}, "5m"),
    "d": ("(d) OTE girişi kapalı", {"require_indicator": True}, None),
}


def pkl(kol: str) -> Path:
    return KOK / f"ltf31_{kol}.pkl"


def hazirla() -> None:
    """20 sembol, swing B2 (zone ve her OB diliminin BoS'u), eşleştirme `son_supuren`."""
    from scripts.measure_ob import liquidity_symbols
    from scripts.swing_secim import aday_b
    from src.backtest.loader import TRAIN_FRAC, _build_symbol
    from src.zones.detect import detect_zones

    b2 = lambda df, symbol, timeframe: aday_b(df, symbol, 2, timeframe)  # noqa: E731
    with mock.patch("src.zones.detect.detect_swings", b2), \
         mock.patch("src.backtest.loader.detect_zones", partial(detect_zones, eslestirme="son_supuren")):
        data = []
        for s in liquidity_symbols(20):
            sd = _build_symbol(s, "bingx", TRAIN_FRAC)
            if sd is not None:
                data.append(sd)
                tf = pd.Series([o.timeframe for o in sd.obs]).value_counts().to_dict()
                print(s, len(sd.zones), "zone", tf, file=sys.stderr, flush=True)
    KOK.mkdir(parents=True, exist_ok=True)
    VERI.write_bytes(pickle.dumps(data, pickle.HIGHEST_PROTOCOL))


def ob_suz(sd, tf: str) -> None:
    """`tf` OB'lerini çıkarır — dizinler maskeyle (delinme önbelleği aynen)."""
    m = np.array([o.timeframe != tf for o in sd.obs], dtype=bool)
    sd.obs = [o for o, k in zip(sd.obs, m) if k]
    for ad in ("ob_top", "ob_bottom", "ob_bull", "ob_known", "ob_pierce", "ob_alive", "ob_bos",
               "ob_gecersiz", "ob_mitig"):
        setattr(sd, ad, getattr(sd, ad)[m])


def kos(kol: str) -> None:
    from scripts.backtest import code_version, spec_version
    from src.backtest.costs import build_cost_model
    from src.backtest.engine import ENTRY_OB_070, Backtest

    ad, kw, cikar = KOLLAR[kol]
    data = pickle.loads(VERI.read_bytes())
    if cikar:
        for sd in data:
            ob_suz(sd, cikar)
    res = Backtest(data, build_cost_model([d.symbol for d in data], "bingx"), BAKIYE,
                   k=Decimal("0.25"), mmr=Decimal("0.005"), t_rahat=Decimal("0.50"),
                   t_kritik=Decimal("0.08"), uyari_blocks_adds=False, limit_orders=True,
                   stop_loss_cap=Decimal("0.03"), entry_rule=ENTRY_OB_070,
                   progress_every=50_000, **kw).run()
    satir = [f"{t.symbol}|{t.entry_ts}|{t.exit_ts}|{t.entry_price}|{t.exit_price}|{t.qty}|"
             f"{t.pnl}|{t.reason}" for t in res.trades]
    zid = {t.zone_id for t in res.trades}
    paket = {
        "kol": kol, "ad": ad, "spec_version": spec_version(), "code_version": code_version(),
        "trades": res.trades, "net": res.portfolio.balance - res.portfolio.start_balance,
        "hash": hashlib.sha256("\n".join(satir).encode()).hexdigest()[:16],
        "zones": {z.zone_id: z for d in data for z in d.zones if z.zone_id in zid},
        "bitis": {d.symbol: d.ts[-1] for d in data},
        "baslangic": {d.symbol: d.ts[0] for d in data},
        "bakiye": BAKIYE, "counters": res.counters, "defter": dict(res.costs.breakdown),
        "maks_dd": res.portfolio.max_drawdown_f, "likidasyon": res.portfolio.liquidation_events,
    }
    pkl(kol).write_bytes(pickle.dumps(paket, pickle.HIGHEST_PROTOCOL))
    print(json.dumps({"kol": kol, "net": str(paket["net"]), "islem": len(res.trades),
                      "hash": paket["hash"]}))


def olc(p: dict) -> dict:
    from scripts.damga import kriter3
    from scripts.inceleme import r_degeri

    T, Z = p["trades"], p["zones"]
    R = [r_degeri(t, Z[t.zone_id]) for t in T]
    kaz = [r for t, r in zip(T, R) if t.pnl > 0]
    kay = [r for t, r in zip(T, R) if t.pnl <= 0]
    bas = min(pd.Timestamp(v, tz="UTC") for v in p["baslangic"].values())
    son = max(pd.Timestamp(v, tz="UTC") for v in p["bitis"].values())
    k3 = kriter3(T, bas, son)
    D = lambda f: float(sum((getattr(t, f) for t in T), Decimal("0")))  # noqa: E731
    c = p["counters"]
    return {
        "bitis": float(p["bakiye"] + p["net"]), "islem": len(T),
        "kazanma": len(kaz) / len(T) if T else float("nan"),
        "R_kaz": statistics.mean(kaz) if kaz else float("nan"),
        "R_kay": statistics.mean(kay) if kay else float("nan"),
        "brut": D("gross"), "komisyon": D("fees"), "funding": D("funding"), "net": float(p["net"]),
        "k3": f"{k3['pozitif']}/{k3['n']}", "k3_gecti": k3["A1"] and k3["A2"],
        "ob_giris": sum(t.giris == "OB" for t in T),
        "ob_tf": pd.Series([t.ob_tf for t in T if t.giris == "OB"], dtype=object).value_counts().to_dict(),
        "eklemeli": sum(t.adds > 0 for t in T), "ekleme": c.get("adds", 0),
        "maks_dd": p.get("maks_dd"), "likidasyon": p.get("likidasyon"),
    }


def rapor(out: Path) -> None:
    from scripts.bootstrap_fark import N, TOHUM, bloklar, bootstrap

    P = {k: pickle.loads(pkl(k).read_bytes()) for k in KOLLAR}
    O = {k: olc(p) for k, p in P.items()}
    f2 = lambda v: f"{v:+.2f}".replace(".", ",")  # noqa: E731
    s = [f"# #31 ve çıkarma kolları — spec {P['31']['spec_version']}", "",
         f"Kaynak: `scripts/ltf_31.py`, kod `{P['31']['code_version']}`. 20 sembol, eğitim dilimi, "
         "100 USDT, #30 kurgusu (B2 + `son_supuren`, A1+B, K = 0,25, limit, ADD-REJECT-E %3). "
         "Brüt = fiyat PnL'i (slippage içinde), sürtünme = komisyon + funding. R: net PnL / ilk girişin "
         "stopta riski (OB girişinde OB'nin ötesi). Bootstrap: brüt farkı (kol − #31), sembol-ay "
         f"eşleşik, {N:,} yineleme, tohum {TOHUM} (`scripts/bootstrap_fark.py`).", "",
         "| Kol | 100 $ → | İşlem | Kazanma | R kaz. / kayb. | Brüt | Sürtünme | Net | Kriter 3 "
         "| Brüt farkı vs #31 (%95) |", "|---|---:|---:|---:|---|---:|---:|---:|---|---|"]
    b31 = bloklar(pkl("31"))
    for k, (ad, _, _) in KOLLAR.items():
        o = O[k]
        if k == "31":
            fark = "—"
        else:
            r = bootstrap(b31, bloklar(pkl(k)))
            sifir = r["fark_ara"][0] <= 0 <= r["fark_ara"][1]
            fark = (f"{f2(r['fark'])} ({f2(r['fark_ara'][0])} … {f2(r['fark_ara'][1])})"
                    f"{' sıfırı kapsıyor' if sifir else ' **sıfırı kapsamıyor**'}")
        s.append(f"| {ad} | {o['bitis']:.2f} $ | {o['islem']} | %{o['kazanma'] * 100:.1f} | "
                 f"{o['R_kaz']:+.2f} / {o['R_kay']:+.2f} | {f2(o['brut'])} | "
                 f"{o['komisyon'] + o['funding']:.2f} ({o['komisyon']:.2f} + {o['funding']:.2f}) | "
                 f"{f2(o['net'])} | {o['k3']} {'GEÇTİ' if o['k3_gecti'] else 'KALDI'} | {fark} |"
                 .replace(".", ","))
    s += ["", "| Kol | OB girişi | OB dilimi | Eklemeli işlem | Ekleme | Maks DD | Likidasyon | Parmak izi |",
          "|---|---:|---|---:|---:|---:|---:|---|"]
    for k, (ad, _, _) in KOLLAR.items():
        o = O[k]
        s.append(f"| {ad} | {o['ob_giris']} | {o['ob_tf']} | {o['eklemeli']} | {o['ekleme']} | "
                 f"%{(o['maks_dd'] or 0) * 100:.1f} | {o['likidasyon']} | `{P[k]['hash']}` |")
    c = P["31"]["counters"]
    s += ["", "#31 sayaçları (ret): " + ", ".join(f"`{a}` {v}" for a, v in sorted(c.items())
                                               if ("reject" in a or "rejected" in a) and v), ""]
    out.write_text("\n".join(s) + "\n", encoding="utf-8")
    print(out)
    print(json.dumps(O, ensure_ascii=False, indent=1, default=str))


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--hazirla", action="store_true")
    a.add_argument("--kol", choices=list(KOLLAR))
    a.add_argument("--rapor", action="store_true")
    a.add_argument("--out", type=Path, default=Path("docs/measurements/ltf_31.md"))
    x = a.parse_args()
    if x.hazirla:
        hazirla()
    if x.kol:
        kos(x.kol)
    if x.rapor:
        rapor(x.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
