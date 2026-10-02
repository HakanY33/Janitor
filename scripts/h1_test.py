"""H1 analizi — temastaki emilim. `docs/HYPOTHESES.md` §1–§6, birebir.

    python -m scripts.h1_test                  # 40 sembol, dilim 2026-10-01 → 12-31
    python -m scripts.h1_test --uzat           # yetersiz örnek: dilim 2027-03-31

**Kilit.** Gerçek işlem akışı `KILIT` (2027-01-01) öncesinde **okunmaz** (`veri_kilidi`).
Tek bakış, ara bakış yok (§6).
Okunduktan sonra emilimli temas `n < N_MIN` (503) ise yalnızca `n` ve dışlama sayıları
yazılır; R hesaplanmaz (§6 yetersiz örnek kuralı). Kod dilime bakmadan, yalnızca sentetik
veriyle sınandı (`tests/test_h1.py`).

Akış: 30m zone tespiti (mevcut kod) → 1m'de `PRIMED → TOUCHED` (`Zone.on_bar` ile aynı
anlam, vektörel; eşdeğerlik testli) → emilim (§3) → sonuç (§4) → ölçüt (§4, §6).

Kriter 3 "en iyi sembol / ay" = çıkarıldığında kalan ortalamayı **en çok düşüren** grup
(kullanıcı onayı, §6). 7 gün dolmadan veri biterse işlem `ACIK` sayılır, `n`'e girmez,
ayrıca raporlanır. Net R funding içerir, sembolün gerçek aralığıyla (§4, `OPEN-59`).

Ön kayıtta **kayıt** rolündeki defter özellikleri ve "ikinci deneme" hesaplanmaz: ölçüte
girmezler ve bu olay tanımında (`PRIMED`'den sonraki ilk 0.70 teması) `touch_count` ≤ 1.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from src.backtest.costs import CostModel
from src.data import collect
from src.zones.model import Zone, touches

# --- ön kayıt sabitleri (değiştirilmez; §3–§6) ---------------------------------
W = 5  # emilim penceresi, dakika (temas mumu dahil)
TABAN = 60  # A_60 penceresi, W'dan önce
KAT = 3  # Σ_W A ≥ KAT × W × A_60
ILERLEME = 0.5  # bant içine en derin ilerleme ≤ bant genişliğinin yarısı
TUTMA = 7 * 1440  # 7 gün, 1m mum
GUVEN = 0.975  # tek yönlü
N_MIN = 503
DILIM_BAS = pd.Timestamp("2026-10-01 00:00", tz="UTC")
DILIM_SON = pd.Timestamp("2026-12-31 23:59", tz="UTC")
DILIM_UZAT = pd.Timestamp("2027-03-31 23:59", tz="UTC")
KILIT = pd.Timestamp("2027-01-01 00:00", tz="UTC")  # bu andan önce işlem akışı okunmaz

DK = np.timedelta64(1, "m")


# --- kilit ----------------------------------------------------------------------

class KilitHatasi(RuntimeError):
    pass


def veri_kilidi(simdi: pd.Timestamp) -> None:
    """Gerçek işlem akışı `KILIT` öncesinde okunmaz. Bayrakla kapatılamaz."""
    if simdi < KILIT:
        raise KilitHatasi(f"{simdi:%Y-%m-%d %H:%M} < {KILIT:%Y-%m-%d}: H1 işlem akışı "
                          "okunmaz (docs/HYPOTHESES.md §6, ara bakış yok)")


def islem_akisi_oku(symbol: str, bas: pd.Timestamp, son: pd.Timestamp,
                    simdi: pd.Timestamp | None = None) -> pd.DataFrame:
    """Diskteki işlem akışı, yalnızca `[bas, son]` günleri. Tek okuma yolu; kilitli."""
    veri_kilidi(simdi or pd.Timestamp.now("UTC"))
    d = collect.DATA_ROOT / "bingx" / collect._safe(symbol) / "trades"
    parca = [pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))
             if bas.strftime("%Y-%m-%d") <= p.stem <= son.strftime("%Y-%m-%d")]
    if not parca:
        return pd.DataFrame({"id": [], "ts": pd.to_datetime([], utc=True), "qty": [], "side": []})
    t = pd.concat(parca, ignore_index=True).drop_duplicates("id").sort_values("id")
    return t[(t.ts >= bas) & (t.ts <= son)].reset_index(drop=True)


# --- olay: PRIMED → TOUCHED (§2) ------------------------------------------------

def _ilk(maske, i: int, n: int, adim: int = 2048) -> int | None:
    """`maske(i, j)` dizisinde ilk True'nun mutlak indisi; parça parça tarar."""
    while i < n:
        j = min(n, i + adim)
        k = np.flatnonzero(maske(i, j))
        if len(k):
            return i + int(k[0])
        i, adim = j, adim * 2
    return None


