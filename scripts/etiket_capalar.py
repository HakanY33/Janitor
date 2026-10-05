"""v2 etiketlerinden çapa tablosu — `docs/inceleme/v2/etiketler.json` → `capalar.md`.

    python -m scripts.etiket_capalar

Yapılandırılmış alanlar (`dogru_0`/`dogru_1`) ve serbest metin notlar **elle** okunup
aşağıdaki `CAPALAR` listesine yazıldı (2026-10-02); kaynak sütunu hangisi olduğunu söyler.
Betik yalnızca yılı tamamlar, verilen zamanın 30m mumunu bulur ve girişe göre konumu yazar.
Aday karşılaştırması yok (`adaylar.md` ayrı adım).

Zaman biçimi: "MM-DD HH:MM" (±1 saat içinde uç), "MM-DD HH:MM/MM-DD HH:MM" (aralıkta uç),
"bot_0"/"bot_1" (botun çapası), "öneri HH:MM" (v2 sayfasındaki mor ipucu, `IPUCU`), None
(notta zaman yok). `hedef`: aralıkta uç yerine bu fiyata en yakın mum.
Rol (`0`/`1`) yalnızca kurgunun yönünden: SHORT `0` önce dip, `1` sonra tepe; LONG tersi.

Girişe göre: çapa mumu girişten **önce kapanmışsa** "önce", aksi hâlde "sonra" (sonradan
bakış — kalibrasyonda kullanılmaz). Aralık girişi kesiyorsa uç hangi muma düştüyse o.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import pandas as pd

from scripts.inceleme import PKL, sec
from scripts.inceleme_v2 import ipucu_noktalari

ETIKET = Path("docs/inceleme/v2/etiketler.json")
OUT = Path("docs/inceleme/v2/capalar.md")
TF = pd.Timedelta("30m")
YAKIN = pd.Timedelta("1h")

# (n, kurgu, yön, rol, tip, zaman, not_fiyat, hedef, kaynak)
# kurgu: aynı işlemde birden çok önerilen setup A/B/… · tip: tepe | dip | ?
CAPALAR = [
    (1, "A", "LONG", "0", "tepe", "01-23 17:30", "1.95 üstü", None, "alan"),
    (1, "A", "LONG", "1", "dip", "01-30 01:30", "1.70–1.75", None, "alan"),
    (1, "B", "LONG", "0", "tepe", "01-28 00:00/01-29 14:00", "~12:00 en high", None, "not"),
    (2, "A", "LONG", "0", "tepe", "10-27 05:00", "2.70 üzeri", None, "alan"),
    (2, "A", "LONG", "1", "dip", "10-28 21:00", "2.45 üzeri", None, "alan"),
    (2, "B", "SHORT", "0", "dip", "10-22 05:00", "iğne", None, "not"),
    (2, "B", "SHORT", "1", "tepe", "10-27 05:00", "A'nın tepesi", None, "not"),
    (3, "A", "LONG", "0", "tepe", "12-22 12:30", "90000 üstü", None, "alan"),
    (3, "A", "LONG", "1", "dip", "12-24 14:30", "87000 altı", None, "alan"),
    (3, "B", "?", "?", "tepe", "12-26 00:00/12-27 05:00", "gün ortasından biraz geride", None, "not"),
    (3, "B", "?", "?", "dip", "12-26 00:00/12-27 05:00", "aynı aralıkta en dip", None, "not"),
    (4, "A", "SHORT", "0", "dip", "03-29 22:30", "65000 altı", None, "alan"),
    (4, "A", "SHORT", "1", "tepe", "03-30 13:00", "68000 üstü", None, "alan"),
    (4, "B", "LONG", "0", "tepe", "03-25 00:00/03-26 23:30", "72K", 72000, "not"),
    (4, "B", "LONG", "1", "dip", "03-29 00:00/03-30 23:30", "65K altı", None, "not"),
    (5, "A", "LONG", "0", "tepe", "12-03 00:00/12-05 00:00", "6.2'nin biraz altı", None, "not"),
    (5, "A", "LONG", "1", "dip", "12-07 11:00/12-08 13:00", "5.4 altı, öğleye yakın", None, "not"),
    (7, "A", "SHORT", "0", "dip", "12-31 20:00", "", None, "not"),
    (7, "A", "SHORT", "1", "tepe", "01-03 00:00/01-04 00:00", "2.05 üzeri", None, "not"),
    (8, "A", "LONG", "0", "tepe", "02-21 00:00/02-22 23:30", "2.8'e en yakın", 2.8, "not"),
    (9, "A", "SHORT", "0", "dip", "03-29 22:00/03-29 23:00", "alt iğne", None, "not"),
    (9, "A", "SHORT", "1", "tepe", "03-30 00:00/03-31 23:30", "1.225'e yakın", 1.225, "not"),
    (10, "A", "LONG", "0", "tepe", "12-22 00:00/12-23 23:30", "870 üstü", None, "not"),
    (10, "A", "LONG", "1", "dip", "12-26 00:00/12-27 05:30", "820'ye en yakın", 820, "not"),
    (11, "A", "LONG", "0", "tepe", "bot_0", "bot 0 doğru", None, "not"),
    (11, "A", "LONG", "1", "dip", "öneri 13:30", "", None, "not + öneri"),
    (12, "A", "LONG", "0", "tepe", "02-06 22:30", "", None, "not"),
    (12, "A", "LONG", "1", "dip", "02-12 20:30", "", None, "not"),
    (13, "A", "LONG", "0", "tepe", "10-13 21:00", "", None, "not"),
    (13, "A", "LONG", "1", "dip", "10-17 08:00", "", None, "not"),
    (13, "B", "SHORT", "0", "dip", "10-17 08:00", "", None, "not"),
    (13, "B", "SHORT", "1", "tepe", "10-18 07:00", "“şimdilik”", None, "not"),
    (14, "A", "SHORT", "0", "dip", "02-14 05:00", "", None, "not"),
    (14, "A", "SHORT", "1", "tepe", "02-15 07:30", "", None, "not"),
    (14, "B", "SHORT", "0", "dip", "02-11 10:30", "örnek, çalışmış", None, "not"),
    (14, "B", "SHORT", "1", "tepe", "02-12 11:30", "örnek, çalışmış", None, "not"),
    (15, "A", "SHORT", "0", "dip", "09-22 00:00/09-22 23:30", "09-22'nin en alt ucu", None, "not"),
    (15, "A", "SHORT", "1", "tepe", "09-23 15:00", "stop yerinin üstü", None, "not"),
    (16, "A", "LONG", "0", "tepe", "10-05 08:00", "", None, "not"),
    (16, "A", "LONG", "1", "dip", "10-05 20:00", "", None, "not"),
    (16, "B", "SHORT", "0", "dip", "10-01 03:30", "", None, "not"),
    (16, "B", "SHORT", "1", "tepe", "10-02 19:30", "3.10", None, "not"),
    (17, "A", "SHORT", "0", "dip", None, "bot 0'dan sonraki dip (“yine yetersiz”)", None, "not"),
    (17, "B", "LONG", "0", "tepe", "10-21 16:30", "", None, "not"),
    (17, "B", "LONG", "1", "dip", "10-22 21:00", "", None, "not"),
    (18, "A", "LONG", "0", "tepe", "09-01 09:00", "", None, "not"),
    (18, "A", "LONG", "1", "dip", "09-01 21:30", "grafiğin nihai lowu", None, "not"),
    (18, "B", "SHORT", "0", "dip", "öneri 12:30", "0.79 altına sarkmış", None, "not + öneri"),
    (19, "A", "SHORT", "0", "dip", "10-17 00:00/10-17 23:30", "0.8 veya altı", None, "not"),
    (19, "A", "SHORT", "1", "tepe", "10-18 00:00/10-18 23:30", "10-18 high'ı", None, "not"),
    (19, "B", "LONG", "0", "tepe", "10-13 20:30", "0.96", None, "not"),
    (19, "B", "LONG", "1", "dip", "10-17 00:00/10-17 23:30", "0.8", None, "not"),
    (20, "A", "LONG", "0", "tepe", "01-22 10:30", "“öneri 13:30'un erkeni”", None, "not"),
    (20, "A", "LONG", "1", "dip", "öneri 15:00", "öneri lowu", None, "not + öneri"),
    (21, "A", "SHORT", "0", "dip", "01-25 20:00", "", None, "not"),
    (21, "A", "SHORT", "1", "tepe", "01-28 12:00", "", None, "not"),
    (22, "A", "SHORT", "0", "dip", None, "1.24'e en yakın lowlardan biri", None, "not"),
    (22, "A", "SHORT", "1", "tepe", "09-19 00:00/09-19 06:00", "1.38 üstü, ilk saatler", None, "not"),
    (23, "A", "SHORT", "0", "dip", "bot_1", "bot 1 doğru", None, "not + öneri"),
    (23, "A", "SHORT", "1", "tepe", "öneri 01:30", "", None, "not + öneri"),
    (23, "B", "LONG", "0", "tepe", "10-03 22:00", "13.5 üzeri", None, "not"),
    (23, "B", "LONG", "1", "dip", "10-04 18:30", "alt iğne", None, "not"),
    (25, "A", "SHORT", "0", "dip", "bot_0", "bot çapaları doğru", None, "not"),
    (25, "A", "SHORT", "1", "tepe", "bot_1", "bot çapaları doğru", None, "not"),
    (26, "A", "LONG", "?", "?", "08-24 19:00/08-24 20:00", "tek mum hacmi, iki mum arası", None, "not"),
    (27, "A", "SHORT", "0", "dip", "02-24 15:00", "", None, "not"),
    (27, "A", "SHORT", "1", "tepe", "02-25 21:00", "640 üstü", None, "not"),
    (28, "A", "LONG", "0", "tepe", "öneri -3", "“önerdiğim high” (−3/−4 mum)", None, "not + öneri"),
    (28, "A", "LONG", "1", "dip", "bot_1", "low değişmiyor (örtük)", None, "not"),
    (29, "A", "LONG", "0", "tepe", "öneri 04:00", "“öneri high doğru” (04:00/04:30)", None, "not + öneri"),
    (29, "A", "LONG", "1", "dip", "bot_1", "low değişmiyor (örtük)", None, "not"),
    (30, "A", "LONG", "0", "tepe", "bot_0", "doğru çizim", None, "not"),
    (30, "A", "LONG", "1", "dip", "bot_1", "doğru çizim", None, "not"),
    (30, "B", "LONG", "1", "dip", "05-04 10:00", "“yeni low”", None, "not"),
]


def _yil(md: str, giris: pd.Timestamp) -> pd.Timestamp:
    """"MM-DD HH:MM" → girişe en yakın yıl (12-31 ↔ 01-02 geçişi)."""
    adaylar = [pd.Timestamp(f"{giris.year + d}-{md}", tz="UTC") for d in (-1, 0, 1)]
    return min(adaylar, key=lambda t: abs(t - giris))


def coz(zaman: str | None, tip: str, hedef: float | None, giris: pd.Timestamp, z, oneriler,
        d30: pd.DataFrame) -> tuple[pd.Timestamp, float] | None:
    """Çapanın 30m mumu ve değeri (tepe → high, dip → low); çözülemezse None."""
    if zaman is None:
        return None
    if zaman in ("bot_0", "bot_1"):
        return (pd.Timestamp(getattr(z, f"anchor_{zaman[-1]}_time")),
                getattr(z, f"anchor_{zaman[-1]}_price"))
    if zaman.startswith("öneri"):
        for an, fiyat, e in oneriler:
            if e.startswith(zaman + " "):
                return an, fiyat
        raise ValueError(f"öneri bulunamadı: {zaman}")
    if "/" in zaman:
        bas, son = (_yil(p, giris) for p in zaman.split("/"))
    else:
        t = _yil(zaman, giris)
        bas, son = t - YAKIN, t + YAKIN
    w = d30[(d30.ts >= bas) & (d30.ts <= son)]
    if w.empty:
        raise ValueError(f"veri yok: {zaman}")
    kol = w.high if tip == "tepe" else w.low if tip == "dip" else None
    if kol is None:  # tip belirsiz: aralığın ilk mumu, değer yok
        return w.ts.iloc[0], float("nan")
    i = (kol - hedef).abs().idxmin() if hedef is not None else (
        kol.idxmax() if tip == "tepe" else kol.idxmin())
    return w.ts[i], float(kol[i])


def main() -> int:
    from src.data import collect

    etiket = {e["n"]: e for e in json.loads(ETIKET.read_text(encoding="utf-8"))}
    p = pickle.loads(PKL.read_bytes())
    secim = {n: t for n, (_, t, _) in enumerate(sec(p["trades"], p["zones"]), 1)}
    satirlar, ozet = [], {"önce": 0, "sonra": 0, "zamansız": 0}
    d30_onbellek: dict[str, pd.DataFrame] = {}
    for n, kurgu, yon, rol, tip, zaman, not_fiyat, hedef, kaynak in CAPALAR:
        t = secim[n]
        assert t.symbol == etiket[n]["symbol"], n  # seçim etiket dosyasıyla aynı mı
        z = p["zones"][t.zone_id]
        d30 = d30_onbellek.setdefault(t.symbol, collect.read_parquet("bingx", t.symbol, "30m"))
        giris = pd.Timestamp(t.entry_ts)
        sonuc = coz(zaman, tip, hedef, giris, z, ipucu_noktalari(n, t, z, d30), d30)
        if sonuc is None:
            mum, deger, konum = "—", "—", "zamansız"
        else:
            an, v = sonuc
            mum, deger = an.strftime("%Y-%m-%d %H:%M"), ("—" if v != v else f"{v:.6g}")
            konum = "önce" if an + TF <= giris else "sonra"
        ozet[konum] += 1
        satirlar.append(f"| {n} | {t.symbol.split('/')[0]} {t.side} | {kurgu} | {yon} | {rol} | "
                        f"{tip} | {zaman or '—'} | {not_fiyat or '—'} | {mum} | {deger} | "
                        f"**{konum}** | {kaynak} |")
    yok = [e for e in etiket.values() if e.get("setup_yok")]
    capasiz = sorted(set(etiket) - {c[0] for c in CAPALAR})
    md = [
        "# v2 etiketlerinden çapalar",
        "",
        "Üreten: `python -m scripts.etiket_capalar` (2026-10-02). Kaynak `etiketler.json`: "
        "yapılandırılmış alanlar (**alan**) ve serbest notlar (**not**) elle okundu; mor ipucu "
        "noktaları (**öneri**) v2 sayfasındaki konumlarından çözüldü. Aday karşılaştırması yok.",
        "",
        "- **Not zamanı**: kullanıcının yazdığı (UTC, yıl girişten tamamlandı). Tek an ±1 saat, "
        "aralık tümüyle taranır; tepe → en yüksek high, dip → en düşük low (fiyat hedefi varsa ona "
        "en yakın mum).",
        "- **Rol** kurgunun yönünden: SHORT `0` önce dip / `1` sonra tepe, LONG tersi. `?` = notta yön yok.",
        "- **Girişe göre**: çapa mumu girişten önce **kapanmışsa** önce. *Sonra* olanlar sonradan "
        "bakıştır — v2 grafiği girişten sonrasını da gösteriyordu — **kalibrasyonda kullanılmaz**.",
        "",
        f"Toplam {len(CAPALAR)} çapa: önce {ozet['önce']}, sonra {ozet['sonra']}, "
        f"zamansız {ozet['zamansız']}.",
        "",
        "| # | İşlem | Kurgu | Yön | Rol | Tip | Not zamanı | Not fiyatı | 30m mumu | Değer | Girişe göre | Kaynak |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        *satirlar,
        "",
        f"## “Setup yok” işaretli işlemler ({len(yok)})",
        "",
        "| # | İşlem | Giriş | Not (özet) |",
        "|---|---|---|---|",
        *[f"| {e['n']} | {e['symbol'].split('/')[0]} {e['side']} | {e['entry_ts']} | "
          f"{e['not'][:110].replace('|', '/')}… |" for e in yok],
        "",
        f"Çapa çıkmayan işlemler: {', '.join(f'#{n}' for n in capasiz) or 'yok'}.",
        "",
    ]
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"{OUT} · {ozet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
