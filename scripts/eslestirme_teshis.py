"""Eşleştirme teşhisi — B2/B3 swing'leri çapaları buluyor, zone'lar neden tutmuyor? (açıklayıcı)

    python -m scripts.eslestirme_teshis     # → docs/inceleme/v3/eslestirme_teshis.md

Salt okur; hiçbir kuralı değiştirmez. v3'ün 44 setup'ı için adayın **ham** zone listesi
(`zones_from_swings`, R-ZONE-05 elemesi işaretli) kullanıcının çapalarıyla karşılaştırılır.
Sınıflar, sırayla ilk tutan:

| sınıf | anlamı |
|---|---|
| doğru | iki çapa eşleşiyor, zone canlı, `known_at` ≤ ilk 0.50 teması (= çift isabet) |
| doğru ama geç | iki çapa eşleşiyor ama `known_at` > ilk 0.50 teması |
| doğru ama elendi | iki çapa eşleşiyor, R-ZONE-05 izleme öncesi penceresinde öldü |
| yanlış 0 | `1` eşleşen zone var, `0`'ı başka |
| yanlış 1 | `0` eşleşen zone var, `1`'i başka |
| ikisi de yanlış · neden | karar anında aynı yönde canlı başka bir zone var (gösterilir) |
| zone kurulmamış · neden | o yönde hiç canlı zone yok |

Neden: `1 süpürmedi` (kullanıcının 1'i swing listesinde ama `swept=False` → `anchor_1` olamaz) ·
`1 swing değil` (listede yok) · `1 süpürdü, zone yok` (0 adayı bulunamadı).

Eşleşme ±2 mum, aynı tip (`swing_secim.eslesir`).

Sonda **0 seçim kuralı karşılaştırması** (örneklem içi, açıklayıcı) ve aday kural "son süpüren
karşı swing" (`son_supuren`) `_anchor_0` yerine geçici olarak takılınca `swing_secim` çift
isabeti. Kodda kural değişmez; doğrulama v4'te (`adaylar.md` 2026-10-05 notu).
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.swing_secim import ADAYLAR, ETIKET, TF, TIP, capalar, eslesir, ilk_050, veri, z_tip0
from src.features.structure import HIGH, LOW
from src.zones.detect import _anchor_0, izleme_oncesi_oldu, zones_from_swings
from src.zones.detect import _anchor_0_son_supuren as son_supuren

OUT = Path("docs/inceleme/v3/eslestirme_teshis.md")
ADAY = ("B3", "B2")


def mum(a, b) -> int:
    return int(round((pd.Timestamp(a) - pd.Timestamp(b)) / TF))


def siniflandir(r, c0, c1, sw, zs, df, d1) -> dict:
    karar = pd.Timestamp(r["karar_ts"], tz="UTC")
    son = ilk_050(d1, c0, c1)
    tip1 = lambda z: "dip" if z_tip0(z) == "tepe" else "tepe"
    m0 = lambda z: eslesir(z.anchor_0_time, z_tip0(z), c0)
    m1 = lambda z: eslesir(z.anchor_1_time, tip1(z), c1)
    olu = {z.zone_id: izleme_oncesi_oldu(z, df) for z in zs}
    out = {"id": r["id"], "sym": r["symbol"], "sembol": r["symbol"].split("/")[0], "u0": c0,
           "u1": c1, "z": None}

    iki = [z for z in zs if m0(z) and m1(z)]
    if iki:
        z = min(iki, key=lambda z: z.known_at)
        canli = [z for z in iki if not olu[z.zone_id]]
        if canli and (son is None or min(z.known_at for z in canli) <= son):
            return {**out, "sinif": "doğru", "z": min(canli, key=lambda z: z.known_at)}
        if canli:
            z = min(canli, key=lambda z: z.known_at)
            return {**out, "sinif": "doğru ama geç", "z": z,
                    "gec_saat": (z.known_at - son) / pd.Timedelta("1h")}
        return {**out, "sinif": "doğru ama elendi", "z": z}
    bir = [z for z in zs if m1(z)]
    if bir:
        z = min(bir, key=lambda z: z.known_at)
        return {**out, "sinif": "yanlış 0", "z": z}
    sifir = [z for z in zs if m0(z)]
    if sifir:
        return {**out, "sinif": "yanlış 1", "z": min(sifir, key=lambda z: z.known_at)}
    s1 = [s for s in sw if eslesir(s.ts, TIP[s.kind], c1)]
    neden = ("1 swing değil" if not s1 else "1 süpürdü, zone yok" if any(s.swept for s in s1)
             else "1 süpürmedi")
    yon = [z for z in zs if tip1(z) == c1.tip and z.known_at <= karar and not olu[z.zone_id]]
    if yon:
        return {**out, "sinif": f"ikisi de yanlış · {neden}", "z": max(yon, key=lambda z: z.known_at)}
    return {**out, "sinif": f"zone kurulmamış · {neden}"}


def onceki_ayni(sw, z):
    """`anchor_1`'in aştığı önceki aynı tip swing (`_anchor_0` aday penceresinin sol ucu)."""
    i = next(i for i, s in enumerate(sw) if s.ts == z.anchor_1_time)
    return next((s for s in reversed(sw[:i]) if s.kind == sw[i].kind), None)


