"""İşlem inceleme paketi — dürüst F1 koşusundan 30 işlem, grafik + not alanlı tek HTML.

    python -m scripts.inceleme --kos      # F1 eğitim koşusu (~6 dk) → logs/inceleme/f1.pkl
    python -m scripts.inceleme --kos --bakiye 100   # → logs/inceleme/f1_100.pkl (sayfaya girmez)
    python -m scripts.inceleme            # seçim + PNG + docs/inceleme/index.html

Koşu `logs/f1check/f1_check.py` ile aynı: düzeltilmiş damga, `OPEN-41`, boşluklu stop,
`liquidity_symbols(20)`, eğitim dilimi, F1 parametreleri. Parmak izi aynı formülle yazılır.

Seçim (tohum sabit, `TOHUM`): R'ye göre en kötü 10 kaybeden · kalan kaybedenlerden rastgele
10 · kazananlardan rastgele 10. R = net PnL / (giriş miktarı × |giriş − `1` çapası|) —
`1` çapası nihai stoptur (R-RISK-02). Sunum yalnızca: hiçbir sayı karar için kullanılmaz.

Grafik için `matplotlib` gerekir (`pip install matplotlib`); bilerek `requirements.txt`'de
değil — sunucu bu betiği koşmaz.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import pickle
import random
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

PKL = Path("logs/inceleme/f1.pkl")
OUT = Path("docs/inceleme")
TOHUM = 20261001
TR = "Europe/Istanbul"
TF = pd.Timedelta("30m")
PAY = 12  # grafikte zone'dan önce / çıkıştan sonra kaç 30m mum
MAKS_MUM = 700  # bundan uzun pencerede başlangıç girişe yaklaştırılır (çapalar dışarıda kalabilir)


def kos(bakiye: Decimal = Decimal("10000"), yol: Path | None = None) -> None:
    from scripts.measure_ob import liquidity_symbols
    from scripts.slippage_stres import F1_TABANI
    from src.backtest.costs import build_cost_model
    from src.backtest.engine import TRAIN_FRAC, Backtest, load_symbol, reset_for_rerun

    data = [d for d in (load_symbol(s, "bingx", TRAIN_FRAC) for s in liquidity_symbols(20)) if d]
    reset_for_rerun(data)
    res = Backtest(data, build_cost_model([d.symbol for d in data], "bingx"), bakiye,
                   k=Decimal("0.25"), mmr=Decimal("0.005"), t_rahat=Decimal("0.50"),
                   t_kritik=Decimal("0.08"), uyari_blocks_adds=False, progress_every=0,
                   **F1_TABANI).run()
    satir = [f"{t.symbol}|{t.entry_ts}|{t.exit_ts}|{t.entry_price}|{t.exit_price}|{t.qty}|"
             f"{t.pnl}|{t.reason}" for t in res.trades]
    iz = hashlib.sha256("\n".join(satir).encode()).hexdigest()[:16]
    zid = {t.zone_id for t in res.trades}
    from scripts.backtest import code_version, spec_version
    paket = {
        "spec_version": spec_version(), "code_version": code_version(),
        "trades": res.trades,
        "net": res.portfolio.balance - res.portfolio.start_balance,
        "hash": iz,
        "zones": {z.zone_id: z for d in data for z in d.zones if z.zone_id in zid},
        "obs": {d.symbol: d.obs for d in data},
        "fvgs": {d.symbol: d.fvgs for d in data},
        "bitis": {d.symbol: d.ts[-1] for d in data},
        "baslangic": {d.symbol: d.ts[0] for d in data},
        "bakiye": bakiye, "counters": res.counters,
    }
    yol = yol or (PKL if bakiye == Decimal("10000") else PKL.with_name(f"f1_{bakiye}.pkl"))
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(pickle.dumps(paket, pickle.HIGHEST_PROTOCOL))
    print(json.dumps({"net": str(paket["net"]), "islem": len(res.trades), "hash": iz,
                      "yol": str(yol)}))


def r_degeri(t, z) -> float:
    risk = float(t.entry_qty) * abs(float(t.entry_price) - z.anchor_1_price)
    return float(t.pnl) / risk if risk else float("nan")


def sec(trades, zones) -> list[tuple[str, object, float]]:
    rr = [(t, r_degeri(t, zones[t.zone_id])) for t in trades]
    kayip = sorted([x for x in rr if x[0].pnl < 0], key=lambda x: x[1])
    kazanc = [x for x in rr if x[0].pnl > 0]
    rnd = random.Random(TOHUM)
    en_kotu = kayip[:10]
    return ([("en kötü kaybeden", t, r) for t, r in en_kotu]
            + [("rastgele kaybeden", t, r) for t, r in rnd.sample(kayip[10:], 10)]
            + [("rastgele kazanan", t, r) for t, r in rnd.sample(kazanc, 10)])


def bantta(t, z, obs, fvgs):
    """Girişte (emir anı = giriş mumunun açılışı) uygun OB/FVG — motorun `eligible_*`'ı."""
    from src.strategy.entry import eligible_fvgs, eligible_obs
    return eligible_obs(obs, z, t.entry_ts), eligible_fvgs(fvgs, z, t.entry_ts)


