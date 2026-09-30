"""H2 keşif koşusu — 4h unmitige OB, sabit 2R. `docs/HYPOTHESES.md` §8.

    python -m scripts.h2_kesif                 # eğitim dilimi, 20 sembol

**Keşif — onay değil.** Tanım §8.1'de, bu koşudan önce sabitlendi; burada hiçbir değer
ayarlanmaz. İleriye dönük değerlendirme (2026-10-01 → 12-31) aynı `islem` fonksiyonuyla.

Doluş kuralları motorunkiyle aynı: limit (giriş, TP) seviye 1 tick geçilmeden dolmaz,
maker, slippage yok. Stop borsada: mum içinde tetiklenir, taker + slippage, boşlukta açılış.
"""
from __future__ import annotations

import argparse
import heapq
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from scripts.backtest import code_version, spec_version
from src.backtest.costs import build_cost_model
from src.backtest.engine import STOP_LOSS_CAP
from src.backtest.loader import TRAIN_FRAC
from src.data import collect
from src.features.fvg import BULLISH
from src.features.ob import detect_order_blocks

TF = "4h"
RR = 2
BASLANGIC = Decimal("10000")


def dort_saat(d30: pd.DataFrame) -> pd.DataFrame:
    """30m → UTC hizalı 4h. Yalnızca 8 alt mumu tam olan mum (eksik mum uydurulmaz)."""
    g = d30.set_index("ts").resample(TF, origin="epoch", closed="left", label="left")
    d = g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    d = d[g.size() == 8].reset_index()
    return d


@dataclass
class Islem:
    yon: str  # LONG / SHORT
    giris: float
    stop: float
    tp: float
    dolum_i: int
    cikis_i: int
    cikis: float  # slippage'sız ham çıkış fiyatı
    neden: str  # TP / STOP / ACIK


def islem(ob, kapanis: float, tick: float, ts: np.ndarray, o, h, l, c) -> Islem | str:
    """Tek OB'nin işlemi. İşlem yoksa nedeni (str) döner. Saf: 1m dizileri üzerinde.

    `kapanis` = impuls 4h mumunun kapanışı (emrin konduğu an bilinen fiyat).
    """
    long = ob.direction == BULLISH
    giris = ob.top if long else ob.bottom
    stop = ob.bottom - tick if long else ob.top + tick
    r = abs(giris - stop)
    # TP tick ızgarasına, girişten uzağa yuvarlanır (kötümser taraf).
    tp = (np.ceil((giris + RR * r) / tick) * tick if long
          else np.floor((giris - RR * r) / tick) * tick)
    if (kapanis <= giris) if long else (kapanis >= giris):
        return "post_only_red"  # emir anında karşı tarafı alırdı
    bas = int(np.searchsorted(ts, np.datetime64(ob.known_at.tz_convert("UTC").tz_localize(None))))
    temas = (l[bas:] <= giris) if long else (h[bas:] >= giris)
    if not temas.any():
        return "temas_yok"
    i = bas + int(temas.argmax())
    doldu = (l[i] <= giris - tick) if long else (h[i] >= giris + tick)
    if not doldu:
        return "dolmadi"  # ilk temas OB'yi tüketti, emir iptal

    def stop_fiyat(j):
        bosluk = (o[j] <= stop) if long else (o[j] >= stop)
        return float(o[j]) if bosluk else stop

    if (l[i] <= stop) if long else (h[i] >= stop):
        return Islem("LONG" if long else "SHORT", giris, stop, tp, i, i, stop_fiyat(i), "STOP")
    sv = (l[i + 1:] <= stop) if long else (h[i + 1:] >= stop)
    tv = (h[i + 1:] >= tp + tick) if long else (l[i + 1:] <= tp - tick)
    js = i + 1 + int(sv.argmax()) if sv.any() else None
    jt = i + 1 + int(tv.argmax()) if tv.any() else None
    yon = "LONG" if long else "SHORT"
    if js is not None and (jt is None or js <= jt):  # aynı mum → stop (§8)
        return Islem(yon, giris, stop, tp, i, js, stop_fiyat(js), "STOP")
    if jt is not None:
        return Islem(yon, giris, stop, tp, i, jt, tp, "TP")
    return Islem(yon, giris, stop, float(c[-1]), i, len(c) - 1, float(c[-1]), "ACIK")


