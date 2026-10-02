"""İki sunucunun verisini tek `data/`'da birleştirir — göç (`docs/SERVER.md` "Göç planı").

    python -m scripts.birlestir --kaynak eski=göç/eski --kaynak xeon=göç/xeon \\
        --gecis 2026-10-08T12:00Z --kuru          # yalnızca rapor (geçiş kapısı)
    python -m scripts.birlestir --kaynak eski=göç/eski --kaynak xeon=göç/xeon \\
        --gecis 2026-10-08T12:00Z                 # yaz

Her kaynak kökü `pull_book --root` ile ayrı çekilmiş bir ağaçtır (`<kök>/data/...`).
Hedefte (`--hedef`, varsayılan `.`) zaten olan satırlar da kaynaktır, en düşük öncelikle:
birleştirme **hiçbir satırı silmez**.

| Veri | Anahtar | Çakışma |
|---|---|---|
| `trades/` | `id` (`fillId`) | aynı `id`, farklı `ts/price/qty/side` → **hata**, dosya yazılmaz |
| `book/` | `ts` dakikası | beklenir: `gecis`'ten önce ilk kaynak (eski), sonra ikinci (xeon) kazanır; `host` kolonu |
| `30m/`, `funding/` | `ts` | farklı değer → **hata**, dosya yazılmaz |

Çakışma varsa hiçbir şey sessizce seçilmez: o dosya atlanır, çıkış kodu 1 (CLAUDE.md #8).
Yazım atomik (geçici dosya + `replace`). İkinci koşu değişiklik bulmaz (idempotent).

Rapor (işlem akışı), sembol başına: **iki sunucuda da görülen `id` sayısı** (göçün asgari
şartı: paralel kayıt doğrulandı), her kaynağın ve birleşimin eksik `id` sayısı, yalnızca bir
kaynakta olan `id` sayısı.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

TUR = ("trades", "book", "30m", "funding")
TRADE_COLS = ["ts", "price", "qty", "side"]


class Cakisma(ValueError):
    pass


def eksik_id(ids: pd.Series) -> int:
    """`[min, max]` aralığında olmayan `id` sayısı (`trades_gap` yöntemi)."""
    u = ids.drop_duplicates()
    return 0 if u.empty else int(u.max() - u.min() + 1 - len(u))


def trades_birlestir(parca: list[tuple[str, pd.DataFrame]]) -> tuple[pd.DataFrame, dict]:
    """`id` birleşimi. Aynı `id` farklı içerikle → `Cakisma`."""
    df = pd.concat([d.assign(_k=ad) for ad, d in parca], ignore_index=True)
    tekil = df.drop_duplicates(["id", *TRADE_COLS])
    cift = tekil.id.duplicated(keep=False)
    if cift.any():
        raise Cakisma(f"{tekil[cift].id.nunique()} id farklı içerikle, ör. "
                      f"{tekil[cift].sort_values('id').head(2)[['id', *TRADE_COLS, '_k']].to_dict('records')}")
    kac = df.groupby("id")._k.nunique()
    sunucu = df[df._k != "hedef"].groupby("id")._k.nunique()
    rapor = {"eksik": {ad: eksik_id(d.id) for ad, d in parca},
             "tek_kaynak": {ad: int(d.id.isin(kac[kac == 1].index).sum()) for ad, d in parca},
             "ortak": int((sunucu > 1).sum())}  # iki sunucuda da görülen id (paralel kayıt)
    out = tekil.drop(columns="_k").drop_duplicates("id").sort_values("id").reset_index(drop=True)
    rapor["eksik"]["birlesim"] = eksik_id(out.id)
    return out, rapor


def book_birlestir(parca: list[tuple[str, pd.DataFrame]], sira: list[str],
                   gecis: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Dakika başına tek görüntü. `gecis` öncesi `sira` sırasıyla, sonrası tersiyle öncelik;
    `sira`'da olmayan (hedef) en son. Satırın geldiği kaynak `host` kolonunda."""
    df = pd.concat([d.assign(host=d["host"] if "host" in d else ad, _k=ad) for ad, d in parca],
                   ignore_index=True)
    df["_dk"] = df.ts.dt.floor("min")
    once = {ad: i for i, ad in enumerate(sira)}
    sonra = {ad: i for i, ad in enumerate(reversed(sira))}
    df["_o"] = [(once if dk < gecis else sonra).get(k, len(sira))
                for dk, k in zip(df._dk, df._k)]
    kac = df.groupby("_dk")._k.nunique()
    out = (df.sort_values(["_dk", "_o"]).drop_duplicates("_dk")
           .drop(columns=["_k", "_dk", "_o"]).reset_index(drop=True))
    return out, {"ikili_dakika": int((kac > 1).sum())}