def ciz(yol: Path, t, z, ob_l, fvg_l) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as md
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    from src.data import collect

    d = collect.read_parquet("bingx", t.symbol, "30m")
    bas = min(z.anchor_0_time, z.anchor_1_time) - PAY * TF
    son = pd.Timestamp(t.exit_ts).floor("30min") + PAY * TF
    not_ = ""
    if (son - bas) / TF > MAKS_MUM:
        bas = min(son - MAKS_MUM * TF, pd.Timestamp(t.entry_ts).floor("30min") - 50 * TF)
        not_ = "çapalar grafiğin solunda kaldı (pencere uzun)"
    d = d[(d.ts >= bas) & (d.ts <= son)]
    x = md.date2num(d.ts.dt.tz_convert("UTC").dt.tz_localize(None))
    gen = (TF / pd.Timedelta("1D")) * 0.7
    fig, ax = plt.subplots(figsize=(14, 6.5), dpi=100)
    yukari = (d.close >= d.open).to_numpy()
    for renk, m in (("#26a69a", yukari), ("#ef5350", ~yukari)):
        ax.vlines(x[m], d.low[m], d.high[m], color=renk, linewidth=0.7)
        ax.bar(x[m], (d.close - d.open).abs()[m].clip(lower=1e-12), gen,
               bottom=d[["open", "close"]].min(axis=1)[m], color=renk, linewidth=0)
    xn = lambda ts: md.date2num(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None))
    sag = x[-1] + gen
    z_bas = max(xn(z.anchor_1_time), x[0])
    for ad, fiyat, renk, stil in (("0", z.anchor_0_price, "#555", "-"),
                                  ("1 (stop)", z.anchor_1_price, "#b71c1c", "-"),
                                  ("0.50 (TP1)", z.level_050, "#1565c0", "--"),
                                  ("0.70", z.level_070, "#ef6c00", "--"),
                                  ("0.79", z.level_079, "#ef6c00", "--")):
        ax.hlines(fiyat, z_bas, sag, color=renk, linestyle=stil, linewidth=1)
        ax.text(sag, fiyat, f" {ad}  {fiyat:.6g}", va="center", fontsize=8, color=renk)
    ax.axhspan(min(z.level_070, z.level_079), max(z.level_070, z.level_079),
               xmin=0, xmax=1, color="#ffb74d", alpha=0.08)
    for kutu, renk, bitis in ([(o, "#7e57c2", o.mitigated_at) for o in ob_l]
                              + [(f, "#00897b", f.filled_at) for f in fvg_l]):
        x0 = max(xn(kutu.created_at), x[0])
        x1 = min(xn(bitis) if bitis is not None else sag, sag)
        ax.add_patch(Rectangle((x0, kutu.bottom), x1 - x0, kutu.top - kutu.bottom,
                               facecolor=renk, alpha=0.22, edgecolor=renk))
    for anchor, fiyat in ((z.anchor_0_time, z.anchor_0_price), (z.anchor_1_time, z.anchor_1_price)):
        if xn(anchor) >= x[0]:
            ax.plot(xn(anchor), fiyat, "o", color="#333", markersize=5)
    long_ = t.side == "LONG"
    ax.plot(xn(t.entry_ts), float(t.entry_price), "^" if long_ else "v", color="#0d47a1",
            markersize=12, markeredgecolor="white", label=f"giriş {float(t.entry_price):.6g}")
    ax.plot(xn(t.exit_ts), float(t.exit_price), "X", color="#000", markersize=11,
            markeredgecolor="white", label=f"çıkış {float(t.exit_price):.6g} ({t.reason})")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(x[0] - gen, sag + (x[-1] - x[0]) * 0.12)
    ax.xaxis.set_major_formatter(md.DateFormatter("%m-%d %H:%M"))
    ax.grid(alpha=0.2)
    ax.set_title(f"{t.symbol}  {t.side}  30m (UTC)  ·  mor kutu OB, yeşil kutu FVG, turuncu bant 0.70–0.79"
                 + (f"  ·  {not_}" if not_ else ""), fontsize=10)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(yol)
    plt.close(fig)
    return not_


