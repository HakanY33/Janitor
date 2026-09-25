"""Cross marjin portföy: pozisyonlar, equity, likidasyon mesafesi.

Spec: R-ENTRY-01 (cross), R-ENTRY-03 (notional bazlı boyut), R-ENTRY-04 (maks kaldıraç),
R-RISK-01 (notional tavanı), R-RISK-05 (likidasyon tamponu), §0.1 (equity tanımı),
§9 (zorunlu sayaçlar).

Para hesabı `Decimal` (CLAUDE.md #4): qty, notional, ortalama maliyet, PnL, bakiye.
Ham fiyat float gelir ve pozisyona girerken `Decimal`'e çevrilir — sınır burasıdır.

**Kaldıraç PnL'i etkilemez.** R-ENTRY-03 boyutu *notional* üzerinden tanımlar ve
"marjin = notional / kaldıraç" **türetilmiş** değerdir. Cross marjinde likidasyon koşulu
da notional cinsindendir (`equity ≤ Σ notional × MMR`), kaldıraç cinsinden değil.
Kaldıraç yalnızca "bu notional'e izin var mı" sorusunda bağlar; R-RISK-01 tavanı
10 × equity olduğu ve spec'teki en düşük örnek kaldıraç 20x olduğu için bu kısıt
bağlamaz. Borsanın `maxLeverage` değeri kimlik doğrulama istediği için çekilemedi
(bkz. rapor); yukarıdaki gerekçeyle sonucu değiştirmiyor.

**Likidasyon — MMR'siz ölçü birincil.** Bakım marjı oranı (MMR) da yalnızca kimlikli
uçtan geliyor. Bu yüzden asıl sayaç MMR'den **bağımsız** olan `equity / toplam notional`
oranıdır; likidasyon eşiği bununla doğrudan karşılaştırılır (`oran ≤ MMR` → likidasyon).
Rapor birkaç MMR değeri için duyarlılık verir, tek bir uydurma sabit kullanmaz.

**Korelasyon en kötü hâlde alınır.** `liq_distance`, tüm pozisyonların **aynı anda
aleyhte** aynı oranda hareket ettiği varsayımıyla hesaplanır — spec'in kendi uyarısı:
"10 ayrı pozisyon, genel bir düşüşte 10 ayrı olay değil tek bir olaydır".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

LONG = "LONG"
SHORT = "SHORT"

DEFAULT_MMR = Decimal("0.005")
"""Bakım marjı oranı varsayılanı. **Borsa yayını değildir** — `fetchLeverageTiers`
kimlik doğrulama istiyor. Rapor bunu tek başına kullanmaz, duyarlılık tablosu verir."""


@dataclass
class Position:
    """Tek sembolde açık pozisyon. Ekleme ortalama maliyeti günceller (R-ADD-04)."""

    symbol: str
    zone_id: str
    side: str  # LONG | SHORT
    qty: Decimal
    avg_price: Decimal
    opened_at: datetime
    last_funding_at: datetime
    adds: int = 0
    tp1_done: bool = False  # R-EXIT-01 · ilk TP alındı, stop maliyete çekildi
    entry_bias: str = "NONE"  # R-ZONE-10 · girişte bilinen 4h yapısal yön (OPEN-29)
    reduce_armed: bool = False  # R-ADD-04 · ekleme oldu, maliyete dönüş küçültme tetikler
    reduces: int = 0  # kaç kez K tabanına indirildi
    reduced_at: datetime | None = None  # ilk küçültmenin zamanı
    fees_paid: Decimal = Decimal("0")
    funding_paid: Decimal = Decimal("0")
    realized: Decimal = Decimal("0")
    max_qty: Decimal = Decimal("0")
    # Olcum alanlari (float): para hareketi degil, islem sonrasi teshis icin.
    mae_leg: float = 0.0       # maks aleyhte sapma / leg boyu
    mae_equity: float = 0.0    # maks aleyhte sapma / o andaki equity
    min_liq_dist: float | None = None  # yasadigi en dusuk likidasyon mesafesi

    @property
    def notional(self) -> Decimal:
        return self.qty * self.avg_price

    def mark_notional(self, price: Decimal) -> Decimal:
        return self.qty * price

    def unrealized(self, price: Decimal) -> Decimal:
        d = price - self.avg_price
        return self.qty * (d if self.side == LONG else -d)

    def add(self, qty: Decimal, price: Decimal) -> None:
        """R-ADD-04 · ortalama maliyet güncellenir; nihai stop `1`'de kalır.

        Küçültme tetiği burada kurulur: her eklemeden sonra fiyatın **yeni** ortalama
        maliyete dönmesi pozisyonu `K` tabanına indirir. Küçültme tetiği düşürür,
        sonraki ekleme yeniden kurar.
        """
        total = self.qty + qty
        self.avg_price = (self.avg_price * self.qty + price * qty) / total
        self.qty = total
        self.adds += 1
        self.max_qty = max(self.max_qty, total)
        self.reduce_armed = True

    def reduce(self, qty: Decimal, price: Decimal) -> Decimal:
        """Pozisyonu küçültür ve gerçekleşen PnL'i döner. Ortalama maliyet değişmez."""
        qty = min(qty, self.qty)
        d = price - self.avg_price
        pnl = qty * (d if self.side == LONG else -d)
        self.qty -= qty
        self.realized += pnl
        return pnl


