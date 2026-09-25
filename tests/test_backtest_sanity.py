"""Motor doğruluk testleri — beklenen değerler **elle** hesaplanmıştır.

`tests/test_backtest.py` kuralların *tetiklendiğini* sınar (stop çalıştı mı, sayaç arttı
mı). Bu dosya farklı bir soru sorar: **rakam doğru mu.** Her senaryonun beklenen PnL,
ortalama maliyet ve bakiye değeri testte sabit olarak yazılıdır ve türetimi yorumda
adım adım gösterilir.

> Beklenen değeri motorun çıktısından üretmek testi anlamsız kılar: o zaman test
> yalnızca "motor kendisiyle tutarlı" der. Bu yüzden aşağıda hiçbir beklenen değer
> `res`/`pos`/`trade` üzerinden hesaplanmaz; hepsi elle çarpılıp bölünmüş sabittir.

**Ortak kurulum.** Tek sembol, SHORT zone: `0 = 100` (altta), `1 = 200` (üstte) →
`0.50 = 150`, `0.70 = 170`, `0.79 = 179`. Başlangıç bakiye **17.000**, `K = 1.0` →
notional 17.000, giriş 170'ten, **qty tam 100**. Taker komisyonu 0.0005 (borsa yayını).
Slippage çoğu senaryoda **0**: komisyon aritmetiği tek başına denetlenebilsin diye.
Slippage'in kendisi ayrı bir testte sabit fiyatlarla sınanır.
"""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.backtest.costs import CostModel, Fees, FundingCurve
from src.backtest.engine import Backtest, SymbolData
from src.backtest.portfolio import Portfolio, Position
from src.features.ob import OrderBlock
from src.zones.model import Zone

SYM = "AAA/USDT:USDT"
SYM_B = "BBB/USDT:USDT"
T0 = pd.Timestamp("2026-01-01", tz="UTC")
TAKER = Decimal("0.0005")
BALANCE = Decimal("17000")


def ts(minutes: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=minutes)


def costs(slippage: str = "0", symbols=(SYM, SYM_B)) -> CostModel:
    return CostModel(
        fees={s: Fees(TAKER, Decimal("0.0002")) for s in symbols},
        funding={},
        slippage_bps=Decimal(slippage),
    )


def zone(symbol: str = SYM, a0: float = 100.0, a1: float = 200.0) -> Zone:
    return Zone.create(symbol, "30m", a0, ts(0), a1, ts(30))


def ob(symbol: str, top: float, bottom: float) -> OrderBlock:
    """İmpulsu çok erken, hiç delinmemiş BEARISH OB — ekleme adayı olarak hazır."""
    return OrderBlock(
        ob_id=f"ob-{top}", symbol=symbol, timeframe="30m", direction="BEARISH",
        top=top, bottom=bottom, created_at=ts(0), impulse_at=ts(0),
    )


def symbol_data(bars, z: Zone, obs: list[OrderBlock] | None = None) -> SymbolData:
    """(high, low) listesinden 1m veri; close = orta nokta. Mumlar `watch_from`'dan başlar."""
    obs = obs or []
    n = len(bars)
    times = pd.to_datetime([z.watch_from + pd.Timedelta(minutes=i) for i in range(n)], utc=True)
    uzak = np.datetime64("2262-01-01")
    return SymbolData(
        symbol=z.symbol,
        ts=times.tz_convert("UTC").tz_localize(None).to_numpy(),
        high=np.array([b[0] for b in bars], dtype=float),
        low=np.array([b[1] for b in bars], dtype=float),
        close=np.array([(b[0] + b[1]) / 2 for b in bars], dtype=float),
        zones=[z], obs=obs, fvgs=[], pierce_at={o.ob_id: None for o in obs},
        ob_top=np.array([o.top for o in obs], dtype=float),
        ob_bottom=np.array([o.bottom for o in obs], dtype=float),
        ob_bull=np.zeros(len(obs), dtype=bool),  # hepsi BEARISH
        ob_impulse=np.array([np.datetime64(o.impulse_at.tz_localize(None)) for o in obs]),
        ob_pierce=np.full(len(obs), uzak),
        ob_alive=np.ones(len(obs), dtype=bool),
    )


# --- (1) tek giris, tek cikis, komisyon dahil --------------------------------

ENTRY = [(152, 148), (172, 168)]  # 0.50 teması → 0.70 teması (giriş)


