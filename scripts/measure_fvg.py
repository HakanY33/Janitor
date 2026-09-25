"""OPEN-23 · FVG anlamlılık ölçümü — `measure_ob.py`'nin FVG karşılığı.

    python -m scripts.measure_fvg a     # genişlik/medyan gövde oranının dağılımı
    python -m scripts.measure_fvg b     # dolum ufku: mitigasyon ve tam dolum oranları
    python -m scripts.measure_fvg c     # kesişim: p95 genişlik + 20 mumda dolmamış

Ölçüm koddaki tanımları **okur**, eşik aramaz (CLAUDE.md: self-tuning yasak).
Bulgular spec'e elle işlenir. `src/` altında hiçbir şey değişmez.

**Veri disiplini (`measure_ob.py` ile aynı).** Her sembolün yalnızca en eski
`TRAIN_FRAC` dilimi okunur; en yeni %20 bu koşuda **açılmaz**. Ufku dilimin sonuna
taşan FVG'ler ufka göre elenir — yoksa "henüz dolmadı" ile "bakacak mum kalmadı"
aynı kovaya düşerdi.

**Payda OB ile birebir aynıdır.** `reference_body` (son `BODY_LOOKBACK` mumun medyan
gövdesi, `shift(1)`) üretim fonksiyonudur; impuls eşiğinin kullandığı seriyi FVG
genişliği için tekrar kullanıyoruz. Böylece "4.0 = p95" ile buradaki p95 aynı
normalizasyon üzerinde okunur.

**Dikkat — iki p95 aynı şey değil.** OB'deki `4.0 = p95` *mumların* dağılımıdır
(mumların %5'i impuls sayılır). FVG'de eşik tespit etmiyor, tespit edilmişi
ayıklıyor: buradaki p95 *FVG'lerin* dağılımıdır (FVG'lerin %5'i). Taban oran farklı,
yoğunluk karşılaştırması (c)'de bu yüzden doğrudan mum/FVG üzerinden yapılır.

**Mitigasyon ve dolum `FVG.on_bar` semantiğidir**, burada yeniden tanımlanmaz:
mitige = fiyat boşluğa ilk girdi, dolum = karşı sınır geçildi. Vektörel yol
`dogrula()` ile üretim `replay()`ine karşı doğrulanır.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from scripts.measure_ob import (
    MIN_BARS,
    TF,
    TRAIN_FRAC,
    UFUKLAR,
    baslik,
    kaydet,
    liquidity_symbols,
    say,
    veri,
)
from src.features.fvg import BULLISH, detect_fvgs, replay
from src.features.ob import detect_order_blocks, reference_body

YUZDELER = (50, 75, 90, 95, 99)  # (a) istenen dilimler
ESIK_DILIMI = 95  # (c) "p95 üstü genişlik"
DOLUM_UFKU = 20  # (c) "20 mum içinde dolmamış"


def egitim_dilimi(symbol: str) -> pd.DataFrame | None:
    """Sembolün en eski `TRAIN_FRAC` dilimi. Kısa geçmişli sembol atlanır."""
    tam = veri(symbol)
    if tam.empty:
        return None
    df = tam.iloc[: int(len(tam) * TRAIN_FRAC)].reset_index(drop=True)
    return df if len(df) >= MIN_BARS else None


def ileri_uc(a: np.ndarray, h: int | None, en_kucuk: bool) -> np.ndarray:
    """`i` konumunda `a[i+1 .. i+h]` penceresinin uç değeri (h=None → dilim sonuna kadar).

    Pencere tamamlanmıyorsa NaN: ufku ayrılmış bölüme taşan FVG'ler böyle elenir.
    """
    uc = np.minimum if en_kucuk else np.maximum
    if h is None:
        yigin = uc.accumulate(a[::-1])[::-1]  # yigin[i] = uc(a[i..son])
        return np.append(yigin[1:], np.nan)
    s = pd.Series(a).rolling(h, min_periods=h)
    return (s.min() if en_kucuk else s.max()).shift(-h).to_numpy()


def sembol_kayitlari(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Eğitim dilimindeki her FVG için: genişlik oranı + ufuk başına mitigasyon/dolum."""
    fvgs = detect_fvgs(df, symbol, TF)
    if not fvgs:
        return pd.DataFrame()

    yer = {ts: i for i, ts in enumerate(df.ts)}
    i = np.array([yer[f.created_at] for f in fvgs])
    top = np.array([f.top for f in fvgs])
    bottom = np.array([f.bottom for f in fvgs])
    bull = np.array([f.direction == BULLISH for f in fvgs])
    ref = reference_body(df).to_numpy()[i]  # OB ile aynı payda

    low, high = df.low.to_numpy(), df.high.to_numpy()
    d = {"symbol": symbol, "i": i, "oran": (top - bottom) / ref}
    for h in (*UFUKLAR, None):
        dip = ileri_uc(low, h, True)[i]  # bullish: aşağıdan doldurulur
        tepe = ileri_uc(high, h, False)[i]  # bearish: yukarıdan doldurulur
        ad = "sinirsiz" if h is None else str(h)
        d[f"mit_{ad}"] = np.where(bull, dip <= top, tepe >= bottom)
        d[f"dol_{ad}"] = np.where(bull, dip <= bottom, tepe >= top)
        d[f"olculur_{ad}"] = ~np.isnan(dip)  # dip/tepe ayni konumlarda NaN

    out = pd.DataFrame(d)
    # Payda NaN (ilk mumlar) veya 0 (gövdesiz pencere) ise oran tanımsız - elenir.
    return out[np.isfinite(out.oran)].reset_index(drop=True)