def ilk_temas(z: Zone, ts: np.ndarray, h: np.ndarray, l: np.ndarray) -> tuple[int | None, str]:
    """Zone'un `PRIMED → TOUCHED` mumu (indis) ya da neden olmadığı.

    `Zone.on_bar` ile aynı anlam: önce çapa teması (0 ya da 1 → öldürür), sonra tek
    ilerleme; bir mumda en fazla bir ilerleme. `ts` 1m açılışları (tz-naive UTC).
    Temas mumunda `1`'e de ulaşıldıysa olay yok (`ayni_mum`, §2).
    """
    n = len(ts)
    i = int(np.searchsorted(ts, np.datetime64(pd.Timestamp(z.watch_from).tz_convert("UTC")
                                               .tz_localize(None))))
    a0, a1 = z.anchor_0_price, z.anchor_1_price
    short = z.bias == "SHORT"

    def olum(s, e):
        dur = h[s:e] >= a1 if short else l[s:e] <= a1
        return dur | ((l[s:e] <= a0) & (a0 <= h[s:e]))

    def temas(lvl):
        return lambda s, e: (l[s:e] <= lvl) & (lvl <= h[s:e])

    p = _ilk(lambda s, e: olum(s, e) | temas(z.level_050)(s, e), i, n)
    if p is None:
        return None, "priming_yok"
    if olum(p, p + 1)[0]:
        return None, "oldu"
    q = _ilk(lambda s, e: olum(s, e) | temas(z.level_070)(s, e), p + 1, n)
    if q is None:
        return None, "temas_yok"
    if olum(q, q + 1)[0]:
        return None, "ayni_mum" if temas(z.level_070)(q, q + 1)[0] else "oldu"
    return q, "temas"


# --- emilim (§3) ---------------------------------------------------------------

def dakika_akisi(trades: pd.DataFrame) -> pd.DataFrame:
    """Dakika başına agresör alış / satış miktarı (baz varlık). İndeks tz-naive UTC."""
    if trades.empty:
        return pd.DataFrame(columns=["buy", "sell"], dtype=float)
    m = trades.ts.dt.tz_convert("UTC").dt.tz_localize(None).dt.floor("min")
    return trades.groupby([m, trades.side]).qty.sum().unstack(fill_value=0.0).reindex(
        columns=["buy", "sell"], fill_value=0.0)


def bosluklar(trades: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.datetime64 | None]:
    """`fillId` atlamaları: kayıp işlemler `(onceki_ts, sonraki_ts)` arasında. + kapsam başı."""
    if trades.empty:
        return np.array([], "datetime64[ns]"), np.array([], "datetime64[ns]"), None
    t = trades.sort_values("id")
    ts = t.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    k = np.flatnonzero(np.diff(t.id.to_numpy()) > 1)
    return ts[k], ts[k + 1], ts[0]


