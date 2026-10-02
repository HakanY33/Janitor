"""Etiketleme paketi v2 — aynı 30 işlem, geniş bağlam, doğru çapa etiket alanları.

    python -m scripts.inceleme_v2 [--pkl logs/inceleme/f1.pkl]   # → docs/inceleme/v2/

Her işlem için iki grafik: üstte 4h (zone'dan önceki 14 gün → çıkış + 1 gün), altta 30m
(zone'dan önceki 300 mum → çıkış + 48 mum). Botun `0` ve `1` çapaları işaretli. Altında
kullanıcının dolduracağı alanlar: doğru `0` (mum saati UTC + fiyat), doğru `1`, ya da
"setup yok". Etiketler tarayıcıda saklanır ve `etiketler.json` olarak indirilir —
swing aday tanımları bu dosyayla karşılaştırılır (`docs/inceleme/v2/adaylar.md`).

Seçim v1'in aynısı (`scripts/inceleme.py:sec`, aynı pkl ve tohum). Yalnızca sunum.
"""
from __future__ import annotations

import argparse
import html
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

from scripts.inceleme import PAY, PKL, MAKS_MUM, TF, kopya, r_degeri, sec, zaman

OUT = Path("docs/inceleme/v2")
ONCE_4H = pd.Timedelta("14D")
ONCE_30 = 300
SONRA_30 = 48

# Notlardan çıkan çapa ipuçları (docs/inceleme/notlar.md). Saatler v1 grafiğinin
# eksenidir (UTC). (saat, uç) — uç `high`/`low`; "-3"/"-4" bot çapasından mum farkı.
IPUCU = {
    11: ("“0.4175 fiyatlandırma bölgesini (19:12) geçememiş; 04:48 bölgesindeki 1 noktası. "
         "19:12'den 0.434'e short OTE, ya da 13:30 mumunun en altından long OTE, 15:00 teması giriş.”",
         [("19:12", "high"), ("04:48", "low"), ("13:30", "low"), ("15:00", "low")]),
    18: ("“low bölgesini 12:30'dan alsaydın (daha eskide daha low likidite olabilir) 0.5 teması "
         "gelmez, işleme girmezdin.”", [("12:30", "low")]),
    19: ("“05:00 mumundan low alınıp long OTE mini setup kursaydın TP olurdun; yine de OTE'yi "
         "geniş alandan almak daha mantıklı.”", [("05:00", "low")]),
    20: ("“13:30 mumundan high (daha geçmişte yüksek likidite varsa oradan), 15:00 mumundan low "
         "→ long biaslı OTE.”", [("13:30", "high"), ("15:00", "low")]),
    23: ("“low noktası doğru; high daha geride (4h'ta). 01:30 mumundan high alarak short OTE.”",
         [("01:30", "high")]),
    28: ("“high noktası 3 ya da 4 mum öncesi olmalı.”", [("-3", "high"), ("-4", "high")]),
    29: ("“high likidite bölgesi 04:00 ya da 04:30 mumlarından; o setupta 0.5 teması hiç "
         "gelmezdi.”", [("04:00", "high"), ("04:30", "high")]),
}


def v1_penceresi(t, z) -> tuple[pd.Timestamp, pd.Timestamp]:
    """v1 grafiğinin (`scripts/inceleme.py:ciz`) zaman penceresi — ipucu saatleri oradan."""
    bas = min(z.anchor_0_time, z.anchor_1_time) - PAY * TF
    son = pd.Timestamp(t.exit_ts).floor("30min") + PAY * TF
    if (son - bas) / TF > MAKS_MUM:
        bas = min(son - MAKS_MUM * TF, pd.Timestamp(t.entry_ts).floor("30min") - 50 * TF)
    return bas, son