def dogrula(symbol: str, df: pd.DataFrame, n: int = 3_000) -> None:
    """Vektörel yol ile üretim `replay()`i aynı sonucu vermeli (mitigasyon + dolum).

    Küçük bir dilimde çalışır: amaç semantik denetimi, performans değil.
    """
    dilim = df.iloc[:n].reset_index(drop=True)
    fvgs = detect_fvgs(dilim, symbol, TF)
    replay(fvgs, dilim)
    yer = {ts: i for i, ts in enumerate(dilim.ts)}
    k = sembol_kayitlari(symbol, dilim).set_index("i")

    for f in fvgs:
        i = yer[f.created_at]
        if i not in k.index:
            continue
        satir = k.loc[i]
        assert bool(satir.mit_sinirsiz) == (f.mitigated_at is not None), f"mitigasyon {i}"
        assert bool(satir.dol_sinirsiz) == (f.filled_at is not None), f"dolum {i}"
        for h in UFUKLAR:
            if not satir[f"olculur_{h}"]:
                continue
            for alan, sutun in (("mitigated_at", "mit"), ("filled_at", "dol")):
                an = getattr(f, alan)
                beklenen = an is not None and yer[an] - i <= h
                assert bool(satir[f"{sutun}_{h}"]) == beklenen, f"{sutun}_{h} @ {i}"
    print(f"  dogrulama: {len(fvgs):,} FVG, replay() ile birebir ayni", file=sys.stderr)


def topla(n_symbols: int, ob_da: bool = False) -> tuple[pd.DataFrame, dict, list[str]]:
    """Tüm sembolleri gezer. `ob_da` ise aynı dilimde OB sayısını da çıkarır."""
    kayitlar, mumlar, atlanan, dogrulandi = [], {}, [], False
    for j, s in enumerate(liquidity_symbols(n_symbols), 1):
        df = egitim_dilimi(s)
        if df is None:
            atlanan.append(s)
            print(f"  [{j}] {s:<28} atlandi", file=sys.stderr)
            continue
        if not dogrulandi:
            dogrula(s, df)
            dogrulandi = True
        k = sembol_kayitlari(s, df)
        kayitlar.append(k)
        mumlar[s] = {"mum": len(df), "fvg": len(k)}
        if ob_da:
            mumlar[s]["ob"] = len(detect_order_blocks(df, s, TF))
        print(f"  [{j}] {s:<28} {len(df):>7,} mum  {len(k):>6,} FVG"
              + (f"  {mumlar[s]['ob']:>5,} OB" if ob_da else ""), file=sys.stderr)
    if not kayitlar:
        sys.exit("olculebilir FVG yok - veri indirildi mi?")
    return pd.concat(kayitlar, ignore_index=True), mumlar, atlanan


def kapsam(d: pd.DataFrame, mumlar: dict, atlanan: list[str]) -> None:
    toplam = sum(v["mum"] for v in mumlar.values())
    say(f"  {len(mumlar)} sembol  ·  {toplam:,} mum  ·  {len(d):,} FVG"
        + (f"  ·  atlanan: {', '.join(atlanan)}" if atlanan else ""))
    say(f"  ham yogunluk: {toplam / len(d):.1f} mum/FVG")


