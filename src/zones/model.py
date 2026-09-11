"""Zone veri modeli ve durum makinesi.

Spec: R-ZONE-01 (alanlar), R-ZONE-03 (seviyeler), R-ZONE-04 (durum makinesi),
R-ZONE-05 (geçersizlik), STRATEGY_SPEC §0 (bias, zorunlu sıra).

Zone kalıcı bir nesnedir, her mumda yeniden hesaplanmaz: `on_bar` mevcut durumu
ilerletir, durum SQLite'ta saklanır (bkz. `src/zones/store.py`).

Fiyatlar float64. Bunlar ham piyasa verisi üzerinde yapılan fib hesabıdır, borsaya
giden bir miktar değil (CLAUDE.md #4). Decimal'e çevirme `execution` sınırındadır.

**Temas tanımı:** mumun aralığı seviyeyi içeriyorsa temas vardır (`low <= seviye <= high`).
Mum *içi* sıra bilinmez — bunun iki sonucu var, ikisi de kötümser tarafta:

  1. Bir mumda hem ilerleme hem geçersizlik koşulu oluşursa **geçersizlik kazanır**.
  2. Bir mumda en fazla **bir** ilerleme yapılır (0.50 ve 0.70'i aynı mumda gören zone
     yalnızca PRIMED olur; giriş için bir sonraki temas beklenir).

Daha ince sıra çözümü isteniyorsa girdi 30m yerine 1m mum olmalı; model değişmez.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ZoneState(str, Enum):
    """R-ZONE-04 durumları. `str` tabanlı: SQLite'a olduğu gibi yazılır."""

    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PRIMED = "PRIMED"
    TOUCHED = "TOUCHED"
    ENTERED = "ENTERED"
    TP1_HIT = "TP1_HIT"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"


S = ZoneState
TERMINAL = frozenset({S.CLOSED, S.INVALIDATED})

# R-ZONE-04. ENTERED -> CLOSED, diyagramda çizilmemiş ama R-ZONE-04 tablosu CLOSED'ı
# "nihai TP (0) veya stop (1)" diye tanımlıyor ve R-ZONE-05 ENTERED'de 1 temasını
# "nihai stop" sayıyor. Bkz. OPEN-ZONE-01.
TRANSITIONS: dict[ZoneState, frozenset[ZoneState]] = {
    S.CREATED: frozenset({S.ACTIVE}),
    S.ACTIVE: frozenset({S.PRIMED, S.INVALIDATED}),
    S.PRIMED: frozenset({S.TOUCHED, S.INVALIDATED}),
    S.TOUCHED: frozenset({S.ENTERED, S.INVALIDATED}),
    S.ENTERED: frozenset({S.TP1_HIT, S.CLOSED, S.INVALIDATED}),
    S.TP1_HIT: frozenset({S.CLOSED, S.INVALIDATED}),
    S.CLOSED: frozenset(),
    S.INVALIDATED: frozenset(),
}


class InvalidTransition(Exception):
    """R-ZONE-04 dışı durum geçişi. Sessizce yutulmaz (CLAUDE.md #8)."""


def touches(level: float, high: float, low: float) -> bool:
    """Mum aralığı seviyeyi içeriyor mu."""
    return low <= level <= high


