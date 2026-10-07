"""#31 açıklayıcı analizler — işlem sıklığı, v4 yanlış alarm, 4h yön uyumu. Kural uygulamaz.

    python -m scripts.analiz_31      # logs/inceleme/ltf31_31.pkl → docs/measurements/analiz_31.md

(1) Sıklık: giriş zamanına göre günlük / haftalık (ISO hafta, UTC) işlem sayısı, sembol başına
haftalık ortalama, en yoğun haftalar, tutma süresi, zone başına işlem.
(4a) v4'ün 30 anında motorun **aktif** zone'u: karar anında bilinen (`known_at` ≤ karar) ve
`0`/`1`'i `watch_from`'dan karara kadar ihlal edilmemiş zone (B2 + `son_supuren`, `swing_secim`
ile aynı). "Bantta" = ayrıca karar 1m mumu 0.70–0.79'a temas (`swing_secim.alarm`, v4 puanının
yanlış alarm tanımı). Kullanıcı: 12/30 setup var.
(4b) #31'in OTE girişleri, girişte bilinen 4h yönüne göre (`Trade.entry_bias`, R-ZONE-10 —
`structure.htf_bias`): uyumlu (LONG+UP, SHORT+DOWN) / ters / belirsiz (`NONE`).
"""
from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd

PKL = Path("logs/inceleme/ltf31_31.pkl")
OUT = Path("docs/measurements/analiz_31.md")
V4 = Path("docs/inceleme/v4/etiketler.json")


def siklik(T, c: dict) -> list[str]:
    df = pd.DataFrame({"s": [t.symbol.split("/")[0] for t in T],
                       "g": pd.to_datetime([t.entry_ts for t in T], utc=True),
                       "c": pd.to_datetime([t.exit_ts for t in T], utc=True),
                       "z": [t.zone_id for t in T], "giris": [t.giris for t in T]})
    bas, son = df.g.min().floor("D"), df.g.max().floor("D")
    gun = df.g.dt.floor("D").value_counts().reindex(pd.date_range(bas, son, freq="D"), fill_value=0)
    hf = df.g.dt.tz_localize(None).dt.to_period("W-SUN")
    hafta = hf.value_counts().reindex(pd.period_range(hf.min(), hf.max(), freq="W-SUN"), fill_value=0)
    # sembol başına: o sembolün kendi işlem dönemi (veri başlangıcı farklı, ör. ZEC)
    sb = df.groupby("s").agg(n=("g", "size"), a=("g", "min"), b=("g", "max"))
    sb["hafta"] = ((sb.b - sb.a) / pd.Timedelta("7D")).clip(lower=1)
    sb["hft"] = sb.n / sb.hafta
    sure = (df.c - df.g) / pd.Timedelta("1h")
    zn = df.groupby("z").size()
    q = lambda x, p: f"{x.quantile(p):.1f}"  # noqa: E731
    s = ["## 1 · İşlem sıklığı", "",
         f"{len(df)} işlem, {bas:%Y-%m-%d} → {son:%Y-%m-%d} ({len(gun)} gün, {len(hafta)} hafta), "
         f"{df.s.nunique()} sembol (ETH'de hiç işlem yok). Giriş zamanına göre.", "",
         "| ölçü | ortalama | medyan | %90 | en çok | sıfır olan |", "|---|---:|---:|---:|---:|---:|",
         f"| günlük işlem (tüm semboller) | {gun.mean():.1f} | {gun.median():.0f} | {q(gun, .9)} | "
         f"{gun.max()} ({gun.idxmax():%Y-%m-%d}) | {(gun == 0).sum()} gün |",
         f"| haftalık işlem (tüm semboller) | {hafta.mean():.1f} | {hafta.median():.0f} | {q(hafta, .9)} | "
         f"{hafta.max()} | {(hafta == 0).sum()} hafta |",
         f"| sembol başına haftalık | {sb.hft.mean():.2f} | {sb.hft.median():.2f} | {q(sb.hft, .9)} | "
         f"{sb.hft.max():.2f} ({sb.hft.idxmax()}) | — |", "",
         f"Sembol-gün başına {len(df) / (sb.hafta.sum() * 7):.2f} işlem. "
         f"Tutma süresi (saat): medyan {sure.median():.1f}, %25 {q(sure, .25)}, %75 {q(sure, .75)}; "
         f"1 saatten kısa {(sure < 1).mean() * 100:.0f}%, 15 dakikadan kısa {(sure < .25).mean() * 100:.0f}%.",
         f"Zone başına işlem: {len(zn)} zone, ortalama {zn.mean():.2f}, en çok {zn.max()}; "
         f"birden fazla işlem açılan zone {(zn > 1).sum()} ({(zn > 1).mean() * 100:.0f}%), bu zone'lardaki "
         f"işlem {zn[zn > 1].sum()} ({zn[zn > 1].sum() / len(df) * 100:.0f}%).",
         f"Portföyde en az bir açık pozisyon olan 1m mumu: {c['bars_with_position'] / c['bars_total'] * 100:.0f}% "
         f"(`bars_with_position` / `bars_total`).", "",
         "**En yoğun 5 hafta:**", "", "| hafta (Pzt) | işlem | en çok sembol |", "|---|---:|---|"]
    for p, n in hafta.sort_values(ascending=False).head(5).items():
        top = df[hf == p].s.value_counts().head(3)
        s.append(f"| {p.start_time:%Y-%m-%d} | {n} | " + ", ".join(f"{a} {b}" for a, b in top.items()) + " |")
    s += ["", "**Sembol başına** (işlem / hafta):", "",
          " · ".join(f"{a} {r.hft:.1f}" for a, r in sb.sort_values("hft", ascending=False).iterrows()), ""]
    return s


