"""Strateji inceleme paketi — #31'in OTE girişlerinden 20 işlem, "girerdim / girmezdim".

    python -m scripts.inceleme_strateji      # logs/inceleme/ltf31_31.pkl → docs/inceleme/strateji/index.html

20 işlem: net PnL'i en kötü 10 OTE girişi + kalanlardan tohum `TOHUM` ile rastgele 10. Sayfada
sıra aynı tohumla karıştırılır; grup (kötü / rastgele) ve PnL gösterilmez, yalnızca indirilen
dosyada (`grup`). Grafik çıkıştan sonrasını da gösterir (açıklayıcı inceleme; karar anında biten
v3/v4'ten farklı). Üstte 4h: zone'un `0`'ından 2 hafta önce → çıkıştan 1 gün sonra. Altta 30m:
girişten önce 200 mum → çıkıştan sonra 50 mum. İşaretler: `0`, `1`, giriş, çıkış; çizgiler
0 · 0.50 · 0.70 · 0.79 · 1 · stop (OTE girişinde `1`, R-RISK-02). Saatler UTC, mumun açılışı.

Etiket: "girerdim" / "girmezdim"; girmezdim → tek tıkla sebep + isteğe bağlı not. JSON indirilir.
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from pathlib import Path

import pandas as pd

PKL = Path("logs/inceleme/ltf31_31.pkl")
OUT = Path("docs/inceleme/strateji")
TOHUM = 20261007
TF = pd.Timedelta("30m")
SEBEPLER = ["trend ters", "düz piyasa", "zigzag zayıf (0-1-0.5)", "hacim yok", "setup yok",
            "bekleyecektim", "diğer"]


def sec(trades) -> list[tuple[str, object]]:
    ote = sorted((t for t in trades if t.giris == "OTE"), key=lambda t: (t.pnl, t.entry_ts))
    rnd = random.Random(TOHUM)
    secim = [("kotu", t) for t in ote[:10]] + [("rastgele", t) for t in rnd.sample(ote[10:], 10)]
    rnd.shuffle(secim)
    return secim


def mumlar(d: pd.DataFrame) -> list:
    return [[int(r.ts.timestamp()), r.open, r.high, r.low, r.close, r.volume] for r in d.itertuples()]


def h4(d30: pd.DataFrame) -> pd.DataFrame:
    return (d30.set_index("ts").resample("4h", closed="left", label="left")
            .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                 close=("close", "last"), volume=("volume", "sum")).dropna().reset_index())


def islem(n: int, grup: str, t, z, d30: pd.DataFrame, d4: pd.DataFrame) -> dict:
    g, c = pd.Timestamp(t.entry_ts), pd.Timestamp(t.exit_ts)
    a0 = pd.Timestamp(z.anchor_0_time)
    i_g = int(d30.ts.searchsorted(g.floor("30min")))
    i_c = int(d30.ts.searchsorted(c.floor("30min")))
    sn = lambda x: int(pd.Timestamp(x).timestamp())  # noqa: E731
    f = lambda x: round(float(x), 10)  # noqa: E731 · yalnızca gösterim (3.9393000000000002 → 3.9393)
    stop = f(t.stop_price) if t.stop_price is not None else z.anchor_1_price
    return {
        "id": f"s{n:02d}", "n": n, "grup": grup, "symbol": t.symbol, "side": t.side,
        "zone_id": z.zone_id, "giris_ts": g.strftime("%Y-%m-%d %H:%M"), "cikis_ts": c.strftime("%Y-%m-%d %H:%M"),
        "giris": {"ts": sn(g), "fiyat": f(t.entry_price)},
        "cikis": {"ts": sn(c), "fiyat": f(t.exit_price), "sebep": t.reason},
        "capa_0": {"ts": sn(a0), "fiyat": z.anchor_0_price},
        "capa_1": {"ts": sn(z.anchor_1_time), "fiyat": z.anchor_1_price},
        "seviye": {"0": z.anchor_0_price, "0.50": f(z.level_050), "0.70": f(z.level_070), "0.79": f(z.level_079),
                   "1": z.anchor_1_price, "stop": stop},
        "ekleme": t.adds, "bias_4h": t.entry_bias,
        "h4": mumlar(d4[(d4.ts >= a0 - pd.Timedelta("14D")) & (d4.ts <= c + pd.Timedelta("1D"))]),
        "m30": mumlar(d30.iloc[max(0, i_g - 200): i_c + 51]),
    }


def uret() -> None:
    from src.data import collect

    p = pickle.loads(PKL.read_bytes())
    secim = sec(p["trades"])
    d30 = {s: collect.read_parquet("bingx", s, "30m") for s in sorted({t.symbol for _, t in secim})}
    d4 = {s: h4(d) for s, d in d30.items()}
    veri = [islem(n, g, t, p["zones"][t.zone_id], d30[t.symbol], d4[t.symbol])
            for n, (g, t) in enumerate(secim, 1)]
    kaynak = (f"{PKL.as_posix()} · parmak izi {p['hash']} · spec {p['spec_version']} · kod {p['code_version']} "
              f"· tohum {TOHUM}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(
        SAYFA.replace("__KAYNAK__", kaynak).replace("__SEBEPLER__", json.dumps(SEBEPLER, ensure_ascii=False))
        .replace("__VERI__", json.dumps(veri, ensure_ascii=False)), encoding="utf-8")
    print(OUT / "index.html", len(veri), "işlem")


SAYFA = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Strateji incelemesi</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root { --bg:#fafafa; --fg:#1b1b1b; --soluk:#666; --kart:#fff; --cizgi:#ddd; --vurgu:#1565c0;
        --s0:#2e7d32; --s1:#c62828; --giris:#1565c0; --cikis:#6a1b9a; --sev:#888; --stop:#c62828; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --fg:#e6e6e6; --soluk:#999; --kart:#1f2226;
        --cizgi:#33373c; --vurgu:#64b5f6; --s0:#66bb6a; --s1:#ef5350; --giris:#64b5f6; --cikis:#ce93d8;
        --sev:#aaa; --stop:#ef5350; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; }
main { max-width:1400px; margin:0 auto; padding:12px 16px 40px; }
h1 { font-size:18px; margin:4px 0; } .soluk { color:var(--soluk); font-size:12px; }
.ust { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:10px 0; }
button, select { font:inherit; padding:5px 10px; border:1px solid var(--cizgi); border-radius:6px;
                 background:var(--kart); color:var(--fg); cursor:pointer; }
button.secili { outline:2px solid var(--vurgu); font-weight:600; }
.kart { background:var(--kart); border:1px solid var(--cizgi); border-radius:8px; padding:10px; }
.grafik { width:100%; height:300px; } .grafik.alt { height:440px; margin-top:6px; }
textarea { width:100%; min-height:60px; font:inherit; background:var(--bg); color:var(--fg);
           border:1px solid var(--cizgi); border-radius:6px; padding:6px; }
#ilerleme { display:flex; flex-wrap:wrap; gap:3px; margin:6px 0; }
#ilerleme span { width:24px; height:18px; font-size:10px; text-align:center; border-radius:3px;
                 border:1px solid var(--cizgi); cursor:pointer; }
#ilerleme span.tamam { background:var(--vurgu); color:var(--bg); }
#ilerleme span.simdi { outline:2px solid var(--fg); }
#sebepler[hidden] { display:none; }
</style></head><body><main>
<h1>Strateji incelemesi — #31 OTE girişleri</h1>
<div class="soluk">Kaynak: __KAYNAK__. 20 işlem karışık sırada (bir kısmı en kötü kaybedenler, bir kısmı
rastgele — hangisi olduğu gösterilmez). Grafik çıkıştan sonrasını da gösterir. Üstte 4h (zone'un 0'ından 2 hafta
önce → çıkış + 1 gün), altta 30m (girişten 200 mum önce → çıkıştan 50 mum sonra). Çizgiler: 0 · 0.50 · 0.70 ·
0.79 · 1 · stop. Saatler UTC, mumun açılışı. Klavye: ← → gezinti.</div>
<div id="ilerleme"></div>
<div class="ust">
  <button id="geri">← önceki</button><select id="liste"></select><button id="ileri">sonraki →</button>
  <span style="flex:1"></span><span class="soluk" id="sayac"></span><button id="indir">Etiketleri indir</button>
</div>
<div class="kart">
  <div id="baslik" style="font-weight:600"></div>
  <div id="g4" class="grafik"></div><div id="g30" class="grafik alt"></div>
  <div class="ust"><b>Bu girişe</b>
    <button data-karar="girerdim">Girerdim</button><button data-karar="girmezdim">Girmezdim</button></div>
  <div class="ust" id="sebepler" hidden><b>Sebep:</b></div>
  <textarea id="not" placeholder="not (isteğe bağlı)"></textarea>
</div>
</main>
<script>
const IS = __VERI__, SEBEP = __SEBEPLER__, ANAHTAR = "janitor_strateji31_etiket";
let E = {};
try { E = JSON.parse(localStorage.getItem(ANAHTAR) || "{}"); } catch (e) { E = {}; }
const kaydet = () => { try { localStorage.setItem(ANAHTAR, JSON.stringify(E)); } catch (e) { console.warn(e); } };
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const utc = t => new Date(t * 1000).toISOString().slice(0, 16).replace("T", " ");
const $ = id => document.getElementById(id);
let i = 0, grafikler = [];
const etiket = a => E[a.id] ||= {id: a.id, karar: null, sebep: null, not: ""};
const tamam = a => !!(E[a.id] && (E[a.id].karar === "girerdim" || (E[a.id].karar === "girmezdim" && E[a.id].sebep)));
$("sebepler").insertAdjacentHTML("beforeend", SEBEP.map(s => `<button data-sebep="${s}">${s}</button>`).join(""));

function ciz() {
  grafikler.forEach(g => g.remove()); grafikler = [];
  const a = IS[i], e = etiket(a);
  for (const [id, adim, veri] of [["g4", 14400, a.h4], ["g30", 1800, a.m30]]) {
    const g = LightweightCharts.createChart($(id), {
      autoSize: true, layout: {background: {color: css("--kart")}, textColor: css("--fg")},
      grid: {vertLines: {color: css("--cizgi")}, horzLines: {color: css("--cizgi")}},
      timeScale: {timeVisible: true, secondsVisible: false, rightOffset: 4},
      localization: {timeFormatter: utc}, crosshair: {mode: 0}});
    const s = g.addCandlestickSeries({upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
      wickUpColor: "#26a69a", wickDownColor: "#ef5350", priceFormat: {type: "price", precision: 6, minMove: 0.000001}});
    s.setData(veri.map(r => ({time: r[0], open: r[1], high: r[2], low: r[3], close: r[4]})));
    const v = g.addHistogramSeries({priceScaleId: "hacim", priceFormat: {type: "volume"}, lastValueVisible: false,
                                    priceLineVisible: false});
    g.priceScale("hacim").applyOptions({scaleMargins: {top: 0.85, bottom: 0}});
    v.setData(veri.map(r => ({time: r[0], value: r[5], color: r[4] >= r[1] ? "#26a69a55" : "#ef535055"})));
    const yer = t => t - (t % adim), ust = a.side === "SHORT";
    const tepe0 = a.capa_0.fiyat > a.capa_1.fiyat;
    s.setMarkers([
      {time: yer(a.capa_0.ts), position: tepe0 ? "aboveBar" : "belowBar", color: css("--s0"),
       shape: tepe0 ? "arrowDown" : "arrowUp", text: "0"},
      {time: yer(a.capa_1.ts), position: tepe0 ? "belowBar" : "aboveBar", color: css("--s1"),
       shape: tepe0 ? "arrowUp" : "arrowDown", text: "1"},
      {time: yer(a.giris.ts), position: ust ? "aboveBar" : "belowBar", color: css("--giris"),
       shape: ust ? "arrowDown" : "arrowUp", text: "giriş " + a.giris.fiyat},
      {time: yer(a.cikis.ts), position: ust ? "belowBar" : "aboveBar", color: css("--cikis"),
       shape: "square", text: "çıkış " + a.cikis.sebep + " " + a.cikis.fiyat},
    ].filter(m => m.time >= veri[0][0]).sort((x, y) => x.time - y.time));
    for (const [ad, fiyat] of Object.entries(a.seviye))
      s.createPriceLine({price: fiyat, title: ad, lineWidth: ad === "stop" ? 2 : 1,
                         lineStyle: ad === "0" || ad === "1" ? 0 : 2,
                         color: css(ad === "stop" ? "--stop" : ad === "0" ? "--s0" : ad === "1" ? "--s1" : "--sev")});
    g.timeScale().fitContent();
    grafikler.push(g);
  }
  $("baslik").textContent = `#${a.n} · ${a.symbol} · ${a.side} · giriş ${a.giris_ts} → çıkış ${a.cikis_ts} UTC` +
    (a.ekleme ? ` · ${a.ekleme} ekleme` : "");
  document.querySelectorAll("[data-karar]").forEach(b => b.classList.toggle("secili", b.dataset.karar === e.karar));
  document.querySelectorAll("[data-sebep]").forEach(b => b.classList.toggle("secili", b.dataset.sebep === e.sebep));
  $("sebepler").hidden = e.karar !== "girmezdim";
  $("not").value = e.not;
  $("liste").value = i;
  $("sayac").textContent = `${IS.filter(tamam).length}/${IS.length} tamam`;
  $("ilerleme").innerHTML = IS.map((x, j) =>
    `<span data-j="${j}" class="${tamam(x) ? "tamam" : ""} ${j === i ? "simdi" : ""}">${x.n}</span>`).join("");
}

const git = j => { i = (j + IS.length) % IS.length; ciz(); };
$("liste").innerHTML = IS.map((a, j) => `<option value="${j}">#${a.n} ${a.symbol.split("/")[0]} ${a.giris_ts}</option>`).join("");
$("liste").onchange = ev => git(+ev.target.value);
$("geri").onclick = () => git(i - 1);
$("ileri").onclick = () => git(i + 1);
$("ilerleme").onclick = ev => { if (ev.target.dataset.j) git(+ev.target.dataset.j); };
document.querySelectorAll("[data-karar]").forEach(b => b.onclick = () => {
  const e = etiket(IS[i]); e.karar = b.dataset.karar; if (e.karar === "girerdim") e.sebep = null; kaydet(); ciz(); });
document.querySelectorAll("[data-sebep]").forEach(b => b.onclick = () => {
  etiket(IS[i]).sebep = b.dataset.sebep; kaydet(); ciz(); });
$("not").oninput = ev => { etiket(IS[i]).not = ev.target.value; kaydet(); };
document.addEventListener("keydown", ev => {
  if (ev.target.tagName === "TEXTAREA") return;
  if (ev.key === "ArrowLeft") git(i - 1); else if (ev.key === "ArrowRight") git(i + 1);
});
$("indir").onclick = () => {
  const veri = IS.map(a => ({...etiket(a), n: a.n, grup: a.grup, symbol: a.symbol, side: a.side, zone_id: a.zone_id,
                             giris_ts: a.giris_ts, cikis_ts: a.cikis_ts, cikis_sebep: a.cikis.sebep, bias_4h: a.bias_4h}));
  const url = URL.createObjectURL(new Blob([JSON.stringify(veri, null, 1)], {type: "application/json"}));
  Object.assign(document.createElement("a"), {href: url, download: "etiketler.json"}).click();
  URL.revokeObjectURL(url);
};
ciz();
</script></body></html>
"""


def main() -> int:
    uret()
    return 0


if __name__ == "__main__":
    sys.exit(main())
