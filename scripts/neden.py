"""F1 ayrilmis dilimde neden kaybetti — YALNIZCA ACIKLAYICI, AYAR ICIN DEGIL.

    python -m scripts.bg scripts.neden

Ayrilmis dilim 2026-09-25'te okundu ve harcandi. Bu betik o veriyi **ornek ici** olarak
yeniden kosar; buradan cikan hicbir sayi bir parametreyi, kurali ya da filtreyi
secmek icin kullanilmaz. Amac yalnizca "ne degisti" sorusunu tarif etmek.

**Kosular** (F1 standart, `ayrilmis.py` / `soguk.py` ile ayni kurulum, 2 kume):
egitim (2026-05-08 13:00'e kadar, `soguk.py` F1) ve ayrilmis (`Ayrilmis`, kesim ->
2026-09-11 13:00). Iki kosunun toplamlari raporlanan sayilarla karsilastirilir.

**Ayristirma.** brut/surtunme = b / f, `b` ve `f` islem basina ortalama. Islem sayisi
oranin payinda ve paydasinda ayni anda durur, orani degistiremez; yalnizca net'i
olcekler. `b = p x W + (1 - p) x L` (p: brut-kazanan orani, W/L: kazanan/kaybeden
ortalama brut). Tutarlar donemin ortalama notional'ina bolunur (bps), boylece
equity'nin buyumesiyle gelen boyut farki karsilastirmaya girmez. Slippage islem basina
tutulmaz; toplam slippage islemlere notional'la orantili dagitilir (toplamlar tutar).

**Bekleyen emir.** Ayrilmis kosuda kesimden once `PRIMED` olan (emri kesimden once
konan, `OPEN-41`) ve kesimden sonra dolan zone'lar "eski emir" olarak isaretlenir.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.ayrilmis import KESIM, SON, Ayrilmis
from scripts.levers import olc
from scripts.slippage_stres import F1_TABANI
from scripts.soguk import SOGUK_PATH, kesim_frac
from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun
from src.data import collect

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# Raporlanan sayilar (logs/soguk.txt, logs/ayrilmis.txt) — yeniden kosu bunlari tutmali.
RAPOR = {("ORIJINAL", "egitim"): 2376, ("YENI", "egitim"): 4187,
         ("ORIJINAL", "ayrilmis"): -1287, ("YENI", "ayrilmis"): -851}
out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


class Izli(Ayrilmis):
    """`Ayrilmis` + kesimden once kurulan bekleyen emirlerin zone'larini tutar."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.eski: set[str] = set()

    def _try_fill(self, z, sd, ts, *a, **kw):
        super()._try_fill(z, sd, ts, *a, **kw)
        if z.zone_id in self._girilen and z.primed_at is not None and z.primed_at < self.kesim:
            self.eski.add(z.zone_id)


def islem_df(trades, slip_total: Decimal) -> pd.DataFrame:
    """Islem listesi -> tablo. `slip`: toplam slippage'in notional payi (bkz. modul notu)."""
    d = pd.DataFrame([{
        "symbol": t.symbol, "zone_id": t.zone_id, "entry_ts": pd.Timestamp(t.entry_ts),
        "notional": float(t.entry_price * t.qty), "gross": float(t.gross),
        "fees": float(t.fees), "funding": float(t.funding), "pnl": float(t.pnl),
        "reason": t.reason, "tp1": t.reached_tp1, "leg_pct": t.leg_pct,
    } for t in trades])
    if d.empty:
        return d
    d["slip"] = float(slip_total) * d.notional / d.notional.sum()
    d["b"] = d.gross + d.slip  # slippage disari cikarilmis brut (olc.brut_slipsiz)
    d["f"] = d.fees + d.slip   # surtunme (ayrilmis.py: komisyon + slippage)
    return d