def zaman(ts) -> tuple[str, str]:
    t = pd.Timestamp(ts)
    return t.tz_convert("UTC").strftime("%Y-%m-%d %H:%M"), t.tz_convert(TR).strftime("%Y-%m-%d %H:%M")


def kopya(deger: str) -> str:
    v = html.escape(deger)
    return f'<code class="k" title="kopyalamak için tıkla" data-v="{v}">{v}</code>'


def kart(n: int, grup: str, t, z, r: float, ob_l, fvg_l, png: str, not_: str) -> str:
    eu, et = zaman(t.entry_ts)
    cu, ct = zaman(t.exit_ts)
    tv = t.symbol.split("/")[0] + "USDT"
    yon = 1 if t.side == "LONG" else -1
    yuzde = (float(t.exit_price) / float(t.entry_price) - 1) * 100 * yon
    gost = "".join(
        f"<li>{tur} · {o.direction} · {o.bottom:.6g} – {o.top:.6g} · bilindi {zaman(o.known_at)[0]} UTC</li>"
        for tur, l in (("OB", ob_l), ("FVG", fvg_l)) for o in l) or "<li>yok</li>"
    sinif = "kayip" if t.pnl < 0 else "kazanc"
    return f"""
<section class="islem {sinif}" id="i{n}">
  <h2>#{n} · {html.escape(t.symbol)} · {t.side} <span class="grup">{grup}</span></h2>
  <div class="ust">
    <table>
      <tr><th>Sembol (TradingView)</th><td>{kopya(tv)} <small>BingX perpetual</small></td></tr>
      <tr><th>Zaman dilimi</th><td>zone 30m · giriş/çıkış 1m</td></tr>
      <tr><th>Giriş</th><td>{kopya(eu)} UTC · {kopya(et)} TR · <b>{float(t.entry_price):.6g}</b></td></tr>
      <tr><th>Çıkış</th><td>{kopya(cu)} UTC · {kopya(ct)} TR · <b>{float(t.exit_price):.6g}</b> · {t.reason}</td></tr>
      <tr><th>Sonuç</th><td class="{sinif}"><b>{r:+.2f} R</b> · fiyat {yuzde:+.2f}% · net {float(t.pnl):+.2f} $ (10.000 $ hesap)</td></tr>
      <tr><th>Çapalar</th><td>0: {z.anchor_0_price:.6g} ({zaman(z.anchor_0_time)[0]} UTC) · 1: {z.anchor_1_price:.6g} ({zaman(z.anchor_1_time)[0]} UTC)</td></tr>
      <tr><th>Fib</th><td>0.50: {z.level_050:.6g} · 0.70: {z.level_070:.6g} · 0.79: {z.level_079:.6g}</td></tr>
      <tr><th>Girişte bantta</th><td><ul>{gost}</ul></td></tr>
      <tr><th>Zone</th><td><small>{z.zone_id}</small>{' · ' + not_ if not_ else ''}</td></tr>
    </table>
  </div>
  <a href="{png}" target="_blank"><img src="{png}" alt="#{n} grafik" loading="lazy"></a>
  <label>Not #{n}<textarea data-n="{n}" placeholder="Bu işlem hakkında notun…"></textarea></label>
</section>"""