def ts_birlestir(parca: list[tuple[str, pd.DataFrame]]) -> tuple[pd.DataFrame, dict]:
    """`ts` birleşimi; aynı `ts` farklı değerle → `Cakisma` (30m, funding)."""
    df = pd.concat([d for _, d in parca], ignore_index=True)
    tekil = df.drop_duplicates()
    cift = tekil.ts.duplicated(keep=False)
    if cift.any():
        raise Cakisma(f"{tekil[cift].ts.nunique()} ts farklı değerle, ör. "
                      f"{tekil[cift].sort_values('ts').head(2).to_dict('records')}")
    return tekil.sort_values("ts").reset_index(drop=True), {}


@dataclass
class Sonuc:
    yazilan: list[str] = field(default_factory=list)
    ayni: int = 0
    hata: dict[str, str] = field(default_factory=dict)
    trades: dict[str, dict] = field(default_factory=dict)  # sembol → toplam rapor
    ikili_dakika: int = 0


def birlestir(kaynaklar: dict[str, Path], hedef: Path, gecis: pd.Timestamp,
              kuru: bool = False) -> Sonuc:
    """Tüm dosyaları birleştirir. `kaynaklar` sıralı: ilk = eski, ikinci = yeni."""
    kokler = {**{ad: k for ad, k in kaynaklar.items()}, "hedef": hedef}
    yollar = sorted({p.relative_to(k).as_posix() for k in kokler.values()
                     for tur in TUR for p in k.glob(f"data/*/*/{tur}/*.parquet")})
    s = Sonuc()
    for rel in yollar:
        parca = [(ad, pd.read_parquet(k / rel)) for ad, k in kokler.items() if (k / rel).exists()]
        tur, sembol = rel.split("/")[3], rel.split("/")[2]
        try:
            if tur == "trades":
                out, r = trades_birlestir(parca)
                t = s.trades.setdefault(sembol, {"eksik": {}, "tek_kaynak": {}, "ortak": 0})
                t["ortak"] += r["ortak"]
                for alan in ("eksik", "tek_kaynak"):
                    for ad, v in r[alan].items():
                        t[alan][ad] = t[alan].get(ad, 0) + v
            elif tur == "book":
                out, r = book_birlestir(parca, list(kaynaklar), gecis)
                s.ikili_dakika += r["ikili_dakika"]
            else:
                out, _ = ts_birlestir(parca)
        except Cakisma as e:
            s.hata[rel] = str(e)
            continue
        hedef_yol = hedef / rel
        if hedef_yol.exists() and pd.read_parquet(hedef_yol).equals(out):
            s.ayni += 1
            continue
        s.yazilan.append(rel)
        if not kuru:
            hedef_yol.parent.mkdir(parents=True, exist_ok=True)
            tmp = hedef_yol.with_suffix(".tmp")
            out.to_parquet(tmp, index=False)
            tmp.replace(hedef_yol)
    return s


def main() -> int:
    p = argparse.ArgumentParser(description="Göç: iki sunucunun verisini birleştir")
    p.add_argument("--kaynak", action="append", required=True, metavar="AD=KÖK",
                   help="sırayla: önce eski, sonra yeni sunucu")
    p.add_argument("--gecis", required=True, help="defter önceliğinin döndüğü an (UTC)")
    p.add_argument("--hedef", type=Path, default=Path("."))
    p.add_argument("--kuru", action="store_true", help="yazma, yalnızca raporla")
    a = p.parse_args()
    kaynaklar = {k.split("=", 1)[0]: Path(k.split("=", 1)[1]) for k in a.kaynak}
    if "hedef" in kaynaklar or len(kaynaklar) < 2:
        sys.exit("en az iki kaynak; 'hedef' adı ayrılmış")
    s = birlestir(kaynaklar, a.hedef, pd.Timestamp(a.gecis).tz_convert("UTC"), a.kuru)
    print(f"{'yazılacak' if a.kuru else 'yazılan'} {len(s.yazilan)} · aynı {s.ayni} · "
          f"hata {len(s.hata)} · defterde iki kaynakta olan dakika {s.ikili_dakika}")
    for sembol, r in s.trades.items():
        print(f"  {sembol}: iki sunucuda ortak id {r['ortak']} · eksik id {r['eksik']} · "
              f"tek kaynakta {r['tek_kaynak']}")
    ortaksiz = [sem for sem, r in s.trades.items() if not r["ortak"]]
    print(f"paralel kayıt (göç asgari şartı): {len(s.trades) - len(ortaksiz)}/{len(s.trades)} "
          f"sembolde ortak id" + (f" · ORTAK YOK: {ortaksiz}" if ortaksiz else ""))
    for rel, e in s.hata.items():
        print(f"  HATA {rel}: {e}", file=sys.stderr)
    return 1 if s.hata else 0


if __name__ == "__main__":
    sys.exit(main())
