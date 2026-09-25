"""TP yerlesimi — `R-EXIT-01` / `R-EXIT-02` tam seviyede mi, once mi.

    python -m scripts.bg scripts.tp_placement

**Neden.** `docs/measurements/levers.md`: olculen brut edge'in tamami TP'lerin
**temasla** doldugu varsayimindan geliyordu; 1 tick asim arandiginda brut fiyat PnL'i
+1.073'ten -3.661'e dustu ve 2.501 bar boyunca acik bir TP limiti seviyeye dokunup
gecmedi. Bu betik o bulgunun dogrudan sonucunu olcer: **TP nereye konmali.**

Spec `R-EXIT-01` "0.50 seviyesinde", `R-EXIT-02` "`0` seviyesi" diyor ve ikisi de
`SETTLED`. Ama orijinal kural TP'yi "**donusun hemen altina**" koymakti; "hemen"
sayisallasmadigi icin kod tam seviyeyi aldi. Bu bir spec bosludur, ve ustteki bulgu
tam da o bosluga isaret ediyor: seviyeye degip donen fiyat tam seviyedeki limiti
doldurmaz, once konulmus olani doldurur.

Taban **D**'dir (`docs/measurements/levers.md`): `R-ENTRY-02` (3) kapali, limit emri,
ekleme tavani 3, kucultme bir kez. Tek degisken TP yerlesimi:

| kol | TP |
|---|---|
| **D1** | tam seviyede, 1 tick asim kurali (mevcut D — referans) |
| **D2** | seviyenin **0.02 leg** onunde |
| **D3** | seviyenin **0.05 leg** onunde |
| **D4** | temasla tetiklenen **piyasa emri**: taker + slippage, asim aranmaz |

"Onde" = pozisyon yonunde, seviyeye varmadan once. Oteleme fib oraninda yapilir
(`0.50 -> 0.50 + offset`, `0 -> 0 + offset`), yani fiyatta SHORT'ta yukari, LONG'da
asagi gider; ikisi de **erken cikistir**. Kismi TP (`0.50`) ve nihai TP (`0`) ayni
otelemeyi alir. **Giris ve stop dort kolda da aynidir** — tek degisken TP.

`D2`/`D3` spec'ten sapar (`R-EXIT-01/02` tam seviye diyor) ve kod varsayilani degildir.
Olculen sey bir spec adayidir, secim degil (CLAUDE.md).

Ayrilmis %20 hicbir kolda okunmaz.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.levers import IFLAS_ESIKLERI, olc
from src.backtest.costs import build_cost_model, load_fees
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 108)
    say(metin)
    say("=" * 108)


# D tabani — dort kolda da sabit (docs/measurements/levers.md).
D_TABANI = {"require_indicator": True, "limit_orders": True,
            "max_adds": 3, "reduce_once": True}

KOLLAR = [
    ("D1", "tam seviyede, 1 tick asim (referans)", {}),
    ("D2", "seviyenin 0.02 leg onunde", {"tp_offset": 0.02}),
    ("D3", "seviyenin 0.05 leg onunde", {"tp_offset": 0.05}),
    ("D4", "temasla tetiklenen piyasa emri", {"tp_market": True}),
]


def cikis_oranlari(trades) -> dict:
    """TP1'e ulasma ve cikis nedeni dagilimi — TP yerlesiminin dogrudan izi."""
    n = len(trades) or 1
    neden = Counter(t.reason for t in trades)
    return {
        "tp1_%": sum(1 for t in trades if t.reached_tp1) / n * 100,
        **{f"{k}_%": neden.get(k, 0) / n * 100
           for k in ("FINAL_TP", "STOP", "BREAKEVEN", "RUN_END", "DELEVERAGE")},
        "neden": neden,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="TP yerlesimi kollari (D tabani)")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--terminate", default="none")
    p.add_argument("--kollar", default="D1,D2,D3,D4")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/tp_placement.txt")
    p.add_argument("--csv", default="logs/tp_placement.csv")
    a = p.parse_args()

    secili = set(a.kollar.split(","))
    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)

    t0 = time.time()
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        c0 = time.time()
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s:<24} "
              f"{'hazir' if sd is not None else 'ATLANDI':<8} {time.time() - c0:>6.1f} sn",
              file=sys.stderr, flush=True)
    if not data:
        sys.exit("hicbir sembolde 30m + 1m veri yok")
    isimler = [d.symbol for d in data]
    yukleme = time.time() - t0
    print(f"  yukleme {yukleme / 60:.1f} dk", file=sys.stderr, flush=True)

    olculer: dict[str, dict] = {}
    sembol_pnl: dict[str, dict[str, Decimal]] = {}
    for ad, aciklama, ek in KOLLAR:
        if ad not in secili:
            continue
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(
            data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
            a.t_rahat, a.t_kritik, a.uyari_adds == "evet",
            progress_every=a.progress_every, terminate=a.terminate,
            **D_TABANI, **ek,
        ).run()
        olculer[ad] = {"aciklama": aciklama, **olc(res, a.balance),
                       **cikis_oranlari(res.trades)}
        per = defaultdict(lambda: Decimal("0"))
        adet: Counter = Counter()
        for t in res.trades:
            per[t.symbol] += t.pnl
            adet[t.symbol] += 1
        sembol_pnl[ad] = {"pnl": dict(per), "adet": adet}
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    kollar = list(olculer)
    baslik(f"TP YERLESIMI  (R-EXIT-01/02)  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say(f"  TABAN = D: R-ENTRY-02 (3) kapali - limit emri - ekleme tavani 3 - "
        f"kucultme bir kez")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr} - sonlandirma {a.terminate}")
    say(f"  giris ve stop dort kolda da ayni; tek degisken TP yerlesimi")
    say(f"  yukleme {yukleme / 60:.1f} dk")
    say("")
    for ad, aciklama, _ in KOLLAR:
        if ad in olculer:
            say(f"  {ad} = TP {aciklama}")

    # --- (a) ana tablo -------------------------------------------------------
    baslik("(a) KOL BASINA PARA VE CIKIS DAGILIMI")
    say("  Brut fiyat PnL'i slippage **disari cikarilmis** haldir; slippage ayri satirda.")
    say("")
    say(f"  {'olcu':<32}" + "".join(f"{k:>18}" for k in kollar))
    satirlar = [
        ("islem sayisi", lambda m: f"{m['islem']:,}"),
        ("brut fiyat PnL", lambda m: f"{m['brut_slipsiz']:,.2f}"),
        ("komisyon", lambda m: f"{m['komisyon']:,.2f}"),
        ("slippage", lambda m: f"{m['slippage']:,.2f}"),
        ("funding", lambda m: f"{m['funding']:,.2f}"),
        ("NET PnL", lambda m: f"{m['net']:,.2f}"),
        ("net getiri", lambda m: f"{m['net_%']:.1f}%"),
        ("bitis bakiye", lambda m: f"{m['bitis']:,.2f}"),
        ("maks drawdown", lambda m: f"{m['maxdd_%']:.1f}%"),
        ("", lambda m: ""),
        ("TP1'e ulasan", lambda m: f"{m['tp1_%']:.1f}%"),
        ("nihai TP ile kapanan", lambda m: f"{m['FINAL_TP_%']:.1f}%"),
        ("stop ile kapanan", lambda m: f"{m['STOP_%']:.1f}%"),
        ("breakeven ile kapanan", lambda m: f"{m['BREAKEVEN_%']:.1f}%"),
        ("kosu sonunda acik kalan", lambda m: f"{m['RUN_END_%']:.1f}%"),
        ("", lambda m: ""),
        ("dolmayan TP limiti (bar)", lambda m: f"{m['dolmayan']['TP (bar)']:,}"),
        ("dolmayan limit (toplam)", lambda m: f"{sum(m['dolmayan'].values()):,}"),
        ("likidasyon", lambda m: f"{m['likidasyon']:,}"),
        ("uzlasma farki", lambda m: f"{m['uzlasma_farki']:.2E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<32}" + "".join(f"{f(olculer[k]):>18}" for k in kollar))

    bozuk = [k for k in kollar if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    say("")
    say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. **" if bozuk
        else "  (uzlasma farki Decimal bolme artigi; her kolda kalemler kapaniyor)")

    # --- (b) komisyon kalem bazinda -----------------------------------------
    baslik("(b) KOMISYON KALEM BAZINDA")
    say("  D4'te tp1 ve tp_nihai taker (piyasa emri); digerlerinde maker. Giris, ekleme,")
    say("  kucultme dort kolda da maker; stop ve breakeven dort kolda da taker.")
    say("")
    kalemler = sorted({k for m in olculer.values() for k in m["kom_kalem"]})
    say(f"  {'kalem':<20}" + "".join(f"{k:>18}" for k in kollar)
        + "".join(f"{k + ' pay':>12}" for k in kollar))
    for kal in kalemler:
        v = [olculer[k]["kom_kalem"].get(kal, Decimal("0")) for k in kollar]
        pay = [f"{x / olculer[k]['komisyon'] * 100:.1f}%" if olculer[k]["komisyon"] else "-"
               for x, k in zip(v, kollar)]
        say(f"  {kal:<20}" + "".join(f"{x:>18,.2f}" for x in v)
            + "".join(f"{x:>12}" for x in pay))
    say(f"  {'TOPLAM':<20}" + "".join(f"{olculer[k]['komisyon']:>18,.2f}" for k in kollar))
    say("")
    say(f"  {'slippage (toplam)':<20}" + "".join(f"{olculer[k]['slippage']:>18,.2f}"
                                                 for k in kollar))

    # --- (c) iflas metrigi ---------------------------------------------------
    baslik("(c) IFLAS METRIGI - equity baslangicin altinda gecen bar orani")
    say(f"  {'esik':<20}" + "".join(f"{k:>18}" for k in kollar))
    for e in IFLAS_ESIKLERI:
        say(f"  {f'baslangicin < %{e * 100:.0f}':<20}"
            + "".join(f"{olculer[k]['iflas'][e]:>17.1f}%" for k in kollar))

    # --- (d) sembol bazinda --------------------------------------------------
    # En iyi kol D1'in kendisi cikarsa ikinci sutun **ikinci en iyi** olur: tek
    # sutunlu bir tablo "yogunlasma kola gore degisiyor mu" sorusunu cevaplayamaz.
    sirali = sorted(kollar, key=lambda k: -olculer[k]["net"])
    en_iyi = sirali[0]
    karsilastirma = ["D1", en_iyi if en_iyi != "D1" else sirali[1]] if "D1" in kollar         else sirali[:2]
    baslik(f"(d) SEMBOL BAZINDA NET PnL - en iyi kol {en_iyi}; sutunlar {', '.join(karsilastirma)}")
    say("  Soru: kayip birkac yuksek-tick sembolde mi yogunlasiyor. `tick bps` = borsanin")
    say("  fiyat adimi / son fiyat x 10.000; limit doluş kurali bu kadarlik asim arar.")
    say("  Cross marjin: sembol PnL'leri toplami hesabin net PnL'ine esittir, ama sembolun")
    say("  **boyutu** o anki portfoy equity'sinden gelir - semboller birbirini tasir.")
    say("")
    fees = load_fees(a.exchange)
    tick_bps = {sd.symbol: float(fees[sd.symbol].tick) / float(sd.close[-1]) * 10000
                for sd in data}
    say(f"  {'sembol':<22}{'tick bps':>10}"
        + "".join(f"{k + ' net':>16}{k + ' islem':>12}" for k in karsilastirma))
    for sym in sorted(tick_bps, key=lambda x: -tick_bps[x]):
        say(f"  {sym:<22}{tick_bps[sym]:>10.3f}"
            + "".join(f"{sembol_pnl[k]['pnl'].get(sym, Decimal('0')):>16,.2f}"
                      f"{sembol_pnl[k]['adet'].get(sym, 0):>12,}"
                      for k in karsilastirma))
    say(f"  {'TOPLAM':<22}{'':>10}"
        + "".join(f"{sum(sembol_pnl[k]['pnl'].values(), Decimal('0')):>16,.2f}"
                  f"{sum(sembol_pnl[k]['adet'].values()):>12,}" for k in karsilastirma))

    say("")
    say("  En agir sembol ve onsuz tablo - dilim ortalamasi tek bir aykiriyi gizler:")
    say(f"  {'kol':<10}{'toplam net':>16}{'en agir sembol':>18}{'payi':>10}"
        f"{'o sembolsuz':>16}{'kazanan':>10}{'tick-PnL sira r':>18}")
    import numpy as _np
    _tickler = [tick_bps[s_] for s_ in tick_bps]
    for k in kollar:
        v = {s_: float(sembol_pnl[k]["pnl"].get(s_, Decimal("0"))) for s_ in tick_bps}
        top = sum(v.values())
        agir = min(v, key=v.get)
        r = float(_np.corrcoef(
            _np.argsort(_np.argsort(_tickler)),
            _np.argsort(_np.argsort([v[s_] for s_ in tick_bps])))[0, 1])
        say(f"  {k:<10}{top:>16,.2f}{agir.split('/')[0]:>18}"
            f"{v[agir] / top * 100 if top else 0:>9.1f}%{top - v[agir]:>16,.2f}"
            f"{sum(1 for x in v.values() if x > 0):>8}/{len(v):<2}{r:>+18.2f}")
    say("  `tick-PnL sira r` = fiyat adimi ile net PnL arasinda Spearman sira korelasyonu.")
    say("  Sifira yakin deger 'kayip yuksek-tick sembollerde' tezini desteklemez.")

    say("")
    say("  Yogunlasma: yuksek-tick yarisi (medyanin ustu) vs dusuk-tick yarisi")
    sirali = sorted(tick_bps, key=lambda x: -tick_bps[x])
    ust, alt = sirali[:len(sirali) // 2], sirali[len(sirali) // 2:]
    say(f"  {'dilim':<22}{'sembol':>10}"
        + "".join(f"{k + ' net':>16}{k + ' pay':>12}" for k in karsilastirma))
    for etiket, dilim in (("yuksek tick", ust), ("dusuk tick", alt)):
        hucreler = ""
        for k in karsilastirma:
            v = sum((sembol_pnl[k]["pnl"].get(s_, Decimal("0")) for s_ in dilim),
                    Decimal("0"))
            top = sum(sembol_pnl[k]["pnl"].values(), Decimal("0"))
            hucreler += f"{v:>16,.2f}" + (f"{v / top * 100:>11.1f}%" if top else f"{'-':>12}")
        say(f"  {etiket:<22}{len(dilim):>10}" + hucreler)

    # --- (e) marjinal katki --------------------------------------------------
    baslik("(e) D1'E GORE FARK")
    say("  Kollar ayri kosulardir: TP yerlesimi equity yolunu degistirir, equity boyutu")
    say("  (R-ENTRY-03), boyut risk bolgesini (R-RISK-05). Islem kumeleri birebir tutmaz.")
    say("")
    if "D1" in olculer:
        d1 = olculer["D1"]
        say(f"  {'kol':<40}{'d net PnL':>16}{'d brut':>16}{'d komisyon':>14}"
            f"{'d TP1 orani':>14}{'d stop orani':>14}")
        for k in kollar:
            if k == "D1":
                continue
            m = olculer[k]
            etiket = f"{k}: TP {m['aciklama']}"
            say(f"  {etiket:<40}"
                f"{m['net'] - d1['net']:>16,.2f}{m['brut_slipsiz'] - d1['brut_slipsiz']:>16,.2f}"
                f"{m['komisyon'] - d1['komisyon']:>14,.2f}"
                f"{m['tp1_%'] - d1['tp1_%']:>13.1f}p{m['STOP_%'] - d1['STOP_%']:>13.1f}p")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"kol": k, "aciklama": m["aciklama"], "islem": m["islem"],
         "brut_fiyat_pnl": m["brut_slipsiz"], "komisyon": m["komisyon"],
         "slippage": m["slippage"], "funding": m["funding"], "net_pnl": m["net"],
         "net_getiri_%": m["net_%"], "maxdd_%": m["maxdd_%"],
         "tp1_%": m["tp1_%"], "final_tp_%": m["FINAL_TP_%"], "stop_%": m["STOP_%"],
         "breakeven_%": m["BREAKEVEN_%"], "run_end_%": m["RUN_END_%"],
         "dolmayan_tp_bar": m["dolmayan"]["TP (bar)"],
         **{f"iflas_{int(e * 100)}_%": m["iflas"][e] for e in IFLAS_ESIKLERI},
         **{f"kom_{kal}": m["kom_kalem"].get(kal, Decimal("0")) for kal in kalemler}}
        for k, m in olculer.items()
    ]).to_csv(a.csv, index=False)
    pd.DataFrame([
        {"kol": k, "symbol": sym, "tick_bps": tick_bps[sym],
         "net_pnl": sembol_pnl[k]["pnl"].get(sym, Decimal("0")),
         "islem": sembol_pnl[k]["adet"].get(sym, 0)}
        for k in kollar for sym in tick_bps
    ]).to_csv(a.csv.replace(".csv", "_sembol.csv"), index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