def test_sanity_single_entry_single_exit_with_fees():
    """Tek giriş + stop. Her kalem elle:

    giriş   : notional 17.000 / fiyat 170        -> qty  100
    giriş k. : 17.000 × 0.0005                   ->    8.50
    çıkış   : stop = çapa 1 = 200
    brüt    : 100 × (170 − 200)                  -> −3.000
    çıkış k. : (100 × 200) × 0.0005              ->   10.00
    pnl     : −3.000 − 8.50 − 10.00              -> −3.018.50
    bakiye  : 17.000 − 8.50 − 3.000 − 10.00      -> 13.981.50
    """
    res = Backtest([symbol_data(ENTRY + [(202, 198)], zone())], costs(),
                   start_balance=BALANCE).run()
    t = res.trades[0]
    assert t.qty == Decimal("100")
    assert t.entry_price == Decimal("170")
    assert t.exit_price == Decimal("200")
    assert t.gross == Decimal("-3000")
    assert t.fees == Decimal("18.50")
    assert t.pnl == Decimal("-3018.50")
    assert res.portfolio.balance == Decimal("13981.50")


def test_sanity_final_tp_pnl_without_tp1_is_not_reachable():
    """0'a giden yol 0.50'den geçer; bu yüzden nihai TP daima kısmi TP'den sonradır.

    Senaryo (2)'nin ön kabulü bu: tek çıkışlı kâr senaryosu kurulamaz.
    """
    res = Backtest([symbol_data(ENTRY + [(102, 98)], zone())], costs(),
                   start_balance=BALANCE).run()
    # 0.50 (150) mumun içinde kalmadığı için tek mumda 0'a inildi: R-ZONE-04 önce
    # TP1_HIT'e geçemez, çapa teması öldürür → doğrudan CLOSED.
    assert res.trades[0].reason == "FINAL_TP"


# --- (2) kismi TP sonrasi kalan pozisyonun maliyeti --------------------------


def test_sanity_cost_basis_after_partial_tp():
    """R-EXIT-01 · ilk TP yarıyı kapatır, **ortalama maliyet değişmez** (170).

    giriş    : qty 100 @ 170, komisyon 8.50
    TP1      : 50 adet @ 150   brüt 50 × (170−150)      -> +1.000
               komisyon (50 × 150) × 0.0005             ->     3.75
    nihai TP : 50 adet @ 100   brüt 50 × (170−100)      -> +3.500
               komisyon (50 × 100) × 0.0005             ->     2.50
    brüt top.: 1.000 + 3.500                            -> +4.500
    komisyon : 8.50 + 3.75 + 2.50                       ->    14.75
    pnl      : 4.500 − 14.75                            -> +4.485.25
    bakiye   : 17.000 + 4.485.25                        -> 21.485.25

    Kalan 50 adedin brütü 3.500 ise maliyet tabanı 170'tir (50 × 70). Kısmi çıkış
    ortalama maliyeti düşürseydi bu sayı tutmazdı.
    """
    res = Backtest([symbol_data(ENTRY + [(152, 148), (102, 98)], zone())], costs(),
                   start_balance=BALANCE).run()
    t = res.trades[0]
    assert t.reason == "FINAL_TP"
    assert t.gross == Decimal("4500")
    assert t.fees == Decimal("14.75")
    assert t.pnl == Decimal("4485.25")
    assert res.portfolio.balance == Decimal("21485.25")


# --- (3) iki ekleme sonrasi ortalama maliyet ---------------------------------


