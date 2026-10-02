"""Doluş kararı — `ExecutionAdapter` arayüzü ve backtest'in `SimAdapter`'ı.

CLAUDE.md #9: gerçek borsaya emir giden tek yer `ExecutionAdapter`'dır; paper ve live
aynı arayüzü uygular. `docs/LIVE.md` Ö2: motorun içindeki doluş simülasyonu buraya
taşındı. `SimAdapter` backtest'in bugünkü davranışının **aynısıdır**; `PaperAdapter`
onu sarıp kayıt ekleyecek (`docs/LIVE.md` §4).

Strateji ve risk "emir şu seviyede, bu mumda doldu mu" sorusunu burada sorar; cevabın
simülasyon mu gerçek borsa mı olduğunu bilmez.

**Kapsam dışı kalan doluş kararı.** TP'lerin 1 tick kuralı (`Zone.tp_tick`) zone durum
makinesinin içinde, `TP1_HIT`/`CLOSED` geçişini sürüyor. Taşımak R-ZONE-04 geçişlerini
değiştirir; tick değeri buradan verilir (`tp_tick`).
"""
from __future__ import annotations

import hashlib
from decimal import ROUND_FLOOR, Decimal
from typing import Protocol

# OPEN-37 · post-only giris emrinin dolus kriteri (yalnizca `limit_orders` acikken).
# `tick1` seviye 1 tick gecilmeli (mevcut) · `tick2` 2 tick · `kapanis` 1 tick gecilmeli
# **ve** mum seviyenin otesinde kapanmali (ayni mumda geri donen mum doldurmaz).
ENTRY_FILLS = ("tick1", "tick2", "kapanis")


def emir_miktari(qty: Decimal, price: Decimal, step: Decimal, min_qty: Decimal,
                 min_cost: Decimal) -> Decimal | None:
    """Borsaya gidecek miktar: adıma **aşağı** yuvarlanır; asgari miktar ya da asgari tutar
    karşılanmıyorsa `None` (emir reddedilir, çağıran sayar). CLAUDE.md #4, #5.

    Aşağı yuvarlama boyutu ve riski hiçbir zaman büyütmez. `step = 0` yuvarlamaz.
    """
    if step > 0:
        qty = (qty / step).to_integral_value(ROUND_FLOOR) * step
    if qty <= 0 or qty < min_qty or qty * price < min_cost:
        return None
    return qty


class ExecutionAdapter(Protocol):
    def limit_filled(self, symbol: str, level: float, high: float, low: float,
                     sell: bool) -> bool: ...

    def entry_filled(self, symbol: str, level: float, high: float, low: float,
                     close: float, sell: bool) -> bool: ...

    def taker(self, symbol: str, zone_id: str, tur: str, qty: Decimal,
              volume: float) -> bool: ...

    def tp_tick(self, symbol: str) -> float: ...


class SimAdapter:
    """Backtest doluş modeli: 1m mumdan limit doluşu + OPEN-36 taker'a düşme stresi.

    `limit_orders` kapalıyken her emir piyasa emridir ve temas yeter.
    """

    def __init__(self, ticks: dict[str, float], limit_orders: bool = False,
                 entry_fill: str = "tick1", taker_frac: float = 0.0,
                 taker_vol_frac: float = 0.0,
                 taker_kinds: frozenset[str] = frozenset({"giris", "tp1", "tp_nihai"}),
                 tp_market: bool = False):
        if entry_fill not in ENTRY_FILLS:
            raise ValueError(f"bilinmeyen giris dolus kriteri: {entry_fill}")
        if limit_orders:
            eksik = [s for s, t in ticks.items() if t <= 0]
            if eksik:
                raise ValueError(
                    f"fiyat adimi (tick) yok: {eksik} — once: python -m scripts.funding --fees-only"
                )
        self.ticks = ticks if limit_orders else {}
        self.limit_orders = limit_orders
        self.entry_fill = entry_fill
        # OPEN-36 · maker dolus stresi (spec'te yok, olcmek icin; ikisi de `0` = kapali).
        # Taker'a dusen limit emri **ayni mumda** dolar ama taker komisyonu ve slippage
        # oder; dolum zamanlamasi degismez (iyimser taraf: gercekte kacan emir de olur).
        # `taker_frac`: emrin (zone, tur) hash'i bu oranin altindaysa duser —
        # deterministik ve ic ice: %10'da dusen %25'te de duser.
        # `taker_vol_frac`: emir miktari dolum mumunun 1m hacminin bu oranini asarsa
        # duser. 1m hacim, defterdeki kuyrugun **vekili**dir (defter verisi yok).
        # `taker_kinds`: hangi emir turleri dusebilir (KALEM adlari; `giris` dahil).
        self.taker_frac = taker_frac
        self.taker_vol_frac = taker_vol_frac
        self.taker_kinds = taker_kinds
        self.tp_market = tp_market

    def limit_filled(self, symbol: str, level: float, high: float, low: float,
                     sell: bool) -> bool:
        """Limit emri doldu mu. `limit_orders` kapaliyken temas yeter (piyasa emri).

        Muhafazakar kural: satis limiti seviyenin **ustune** konur ve fiyat seviyeyi
        1 tick yukari gecmeden dolmus sayilmaz; alis limiti icin tersi. Sirada onde
        olma varsayimi yapilmaz — seviyeye degip donen mum emri doldurmaz.
        """
        if not self.limit_orders:
            return low <= level <= high
        t = self.ticks[symbol]
        return high >= level + t if sell else low <= level - t

    def entry_filled(self, symbol: str, level: float, high: float, low: float,
                     close: float, sell: bool) -> bool:
        """OPEN-37 · post-only giris emri doldu mu (`entry_fill` kriteri).

        `close` bu mumun kapanisi. Karar degil dolus modeli — emir mumdan once
        konmustu (CLAUDE.md #3).
        """
        if not self.limit_orders:
            # Giriş bekleyen limittir (`OPEN-41`): seviyeyi atlayan (boşluklu) mum da doldurur.
            return high >= level if sell else low <= level
        if self.entry_fill == "tick1":
            return self.limit_filled(symbol, level, high, low, sell)
        t = self.ticks[symbol]
        if self.entry_fill == "tick2":
            return high >= level + 2 * t if sell else low <= level - 2 * t
        return self.limit_filled(symbol, level, high, low, sell) and \
            (close >= level if sell else close <= level)

    def taker(self, symbol: str, zone_id: str, tur: str, qty: Decimal,
              volume: float) -> bool:
        """OPEN-36 · bu limit emri taker'a dustu mu. `volume`: dolum mumunun 1m hacmi."""
        if tur not in self.taker_kinds:
            return False
        dus = False
        if self.taker_frac:
            h = hashlib.blake2b(f"{zone_id}|{tur}".encode(), digest_size=8).digest()
            dus = int.from_bytes(h, "big") / 2 ** 64 < self.taker_frac
        if not dus and self.taker_vol_frac:
            dus = volume <= 0 or float(qty) > self.taker_vol_frac * volume  # hacimsiz mum: dolmaz
        return dus

    def tp_tick(self, symbol: str) -> float:
        """Zone'un TP 1 tick kuralı. `tp_market`: TP temasla dolar, aşım aranmaz."""
        return 0.0 if (self.tp_market or not self.limit_orders) else self.ticks[symbol]