def emilim(bias: str, l070: float, l079: float, t0: np.datetime64, akis: pd.DataFrame,
           gap: tuple, ts: np.ndarray, h: np.ndarray, l: np.ndarray) -> tuple[str, dict]:
    """`var` / `yok` / `dislandi_bosluk` / `dislandi_a60` ve ölçülen değerler.

    Pencere `W` = `t0`'da biten son 5 dakika, taban `W`'dan önceki 60 dakika. İkisinin
    birleşiminde (65 dk) `trades_gap` ya da kayıt başlangıcı varsa dışlanır (§3, 2026-09-30
    değişikliği). Emilim ölçülürken yalnızca `< t0` dakikaları okunur (CLAUDE.md #3).
    """
    bas = t0 - (W + TABAN) * DK
    g0, g1, kapsam = gap
    if kapsam is None or kapsam > bas or ((g1 >= bas) & (g0 < t0)).any():
        return "dislandi_bosluk", {}
    karsi = "buy" if bias == "SHORT" else "sell"
    a = akis[karsi].reindex(pd.date_range(bas, t0 - DK, freq="min"), fill_value=0.0).to_numpy()
    a60, aw = float(np.median(a[:TABAN])), float(a[TABAN:].sum())
    if a60 == 0:
        return "dislandi_a60", {"A_60": 0.0, "A_W": aw}
    i, j = np.searchsorted(ts, [t0 - W * DK, t0])
    uc = h[i:j].max() if bias == "SHORT" else l[i:j].min()
    ilerleme = (uc - l070) / (l079 - l070)
    ok = aw >= KAT * W * a60 and ilerleme <= ILERLEME
    return ("var" if ok else "yok"), {"A_60": a60, "A_W": aw, "ilerleme": float(ilerleme)}


# --- sonuç (§4) ----------------------------------------------------------------

def sonuc(z: Zone, q: int, ts, o, h, l, c, taker: Decimal, costs: CostModel) -> dict:
    """Temas mumu `q` kapanışından taker giriş; stop `1`, hedef `0.50` tam çıkış, 7 gün.

    Stop: `1`'e ulaşıldı → dokunduysa kapanıştan, boşlukla geçtiyse açılıştan (R-RISK-02).
    Hedef: `0.50`'ye ulaşıldı → seviyeden. Aynı mum → stop. Net = taker gidiş-dönüş +
    slippage + funding (`costs.py`, sembolün gerçek funding anları; `t0` hariç, çıkış
    mumunun kapanışı dahil). `ts` 1m açılışları (tz-naive UTC).
    """
    short = z.bias == "SHORT"
    giris, stop, tp = float(c[q]), z.anchor_1_price, z.level_050
    s, e = q + 1, min(len(c), q + 1 + TUTMA)
    sv = h[s:e] >= stop if short else l[s:e] <= stop
    tv = l[s:e] <= tp if short else h[s:e] >= tp
    js = s + int(sv.argmax()) if sv.any() else None
    jt = s + int(tv.argmax()) if tv.any() else None
    if js is not None and (jt is None or js <= jt):
        neden, j = "STOP", js
        cikis = float(c[j]) if touches(stop, h[j], l[j]) else float(o[j])
    elif jt is not None:
        neden, j, cikis = "TP", jt, tp
    elif e - s == TUTMA:
        neden, j, cikis = "SURE", e - 1, float(c[e - 1])
    else:
        return {"neden": "ACIK"}
    yon = "SHORT" if short else "LONG"
    sgn = Decimal(-1 if short else 1)
    G, C = Decimal(str(giris)), Decimal(str(cikis))
    Gd, Cd = costs.fill_price(G, yon, opening=True), costs.fill_price(C, yon, opening=False)
    risk = abs(G - Decimal(str(stop)))
    fund = costs.funding_cost(z.symbol, yon, G, pd.Timestamp(ts[q] + DK, tz="UTC"),
                              pd.Timestamp(ts[j] + DK, tz="UTC"))  # birim miktar başına
    net = sgn * (Cd - Gd) - taker * (Gd + Cd) - fund
    return {"neden": neden, "giris": giris, "cikis": cikis, "cikis_i": j,
            "funding_R": float(fund / risk),
            "R_brut": float(sgn * (C - G) / risk), "R_net": float(net / risk)}


# --- sembol akışı ----------------------------------------------------------------