def v4_aktif() -> list[str]:
    from scripts.swing_secim import ADAYLAR, alarm, capalar, veri, zonlar

    E = json.loads(V4.read_text(encoding="utf-8"))
    V = {s: veri(s) for s in sorted({r["symbol"] for r in E})}
    zs = {s: zonlar(V[s][0], s, ADAYLAR["B2"](V[s][0], s), "son_supuren") for s in V}
    tab = Counter()
    satir = []
    for r in E:
        k = pd.Timestamp(r["karar_ts"], tz="UTC")
        d1 = V[r["symbol"]][1]
        aktif = [z for z in zs[r["symbol"]] if z.known_at <= k and not olu(z, d1, k)
                 and not degdi_070(z, d1, k)]
        setup = capalar(r) is not None
        bant = alarm(zs[r["symbol"]], d1, k)
        hazir = [z for z in aktif if z.pencere_050 or primed(z, d1, k)]
        tab[("hazir", setup, bool(hazir))] += 1
        tab[(setup, bool(aktif))] += 1
        tab[("veya", setup, bool(aktif) or bant)] += 1
        tab[("bant", setup, bant)] += 1
        satir.append(f"| {r['id']} | {r['symbol'].split('/')[0]} | {r['karar_ts']} | "
                     f"{'var' if setup else 'yok'} | {len(aktif)} | {len(hazir)} | {'evet' if bant else '—'} |")
    na = tab[(True, True)] + tab[(False, True)]
    nb = tab[("bant", True, True)] + tab[("bant", False, True)]
    nh = tab[("hazir", True, True)] + tab[("hazir", False, True)]
    return ["## 4a · v4: motorun aktif zone'u ↔ kullanıcının setup'ı", "",
            f"Kullanıcı **12/30** setup var. Motor: karar anında aktif zone'u olan an **{na}/30**, "
            f"0.50'ye ulaşmış (PRIMED — OTE emri bekliyor) **{nh}/30**, bantta (0.70–0.79 temas) **{nb}/30**, ikisinden biri "
            f"**{tab[('veya', True, True)] + tab[('veya', False, True)]}/30**.", "",
            "| | kullanıcı setup var (12) | setup yok (18) |", "|---|---:|---:|",
            f"| motorda aktif zone var | {tab[(True, True)]} | {tab[(False, True)]} |",
            f"| aktif zone yok | {tab[(True, False)]} | {tab[(False, False)]} |",
            f"| PRIMED zone var | {tab[('hazir', True, True)]} | {tab[('hazir', False, True)]} |",
            f"| bantta zone var | {tab[('bant', True, True)]} | {tab[('bant', False, True)]} |",
            f"| **aktif ya da bantta** (motor “setup var”) | {tab[('veya', True, True)]} | "
            f"{tab[('veya', False, True)]} |", "",
            "Aktif = bilinen, `0`/`1`'i ihlal edilmemiş ve 0.70'e karardan önce değmemiş (değdiyse motor o "
            "zone'da işlemini yapmış olurdu; spec dışı zone ölümleri — sonlandırma, kill — sayılmadı). PRIMED = aktif ve 0.50'ye "
            "ulaşmış (v0.11'de OTE emri zone ölene kadar durur → bu anlarda motorun bekleyen emri var). Kullanıcının setup'ı ile "
            "motorun zone'unun **aynı leg** olduğu kontrol edilmedi (o, v4 puanının çift isabetidir: 8/12).",
            "", "<details><summary>30 an</summary>", "",
            "| an | sembol | karar | kullanıcı | aktif zone | PRIMED | bantta |", "|---|---|---|---|---:|---:|---|",
            *satir, "", "</details>", ""]