def ipucu_noktalari(n: int, t, z, d30: pd.DataFrame) -> list[tuple[pd.Timestamp, float, str]]:
    """İpucu saatlerini v1 penceresindeki mumlara çevirir: (an, fiyat, etiket)."""
    if n not in IPUCU:
        return []
    bas, son = v1_penceresi(t, z)
    w = d30[(d30.ts >= bas) & (d30.ts <= son)]
    yuksek = max((z.anchor_0_price, z.anchor_0_time), (z.anchor_1_price, z.anchor_1_time))
    out = []
    for saat, uc in IPUCU[n][1]:
        if saat.startswith("-"):  # bot'un aynı uçtaki çapasından k mum önce
            an = pd.Timestamp(yuksek[1]) - int(saat[1:]) * TF
            satir = w[w.ts == an]
        else:
            hh, mm = map(int, saat.split(":"))
            dk = hh * 60 + mm
            mum = w.ts.dt.hour * 60 + w.ts.dt.minute
            satir = w[(mum <= dk) & (dk < mum + 30)]
        for _, r in satir.iterrows():
            out.append((r.ts, float(r.high if uc == "high" else r.low), f"öneri {saat} {uc}"))
    return out


def _mumlar(ax, d: pd.DataFrame, gen: float) -> None:
    import matplotlib.dates as md
    x = md.date2num(d.ts.dt.tz_convert("UTC").dt.tz_localize(None))
    yukari = (d.close >= d.open).to_numpy()
    for renk, m in (("#26a69a", yukari), ("#ef5350", ~yukari)):
        ax.vlines(x[m], d.low[m], d.high[m], color=renk, linewidth=0.6)
        ax.bar(x[m], (d.close - d.open).abs()[m].clip(lower=1e-12), gen,
               bottom=d[["open", "close"]].min(axis=1)[m], color=renk, linewidth=0)


def ciz(yol: Path, n: int, t, z, d30: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as md
    import matplotlib.pyplot as plt

    xn = lambda ts: md.date2num(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None))
    ilk = min(z.anchor_0_time, z.anchor_1_time)
    cikis = pd.Timestamp(t.exit_ts)
    d4 = (d30.set_index("ts").resample("4h", closed="left", label="left")
          .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
               close=("close", "last")).dropna().reset_index())
    d4 = d4[(d4.ts >= ilk - ONCE_4H) & (d4.ts <= cikis + pd.Timedelta("1D"))]
    i0 = int(d30.ts.searchsorted(ilk)) - ONCE_30
    i1 = int(d30.ts.searchsorted(cikis.floor("30min"))) + SONRA_30
    d3 = d30.iloc[max(i0, 0):i1 + 1]

    fig, (ust, alt) = plt.subplots(2, 1, figsize=(18, 12), dpi=100,
                                   gridspec_kw={"height_ratios": [1, 1.25]})
    for ax, d, gen, baslik in ((ust, d4, 4 / 24 * 0.7, "4h · zone'dan önceki 14 gün"),
                               (alt, d3, 1 / 48 * 0.7, "30m · zone'dan önceki 300 mum")):
        _mumlar(ax, d, gen)
        x0, x1 = xn(d.ts.iloc[0]), xn(d.ts.iloc[-1])
        for ad, fiyat, renk in (("bot 0", z.anchor_0_price, "#555"),
                                ("bot 1", z.anchor_1_price, "#b71c1c"),
                                ("0.50", z.level_050, "#1565c0"), ("0.70", z.level_070, "#ef6c00")):
            ax.hlines(fiyat, xn(ilk), x1 + gen, color=renk, linestyle="--", linewidth=0.8)
            ax.text(x1 + gen, fiyat, f" {ad} {fiyat:.6g}", va="center", fontsize=8, color=renk)
        for ad, an, fiyat in (("0", z.anchor_0_time, z.anchor_0_price),
                              ("1", z.anchor_1_time, z.anchor_1_price)):
            ax.plot(xn(an), fiyat, "o", color="#000", markersize=7, markerfacecolor="none",
                    markeredgewidth=2)
            ax.annotate(f"bot {ad}\n{zaman(an)[0][5:]}", (xn(an), fiyat), fontsize=8,
                        xytext=(0, 14 if fiyat == max(z.anchor_0_price, z.anchor_1_price) else -24),
                        textcoords="offset points", ha="center")
        ax.axvline(xn(t.entry_ts), color="#0d47a1", linewidth=0.8, alpha=0.6)
        ax.axvline(xn(cikis), color="#000", linewidth=0.8, alpha=0.6, linestyle=":")
        ax.set_xlim(x0 - gen, x1 + (x1 - x0) * 0.10)
        ax.xaxis.set_major_locator(md.AutoDateLocator(minticks=8, maxticks=24))
        ax.xaxis.set_major_formatter(md.DateFormatter("%m-%d\n%H:%M"))
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=8)
        ax.set_title(f"#{n} {t.symbol} {t.side} · {baslik} · UTC · mavi çizgi giriş, noktalı çıkış",
                     fontsize=10, loc="left")
    for an, fiyat, etiket in ipucu_noktalari(n, t, z, d30):
        alt.plot(xn(an), fiyat, "D", color="#8e24aa", markersize=6)
        alt.annotate(etiket, (xn(an), fiyat), fontsize=7, color="#8e24aa",
                     xytext=(4, 4), textcoords="offset points")
    fig.tight_layout()
    fig.savefig(yol)
    plt.close(fig)