# --- (a) genislik dagilimi ---------------------------------------------------

def part_a(n_symbols: int) -> None:
    d, mumlar, atlanan = topla(n_symbols)
    baslik(f"(a) FVG GENISLIK / MEDYAN GOVDE  ·  {TF}  ·  verinin en eski %{TRAIN_FRAC*100:.0f}'i")
    say("  Payda: son 20 mumun medyan govdesi (reference_body, OB ile ayni seri).")
    say("  Dagilim TESPIT EDILEN FVG'ler uzerinde. OB'deki 4.0 = p95 ise MUMLAR")
    say("  uzerindeydi - taban oran farkli, dogrudan karsilastirilamaz.")
    say("")
    kapsam(d, mumlar, atlanan)

    say("")
    say(f"  {'dilim':>6} {'oran':>8} {'ustundeki FVG':>14} {'mum/FVG':>9}")
    toplam = sum(v["mum"] for v in mumlar.values())
    for p in YUZDELER:
        esik = d.oran.quantile(p / 100)
        ustu = int((d.oran >= esik).sum())
        say(f"  p{p:<5} {esik:>8.2f} {ustu:>14,} {toplam / max(ustu, 1):>9.1f}")
    say("")
    say(f"  ortalama {d.oran.mean():.2f}  ·  min {d.oran.min():.2f}  ·  "
        f"maks {d.oran.max():.2f}")
    say(f"  >= 4.0 (OB esigi) olan FVG: {(d.oran >= 4.0).sum():,} "
        f"(%{(d.oran >= 4.0).mean()*100:.1f})")

    say("")
    say("  Sembol basina p95 - tek kuresel esik savunulabilir mi:")
    per = d.groupby("symbol").oran.quantile(0.95)
    say(f"    min {per.min():.2f}  medyan {per.median():.2f}  maks {per.max():.2f}  "
        f"(havuz p95 {d.oran.quantile(0.95):.2f})")
    for s, v in per.sort_values().items():
        say(f"      {s:<24} {v:>6.2f}")


# --- (b) dolum ufku ----------------------------------------------------------

def part_b(n_symbols: int) -> None:
    d, mumlar, atlanan = topla(n_symbols)
    baslik(f"(b) DOLUM UFKU  ·  {TF}  ·  verinin en eski %{TRAIN_FRAC*100:.0f}'i")
    say("  mitige = fiyat bosluga ilk girdi  ·  dolum = karsi sinir gecildi (FVG.on_bar)")
    say("  Ufuk = olusum mumundan (3. mum) sonra bakilan mum sayisi.")
    say("  Kuyrugu ufka yetmeyen FVG elenir - 'dolmadi' ile 'bakilamadi' ayri tutulur.")
    say("")
    kapsam(d, mumlar, atlanan)

    basliklar = [str(h) for h in UFUKLAR] + ["sinirsiz"]
    say("")
    say(f"  {'':<12}" + "".join(f"{('ufuk ' + ('sonsuz' if b == 'sinirsiz' else b)):>12}" for b in basliklar))
    say(f"  {'olculebilir':<12}" + "".join(
        f"{int(d[f'olculur_{b}'].sum()):>12,}" for b in basliklar))
    for sutun, etiket in (("mit", "mitige"), ("dol", "tam dolum")):
        say(f"  {etiket:<12}" + "".join(
            f"{d.loc[d[f'olculur_{b}'], f'{sutun}_{b}'].mean()*100:>11.1f}%"
            for b in basliklar))
    say("")
    say("  Yeni dolum (bir onceki ufka gore fark, puan):")
    for sutun, etiket in (("mit", "mitige"), ("dol", "tam dolum")):
        onceki, satir = 0.0, ""
        for b in basliklar:
            oran = d.loc[d[f"olculur_{b}"], f"{sutun}_{b}"].mean() * 100
            satir += f"{oran - onceki:>11.1f}p"
            onceki = oran
        say(f"  {etiket:<12}{satir}")

    say("")
    say("  Ayni tablo, genislik dilimine gore (tam dolum %, olculebilir FVG uzerinde):")
    kenar = [0, 50, 75, 90, 95, 100]
    say(f"  {'dilim':<12}" + "".join(f"{('ufuk ' + ('sonsuz' if b == 'sinirsiz' else b)):>12}" for b in basliklar) + f"{'n':>9}")
    for alt, ust in zip(kenar, kenar[1:]):
        lo, hi = d.oran.quantile(alt / 100), d.oran.quantile(ust / 100)
        m = (d.oran >= lo) & (d.oran <= hi if ust == 100 else d.oran < hi)
        say(f"  p{alt}-p{ust:<8}" + "".join(
            f"{d.loc[m & d[f'olculur_{b}'], f'dol_{b}'].mean()*100:>11.1f}%"
            for b in basliklar) + f"{int(m.sum()):>9,}")