@dataclass
class Zone:
    """R-ZONE-01 · Zone nesnesi. Alan sırası spec'teki sırayla aynı."""

    zone_id: str
    symbol: str
    timeframe: str
    bias: str  # LONG | SHORT — çizim yönünden türetilir (§0)
    anchor_0_price: float
    anchor_0_time: datetime
    anchor_1_price: float
    anchor_1_time: datetime
    level_050: float
    level_070: float
    level_079: float
    state: ZoneState
    created_at: datetime
    state_changed_at: datetime
    primed_at: datetime | None = None
    touch_count: int = 0
    quality_score: float | None = None  # R-ZONE-08 TASARLANACAK — kod hesaplamaz

    @classmethod
    def create(
        cls,
        symbol: str,
        timeframe: str,
        anchor_0_price: float,
        anchor_0_time: datetime,
        anchor_1_price: float,
        anchor_1_time: datetime,
        zone_id: str | None = None,
    ) -> Zone:
        """Çapalardan zone kurar: seviyeler R-ZONE-03, bias §0 tablosu.

        `created_at` çapa zamanından gelir, duvar saatinden değil — backtest ve canlı
        aynı zone'u üretsin diye.
        """
        for name, t in (("anchor_0_time", anchor_0_time), ("anchor_1_time", anchor_1_time)):
            if t.tzinfo is None or t.utcoffset() is None:
                raise ValueError(f"{name} tz-naive; UTC olmalı (ARCHITECTURE.md §3)")
        if anchor_0_price == anchor_1_price:
            raise ValueError("çapalar aynı fiyatta; leg yok")

        span = anchor_1_price - anchor_0_price
        created_at = max(anchor_0_time, anchor_1_time)
        return cls(
            zone_id=zone_id or uuid.uuid4().hex,
            symbol=symbol,
            timeframe=timeframe,
            bias="SHORT" if span > 0 else "LONG",  # 0 altta → SHORT (§0)
            anchor_0_price=anchor_0_price,
            anchor_0_time=anchor_0_time,
            anchor_1_price=anchor_1_price,
            anchor_1_time=anchor_1_time,
            level_050=anchor_0_price + 0.50 * span,  # lineer fib, log kapalı
            level_070=anchor_0_price + 0.70 * span,
            level_079=anchor_0_price + 0.79 * span,
            state=S.CREATED,
            created_at=created_at,
            state_changed_at=created_at,
        )

    # --- durum geçişleri -----------------------------------------------------

    def transition(self, new_state: ZoneState, ts: datetime) -> ZoneState:
        """R-ZONE-04 dışı her geçiş `InvalidTransition` yükseltir."""
        if new_state not in TRANSITIONS[self.state]:
            raise InvalidTransition(
                f"{self.zone_id}: {self.state.value} -> {new_state.value} geçersiz (R-ZONE-04)"
            )
        self.state = new_state
        self.state_changed_at = ts
        if new_state is S.PRIMED:
            self.primed_at = ts
        return new_state

    def activate(self, ts: datetime) -> ZoneState:
        """CREATED → ACTIVE. Zone izlemeye alındı, 0.50 teması bekleniyor (R-ZONE-06)."""
        return self.transition(S.ACTIVE, ts)

    def enter(self, ts: datetime) -> ZoneState:
        """TOUCHED → ENTERED. Kararı strateji + risk katmanı verir, fiyat değil.

        0.70 teması girişin *gerekli* koşuludur, yeterli değil: R-ENTRY-02 bantta OB/FVG
        arar, R-RISK veto edebilir. Zone bu yüzden kendi kendine ENTERED'a geçmez.
        """
        return self.transition(S.ENTERED, ts)

    def on_bar(self, high: float, low: float, ts: datetime) -> ZoneState:
        """Kapanmış bir mumu uygular ve yeni durumu döner.

        Spec: R-ZONE-04 (ilerleme), R-ZONE-05 (geçersizlik).

        Sıra önemlidir: önce çapa teması (öldürür), sonra ilerleme. CREATED ve terminal
        durumlar fiyat işlemez.
        """
        if self.state is S.CREATED or self.state in TERMINAL:
            return self.state

        if touches(self.anchor_0_price, high, low) or touches(self.anchor_1_price, high, low):
            # R-ZONE-05: giriş öncesi sıra bozuldu → zone ölür. Pozisyon varken aynı temas
            # tanımlı sonuçtur: 0 = nihai TP, 1 = nihai stop → CLOSED.
            return self.transition(
                S.CLOSED if self.state in (S.ENTERED, S.TP1_HIT) else S.INVALIDATED, ts
            )

        if self.state in (S.PRIMED, S.TOUCHED) and touches(self.level_070, high, low):
            self.touch_count += 1  # giriş bandına kaç kez gelindi (R-ZONE-01)

        if self.state is S.ACTIVE and touches(self.level_050, high, low):
            return self.transition(S.PRIMED, ts)  # ön koşul karşılandı, zone silahlandı
        if self.state is S.PRIMED and touches(self.level_070, high, low):
            return self.transition(S.TOUCHED, ts)
        if self.state is S.ENTERED and touches(self.level_050, high, low):
            return self.transition(S.TP1_HIT, ts)  # ilk TP; stop maliyete = R-EXIT işi
        return self.state
