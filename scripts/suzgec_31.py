"""Piyasa süzgeç adayları S1/S2/S3 — #31 üstüne (`docs/adaylar_piyasa.md`, ön kayıt).

    python -m scripts.suzgec_31 --esikler                # eşikleri hesapla → logs/inceleme/suzgec_esikler.pkl
    python -m scripts.bg scripts.suzgec_31 --kol s1s2s3  # her kol ayrı süreç
    python -m scripts.suzgec_31 --rapor --out docs/measurements/suzgec_31.md

Kurgu #31 ile aynı (`scripts/ltf_31.py`); değişen yalnızca üç aday giriş kapısı. Taban #31
(`logs/inceleme/ltf31_31.pkl`) yeniden koşulmaz, doğrudan okunur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.ltf_31 import BAKIYE, VERI, olc, pkl as ltf31_pkl

KOK = Path("logs/inceleme")
ESIKLER = KOK / "suzgec_esikler.pkl"
ETIKET = Path("docs/inceleme/strateji/etiketler.json")

KOLLAR = {
    "s1": ("S1 (belirsiz trend)", True, False, False),
    "s2": ("S2 (düz piyasa)", False, True, False),
    "s3": ("S3 (zayıf zigzag)", False, False, True),
    "s1s2": ("S1+S2", True, True, False),
    "s1s3": ("S1+S3", True, False, True),
    "s2s3": ("S2+S3", False, True, True),
    "s1s2s3": ("S1+S2+S3", True, True, True),
}


def pkl(kol: str) -> Path:
    return KOK / f"suzgec_{kol}.pkl"


# --- eşikler: medyan, veriden — performanstan önce (docs/adaylar_piyasa.md) --


def vol_block_for(ts: np.ndarray, volume: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """S2 · her 1m kapanışı için "düz piyasa" bayrağı.

    `24s hacim < son 30 tam günün günlük hacim medyanı` (günler girişin takvim
    gününden **önceki** 30 gün — bugünü saymaz). Nedensel: NaN karşılaştırması
    `False` olduğu için ilk ~30 günde (medyan hesaplanamaz) bayrak hep kapalı.
    """
    idx = pd.to_datetime(ts)
    vol = pd.Series(volume, index=idx)
    roll24 = vol.rolling("24h").sum()
    gunluk = vol.resample("1D").sum()
    medyan_30 = gunluk.rolling(30, min_periods=1).median().shift(1)
    gun = idx.floor("D")
    esik = medyan_30.reindex(gun).to_numpy()
    blok = (roll24.to_numpy() < esik)  # NaN < x → False (numpy)
    return ts, np.nan_to_num(blok, nan=0.0).astype(bool)


def otuz_dakika_kapanis(sd) -> pd.Series:
    s = pd.Series(sd.close, index=pd.to_datetime(sd.ts))
    return s.resample("30min", closed="left", label="left").last().dropna()


def leg_verimliligi(sd, z, s30: pd.Series) -> float:
    """S3 · `|capa_1 - capa_0| / Σ|30m kapanış farkları|` (capa_0 → capa_1)."""
    a0 = pd.Timestamp(z.anchor_0_time)
    a1 = pd.Timestamp(z.anchor_1_time)
    if a0.tzinfo is not None:
        a0 = a0.tz_localize(None)
    if a1.tzinfo is not None:
        a1 = a1.tz_localize(None)
    sub = s30.loc[a0:a1]
    toplam = sub.diff().dropna().abs().sum()
    if len(sub) < 2 or toplam == 0:
        return 1.0
    return abs(z.anchor_1_price - z.anchor_0_price) / toplam


def hazirla_esikler() -> None:
    data = pickle.loads(VERI.read_bytes())
    vol_block = {sd.symbol: vol_block_for(sd.ts, sd.volume) for sd in data}

    verimlilik: dict[str, float] = {}
    for sd in data:
        s30 = otuz_dakika_kapanis(sd)
        for z in sd.zones:
            verimlilik[z.zone_id] = leg_verimliligi(sd, z, s30)

    medyan = float(np.median(list(verimlilik.values())))
    leg_block = frozenset(zid for zid, v in verimlilik.items() if v <= medyan)

    KOK.mkdir(parents=True, exist_ok=True)
    ESIKLER.write_bytes(pickle.dumps(
        {"vol_block": vol_block, "leg_block": leg_block, "leg_eff_medyan": medyan,
         "leg_eff_n": len(verimlilik)}, pickle.HIGHEST_PROTOCOL))
    print(json.dumps({"leg_eff_medyan": medyan, "zone_sayisi": len(verimlilik),
                      "leg_block_sayisi": len(leg_block)}))


# --- koşu --------------------------------------------------------------------


def kos(kol: str) -> None:
    from scripts.backtest import code_version, spec_version
    from src.backtest.costs import build_cost_model
    from src.backtest.engine import ENTRY_OB_070, Backtest

    ad, s1, s2, s3 = KOLLAR[kol]
    data = pickle.loads(VERI.read_bytes())
    e = pickle.loads(ESIKLER.read_bytes())
    kw = {}
    if s1:
        kw["reject_bias_none"] = True
    if s2:
        kw["vol_block"] = e["vol_block"]
    if s3:
        kw["leg_block"] = e["leg_block"]
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


def kazanan_sembol(p: dict) -> tuple[int, int]:
    net: dict[str, float] = {}
    for t in p["trades"]:
        net[t.symbol] = net.get(t.symbol, 0.0) + float(t.pnl)
    sembol_n = len(p["baslangic"])
    return sum(v > 0 for v in net.values()), sembol_n


# --- madde 3 · 20 etiketli işlemle tutarlılık --------------------------------


def tutarlilik(kol: str) -> dict:
    """20 etiketli işlemin kaçını bu kombinasyon elerdi; kullanıcının kararıyla örtüşme."""
    ad, s1, s2, s3 = KOLLAR[kol]
    e = pickle.loads(ESIKLER.read_bytes())
    etiketler = json.loads(ETIKET.read_text(encoding="utf-8"))
    data = {sd.symbol: sd for sd in pickle.loads(VERI.read_bytes())}
    p31 = pickle.loads(ltf31_pkl("31").read_bytes())
    T = {t.zone_id: t for t in p31["trades"]}

    girmezdim_elendi = girerdim_elendi = 0
    for row in etiketler:
        t = T[row["zone_id"]]
        sd = data[row["symbol"]]
        elendi = False
        if s1 and row["bias_4h"] == "NONE":
            elendi = True
        if s2 and not elendi:
            ts_arr, blok = e["vol_block"][row["symbol"]]
            i = int(np.searchsorted(ts_arr, np.datetime64(pd.Timestamp(t.entry_ts).tz_localize(None)),
                                    side="right")) - 1
            elendi = bool(blok[i]) if i >= 0 else False
        if s3 and not elendi:
            elendi = row["zone_id"] in e["leg_block"]
        if elendi and row["karar"] == "girmezdim":
            girmezdim_elendi += 1
        elif elendi and row["karar"] == "girerdim":
            girerdim_elendi += 1
    return {"girmezdim_elendi": girmezdim_elendi, "girmezdim_toplam": 12,
            "girerdim_elendi": girerdim_elendi, "girerdim_toplam": 8}


# --- rapor -------------------------------------------------------------------


def rapor(out: Path) -> None:
    p31 = pickle.loads(ltf31_pkl("31").read_bytes())
    o31 = olc(p31)
    satirlar = [("#31 (taban)", o31, None)]
    for k, (ad, *_rest) in KOLLAR.items():
        p = pickle.loads(pkl(k).read_bytes())
        satirlar.append((ad, olc(p), tutarlilik(k)))
    satirlar.sort(key=lambda x: -x[1]["net"] if x[0] != "#31 (taban)" else float("inf"))

    f2 = lambda v: f"{v:+.2f}".replace(".", ",")  # noqa: E731
    s = [f"# Piyasa süzgeçleri S1/S2/S3 — #31 üstüne (ön kayıt `docs/adaylar_piyasa.md`)", "",
         f"Kaynak: `scripts/suzgec_31.py`, spec {p31['spec_version']}, kod {p31['code_version']}. "
         "20 sembol, eğitim dilimi, 100 USDT, #31 kurgusu (B2 + `son_supuren`, A1+B, OB/OTE girişi, "
         "ekleme 1-1 × 3, K = 0,25, limit, ADD-REJECT-E %3). Sıralama net PnL'e göre (taban hariç).", "",
         "| Kol | 100 $ → | İşlem | Kazanma | R kaz. / kayb. | Brüt | Sürtünme | Net | Kriter 3 |",
         "|---|---:|---:|---:|---|---:|---:|---:|---|"]
    for ad, o, _ in satirlar:
        s.append(f"| {ad} | {o['bitis']:.2f} $ | {o['islem']} | %{o['kazanma'] * 100:.1f} | "
                 f"{o['R_kaz']:+.2f} / {o['R_kay']:+.2f} | {f2(o['brut'])} | "
                 f"{o['komisyon'] + o['funding']:.2f} ({o['komisyon']:.2f} + {o['funding']:.2f}) | "
                 f"{f2(o['net'])} | {o['k3']} {'GEÇTİ' if o['k3_gecti'] else 'KALDI'} |".replace(".", ","))

    s += ["", "## Madde 3 — 20 etiketli işlemle tutarlılık (kalibrasyon değil, rapor)", "",
          "Kullanıcının 12 \"girmezdim\" ve 8 \"girerdim\"inden kaçını bu kombinasyon elerdi.", "",
          "| Kol | girmezdim elenen (12) | girerdim yanlış elenen (8) |", "|---|---:|---:|"]
    for ad, _, t in satirlar:
        if t is None:
            continue
        s.append(f"| {ad} | {t['girmezdim_elendi']}/12 | {t['girerdim_elendi']}/8 |")

    out.write_text("\n".join(s) + "\n", encoding="utf-8")
    print(out)


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--esikler", action="store_true")
    a.add_argument("--kol", choices=list(KOLLAR))
    a.add_argument("--rapor", action="store_true")
    a.add_argument("--out", type=Path, default=Path("docs/measurements/suzgec_31.md"))
    x = a.parse_args()
    if x.esikler:
        hazirla_esikler()
    if x.kol:
        kos(x.kol)
    if x.rapor:
        rapor(x.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
