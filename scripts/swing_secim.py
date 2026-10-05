"""Swing adayı seçimi — `docs/inceleme/v2/adaylar.md` ön kaydının uygulaması.

    python -m scripts.swing_secim              # etiket doğrulama + 7 aday-değer → docs/inceleme/v3/swing_secim.md
    python -m scripts.bg scripts.swing_secim --kos B3 --ek _v08   # seçilenle F1/100 USDT koşusu
    python -m scripts.swing_secim --eslestirme son_supuren --adaylar B2,B3 --out docs/inceleme/v3/swing_secim_son_supuren.md

Tanımlar, ızgaralar ve ölçüt ön kayıttaki gibi (etiketler görülmeden yazıldı, değişmez).
Etiketler `docs/inceleme/v3/etiketler.json`. Leg seçimi (`zones_from_swings`) ve izleme öncesi
eleme (`izleme_oncesi_oldu`, R-ZONE-05) mevcut koddan; değişen yalnızca swing listesi.

**Yorumlar** (ön kayıt metni tek başına yetmiyordu, en dar okuma seçildi):

- C'nin "pencere içinde daha önce kabul edilmiş swing" ifadesi C'nin kendi listesi olursa
  ilk swing hiçbir şeyi aşamaz ve liste boş kalır. Likidite = **mevcut tanımın** (`N = 2`,
  `0.5 × ATR`) swing'leri; `[i − L, i)` içinde biri aşılmış olmalı. C'de yer değiştirme filtresi yok.
- B ve C'de `label`/`swept` `detect_swings` ile aynı: önceki aynı tip swing'e göre.
- D: 4h swing'in fiyatı ve teyidi 4h'tan; zamanı, o 4h içinde ucu üreten ilk 30m mum.
- Etiket: `setup_yok` seçili ama çapası olan b03/b04 setup sayılır (kullanıcının v2 notu:
  "yapı var, hazır değil"). `bot_dogru` → botun çapaları.
- Yanlış alarm: setup yok etiketli anda, adayın `known_at ≤ karar` olan, `watch_from` → karar
  arasında `0`/`1`'e değilmemiş bir zone'unun `0.70–0.79` bandına karar mumu (karar anında
  açılan 1m) temas ediyor mu.
- 0.50 teması etiketli leg'de `1` mumunun kapanışından sonraki ilk 1m mumu; eğitim dilimi
  içinde yoksa son tarih yok sayılır (ayrılmış dilim okunmaz) ve raporda sayılır.
"""
from __future__ import annotations

import argparse
import json
import pickle
import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from src.features.ids import stable_id
from src.features.structure import HIGH, LOW, Swing, atr, detect_swings
from src.zones.detect import ESLESTIRME, izleme_oncesi_oldu, pencerede_050, zones_from_swings

ETIKET = Path("docs/inceleme/v3/etiketler.json")
OUT = Path("docs/inceleme/v3/swing_secim.md")
TF = pd.Timedelta("30m")
M1 = pd.Timedelta("1m")
YAKIN = 2 * TF  # ±2 mum eşleşme
SETUP_SAY = {"b03", "b04"}  # setup_yok seçili ama yapı var (v2 notu)
ESIT = 2  # seçim kuralı: ≤ 2 işlem fark eşit
TIP = {HIGH: "tepe", LOW: "dip"}


# --- adaylar ----------------------------------------------------------------

def _etiketle(ham: list[tuple[int, str, float, int]], df: pd.DataFrame, symbol: str,
              aday: str) -> list[Swing]:
    """(pivot i, tip, fiyat, teyit j) → Swing; `label`/`swept` `detect_swings` ile aynı kural."""
    ts = df.ts.to_numpy()
    son: dict[str, Swing] = {}
    out = []
    for i, kind, price, j in ham:
        o = son.get(kind)
        swept = o is not None and (price > o.price if kind == HIGH else price < o.price)
        label = None if o is None else (("HH" if swept else "LH") if kind == HIGH
                                        else ("LL" if swept else "HL"))
        s = Swing(swing_id=stable_id("swing", symbol, aday, kind, ts[i]), symbol=symbol,
                  timeframe="30m", kind=kind, price=price, ts=pd.Timestamp(ts[i]),
                  pivot_confirmed_at=pd.Timestamp(ts[j]), label=label, swept=swept)
        out.append(s)
        son[kind] = s
    return out


