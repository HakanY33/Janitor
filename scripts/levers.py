"""Uc kaldiracin katkisi — salinim tavani, limit emri, gosterge kapisi.

    python -m scripts.bg scripts.levers

`scripts/reconcile.py` salinimin **maliyetini** olctu: brut fiyat PnL'i +%10,7,
kaybin tamami surtunme, komisyonun %58,4'u ekle-kucult salinimindan. Bu betik
"ne kadar" sorusunu "hangi kaldirac ne kadar" sorusuna cevirir.

Kollar **kumulatiftir** — her kol bir oncekinin uzerine tek bir degisiklik koyar,
boylece fark o degisiklige atfedilebilir:

| kol | uzerine koydugu |
|---|---|
| **A** | mevcut hal (referans) |
| **B** | pozisyon omru boyunca en fazla 3 ekleme; kucultme pozisyon basina bir kez |
| **C** | limit emri fiyatlamasi: giris/TP1/TP/ekleme/kucultme maker + sifir slippage |
| **D** | `R-ENTRY-02` (3) kapali: yalnizca OB ve FVG girisleri |

**Uc kol da spec'ten sapar** ve hicbiri varsayilan degildir (CLAUDE.md: spec'te
olmayan davranis uydurulmaz). Olculen sey birer spec adayidir, secim degil:

* B — `R-ADD-01/03` ekleme sayisina sinir koymuyor, `R-ADD-04` her eklemeden sonra
  gecerli. Tavan ve tek-sefer kucultme spec'te **yok**.
* C — `R-ENTRY-02` (1) OB girisi icin "limit emir konabilir" diyor, gerisi icin bir sey
  demiyor; kod bugune kadar **her** kalemi taker saydi (kotumser taraf). Bu kol o
  varsayimi kaldirir: giris, TP1, nihai TP, ekleme ve kucultme limit emridir.
  Dolus kurali muhafazakardir: fiyat seviyeyi **1 tick** gecmeden emir dolmus sayilmaz
  ve sirada onde olma varsayimi yapilmaz. Tick borsadan gelir
  (`data/{exchange}/fees.json`, `scripts.funding --fees-only` yazar).
  Stop, maliyete cekilmis stop, likidasyon, R-RISK-05 kucultmesi ve kosu sonu limit
  **degildir**: taker + slippage kalir.
* D — `R-ENTRY-02` (3) "gosterge yoksa 0.70 temasi gecerli giristir" diyor; bu kol o
  maddeyi kapatir.

Her kol icin uzlastirma yapilir: **kalemler toplami gercek PnL'e esit olmali.**
Esit degilse rapor degil, hata vardir ve betik bunu yuksek sesle soyler.

Ayrilmis %20 hicbir kolda okunmaz.
"""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.backtest import code_version, spec_version
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


# Kol tanimlari: ad, aciklama, motor parametreleri (kumulatif olarak birikir).
KOLLAR = [
    ("A", "mevcut hal (referans)", {}),
    ("B", "+ en fazla 3 ekleme, kucultme bir kez", {"max_adds": 3, "reduce_once": True}),
    ("C", "+ limit emri (maker, 1 tick asim)", {"limit_orders": True}),
    ("D", "+ R-ENTRY-02 (3) kapali", {"require_indicator": True}),
]

IFLAS_ESIKLERI = (0.50, 0.25, 0.10)