SAYFA = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>F1 İşlem İnceleme</title>
<style>
:root {{ --bg:#fafafa; --fg:#1b1b1b; --kart:#fff; --cizgi:#ddd; --kayip:#c62828; --kazanc:#2e7d32; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181b; --fg:#e6e6e6; --kart:#1f2226; --cizgi:#33373c; --kayip:#ef5350; --kazanc:#66bb6a; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1200px; padding:16px; }}
.islem {{ background:var(--kart); border:1px solid var(--cizgi); border-radius:8px; padding:12px 16px; margin:18px 0; }}
h2 {{ font-size:17px; margin:4px 0 10px; }} .grup {{ font-weight:400; font-size:13px; opacity:.7; }}
table {{ border-collapse:collapse; width:100%; }} th {{ text-align:left; white-space:nowrap; padding:3px 12px 3px 0; vertical-align:top; opacity:.75; font-weight:500; }}
td {{ padding:3px 0; }} ul {{ margin:0; padding-left:18px; }}
td.kayip {{ color:var(--kayip); }} td.kazanc {{ color:var(--kazanc); }}
.kayip h2 {{ border-left:4px solid var(--kayip); padding-left:8px; }} .kazanc h2 {{ border-left:4px solid var(--kazanc); padding-left:8px; }}
img {{ width:100%; height:auto; margin:10px 0; border:1px solid var(--cizgi); background:#fff; }}
textarea {{ width:100%; min-height:70px; box-sizing:border-box; margin-top:4px; font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--cizgi); border-radius:6px; padding:6px; }}
code.k {{ cursor:copy; background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }}
.bar {{ position:sticky; top:0; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--cizgi); z-index:1; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
button {{ font:inherit; padding:5px 12px; cursor:pointer; }}
</style></head><body>
<h1>F1 işlem inceleme — 30 işlem</h1>
<p>{ozet}</p>
<div class="bar"><button id="indir">Notları indir (notlar.md)</button><span id="durum"></span>
<span><a href="#i1">en kötü 1–10</a> · <a href="#i11">rastgele kaybeden 11–20</a> · <a href="#i21">rastgele kazanan 21–30</a></span></div>
{kartlar}
<script>
const A = "janitor-inceleme-";
const al = k => {{ try {{ return localStorage.getItem(A + k) || ""; }} catch (e) {{ return ""; }} }};
const koy = (k, v) => {{ try {{ localStorage.setItem(A + k, v); }} catch (e) {{}} }};
document.querySelectorAll("textarea").forEach(t => {{ t.value = al(t.dataset.n); t.addEventListener("input", () => koy(t.dataset.n, t.value)); }});
document.querySelectorAll("code.k").forEach(c => c.addEventListener("click", () => {{
  navigator.clipboard.writeText(c.dataset.v).then(() => {{ document.getElementById("durum").textContent = "kopyalandı: " + c.dataset.v; }});
}}));
document.getElementById("indir").addEventListener("click", () => {{
  const satir = [...document.querySelectorAll("section.islem")].map(s => {{
    const n = s.id.slice(1), b = s.querySelector("h2").textContent.trim();
    return n + ". " + b + "\\n   " + (s.querySelector("textarea").value.trim().replace(/\\n/g, "\\n   ") || "-");
  }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["# F1 inceleme notları\\n\\n" + satir.join("\\n\\n") + "\\n"], {{type: "text/markdown"}}));
  a.download = "notlar.md"; a.click();
}});
</script></body></html>
"""


def uret() -> None:
    p = pickle.loads(PKL.read_bytes())
    trades, zones = p["trades"], p["zones"]
    secim = sec(trades, zones)
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    kartlar, liste = [], []
    for n, (grup, t, r) in enumerate(secim, 1):
        z = zones[t.zone_id]
        ob_l, fvg_l = bantta(t, z, p["obs"][t.symbol], p["fvgs"][t.symbol])
        png = f"img/{n:02d}.png"
        not_ = ciz(OUT / png, t, z, ob_l, fvg_l)
        kartlar.append(kart(n, grup, t, z, r, ob_l, fvg_l, png, not_))
        liste.append(f"{n}. {t.symbol} {t.side} · giriş {zaman(t.entry_ts)[0]} UTC · {r:+.2f} R · "
                     f"{t.reason} ({grup})\n   ")
        print(f"{n:2d} {grup:18s} {t.symbol:16s} {r:+.2f}R", flush=True)
    kaz = sum(1 for t in trades if t.pnl > 0)
    ozet = (f"Kaynak: dürüst F1 koşusu (eğitim dilimi, düzeltilmiş zaman damgası, OPEN-41, boşluklu stop), "
            f"20 sembol, 10.000 $ başlangıç. Net {float(p['net']):+,.0f} $, {len(trades)} işlem, "
            f"kazanan {kaz} (%{kaz / len(trades) * 100:.1f}). Parmak izi <code>{p['hash']}</code> · "
            f"spec <code>{p['spec_version']}</code> · kod <code>{p['code_version']}</code>. "
            f"Seçim: R'ye göre en kötü 10 kaybeden, rastgele 10 kaybeden, rastgele 10 kazanan (tohum {TOHUM}). "
            f"R = net PnL / (giriş miktarı × |giriş − 1 çapası|). Notlar bu tarayıcıda saklanır; "
            f"“Notları indir” numaralı listeyi <code>notlar.md</code> olarak verir.")
    (OUT / "index.html").write_text(SAYFA.format(ozet=ozet, kartlar="".join(kartlar)), encoding="utf-8")
    (OUT / "notlar.md").write_text("# F1 inceleme notları\n\nHer maddenin altına notunu yaz.\n\n"
                                   + "\n\n".join(liste) + "\n", encoding="utf-8")


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--kos", action="store_true", help="F1 koşusunu yap ve sakla")
    a.add_argument("--bakiye", default="10000", help="başlangıç bakiyesi, USDT")
    g = a.parse_args()
    if g.kos:
        kos(Decimal(g.bakiye))
    else:
        uret()
    return 0


if __name__ == "__main__":
    sys.exit(main())