def sembol_temaslari(symbol: str, zones: list[Zone], d1: pd.DataFrame, trades: pd.DataFrame,
                     bas: pd.Timestamp, son: pd.Timestamp) -> tuple[list[dict], dict]:
    """Dilimdeki (`bas ≤ t0 ≤ son`) temaslar ve emilim sınıfı. Sonuç hesaplanmaz."""
    ts = d1.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    h, l = d1.high.to_numpy(float), d1.low.to_numpy(float)
    akis, gap = dakika_akisi(trades), bosluklar(trades)
    b, s = (np.datetime64(x.tz_localize(None)) for x in (bas, son))
    sayac: dict[str, int] = {}
    out = []
    for z in zones:
        q, neden = ilk_temas(z, ts, h, l)
        t0 = ts[q] + DK if q is not None else None
        if t0 is None or not (b <= t0 <= s):
            continue
        sinif, deger = emilim(z.bias, z.level_070, z.level_079, t0, akis, gap, ts, h, l)
        sayac[sinif] = sayac.get(sinif, 0) + 1
        out.append({"symbol": symbol, "zone_id": z.zone_id, "bias": z.bias,
                    "t0": pd.Timestamp(t0, tz="UTC"), "q": q, "emilim": sinif, **deger})
    return out, sayac


