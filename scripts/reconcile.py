"""Paranin nereye gittigi — aritmetik uzlastirma, salinim olcumu, iflas metrigi.

    python -m scripts.bg scripts.reconcile --terminate none

**Neden bu betik var.** `bps` metrigi paranin gittigi yeri gostermiyor. Islem basina
-1,88 bps ile 7.413 islem, K=0,25'te kabaca -%35 etmeli; gercek -%99,7. Fark bir
hesap hatasi degil, metrigin sakladigi uc sey: (1) `bps` tabani **tepe** notional'dir,
giris notional'i degil — ekleme tabani buyutur; (2) 13 pozisyon es zamanli acik, yani
equity'nin gordugu kaldirac tek isleminkinin kati; (3) getiri carpimsaldir.

Uc bolum:

* **(a)** Toplam net PnL'i kalemlere ayirir: giris/cikis/ekleme/kucultme komisyonu,
  funding, slippage, brut fiyat PnL'i. **Kalemler toplami gercek PnL'e esit olmali** —
  esit degilse rapor degil, hata vardir ve betik bunu yuksek sesle soyler.
* **(b)** Pozisyon basina ekle-kucult salinimi: tur sayisi, tepe/baslangic notional
  orani, odenen komisyon. Mutlak kaybin ne kadari en cok tur atan %5'ten geliyor.
* **(d)** Iflas metrigi: equity'nin baslangicin %50 / %25 / %10 altinda gecirdigi bar.
  Likidasyon sayaci 0 iken hesabin bitmesi mumkun; o durumda "likide olmadik" yanilticidir.

Ayrilmis %20 okunmaz.
"""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from src.backtest.costs import build_cost_model
from src.backtest.engine import (
    TERMINATION_RULES,
    TRAIN_FRAC,
    Backtest,
    load_symbol,
)

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
    say("=" * 100)
    say(metin)
    say("=" * 100)


def pct(x: Decimal, taban: Decimal) -> str:
    return f"{x / taban * 100:>7.2f}%" if taban else "      -"


