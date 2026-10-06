"""v4 puanlaması — ön kayıtlı doğrulama + OB etiketleri. Tek komut, tek bakış.

    python -m scripts.v4_puan       # docs/inceleme/v4/etiketler.json → docs/inceleme/v4/puan.md

**(a) OTE — ön kayıt** (`docs/inceleme/v2/adaylar.md`, 2026-10-05 ek): swing `B2` + eşleştirme
`son_supuren`, ölçütler v3'tekiyle aynı kod (`swing_secim.aday_olc`). Karar: çift isabet oranı
≥ `ESIK` (%28 = v3 örneklem içi %57'nin yarısı) → GEÇTİ, altı → KALDI. Etiketlenmemiş an varsa
karar verilmez, hata (CLAUDE.md #8) — eksik etiketle "bir kez" ölçüm yanlış olur.

**(b) OB** (sayfanın OB adımı, OTE'den ayrı): motorun gösterdiği OB'lerin doğruluk oranı
(doğru / (doğru + yanlış)), etiketsiz kalan OB, kaçırılan OB (`ob_eksik`; tıklanan mum motorun
bir OB'sinin 1. mumuysa "motorda vardı" ayrıca sayılır), ve doğru ↔ yanlış OB'lerin özellikleri:
yön, genişlik, mitigasyon, yaş, 2. mumun gövdesi ve 1–3. mum boşluğu (son 20 mumun medyan
gövdesine göre, `reference_body` — karar anında bilinen değer).

Açıklayıcıdır; (b) seçim ya da kural değiştirmez.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.swing_secim import aday_olc, capalar, ilk_050, veri
from src.features.candles import reference_body

ETIKET = Path("docs/inceleme/v4/etiketler.json")
OUT = Path("docs/inceleme/v4/puan.md")
ADAY, ESLESTIRME = "B2", "son_supuren"  # adaylar.md 2026-10-05 (ek) — değişmez
ESIK = 0.28
TF_SN = 1800


def etiketsiz(E: list[dict]) -> list[str]:
    """OTE etiketi tamamlanmamış anlar (sayfanın `tamam` ölçütü)."""
    return [r["id"] for r in E if not (
        r.get("secim") in ("setup_yok", "bot_dogru")
        or (r.get("secim") == "farkli" and r.get("capa_0") and r.get("capa_1")))]


def ote_puan(E: list[dict], V: dict) -> dict:
    """(a) Ön kayıt ölçütleri ve karar. `V`: sembol → (30m, 1m)."""
    eksik = etiketsiz(E)
    if eksik:
        raise ValueError(f"OTE etiketi eksik: {eksik} — karar verilmez")
    setup = [(r, c) for r in E if (c := capalar(r))]
    yok = [r for r in E if not capalar(r)]
    if not setup:
        raise ValueError("setup'lı an yok — oran tanımsız")
    son = {r["id"]: ilk_050(V[r["symbol"]][1], c0, c1) for r, (c0, c1) in setup}
    o = aday_olc(ADAY, ESLESTIRME, setup, yok, V, son)
    oran = o["cift"] / len(setup)
    return {**o, "n": len(setup), "n_yok": len(yok), "oran": oran,
            "karar": "GEÇTİ" if oran >= ESIK else "KALDI",
            "son_yok": [i for i, t in son.items() if t is None]}


def _ozellik(o: dict, r: dict, d30: pd.DataFrame | None) -> dict:
    karar = pd.Timestamp(r["karar_ts"], tz="UTC").timestamp()
    f = {"yon": o["yon"], "genislik_bps": (o["ust"] - o["alt"]) / o["alt"] * 1e4,
         "mitige": o["mit"] is not None, "yas_mum": (karar - o["t1"]) / TF_SN,
         "mitigasyona_mum": (o["mit"] - o["t3"]) / TF_SN - 1 if o["mit"] else None}
    if d30 is not None:
        i = int(d30.ts.searchsorted(pd.Timestamp(o["t1"], unit="s", tz="UTC")))
        ref = reference_body(d30.iloc[max(0, i - 25):i + 3]).iloc[-2]  # 2. mumdaki medyan (shift'li)
        m1, m2, m3 = (d30.iloc[i + k] for k in range(3))
        bosluk = (m3.low - m1.high) if o["yon"] == "talep" else (m1.low - m3.high)
        f["govde2_ref"] = abs(m2.close - m2.open) / ref if ref else None
        f["bosluk_ref"] = bosluk / ref if ref else None
    return f


def ob_puan(E: list[dict], V: dict | None = None) -> dict:
    """(b) OB etiketleri. `V` verilmezse mum özellikleri hesaplanmaz."""
    satir, acilmadi, eksik, vardi = [], [], 0, 0
    for r in E:
        if r.get("ob_liste") is None or not r.get("ob_acildi"):
            acilmadi.append(r["id"])
            continue
        d30 = V[r["symbol"]][0] if V else None
        for o in r["ob_liste"]:
            satir.append({"an": r["id"], "id": o["id"], "etiket": r.get("ob", {}).get(o["id"]),
                          **_ozellik(o, r, d30)})
        t1ler = {o["t1"] for o in r["ob_liste"]}
        eksik += len(r.get("ob_eksik", []))
        vardi += sum(x["ts"] in t1ler for x in r.get("ob_eksik", []))
    say = Counter(s["etiket"] for s in satir)
    d, y = say.get("dogru", 0), say.get("yanlis", 0)
    gruplar = {}
    for et in ("dogru", "yanlis"):
        g = [s for s in satir if s["etiket"] == et]
        med = lambda k: statistics.median(v) if (v := [s[k] for s in g if s.get(k) is not None]) else None
        gruplar[et] = {"n": len(g), "talep": sum(s["yon"] == "talep" for s in g),
                       "mitige": sum(s["mitige"] for s in g),
                       **{k: med(k) for k in ("genislik_bps", "yas_mum", "mitigasyona_mum",
                                              "govde2_ref", "bosluk_ref")}}
    return {"ob": len(satir), "dogru": d, "yanlis": y, "etiketsiz": say.get(None, 0),
            "dogruluk": d / (d + y) if d + y else None, "kacirilan": eksik,
            "kacirilan_motorda_vardi": vardi, "acilmadi": acilmadi, "gruplar": gruplar,
            "an_basina_ob": len(satir) / max(1, len(E) - len(acilmadi))}


def rapor(a: dict, b: dict, kaynak: Path) -> str:
    g = b["gruplar"]
    f = lambda v, n=1: "—" if v is None else f"{v:.{n}f}"
    satirlar = [
        "# v4 puanı", "",
        f"Kaynak `{kaynak.as_posix()}` · `scripts/v4_puan.py` · ön kayıt `docs/inceleme/v2/adaylar.md` "
        f"(2026-10-05 ek): `{ADAY}` + `{ESLESTIRME}`, eşik %{ESIK * 100:.0f}.", "",
        "## (a) OTE — ön kayıtlı doğrulama", "",
        f"**{a['karar']}** — çift isabet **{a['cift']}/{a['n']} ({a['oran']:.0%})**, eşik %{ESIK * 100:.0f}.", "",
        "| ölçüt | değer |", "|---|---:|",
        f"| setup'lı / setup yok | {a['n']} / {a['n_yok']} |",
        f"| 0 geri çağırma | {a['r0']}/{a['n']} |", f"| 1 geri çağırma | {a['r1']}/{a['n']} |",
        f"| yanlış alarm (rastgele, setup yok) | {a['fa_r']}/{a['n_yok']} |",
        f"| teyit gecikmesi medyanı (saat) | {f(a['gec'])} |",
        f"| 0.50 teması eğitim diliminde yok | {len(a['son_yok'])} |",
        f"| isabet eden anlar | {', '.join(a['isabet']) or '—'} |", "",
        "## (b) OB etiketleri (açıklayıcı)", "",
        f"Motorun gösterdiği {b['ob']} OB: doğru {b['dogru']}, yanlış {b['yanlis']}, etiketsiz "
        f"{b['etiketsiz']} → **doğruluk {f(b['dogruluk'] and b['dogruluk'] * 100, 0)}%**. "
        f"Kaçırılan (kullanıcının eklediği) {b['kacirilan']}"
        f" (bunların {b['kacirilan_motorda_vardi']}'i motorun bir OB'siyle aynı 1. mum). "
        f"OB adımı açılmayan an: {len(b['acilmadi'])}.", "",
        "| özellik (medyan) | doğru | yanlış |", "|---|---:|---:|",
        f"| OB sayısı | {g['dogru']['n']} | {g['yanlis']['n']} |",
        f"| talep / toplam | {g['dogru']['talep']}/{g['dogru']['n']} | {g['yanlis']['talep']}/{g['yanlis']['n']} |",
        f"| karar anında mitige | {g['dogru']['mitige']}/{g['dogru']['n']} | {g['yanlis']['mitige']}/{g['yanlis']['n']} |",
        *(f"| {ad} | {f(g['dogru'][k], 2)} | {f(g['yanlis'][k], 2)} |" for ad, k in (
            ("genişlik (bps)", "genislik_bps"), ("yaş (mum, karara)", "yas_mum"),
            ("mitigasyona kadar (mum)", "mitigasyona_mum"),
            ("2. mum gövdesi / medyan gövde", "govde2_ref"),
            ("1–3. mum boşluğu / medyan gövde", "bosluk_ref"))), ""]
    return "\n".join(satirlar) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--etiket", type=Path, default=ETIKET)
    p.add_argument("--out", type=Path, default=OUT)
    x = p.parse_args()
    E = json.loads(x.etiket.read_text(encoding="utf-8"))
    V = {s: veri(s) for s in sorted({r["symbol"] for r in E})}
    a, b = ote_puan(E, V), ob_puan(E, V)
    x.out.write_text(rapor(a, b, x.etiket), encoding="utf-8")
    print(f"{x.out} · OTE {a['karar']} {a['cift']}/{a['n']} · OB doğruluk {b['dogruluk']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
