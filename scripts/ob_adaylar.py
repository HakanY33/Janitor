"""v4 · OB aday kuralları — ön kayıtlı uyum ölçümü (`docs/inceleme/v4/ob_adaylar.md`).

    python -m scripts.ob_adaylar     # → docs/inceleme/v4/ob_adaylar_sonuc.md

Kural tanımları ön kayıttaki gibidir: A (ardışık OB'ler: A1 hepsi geçersiz, A2 sonuncusu, A3 ilki),
B (BoS: OB'den başlayan hareket, fiyat bölgeye ilk dönmeden, son karşı `B2` swing'ini kapanışla
kırar), birleşimler. Yalnızca karar anında kapanmış 30m mumları kullanılır (CLAUDE.md #3).
Açıklayıcı bir ölçümdür: seçim ön kayıttaki kurala göre yapılır, spec'e elle yazılır.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from scripts.swing_secim import aday_b
from src.data import collect
from src.features.fvg import BULLISH
from src.features.ob import OrderBlock, detect_order_blocks
from src.features.structure import HIGH, LOW, Swing

ETIKET = Path("docs/inceleme/v4/etiketler.json")
OUT = Path("docs/inceleme/v4/ob_adaylar_sonuc.md")
HARIC = {"r28", "r29"}  # gövde çizimi (kullanıcı notu)
TF = pd.Timedelta("30m")
ADAYLAR = ["A1", "A2", "A3", "B", "A1+B", "A2+B", "A3+B"]  # ön kayıt sırası


def ardisik(obs: list[OrderBlock], varyant: str) -> set[str]:
    """A · geçerli `ob_id`'ler. Seri = araya ters yön girmeden gelen aynı yönlü OB'ler."""
    obs = sorted(obs, key=lambda o: o.created_at)
    seriler: list[list[OrderBlock]] = []
    for o in obs:
        if seriler and seriler[-1][0].direction == o.direction:
            seriler[-1].append(o)
        else:
            seriler.append([o])
    gecerli = set()
    for s in seriler:
        if len(s) == 1 or varyant == "A0":
            gecerli |= {o.ob_id for o in s}
        elif varyant == "A2":
            gecerli.add(s[-1].ob_id)
        elif varyant == "A3":
            gecerli.add(s[0].ob_id)
    return gecerli


def bos(o: OrderBlock, df: pd.DataFrame, swings: list[Swing]) -> bool:
    """B · OB'den başlayan hareket son karşı swing'i kapanışla kırdı mı (bölgeye ilk dönüşten önce)."""
    tip = HIGH if o.direction == BULLISH else LOW
    once = [s for s in swings if s.kind == tip and s.ts < o.created_at]
    if not once:
        return False
    seviye = once[-1].price
    for r in df[df.ts > o.created_at].itertuples():
        if r.ts > o.impulse_at and r.low <= o.top and r.high >= o.bottom:
            return False  # bölgeye döndü: hareket bitti
        if (r.close > seviye) if o.direction == BULLISH else (r.close < seviye):
            return True
    return False


def gecerli(aday: str, obs: list[OrderBlock], df: pd.DataFrame, swings: list[Swing]) -> set[str]:
    a = next((p for p in aday.split("+") if p.startswith("A")), "A0")
    g = ardisik(obs, a)
    if "B" in aday.split("+"):
        g = {o.ob_id for o in obs if o.ob_id in g and bos(o, df, swings)}
    return g


def olc() -> tuple[dict, int]:
    E = json.loads(ETIKET.read_text(encoding="utf-8"))
    sayac = {a: {"gd": 0, "gy": 0, "xd": 0, "xy": 0} for a in ["A0", *ADAYLAR]}
    n = 0
    for e in E:
        if e["id"] in HARIC or not e.get("ob"):
            continue
        karar = pd.Timestamp(e["karar_ts"], tz="UTC")
        d30 = collect.read_parquet("bingx", e["symbol"], "30m")
        df = d30[d30.ts + TF <= karar].reset_index(drop=True)
        obs, swings = detect_order_blocks(df, e["symbol"], "30m"), aday_b(df, e["symbol"], 2)
        kim = {o["id"]: o["ob_id"] for o in e["ob_liste"]}
        etiket = {kim[k]: v for k, v in e["ob"].items() if v in ("dogru", "yanlis")}
        assert etiket.keys() <= {o.ob_id for o in obs}, e["id"]
        n += len(etiket)
        for a in sayac:
            g = gecerli(a, obs, df, swings)
            for oid, v in etiket.items():
                sayac[a][("g" if oid in g else "x") + v[0]] += 1
    return sayac, n


def main() -> int:
    sayac, n = olc()
    uyum = {a: (s["gd"] + s["xy"]) for a, s in sayac.items()}
    sec = max(ADAYLAR, key=lambda a: (uyum[a], -a.count("+"), -ADAYLAR.index(a)))
    karar = sec if uyum[sec] > uyum["A0"] else None
    satir = [f"| `{a}` | {uyum[a]}/{n} ({uyum[a] / n:.0%}) | {s['gd']} | {s['gy']} | {s['xd']} | {s['xy']} |"
             for a, s in sayac.items()]
    OUT.write_text("\n".join([
        "# v4 · OB aday kuralları — sonuç", "",
        f"Ön kayıt `docs/inceleme/v4/ob_adaylar.md` · `scripts/ob_adaylar.py` · {n} etiketli OB "
        "(r28, r29 ve etiketsizler hariç).", "",
        "| aday | uyum | geçerli · doğru | geçerli · yanlış | geçersiz · doğru | geçersiz · yanlış |",
        "|---|---:|---:|---:|---:|---:|", *satir, "",
        (f"**Seçilen: `{karar}`** (uyum {uyum[karar]}/{n}, taban `A0` {uyum['A0']}/{n})." if karar else
         f"**Kural seçilmedi:** en iyi aday `{sec}` ({uyum[sec]}/{n}) tabanı (`A0` {uyum['A0']}/{n}) geçmiyor."),
        "", "**Sınır:** seçim tek bir etiket setine (bir kullanıcı, v4) dayanıyor; örneklem içidir, "
        "bağımsız doğrulaması yok.", ""]), encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