def sonuclar(temas: list[dict], zones: dict[str, Zone], d1: pd.DataFrame, taker: Decimal,
             costs: CostModel) -> list[dict]:
    ts = d1.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    o, h, l, c = (d1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    return [{**t, **sonuc(zones[t["zone_id"]], t["q"], ts, o, h, l, c, taker, costs)}
            for t in temas]


# --- ölçüt (§4, §6) -------------------------------------------------------------

def alt_sinir(r: pd.Series) -> float:
    n = len(r)
    if n < 2:
        return float("nan")
    return float(r.mean() - stats.t.ppf(GUVEN, n - 1) * r.std(ddof=1) / np.sqrt(n))


def grup_cikar(df: pd.DataFrame, anahtar: pd.Series) -> tuple[str, float]:
    """Çıkarıldığında kalan ortalama net R'yi en çok düşüren grup ve kalan ortalama."""
    g = df.R_net.groupby(anahtar).agg(["sum", "count"])
    kalan = (df.R_net.sum() - g["sum"]) / (len(df) - g["count"])
    kalan = kalan[len(df) - g["count"] > 0]
    if kalan.empty:
        return "-", float("nan")
    k = kalan.idxmin()
    return str(k), float(kalan[k])


def degerlendir(df: pd.DataFrame) -> dict:
    """Emilimli, kapanmış temaslar üzerinde kriter 1–3. `n < N_MIN` → yalnızca n."""
    n = len(df)
    if n < N_MIN:
        return {"n": n, "sonuc": "KARARSIZ", "kriter1": False}
    lb = alt_sinir(df.R_net)
    sem, sem_r = grup_cikar(df, df.symbol)
    ay, ay_r = grup_cikar(df, df.t0.dt.strftime("%Y-%m"))
    k2, k3 = lb > 0, sem_r > 0 and ay_r > 0
    return {"n": n, "kriter1": True, "ort": float(df.R_net.mean()), "ort_brut": float(df.R_brut.mean()),
            "sd": float(df.R_net.std(ddof=1)), "alt_sinir": lb, "kriter2": k2,
            "en_iyi_sembol": sem, "sembolsuz_ort": sem_r, "en_iyi_ay": ay, "aysiz_ort": ay_r,
            "kriter3": k3, "sonuc": "KABUL" if k2 and k3 else "RET"}


def analiz(veri: list[tuple], costs: CostModel, bas: pd.Timestamp, son: pd.Timestamp) -> dict:
    """`veri` = [(symbol, zones, d1, trades)]. Saf: dosya okumaz — sentetik testin girişi.

    Önce yalnızca emilim sınıfları sayılır; `n < N_MIN` ise sonuç hiç hesaplanmaz.
    """
    temas, sayac, parca = [], {}, []
    for symbol, zones, d1, trades in veri:
        t, s = sembol_temaslari(symbol, zones, d1, trades, bas, son)
        temas += t
        parca.append((symbol, zones, d1, t))
        for k, v in s.items():
            sayac[k] = sayac.get(k, 0) + v
    rapor = {"sayac": sayac, "n_emilimli": sayac.get("var", 0)}
    if rapor["n_emilimli"] < N_MIN:
        rapor["degerlendirme"] = {"n": rapor["n_emilimli"], "sonuc": "KARARSIZ", "kriter1": False}
        return rapor  # §6: R'ye bakılmaz
    satir = []
    for symbol, zones, d1, t in parca:
        taker = costs.fees[symbol].taker
        satir += sonuclar(t, {z.zone_id: z for z in zones}, d1, taker, costs)
    df = pd.DataFrame(satir)
    em = df[df.emilim == "var"]
    kapali = em[em.neden != "ACIK"]
    rapor["acik"] = int((em.neden == "ACIK").sum())
    rapor["degerlendirme"] = degerlendir(kapali)
    yok = df[(df.emilim == "yok") & (df.neden != "ACIK")]
    rapor["emilimsiz"] = {"n": len(yok), "ort": float(yok.R_net.mean()) if len(yok) else float("nan")}
    rapor["tablo"] = df
    return rapor


# --- ağ kabuğu ------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="H1 — temastaki emilim (tek bakış)")
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--uzat", action="store_true", help="yetersiz örnek: dilim 2027-03-31")
    p.add_argument("--out", default="logs/h1_test")
    a = p.parse_args()

    veri_kilidi(pd.Timestamp.now("UTC"))  # 30m/1m okumadan önce de dur
    import json

    from scripts.backtest import code_version, spec_version
    from scripts.measure_ob import liquidity_symbols
    from scripts.soguk import SOGUK_PATH
    from src.backtest.costs import build_cost_model
    from src.backtest.loader import DETECT_TF
    from src.zones.detect import detect_zones

    semboller = a.symbols or (liquidity_symbols(20)
                              + json.loads(SOGUK_PATH.read_text(encoding="utf-8"))["symbols"][:20])
    son = DILIM_UZAT if a.uzat else DILIM_SON
    costs = build_cost_model(semboller, "bingx")
    veri = []
    for s in semboller:
        d30 = collect.read_parquet("bingx", s, DETECT_TF)
        d30 = d30[d30.ts + pd.Timedelta(DETECT_TF) <= son + pd.Timedelta("1min")]
        d1 = collect.read_parquet("bingx", s, "1m").reset_index(drop=True)
        zones = [z for z in detect_zones(d30, s, DETECT_TF) if z.watch_from <= son]
        veri.append((s, zones, d1, islem_akisi_oku(s, DILIM_BAS, son)))
        print(f"  {s}: {len(zones)} zone", file=sys.stderr, flush=True)
    r = analiz(veri, costs, DILIM_BAS, son)
    d = r["degerlendirme"]
    satir = [
        "H1 — TEMASTAKİ EMİLİM (docs/HYPOTHESES.md)",
        f"spec_version {spec_version()} · code_version {code_version()}",
        f"dilim {DILIM_BAS:%Y-%m-%d} → {son:%Y-%m-%d} · {len(semboller)} sembol",
        "temas sınıfları: " + " · ".join(f"{k} {v}" for k, v in sorted(r["sayac"].items())),
        f"dışlanan (boşluk, 65 dk pencere): {r['sayac'].get('dislandi_bosluk', 0)} · "
        f"dışlanan (A_60 = 0): {r['sayac'].get('dislandi_a60', 0)}",
        f"emilimli n = {d['n']} (eşik {N_MIN}) · sonuç {d['sonuc']}",
    ]
    if d["kriter1"]:
        satir += [
            f"açık (7 gün dolmadı, n dışı): {r['acik']}",
            f"R net ort {d['ort']:+.3f} · brüt {d['ort_brut']:+.3f} · sd {d['sd']:.3f} · "
            f"tek yönlü %97,5 alt sınır {d['alt_sinir']:+.3f} → kriter 2 {'GEÇTİ' if d['kriter2'] else 'KALDI'}",
            f"kriter 3: {d['en_iyi_sembol']} çıkınca {d['sembolsuz_ort']:+.3f} · {d['en_iyi_ay']} "
            f"çıkınca {d['aysiz_ort']:+.3f} → {'GEÇTİ' if d['kriter3'] else 'KALDI'}",
            f"emilimsiz (ölçüt değil): n {r['emilimsiz']['n']} · R net ort {r['emilimsiz']['ort']:+.3f}",
        ]
        r["tablo"].to_csv(a.out + ".csv", index=False)
    Path(a.out + ".txt").parent.mkdir(parents=True, exist_ok=True)
    Path(a.out + ".txt").write_text("\n".join(satir) + "\n", encoding="utf-8")
    print("\n".join(satir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
