"""Zone veri modeli ve durum makinesi.

Spec: R-ZONE-01 (alanlar), R-ZONE-03 (seviyeler), R-ZONE-04 (durum makinesi),
R-ZONE-05 (geçersizlik), STRATEGY_SPEC §0 (bias, zorunlu sıra).

Zone kalıcı bir nesnedir, her mumda yeniden hesaplanmaz: `on_bar` mevcut durumu
ilerletir, durum SQLite'ta saklanır (bkz. `src/zones/store.py`).

Fiyatlar float64. Bunlar ham piyasa verisi üzerinde yapılan fib hesabıdır, borsaya
giden bir miktar değil (CLAUDE.md #4). Decimal'e çevirme `execution` sınırındadır.

**Temas tanımı:** mumun aralığı seviyeyi içeriyorsa temas vardır (`low <= seviye <= high`).
Mum *içi* sıra bilinmez — bunun iki sonucu var, ikisi de kötümser tarafta:

  1. Bir mumda hem ilerleme hem çapa teması oluşursa **öldürme kazanır**.
  2. Bir mumda en fazla **bir** ilerleme yapılır (0.50 ve 0.70'i aynı mumda gören zone
     yalnızca PRIMED olur; giriş için bir sonraki temas beklenir).

R-ZONE-09: `on_bar` **1m mumlarla** beslenir, zone'un `timeframe` alanı ne olursa olsun.
`timeframe` yalnızca geometrinin (leg, çapalar, seviyeler) geldiği zaman dilimidir;
durum geçişleriyle ilgisi yoktur. Her iki kötümser kararın kaç kez tetiklendiği
`kill_wins` / `skipped_progress` sayaçlarında tutulur (R-ZONE-09).

Besleme `watch_from`'dan önce başlayamaz (R-ZONE-09); daha erken bir mum look-ahead'dir
ve `ValueError` yükseltir.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pandas as pd  # yalnızca timeframe -> Timedelta ayrıştırması ("30m", "4h")

HYSTERESIS = 0.25
"""R-ZONE-01 · banttan "belirgin çıkış" eşiği, bant genişliğinin oranı olarak.