def olu(z, d1, karar) -> bool:
    """`swing_secim.alarm`'daki ölüm ölçütü: `watch_from`'dan karara `0`/`1` ihlali."""
    p = d1[(d1.ts >= z.watch_from) & (d1.ts < karar)]
    if z.bias == "SHORT":
        return bool((p.low <= z.anchor_0_price).any() or (p.high >= z.anchor_1_price).any())
    return bool((p.high >= z.anchor_0_price).any() or (p.low <= z.anchor_1_price).any())


def degdi_070(z, d1, karar) -> bool:
    """`watch_from`'dan karara 0.70 teması — motor o zone'da girişini yapmış/kapatmış olurdu."""
    p = d1[(d1.ts >= z.watch_from) & (d1.ts < karar)]
    return bool((p.high >= z.level_070).any() if z.bias == "SHORT" else (p.low <= z.level_070).any())


def primed(z, d1, karar) -> bool:
    """`watch_from`'dan karara 0.50 teması (R-ZONE: PRIMED; pencerede ulaşılmışsa `pencere_050`)."""
    p = d1[(d1.ts >= z.watch_from) & (d1.ts < karar)]
    if z.bias == "SHORT":
        return bool((p.high >= z.level_050).any())
    return bool((p.low <= z.level_050).any())


def uyum(T) -> list[str]:
    g = {"uyumlu": [], "ters": [], "belirsiz": []}
    for t in T:
        if t.giris != "OTE":
            continue
        b = t.entry_bias
        g["belirsiz" if b == "NONE" else
          "uyumlu" if (t.side, b) in (("LONG", "UP"), ("SHORT", "DOWN")) else "ters"].append(t)
    n = sum(len(v) for v in g.values())
    s = ["## 4b · OTE girişleri ↔ 4h yapı yönü (R-ZONE-10)", "",
         f"#31'in {n} OTE girişi (OB girişleri hariç), girişte bilinen 4h yön (`entry_bias`). Kural "
         "uygulanmadı; brüt = fiyat PnL'i (slippage içinde), net = brüt − komisyon − funding.", "",
         "| grup | işlem | pay | kazanma | brüt $ | brüt/işlem $ | net $ |", "|---|---:|---:|---:|---:|---:|---:|"]
    for ad, L in g.items():
        if not L:
            continue
        br = sum((t.gross for t in L), Decimal(0))
        ne = sum((t.pnl for t in L), Decimal(0))
        s.append(f"| {ad} | {len(L)} | %{len(L) / n * 100:.0f} | %{sum(t.pnl > 0 for t in L) / len(L) * 100:.1f} "
                 f"| {br:+.2f} | {br / len(L):+.4f} | {ne:+.2f} |".replace(".", ","))
    s += ["", "Tek koşu, örneklem içi, bootstrap yok — gruplar arası fark gürültü olabilir.", ""]
    return s


def main() -> int:
    p = pickle.loads(PKL.read_bytes())
    T = p["trades"]
    s = ["# #31 açıklayıcı analizler", "",
         f"Kaynak `scripts/analiz_31.py`, `{PKL.as_posix()}` (parmak izi `{p['hash']}`, spec "
         f"{p['spec_version']}, kod {p['code_version']}). Açıklayıcıdır, kural değiştirmez.", "",
         *siklik(T, p["counters"]), *v4_aktif(), *uyum(T)]
    OUT.write_text("\n".join(s) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