def aday_a(df, symbol, n):
    """A · büyük fraktal, `N` ∈ {6, 12}; yer değiştirme filtresi aynı."""
    return detect_swings(df, symbol, "30m", n=n)


def aday_b(df, symbol, k):
    """B · ATR zigzag: koşan uçtan `k × ATR(14)` geri çekilme uçu swing yapar, yön döner.

    Teyit = geri çekilmenin gerçekleştiği mum. Aynı mumda yeni uç ve geri çekilme varsa
    yalnızca uç güncellenir (mum içi sıra bilinmez).
    """
    a, h, l = atr(df).to_numpy(), df.high.to_numpy(), df.low.to_numpy()
    ham, yon, hi, lo = [], None, None, None
    for j in range(len(df)):
        if np.isnan(a[j]):
            continue
        if yon is None:
            hi = j if hi is None or h[j] > h[hi] else hi
            lo = j if lo is None or l[j] < l[lo] else lo
            if hi < j and l[j] <= h[hi] - k * a[j]:
                ham.append((hi, HIGH, float(h[hi]), j)); yon = "D"
                lo = hi + 1 + int(np.argmin(l[hi + 1:j + 1]))
            elif lo < j and h[j] >= l[lo] + k * a[j]:
                ham.append((lo, LOW, float(l[lo]), j)); yon = "U"
                hi = lo + 1 + int(np.argmax(h[lo + 1:j + 1]))
        elif yon == "U":
            if h[j] > h[hi]:
                hi = j
            elif l[j] <= h[hi] - k * a[j]:
                ham.append((hi, HIGH, float(h[hi]), j)); yon = "D"
                lo = hi + 1 + int(np.argmin(l[hi + 1:j + 1]))
        else:
            if l[j] < l[lo]:
                lo = j
            elif h[j] >= l[lo] + k * a[j]:
                ham.append((lo, LOW, float(l[lo]), j)); yon = "U"
                hi = lo + 1 + int(np.argmax(h[lo + 1:j + 1]))
    return _etiketle(ham, df, symbol, f"B{k}")


def aday_c(df, symbol, L, M=4):
    """C · `[i − L, i + M]` penceresinin tek ucu **ve** `[i − L, i)` içinde bir taban swing'i aşmış."""
    h, l = df.high.to_numpy(), df.low.to_numpy()
    ts_ns = df.ts.dt.tz_convert(None).to_numpy()
    taban = detect_swings(df, symbol, "30m")
    t_ns = np.array([s.ts.tz_convert(None).to_datetime64() for s in taban]).astype(ts_ns.dtype)
    t_kind = np.array([s.kind for s in taban])
    t_fiyat = np.array([s.price for s in taban])
    tmax = pd.Series(h).rolling(L + M + 1, min_periods=1).max().to_numpy()
    tmin = pd.Series(l).rolling(L + M + 1, min_periods=1).min().to_numpy()
    ham = []
    for i in range(L, len(df) - M):
        p = slice(i - L, i + M + 1)
        for kind, arr, uc, aşti in ((HIGH, h, tmax, np.greater), (LOW, l, tmin, np.less)):
            if arr[i] != uc[i + M] or (arr[p] == arr[i]).sum() != 1:
                continue
            m = (t_kind == kind) & (t_ns >= ts_ns[i - L]) & (t_ns < ts_ns[i]) & aşti(arr[i], t_fiyat)
            if m.any():
                ham.append((i, kind, float(arr[i]), i + M))
                break  # _raw_pivots gibi: aynı mumda tek swing
    return _etiketle(ham, df, symbol, f"C{L}")


def aday_d(df, symbol):
    """D · mevcut tanım 4h mumlarında; çapa fiyatı 4h ucu, zamanı o ucu üreten 30m mum."""
    h4 = (df.set_index("ts").resample("4h", closed="left", label="left")
          .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
               close=("close", "last"), volume=("volume", "sum"), n=("close", "size"))
          .dropna().reset_index())
    h4 = h4[h4.ts + pd.Timedelta("4h") <= df.ts.iloc[-1] + TF]  # kısmi son 4h mumu yok
    out = []
    for s in detect_swings(h4, symbol, "4h"):
        p = df[(df.ts >= s.ts) & (df.ts < s.ts + pd.Timedelta("4h"))]
        t30 = p.ts.iloc[int(np.argmax(p.high.to_numpy()) if s.kind == HIGH
                            else np.argmin(p.low.to_numpy()))]
        out.append(Swing(swing_id=stable_id("swing", symbol, "D", s.kind, t30), symbol=symbol,
                         timeframe="30m", kind=s.kind, price=s.price, ts=t30,
                         # known_at = pivot_confirmed_at + 30m = 4h teyit mumunun kapanışı
                         pivot_confirmed_at=s.known_at - TF, label=s.label, swept=s.swept))
    return out


