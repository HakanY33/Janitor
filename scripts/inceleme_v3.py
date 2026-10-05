"""Etiketleme paketi v3 — karar anında biten grafik, tıkla-seç çapalar.

    python -m scripts.inceleme_v3 [--pkl logs/inceleme/f1.pkl]   # → docs/inceleme/v3/index.html
    python -m scripts.inceleme_v3 --v4                            # → docs/inceleme/v4/index.html

**v4** (doğrulama seti, `adaylar.md` "ikinci 30"): yalnızca 30 rastgele an, tohum `TOHUM_V4`,
aynı örnekleme çerçevesi; ayrıca v3'ün 50 anıyla aynı sembolde ±1 gün çakışmaz. Etiketler ayrı
tarayıcı anahtarında. **v4 akışı (kullanıcı, 2026-10-05):** motorun OTE çapaları gösterilmez
(rastgele anlarda zaten yok). Önce OTE çapaları (ya da "setup yok"); OTE etiketi tamamlanınca
"OB'leri göster" açılır ve **OTE kilitlenir**. OB'ler = karar anına kadar kapanmış 30m
mumlarından, spec v0.8 tanımıyla (`ob_listesi`); her biri doğru / yanlış, kaçırılan OB 30m mumuna
tıklanarak eklenir (tıklanan mum = 1. mum). OB etiketleri ayrı alanlarda: `ob` ({OB kimliği:
dogru | yanlis}), `ob_eksik`, `ob_acildi` (OB'lerin açıldığı an); indirilen dosyada `ob_liste`
gösterilen OB'lerin kopyasıdır.

50 an: v1/v2'nin 30 işlemi (karar anı = giriş anı) + 20 rastgele an (eğitim dilimi, tohum
`TOHUM`, aynı sembolde bot işleminin giriş−1 gün … çıkış+1 gün aralığına düşmeyen 30m sınırı).
Grafik karar anında biter: yalnızca o anda **kapanmış** mumlar (CLAUDE.md #3); kapanmamış
4h mumu da çizilmez. Üstte 4h (son 14 gün), altta 30m (son 300 mum). İşlem sonucu gösterilmez.

Sayfa lightweight-charts (CDN) kullanır. Mumun üst yarısına tıklamak tepe (high), alt
yarısına dip (low) seçer; değer verinin kendisinden alınır, tıklanan pikselden değil.
Etiketler tarayıcıda saklanır, "Etiketleri indir" → `docs/inceleme/v3/etiketler.json`.
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from pathlib import Path

import pandas as pd

from scripts.inceleme import PKL, sec

OUT = Path("docs/inceleme/v3")
TOHUM = 20261002
RASTGELE = 20
TOHUM_V4 = 20261005
RASTGELE_V4 = 30
ONCE_4H = pd.Timedelta("14D")
ONCE_30 = 300
TF = pd.Timedelta("30m")
TF4 = pd.Timedelta("4h")
YAKIN = pd.Timedelta("1D")


def kapanmis(d30: pd.DataFrame, karar: pd.Timestamp) -> tuple[list, list]:
    """`karar` anında kapanmış 30m (son 300) ve 4h (son 14 gün) mumları, [t, o, h, l, c]."""
    d = d30[d30.ts + TF <= karar]
    d4 = (d.set_index("ts").resample("4h", closed="left", label="left")
          .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
               close=("close", "last"), n=("close", "size")).dropna().reset_index())
    # 4h mumu ancak sekiz 30m'si de kapanınca vardır; kısmi son mum çizilmez
    d4 = d4[(d4.ts + TF4 <= karar) & (d4.ts >= karar - ONCE_4H)]
    satir = lambda f: [[int(r.ts.timestamp()), r.open, r.high, r.low, r.close]
                       for r in f.itertuples()]
    return satir(d4), satir(d.iloc[-ONCE_30:])


def ob_listesi(d30: pd.DataFrame, symbol: str, karar: pd.Timestamp) -> list[dict]:
    """v4 · grafikteki 30m penceresinde (son `ONCE_30` kapanmış mum) karar anına kadar bilinen OB'ler.

    Tespit ve mitigasyon yalnızca `karar`'da kapanmış mumlarla (CLAUDE.md #3): sonradan gelen
    temas `mit`'e girmez. Pencere dışı mumlar sonucu değiştirmez — OB üç mumdan, mitigasyon
    sonrasındaki mumlardan bilinir — bu yüzden tespit doğrudan pencerede yapılır.
    """
    from src.features.fvg import BULLISH
    from src.features.ob import detect_order_blocks, replay_obs

    d = d30[d30.ts + TF <= karar].iloc[-ONCE_30:].reset_index(drop=True)
    obs = detect_order_blocks(d, symbol, "30m")
    replay_obs(obs, d)
    sn = lambda t: int(pd.Timestamp(t).timestamp())
    return [{"id": f"OB{k}", "ob_id": o.ob_id, "yon": "talep" if o.direction == BULLISH else "arz",
             "t1": sn(o.created_at), "t3": sn(o.impulse_at), "ust": o.top, "alt": o.bottom,
             "mit": sn(o.mitigated_at) if o.mitigated_at is not None else None}
            for k, o in enumerate(obs, 1)]


def rastgele_anlar(trades, bitis: dict, d30ler: dict, tohum: int = TOHUM, adet: int = RASTGELE,
                   onceki: list[tuple[str, pd.Timestamp]] = ()) -> list[tuple[str, pd.Timestamp]]:
    """Eğitim diliminden `adet` an. Dilim = sembolün ilk bot işlemi → `bitis` (eğitim sonu).
    `onceki` (sembol, an) çiftleriyle aynı sembolde ±1 gün çakışan an alınmaz.

    ponytail: reddetmeli örnekleme; işlem yoğunluğu çok yüksek bir sembolde yavaşlar,
    20 an için önemsiz.
    """
    rnd = random.Random(tohum)
    yasak: dict[str, list] = {}
    for t in trades:
        yasak.setdefault(t.symbol, []).append((t.entry_ts - YAKIN, t.exit_ts + YAKIN))
    semboller = sorted(yasak)
    out: list[tuple[str, pd.Timestamp]] = []
    while len(out) < adet:
        s = rnd.choice(semboller)
        bas = min(a for a, _ in yasak[s]) + YAKIN
        son = pd.Timestamp(bitis[s], tz="UTC")
        adim = int((son - bas) / TF)
        an = (bas + rnd.randrange(adim) * TF).ceil("30min")
        if any(a <= an <= b for a, b in yasak[s]) or any(s == x and abs(an - y) < YAKIN
                                                          for x, y in [*onceki, *out]):
            continue
        if (d30ler[s].ts + TF <= an).sum() < ONCE_30:
            continue
        out.append((s, an))
    return out


def uret(pkl: Path, v4: bool = False) -> None:
    from src.data import collect

    p = pickle.loads(pkl.read_bytes())
    trades = p["trades"]
    d30ler = {s: collect.read_parquet("bingx", s, "30m") for s in sorted({t.symbol for t in trades})}
    anlar = []
    if v4:
        v3 = json.loads((OUT / "etiketler.json").read_text(encoding="utf-8"))
        onceki = [(r["symbol"], pd.Timestamp(r["karar_ts"], tz="UTC")) for r in v3]
        rast = rastgele_anlar(trades, p["bitis"], d30ler, TOHUM_V4, RASTGELE_V4, onceki)
        return _yaz(OUT.with_name("v4"), "v4", _rastgele(rast, d30ler, 0, ob=True), pkl, p, TOHUM_V4,
                    f"{RASTGELE_V4} rastgele an (doğrulama seti, v3'ün 50 anıyla aynı sembolde ±1 gün "
                    "çakışmaz). <b>Sıra:</b> önce OTE çapaları ya da “setup yok”; sonra “OB'leri göster” "
                    "(OTE kilitlenir), her OB'yi doğru / yanlış işaretle, kaçırılan OB'yi “kaçırılan OB "
                    "ekle” ile 30m'de 1. mumuna tıklayarak ekle. Kaynak satırındaki spec/kod anların örneklendiği "
                    "koşunundur; OB kutuları sayfa üretiminde spec v0.8 OB tanımıyla (OPEN-64) hesaplandı")
    for n, (_, t, _) in enumerate(sec(trades, p["zones"]), 1):
        z = p["zones"][t.zone_id]
        karar = pd.Timestamp(t.entry_ts)
        h4, m30 = kapanmis(d30ler[t.symbol], karar)
        anlar.append({
            "id": f"b{n:02d}", "tur": "bot", "n": n, "symbol": t.symbol, "side": t.side,
            "zone_id": z.zone_id, "karar_ts": karar.strftime("%Y-%m-%d %H:%M"),
            "bot_0": {"ts": int(pd.Timestamp(z.anchor_0_time).timestamp()), "fiyat": z.anchor_0_price},
            "bot_1": {"ts": int(pd.Timestamp(z.anchor_1_time).timestamp()), "fiyat": z.anchor_1_price},
            "h4": h4, "m30": m30})
    anlar += _rastgele(rastgele_anlar(trades, p["bitis"], d30ler), d30ler, 30)
    _yaz(OUT, "v3", anlar, pkl, p, TOHUM, "30 bot işlemi (karar anı = giriş) + 20 rastgele an")


def _rastgele(rast, d30ler, n0: int, ob: bool = False) -> list[dict]:
    out = []
    for i, (s, karar) in enumerate(sorted(rast, key=lambda x: x[1]), 1):
        h4, m30 = kapanmis(d30ler[s], karar)
        out.append({"id": f"r{i:02d}", "tur": "rastgele", "n": n0 + i, "symbol": s,
                    "karar_ts": karar.strftime("%Y-%m-%d %H:%M"), "h4": h4, "m30": m30,
                    **({"ob": ob_listesi(d30ler[s], s, karar)} if ob else {})})
    return out


def _yaz(out: Path, surum: str, anlar: list, pkl: Path, p: dict, tohum: int, aciklama: str) -> None:
    kaynak = (f"{pkl} · parmak izi {p['hash']} · spec {p['spec_version']} · kod {p['code_version']} "
              f"· rastgele tohum {tohum}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        SAYFA.replace("__KAYNAK__", kaynak).replace("__ACIKLAMA__", aciklama)
        .replace("__SURUM__", surum).replace("__VERI__", json.dumps(anlar, ensure_ascii=False)),
        encoding="utf-8")
    print(f"{out / 'index.html'} · {len(anlar)} an")


SAYFA = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etiketleme __SURUM__</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root { --bg:#fafafa; --fg:#1b1b1b; --soluk:#666; --kart:#fff; --cizgi:#ddd; --vurgu:#1565c0;
        --s0:#2e7d32; --s1:#c62828; --bot:#777; --talep:#00897b; --arz:#ef6c00; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --fg:#e6e6e6; --soluk:#999; --kart:#1f2226;
        --cizgi:#33373c; --vurgu:#64b5f6; --s0:#66bb6a; --s1:#ef5350; --bot:#aaa; --talep:#4db6ac;
        --arz:#ffb74d; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; }
main { max-width:1400px; margin:0 auto; padding:12px 16px 40px; }
h1 { font-size:18px; margin:4px 0; } .soluk { color:var(--soluk); font-size:12px; }
.ust { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:10px 0; }
button, select { font:inherit; padding:5px 10px; border:1px solid var(--cizgi); border-radius:6px;
                 background:var(--kart); color:var(--fg); cursor:pointer; }
button.aktif { outline:2px solid var(--vurgu); }
#m0.aktif { outline-color:var(--s0); } #m1.aktif { outline-color:var(--s1); }
.kart { background:var(--kart); border:1px solid var(--cizgi); border-radius:8px; padding:10px; }
.grafik { width:100%; height:300px; } .grafik.alt { height:420px; margin-top:6px; }
.secenek { display:flex; flex-wrap:wrap; gap:14px; margin:10px 0; }
.capa { font-family:ui-monospace, monospace; font-size:13px; }
textarea { width:100%; min-height:70px; font:inherit; background:var(--bg); color:var(--fg);
           border:1px solid var(--cizgi); border-radius:6px; padding:6px; }
#ilerleme { display:flex; flex-wrap:wrap; gap:3px; margin:6px 0; }
#ilerleme span { width:22px; height:18px; font-size:10px; text-align:center; border-radius:3px;
                 border:1px solid var(--cizgi); cursor:pointer; }
#ilerleme span.tamam { background:var(--vurgu); color:var(--bg); }
#ilerleme span.simdi { outline:2px solid var(--fg); }
#ilerleme span.obtamam { box-shadow:inset 0 -4px 0 var(--talep); }
button:disabled { opacity:.45; cursor:default; } #mob.aktif { outline-color:var(--talep); }
.obsatir { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:3px 0;
           border-bottom:1px solid var(--cizgi); font-family:ui-monospace, monospace; font-size:13px; }
.obsatir button.secili { outline:2px solid var(--vurgu); }
</style></head><body><main>
<h1>Etiketleme __SURUM__ — karar anında biten grafik</h1>
<div class="soluk">Kaynak: __KAYNAK__. __ACIKLAMA__. Grafik karar
anında biter: yalnızca kapanmış mumlar; sonrası yok, işlem sonucu yok. Saatler UTC, mumun açılışı.
<b>Seçim:</b> “0” ya da “1” modunu seç, mumun <b>üst yarısına</b> tıkla → tepe (high), <b>alt yarısına</b>
→ dip (low). Fiyat verinin kendisinden kaydedilir. Klavye: ← → gezinti, 0 / 1 mod.</div>
<div id="ilerleme"></div>
<div class="ust">
  <button id="geri">← önceki</button><select id="liste"></select><button id="ileri">sonraki →</button>
  <span style="flex:1"></span><button id="indir">Etiketleri indir</button>
</div>
<div class="kart">
  <div id="baslik" style="font-weight:600"></div>
  <div id="g4" class="grafik"></div><div id="g30" class="grafik alt"></div>
  <div class="secenek">
    <label id="botsec"><input type="radio" name="secim" value="bot_dogru"> botun çapaları doğru</label>
    <label><input type="radio" name="secim" value="farkli"> farklı çapa (tıklayarak)</label>
    <label><input type="radio" name="secim" value="setup_yok"> setup yok</label>
  </div>
  <div class="ust">
    <button id="m0">0 seç</button><button id="m1">1 seç</button><button id="temizle">çapaları temizle</button>
    <span class="capa" id="c0"></span><span class="capa" id="c1"></span>
  </div>
  <textarea id="not" placeholder="serbest not"></textarea>
  <div id="obbolum" style="margin-top:10px; border-top:1px solid var(--cizgi); padding-top:8px">
    <div class="ust"><b>OB etiketleri</b>
      <button id="obgoster">OB'leri göster</button>
      <button id="mob">kaçırılan OB ekle (30m'de 1. mumuna tıkla)</button>
      <span class="soluk" id="obbilgi"></span></div>
    <div id="oblist"></div><div id="obeksik" style="margin-top:6px"></div>
  </div>
</div>
</main>
<script>
const ANLAR = __VERI__;
const ANAHTAR = "janitor___SURUM___etiket";
let E = {};
try { E = JSON.parse(localStorage.getItem(ANAHTAR) || "{}"); } catch (e) { E = {}; }
const kaydet = () => { try { localStorage.setItem(ANAHTAR, JSON.stringify(E)); } catch (e) { console.warn(e); } };
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const utc = t => new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ");
let i = 0, mod = "0", grafikler = [];

function etiket(a) {
  const e = E[a.id] ||= {id: a.id, tur: a.tur, n: a.n, symbol: a.symbol, karar_ts: a.karar_ts,
                         side: a.side ?? null, zone_id: a.zone_id ?? null, bot_0: a.bot_0 ?? null,
                         bot_1: a.bot_1 ?? null, secim: null, capa_0: null, capa_1: null, not: ""};
  if (a.ob) { e.ob ??= {}; e.ob_eksik ??= []; e.ob_acildi ??= null; }  // OB alanları OTE'den ayrı
  return e;
}
const kilitli = a => !!(a.ob && etiket(a).ob_acildi);  // OB'ler açıldıysa OTE değişmez
const obTamam = a => kilitli(a) && a.ob.every(o => etiket(a).ob[o.id]);
const tamam = id => !!(E[id] && (E[id].secim === "bot_dogru" || E[id].secim === "setup_yok" ||
                       (E[id].secim === "farkli" && E[id].capa_0 && E[id].capa_1)));

function isaretler(a, tf) {
  const e = etiket(a), adim = tf === "4h" ? 14400 : 1800, m = [];
  const yer = t => t - (t % adim);
  for (const k of ["0", "1"]) {
    if (a["bot_" + k]) m.push({time: yer(a["bot_" + k].ts), position: "inBar",
                               color: css("--bot"), shape: "circle", text: "bot " + k});
    const c = e["capa_" + k];
    if (c) m.push({time: yer(c.ts), position: c.tip === "tepe" ? "aboveBar" : "belowBar",
                   color: css(k === "0" ? "--s0" : "--s1"), shape: c.tip === "tepe" ? "arrowDown" : "arrowUp",
                   text: k});
  }
  if (tf === "30m" && kilitli(a)) {
    for (const o of a.ob) {
      const v = e.ob[o.id];
      m.push({time: o.t1, position: o.yon === "arz" ? "aboveBar" : "belowBar", shape: "square",
              color: css(o.yon === "arz" ? "--arz" : "--talep"),
              text: o.id + (v === "dogru" ? " ✓" : v === "yanlis" ? " ✗" : "")});
    }
    for (const x of e.ob_eksik) m.push({time: x.ts, position: x.yon === "arz" ? "aboveBar" : "belowBar",
                                        shape: "circle", color: css("--vurgu"), text: "+OB"});
  }
  return m.sort((x, y) => x.time - y.time);
}

function ciz() {
  grafikler.forEach(g => g.remove()); grafikler = [];
  const a = ANLAR[i], e = etiket(a);
  for (const [id, tf, veri] of [["g4", "4h", a.h4], ["g30", "30m", a.m30]]) {
    const el = document.getElementById(id);
    const g = LightweightCharts.createChart(el, {
      autoSize: true, layout: {background: {color: css("--kart")}, textColor: css("--fg")},
      grid: {vertLines: {color: css("--cizgi")}, horzLines: {color: css("--cizgi")}},
      timeScale: {timeVisible: true, secondsVisible: false, rightOffset: 4},
      localization: {timeFormatter: utc}, crosshair: {mode: 0}});
    const s = g.addCandlestickSeries({upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
                                      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
                                      priceFormat: {type: "price", precision: 6, minMove: 0.000001}});
    const bar = new Map(veri.map(r => [r[0], r]));
    s.setData(veri.map(r => ({time: r[0], open: r[1], high: r[2], low: r[3], close: r[4]})));
    s.setMarkers(isaretler(a, tf));
    for (const k of ["0", "1"]) if (a["bot_" + k])
      s.createPriceLine({price: a["bot_" + k].fiyat, color: css("--bot"), lineStyle: 2, lineWidth: 1,
                         title: "bot " + k});
    if (tf === "30m" && kilitli(a)) {  // OB kutusu: üst ve alt kenar, 1. mumdan mitigasyona (yoksa sona)
      const son = veri[veri.length - 1][0];
      for (const o of a.ob) for (const fiyat of [o.ust, o.alt]) {
        const bitis = Math.max(o.mit ? o.mit - 1800 : son, o.t3);
        g.addLineSeries({color: css(o.yon === "arz" ? "--arz" : "--talep"), lineWidth: 2,
                         lineStyle: o.mit ? 2 : 0, priceLineVisible: false, lastValueVisible: false,
                         crosshairMarkerVisible: false})
          .setData([{time: o.t1, value: fiyat}, {time: bitis, value: fiyat}]);
      }
    }
    g.subscribeClick(p => {
      if (!p.time || !p.point) return;
      const r = bar.get(p.time); if (!r) return;
      if (mod === "ob") {  // kaçırılan OB: tıklanan mum = 1. mum; yön mumun renginden
        if (tf !== "30m" || !kilitli(a)) return;
        e.ob_eksik.push({ts: r[0], saat: utc(r[0]), yon: r[4] > r[1] ? "arz" : r[4] < r[1] ? "talep" : "?",
                         ust: Math.max(r[1], r[4]), alt: Math.min(r[1], r[4])});
        kaydet(); ciz(); return;
      }
      if (kilitli(a)) return;
      const y = s.coordinateToPrice(p.point.y), tip = y >= (r[2] + r[3]) / 2 ? "tepe" : "dip";
      e["capa_" + mod] = {ts: r[0], saat: utc(r[0]), fiyat: tip === "tepe" ? r[2] : r[3], tip, tf};
      e.secim = "farkli"; kaydet(); ciz();
    });
    g.timeScale().fitContent();
    grafikler.push(g);
  }
  document.getElementById("baslik").textContent =
    `#${a.n} · ${a.symbol} · karar ${a.karar_ts} UTC · ` + (a.tur === "bot" ? `bot işlemi (${a.side})` : "rastgele an");
  document.getElementById("botsec").style.display = a.tur === "bot" ? "" : "none";
  document.querySelectorAll("input[name=secim]").forEach(r => r.checked = r.value === e.secim);
  for (const k of ["0", "1"]) {
    const c = e["capa_" + k];
    document.getElementById("c" + k).textContent = c ? `${k}: ${c.tip} ${c.saat} (${c.tf}) ${c.fiyat}` : `${k}: —`;
  }
  document.getElementById("not").value = e.not;
  document.getElementById("liste").value = i;
  document.getElementById("m0").classList.toggle("aktif", mod === "0");
  document.getElementById("m1").classList.toggle("aktif", mod === "1");
  const kilit = kilitli(a);
  document.querySelectorAll("input[name=secim]").forEach(r => r.disabled = kilit);
  for (const id of ["m0", "m1", "temizle"]) document.getElementById(id).disabled = kilit;
  document.getElementById("obbolum").style.display = a.ob ? "" : "none";
  if (a.ob) {
    const og = document.getElementById("obgoster");
    og.disabled = kilit || !tamam(a.id);
    og.textContent = kilit ? "OB'ler açık — OTE kilitli" : "OB'leri göster";
    document.getElementById("mob").disabled = !kilit;
    document.getElementById("mob").classList.toggle("aktif", mod === "ob");
    document.getElementById("obbilgi").textContent = !kilit
      ? (tamam(a.id) ? "OTE tamam; OB'leri açınca OTE değiştirilemez." : "Önce OTE çapaları ya da “setup yok”.")
      : `${a.ob.length} OB · ${a.ob.filter(o => e.ob[o.id]).length} etiketli · ${e.ob_eksik.length} eklenen`;
    document.getElementById("oblist").innerHTML = !kilit ? "" : (a.ob.length ? a.ob.map(o =>
      `<div class="obsatir"><b>${o.id}</b> ${o.yon} · 1. mum ${utc(o.t1)} · ${o.alt}–${o.ust} · ` +
      `${o.mit ? "mitige " + utc(o.mit) : "unmitige"}` +
      ["dogru", "yanlis"].map(v => ` <button data-ob="${o.id}" data-v="${v}" class="${e.ob[o.id] === v ? "secili" : ""}">` +
                                   `${v === "dogru" ? "doğru" : "yanlış"}</button>`).join("") + `</div>`).join("")
      : `<div class="soluk">Bu pencerede karar anına kadar bilinen OB yok.</div>`);
    document.getElementById("obeksik").innerHTML = e.ob_eksik.map((x, k) =>
      `<div class="obsatir">+OB ${x.yon} · 1. mum ${x.saat} · ${x.alt}–${x.ust} <button data-sil="${k}">sil</button></div>`).join("");
  }
  document.getElementById("ilerleme").innerHTML = ANLAR.map((x, j) =>
    `<span data-j="${j}" class="${tamam(x.id) ? "tamam" : ""} ${x.ob && obTamam(x) ? "obtamam" : ""} ` +
    `${j === i ? "simdi" : ""}">${x.n}</span>`).join("");
}

const git = j => { i = (j + ANLAR.length) % ANLAR.length; ciz(); };
document.getElementById("liste").innerHTML =
  ANLAR.map((a, j) => `<option value="${j}">#${a.n} ${a.symbol.split("/")[0]} ${a.karar_ts}${a.tur === "bot" ? "" : " (rastgele)"}</option>`).join("");
document.getElementById("liste").onchange = ev => git(+ev.target.value);
document.getElementById("geri").onclick = () => git(i - 1);
document.getElementById("ileri").onclick = () => git(i + 1);
document.getElementById("ilerleme").onclick = ev => { if (ev.target.dataset.j) git(+ev.target.dataset.j); };
document.getElementById("m0").onclick = () => { mod = "0"; ciz(); };
document.getElementById("m1").onclick = () => { mod = "1"; ciz(); };
document.getElementById("temizle").onclick = () => {
  const e = etiket(ANLAR[i]); e.capa_0 = e.capa_1 = null; if (e.secim === "farkli") e.secim = null; kaydet(); ciz(); };
document.querySelectorAll("input[name=secim]").forEach(r => r.onchange = () => {
  etiket(ANLAR[i]).secim = r.value; kaydet(); ciz(); });
document.getElementById("obgoster").onclick = () => {
  const a = ANLAR[i];
  if (!tamam(a.id) || kilitli(a)) return;
  etiket(a).ob_acildi = new Date().toISOString(); kaydet(); ciz(); };
document.getElementById("mob").onclick = () => { mod = "ob"; ciz(); };
document.getElementById("oblist").onclick = ev => {
  const b = ev.target.dataset; if (!b.ob) return;
  etiket(ANLAR[i]).ob[b.ob] = b.v; kaydet(); ciz(); };
document.getElementById("obeksik").onclick = ev => {
  if (ev.target.dataset.sil === undefined) return;
  etiket(ANLAR[i]).ob_eksik.splice(+ev.target.dataset.sil, 1); kaydet(); ciz(); };
document.getElementById("not").oninput = ev => { etiket(ANLAR[i]).not = ev.target.value; kaydet(); };
document.addEventListener("keydown", ev => {
  if (ev.target.tagName === "TEXTAREA") return;
  if (ev.key === "ArrowLeft") git(i - 1); else if (ev.key === "ArrowRight") git(i + 1);
  else if (ev.key === "0" || ev.key === "1") { mod = ev.key; ciz(); }
});
document.getElementById("indir").onclick = () => {
  const veri = ANLAR.map(a => ({...etiket(a), ...(a.ob ? {ob_liste: a.ob} : {})}));
  const url = URL.createObjectURL(new Blob([JSON.stringify(veri, null, 1)], {type: "application/json"}));
  Object.assign(document.createElement("a"), {href: url, download: "etiketler.json"}).click();
  URL.revokeObjectURL(url);
};
ciz();
</script></body></html>
"""


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--pkl", default=str(PKL))
    a.add_argument("--v4", action="store_true", help="doğrulama seti (30 rastgele an)")
    x = a.parse_args()
    uret(Path(x.pkl), x.v4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
