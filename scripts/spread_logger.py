"""Emir defteri kayitcisi — spread ve ilk 5 kademe derinligi, dakikada bir.

    python -m scripts.bg scripts.spread_logger

**Neden var.** Backtest'in slippage'i bir **varsayimdir**: borsa slippage yayinlamaz,
bu yuzden `src/backtest/costs.py` onu acik bir parametre olarak tutar (§8) ve raporda
ayri satirda verir. Bu kayitci o varsayimi olculen veriyle degistirmek icindir: yeterli
gecmis birikince gercek spread ve derinlik dagilimi `slippage_bps` yerine gecer.

**Emir gondermez, anahtar istemez.** Yalnizca herkese acik emir defteri ucunu okur
(`fetch_order_book`). Bu dosyada hicbir kod yolu emir uretmez.

Kayit duzeni OHLCV ile ayni (ARCHITECTURE.md §3):
`data/{exchange}/{symbol}/book/{yyyy-mm}.parquet` — bir satir bir sembolun bir dakikasi.

| kolon | ne |
|---|---|
| `ts` | dakikaya yuvarlanmis anlik goruntu zamani (UTC) |
| `bid` `ask` `mid` | en iyi kademeler ve orta fiyat |
| `spread_bps` | `(ask - bid) / mid x 10.000` |
| `bid_p1..5` `bid_q1..5` | alis tarafinin ilk 5 kademesi (fiyat, miktar) |
| `ask_p1..5` `ask_q1..5` | satis tarafinin ilk 5 kademesi |

Derinlik **kademe kademe** saklanir, toplanmis degil: bir emrin defteri ne kadar
yuruyecegi ancak kademelerin sirasiyla hesaplanir; toplam "5 kademede su kadar var"
bilgisi o hesabi yapamaz ve sonradan geri uretilemez.

**Anlik goruntu, gecmis degil.** Borsa emir defteri gecmisi vermez; bu veri yalnizca
bu surecin kostugu dakikalar icin birikir. Kacirilan dakika kalicidir.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback

import pandas as pd

from src.data.collect import exchange, log_event, write_parquet

TIMEFRAME = "book"  # saklama duzeninde "zaman dilimi" yuvasi
DEPTH = 5  # kac kademe kaydedilir
CYCLE = 60.0  # saniye — dakikada bir anlik goruntu


def row(symbol: str, book: dict, ts: pd.Timestamp) -> dict:
    """Bir emir defteri anlik goruntusunden bir satir.

    Defter `DEPTH` kademeden sığ gelirse eksik kademeler `NaN` kalir — sifir yazmak
    "derinlik yok" ile "kademe gelmedi"yi karistirirdi (CLAUDE.md #8).
    """
    bids, asks = book.get("bids") or [], book.get("asks") or []
    if not bids or not asks:
        raise ValueError(f"{symbol}: emir defteri bos ({len(bids)} alis, {len(asks)} satis)")
    bid, ask = float(bids[0][0]), float(asks[0][0])
    mid = (bid + ask) / 2
    r = {"ts": ts, "bid": bid, "ask": ask, "mid": mid,
         "spread_bps": (ask - bid) / mid * 10_000 if mid else float("nan")}
    for taraf, kademeler in (("bid", bids), ("ask", asks)):
        for i in range(DEPTH):
            p, q = (kademeler[i][0], kademeler[i][1]) if i < len(kademeler) else (None, None)
            r[f"{taraf}_p{i + 1}"] = float(p) if p is not None else float("nan")
            r[f"{taraf}_q{i + 1}"] = float(q) if q is not None else float("nan")
    return r


def flush(tampon: dict[str, list[dict]], exchange_name: str) -> int:
    """Tamponu diske yazar ve bosaltir (sembol anahtarlari kalir). Satir sayisi doner."""
    n = 0
    for symbol, rows in tampon.items():
        if not rows:
            continue
        write_parquet(pd.DataFrame(rows), exchange_name, symbol, TIMEFRAME)
        n += len(rows)
        rows.clear()
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="Emir defteri spread/derinlik kayitcisi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--limit", type=int, default=20, help="liquidity.json'dan kac sembol")
    p.add_argument("--flush-every", type=int, default=30,
                   help="kac dakikada bir diske yazilir")
    p.add_argument("--cycles", type=int, default=0, help="kac dakika kosar; 0 = sonsuz")
    a = p.parse_args()

    if a.symbols:
        symbols = a.symbols
    else:
        from scripts.measure_ob import liquidity_symbols
        symbols = liquidity_symbols(a.limit)

    ex = exchange(a.exchange)
    tampon: dict[str, list[dict]] = {s: [] for s in symbols}
    print(f"{len(symbols)} sembol, dakikada bir, {a.flush_every} dakikada bir yazim",
          flush=True)

    i = 0
    try:
        while not a.cycles or i < a.cycles:
            t0 = time.time()
            ts = pd.Timestamp.now("UTC").floor("min")
            hata = 0
            for s in symbols:
                try:
                    tampon[s].append(row(s, ex.fetch_order_book(s, limit=DEPTH), ts))
                except Exception as exc:  # sembol duser, kayit surer — sessizce degil
                    hata += 1
                    log_event("collect", {"job": "spread_logger", "symbol": s,
                                          "error": repr(exc),
                                          "traceback": traceback.format_exc()})
            i += 1
            if hata == len(symbols):
                # Hicbir sembol gelmiyorsa sorun semboller degil baglantidir; sessizce
                # bos dosya biriktirmek yerine gorunur olsun.
                print(f"[{ts:%Y-%m-%d %H:%M}] hicbir sembol okunamadi", file=sys.stderr,
                      flush=True)
            if i % a.flush_every == 0:
                print(f"[{ts:%Y-%m-%d %H:%M}] {flush(tampon, a.exchange):,} satir yazildi"
                      f"{f'  ({hata} sembol hatali)' if hata else ''}", flush=True)
            uyku = CYCLE - (time.time() - t0)
            if uyku > 0:
                time.sleep(uyku)
    except KeyboardInterrupt:
        print("durduruldu", file=sys.stderr)
    finally:
        # Yarim tampon kaybolmaz: surec nasil biterse bitsin elde olan yazilir.
        n = flush(tampon, a.exchange)
        print(f"cikista {n:,} satir yazildi ({i:,} dakika kaydedildi)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