def main() -> int:
    p = argparse.ArgumentParser(description="PnL uzlastirmasi + salinim + iflas metrigi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--k", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--t-rahat", type=Decimal, default=Decimal("0.50"))
    p.add_argument("--t-kritik", type=Decimal, default=Decimal("0.08"))
    p.add_argument("--uyari-adds", choices=["evet", "hayir"], default="hayir")
    p.add_argument("--terminate", choices=TERMINATION_RULES, default="none")
    p.add_argument("--progress-every", type=int, default=100_000)
    p.add_argument("--out", default="logs/reconcile.txt")
    p.add_argument("--csv", default="logs/reconcile_trades.csv")
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

    c0 = time.time()
    res = Backtest(data, build_cost_model(isimler, a.exchange), a.balance, a.k, a.mmr,
                   a.t_rahat, a.t_kritik, a.uyari_adds == "evet",
                   progress_every=a.progress_every, terminate=a.terminate).run()
    print(f"  kosu {(time.time() - c0) / 60:.1f} dk", file=sys.stderr, flush=True)

    pf, c, tr = res.portfolio, res.costs, res.trades
    gercek = pf.balance - pf.start_balance

    baslik(f"PARA NEREYE GITTI  spec {spec_version()}  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i - ayrilmis %20 okunmadi")
    say(f"  K={a.k} - T_rahat={a.t_rahat} - T_kritik={a.t_kritik} - "
        f"UYARI eklemeyi engeller={a.uyari_adds} - MMR={a.mmr}")
    say(f"  OPEN-29 sonlandirma: {a.terminate} - baslangic bakiye {a.balance}")
    say(f"  yukleme {yukleme / 60:.1f} dk")

    # --- (a) aritmetik uzlastirma -------------------------------------------
    b = c.breakdown
    # Kalem adlari defterden okunur, elle sayilmaz: motor yeni bir kalem acinca
    # (ornegin limit kolunda `tp_nihai`) burada sessizce duserdi ve uzlastirma
    # tutmazdi. `KALEM` motorun tek kaynagi (src/backtest/engine.py).
    kom = {k[len("komisyon_"):]: v for k, v in b.items() if k.startswith("komisyon_")}
    funding = b.get("funding", Decimal("0"))
    slip = c.total_slippage
    brut_fiyat = sum((t.gross for t in tr), Decimal("0"))   # slippage ICINDE
    brut_slipsiz = brut_fiyat + slip                        # slippage disari cikarildi

    kalemler = [
        ("brut fiyat PnL (slippage'siz)", brut_slipsiz),
        ("slippage (tum kalemler)", -slip),
        *[(f"komisyon - {ad}", -v) for ad, v in sorted(kom.items())],
        ("funding", -funding),
    ]
    toplam = sum(v for _, v in kalemler)

    baslik("(a) ARITMETIK UZLASTIRMA - kalemler toplami gercek PnL'e esit olmali")
    say(f"  {'kalem':<42} {'tutar':>16} {'baslangic bakiyeye':>20}")
    for ad, v in kalemler:
        say(f"  {ad:<42} {v:>16,.2f} {pct(v, a.balance):>20}")
    say(f"  {'-' * 42} {'-' * 16} {'-' * 20}")
    say(f"  {'KALEMLER TOPLAMI':<42} {toplam:>16,.2f} {pct(toplam, a.balance):>20}")
    say(f"  {'GERCEK PnL (bitis - baslangic bakiye)':<42} {gercek:>16,.2f} "
        f"{pct(gercek, a.balance):>20}")
    fark = toplam - gercek
    say(f"  {'FARK':<42} {fark:>16,.2E}")
    if abs(fark) > Decimal("0.01"):
        say("")
        say("  ** UYARI: kalemler kapanmadi. Rapor degil, hata var. **")
    else:
        say("  (fark Decimal bolme artigi; kalemler kapaniyor)")

    say("")
    say("  Komisyon nereye gitti:")
    kom_top = sum(kom.values(), Decimal("0"))
    for ad, v in sorted(kom.items()):
        say(f"    {ad:<12} {v:>14,.2f} {pct(v, kom_top):>9} (komisyonun payi)")
    say(f"    {'TOPLAM':<12} {kom_top:>14,.2f}")

    say("")
    say("  Neden 'islem basina bps x islem sayisi' tutmuyor:")
    n = len(tr) or 1
    ort_giris_notional = sum((t.entry_qty * t.entry_price for t in tr), Decimal("0")) / n
    ort_tepe_notional = sum((t.qty * t.entry_price for t in tr), Decimal("0")) / n
    say(f"    ortalama giris notional                 {ort_giris_notional:>14,.2f}")
    say(f"    ortalama tepe notional (bps tabani)     {ort_tepe_notional:>14,.2f}")
    say(f"    tepe / giris                            "
        f"{ort_tepe_notional / ort_giris_notional if ort_giris_notional else 0:>14,.2f}x")
    say(f"    tepe eszamanli pozisyon                 {max(pf.concurrent_hist, default=0):>14}")
    say("    bps tabani tepe notional'dir; ekleme tabani buyutur ve 'bps x K x islem'")
    say("    hesabi bu buyumeyi ve es zamanliligi gormez.")

    # --- (b) salinim ---------------------------------------------------------
    baslik("(b) EKLE-KUCULT SALINIMI - pozisyon basina")
    tur = np.array([t.reduces for t in tr])
    oran = np.array([float(t.qty / t.entry_qty) if t.entry_qty else 1.0 for t in tr])
    komisyon = np.array([float(t.fees) for t in tr])
    pnl = np.array([float(t.pnl) for t in tr])

    say(f"  {'olcu':<38} {'medyan':>10} {'ortalama':>10} {'p90':>10} {'p99':>10} {'maks':>10}")
    for ad, v in (("ekle-kucult tur sayisi", tur), ("tepe notional / baslangic", oran),
                  ("odenen komisyon", komisyon)):
        say(f"  {ad:<38} {np.median(v):>10.2f} {np.mean(v):>10.2f} "
            f"{np.percentile(v, 90):>10.2f} {np.percentile(v, 99):>10.2f} {np.max(v):>10.2f}")

    say("")
    say("  Tur sayisina gore dagilim:")
    say(f"  {'tur':>6} {'islem':>9} {'pay':>8} {'toplam net':>14} {'ort komisyon':>14} "
        f"{'ort tepe/bas':>14}")
    kovalar = [(0, 0), (1, 1), (2, 3), (4, 9), (10, 10**9)]
    for lo, hi in kovalar:
        m = (tur >= lo) & (tur <= hi)
        if not m.any():
            continue
        etiket = f"{lo}" if lo == hi else (f"{lo}+" if hi > 10**8 else f"{lo}-{hi}")
        say(f"  {etiket:>6} {int(m.sum()):>9,} {m.mean() * 100:>7.1f}% "
            f"{pnl[m].sum():>14,.2f} {komisyon[m].mean():>14,.2f} {oran[m].mean():>14,.2f}")

    say("")
    say("  Mutlak kaybin kaynagi - en cok tur atan %5:")
    esik = np.percentile(tur, 95)
    ust = tur >= esik
    kayip_top = pnl[pnl < 0].sum()
    say(f"    %95 tur esigi                          {esik:>14,.1f} tur")
    say(f"    dilimdeki islem                        {int(ust.sum()):>14,} "
        f"({ust.mean() * 100:.1f}%)")
    say(f"    dilimin net PnL'i                      {pnl[ust].sum():>14,.2f}")
    say(f"    dilimin komisyonu                      {komisyon[ust].sum():>14,.2f} "
        f"({komisyon[ust].sum() / komisyon.sum() * 100:.1f}% tum komisyonun)")
    say(f"    toplam mutlak kayip (negatif islemler) {kayip_top:>14,.2f}")
    dilim_kayip = pnl[ust & (pnl < 0)].sum()
    say(f"    dilimin mutlak kayip payi              {dilim_kayip:>14,.2f} "
        f"({dilim_kayip / kayip_top * 100 if kayip_top else 0:.1f}%)")

    # --- (d) iflas metrigi ---------------------------------------------------
    baslik("(d) IFLAS METRIGI - equity baslangicin ne kadar altinda, ne kadar sure")
    say("  Likidasyon sayaci 0 olabilir ve hesap yine de bitebilir: notional = equity x K")
    say("  oldugu icin pozisyonlar equity ile birlikte kuculur ve sifira asimptot olur.")
    say("  Bu tablo o olumu gorunur kilar.")
    say("")
    n_bar = pf.observed_bars or 1
    say(f"  {'esik':>22} {'bar':>14} {'kosunun pay':>14}")
    for esik_o in (0.50, 0.25, 0.10):
        v = pf.ruin_bars[esik_o]
        say(f"  {f'baslangicin < %{esik_o * 100:.0f}':>22} {v:>14,} "
            f"{v / n_bar * 100:>13.1f}%")
    say(f"  {'toplam bar':>22} {n_bar:>14,}")
    say("")
    say(f"  likidasyon olayi       {res.counters['liquidations']:>10,}")
    say(f"  maks drawdown          {pf.max_drawdown * 100:>10.1f}%")
    say(f"  bitis bakiye           {pf.balance:>10,.2f}")

    pd.DataFrame([{"symbol": t.symbol, "reason": t.reason, "adds": t.adds,
                   "reduces": t.reduces, "entry_qty": t.entry_qty, "max_qty": t.qty,
                   "tepe_bas": float(t.qty / t.entry_qty) if t.entry_qty else 1.0,
                   "fees": t.fees, "funding": t.funding, "gross": t.gross,
                   "pnl": t.pnl, "bars_held": t.bars_held} for t in tr]
                 ).to_csv(a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
