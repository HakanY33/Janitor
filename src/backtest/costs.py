"""Maliyet modeli — komisyon, funding, slippage.

Spec: §8 "Maliyet modeli — zorunlu. Taker/maker komisyonu + funding + slippage.
Oranlar borsanın yayınladığı listelerden alınır, tahmin edilmez."

**Komisyon** `data/{exchange}/fees.json`'dan okunur (`python -m scripts.funding` yazar).
Dosya yoksa hata verilir — komisyonsuz backtest sonucu raporlanmaz (CLAUDE.md).

**Funding** `data/{exchange}/{symbol}/funding/*.parquet`'ten okunur. Pozisyon 8 saatlik
funding anlarını geçtikçe ödenir/alınır: `maliyet = notional × oran`, long pozitif oranda
öder. İşaret gerçek yönüyle uygulanır — funding lehte de olabilir.

**Funding kapsama boşluğu — ölçüldü, gizlenmedi.** BingX funding geçmişini yalnızca son
~1000 kayıtla (≈333 gün) veriyor ve `since`'i yok sayıyor; OHLCV geçmişi bundan uzun.
Kapsam dışı funding anlarında oran **atanır**: sembolün ölçülen `|oran|` medyanı, daima
**aleyhte** işaretle. Bu kötümser taraftır ve uydurma değil ölçülen dağılımdan gelir.
Rapor ölçülen/atanan ayrımını ve kapsama oranını ayrı satırlarda verir.

**Slippage tek istisnadır.** Borsa slippage yayınlamaz — "yayınlanan listeden alınır"
kuralı buna uygulanamaz. Bu yüzden açık bir parametredir (`slippage_bps`), varsayılanı
kötümser tarafta sabittir ve toplam slippage maliyeti raporda **ayrı** verilir; okuyucu
başka bir varsayımla yeniden ölçekleyebilir.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from src.data import collect

FEES_PATH = "fees.json"
FUNDING_TF = "funding"
FUNDING_INTERVAL = pd.Timedelta("8h")

SLIPPAGE_BPS = Decimal("2")
"""Varsayılan slippage, baz puan (0.02%). **Borsa yayını değildir** — varsayımdır.

