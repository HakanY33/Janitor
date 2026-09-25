"""R-RISK-05 ızgara süpürmesi — `T_rahat` × `T_kritik` × `K` × UYARI-ekleme kolu.

    python -m scripts.sweep                  # 4 × 3 × 2 × 2 = 48 kombinasyon, 20 sembol

Spec: R-RISK-05 ("eşikler süpürülecek, sabitlenmeyecek"), R-RISK-01, R-ADD-03,
§8 (maliyet modeli, zorunlu sayaçlar).

**Veri bir kez yüklenir.** Hazırlık (parquet okuma, zone/OB/FVG tespiti, `pierce_time`)
hücreden hücreye değişmiyor ve koşunun en pahalı kısmı; `reset_for_rerun` ile aynı veri
her hücrede yeniden kullanılır. Ayrılmış %20 hiçbir hücrede açılmaz.

**`R-RISK-01` bağlanma süresi neden raporlanıyor.** Tavan sürekli bağlıyorsa hücreler
arasındaki fark stratejinin değil, **hangi zone'un sıraya girdiğinin** ölçüsüdür
(`R-ZONE-08` `TASARLANACAK`). O durumda tablo bir kalibrasyon değil, bir sıralama
artefaktıdır — bu yüzden her satırda yüzde olarak verilir.
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.backtest.costs import build_cost_model
from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun
from scripts.backtest import code_version, spec_version

T_RAHAT = (Decimal("0.50"), Decimal("0.30"), Decimal("0.20"), Decimal("0.10"))
T_KRITIK = (Decimal("0.15"), Decimal("0.08"), Decimal("0.05"))
"""`0.05`, `T_rahat = 0.10` satırı tek hücreye düşmesin diye eklendi: `0.15` o satırda
kısıtı ihlal ediyor, geriye yalnızca `0.08` kalıyordu."""

K_VALUES = (Decimal("1.0"), Decimal("0.5"))

UYARI_BLOCKS_ADDS = (True, False)
"""R-RISK-05 UYARI bandının eklemeye etkisi.

`True` spec'in yazılı hâlidir: "Yeni pozisyon açılmaz · ekleme reddedilir
(`ADD-REJECT-D`)". `False` varyantı UYARI'yı yalnızca **yeni zone girişine** uygular;
mevcut pozisyona ekleme `R-RISK-01` tavanına ve `ADD-REJECT-A/B/C`'ye tabi olarak sürer.
KRİTİK her iki kolda da her şeyi durdurur ve küçültmeyi uygular.