def kart(n: int, grup: str, t, z, r: float, png: str) -> str:
    eu, _ = zaman(t.entry_ts)
    tv = t.symbol.split("/")[0] + "USDT"
    sinif = "kayip" if t.pnl < 0 else "kazanc"
    ipucu = (f'<p class="ipucu"><b>Notundan öneri:</b> {html.escape(IPUCU[n][0])} '
             f'<small>(grafikte mor ◆; saatler v1 grafiğinden, UTC)</small></p>') if n in IPUCU else ""
    alan = lambda ad, yer: (f'<label>{ad}<input data-k="{n}.{yer}" placeholder="'
                            f'{"2025-10-28 01:30" if yer.endswith("t") else "fiyat"}"></label>')
    return f"""
<section class="islem {sinif}" id="i{n}">
  <h2>#{n} · {html.escape(t.symbol)} · {t.side} <span class="grup">{grup} · {r:+.2f} R · {t.reason}</span></h2>
  <p>{kopya(tv)} · giriş {kopya(eu)} UTC · bot 0: <b>{z.anchor_0_price:.6g}</b> ({zaman(z.anchor_0_time)[0]})
     · bot 1: <b>{z.anchor_1_price:.6g}</b> ({zaman(z.anchor_1_time)[0]})</p>
  {ipucu}
  <a href="{png}" target="_blank"><img src="{png}" alt="#{n} grafik" loading="lazy"></a>
  <fieldset>
    <legend>Doğru çapalar (mum saati UTC, 30m mumun açılışı)</legend>
    <div class="satir">{alan("0 · saat", "0t")}{alan("0 · fiyat", "0p")}</div>
    <div class="satir">{alan("1 · saat", "1t")}{alan("1 · fiyat", "1p")}</div>
    <label class="yok"><input type="checkbox" data-k="{n}.yok"> setup yok</label>
    <label>Not<textarea data-k="{n}.not"></textarea></label>
  </fieldset>
</section>"""