def ozet(d: pd.DataFrame) -> dict:
    """Islem basina olculer; tutarlar donemin ortalama notional'ina gore bps."""
    n = len(d)
    ref = d.notional.mean() / 10_000
    kaz = d.b > 0
    return {
        "n": n, "net": d.pnl.sum(),
        "kazanma": (d.pnl > 0).mean(), "tp1": d.tp1.mean(),
        "stop": (d.reason == "STOP").mean(), "final_tp": (d.reason == "FINAL_TP").mean(),
        "breakeven": (d.reason == "BREAKEVEN").mean(), "run_end": (d.reason == "RUN_END").mean(),
        "leg_pct": d.leg_pct.mean(), "notional": d.notional.mean(),
        "p": kaz.mean(),
        "W": d.b[kaz].mean() / ref if kaz.any() else 0.0,
        "L": d.b[~kaz].mean() / ref if (~kaz).any() else 0.0,
        "b": d.b.mean() / ref, "f": d.f.mean() / ref, "fund": d.funding.mean() / ref,
        "oran": d.b.sum() / d.f.sum(),
    }


def karsi_olgu(e: dict, h: dict) -> dict[str, float]:
    """Egitim oranindan baslayip bir bileseni ayrilmisinkiyle degistirince oran ne olur."""
    def oran(p, W, L, f):
        return (p * W + (1 - p) * L) / f
    return {
        "egitim": oran(e["p"], e["W"], e["L"], e["f"]),
        "yalniz isabet (p)": oran(h["p"], e["W"], e["L"], e["f"]),
        "yalniz buyukluk (W, L)": oran(e["p"], h["W"], h["L"], e["f"]),
        "yalniz surtunme (f)": oran(e["p"], e["W"], e["L"], h["f"]),
        "ayrilmis": oran(h["p"], h["W"], h["L"], h["f"]),
    }


def atr_bps(symbol: str, exchange: str, son: pd.Timestamp) -> pd.Series:
    """30m ATR(14) / kapanis, bps — aylik ortalama."""
    d = collect.read_parquet(exchange, symbol, "30m")
    d = d[d.ts <= son].set_index("ts")
    if d.empty:
        return pd.Series(dtype=float)
    pc = d.close.shift(1)
    tr = np.maximum(d.high - d.low, np.maximum((d.high - pc).abs(), (d.low - pc).abs()))
    atr = tr.rolling(14).mean() / d.close * 10_000
    return atr.groupby(atr.index.strftime("%Y-%m")).mean()