def kural_tablosu(setup, V) -> list[str]:
    """Kullanıcının 1'i listedeyse hangi `anchor_0` kuralı kullanıcının 0'ını buluyor."""
    def uc(L, kar):
        return min(L, key=lambda s: s.price) if kar == LOW else max(L, key=lambda s: s.price)

    sayac: dict[str, Counter] = {}
    for ad in ADAY:
        sw_ = {s: ADAYLAR[ad](V[s][0], s) for s in V}
        for r, (c0, c1) in setup:
            sw = sw_[r["symbol"]]
            kar = LOW if c0.tip == "dip" else HIGH
            i1 = next((i for i, s in enumerate(sw)
                       if s.kind != kar and eslesir(s.ts, TIP[s.kind], c1)), None)
            if i1 is None:
                continue
            karsi = [s for s in sw[:i1] if s.kind == kar]
            yakin = [s for s in karsi if s.ts >= sw[i1].ts - 144 * TF]
            u0 = [s for s in karsi if eslesir(s.ts, TIP[s.kind], c0)]
            bul = lambda s: s is not None and eslesir(s.ts, TIP[s.kind], c0)
            for k, v in {
                "(payda: kullanıcının 1'i listede)": True,
                "kullanıcının 0'ı kendisi süpüren swing": bool(u0) and u0[-1].swept,
                "mevcut `_anchor_0` (1'in aştığı aynı tip swing → 1 penceresi)": bul(_anchor_0(sw, i1)),
                "1'den hemen önceki karşı swing": bul(karsi[-1] if karsi else None),
                "son 144 mumdaki en uç karşı swing": bul(uc(yakin, kar) if yakin else None),
                "**son süpüren karşı swing** (`son_supuren`)": bul(son_supuren(sw, i1)),
            }.items():
                sayac.setdefault(k, Counter())[ad] += bool(v)
    return ["## 0 seçim kuralları (örneklem içi, açıklayıcı)", "",
            "| kural | B3 | B2 |", "|---|---:|---:|",
            *(f"| {k} | {v['B3']} | {v['B2']} |" for k, v in sayac.items())]