@dataclass
class Portfolio:
    """Cross marjin hesap. Tek bakiye, tüm pozisyonlar aynı teminatı paylaşır."""

    balance: Decimal
    start_balance: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
    mmr: Decimal = DEFAULT_MMR
    # §9 sayaçları — izleme yolunda float birikir (bkz. `observe`)
    peak_equity_f: float = 0.0
    max_drawdown_f: float = 0.0
    min_equity_ratio_f: float | None = None  # min(equity / toplam notional) — MMR'siz
    # İflas metriği: equity'nin başlangıcın altına düştüğü bar sayısı. Likidasyon
    # sayacı 0 iken hesabın bitmesi mümkün (notional equity ile küçülür, sıfıra
    # asimptot olur) — o durumda "likide olmadık" yanıltıcıdır, ölçü budur.
    ruin_bars: dict = field(default_factory=lambda: {0.50: 0, 0.25: 0, 0.10: 0})
    observed_bars: int = 0
    liquidation_events: int = 0
    concurrent_hist: dict[int, int] = field(default_factory=dict)

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        """§0.1 · bakiye + tüm açık pozisyonların gerçekleşmemiş PnL'i."""
        return self.balance + sum(
            (p.unrealized(marks[p.symbol]) for p in self.positions.values() if p.symbol in marks),
            Decimal("0"),
        )

    def total_notional(self, marks: dict[str, Decimal]) -> Decimal:
        return sum(
            (p.mark_notional(marks[p.symbol]) for p in self.positions.values() if p.symbol in marks),
            Decimal("0"),
        )

    def maintenance_margin(self, marks: dict[str, Decimal]) -> Decimal:
        return self.total_notional(marks) * self.mmr

    def liq_distance(self, marks: dict[str, Decimal]) -> Decimal | None:
        """R-RISK-05 · `|likidasyon − mark| / mark`, hepsi birlikte hareket ederse.

        `equity − N·δ = N·MMR` → `δ = equity/N − MMR`. Pozisyon yoksa `None`
        (mesafe tanımsız, likidasyon riski yok).
        """
        n = self.total_notional(marks)
        if n <= 0:
            return None
        return self.equity(marks) / n - self.mmr

    def is_liquidated(self, marks: dict[str, Decimal]) -> bool:
        """Cross marjin likidasyonu: equity bakım marjının altına düştü."""
        n = self.total_notional(marks)
        return n > 0 and self.equity(marks) <= n * self.mmr

    # --- izleme yolu (float) ---------------------------------------------------
    # Sayaçlar her 1m mumda güncellenir; `Decimal` bu sıcaklıkta gereksiz pahalıdır ve
    # burada para *hareket etmez*, yalnızca ölçülür (CLAUDE.md #4: ölçüm float olabilir).
    # Paranın hareket ettiği her yer (dolum, gerçekleşen PnL, bakiye) `Decimal` kalır.

    def equity_f(self, marks: dict[str, float]) -> float:
        eq = float(self.balance)
        for p in self.positions.values():
            price = marks.get(p.symbol)
            if price is None:
                continue
            d = price - float(p.avg_price)
            eq += float(p.qty) * (d if p.side == LONG else -d)
        return eq

    def total_notional_f(self, marks: dict[str, float]) -> float:
        return sum(
            float(p.qty) * marks[p.symbol]
            for p in self.positions.values()
            if p.symbol in marks
        )

    def liq_distance_f(self, marks: dict[str, float]) -> float | None:
        n = self.total_notional_f(marks)
        return None if n <= 0 else self.equity_f(marks) / n - float(self.mmr)

    def is_liquidated_f(self, marks: dict[str, float]) -> bool:
        n = self.total_notional_f(marks)
        return n > 0 and self.equity_f(marks) <= n * float(self.mmr)

    def observe(self, marks: dict[str, float]) -> None:
        """Her mumda çağrılır: §9 sayaçlarını ilerletir.

        Tamamen float: burada para hareket etmez, ölçülür. 1m çözünürlükte milyonlarca
        kez çağrıldığı için `Decimal` dönüşümü ölçümün kendisinden pahalıya geliyordu.
        Sonuçlar raporda `Decimal`'e çevrilir.
        """
        if not self.positions:  # pozisyon yokken equity = bakiye, mark gerekmez
            eq, n = float(self.balance), 0.0
        else:
            eq, n = self.equity_f(marks), self.total_notional_f(marks)

        self.observed_bars += 1
        sb = float(self.start_balance)
        for esik in self.ruin_bars:
            if eq < sb * esik:
                self.ruin_bars[esik] += 1

        if eq > self.peak_equity_f:
            self.peak_equity_f = eq
        if self.peak_equity_f > 0:
            dd = (self.peak_equity_f - eq) / self.peak_equity_f
            if dd > self.max_drawdown_f:
                self.max_drawdown_f = dd

        if n > 0:
            ratio = eq / n
            if self.min_equity_ratio_f is None or ratio < self.min_equity_ratio_f:
                self.min_equity_ratio_f = ratio
        k = len(self.positions)
        self.concurrent_hist[k] = self.concurrent_hist.get(k, 0) + 1

    # Rapor yüzeyi: ölçümler float birikir, dışarıya Decimal verilir.
    @property
    def max_drawdown(self) -> Decimal:
        return Decimal(str(self.max_drawdown_f))

    @property
    def peak_equity(self) -> Decimal:
        return Decimal(str(self.peak_equity_f))

    @property
    def min_equity_ratio(self) -> Decimal | None:
        return None if self.min_equity_ratio_f is None else Decimal(str(self.min_equity_ratio_f))

    @property
    def min_liq_distance(self) -> Decimal | None:
        r = self.min_equity_ratio
        return None if r is None else r - self.mmr

    def would_liquidate_at(self, ratio: Decimal, mmr: Decimal) -> bool:
        """Duyarlılık: verilen MMR'de bu equity/notional oranı likidasyon mudur."""
        return ratio <= mmr