def test_sanity_average_cost_after_two_adds():
    """R-ADD-03 çarpan seçimi + R-ADD-04 · iki ekleme sonrası ortalama maliyet.

    Çarpan artık sabit değil: maliyeti `0.79` seviyesinin (=179) ötesine çeken **en
    küçük** çarpan seçilir. Elle:

    giriş : notional 17.000 × 0.2 = 3.400 / 170            -> qty 20 @ 170
    ekle1 : 180'de. 1-1 → 175 · 1-3 → 177.5 · 1-5 → 178.33 (hepsi < 179)
            1-10 → (170×20 + 180×200) / 220 = 39.400/220   -> 179.0909…  ✔ seçilen
    ekle2 : 190'da. 1-1 → (39.400 + 190×220) / 440 = 81.200/440
                                                          -> 184.5454…  ✔ seçilen
    çıkış : stop 200, qty 440
            brüt = 440 × (184.5454… − 200) = 81.200 − 88.000 -> −6.800

    `uyari_blocks_adds=False`: ikinci eklemede oran 0.349 → UYARI. Bu kol açıkken
    ekleme orada dururdu (ayrı testte sabit).
    """
    obs = [ob(SYM, 182.0, 178.0), ob(SYM, 192.0, 188.0)]
    bars = ENTRY + [(182, 178), (192, 188), (202, 198)]
    res = Backtest([symbol_data(bars, zone(), obs)], costs(), start_balance=BALANCE,
                   k=Decimal("0.2"), uyari_blocks_adds=False).run()
    t = res.trades[0]
    assert res.counters["adds"] == 2 and t.adds == 2
    assert res.counters["adds_by_mult"] == {"1-10": 1, "1-1": 1}
    assert t.qty == Decimal("440")  # 20 + 200 + 220
    assert t.gross == pytest.approx(Decimal("-6800"))


def test_sanity_large_multiplier_hits_notional_cap_then_smaller_one_fits():
    """`K = 1.0`: 180'de seçilen 1-10 tavanı aşar (`ADD-REJECT-B`); 190'da 1-1 yeter.

    180'de : maliyeti 179'un ötesine çeken en küçük çarpan **1-10**
             eklenecek notional 1.000 × 180 = 180.000
             equity 17.000 − 8,50 − 100×10 = 15.991,50 · tavan 10× = 159.915
             mevcut 100 × 180 = 18.000 → 198.000 > 159.915  ->  REDDEDILIR (B)
    190'da : fiyat maliyetten daha uzak, **1-1** yetiyor
             (170×100 + 190×100) / 200 = 180 ≥ 179  ->  kabul
             notional 19.000 + 19.000 = 38.000 < 10 × 14.991,50  ->  tavan bağlamıyor
    çıkış  : stop 200, qty 200 → brüt = 200 × (180 − 200) = −4.000

    Bulgu: fiyat aleyhte ilerledikçe hedefe **daha küçük** çarpan yetiyor, yani tavan
    ilk denemeyi eleyip sonrakine izin verebiliyor.
    """
    obs = [ob(SYM, 182.0, 178.0), ob(SYM, 192.0, 188.0)]
    bars = ENTRY + [(182, 178), (192, 188), (202, 198)]
    res = Backtest([symbol_data(bars, zone(), obs)], costs(), start_balance=BALANCE,
                   k=Decimal("1.0"), uyari_blocks_adds=False).run()
    assert res.counters["add_reject_b"] >= 1
    assert res.counters["adds"] == 1
    assert res.counters["adds_by_mult"] == {"1-1": 1}
    t = res.trades[0]
    assert t.qty == Decimal("200")
    assert t.gross == pytest.approx(Decimal("-4000"))


def test_sanity_no_add_when_no_multiplier_reaches_target():
    """Hiçbir çarpan maliyeti `0.79`'un ötesine çekemiyorsa ekleme yapılmaz.

    Fiyat bandın hemen üstünde (179.5) iken en büyük çarpan bile maliyeti ancak
    (170×20 + 179,5×200)/220 = 178,64'e taşır — 179'un altında kalır.
    """
    obs = [ob(SYM, 180.0, 179.0)]
    bars = ENTRY + [(180, 179), (180, 179), (202, 198)]
    res = Backtest([symbol_data(bars, zone(), obs)], costs(), start_balance=BALANCE,
                   k=Decimal("0.2"), uyari_blocks_adds=False).run()
    assert res.counters["adds"] == 0
    assert res.counters["add_reject_mult"] >= 1


def test_sanity_add_average_cost_arithmetic_directly():
    """`Position.add` tek başına: ağırlıklı ortalama, elle hesaplanmış değerlerle."""
    p = Position(symbol=SYM, zone_id="z", side="SHORT", qty=Decimal("20"),
                 avg_price=Decimal("170"), opened_at=ts(0), last_funding_at=ts(0))
    p.add(Decimal("20"), Decimal("180"))
    assert p.avg_price == Decimal("175")  # (3400 + 3600) / 40
    p.add(Decimal("40"), Decimal("190"))
    assert p.avg_price == Decimal("182.5")  # (7000 + 7600) / 80
    assert p.qty == Decimal("80")