def main() -> int:
    p = argparse.ArgumentParser(description="F1 neden kaybetti (aciklayici)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/neden.txt")
    p.add_argument("--csv", default="logs/neden_islemler.csv")
    a = p.parse_args()
    kesim, son = pd.Timestamp(KESIM, tz="UTC"), pd.Timestamp(SON, tz="UTC")

    from scripts.measure_ob import liquidity_symbols
    sem = {"ORIJINAL": liquidity_symbols(20),
           "YENI": json.loads(SOGUK_PATH.read_text(encoding="utf-8"))["symbols"]}
    kw = dict(k=Decimal("0.25"), mmr=Decimal("0.005"), t_rahat=Decimal("0.50"),
              t_kritik=Decimal("0.08"), uyari_blocks_adds=False,
              progress_every=a.progress_every, **F1_TABANI)

    tablolar: list[pd.DataFrame] = []
    m: dict[tuple[str, str], dict] = {}
    for kume, ss in sem.items():
        for donem in ("egitim", "ayrilmis"):
            data = []
            for s in ss:
                if donem == "egitim" and kume == "ORIJINAL":
                    f = TRAIN_FRAC  # soguk.py ile ayni
                else:
                    f = kesim_frac(s, a.exchange, kesim if donem == "egitim" else son)
                sd = load_symbol(s, a.exchange, f) if f else None
                if sd is not None:
                    data.append(sd)
            reset_for_rerun(data)
            cm = build_cost_model([d.symbol for d in data], a.exchange)
            c0 = time.time()
            print(f"  {kume} {donem} basliyor ({len(data)} sembol)...", file=sys.stderr, flush=True)
            if donem == "egitim":
                bt = Backtest(data, cm, a.balance, **kw)
            else:
                bt = Izli(data, cm, a.balance, kesim=kesim, **kw)
            res = bt.run()
            d = islem_df(res.trades, res.costs.total_slippage)
            d["kume"], d["donem"] = kume, donem
            d["eski"] = d.zone_id.isin(getattr(bt, "eski", set()))
            tablolar.append(d)
            m[kume, donem] = {**ozet(d), "olc": olc(res, a.balance)}
            print(f"  {kume} {donem}: {len(d):,} islem, net {m[kume, donem]['net']:,.0f}, "
                  f"{(time.time() - c0) / 60:.1f} dk", file=sys.stderr, flush=True)

    tum = pd.concat(tablolar, ignore_index=True)
    tum["ay"] = tum.entry_ts.dt.strftime("%Y-%m")
    sutun = [(k, dn) for k in sem for dn in ("egitim", "ayrilmis")]

    say("=" * 100)
    say("F1 · EGITIM vs AYRILMIS · YALNIZCA ACIKLAYICI — AYAR ICIN KULLANILMAZ")
    say("=" * 100)
    say(f"  ayrilmis dilim {kesim:%Y-%m-%d %H:%M} -> {son:%Y-%m-%d %H:%M} UTC · ornek ici (harcandi)")
    say("")
    say("TUTARLILIK (raporlanan net ile)")
    for k in sutun:
        say(f"  {k[0]:<9}{k[1]:<9} rapor {RAPOR[k]:>7,}  yeniden {m[k]['net']:>9,.0f}"
            f"  {'OK' if abs(m[k]['net'] - RAPOR[k]) < 1 else '** FARKLI **'}")

    say("")
    say(f"  {'olcu':<32}" + "".join(f"{f'{k[0][:4]} {k[1]}':>16}" for k in sutun))
    for ad, key, fmt in (
        ("islem", "n", "{:,.0f}"), ("net", "net", "{:,.0f}"),
        ("kazanma orani (net > 0)", "kazanma", "{:.1%}"),
        ("TP1'e ulasma", "tp1", "{:.1%}"), ("cikis: STOP", "stop", "{:.1%}"),
        ("cikis: FINAL_TP", "final_tp", "{:.1%}"), ("cikis: BREAKEVEN", "breakeven", "{:.1%}"),
        ("cikis: RUN_END", "run_end", "{:.1%}"),
        ("ortalama leg buyuklugu", "leg_pct", "{:.2%}"),
        ("ortalama giris notional", "notional", "{:,.0f}"),
    ):
        say(f"  {ad:<32}" + "".join(f"{fmt.format(m[k][key]):>16}" for k in sutun))
    for k in sutun:
        aylar = tum[(tum.kume == k[0]) & (tum.donem == k[1])].ay.value_counts()
        m[k]["aylik"] = aylar.mean()
    say(f"  {'aylik islem (ortalama)':<32}" + "".join(f"{m[k]['aylik']:>16.0f}" for k in sutun))

    say("")
    say("BRUT / SURTUNME AYRISTIRMASI (bps = donemin ortalama giris notional'ina gore)")
    say(f"  {'bilesen':<32}" + "".join(f"{f'{k[0][:4]} {k[1]}':>16}" for k in sutun))
    for ad, key, fmt in (
        ("p  brut-kazanan orani", "p", "{:.1%}"), ("W  kazanan ort. brut (bps)", "W", "{:+.1f}"),
        ("L  kaybeden ort. brut (bps)", "L", "{:+.1f}"), ("b  islem basi brut (bps)", "b", "{:+.2f}"),
        ("f  islem basi surtunme (bps)", "f", "{:.2f}"), ("funding (bps)", "fund", "{:+.2f}"),
        ("brut / surtunme", "oran", "{:.3f}"),
    ):
        say(f"  {ad:<32}" + "".join(f"{fmt.format(m[k][key]):>16}" for k in sutun))
    for kume in sem:
        e, h = m[kume, "egitim"], m[kume, "ayrilmis"]
        say("")
        say(f"  {kume} karsi olgu — egitimden baslayip tek bileseni degistir:")
        for ad, v in karsi_olgu(e, h).items():
            say(f"    {ad:<28} {v:>7.3f}")
        # Net = n x islem basi net. Log-olmayan basit ayristirma: sirayla degistir.
        ne, nh = e["n"], h["n"]
        pe, ph = e["net"] / ne, h["net"] / nh
        say(f"    net: egitim {e['net']:,.0f} = {ne:,} x {pe:+.2f}  ·  ayrilmis {h['net']:,.0f} "
            f"= {nh:,} x {ph:+.2f}")
        say(f"    islem sayisi etkisi (egitim islem basi netiyle) {(nh - ne) * pe:+,.0f} · "
            f"islem basi etki {nh * (ph - pe):+,.0f}")

    say("")
    say("AYLIK — islem · kazanma · net · ATR(30m, bps) · BTC getirisi")
    atr = {}
    for kume, ss in sem.items():
        seriler = [atr_bps(s, a.exchange, son) for s in ss]
        atr[kume] = pd.concat(seriler, axis=1).mean(axis=1)
    btc = collect.read_parquet(a.exchange, "BTC/USDT:USDT", "30m")
    btc = btc[btc.ts <= son].set_index("ts").close
    btc_ay = btc.groupby(btc.index.strftime("%Y-%m")).agg(["first", "last"])
    btc_ret = btc_ay["last"] / btc_ay["first"] - 1
    aylar = sorted(tum.ay.unique())
    say(f"  {'ay':<8}{'donem':<9}" + "".join(f"{k:>30}" for k in sem) + f"{'BTC':>9}")
    for ay in aylar:
        dn = "ayrilmis" if ay >= f"{kesim:%Y-%m}" else "egitim"
        hucre = []
        for kume in sem:
            x = tum[(tum.kume == kume) & (tum.ay == ay)]
            hucre.append(f"{len(x):>4} {(x.pnl > 0).mean() if len(x) else 0:>5.0%} "
                         f"{x.pnl.sum():>7,.0f} {atr[kume].get(ay, float('nan')):>6.1f}")
        say(f"  {ay:<8}{dn:<9}" + "".join(f"{h:>30}" for h in hucre)
            + f"{btc_ret.get(ay, float('nan')):>+9.1%}")
    say("  (2026-05: egitim ve ayrilmis islemleri ayni satirda; donem kesimi 05-08 13:00)")
    for kume in sem:
        for dn in ("egitim", "ayrilmis"):
            x = tum[(tum.kume == kume) & (tum.donem == dn)]
            ay_atr = atr[kume][atr[kume].index.isin(x.ay.unique())]
            m[kume, dn]["atr"] = ay_atr.mean()
    say(f"  ATR ortalamasi (islem olan aylar): " + " · ".join(
        f"{k[0][:4]} {k[1]} {m[k]['atr']:.1f}" for k in sutun))
    eb = btc_ret[btc_ret.index < f"{kesim:%Y-%m}"]
    hb = btc_ret[btc_ret.index > f"{kesim:%Y-%m}"]
    say(f"  BTC aylik getiri |ortalama|: egitim {eb.abs().mean():.1%} · ayrilmis (Haz-Eyl) "
        f"{hb.abs().mean():.1%}")

    say("")
    say("BEKLEYEN EMIR NOTU — kesimden once kurulan, kesimden sonra dolan emirler")
    for kume in sem:
        x = tum[(tum.kume == kume) & (tum.donem == "ayrilmis")]
        e = x[x.eski]
        mayis = x[x.ay == f"{kesim:%Y-%m}"]
        say(f"  {kume}: {len(e)} islem / {len(x)} · net {e.pnl.sum():+,.0f} · "
            f"kazanma {(e.pnl > 0).mean() if len(e) else 0:.0%} · "
            f"ilk dolum {e.entry_ts.min() if len(e) else '-'} · son {e.entry_ts.max() if len(e) else '-'}")
        say(f"    Mayis {mayis.pnl.sum():+,.0f} = eski emir {mayis[mayis.eski].pnl.sum():+,.0f}"
            f" + yeni emir {mayis[~mayis.eski].pnl.sum():+,.0f} · "
            f"eski emirler haric dilim net {x[~x.eski].pnl.sum():+,.0f}")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    tum.drop(columns=["b", "f"]).to_csv(a.csv, index=False)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