SAYFA = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Çapa Etiketleme v2</title>
<style>
:root {{ --bg:#fafafa; --fg:#1b1b1b; --kart:#fff; --cizgi:#ddd; --kayip:#c62828; --kazanc:#2e7d32; --oneri:#8e24aa; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181b; --fg:#e6e6e6; --kart:#1f2226; --cizgi:#33373c; --kayip:#ef5350; --kazanc:#66bb6a; --oneri:#ce93d8; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1400px; padding:16px; }}
.islem {{ background:var(--kart); border:1px solid var(--cizgi); border-radius:8px; padding:12px 16px; margin:18px 0; }}
h2 {{ font-size:17px; margin:4px 0 8px; }} .grup {{ font-weight:400; font-size:13px; opacity:.7; }}
.kayip h2 {{ border-left:4px solid var(--kayip); padding-left:8px; }} .kazanc h2 {{ border-left:4px solid var(--kazanc); padding-left:8px; }}
img {{ width:100%; height:auto; margin:8px 0; border:1px solid var(--cizgi); background:#fff; }}
.ipucu {{ border-left:3px solid var(--oneri); padding:4px 10px; margin:6px 0; }}
fieldset {{ border:1px solid var(--cizgi); border-radius:6px; padding:8px 12px; }}
.satir {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:6px; }}
label {{ display:flex; flex-direction:column; font-size:13px; gap:2px; }}
label.yok {{ flex-direction:row; align-items:center; gap:6px; margin:4px 0; }}
input:not([type]), textarea {{ font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--cizgi); border-radius:6px; padding:5px 8px; min-width:200px; }}
textarea {{ min-height:50px; width:100%; box-sizing:border-box; }}
code.k {{ cursor:copy; background:rgba(127,127,127,.15); padding:1px 5px; border-radius:4px; }}
.bar {{ position:sticky; top:0; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--cizgi); z-index:1; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
button {{ font:inherit; padding:5px 12px; cursor:pointer; }}
</style></head><body>
<h1>Çapa etiketleme v2 — aynı 30 işlem</h1>
<p>{ozet}</p>
<div class="bar"><button id="indir">Etiketleri indir (etiketler.json)</button><span id="durum"></span></div>
{kartlar}
<script>
const A = "janitor-etiket-v2-";
const al = k => {{ try {{ return localStorage.getItem(A + k) || ""; }} catch (e) {{ return ""; }} }};
const koy = (k, v) => {{ try {{ localStorage.setItem(A + k, v); }} catch (e) {{}} }};
document.querySelectorAll("[data-k]").forEach(el => {{
  const k = el.dataset.k, kutu = el.type === "checkbox";
  if (kutu) el.checked = al(k) === "1"; else el.value = al(k);
  el.addEventListener("input", () => koy(k, kutu ? (el.checked ? "1" : "") : el.value));
}});
document.querySelectorAll("code.k").forEach(c => c.addEventListener("click", () => {{
  navigator.clipboard.writeText(c.dataset.v).then(() => {{ document.getElementById("durum").textContent = "kopyalandı: " + c.dataset.v; }});
}}));
const META = {meta};
document.getElementById("indir").addEventListener("click", () => {{
  const v = k => (document.querySelector(`[data-k="${{k}}"]`) || {{}});
  const out = META.map(m => ({{ ...m,
    dogru_0: {{ saat: v(m.n + ".0t").value || null, fiyat: v(m.n + ".0p").value || null }},
    dogru_1: {{ saat: v(m.n + ".1t").value || null, fiyat: v(m.n + ".1p").value || null }},
    setup_yok: !!v(m.n + ".yok").checked, not: v(m.n + ".not").value || "" }}));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {{type: "application/json"}}));
  a.download = "etiketler.json"; a.click();
}});
</script></body></html>
"""


def uret(pkl: Path) -> None:
    from src.data import collect

    p = pickle.loads(pkl.read_bytes())
    secim = sec(p["trades"], p["zones"])
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    kartlar, meta = [], []
    for n, (grup, t, r) in enumerate(secim, 1):
        z = p["zones"][t.zone_id]
        d30 = collect.read_parquet("bingx", t.symbol, "30m")
        png = f"img/{n:02d}.png"
        ciz(OUT / png, n, t, z, d30)
        kartlar.append(kart(n, grup, t, z, r, png))
        meta.append({"n": n, "symbol": t.symbol, "side": t.side, "zone_id": z.zone_id,
                     "entry_ts": zaman(t.entry_ts)[0],
                     "bot_0": {"saat": zaman(z.anchor_0_time)[0], "fiyat": z.anchor_0_price},
                     "bot_1": {"saat": zaman(z.anchor_1_time)[0], "fiyat": z.anchor_1_price}})
        print(f"{n:2d} {t.symbol}", flush=True)
    ozet = (f"Kaynak: v1 ile aynı 30 işlem (<code>{pkl}</code>, parmak izi <code>{p['hash']}</code>, "
            f"spec <code>{p['spec_version']}</code>, kod <code>{p['code_version']}</code>). "
            "Her işlemde üstte 4h (zone'dan önceki 14 gün), altta 30m (zone'dan önceki 300 mum ve "
            "çıkıştan sonra 48 mum). Botun çapaları siyah halka. Saatler <b>UTC</b>, 30m mumun açılışı "
            "(TradingView'da UTC seç). Doğru çapa yoksa “setup yok”. Etiketler bu tarayıcıda saklanır; "
            "bitince “Etiketleri indir” ve dosyayı <code>docs/inceleme/v2/etiketler.json</code> olarak koy.")
    (OUT / "index.html").write_text(
        SAYFA.format(ozet=ozet, kartlar="".join(kartlar), meta=json.dumps(meta, ensure_ascii=False)),
        encoding="utf-8")


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--pkl", default=str(PKL))
    uret(Path(a.parse_args().pkl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