def test_sanity_add_is_size_weighted_not_simple_mean():
    """Eşit olmayan ekleme: ağırlık gerçekten uygulanıyor mu.

    1-1 eklemede pozisyon ikiye katlandığı için ağırlıklı ortalama ile iki fiyatın
    düz ortalaması **sayısal olarak aynıdır** — o senaryo ikisini ayırt edemez.
    R-ADD-03 çarpanları 1-3, 1-5, 1-10'u da içerdiği için burada eşit olmayan bir
    ekleme ile sabitlenir:

        (170 × 20 + 190 × 60) / 80 = 14.800 / 80 -> 185      (ağırlıklı, doğru)
        (170 + 190) / 2                          -> 180      (düz ortalama, yanlış)
    """
    p = Position(symbol=SYM, zone_id="z", side="SHORT", qty=Decimal("20"),
                 avg_price=Decimal("170"), opened_at=ts(0), last_funding_at=ts(0))
    p.add(Decimal("60"), Decimal("190"))  # 1-3 ekleme
    assert p.avg_price == Decimal("185")
    assert p.qty == Decimal("80")


def test_sanity_reduce_keeps_average_cost_unchanged():
    """Kısmi çıkış ortalama maliyeti değiştirmez; yalnızca qty düşer (R-EXIT-01)."""
    p = Position(symbol=SYM, zone_id="z", side="SHORT", qty=Decimal("100"),
                 avg_price=Decimal("170"), opened_at=ts(0), last_funding_at=ts(0))
    assert p.reduce(Decimal("50"), Decimal("150")) == Decimal("1000")  # 50 × (170−150)
    assert p.avg_price == Decimal("170") and p.qty == Decimal("50")


# --- (4) bilinen funding oraniyla 24 saat tasinan pozisyon -------------------


def test_sanity_funding_over_24h_with_known_rate():
    """24 saat taşınan SHORT, bilinen 0.0001 oranıyla üç funding anı geçer.

    İzleme 01:00'de başlar, giriş 01:01'de olur. (01:01, ertesi gün 01:59] aralığındaki
    8 saatlik anlar: 08:00, 16:00, 00:00 → **3 olay**.

    notional : 100 × 170                                -> 17.000
    olay bşn.: 17.000 × 0.0001                          ->      1.70
    SHORT    : pozitif oranda funding **alır** → maliyet negatif
    toplam   : 3 × (−1.70)                              ->     −5.10
    """
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array(["2026-01-01T08:00", "2026-01-01T16:00", "2026-01-02T00:00"],
                       dtype="datetime64[ns]"),
        rates=np.array([0.0001, 0.0001, 0.0001]),
        imputed_rate=0.0001,
    )}
    # 01:00'den itibaren 1500 mum → son mum ertesi gün 01:59.
    bars = ENTRY + [(176, 174)] * 1498
    res = Backtest([symbol_data(bars, zone())], c, start_balance=BALANCE).run()
    t = res.trades[0]
    assert t.reason == "RUN_END"
    assert c.funding_events == 3
    assert c.funding_events_imputed == 0  # üçü de ölçülen orandan
    assert t.funding == Decimal("-5.10")
    assert c.total_funding == Decimal("-5.10")


def test_sanity_funding_long_pays_same_magnitude():
    """Aynı oran, LONG tarafta **ödenir**: işaret ters, büyüklük aynı (3 × 1.70)."""
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array(["2026-01-01T08:00", "2026-01-01T16:00", "2026-01-02T00:00"],
                       dtype="datetime64[ns]"),
        rates=np.array([0.0001, 0.0001, 0.0001]), imputed_rate=0.0001,
    )}
    start = pd.Timestamp("2026-01-01 01:01", tz="UTC")
    end = pd.Timestamp("2026-01-02 01:59", tz="UTC")
    assert c.funding_cost(SYM, "LONG", Decimal("17000"), start, end) == Decimal("5.10")


# --- (5) iki es zamanli pozisyonda cross equity ------------------------------


