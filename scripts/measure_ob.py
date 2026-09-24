"""OPEN-23 · OB anlamlılık ölçümü. Kaynak kodu değiştirmez, sabitleri okur.

    python -m scripts.measure_ob a          # yoğunluk: IMPULSE_MULT 4.0 ne kadar filtreledi
    python -m scripts.measure_ob b          # delinme oranı, 5/10/20/50 mum ufkunda
    python -m scripts.measure_ob rank       # likiditeye göre sembol sıralaması (ağa çıkar)
    python -m scripts.measure_ob c          # hipotez testi, çok sembollü

Ölçüm koddaki eşikleri **okur**, kendi değer aramaz (CLAUDE.md: self-tuning yasak).
Bulgular spec'e elle işlenir.

**Veri ayrımı (aşırı uyum koruması, `OPEN-23`).** (c) her sembolün mum sayısına göre
en eski `TRAIN_FRAC` dilimini okur. En yeni %20 bu koşuda **açılmaz** — doğrulama için
ayrılmıştır. Ufku ayrılmış bölüme taşan OB'ler elenir, yoksa menzil ölçümü sınırdan
sızardı.

**İki vekil ölçüt.** Hipotez 4 ve 5'in girdisi spec'te sayısallaştırılmadı; buradaki
karşılıkları yalnızca ölçüm içindir, karar hattına girmez (`src/` altında yer almazlar):

- *4h+ yön* (`R-ZONE-07`): 30m'den türetilen 4h mumlarda kapanış, 20 mumluk SMA'nın
  üstünde mi. `OPEN-24` — spec "yön 4h+ ile belirlenir" diyor, ölçütü vermiyor.
- *Likidite süpürmesi* (`R-ZONE-02`): OB mumunun kendisi, önceki 20 mumun en düşüğünü
  (bearish için en yükseğini) aşmış mı.
  ponytail: leg tespiti (`OPEN-01`) gelince gerçek swing ucuyla değiştirilir.

**Komşuluk penceresi (`OPEN-25`).** `evaluate_strength` kapsamı çağırana bırakır ("hangi
TF, ne kadar geçmiş"). Tüm geçmiş verilirse `opposite_ob` ilk birkaç OB'den sonra **her
zaman** doğrudur (ölçüldü: NEAR'da %100) ve H2 test edilemez hâle gelir. R-ADD-05 zaten
komşuluktan söz ediyor ("ardı ardına olunca"), bu yüzden H2/H3 son `NEIGHBOR_BARS` mumun
OB'leriyle ölçülür. Pencere spec'te verilmedi — sayı bir **ölçüm tercihidir**, karar
hattına girmez. H1 penceresiz: dolmamış bir FVG tanımı gereği hâlâ açıktır, yaşı onu
geçersiz kılmaz.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import collect
from src.features.fvg import detect_fvgs, replay
from src.features.ob import (
    BODY_LOOKBACK,
    BULLISH,
    IMPULSE_MULT,
    detect_order_blocks,
    evaluate_strength,
    pierce_time,
)

EXCHANGE = "bingx"
NEAR = "NEAR/USDT:USDT"
TF = "30m"
# STRATEGY_SPEC §0 referans zone'unun penceresi — OPEN-23'teki 17 OB / 21 FVG buradan.
PENCERE = (pd.Timestamp("2026-09-08 13:30", tz="UTC"), pd.Timestamp("2026-09-10 12:00", tz="UTC"))
UFUKLAR = (5, 10, 20, 50)  # (b) delinme ufku, (c) menzil ufku
TRAIN_FRAC = 0.80  # (c) en yeni %20 doğrulama için ayrıldı, okunmaz
SWEEP_LOOKBACK = 20  # (c) likidite süpürmesi vekili
NEIGHBOR_BARS = 50  # (c) H2/H3 komşuluk penceresi — OPEN-25, bkz. modül docstring
HTF_TF, HTF_SMA = "4h", 20  # (c) yön vekili
MIN_BARS = 5_000  # (c) eğitim diliminde bundan az mumu olan sembol atlanır
LIQ_PATH = Path("data") / EXCHANGE / "liquidity.json"  # universe/ disinda: orasi tarihli anlik goruntuler
# BingX'in tokenlestirilmis emtia/endeks kontratlari (altin, gumus, WTI, Brent). Hacimde
# ust siralarda ama kripto degil: farkli mikroyapi, farkli seans. Kapsam disi (CLAUDE.md).
NON_CRYPTO = ("NCCO",)

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line)


def kaydet(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {path}")


def veri(symbol: str = NEAR, tf: str = TF, start=None, end=None) -> pd.DataFrame:
    df = collect.read_parquet(EXCHANGE, symbol, tf)
    if start is not None:
        df = df[df.ts >= start]
    if end is not None:
        df = df[df.ts <= end]
    return df.reset_index(drop=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 78)
    say(metin)
    say("=" * 78)


# --- (a) yogunluk ------------------------------------------------------------

def part_a() -> None:
    """IMPULSE_MULT 2.0 -> 4.0 yoğunluğu ne kadar düşürdü (OPEN-23'teki 17/21 ile)."""
    baslik(f"(a) TESPIT YOGUNLUGU  ·  IMPULSE_MULT = {IMPULSE_MULT}  ·  {NEAR} {TF}")
    say("  FVG eşikten bağımsız: sayısı yalnızca referans olarak verilir.")
    say("  1m tespit için kapalı (R-ZONE-09) — karşılaştırma 5m ve üstünde yapılır.")

    for etiket, (start, end) in {
        f"OPEN-23 penceresi  {PENCERE[0]:%m-%d %H:%M} -> {PENCERE[1]:%m-%d %H:%M}": PENCERE,
        "tüm geçmiş": (None, None),
    }.items():
        df = veri(start=start, end=end)
        fvgs = detect_fvgs(df, NEAR, TF)
        say("")
        say(f"{etiket}  ·  {len(df):,} mum")
        say(f"  {'esik':<6} {'OB':>6} {'OB basina mum':>14} {'FVG':>6} {'FVG basina mum':>15}")
        for mult in (2.0, IMPULSE_MULT):
            obs = detect_order_blocks(df, NEAR, TF, body_mult=mult)
            say(f"  {mult:<6.1f} {len(obs):>6,} {len(df) / max(len(obs), 1):>14.1f} "
                f"{len(fvgs):>6,} {len(df) / max(len(fvgs), 1):>15.1f}")
        if (start, end) == PENCERE:
            obs = detect_order_blocks(df, NEAR, TF)
            say(f"  OPEN-23 kaydi: 17 OB / 21 FVG (esik 2.0)  ->  "
                f"simdi {len(obs)} OB / {len(fvgs)} FVG")


# --- (b) ufuklu delinme ------------------------------------------------------

def pierce_within(ob, df: pd.DataFrame, i_imp: int, horizon: int):
    """OB, impulstan sonraki `horizon` mum içinde delindi mi.

    `pierce_time` üretim fonksiyonudur; burada yalnızca göreceği pencere kısaltılır.
    Pencere `BODY_LOOKBACK` mum geriden başlar: `reference_body` medyanı geçmişe bakar,
    daha kısa bir dilimde eşik farklı çıkardı. Delinme mumunda pencere içi geçmiş tam
    df ile birebir aynıdır, çünkü rolling(20) o noktada tamamen dilimin içinde kalır.
    """
    pencere = df.iloc[max(0, i_imp - BODY_LOOKBACK): i_imp + 1 + horizon]
    return pierce_time(ob, pencere)


def part_b(symbol: str = NEAR) -> None:
    """Yatay ufuklu delinme oranı bilgi taşımıyor; ufka göre ayrıştır."""
    df = veri(symbol)
    obs = detect_order_blocks(df, symbol, TF)
    idx = {ts: i for i, ts in enumerate(df.ts)}
    baslik(f"(b) DELINME, UFKA GORE  ·  {symbol} {TF}  ·  {len(df):,} mum  ·  {len(obs):,} OB")
    say(f"  {df.ts.iloc[0]:%Y-%m-%d} -> {df.ts.iloc[-1]:%Y-%m-%d}")
    say("  Ufuk = impuls mumundan sonra bakilan mum sayisi. Kuyrugu ufka yetmeyen OB elenir.")
    say("")
    say(f"  {'ufuk':>5} {'olculebilir OB':>15} {'delinen':>9} {'oran':>8} {'yeni delinme':>13}")

    onceki = 0.0
    for h in UFUKLAR:
        olculen = [(ob, idx[ob.impulse_at]) for ob in obs if idx[ob.impulse_at] + h < len(df)]
        delinen = sum(pierce_within(ob, df, i, h) is not None for ob, i in olculen)
        oran = delinen / max(len(olculen), 1) * 100
        say(f"  {h:>5} {len(olculen):>15,} {delinen:>9,} {oran:>7.1f}% {oran - onceki:>12.1f}p")
        onceki = oran

    sonsuz = sum(pierce_time(ob, df) is not None for ob in obs)
    say(f"  {'sinirsiz':>5} {len(obs):>15,} {sonsuz:>9,} {sonsuz / len(obs) * 100:>7.1f}% "
        f"{sonsuz / len(obs) * 100 - onceki:>12.1f}p")
    say("")
    say("  Onceki kayit: esik 2.0, ufuksuz, 30m 2026-04'ten itibaren -> %88.9.")
    say("  Ufuksuz oran 'yeterince beklersen her OB delinir' der; karar icin gereken,")
    say("  OB'nin ise yarayacagi pencerede delinip delinmedigidir.")


# --- likidite siralamasi (aga cikar) -----------------------------------------

def part_rank(n: int = 20) -> list[str]:
    """Borsanın o anki 24s hacmine göre ilk n perpetual. Sonuç diske yazılır.

    `NON_CRYPTO` önekli kontratlar elenir: kapsam kripto vadeli.

    Sıralama **bugünün** hacmiyle yapılır; geçmiş hacim sıralaması elde yok. Seçim bu
    yüzden survivorship taşır (bugün likit olan). Soru aşırı uyum değil hipotez ayrımı
    olduğu için kabul edildi ve raporda yazılı.
    """
    ex = collect.exchange(EXCHANGE)
    evren = set(collect.load_universe(EXCHANGE)["symbols"])
    tickers = ex.fetch_tickers()
    hacim = {
        s: t.get("quoteVolume") or 0.0
        for s, t in tickers.items()
        if s in evren and s.endswith("/USDT:USDT") and not s.startswith(NON_CRYPTO)
    }
    sirali = sorted(hacim, key=hacim.get, reverse=True)[:n]
    LIQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIQ_PATH.write_text(json.dumps({
        "as_of": pd.Timestamp.now("UTC").isoformat(),
        "symbols": sirali,
        "quote_volume": {s: hacim[s] for s in sirali},
    }, indent=1), encoding="utf-8")
    baslik(f"LIKIDITE SIRALAMASI  ·  {EXCHANGE}  ·  ilk {n}")
    for i, s in enumerate(sirali, 1):
        say(f"  {i:>2} {s:<28} 24s hacim {hacim[s]:>18,.0f}")
    say(f"  -> {LIQ_PATH}")
    say(f"  indir: python -m scripts.backfill --timeframe {TF} --symbols " + " ".join(sirali))
    return sirali


def liquidity_symbols(n: int) -> list[str]:
    if not LIQ_PATH.exists():
        sys.exit(f"{LIQ_PATH} yok - once: python -m scripts.measure_ob rank")
    return json.loads(LIQ_PATH.read_text(encoding="utf-8"))["symbols"][:n]


# --- (c) hipotez testi -------------------------------------------------------

# Bayrak varken menzilin hangi yone gitmesi bekleniyor. Hipotez metinlerinden okunur:
# "daha genis uretir" -> +1, "menzili dusurur" -> -1.
YON = {"fvg_icinde": +1, "ters_ob": -1, "ardisik": -1, "htf_uyumlu": +1, "supurme": +1}

HIPOTEZLER = {
    "fvg_icinde": "H1 · icinde dolmamis FVG olan OB daha genis menzil uretir  (R-ADD-05)",
    "ters_ob": "H2 · ters yonlu OB varligi menzili dusurur                 (R-ADD-05)",
    "ardisik": "H3 · ardisik ayni yonlu OB serisi menzili dusurur           (R-ADD-05)",
    "htf_uyumlu": "H4 · 4h+ yon ile uyumlu OB daha genis menzil uretir         (R-ZONE-07)",
    "supurme": "H5 · likidite supurmesi sonrasi olusan OB daha gucludur     (R-ZONE-02)",
}


def htf_yon(df: pd.DataFrame) -> pd.DataFrame:
    """30m'den türetilen 4h yön serisi. `known_at` = mumun kapandığı an.

    Look-ahead (CLAUDE.md #3): bir OB yalnızca impuls mumu kapanana kadar **kapanmış**
    4h mumları görebilir; içinde bulunduğu 4h mumunu göremez.
    """
    htf = (
        df.set_index("ts")
        .resample(HTF_TF, closed="left", label="left")
        .agg(close=("close", "last"))
        .dropna()
    )
    htf["known_at"] = htf.index + pd.Timedelta(HTF_TF)
    htf["up"] = htf.close > htf.close.rolling(HTF_SMA).mean()
    return htf.reset_index(drop=True)


def supurme_bayragi(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Her mum için: önceki `SWEEP_LOOKBACK` mumun dibini/tepesini aştı mı."""
    alt = df.low.rolling(SWEEP_LOOKBACK).min().shift(1).to_numpy()
    ust = df.high.rolling(SWEEP_LOOKBACK).max().shift(1).to_numpy()
    return df.low.to_numpy() < alt, df.high.to_numpy() > ust


def sembol_kayitlari(symbol: str) -> tuple[list[dict], str]:
    """Bir sembolün eğitim dilimindeki her OB'si için bayraklar + menzil."""
    tam = veri(symbol)
    if tam.empty:
        return [], "veri yok"
    df = tam.iloc[:int(len(tam) * TRAIN_FRAC)].reset_index(drop=True)  # en yeni %20 acilmaz
    del tam
    if len(df) < MIN_BARS:
        return [], f"egitim dilimi {len(df):,} mum (< {MIN_BARS:,})"

    obs = detect_order_blocks(df, symbol, TF)
    fvgs = detect_fvgs(df, symbol, TF)
    replay(fvgs, df)
    # H1 icin yalnizca OB fiyat bandini kesen bosluklar aday. Kesmeyenleri elemek
    # `evaluate_strength`in sonucunu degistirmez (`overlaps` zaten onlari eliyor), ama
    # sembol basina milyonlarca dataclass erisimini numpy maskesine indirir.
    f_top = np.array([f.top for f in fvgs])
    f_bottom = np.array([f.bottom for f in fvgs])
    htf = htf_yon(df)
    htf_bilinir, htf_up = htf.known_at.to_numpy(), htf.up.to_numpy()
    supuruldu_alt, supuruldu_ust = supurme_bayragi(df)
    idx = {ts: i for i, ts in enumerate(df.ts)}
    ob_zaman = np.array([o.impulse_at for o in obs])  # H2/H3 komsuluk penceresi icin
    high, low, close = df.high.to_numpy(), df.low.to_numpy(), df.close.to_numpy()
    bar = pd.Timedelta(TF)
    ufuk_max = max(UFUKLAR)

    kayitlar = []
    for ob in obs:
        i_imp, i_ob = idx[ob.impulse_at], idx[ob.created_at]
        if i_imp + ufuk_max >= len(df):  # ufku ayrilmis bolume tasiyor - elenir
            continue
        # 4h yon: impuls mumu kapandiginda bilinen son 4h mumu
        j = int(np.searchsorted(htf_bilinir, ob.impulse_at + bar, side="right")) - 1
        if j < HTF_SMA:
            continue  # SMA henuz oturmadi
        komsu = slice(int(np.searchsorted(ob_zaman, df.ts[max(0, i_imp - NEIGHBOR_BARS)])), None)
        aday = [fvgs[k] for k in np.flatnonzero((f_bottom <= ob.top) & (f_top >= ob.bottom))]
        guc = evaluate_strength(ob, aday, obs[komsu])
        bull = ob.direction == BULLISH
        taban = ob.top if bull else ob.bottom
        kayit = {
            "symbol": symbol,
            "fvg_icinde": guc.fvg_inside_unfilled,
            "ters_ob": guc.opposite_ob,
            "ardisik": guc.consecutive_obs,
            "htf_uyumlu": bool(htf_up[j]) == bull,
            "supurme": bool(supuruldu_alt[i_ob] if bull else supuruldu_ust[i_ob]),
        }
        for h in UFUKLAR:
            son = slice(i_imp + 1, i_imp + 1 + h)
            uc = high[son].max() if bull else low[son].min()
            kayit[f"menzil_{h}"] = (uc - taban if bull else taban - uc) / taban * 100
            # Ikinci taban: impuls kapanisi. OB siniri bir supurme mumunda uca oturur;
            # ayni fark her iki tabanda da ayni yonde cikmazsa bulgu olcum artifaktidir.
            kapanis = close[i_imp]
            kayit[f"imp_{h}"] = (uc - kapanis if bull else kapanis - uc) / kapanis * 100
        kayitlar.append(kayit)
    return kayitlar, ""


def welch_t(a: np.ndarray, b: np.ndarray) -> float:
    """İki grup ortalaması arasındaki Welch t. |t| > 2 kabaca 'gürültü değil'."""
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    payda = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float("nan") if payda == 0 else float((a.mean() - b.mean()) / payda)


def part_c(n_symbols: int, olcum: str, csv: str | None = None) -> None:
    symbols = liquidity_symbols(n_symbols)
    baslik(f"(c) HIPOTEZ TESTI  ·  {len(symbols)} sembol  ·  {TF}  ·  "
           f"verinin en eski %{TRAIN_FRAC * 100:.0f}'i")
    say("  Menzil: impulstan sonraki N mumda yon lehine en uzak nokta, OB sinirindan")
    say(f"  itibaren fiyatin %'si. Birincil olcum: {olcum}.")
    say("  Asiri uyum korumasi: en yeni %20 hic okunmadi (dogrulama icin ayrildi).")
    say(f"  H2/H3 komsuluk penceresi: son {NEIGHBOR_BARS} mum (OPEN-25). H1 penceresiz.")
    say("  Sembol secimi bugunun 24s hacmine gore - survivorship tasir.")

    kayitlar, atlanan = [], []
    for i, s in enumerate(symbols, 1):
        k, neden = sembol_kayitlari(s)
        kayitlar.extend(k) if k else atlanan.append(f"{s} ({neden})")
        print(f"  [{i}/{len(symbols)}] {s:<28} {len(k):>6,} OB {neden}", file=sys.stderr)
    if not kayitlar:
        sys.exit("olculebilir OB yok - veri indirildi mi?")

    d = pd.DataFrame(kayitlar)
    if csv:
        d.to_csv(csv, index=False)
    say("")
    say(f"  olculen OB: {len(d):,}  ·  sembol: {d.symbol.nunique()}"
        + (f"  ·  atlanan: {', '.join(atlanan)}" if atlanan else ""))
    say(f"  menzil dagilimi: ortalama {d[olcum].mean():.2f}%  medyan {d[olcum].median():.2f}%"
        f"  p10 {d[olcum].quantile(.1):.2f}%  p90 {d[olcum].quantile(.9):.2f}%")

    say("")
    say(f"  {'hipotez':<11} {'bayrak':>7} {'n':>7} {'ort %':>7} {'medyan':>7} "
        f"{'fark':>7} {'t':>6} {'lehte':>8} {'sonuc':<12}")
    for ad in HIPOTEZLER:
        var, yok = d[d[ad]][olcum], d[~d[ad]][olcum]
        if not len(var) or not len(yok):
            say(f"  {ad:<11} tek grup: bayrak %{d[ad].mean() * 100:.0f} - ayrim yok")
            continue
        # Sembol ici fark: olcekleri farkli semboller havuzda birbirini ezmesin.
        icsel = [
            g[g[ad]][olcum].mean() - g[~g[ad]][olcum].mean()
            for _, g in d.groupby("symbol") if g[ad].any() and (~g[ad]).any()
        ]
        fark = var.mean() - yok.mean()
        t = welch_t(var.to_numpy(), yok.to_numpy())
        lehte = sum(np.sign(x) == YON[ad] for x in icsel)
        sonuc = ("ayrim yok" if abs(t) < 2 else
                 "dogrulandi" if np.sign(fark) == YON[ad] else "TERS CIKTI")
        for etiket, grup in (("var", var), ("yok", yok)):
            satir = (f"  {ad if etiket == 'var' else '':<11} {etiket:>7} {len(grup):>7,} "
                     f"{grup.mean():>7.2f} {grup.median():>7.2f}")
            if etiket == "var":
                satir += f" {fark:>7.2f} {t:>6.1f} {lehte:>4}/{len(icsel):<3} {sonuc:<12}"
            say(satir)
    say(f"  lehte = hipotezin bekledigi yonde cikan sembol sayisi (beklenen yon: "
        + ", ".join(f"{a}{'+' if y > 0 else '-'}" for a, y in YON.items()) + ")")

    say("")
    say("  Hipotez metinleri:")
    for ad, metin in HIPOTEZLER.items():
        say(f"    {ad:<11} {metin}")

    say("")
    say("  Ufka gore fark (bayrak var - yok, ortalama %):")
    say(f"  {'hipotez':<11}" + "".join(f"{'menzil_' + str(h):>12}" for h in UFUKLAR))
    for ad in HIPOTEZLER:
        if not d[ad].any() or d[ad].all():
            continue
        say(f"  {ad:<11}" + "".join(
            f"{d[d[ad]][f'menzil_{h}'].mean() - d[~d[ad]][f'menzil_{h}'].mean():>12.2f}"
            for h in UFUKLAR))

    say("")
    say("  Ayni fark, taban = impuls mumunun kapanisi (olcum artifakti kontrolu).")
    say("  Bir fark bulgu sayilmak icin iki tabanda da ayni yonde cikmali: OB siniri")
    say("  supurme/genis mumlarda uca oturur ve tek basina yapay fark uretebilir.")
    say(f"  {'hipotez':<11}" + "".join(f"{'imp_' + str(h):>12}" for h in UFUKLAR)
        + f"{'taban uyumu':>14}")
    for ad in HIPOTEZLER:
        if not d[ad].any() or d[ad].all():
            continue
        farklar = [d[d[ad]][f"imp_{h}"].mean() - d[~d[ad]][f"imp_{h}"].mean() for h in UFUKLAR]
        ana = d[d[ad]][olcum].mean() - d[~d[ad]][olcum].mean()
        j = UFUKLAR.index(int(olcum.rsplit("_", 1)[1]))
        uyum = "ayni yon" if np.sign(farklar[j]) == np.sign(ana) else "KAYBOLDU"
        say(f"  {ad:<11}" + "".join(f"{f:>12.2f}" for f in farklar) + f"{uyum:>14}")

    say("")
    say("  Bayrak oranlari (hangi bayrak ayrim uretebilecek kadar dengeli):")
    for ad in HIPOTEZLER:
        say(f"    {ad:<11} var %{d[ad].mean() * 100:.1f}")


def main() -> int:
    p = argparse.ArgumentParser(description="OPEN-23 OB anlamlilik olcumu")
    p.add_argument("part", choices=["a", "b", "rank", "c"])
    p.add_argument("--symbols", type=int, default=20, help="(c) kac sembol / (rank) kac satir")
    p.add_argument("--horizon", type=int, default=20, help="(c) birincil menzil ufku")
    p.add_argument("--csv", help="(c) OB basina ham kayitlari bu dosyaya yaz")
    p.add_argument("--out", help="raporun yazilacagi dosya")
    a = p.parse_args()

    if a.part == "a":
        part_a()
    elif a.part == "b":
        part_b()
    elif a.part == "rank":
        part_rank(a.symbols)
    else:
        part_c(a.symbols, f"menzil_{a.horizon}", a.csv)
    kaydet(a.out or f"logs/olcum_{a.part}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