def sembol_islemleri(s: str, tick: float, frac: float) -> tuple[list[dict], dict]:
    d30 = collect.read_parquet("bingx", s, "30m")
    d30 = d30.iloc[: int(len(d30) * frac)].reset_index(drop=True)
    d1 = collect.read_parquet("bingx", s, "1m")
    d1 = d1[d1.ts <= d30.ts.iloc[-1] + pd.Timedelta("30m")].reset_index(drop=True)
    d4 = dort_saat(d30)
    obs = detect_order_blocks(d4, s, TF)
    kap = dict(zip(d4.ts, d4.close))
    ts = d1.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    o, h, l, c = (d1[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    sayac: dict[str, int] = {"ob": 0}
    out = []
    for ob in obs:
        if not (d1.ts.iloc[0] <= ob.known_at and ob.known_at < d1.ts.iloc[-1]):
            continue  # 1m kapsamı dışı
        sayac["ob"] += 1
        x = islem(ob, kap[ob.impulse_at], tick, ts, o, h, l, c)
        if isinstance(x, str):
            sayac[x] = sayac.get(x, 0) + 1
            continue
        sayac[x.neden] = sayac.get(x.neden, 0) + 1
        out.append({"symbol": s, "ob_id": ob.ob_id, "yon": x.yon, "giris": x.giris,
                    "stop": x.stop, "tp": x.tp, "neden": x.neden, "cikis_ham": x.cikis,
                    "dolum": pd.Timestamp(ts[x.dolum_i], tz="UTC"),
                    "kapanis": pd.Timestamp(ts[x.cikis_i], tz="UTC") + pd.Timedelta("1min")})
    sayac["bas"], sayac["son"] = d1.ts.iloc[0], d1.ts.iloc[-1]
    return out, sayac


def portfoy(islemler: list[dict], costs) -> pd.DataFrame:
    """Doluş sırasıyla boyut (realize equity × L / R), kapanış sırasıyla realize."""
    islemler.sort(key=lambda x: x["dolum"])
    equity, acik, satir = BASLANGIC, [], []
    notional_acik = Decimal("0")
    tepe_kaldirac = 0.0
    for x in islemler:
        while acik and acik[0][0] <= x["dolum"]:
            _, _, net, notional = heapq.heappop(acik)
            equity += net
            notional_acik -= notional
        giris, stop, cik = (Decimal(str(x[k])) for k in ("giris", "stop", "cikis_ham"))
        qty = STOP_LOSS_CAP * equity / abs(giris - stop)
        sgn = 1 if x["yon"] == "LONG" else -1
        taker = x["neden"] == "STOP"
        cik_dolum = costs.fill_price(cik, x["yon"], opening=False) if taker else cik
        slip = abs(cik - cik_dolum) * qty
        brut = sgn * (cik - giris) * qty
        kom = (costs.fee(x["symbol"], qty * giris, "giris", maker=True)
               + costs.fee(x["symbol"], qty * cik_dolum, "cikis", maker=not taker))
        fund = costs.funding_cost(x["symbol"], x["yon"], qty * giris, x["dolum"], x["kapanis"])
        net = brut - slip - kom - fund
        risk = qty * abs(giris - stop)
        heapq.heappush(acik, (x["kapanis"], x["ob_id"], net, qty * giris))
        notional_acik += qty * giris
        tepe_kaldirac = max(tepe_kaldirac, float(notional_acik / equity))
        satir.append({**x, "qty": float(qty), "brut": float(brut), "slippage": float(slip),
                      "komisyon": float(kom), "funding": float(fund), "net": float(net),
                      "R_brut": float(brut / risk), "R_net": float(net / risk)})
    df = pd.DataFrame(satir)
    df.attrs["tepe_kaldirac"] = tepe_kaldirac
    return df


def kriter3(df: pd.DataFrame, bas: pd.Timestamp, son: pd.Timestamp) -> tuple[bool, bool, pd.Series]:
    """Spec §8 kriter 3 (A1, A2). Ay = UTC takvim ayı; dilimde yarısından azı kalan ay sayılmaz."""
    aylik = df.groupby(df.kapanis.dt.tz_convert("UTC").dt.strftime("%Y-%m")).net.sum()
    tam = []
    for ay in aylik.index:
        a0 = pd.Timestamp(ay + "-01", tz="UTC")
        a1 = a0 + pd.offsets.MonthBegin(1)
        gun = (min(a1, son) - max(a0, bas)).total_seconds() / 86400
        if gun >= (a1 - a0).days / 2:
            tam.append(ay)
    a = aylik[tam]
    toplam = a.sum()
    return (bool(len(a)) and (a > 0).mean() >= 0.60,
            toplam > 0 and bool((a <= 0.40 * toplam).all()), a)


def main() -> int:
    p = argparse.ArgumentParser(description="H2 keşif — keşif, onay değil")
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--out", default="logs/h2_kesif")
    a = p.parse_args()
    from scripts.measure_ob import liquidity_symbols
    semboller = a.symbols or liquidity_symbols(20)
    costs = build_cost_model(semboller, "bingx")
    islemler, sayac, bas, son = [], {}, [], []
    for s in semboller:
        x, sy = sembol_islemleri(s, float(costs.fees[s].tick), TRAIN_FRAC)
        islemler += x
        bas.append(sy.pop("bas"))
        son.append(sy.pop("son"))
        for k, v in sy.items():
            sayac[k] = sayac.get(k, 0) + v
        print(f"  {s}: {sy}", file=sys.stderr, flush=True)
    df = portfoy(islemler, costs)
    kapali = df[df.neden != "ACIK"]
    n = len(kapali)
    r = kapali.R_net
    alt = r.mean() - stats.t.ppf(0.975, n - 1) * r.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    brut, surt = df.brut.sum(), (df.komisyon + df.slippage + df.funding).sum()
    a1, a2, aylik = kriter3(df, min(bas), max(son))
    satirlar = [
        "H2 KEŞİF — ONAY DEĞİL (docs/HYPOTHESES.md §8)",
        f"spec_version {spec_version()} · code_version {code_version()}",
        f"dilim: eğitim (30m en eski %{TRAIN_FRAC * 100:.0f}), 1m {min(bas):%Y-%m-%d} → {max(son):%Y-%m-%d}, {len(semboller)} sembol",
        f"OB {sayac['ob']} · post-only red {sayac.get('post_only_red', 0)} · temas yok {sayac.get('temas_yok', 0)} · "
        f"dokundu dolmadı {sayac.get('dolmadi', 0)} · dolan {len(df)} (TP {sayac.get('TP', 0)} · STOP {sayac.get('STOP', 0)} · açık {sayac.get('ACIK', 0)})",
        f"işlem (kapanan) n = {n} · kazanma {(kapali.neden == 'TP').mean():.1%}",
        f"R brüt ort {kapali.R_brut.mean():+.3f} · R net ort {r.mean():+.3f} · sd {r.std(ddof=1):.3f} · "
        f"tek yönlü %97,5 alt sınır {alt:+.3f}",
        f"brüt {brut:+,.0f} · sürtünme {surt:,.0f} (komisyon {df.komisyon.sum():,.0f} · slippage "
        f"{df.slippage.sum():,.0f} · funding {df.funding.sum():+,.0f}, kapsama %{costs.funding_coverage * 100:.0f}) · "
        f"net {df.net.sum():+,.0f} · brüt/sürtünme {brut / surt:+.2f}",
        f"kriter 3: A1 {'GEÇTİ' if a1 else 'KALDI'} ({(aylik > 0).sum()}/{len(aylik)} pozitif ay) · "
        f"A2 {'GEÇTİ' if a2 else 'KALDI'}",
        "aylık net: " + " · ".join(f"{k} {v:+,.0f}" for k, v in aylik.items()),
        f"tepe açık notional / equity {df.attrs['tepe_kaldirac']:.1f}× (sınır uygulanmadı — H2 risk katmanı değil)",
        f"son equity {float(BASLANGIC) + df.net.sum():,.0f} (başlangıç {BASLANGIC})",
    ]
    Path(a.out + ".txt").parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".txt").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    df.to_csv(a.out + ".csv", index=False)
    print("\n".join(satirlar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