def test_sanity_cross_equity_sums_both_positions():
    """İkinci pozisyonun boyutu, birincinin **gerçekleşmemiş** kârını içeren equity'den.

    A zone: 0=100, 1=200 → giriş 170.  B zone: 0=30, 1=130 → giriş **100** (bölme temiz).
    Mumlar aynı zaman ızgarasında; sembol sırası [A, B].

    mum1 : A 170'e dokunur → A girer
           equity 17.000 → notional 17.000 / 170        -> qty_A 100
           komisyon 17.000 × 0.0005                     ->     8.50
           bakiye                                       -> 16.991.50
    mum2 : A'nın markı 160 → gerçekleşmemiş +1.000 (short 170→160)
           equity = 16.991.50 + 1.000                   -> 17.991.50
           B 100'e dokunur → notional 17.991.50 / 100   -> qty_B 179.9150
           komisyon 17.991.50 × 0.0005                  ->     8.99575
           bakiye                                       -> 16.982.50425
    mum3 : ikisi de stop
           A brüt 100 × (170−200)                       -> −3.000   kom. 10.00
           B brüt 179.9150 × (100−130)                  -> −5.397.45 kom. 11.694475
           bakiye 16.982.50425 −3.000 −10 −5.397.45 −11.694475 -> 8.563.359775

    Ayırt edici nokta: motor A'nın gerçekleşmemiş kârını equity'ye **katmasaydı**
    qty_B = 16.991.50 / 100 = 169.9150 olurdu.
    """
    a = symbol_data([(152, 148), (172, 168), (162, 158), (202, 198)], zone(SYM))
    b = symbol_data([(82, 78), (92, 88), (102, 98), (132, 128)], zone(SYM_B, 30.0, 130.0))
    res = Backtest([a, b], costs(), start_balance=BALANCE).run()

    assert res.counters["entries"] == 2
    t = {x.symbol: x for x in res.trades}
    assert t[SYM].qty == Decimal("100")
    assert t[SYM_B].qty == Decimal("179.9150")  # 169.9150 olsaydı equity toplanmamıştı
    assert t[SYM].gross == Decimal("-3000")
    assert t[SYM_B].gross == Decimal("-5397.45")
    assert res.portfolio.balance == Decimal("8563.359775")


def test_sanity_equity_is_sum_over_positions():
    """`Portfolio.equity` iki pozisyonun gerçekleşmemiş PnL'ini toplar (elle)."""
    pf = Portfolio(balance=Decimal("1000"), start_balance=Decimal("1000"))
    pf.positions[SYM] = Position(symbol=SYM, zone_id="a", side="SHORT", qty=Decimal("10"),
                                 avg_price=Decimal("100"), opened_at=ts(0), last_funding_at=ts(0))
    pf.positions[SYM_B] = Position(symbol=SYM_B, zone_id="b", side="LONG", qty=Decimal("5"),
                                   avg_price=Decimal("50"), opened_at=ts(0), last_funding_at=ts(0))
    # short 10 × (100 − 90) = +100 · long 5 × (60 − 50) = +50 · 1000 + 150
    assert pf.equity({SYM: Decimal("90"), SYM_B: Decimal("60")}) == Decimal("1150")


# --- slippage, sabit fiyatlarla ----------------------------------------------


def test_sanity_slippage_shifts_fill_prices_by_fixed_amount():
    """2 bps slippage: SHORT girişte 170 → 169.966, çıkışta 200 → 200.04.

    170 × (1 − 0.0002) = 169.966 · 200 × (1 + 0.0002) = 200.04
    """
    res = Backtest([symbol_data(ENTRY + [(202, 198)], zone())], costs(slippage="2"),
                   start_balance=BALANCE).run()
    t = res.trades[0]
    assert t.entry_price == Decimal("169.966")
    assert t.exit_price == Decimal("200.04")


def test_sanity_zero_slippage_fills_exactly_at_level():
    res = Backtest([symbol_data(ENTRY + [(202, 198)], zone())], costs(),
                   start_balance=BALANCE).run()
    assert res.trades[0].entry_price == Decimal("170")
    assert res.trades[0].exit_price == Decimal("200")


def test_sanity_pnl_identity_holds_on_every_trade():
    """pnl ≡ brüt − komisyon − funding. Motorun kendi kalemleri birbirini tutmalı."""
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array(["2026-01-01T08:00"], dtype="datetime64[ns]"),
        rates=np.array([0.0003]), imputed_rate=0.0003,
    )}
    bars = ENTRY + [(176, 174)] * 600
    res = Backtest([symbol_data(bars, zone())], c, start_balance=BALANCE).run()
    for t in res.trades:
        assert t.pnl == t.gross - t.fees - t.funding