ADAYLAR = {
    "A6": lambda d, s: aday_a(d, s, 6), "A12": lambda d, s: aday_a(d, s, 12),
    "B2": lambda d, s: aday_b(d, s, 2), "B3": lambda d, s: aday_b(d, s, 3),
    "C96": lambda d, s: aday_c(d, s, 96), "C336": lambda d, s: aday_c(d, s, 336),
    "D": aday_d,
}


def zonlar(df, symbol, swings, eslestirme: str = ESLESTIRME):
    """`detect_zones`'un gövdesi, swing listesi dışarıdan. `eslestirme`: R-ZONE-10 `anchor_0` seçeneği."""
    zs = [z for z in zones_from_swings(swings, symbol, "30m", eslestirme=eslestirme)
          if not izleme_oncesi_oldu(z, df)]
    for z in zs:
        z.pencere_050 = pencerede_050(z, df)
    return zs


# --- etiketler ---------------------------------------------------------------

@dataclass
class Capa:
    ts: pd.Timestamp
    tip: str  # tepe | dip
    fiyat: float


def capalar(r) -> tuple[Capa, Capa] | None:
    if r["secim"] == "bot_dogru":
        a, b = r["bot_0"], r["bot_1"]
        t0 = "tepe" if a["fiyat"] > b["fiyat"] else "dip"
        return (Capa(pd.Timestamp(a["ts"], unit="s", tz="UTC"), t0, a["fiyat"]),
                Capa(pd.Timestamp(b["ts"], unit="s", tz="UTC"), "dip" if t0 == "tepe" else "tepe",
                     b["fiyat"]))
    if r["secim"] == "farkli" or (r["secim"] == "setup_yok" and r["id"] in SETUP_SAY):
        return tuple(Capa(pd.Timestamp(r[k]["ts"], unit="s", tz="UTC"), r[k]["tip"], r[k]["fiyat"])
                     for k in ("capa_0", "capa_1"))
    return None


def veri(symbol):
    from src.backtest.loader import TRAIN_FRAC
    from src.data import collect
    d30 = collect.read_parquet("bingx", symbol, "30m")
    d30 = d30.iloc[: int(len(d30) * TRAIN_FRAC)].reset_index(drop=True)
    d1 = collect.read_parquet("bingx", symbol, "1m")
    return d30, d1[d1.ts < d30.ts.iloc[-1] + TF].reset_index(drop=True)


def ilk_050(d1, c0: Capa, c1: Capa):
    """Etiketli leg'de `1` mumu kapandıktan sonraki ilk 0.50 teması (1m açılışı) ya da None."""
    l050 = (c0.fiyat + c1.fiyat) / 2
    p = d1[d1.ts >= c1.ts + TF]
    m = (p.low <= l050) if c1.tip == "tepe" else (p.high >= l050)
    return p.ts[m].iloc[0] if m.any() else None


def dogrula(r, c0: Capa, c1: Capa, d30, d1) -> dict:
    """Adım 2: yerel uç (±2 mumda daha uç mum) + `1` → karar arasında R-ZONE-05 ölümü."""
    out = {}
    for ad, c in (("0", c0), ("1", c1)):
        i = int(d30.ts.searchsorted(c.ts))
        assert d30.ts.iloc[i] == c.ts, (r["id"], ad)
        p = d30.iloc[max(0, i - 2): i + 3]
        daha = p[p.high > c.fiyat] if c.tip == "tepe" else p[p.low < c.fiyat]
        out[ad] = [(t.strftime("%m-%d %H:%M"), v) for t, v in
                   zip(daha.ts, daha.high if c.tip == "tepe" else daha.low)]
    karar = pd.Timestamp(r["karar_ts"], tz="UTC")
    p = d1[(d1.ts >= c1.ts + TF) & (d1.ts + M1 <= karar)]
    if c1.tip == "tepe":
        m0, m1 = p.low <= c0.fiyat, p.high >= c1.fiyat
    else:
        m0, m1 = p.high >= c0.fiyat, p.low <= c1.fiyat
    out["olum"] = [(k, p.ts[m].iloc[0]) for k, m in (("0", m0), ("1", m1)) if m.any()]
    return out