İkinci kol **spec'ten sapar**: tablo bir kalibrasyon değil, bir **spec adayı** ölçer.
Sorduğu soru şu — bu strateji zarardayken ekleyerek maliyet düşürdüğüne göre, UYARI'da
eklemeyi kapatmak likidasyonu mu önlüyor yoksa yalnızca stratejinin çalışma mekanizmasını
mı kapatıyor."""


def gecerli(t_rahat: Decimal, t_kritik: Decimal) -> bool:
    """R-RISK-05 kısıtı: `T_kritik < T_rahat`.

    Eşitlik veya ters sıralamada UYARI bandı kapanır/ters döner ve sonuç koşulların
    değerlendirilme sırasına bağlı bir artefakta dönüşür. Bu hücreler çalıştırılmaz.
    """
    return t_kritik < t_rahat

out: list[str] = []


def say(line: str = "") -> None:
    out.append(line)
    print(line, flush=True)


def baslik(metin: str) -> None:
    say("")
    say("=" * 110)
    say(metin)
    say("=" * 110)


def cell_metrics(res, k, t_rahat, t_kritik, uyari_add, elapsed) -> dict:
    pf, c, tr = res.portfolio, res.costs, res.trades
    adds = Counter(t.adds for t in tr)
    bars = res.counters["bars_total"] or 1
    oran = pf.min_equity_ratio
    return {
        "K": k, "T_rahat": t_rahat, "T_kritik": t_kritik,
        "uyari_ekleme_engel": uyari_add,
        "net_getiri_%": (pf.balance / pf.start_balance - 1) * 100,
        "bitis_bakiye": pf.balance,
        "max_drawdown_%": pf.max_drawdown * 100,
        "islem": len(tr),
        "kazanan_%": (sum(1 for t in tr if t.pnl > 0) / len(tr) * 100) if tr else Decimal("0"),
        "min_eq_notional_%": (oran * 100) if oran is not None else None,
        "min_liq_mesafe_%": (pf.min_liq_distance * 100) if oran is not None else None,
        "likidasyon": res.counters["liquidations"],
        "deleverage": res.counters["deleverage_events"],
        "ekleme": res.counters["adds"],
        "ekleme_dagilimi": dict(sorted(adds.items())),
        "delev_realize": res.deleverage_realized,  # küçültmelerde realize PnL (net)
        "komisyon": c.total_fees,
        "funding": c.total_funding,
        "slippage": c.total_slippage,
        "risk01_bagli_%": res.counters["risk01_binding_bars"] / bars * 100,
        "pozisyonlu_bar_%": res.counters["bars_with_position"] / bars * 100,
        "max_eszamanli": max(pf.concurrent_hist, default=0),
        "belirsiz_%": (sum(1 for t in tr if t.ambiguous) / len(tr) * 100) if tr else Decimal("0"),
        "sure_sn": elapsed,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="R-RISK-05 ızgara süpürmesi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--balance", type=Decimal, default=Decimal("10000"))
    p.add_argument("--mmr", type=Decimal, default=Decimal("0.005"))
    p.add_argument("--train-frac", type=float, default=TRAIN_FRAC)
    p.add_argument("--out", default="logs/sweep.txt")
    p.add_argument("--csv", default="logs/sweep.csv")
    a = p.parse_args()

    from scripts.measure_ob import liquidity_symbols
    symbols = liquidity_symbols(a.limit)

    t0 = time.time()
    data, skipped = [], []
    for i, s in enumerate(symbols, 1):
        sd = load_symbol(s, a.exchange, a.train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
        print(f"  [{i}/{len(symbols)}] {s:<24} "
              f"{'hazir' if sd is not None else 'ATLANDI (1m yok)'}", file=sys.stderr, flush=True)
    if not data:
        sys.exit("hiçbir sembolde 30m + 1m veri yok")
    yukleme = time.time() - t0

    baslik(f"R-RISK-05 IZGARA SUPURMESI  ·  spec {spec_version()}  ·  kod {code_version()}")
    say(f"  {len(data)}/{len(symbols)} sembol"
        + (f"  ·  atlanan: {', '.join(skipped)}" if skipped else ""))
    say(f"  veri: verinin en eski %{a.train_frac * 100:.0f}'i · ayrılmış %20 okunmadı")
    say(f"  geometri/tespit 30m · durum geçişleri 1m (R-ZONE-09) · MMR={a.mmr}"
        f" · başlangıç bakiye {a.balance}")
    say(f"  hazırlık {yukleme:.0f} sn (tüm hücrelerde yeniden kullanılır)")
    say("")
    say("  ** OPEN-27 — ekleme çarpanı bu koşuda daima 1-1 (ADD_MULTIPLIER = 1). **")
    say("     R-ADD-03'ün 1-3 / 1-5 / 1-10 seçenekleri kullanılmıyor; çarpan seçim kuralı")
    say("     ('fiyatın gideceği tahmin edilen nokta') sayısallaşmadığı için en temkinli")
    say("     olan sabitlendi. Ekleme sayısı ve etkisi bu basitleştirme altında okunmalı.")
    say("")
    say("  ** OPEN-28 — KRİTİK bölgede pozisyon yarılanır (R-RISK-05 / R-KILL-04). **")
    say("     Bölgede kalınan her mumda her pozisyon yarıya iner. Yarılama equity/notional")
    say("     oranını ikiye katladığı için bölgeden sınırlı adımda çıkılır; eşiği tam")
    say("     hedefleyen küçültme sınırda salınıma giriyordu. Küçültme oranı spec'te")
    say("     tanımlı değildi. Bu davranış olmadan T_kritik ölü bir parametredir.")
    say("")
    say("  ** Kısıt: T_kritik < T_rahat. Sağlamayan hücreler çalıştırılmaz (R-RISK-05). **")
    say("")
    say("  ** UYA+ sütunu — UYARI bandı eklemeyi de engelliyor mu. **")
    say("     evet = spec'in yazılı hâli (R-RISK-05: 'ekleme reddedilir · ADD-REJECT-D').")
    say("     hayir = SPEC ADAYI: UYARI yalnızca yeni zone girişini durdurur; mevcut")
    say("     pozisyona ekleme R-RISK-01 ve ADD-REJECT-A/B/C'ye tabi olarak sürer.")
    say("     KRİTİK her iki kolda da her şeyi durdurur ve küçültmeyi uygular.")

    rows = []
    cells = list(itertools.product(K_VALUES, T_RAHAT, T_KRITIK, UYARI_BLOCKS_ADDS))
    atlanan_hucre = 0
    for n, (k, t_rahat, t_kritik, uyari_add) in enumerate(cells, 1):
        etiket = f"K={k} T_rahat={t_rahat} T_kritik={t_kritik} UYARI_ekleme_engel={uyari_add}"
        if not gecerli(t_rahat, t_kritik):
            rows.append({"K": k, "T_rahat": t_rahat, "T_kritik": t_kritik,
                         "uyari_ekleme_engel": uyari_add, "atlandi": True})
            atlanan_hucre += 1
            print(f"  [{n}/{len(cells)}] {etiket} -> ATLANDI (T_kritik >= T_rahat)",
                  file=sys.stderr, flush=True)
            continue
        reset_for_rerun(data)
        costs = build_cost_model([d.symbol for d in data], a.exchange)
        c0 = time.time()
        res = Backtest(data, costs, a.balance, k, a.mmr, t_rahat, t_kritik, uyari_add).run()
        m = cell_metrics(res, k, t_rahat, t_kritik, uyari_add, time.time() - c0)
        m["atlandi"] = False
        rows.append(m)
        # Hücre biter bitmez diske: koşu saatler sürüyor, yarıda kesilirse biten
        # hücreler kaybolmasın. Nihai tablo yine sonda yazılır.
        pd.DataFrame([{x: y for x, y in r.items() if x != "ekleme_dagilimi"}
                      for r in rows]).to_csv(a.csv, index=False)
        print(f"  [{n}/{len(cells)}] {etiket} -> getiri {m['net_getiri_%']:+.1f}%  "
              f"islem {m['islem']:,}  ekleme {m['ekleme']:,}  ({m['sure_sn']:.0f} sn)",
              file=sys.stderr, flush=True)

    calisan = [m for m in rows if not m["atlandi"]]

    def kimlik(m) -> str:
        return (f"  {m['K']:>4} {m['T_rahat']:>6} {m['T_kritik']:>6} "
                f"{('evet' if m['uyari_ekleme_engel'] else 'hayir'):>6} ")

    # --- ana tablo -----------------------------------------------------------
    baslik("IZGARA — ana tablo")
    say(f"  {len(calisan)} hucre calisti, {atlanan_hucre} hucre atlandi "
        f"(T_kritik >= T_rahat, R-RISK-05 kisiti)")
    say("")
    say(f"  {'K':>4} {'T_rah':>6} {'T_kri':>6} {'UYA+':>6} {'net getiri':>11} {'maxDD':>8} "
        f"{'islem':>7} {'min liq':>9} {'likid':>6} {'delev':>7} {'ekleme':>7} "
        f"{'R-RISK-01 bagli':>16}")
    for m in rows:
        if m["atlandi"]:
            say(kimlik(m) + f"{'atlandi (T_kritik >= T_rahat)':>62}")
            continue
        liq = f"{m['min_liq_mesafe_%']:.2f}%" if m["min_liq_mesafe_%"] is not None else "-"
        say(kimlik(m)
            + f"{m['net_getiri_%']:>10.1f}% {m['max_drawdown_%']:>7.1f}% "
            f"{m['islem']:>7,} {liq:>9} {m['likidasyon']:>6,} {m['deleverage']:>7,} "
            f"{m['ekleme']:>7,} {m['risk01_bagli_%']:>15.2f}%")

    # --- maliyet kalemleri ---------------------------------------------------
    baslik("MALIYET KALEMLERI (§8 — ayri ayri)")
    say(f"  {'K':>4} {'T_rah':>6} {'T_kri':>6} {'UYA+':>6} {'komisyon':>13} {'funding':>12} "
        f"{'slippage':>13} {'toplam':>13} {'islem basina':>13}")
    for m in calisan:
        top = m["komisyon"] + m["funding"] + m["slippage"]
        say(kimlik(m)
            + f"{m['komisyon']:>13,.2f} {m['funding']:>12,.2f} {m['slippage']:>13,.2f} "
            f"{top:>13,.2f} {(top / m['islem'] if m['islem'] else 0):>13,.2f}")

    # --- kaldirac azaltmanin maliyeti ---------------------------------------
    baslik("KALDIRAC AZALTMA MALIYETI (R-RISK-05 KRITIK — OPEN-28)")
    say("  Strateji zarardayken ekleyerek maliyet dusurur; KRITIK'te zorla kucultmek")
    say("  aleyhte hareketin dibinde satmaktir. Bu kalem, o kucultmelerde realize edilen")
    say("  PnL toplamidir (komisyon dusulmus) — likidasyon riskinin karsisina konur.")
    say("")
    say(f"  {'K':>4} {'T_rah':>6} {'T_kri':>6} {'UYA+':>6} {'olay':>7} {'realize PnL':>14} "
        f"{'olay basina':>13} {'net getiriye pay':>17} {'likidasyon':>11}")
    for m in calisan:
        olay, realize = m["deleverage"], m["delev_realize"]
        pay = realize / a.balance * 100
        say(kimlik(m)
            + f"{olay:>7,} {realize:>14,.2f} "
            f"{(realize / olay if olay else Decimal('0')):>13,.2f} "
            f"{pay:>16.1f}% {m['likidasyon']:>11,}")
    say("")
    say("  'net getiriye pay' = realize PnL / baslangic bakiye. Negatifse kucultme")
    say("  hesaptan bu kadar goturmus demektir; likidasyon sayaci 0 ise bedeli budur.")

    # --- ekleme dagilimi -----------------------------------------------------
    baslik("GERCEKLESEN EKLEME SAYISI DAGILIMI (islem basina, OPEN-27: hepsi 1-1)")
    en_fazla = max((max(m["ekleme_dagilimi"], default=0) for m in calisan), default=0)
    say(f"  {'K':>4} {'T_rah':>6} {'T_kri':>6} {'UYA+':>6} "
        + "".join(f"{str(x) + ' ekleme':>12}" for x in range(en_fazla + 1)))
    for m in calisan:
        d = m["ekleme_dagilimi"]
        say(kimlik(m) + "".join(f"{d.get(i, 0):>12,}" for i in range(en_fazla + 1)))

    # --- R-RISK-01 yorumu ----------------------------------------------------
    baslik("R-RISK-01 TAVANI — sonuc stratejiyi mi, zone siralamasini mi olcuyor")
    say("  'bagli' = tavanin yeni girisi engelledigi mumlarin orani.")
    say("  Surekli bagliysa hucreler arasi fark R-ZONE-08 (TASARLANACAK) sirasini olcer.")
    say("")
    say(f"  {'K':>4} {'T_rah':>6} {'T_kri':>6} {'UYA+':>6} {'bagli %':>9} {'pozisyonlu bar %':>18} "
        f"{'maks eszamanli':>16} {'yorum':<32}")
    for m in calisan:
        pay = m["risk01_bagli_%"]
        yorum = ("tavan baglamiyor" if pay < 1 else
                 "ara ara bagliyor" if pay < 20 else
                 "SIK BAGLIYOR - siralama etkisi" if pay < 60 else
                 "SUREKLI BAGLI - sonuc siralama olcuyor")
        say(kimlik(m) + f"{pay:>8.2f}% "
            f"{m['pozisyonlu_bar_%']:>17.2f}% {m['max_eszamanli']:>16} {yorum:<32}")

    df = pd.DataFrame([{k: v for k, v in m.items() if k != "ekleme_dagilimi"} for m in rows])
    df.to_csv(a.csv, index=False)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n-> {a.out}\n-> {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
