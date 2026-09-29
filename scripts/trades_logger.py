"""Islem akisi kayitcisi — BingX herkese acik islem akisindan her islem.

    python -m scripts.bg scripts.trades_logger
    python -m scripts.trades_logger --delta BTC/USDT:USDT 2026-09-27   # dakika deltasi

**Neden var.** Dakika bazli delta ve kumulatif delta (agresor alis - agresor satis)
OHLCV'den turetilemez. Bu kayitci ham islemi saklar; delta ondan turetilir.

**Emir gondermez, anahtar istemez.** Yalnizca herkese acik `quote/trades` ucunu okur.

**Gecmis yok.** Uc yalnizca son 1.000 islemi verir; `fromId`, `startTime`, `endTime`
yok sayilir (2026-09-27 yoklamasi: BTC'de ~3 dakika, ORDI'de ~6 dakika geri). Veri
yalnizca bu surecin kostugu surece birikir. Kacirilan islem kalicidir.

**Neden REST, WebSocket degil.** WS islemi kimliksiz gonderir: kopan baglantida
kaybolan islem gorunmez. REST'te `fillId` sembol basina ardisik artar (1.000 islemde
aralik tam 999). Iki yoklama arasinda kimlik atlarsa kac islemin kacirildigi kesin
bilinir ve `logs/collect/` altina `trades_gap` olarak yazilir — sessiz kayip yok.
Yoklama `--cycle` saniyede bir; bir sembol o surede 1.000'den fazla islem gorurse
bosluk olusur.

Kayit: `data/{exchange}/{symbol}/trades/{yyyy-mm-dd}.parquet`, bir satir bir islem.

| kolon | ne |
|---|---|
| `id` | borsanin `fillId`'si, sembol basina ardisik |
| `ts` | islem zamani (UTC, ms) |
| `price` `qty` | fiyat, miktar (baz varlik) |
| `side` | agresor tarafi: `buy` = alici agresor (`isBuyerMaker` false) |
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from src.data import collect
from src.data.collect import _safe, exchange, log_event

TIMEFRAME = "trades"


def day_dir(exchange_name: str, symbol: str) -> Path:
    return collect.DATA_ROOT / exchange_name / _safe(symbol) / TIMEFRAME


def rows(trades: list[dict]) -> pd.DataFrame:
    """ccxt islemleri -> tablo. `fillId` yoksa hata: kimliksiz satir bosluk tespitini bozar."""
    return pd.DataFrame({
        "id": [int(t["info"]["fillId"]) for t in trades],
        "ts": pd.to_datetime([t["timestamp"] for t in trades], unit="ms", utc=True),
        "price": [float(t["price"]) for t in trades],
        "qty": [float(t["amount"]) for t in trades],
        "side": [t["side"] for t in trades],
    }).sort_values("id")


def flush(df: pd.DataFrame, exchange_name: str, symbol: str) -> None:
    """Gune bolerek yazar; mevcut gun dosyasiyla `id` uzerinden birlesir."""
    for gun, chunk in df.groupby(df.ts.dt.strftime("%Y-%m-%d")):
        path = day_dir(exchange_name, symbol) / f"{gun}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            chunk = pd.concat([pd.read_parquet(path), chunk], ignore_index=True)
        chunk = chunk.drop_duplicates("id").sort_values("id").reset_index(drop=True)
        tmp = path.with_suffix(".tmp")
        chunk.to_parquet(tmp, index=False)
        tmp.replace(path)  # atomik: sert kapanista yarim dosya kalmaz


def last_id(exchange_name: str, symbol: str) -> int | None:
    """Diskteki son islem kimligi — yeniden baslamadaki boslugu da saymak icin."""
    files = sorted(day_dir(exchange_name, symbol).glob("*.parquet"))
    return int(pd.read_parquet(files[-1], columns=["id"]).id.max()) if files else None


def minute_delta(df: pd.DataFrame) -> pd.DataFrame:
    """Dakika bazli delta ve kumulatif delta (baz varlik miktari cinsinden).

    `delta` = agresor alis - agresor satis. Islem olmayan dakika 0 delta ile yer alir,
    kumulatif delta dakikalar boyunca surer.
    """
    buy = df.qty.where(df.side == "buy", 0.0)
    out = pd.DataFrame({"buy": buy, "sell": df.qty - buy}).groupby(df.ts.dt.floor("min")).sum()
    out["delta"] = out.buy - out.sell
    out["n"] = df.groupby(df.ts.dt.floor("min")).size()
    out = out.asfreq("min", fill_value=0)
    out["cum_delta"] = out.delta.cumsum()
    return out


def poll(ex, symbol: str, last: int | None) -> tuple[pd.DataFrame, int | None, int]:
    """Bir yoklama: yeni islemler, yeni son kimlik, kacirilan islem sayisi."""
    df = rows(ex.fetch_trades(symbol, limit=1000))
    if last is not None:
        df = df[df.id > last]
    if df.empty:
        return df, last, 0
    kayip = int(df.id.iloc[0] - last - 1) if last is not None else 0
    return df, int(df.id.iloc[-1]), max(kayip, 0)


def main() -> int:
    p = argparse.ArgumentParser(description="Islem akisi kayitcisi")
    p.add_argument("--exchange", default="bingx")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--limit", type=int, default=20, help="liquidity.json'dan kac sembol")
    p.add_argument("--cycle", type=float, default=5.0, help="yoklama araligi, saniye")
    p.add_argument("--flush-every", type=float, default=300.0, help="yazim araligi, saniye")
    p.add_argument("--delta", nargs=2, metavar=("SEMBOL", "GUN"),
                   help="kayittan dakika deltasini yazdir ve cik")
    a = p.parse_args()

    if a.delta:
        path = day_dir(a.exchange, a.delta[0]) / f"{a.delta[1]}.parquet"
        print(minute_delta(pd.read_parquet(path)).to_string())
        return 0

    if a.symbols:
        symbols = a.symbols
    else:
        from scripts.measure_ob import liquidity_symbols
        symbols = liquidity_symbols(a.limit)

    ex = exchange(a.exchange)
    son = {s: last_id(a.exchange, s) for s in symbols}
    tampon: dict[str, list[pd.DataFrame]] = {s: [] for s in symbols}
    print(f"{len(symbols)} sembol, {a.cycle:g} sn'de bir yoklama, "
          f"{a.flush_every:g} sn'de bir yazim", flush=True)

    def yaz() -> int:
        n = 0
        for s, parcalar in tampon.items():
            if parcalar:
                df = pd.concat(parcalar, ignore_index=True)
                flush(df, a.exchange, s)
                n += len(df)
                parcalar.clear()
        return n

    t_flush, kayip_top = time.time(), 0
    try:
        while True:
            t0 = time.time()
            hata = 0
            for s in symbols:
                try:
                    df, yeni_son, kayip = poll(ex, s, son[s])
                except Exception as exc:  # sembol duser, kayit surer — sessizce degil
                    hata += 1
                    log_event("collect", {"job": "trades_logger", "symbol": s,
                                          "error": repr(exc),
                                          "traceback": traceback.format_exc()})
                    continue
                if kayip:
                    kayip_top += kayip
                    log_event("collect", {"job": "trades_gap", "symbol": s,
                                          "after_id": son[s], "next_id": int(df.id.iloc[0]),
                                          "missing": kayip})
                if not df.empty:
                    tampon[s].append(df)
                son[s] = yeni_son
            if hata == len(symbols):
                print(f"[{pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M:%S}] hicbir sembol okunamadi",
                      file=sys.stderr, flush=True)
            if time.time() - t_flush >= a.flush_every:
                n = yaz()
                print(f"[{pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M}] {n:,} islem yazildi"
                      f"{f'  (baslangictan beri {kayip_top:,} kacirildi)' if kayip_top else ''}",
                      flush=True)
                t_flush = time.time()
            uyku = a.cycle - (time.time() - t0)
            if uyku > 0:
                time.sleep(uyku)
    except KeyboardInterrupt:
        print("durduruldu", file=sys.stderr)
    finally:
        # Yarim tampon kaybolmaz: surec nasil biterse bitsin elde olan yazilir.
        print(f"cikista {yaz():,} islem yazildi", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