def eslesir(t, kind_tip, c: Capa) -> bool:
    return kind_tip == c.tip and abs(pd.Timestamp(t) - c.ts) <= YAKIN


def z_tip0(z) -> str:
    return "tepe" if z.anchor_0_price > z.anchor_1_price else "dip"


def alarm(zs, d1, karar) -> bool:
    """Karar anında bantta (0.70–0.79) canlı bir zone var mı."""
    bar = d1[d1.ts == karar]
    if bar.empty:
        return False
    lo, hi = float(bar.low.iloc[0]), float(bar.high.iloc[0])
    for z in zs:
        if z.known_at > karar:
            continue
        b0, b1 = sorted((z.level_070, z.level_079))
        if hi < b0 or lo > b1:
            continue
        p = d1[(d1.ts >= z.watch_from) & (d1.ts < karar)]
        if z.bias == "SHORT":
            olu = (p.low <= z.anchor_0_price).any() or (p.high >= z.anchor_1_price).any()
        else:
            olu = (p.high >= z.anchor_0_price).any() or (p.low <= z.anchor_1_price).any()
        if not olu:
            return True
    return False


def degerlendir(eslestirme: str = ESLESTIRME, adaylar: list[str] | None = None,
                out: Path = OUT) -> str:
    """Ön kayıt ölçütleri + seçim kuralı. `adaylar` verilmezse yedisi; `eslestirme` R-ZONE-10 seçeneği."""
    E = json.loads(ETIKET.read_text(encoding="utf-8"))
    semboller = sorted({r["symbol"] for r in E})
    V = {s: veri(s) for s in semboller}
    satir = [f"# Swing seçimi — v3 etiketleri · eşleştirme `{eslestirme}`", "",
             f"Kaynak: `scripts/swing_secim.py --eslestirme {eslestirme}`, `{ETIKET.as_posix()}` "
             f"({len(E)} an). Ön kayıt `docs/inceleme/v2/adaylar.md` (ölçüt değiştirilmedi). "
             "Yorumlar betiğin başında.", ""]

    # --- adım 2: doğrulama
    setup = [(r, capalar(r)) for r in E if capalar(r)]
    yok = [r for r in E if not capalar(r)]
    satir += ["## 1 · Etiket doğrulama", "",
              f"Setup'lı **{len(setup)}** (b03, b04 dahil), setup yok **{len(yok)}** "
              f"({', '.join(r['id'] for r in yok)}).", "",
              "| an | sembol | karar | 0 | 1 | 0: ±2 mumda daha uç | 1: ±2 mumda daha uç | `1` → karar R-ZONE-05 |",
              "|---|---|---|---|---|---|---|---|"]
    olu_say, uc_say, kontrol = 0, 0, {}
    for r, (c0, c1) in setup:
        d30, d1 = V[r["symbol"]]
        k = dogrula(r, c0, c1, d30, d1)
        kontrol[r["id"]] = k
        olu_say += bool(k["olum"])
        uc_say += bool(k["0"]) + bool(k["1"])
        olum = ", ".join(f"**{a}** {t:%m-%d %H:%M}" for a, t in k["olum"]) or "canlı"
        satir.append(f"| {r['id']} | {r['symbol'].split('/')[0]} | {r['karar_ts']} | "
                     f"{c0.tip} {c0.ts:%m-%d %H:%M} | {c1.tip} {c1.ts:%m-%d %H:%M} | "
                     f"{', '.join(f'{t} {v}' for t, v in k['0']) or '—'} | "
                     f"{', '.join(f'{t} {v}' for t, v in k['1']) or '—'} | {olum} |")
    satir += ["", f"**Yerel uç değil:** {uc_say} çapa (2 × {len(setup)} içinde). "
              f"**Karar anına kadar ölmüş yapı:** {olu_say}/{len(setup)} (etiketlerden çıkarılmadı; "
              "ilk ihlal edilen çapa ve 1m zamanı). Ölüm penceresi `1` mumunun kapanışı → karar.", ""]

    # --- adım 3: adaylar
    son_tarih = {r["id"]: ilk_050(V[r["symbol"]][1], c0, c1) for r, (c0, c1) in setup}
    sonra = [i for i, t in son_tarih.items() if t is None]
    sonuc = {}
    for ad in adaylar or list(ADAYLAR):
        fn = ADAYLAR[ad]
        sw = {s: fn(V[s][0], s) for s in semboller}
        zs = {s: zonlar(V[s][0], s, sw[s], eslestirme) for s in semboller}
        cift, r0, r1, gec, isabet = 0, 0, 0, [], []
        for r, (c0, c1) in setup:
            s = r["symbol"]
            r0 += any(eslesir(x.ts, TIP[x.kind], c0) for x in sw[s])
            r1 += any(eslesir(x.ts, TIP[x.kind], c1) for x in sw[s])
            son = son_tarih[r["id"]]
            uy = [z for z in zs[s] if eslesir(z.anchor_0_time, z_tip0(z), c0)
                  and eslesir(z.anchor_1_time, "dip" if z_tip0(z) == "tepe" else "tepe", c1)
                  and (son is None or z.known_at <= son)]
            if uy:
                cift += 1
                isabet.append(r["id"])
                gec.append(min((z.known_at - z.anchor_1_time) / pd.Timedelta("1h") for z in uy))
        fa_b = sum(alarm(zs[r["symbol"]], V[r["symbol"]][1], pd.Timestamp(r["karar_ts"], tz="UTC"))
                   for r in yok if r["tur"] == "bot")
        fa_r = sum(alarm(zs[r["symbol"]], V[r["symbol"]][1], pd.Timestamp(r["karar_ts"], tz="UTC"))
                   for r in yok if r["tur"] == "rastgele")
        ay = sum((V[s][0].ts.iloc[-1] - V[s][0].ts.iloc[0]) / pd.Timedelta("30D") for s in semboller)
        sonuc[ad] = dict(cift=cift, r0=r0, r1=r1, fa_b=fa_b, fa_r=fa_r,
                         gec=statistics.median(gec) if gec else float("nan"), isabet=isabet,
                         zone_ay=sum(len(z) for z in zs.values()) / ay,
                         swing_ay=sum(len(x) for x in sw.values()) / ay)
        print(ad, {k: v for k, v in sonuc[ad].items() if k != "isabet"}, flush=True)

    n = len(setup)
    nb = sum(r["tur"] == "bot" for r in yok)
    nr = len(yok) - nb
    satir += ["## 2 · Adaylar", "",
              f"Setup'lı {n} an; setup yok {nb} bot + {nr} rastgele. 0.50 teması eğitim diliminde "
              f"bulunmayan setup: {len(sonra)} ({', '.join(sonra) or '—'}) — son tarih yok sayıldı.", "",
              f"| aday | çift isabet (/{n}) | 0 geri çağırma | 1 geri çağırma | yanlış alarm bot (/{nb}) | "
              f"yanlış alarm rastgele (/{nr}) | teyit gecikmesi medyanı (saat) | swing / sembol-ay | zone / sembol-ay |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ad, s in sonuc.items():
        satir.append(f"| {ad} | {s['cift']} ({s['cift'] / n:.0%}) | {s['r0']} ({s['r0'] / n:.0%}) | "
                     f"{s['r1']} ({s['r1'] / n:.0%}) | {s['fa_b']} | {s['fa_r']} | {s['gec']:.1f} | "
                     f"{s['swing_ay']:.0f} | {s['zone_ay']:.0f} |")

    # --- seçim kuralı
    tepe = max(s["cift"] for s in sonuc.values())
    esit = [a for a, s in sonuc.items() if tepe - s["cift"] <= ESIT]
    sira = sorted(esit, key=lambda a: (sonuc[a]["fa_b"] + sonuc[a]["fa_r"],
                                        -(sonuc[a]["r0"] + sonuc[a]["r1"]), sonuc[a]["gec"]))
    secilen = sira[0]
    satir += ["", "## 3 · Seçim", "",
              f"En yüksek çift isabet {tepe}/{n}. Fark ≤ {ESIT} → eşit: {', '.join(esit)}. "
              "İkincil sıra: yanlış alarm (bot + rastgele) ↓, tek çapa geri çağırma (0 + 1) ↑, "
              "teyit gecikmesi ↓.", "",
              f"**Seçilen: {secilen}.** İsabet eden anlar: {', '.join(sonuc[secilen]['isabet']) or '—'}.", ""]
    out.write_text("\n".join(satir) + "\n", encoding="utf-8")
    print(f"{out} · seçilen {secilen}")
    return secilen


# --- adım 4: seçilenle koşu ----------------------------------------------------

def kos(ad: str, bakiye: Decimal = Decimal("100"), ek: str = "",
        eslestirme: str = ESLESTIRME) -> None:
    """F1/100 USDT koşusu (`scripts.inceleme.kos`), zone'lar adayın swing listesinden.

    Önbellek (`load_symbol`) atlanır: anahtarı swing tanımını içermiyor.
    `htf_bias` yönü `structure.detect_swings`'i kullanır, değişmez.
    """
    from functools import partial

    from scripts import inceleme
    from src.backtest.loader import _build_symbol
    from src.zones.detect import detect_zones

    fn = ADAYLAR[ad]
    with mock.patch("src.zones.detect.detect_swings", lambda df, symbol, timeframe: fn(df, symbol)), \
         mock.patch("src.backtest.loader.detect_zones", partial(detect_zones, eslestirme=eslestirme)), \
         mock.patch("src.backtest.engine.load_symbol", _build_symbol):
        inceleme.kos(bakiye, yol=Path(f"logs/inceleme/swing_{ad}_{bakiye}{ek}.pkl"))


def ozet(pkl: Path) -> None:
    """SONUCLAR satırı için sayılar: bitiş, kazanma, işlem, R, kriter 3, leg, sembol-ay."""
    from scripts.damga import kriter3
    from scripts.inceleme import r_degeri

    p = pickle.loads(pkl.read_bytes())
    T, Z = p["trades"], p["zones"]
    R = [r_degeri(t, Z[t.zone_id]) for t in T]
    kaz = [r for t, r in zip(T, R) if t.pnl > 0]
    kay = [r for t, r in zip(T, R) if t.pnl <= 0]
    bas = min(pd.Timestamp(v, tz="UTC") for v in p["baslangic"].values())
    son = max(pd.Timestamp(v, tz="UTC") for v in p["bitis"].values())
    k3 = kriter3(T, bas, son)
    leg = statistics.median(abs(Z[t.zone_id].anchor_1_price - Z[t.zone_id].anchor_0_price)
                            / Z[t.zone_id].anchor_0_price * 100 for t in T)
    ay = sum((pd.Timestamp(p["bitis"][s]) - pd.Timestamp(p["baslangic"][s])) / pd.Timedelta("30D")
             for s in p["bitis"])
    print(json.dumps({
        "bitis": str(p["bakiye"] + p["net"]), "islem": len(T),
        "kazanma": len(kaz) / len(T) if T else None,
        "R_kazanan": statistics.mean(kaz) if kaz else None,
        "R_kaybeden": statistics.mean(kay) if kay else None,
        "kriter3": f"{k3['pozitif']}/{k3['n']} pozitif ay, A1 {k3['A1']}, A2 {k3['A2']}",
        "aylik": {a: str(v.quantize(Decimal('0.01'))) for a, v in k3["aylar"].items()},
        "leg_medyan_yuzde": leg, "islem_sembol_ay": len(T) / ay, "hash": p["hash"],
        "spec": p["spec_version"], "kod": p["code_version"],
        "sayac": {k: v for k, v in p["counters"].items() if "reject" in k},
    }, ensure_ascii=False, indent=1, default=str))


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--kos", metavar="ADAY", choices=list(ADAYLAR))
    a.add_argument("--ek", default="", help="pkl adına ek (ör. _v08), eski koşunun üzerine yazmamak için")
    a.add_argument("--ozet", metavar="PKL")
    a.add_argument("--eslestirme", default=ESLESTIRME, choices=["pencere", "son_supuren"],
                   help="R-ZONE-10 anchor_0 seçeneği")
    a.add_argument("--adaylar", help="virgüllü, ör. B2,B3 (varsayılan: yedisi)")
    a.add_argument("--out", type=Path, default=OUT)
    x = a.parse_args()
    if x.kos:
        kos(x.kos, ek=x.ek, eslestirme=x.eslestirme)
    elif x.ozet:
        ozet(Path(x.ozet))
    else:
        degerlendir(x.eslestirme, x.adaylar.split(",") if x.adaylar else None, x.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