Zone başına `Zone.hysteresis` ile değiştirilebilir. 0 = histerezis kapalı.
"""


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

# R-ZONE-04. INVALIDATED yalnızca pozisyon açılmadan önce geçerlidir: ENTERED ve
# TP1_HIT durumunda çapa teması bir geçersizlik değil, işlem sonucudur (0 = nihai TP,
# 1 = nihai stop) → CLOSED. Bu yüzden o iki durumdan INVALIDATED'a kenar yoktur.
TRANSITIONS: dict[ZoneState, frozenset[ZoneState]] = {
    S.CREATED: frozenset({S.ACTIVE}),
    S.ACTIVE: frozenset({S.PRIMED, S.INVALIDATED}),
    S.PRIMED: frozenset({S.TOUCHED, S.INVALIDATED}),
    S.TOUCHED: frozenset({S.ENTERED, S.INVALIDATED}),
    S.ENTERED: frozenset({S.TP1_HIT, S.CLOSED}),
    S.TP1_HIT: frozenset({S.CLOSED}),
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
    # Spec alan listesi yukarıda biter. Aşağıdakiler uygulama durumu:
    pivot_confirmed_at: datetime | None = None  # R-ZONE-09 · dışarıdan verilir (R-ZONE-02 yok)
    hysteresis: float = HYSTERESIS  # R-ZONE-01 · bant genişliğinin oranı
    in_band: bool = False  # önceki mum giriş bandında mıydı — olay bazlı sayım (R-ZONE-01)
    kill_wins: int = 0  # R-ZONE-09 · öldürme ilerlemeye baskın geldi
    skipped_progress: int = 0  # R-ZONE-09 · aynı mumdaki ikinci ilerleme atlandı

    @classmethod
    def create(
        cls,
        symbol: str,
        timeframe: str,
        anchor_0_price: float,
        anchor_0_time: datetime,
        anchor_1_price: float,
        anchor_1_time: datetime,
        pivot_confirmed_at: datetime | None = None,
        hysteresis: float = HYSTERESIS,
        zone_id: str | None = None,
    ) -> Zone:
        """Çapalardan zone kurar: seviyeler R-ZONE-03, bias §0 tablosu.

        `created_at` çapa zamanından gelir, duvar saatinden değil — backtest ve canlı
        aynı zone'u üretsin diye.
        """
        for name, t in (
            ("anchor_0_time", anchor_0_time),
            ("anchor_1_time", anchor_1_time),
            ("pivot_confirmed_at", pivot_confirmed_at),
        ):
            if t is None:
                continue
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
            pivot_confirmed_at=pivot_confirmed_at,
            hysteresis=hysteresis,
        )

    @property
    def watch_from(self) -> datetime:
        """R-ZONE-09 · `max(anchor_1 HTF mumunun kapanışı, pivot teyit zamanı)`.

        Çapa, kendi HTF mumunun *içinde* oluşur; o mumun 1m'lerini beslemek çapaya
        dokunur ve zone'u doğduğu anda öldürür. Pivot teyidi (`R-ZONE-02`, `IMPL-01`)
        henüz yok, dışarıdan verilir; verilmezse ilk terim taban olarak iş görür.
        Leg tespiti otomatikleştiğinde ikinci terim asıl kısıt olur.
        """
        htf_close = self.anchor_1_time + pd.Timedelta(self.timeframe)
        if self.pivot_confirmed_at is None:
            return htf_close
        return max(htf_close, self.pivot_confirmed_at)

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

    def activate(self) -> ZoneState:
        """CREATED → ACTIVE. Zone izlemeye alındı, 0.50 teması bekleniyor (R-ZONE-06).

        İzleme her zaman `watch_from`'dan başlar (R-ZONE-09); zaman dışarıdan
        verilmez, çünkü erken bir başlangıç doğrudan look-ahead bias üretir.
        """
        return self.transition(S.ACTIVE, self.watch_from)

    def enter(self, ts: datetime) -> ZoneState:
        """TOUCHED → ENTERED. Kararı strateji + risk katmanı verir, fiyat değil.

        0.70 teması girişin *gerekli* koşuludur, yeterli değil: R-ENTRY-02 bantta OB/FVG
        arar, R-RISK veto edebilir. Zone bu yüzden kendi kendine ENTERED'a geçmez.
        """
        return self.transition(S.ENTERED, ts)

    def _progress(self, high: float, low: float) -> ZoneState | None:
        """Bu mumun tetiklediği *tek* ilerleme; yoksa None (R-ZONE-04).

        TOUCHED → ENTERED burada yok: girişi strateji verir, fiyat değil (bkz. `enter`).
        """
        if self.state is S.ACTIVE and touches(self.level_050, high, low):
            return S.PRIMED  # ön koşul karşılandı, zone silahlandı
        if self.state is S.PRIMED and touches(self.level_070, high, low):
            return S.TOUCHED
        if self.state is S.ENTERED and touches(self.level_050, high, low):
            return S.TP1_HIT  # ilk TP; stop maliyete = R-EXIT işi
        return None

    def on_bar(self, high: float, low: float, ts: datetime) -> ZoneState:
        """Kapanmış bir mumu uygular ve yeni durumu döner.

        Spec: R-ZONE-04 (ilerleme), R-ZONE-05 (geçersizlik), R-ZONE-09 (1m mum,
        mum içi çakışma sayaçları).

        Mum 1m'dir (R-ZONE-09); `self.timeframe` geometrinin TF'si, buraya karışmaz.
        Sıra önemlidir: önce çapa teması (öldürür), sonra tek bir ilerleme. CREATED ve
        terminal durumlar fiyat işlemez.
        """
        if self.state is S.CREATED or self.state in TERMINAL:
            return self.state

        if ts < self.watch_from:
            raise ValueError(
                f"{self.zone_id}: {ts} < WATCH_FROM {self.watch_from} — look-ahead (R-ZONE-09)"
            )

        if touches(self.anchor_0_price, high, low) or touches(self.anchor_1_price, high, low):
            if self._progress(high, low) is not None:
                self.kill_wins += 1  # aynı mumda ilerleme de vardı, öldürme kazandı
            # R-ZONE-05: giriş öncesi sıra bozuldu → zone ölür. Pozisyon varken aynı temas
            # tanımlı sonuçtur: 0 = nihai TP, 1 = nihai stop → CLOSED.
            return self.transition(
                S.CLOSED if self.state in (S.ENTERED, S.TP1_HIT) else S.INVALIDATED, ts
            )

        # R-ZONE-01: temas = giriş bandına (0.70–0.79) bant *dışından* giriş. Bant içinde
        # geçen ardışık mumlar sayacı artırmaz — sayılan mum değil, olay.
        band_low, band_high = sorted((self.level_070, self.level_079))
        margin = self.hysteresis * (band_high - band_low)
        if low <= band_high and high >= band_low:
            # Yalnızca PRIMED'den itibaren sayılır: fiyat 1'den 0.50'ye inerken banttan
            # zorunlu olarak geçer, o temas her zone'da vardır ve bilgi taşımaz.
            if not self.in_band and self.primed_at is not None:
                self.touch_count += 1
            self.in_band = True
        elif high < band_low - margin or low > band_high + margin:
            # Histerezis: yeni temas için bandı genişliğinin `hysteresis` katı kadar
            # aşarak terk etmek gerekir. Aksi hâlde 1m'de sınırdaki titreşim sayacı şişirir.
            self.in_band = False

        nxt = self._progress(high, low)
        if nxt is None:
            return self.state
        self.transition(nxt, ts)
        if self._progress(high, low) is not None:
            self.skipped_progress += 1  # mum içi sıra bilinmez → ikinci ilerleme atlandı
        return self.state