def olc(res, balance: Decimal) -> dict:
    """Bir kolun butun sayilari. Brut fiyat PnL'i slippage **disari cikarilmis** hali."""
    pf, c = res.portfolio, res.costs
    slip = c.total_slippage
    brut_slipsiz = sum((t.gross for t in res.trades), Decimal("0")) + slip
    kom = {k[len("komisyon_"):]: v for k, v in c.breakdown.items()
           if k.startswith("komisyon_")}
    kom_top = sum(kom.values(), Decimal("0"))
    funding = c.breakdown.get("funding", Decimal("0"))
    gercek = pf.balance - pf.start_balance
    n_bar = pf.observed_bars or 1
    ko = res.counters
    return {
        "islem": len(res.trades),
        "brut_slipsiz": brut_slipsiz,
        "komisyon": kom_top,
        "kom_kalem": kom,
        "slippage": slip,
        "funding": funding,
        "net": gercek,
        "net_%": gercek / balance * 100,
        # Uzlastirma: kalemler toplami gercek PnL'e esit olmali.
        "uzlasma_farki": brut_slipsiz - slip - kom_top - funding - gercek,
        "maxdd_%": pf.max_drawdown * 100,
        "iflas": {e: pf.ruin_bars[e] / n_bar * 100 for e in IFLAS_ESIKLERI},
        "dolmayan": {
            "giris (hic dokunulmadi)": ko["unfilled"],
            "giris (1 tick gecilmedi)": ko["limit_miss_giris"],
            "ekleme": ko["limit_miss_ekleme"],
            "kucultme": ko["limit_miss_kucultme"],
            "TP (bar)": ko["limit_miss_tp"],
        },
        "adds": ko["adds"],
        "reduces": ko["reduce_events"],
        "add_reject_cap": ko["add_reject_cap"],
        "likidasyon": ko["liquidations"],
        "atlanan_ciplak": ko["no_indicator_skipped"],
        "bitis": pf.balance,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="A/B/C/D kol karsilastirmasi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--terminate", default="none",
                   help="OPEN-29 kapandi, none kalir; baska bir kol icin degistirilir")
    p.add_argument("--max-adds", type=int, default=3, help="B kolu ekleme tavani")
    p.add_argument("--kollar", default="ABCD", help="kosulacak kollar, orn. 'AB'")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/levers.txt")
    p.add_argument("--csv", default="logs/levers.csv")
    a = p.parse_args()

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

    # Kumulatif: her kol oncekinin parametrelerini devralir.
    olculer: dict[str, dict] = {}
    params: dict = {}
    for ad, aciklama, ek in KOLLAR:
        params = {**params, **ek}
        if ad not in a.kollar:
            continue
        if "max_adds" in params:
            params["max_adds"] = a.max_adds
        reset_for_rerun(data)
        c0 = time.time()
        print(f"  kol {ad} ({aciklama}) basliyor...", file=sys.stderr, flush=True)
        res = Backtest(
            data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
            a.t_rahat, a.t_kritik, a.uyari_adds == "evet",
            progress_every=a.progress_every, terminate=a.terminate, **params,
        ).run()
        olculer[ad] = {"aciklama": aciklama, **olc(res, a.balance)}
        print(f"  kol {ad}: {len(res.trades):,} islem, {(time.time() - c0) / 60:.1f} dk",
              file=sys.stderr, flush=True)

    kollar = list(olculer)
    baslik(f"UC KALDIRACIN KATKISI  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr}")
    say(f"  sonlandirma: {a.terminate} - baslangic bakiye {a.balance} - "
        f"B kolu ekleme tavani {a.max_adds}")
    say(f"  yukleme {yukleme / 60:.1f} dk")
    say("")
    for ad, aciklama, _ in KOLLAR:
        if ad in olculer:
            say(f"  {ad} = {aciklama}")

    # --- (0) tick buyuklugu --------------------------------------------------
    # C kolunun "1 tick gecmeden dolmaz" kurali ne kadar bagliyor: adim fiyata gore
    # cok kucukse kural neredeyse hic bagi olmaz ve kolun farki tamamen maker/taker
    # ile slippage'ten gelir. Bu tablo o ayrimi okunur kilar.
    baslik("(0) LIMIT DOLUS KURALININ BAGLAYICILIGI - fiyat adimi baz puan olarak")
    say("  tick bps = borsanin fiyat adimi / son fiyat x 10.000. Kural bu kadarlik bir")
    say("  asim arar; maker-taker farki (3 bps) ve slippage varsayimi (2 bps) ile")
    say("  karsilastirilir.")
    say("")
    _fees = load_fees(a.exchange)
    tickler = sorted(
        ((sd.symbol, float(_fees[sd.symbol].tick), float(sd.close[-1])) for sd in data),
        key=lambda r: -r[1] / r[2],
    )
    say(f"  {'sembol':<22}{'tick':>16}{'son fiyat':>16}{'tick bps':>12}")
    for sym, tick, fiyat in tickler:
        say(f"  {sym:<22}{tick:>16.8f}{fiyat:>16.6f}{tick / fiyat * 10000:>12.3f}")
    bps_list = sorted(t / f * 10000 for _, t, f in tickler)
    say(f"  {'medyan':<22}{'':>32}{bps_list[len(bps_list) // 2]:>12.3f}")

    # --- (a) ana tablo -------------------------------------------------------
    baslik("(a) KOL BASINA PARA - brut fiyat PnL'i, surtunme kalemleri, net")
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
        ("likidasyon", lambda m: f"{m['likidasyon']:,}"),
        ("ekleme", lambda m: f"{m['adds']:,}"),
        ("kucultme", lambda m: f"{m['reduces']:,}"),
        ("ekleme tavanina takilan (bar)", lambda m: f"{m['add_reject_cap']:,}"),
        ("atlanan ciplak giris", lambda m: f"{m['atlanan_ciplak']:,}"),
        ("dolmayan limit (toplam)", lambda m: f"{sum(m['dolmayan'].values()):,}"),
        ("uzlasma farki", lambda m: f"{m['uzlasma_farki']:.2E}"),
    ]
    for ad, f in satirlar:
        say(f"  {ad:<32}" + "".join(f"{f(olculer[k]):>18}" for k in kollar))

    bozuk = [k for k in kollar if abs(olculer[k]["uzlasma_farki"]) > Decimal("0.01")]
    say("")
    if bozuk:
        say(f"  ** UYARI: {', '.join(bozuk)} kolunda kalemler kapanmadi. Rapor degil, hata var. **")
    else:
        say("  (uzlasma farki Decimal bolme artigi; her kolda kalemler kapaniyor)")

    # --- (b) komisyon kalem bazinda -----------------------------------------
    baslik("(b) KOMISYON KALEM BAZINDA - para hangi emirde gitti")
    say("  C ve D kolunda giris/TP/ekleme/kucultme maker, stop ve zorunlu cikislar taker.")
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

    # --- (c) iflas metrigi ---------------------------------------------------
    baslik("(c) IFLAS METRIGI - equity baslangicin altinda gecen bar orani")
    say("  Likidasyon sayaci 0 olabilir ve hesap yine de biter: notional = equity x K")
    say("  oldugu icin pozisyonlar equity ile kuculur ve sifira asimptot olur.")
    say("")
    say(f"  {'esik':<20}" + "".join(f"{k:>18}" for k in kollar))
    for e in IFLAS_ESIKLERI:
        say(f"  {f'baslangicin < %{e * 100:.0f}':<20}"
            + "".join(f"{olculer[k]['iflas'][e]:>17.1f}%" for k in kollar))

    # --- (d) dolmayan limit --------------------------------------------------
    baslik("(d) DOLMAYAN LIMIT - muhafazakar dolus kuralinin kacirdiklari")
    say("  'giris (hic dokunulmadi)' her kolda vardir: hedefe hic gelinmeden zone oldu.")
    say("  Geri kalan satirlar yalnizca limit kolunda dolar: seviyeye dokunuldu ama")
    say("  1 tick asilmadi. 'TP (bar)' bir **bar** sayacidir: ayni acik TP limiti")
    say("  kacirildigi her mumda bir kez sayilir, emir basina degil.")
    say("")
    say(f"  {'kalem':<28}" + "".join(f"{k:>18}" for k in kollar))
    for kal in olculer[kollar[0]]["dolmayan"]:
        say(f"  {kal:<28}" + "".join(f"{olculer[k]['dolmayan'][kal]:>18,}" for k in kollar))
    say(f"  {'TOPLAM':<28}"
        + "".join(f"{sum(olculer[k]['dolmayan'].values()):>18,}" for k in kollar))

    # --- (e) marjinal katki --------------------------------------------------
    baslik("(e) MARJINAL KATKI - her kaldiracin tek basina getirdigi fark")
    say("  Kollar kumulatif oldugu icin fark bir onceki kola gore alinir. Kollar ayri")
    say("  kosulardir: maliyet equity'yi, equity boyutu, boyut risk bolgesini degistirir;")
    say("  islem kumeleri birebir tutmaz ve satirlar birbirinden cikarilmaz.")
    say("")
    say(f"  {'kaldirac':<44}{'d net PnL':>16}{'d komisyon':>16}{'d slippage':>16}"
        f"{'d islem':>12}{'d maxDD':>12}")
    for onceki, simdi in zip(kollar, kollar[1:]):
        o, y = olculer[onceki], olculer[simdi]
        etiket = f"{onceki} -> {simdi}: {y['aciklama']}"
        say(f"  {etiket:<44}"
            f"{y['net'] - o['net']:>16,.2f}{y['komisyon'] - o['komisyon']:>16,.2f}"
            f"{y['slippage'] - o['slippage']:>16,.2f}"
            f"{y['islem'] - o['islem']:>12,}{y['maxdd_%'] - o['maxdd_%']:>11.1f}%")

    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"kol": k, "aciklama": m["aciklama"], "islem": m["islem"],
         "brut_fiyat_pnl": m["brut_slipsiz"], "komisyon": m["komisyon"],
         "slippage": m["slippage"], "funding": m["funding"], "net_pnl": m["net"],
         "net_getiri_%": m["net_%"], "maxdd_%": m["maxdd_%"],
         "likidasyon": m["likidasyon"], "adds": m["adds"], "reduces": m["reduces"],
         "dolmayan_limit": sum(m["dolmayan"].values()),
         **{f"iflas_{int(e * 100)}_%": m["iflas"][e] for e in IFLAS_ESIKLERI},
         **{f"kom_{kal}": m["kom_kalem"].get(kal, Decimal("0")) for kal in kalemler}}
        for k, m in olculer.items()
    ]).to_csv(a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