Kötümser taraf: her dolum fiyatı aleyhe bu kadar kaydırılır (giriş daha kötü, çıkış
daha kötü). Raporda toplam slippage ayrı satırda verilir; başka bir varsayım için
`--slippage-bps` ile değiştirilir ve sonuç yeniden ölçülür, tahmin edilmez.
"""


@dataclass
class Fees:
    """Sembol başına borsanın yayınladığı oranlar ve fiyat adımı.

    `tick` = `market["precision"]["price"]` (BingX'te `precisionMode` TICK_SIZE, yani
    değer doğrudan fiyat adımıdır). Limit emri kolunun "seviyeyi 1 tick geç" kuralı
    bunu okur; kodda elle yazılmış hassasiyet tablosu yoktur (CLAUDE.md #5).
    `0` = adım bilinmiyor; limit kolu bu değerle **koşmaz**, hata verir.
    """

    taker: Decimal
    maker: Decimal
    tick: Decimal = Decimal("0")


def load_fees(exchange: str = "bingx") -> dict[str, Fees]:
    """`data/{exchange}/fees.json` — yoksa hata (CLAUDE.md #8: sessiz varsayılan yok)."""
    path = collect.DATA_ROOT / exchange / FEES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} yok — komisyon oranı tahmin edilmez. Önce: python -m scripts.funding"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))["fees"]
    return {
        s: Fees(
            Decimal(str(v["taker"])),
            Decimal(str(v["maker"])),
            # Eski dosyalarda yok: 0 kalir ve yalnizca limit kolu bunu hata sayar.
            # Sessizce bir adim uydurmak yerine o kol calismaz (CLAUDE.md #5, #8).
            Decimal(str(v["tick"])) if "tick" in v else Decimal("0"),
        )
        for s, v in raw.items()
    }


@dataclass
class FundingCurve:
    """Bir sembolün funding oranı serisi + kapsam dışı için aleyhte atanan oran."""

    times: np.ndarray  # funding anları (datetime64[ns, UTC])
    rates: np.ndarray  # ölçülen oranlar
    imputed_rate: float  # |oran| medyanı — kapsam dışında daima aleyhte uygulanır

    def rate_at(self, ts: pd.Timestamp, side: str) -> tuple[float, bool]:
        """(oran, ölçüldü_mü). Kapsam dışında aleyhte atanan oran döner.

        Aleyhte = long için pozitif (öder), short için negatif (öder). İşaret
        `cost_for` tarafından yöne çevrilir; burada yalnızca büyüklük ve yön kurulur.
        """
        i = int(np.searchsorted(self.times, np.datetime64(ts.tz_convert("UTC").tz_localize(None))))
        if i < len(self.times) and self.times[i] == np.datetime64(
            ts.tz_convert("UTC").tz_localize(None)
        ):
            return float(self.rates[i]), True
        return (self.imputed_rate if side == "LONG" else -self.imputed_rate), False


def load_funding(symbol: str, exchange: str = "bingx") -> FundingCurve:
    """Sembolün funding geçmişi. Kayıt yoksa boş eğri (her an atanır) döner."""
    df = collect.read_parquet(exchange, symbol, FUNDING_TF)
    if df.empty or "funding_rate" not in df.columns:
        return FundingCurve(np.array([], dtype="datetime64[ns]"), np.array([]), 0.0)
    df = df.sort_values("ts")
    rates = df.funding_rate.to_numpy(dtype=float)
    return FundingCurve(
        times=df.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy(),
        rates=rates,
        imputed_rate=float(np.median(np.abs(rates))) if len(rates) else 0.0,
    )


def funding_times(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """`start` (hariç) ile `end` (dahil) arasındaki 8 saatlik funding anları."""
    if end <= start:
        return []
    first = start.ceil(FUNDING_INTERVAL)
    if first <= start:
        first = first + FUNDING_INTERVAL
    return list(pd.date_range(first, end, freq=FUNDING_INTERVAL))


@dataclass
class CostModel:
    """Tüm maliyet bileşenleri tek yerde. Sayaçlar rapor için birikir."""

    fees: dict[str, Fees]
    funding: dict[str, FundingCurve] = field(default_factory=dict)
    slippage_bps: Decimal = SLIPPAGE_BPS
    # §9 sayaçları
    total_fees: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    funding_measured: Decimal = Decimal("0")
    funding_imputed: Decimal = Decimal("0")
    funding_events: int = 0
    funding_events_imputed: int = 0
    # Kalem defteri: hangi para hangi islemde gitti. Toplamlar (`total_*`) neyin
    # gittigini soyler, bu defter **nerede** gittigini. Ekle-kucult salinimi
    # komisyonu giris/cikis disinda buyutuyorsa yalnizca burada gorunur.
    breakdown: dict = field(default_factory=dict)

    def _kaydet(self, kalem: str, tutar: Decimal) -> None:
        self.breakdown[kalem] = self.breakdown.get(kalem, Decimal("0")) + tutar

    def fill_price(self, price: Decimal, side: str, opening: bool) -> Decimal:
        """Slippage uygulanmış dolum fiyatı — her zaman aleyhte.

        Açılışta long daha pahalıya alır, short daha ucuza satar; kapanışta tersi.
        """
        adverse_up = (side == "LONG") == opening
        shift = price * self.slippage_bps / Decimal("10000")
        return price + shift if adverse_up else price - shift

    def apply_slippage_cost(self, qty: Decimal, price: Decimal,
                            kalem: str = "cikis") -> None:
        """Slippage'in parasal karşılığını ayrı sayaçta biriktirir (§8 ayrı raporlanır).

        Slippage dolum fiyatının **içindedir** (`fill_price`), yani brüt PnL'e zaten
        yansımıştır. Bu sayaç onu ikinci kez düşmez; ayrı kalem olarak görünür kılar.
        """
        c = qty * price * self.slippage_bps / Decimal("10000")
        self.total_slippage += c
        self._kaydet(f"slippage_{kalem}", c)

    def fee(self, symbol: str, notional: Decimal, kalem: str = "cikis",
            maker: bool = False) -> Decimal:
        """Komisyon. Varsayılan **taker**: R-ENTRY-02 "temas anında girilir" piyasa emridir.

        `maker=True` yalnızca limit emri kolunda geçerlidir (`Backtest.limit_orders`).
        Oran yine `fees.json`'dan gelir; iki oran arasındaki fark tahmin edilmez.
        """
        f = self.fees[symbol]
        fee = notional * (f.maker if maker else f.taker)
        self.total_fees += fee
        self._kaydet(f"komisyon_{kalem}", fee)
        return fee

    def funding_cost(
        self, symbol: str, side: str, notional: Decimal, start: pd.Timestamp, end: pd.Timestamp
    ) -> Decimal:
        """Pozisyonun `start`→`end` aralığında ödediği toplam funding.

        Pozitif dönen değer **maliyettir** (equity'den düşer); negatif değer gelirdir.
        """
        curve = self.funding.get(symbol)
        if curve is None:
            return Decimal("0")
        total = Decimal("0")
        for t in funding_times(start, end):
            rate, measured = curve.rate_at(t, side)
            # Long pozitif oranda öder, short pozitif oranda alır.
            cost = notional * Decimal(str(rate)) * (Decimal("1") if side == "LONG" else Decimal("-1"))
            total += cost
            self.funding_events += 1
            if measured:
                self.funding_measured += cost
            else:
                self.funding_imputed += cost
                self.funding_events_imputed += 1
        self.total_funding += total
        self._kaydet("funding", total)
        return total

    @property
    def funding_coverage(self) -> float:
        """Ölçülen funding olaylarının oranı — rapor satırı."""
        if not self.funding_events:
            return 1.0
        return 1 - self.funding_events_imputed / self.funding_events


def build_cost_model(symbols: list[str], exchange: str = "bingx", slippage_bps: Decimal = SLIPPAGE_BPS) -> CostModel:
    fees = load_fees(exchange)
    eksik = [s for s in symbols if s not in fees]
    if eksik:
        raise KeyError(f"komisyon oranı yok: {eksik} — python -m scripts.funding")
    return CostModel(
        fees=fees,
        funding={s: load_funding(s, exchange) for s in symbols},
        slippage_bps=slippage_bps,
    )