# --- (c) kesisim -------------------------------------------------------------

def part_c(n_symbols: int) -> None:
    d, mumlar, atlanan = topla(n_symbols, ob_da=True)
    toplam = sum(v["mum"] for v in mumlar.values())
    ob_toplam = sum(v["ob"] for v in mumlar.values())
    esik = d.oran.quantile(ESIK_DILIMI / 100)

    baslik(f"(c) KESISIM  ·  p{ESIK_DILIMI} ustu genislik + {DOLUM_UFKU} mumda dolmamis")
    say(f"  Esik: oran >= {esik:.2f} (havuz p{ESIK_DILIMI}).  Hedef yogunluk: ~25 mum/FVG.")
    say(f"  '{DOLUM_UFKU} mumda dolmamis' = tam dolum yok; mitigasyon varyanti da verildi.")
    say("")
    kapsam(d, mumlar, atlanan)
    say(f"  ayni dilimde OB: {ob_toplam:,}  ->  {toplam / ob_toplam:.1f} mum/OB "
        f"(IMPULSE_MULT=4.0, karsilastirma tabani)")

    olculur = d[d[f"olculur_{DOLUM_UFKU}"]]
    genis = olculur.oran >= esik
    dolmadi = ~olculur[f"dol_{DOLUM_UFKU}"]
    mitigeyok = ~olculur[f"mit_{DOLUM_UFKU}"]

    say("")
    say(f"  Olculebilir FVG ({DOLUM_UFKU} mumluk kuyrugu olan): {len(olculur):,}")
    say(f"  {'filtre':<38} {'n':>8} {'olculebilirin %':>16} {'mum/FVG':>9}")
    for etiket, m in (
        ("hepsi", pd.Series(True, index=olculur.index)),
        (f"p{ESIK_DILIMI} ustu genislik", genis),
        (f"{DOLUM_UFKU} mumda dolmamis", dolmadi),
        (f"{DOLUM_UFKU} mumda mitige olmamis", mitigeyok),
        (f"genislik + dolmamis  [KESISIM]", genis & dolmadi),
        (f"genislik + mitige olmamis", genis & mitigeyok),
    ):
        n = int(m.sum())
        say(f"  {etiket:<38} {n:>8,} {n / len(olculur) * 100:>15.1f}% "
            f"{toplam / max(n, 1):>9.1f}")

    say("")
    say("  Bagimsiz olsalardi beklenen kesisim: "
        f"{genis.mean() * dolmadi.mean() * len(olculur):,.0f} FVG "
        f"(gerceklesen {int((genis & dolmadi).sum()):,})")

    say("")
    say(f"  Hangi genislik dilimi ~25 mum/FVG verir ({DOLUM_UFKU} mumda dolmamis sarti ile):")
    say(f"  {'dilim':>6} {'oran':>8} {'kesisim n':>11} {'mum/FVG':>9}")
    for p in (0, 25, 50, 60, 70, 75, 80, 85, 90, 95, 99):
        e = olculur.oran.quantile(p / 100)
        n = int(((olculur.oran >= e) & dolmadi).sum())
        say(f"  p{p:<5} {e:>8.2f} {n:>11,} {toplam / max(n, 1):>9.1f}")
    say("")
    say("  Tablo tarif eder, eslestirmez: esik secimi spec kararidir (self-tuning yasak).")


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-23 FVG anlamlilik olcumu")
    p.add_argument("part", choices=["a", "b", "c"])
    p.add_argument("--symbols", type=int, default=20)
    p.add_argument("--out")
    a = p.parse_args()

    {"a": part_a, "b": part_b, "c": part_c}[a.part](a.symbols)
    kaydet(a.out or f"logs/olcum_fvg_{a.part}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
