"""FVG (Fair Value Gap) tespiti ve mitigasyon takibi.

Spec: R-ENTRY-02 (2) (bantta FVG varsa doldurulması beklenebilir), R-ADD-05
(OB içinde doldurulacak FVG gücü artırır).

**Tanım** (kullanıcı, 2026-09-11 — STRATEGY_SPEC'te FVG'nin sözlük tanımı yok, bkz.
`OPEN-22`): üç mumluk yapıda 1. ve 3. mumun **fitilleri** arasındaki dokunulmamış
boşluk. Gövde değil fitil; orta mumun yönü şart koşulmaz.

```
          ┌─┐  3. mum
          │ │
     ░░░░░░░░  boşluk = [1. mumun high'ı, 3. mumun low'u]
   ┌─┐
   │ │  1. mum
```

Zone gibi kalıcıdır (`FvgStore`): boşluk bir kez oluşur, mitigasyon zamanla işlenir.
`created_at` **3. mumun** zamanıdır — boşluk ancak o mum kapanınca bilinir
(CLAUDE.md #3). Fiyatlar float64: ham piyasa verisi, para hesabı değil (CLAUDE.md #4).
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.features.candles import reference_body

BULLISH = "BULLISH"  # yukarı boşluk — fiyat üstünde, aşağıdan doldurulur
BEARISH = "BEARISH"  # aşağı boşluk — fiyat altında, yukarıdan doldurulur

MIN_DETECT_TF = "5m"  # R-ZONE-09 · tespit zaman dilimi alt sınırı


def require_detect_tf(timeframe: str) -> None:
    """R-ZONE-09 · OB, FVG ve impuls tespiti 5m ve üstünde çalışır.

    1m yalnızca zone durum geçişleri içindir: o çözünürlükte gövdeler tick sınırına
    oturur, gövde/medyan oranı ayrık değerler alır ve eşik okuması kırılganlaşır.
    Sessizce 1m kabul etmek yerine hata verilir — yanlış TF'le üretilmiş bir OB
    listesi gürültüdür ama gürültü olduğu görünmez.
    """
    if pd.Timedelta(timeframe) < pd.Timedelta(MIN_DETECT_TF):
        raise ValueError(
            f"R-ZONE-09: OB/FVG tespiti {MIN_DETECT_TF} ve üstü içindir, {timeframe} verildi"
        )


@dataclass
class FVG:
    """Bir boşluk. `top`/`bottom` boşluğun fiyat sınırları, yön çizim yönü değil boşluğun yönü."""

    fvg_id: str
    symbol: str
    timeframe: str
    direction: str
    top: float
    bottom: float
    created_at: datetime
    mitigated_at: datetime | None = None  # fiyat boşluğa ilk girdiği an
    filled_at: datetime | None = None  # karşı sınır geçildi, boşluk kapandı
    width_ratio: float | None = None  # R-ENTRY-05 · genişlik / medyan gövde (20 mum)

    def overlaps(self, top: float, bottom: float) -> bool:
        """Verilen fiyat aralığıyla kesişiyor mu (R-ADD-05: OB içinde FVG)."""
        return self.bottom <= top and self.top >= bottom

    def on_bar(self, high: float, low: float, ts: datetime) -> None:
        """Mitigasyon durumunu ilerletir. Dolmuş boşluk bir daha değişmez.

        Mum içi sıra bilinmez: aynı mumda hem giriş hem tam dolum olabilir, ikisi de
        o muma işlenir (zone durum makinesindeki kötümser yaklaşımın karşılığı değil —
        burada iki olay birbiriyle çelişmiyor).
        """
        if self.filled_at is not None:
            return
        if self.direction == BULLISH:
            touched, filled = low <= self.top, low <= self.bottom
        else:
            touched, filled = high >= self.bottom, high >= self.top
        if touched and self.mitigated_at is None:
            self.mitigated_at = ts
        if filled:
            self.filled_at = ts


def detect_fvgs(df: pd.DataFrame, symbol: str, timeframe: str) -> list[FVG]:
    """Üç mumluk boşlukları tarar. Mumlar `ts` sıralı ve kapanmış olmalı.

    `df`: ts, open, high, low, close, volume (bkz. `src/data/collect.py`).
    """
    require_detect_tf(timeframe)
    prev = df.assign(
        prev_high=df.high.shift(2),
        prev_low=df.low.shift(2),
        # R-ENTRY-05 · genişlik ölçütünün paydası. Oluşum anında bilinir (shift(1)'li
        # medyan yalnızca geçmişe bakar), bu yüzden boşlukla birlikte saklanır.
        ref_body=reference_body(df),
    )
    out = []
    for r in prev.itertuples():
        if r.prev_high < r.low:  # NaN karşılaştırması False → ilk iki mum elenir
            direction, top, bottom = BULLISH, r.low, r.prev_high
        elif r.prev_low > r.high:
            direction, top, bottom = BEARISH, r.prev_low, r.high
        else:
            continue
        out.append(
            FVG(
                fvg_id=uuid.uuid4().hex,
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                top=top,
                bottom=bottom,
                created_at=r.ts,
                # Payda tanımsız veya sıfırsa oran yoktur; R-ENTRY-05 eşiği o boşluğu
                # geçiremez ve boşluk aday olmaz (None ile karşılaştırma yapılmaz).
                width_ratio=(
                    (top - bottom) / r.ref_body
                    if pd.notna(r.ref_body) and r.ref_body > 0
                    else None
                ),
            )
        )
    return out


def replay(fvgs: list[FVG], df: pd.DataFrame) -> None:
    """Boşlukları mumlarla besler — her boşluk yalnızca **kendinden sonraki** mumları görür.

    Look-ahead koruması tek yerde durur (CLAUDE.md #3): oluşum mumu ve öncesi bir
    boşluğu mitige edemez.

    Dolan boşlukta döngü kesilir ve başlangıç `searchsorted` ile bulunur: `on_bar` dolmuş
    boşlukta zaten hiçbir şey yapmıyordu, boşluk başına tüm geçmişi taramak yalnızca
    maliyetti (binlerce boşlukta O(n²)).
    """
    rows = list(df.itertuples())
    for f in fvgs:
        for i in range(int(df.ts.searchsorted(f.created_at, side="right")), len(rows)):
            r = rows[i]
            f.on_bar(r.high, r.low, r.ts)
            if f.filled_at is not None:
                break


# --- kalıcılık ---------------------------------------------------------------

FIELDS = [f.name for f in fields(FVG)]
TIME_FIELDS = {"created_at", "mitigated_at", "filled_at"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS fvgs (
    fvg_id       TEXT PRIMARY KEY,
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    direction    TEXT NOT NULL,
    top          REAL NOT NULL,
    bottom       REAL NOT NULL,
    created_at   TEXT NOT NULL,
    mitigated_at TEXT,
    filled_at    TEXT,
    width_ratio  REAL
);
CREATE INDEX IF NOT EXISTS fvgs_open ON fvgs (symbol, timeframe, filled_at);
"""


class FvgStore:
    """`fvgs` tablosu. ZoneStore ile aynı kalıp.

    ponytail: kalıp iki tabloda tekrarlanıyor; üçüncüsünde ortak bir yardımcıya çıkar.
    """

    def __init__(self, path: str | Path = "state.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save(self, fvg: FVG) -> None:
        row = [getattr(fvg, name) for name in FIELDS]
        row = [v.isoformat() if isinstance(v, datetime) else v for v in row]
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO fvgs ({','.join(FIELDS)}) "
                f"VALUES ({','.join('?' * len(FIELDS))})",
                row,
            )

    def get(self, fvg_id: str) -> FVG | None:
        row = self.conn.execute("SELECT * FROM fvgs WHERE fvg_id = ?", (fvg_id,)).fetchone()
        return _fvg(row) if row else None

    def unfilled(self, symbol: str | None = None, timeframe: str | None = None) -> list[FVG]:
        """Henüz doldurulmamış boşluklar — R-ENTRY-02 (2) ve R-ADD-05 girdisi."""
        sql = "SELECT * FROM fvgs WHERE filled_at IS NULL"
        args: list = []
        for column, value in (("symbol", symbol), ("timeframe", timeframe)):
            if value is not None:
                sql += f" AND {column} = ?"
                args.append(value)
        return [_fvg(r) for r in self.conn.execute(sql + " ORDER BY created_at", args)]

    def close(self) -> None:
        self.conn.close()


def _fvg(row: sqlite3.Row) -> FVG:
    data = dict(row)
    for name in TIME_FIELDS:
        if data[name] is not None:
            data[name] = datetime.fromisoformat(data[name])
    return FVG(**data)
