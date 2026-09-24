"""Zone kalıcılığı — SQLite.

Spec: ARCHITECTURE.md §4.2 (`zones` tablosu), R-ZONE-01.

Zone her mumda yeniden hesaplanmaz; çökme sonrası durum buradan geri yüklenir.
Tablo şeması dataclass alanlarıyla birebir — kolon listesi tek yerde (`FIELDS`).

Zaman damgaları ISO-8601 metin olarak saklanır (SQLite'ın tarih tipi yok); okunurken
tz-aware `datetime`'a döner. Fiyatlar REAL: bunlar piyasa verisi, para hesabı değil
(CLAUDE.md #4).
"""
from __future__ import annotations

import sqlite3
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from src.zones.model import TERMINAL, Zone, ZoneState

FIELDS = [f.name for f in fields(Zone)]
TIME_FIELDS = {
    "anchor_0_time", "anchor_1_time", "created_at", "state_changed_at", "primed_at",
    "pivot_confirmed_at",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS zones (
    zone_id          TEXT PRIMARY KEY,
    symbol           TEXT NOT NULL,
    timeframe        TEXT NOT NULL,
    bias             TEXT NOT NULL,
    anchor_0_price   REAL NOT NULL,
    anchor_0_time    TEXT NOT NULL,
    anchor_1_price   REAL NOT NULL,
    anchor_1_time    TEXT NOT NULL,
    level_050        REAL NOT NULL,
    level_070        REAL NOT NULL,
    level_079        REAL NOT NULL,
    state            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    state_changed_at TEXT NOT NULL,
    primed_at        TEXT,
    touch_count      INTEGER NOT NULL,
    quality_score    REAL,
    pivot_confirmed_at TEXT,
    hysteresis       REAL NOT NULL,
    in_band          INTEGER NOT NULL,
    kill_wins        INTEGER NOT NULL,
    skipped_progress INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS zones_watch ON zones (symbol, timeframe, state);
"""


class ZoneStore:
    """`zones` tablosu üzerinde ince bir sarmalayıcı. ORM yok, ihtiyaç yok."""

    def __init__(self, path: str | Path = "state.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def save(self, zone: Zone) -> None:
        """Zone'u yazar; aynı `zone_id` varsa üzerine yazar (durum ilerler, kimlik sabit)."""
        row = [getattr(zone, name) for name in FIELDS]
        row = [v.isoformat() if isinstance(v, datetime) else v for v in row]
        row = [v.value if isinstance(v, ZoneState) else v for v in row]
        with self.conn:
            self.conn.execute(
                f"INSERT OR REPLACE INTO zones ({','.join(FIELDS)}) "
                f"VALUES ({','.join('?' * len(FIELDS))})",
                row,
            )

    def get(self, zone_id: str) -> Zone | None:
        row = self.conn.execute("SELECT * FROM zones WHERE zone_id = ?", (zone_id,)).fetchone()
        return _zone(row) if row else None

    def open_zones(self, symbol: str | None = None, timeframe: str | None = None) -> list[Zone]:
        """İzlenmeye devam eden zone'lar — terminal durumdakiler hariç (R-ZONE-06).

        İzlenen zone sayısına sınır yok; sınır pozisyon tarafında (R-RISK-01/05).
        """
        sql = f"SELECT * FROM zones WHERE state NOT IN ({','.join('?' * len(TERMINAL))})"
        args: list = [s.value for s in TERMINAL]
        for column, value in (("symbol", symbol), ("timeframe", timeframe)):
            if value is not None:
                sql += f" AND {column} = ?"
                args.append(value)
        return [_zone(r) for r in self.conn.execute(sql + " ORDER BY created_at", args)]

    def conflict_totals(self) -> dict[str, int]:
        """R-ZONE-09 · mum içi çakışma sayaçlarının tüm zone'lar üzerindeki toplamı.

        Zone başına değerler `Zone.kill_wins` / `Zone.skipped_progress` alanlarında.
        Oran yüksek çıkarsa kural yeniden ele alınır — bu yüzden sayılır.
        """
        row = self.conn.execute(
            "SELECT COALESCE(SUM(kill_wins), 0) AS kill_wins, "
            "COALESCE(SUM(skipped_progress), 0) AS skipped_progress FROM zones"
        ).fetchone()
        return dict(row)

    def close(self) -> None:
        self.conn.close()


def _zone(row: sqlite3.Row) -> Zone:
    data = dict(row)
    for name in TIME_FIELDS:
        if data[name] is not None:
            data[name] = datetime.fromisoformat(data[name])
    data["state"] = ZoneState(data["state"])
    data["in_band"] = bool(data["in_band"])  # SQLite'ta INTEGER
    return Zone(**data)