def rapor() -> None:
    E = json.loads(ETIKET.read_text(encoding="utf-8"))
    setup = [(r, capalar(r)) for r in E if capalar(r)]
    V = {s: veri(s) for s in sorted({r["symbol"] for r, _ in setup})}
    satir = ["# Eşleştirme teşhisi — v3, 44 setup", "",
             f"Kaynak `scripts/eslestirme_teshis.py` (açıklayıcı, kural değiştirmez). Sınıf tanımları "
             "betiğin başında. Mum = 30m; Δ = motor − kullanıcı (eksi = motorunki daha eski).", ""]
    for ad in ADAY:
        sw = {s: ADAYLAR[ad](V[s][0], s) for s in V}
        zs = {s: zones_from_swings(sw[s], s, "30m") for s in V}
        S = [siniflandir(r, c0, c1, sw[r["symbol"]], zs[r["symbol"]], *V[r["symbol"]])
             for r, (c0, c1) in setup]
        say = Counter(x["sinif"] for x in S)
        satir += [f"## {ad}", "", "| sınıf | sayı |", "|---|---:|"]
        satir += [f"| {k} | {v} |" for k, v in say.most_common()]

        # yanlış 0 örüntüsü
        y0 = [x for x in S if x["sinif"] == "yanlış 0"]
        if y0:
            d = [mum(x["z"].anchor_0_time, x["u0"].ts) for x in y0]
            leg_m = [abs(x["z"].anchor_1_price - x["z"].anchor_0_price) for x in y0]
            leg_u = [abs(x["u1"].fiyat - x["u0"].fiyat) for x in y0]
            daha_eski_kul = sum(v > 0 for v in d)
            buyuk_kul = sum(u > m for u, m in zip(leg_u, leg_m))
            pencere_disi = 0
            for x in y0:
                o = onceki_ayni(sw[x["sym"]], x["z"])
                pencere_disi += o is not None and x["u0"].ts < o.ts
            satir += ["", f"**Yanlış 0 ({len(y0)}):** kullanıcının 0'ı motorunkinden **daha eski** "
                      f"{daha_eski_kul}/{len(y0)}; kullanıcının leg'i **daha büyük** (0 daha uç) "
                      f"{buyuk_kul}/{len(y0)}; Δ medyanı {statistics.median(d):+.0f} mum. Kullanıcının 0'ı, "
                      f"motorun aday penceresinin (1'in aştığı önceki aynı tip swing → 1) **solunda**: "
                      f"{pencere_disi}/{len(y0)}."]
        gec = [x for x in S if x["sinif"] == "doğru ama geç"]
        if gec:
            satir += ["", f"**Doğru ama geç ({len(gec)}):** gecikme medyanı "
                      f"{statistics.median(x['gec_saat'] for x in gec):.1f} saat (0.50 temasından sonra)."]
        satir += ["", "| an | sembol | sınıf | kullanıcı 0 | kullanıcı 1 | motor 0 | motor 1 | Δ0 (mum) | Δ1 (mum) | motor known_at |",
                  "|---|---|---|---|---|---|---|---:|---:|---|"]
        for x in S:
            z, u0, u1 = x["z"], x["u0"], x["u1"]
            motor = (f"{z_tip0(z)} {z.anchor_0_time:%m-%d %H:%M} {z.anchor_0_price:g} | "
                     f"{'dip' if z_tip0(z) == 'tepe' else 'tepe'} {z.anchor_1_time:%m-%d %H:%M} "
                     f"{z.anchor_1_price:g} | {mum(z.anchor_0_time, u0.ts)} | "
                     f"{mum(z.anchor_1_time, u1.ts)} | {z.known_at:%m-%d %H:%M}") if z else "— | — | | |"
            satir.append(f"| {x['id']} | {x['sembol']} | {x['sinif']} | {u0.tip} {u0.ts:%m-%d %H:%M} "
                         f"{u0.fiyat:g} | {u1.tip} {u1.ts:%m-%d %H:%M} {u1.fiyat:g} | {motor} |")
        satir.append("")
        print(ad, dict(say), flush=True)
    satir += kural_tablosu(setup, V)
    import scripts.swing_secim as secim
    yan = OUT.with_name("eslestirme_son_supuren.md")
    secim.degerlendir("son_supuren", out=yan)  # adaylar son_supuren ile; ölçüt aynı
    satir += ["", f"Aday kuralla tüm adayların çift isabeti (ölçüt değişmeden): `{yan.as_posix()}` §2.", ""]
    OUT.write_text("\n".join(satir) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    rapor()
    sys.exit(0)
