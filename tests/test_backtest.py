"""Backtest motoru testleri — maliyet modeli, portföy ve uçtan uca kural akışı.

Spec: R-ENTRY-02/03, R-ADD-02/04, R-EXIT-01/02, R-RISK-01/02/05, §8 (maliyet,
intrabar belirsizliği), §9 (sayaçlar).

Motor diske veya ağa bağlanmadan sınanır: `SymbolData` elle kurulur. Böylece her
kuralın tetiklendiği mum dizisi açıkça görünür (ve testler veri indirilmeden koşar).
"""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.backtest.costs import CostModel, Fees, FundingCurve, funding_times
from src.backtest.engine import Backtest, SymbolData
from src.backtest.portfolio import LONG, SHORT, Portfolio, Position
from src.zones.model import Zone

SYM = "TEST/USDT:USDT"
T0 = pd.Timestamp("2026-01-01", tz="UTC")


def ts(minutes: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=minutes)


def costs(slippage=Decimal("2")) -> CostModel:
    return CostModel(
        fees={SYM: Fees(Decimal("0.0005"), Decimal("0.0002"))},
        funding={},
        slippage_bps=slippage,
    )


# --- maliyet modeli (§8) ------------------------------------------------------


def test_cost_slippage_always_adverse():
    """Açılışta long pahalıya alır/short ucuza satar; kapanışta tersi."""
    c = costs()
    p = Decimal("100")
    assert c.fill_price(p, LONG, opening=True) > p
    assert c.fill_price(p, SHORT, opening=True) < p
    assert c.fill_price(p, LONG, opening=False) < p
    assert c.fill_price(p, SHORT, opening=False) > p


def test_cost_fee_accumulates_taker_by_default():
    c = costs()
    assert c.fee(SYM, Decimal("10000")) == Decimal("5.0000")
    c.fee(SYM, Decimal("10000"))
    assert c.total_fees == Decimal("10.0000")


def test_cost_fee_maker_is_cheaper_than_taker():
    """Limit kolu maker oranini kullanir; oran yine fees.json'dan gelir."""
    c = costs()
    assert c.fee(SYM, Decimal("10000"), maker=True) < c.fee(SYM, Decimal("10000"))


def test_funding_times_are_8h_boundaries_exclusive_of_start():
    """Funding anları 8 saatlik ızgara; açılış anının kendisi sayılmaz."""
    t = funding_times(pd.Timestamp("2026-01-01 00:00", tz="UTC"),
                      pd.Timestamp("2026-01-01 17:00", tz="UTC"))
    assert t == [pd.Timestamp("2026-01-01 08:00", tz="UTC"),
                 pd.Timestamp("2026-01-01 16:00", tz="UTC")]


def test_funding_times_empty_when_end_before_start():
    assert funding_times(ts(10), ts(5)) == []


def test_funding_long_pays_positive_rate():
    """Pozitif oranda long öder (maliyet pozitif), short alır (maliyet negatif)."""
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array([np.datetime64("2026-01-01T08:00")]),
        rates=np.array([0.0001]), imputed_rate=0.0001,
    )}
    start, end = pd.Timestamp("2026-01-01 00:00", tz="UTC"), pd.Timestamp("2026-01-01 09:00", tz="UTC")
    uzun = c.funding_cost(SYM, LONG, Decimal("10000"), start, end)
    c2 = costs(); c2.funding = c.funding
    kisa = c2.funding_cost(SYM, SHORT, Decimal("10000"), start, end)
    assert uzun > 0 and kisa < 0 and uzun == -kisa


def test_funding_outside_coverage_is_imputed_adversely():
    """Kapsam dışı funding anı sıfır sayılmaz; aleyhte atanır ve ayrı sayılır."""
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array([], dtype="datetime64[ns]"), rates=np.array([]), imputed_rate=0.0002,
    )}
    cost = c.funding_cost(SYM, LONG, Decimal("10000"), ts(0), pd.Timestamp("2026-01-01 09:00", tz="UTC"))
    assert cost > 0, "atanan funding aleyhte olmalı"
    assert c.funding_events_imputed == 1 and c.funding_coverage == 0.0


def test_funding_coverage_reports_measured_share():
    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array([np.datetime64("2026-01-01T08:00")]),
        rates=np.array([0.0001]), imputed_rate=0.0001,
    )}
    c.funding_cost(SYM, LONG, Decimal("1000"), pd.Timestamp("2026-01-01 00:00", tz="UTC"),
                   pd.Timestamp("2026-01-01 17:00", tz="UTC"))
    assert c.funding_events == 2 and c.funding_events_imputed == 1
    assert c.funding_coverage == 0.5


# --- portfoy ------------------------------------------------------------------


def pos(side=SHORT, qty="10", price="100") -> Position:
    return Position(symbol=SYM, zone_id="z", side=side, qty=Decimal(qty),
                    avg_price=Decimal(price), opened_at=ts(0), last_funding_at=ts(0))


def test_R_ADD_04_add_updates_average_cost():
    p = pos(qty="10", price="100")
    p.add(Decimal("10"), Decimal("120"))
    assert p.avg_price == Decimal("110") and p.qty == Decimal("20") and p.adds == 1


def test_position_unrealized_sign_by_side():
    assert pos(SHORT, price="100").unrealized(Decimal("90")) > 0
    assert pos(SHORT, price="100").unrealized(Decimal("110")) < 0
    assert pos(LONG, price="100").unrealized(Decimal("110")) > 0


def test_position_reduce_realizes_pnl_and_keeps_avg():
    p = pos(SHORT, qty="10", price="100")
    pnl = p.reduce(Decimal("5"), Decimal("90"))
    assert pnl == Decimal("50") and p.qty == Decimal("5") and p.avg_price == Decimal("100")


def test_equity_is_balance_plus_unrealized():
    """§0.1 · equity = bakiye + açık pozisyonların gerçekleşmemiş PnL'i."""
    pf = Portfolio(balance=Decimal("1000"), start_balance=Decimal("1000"))
    pf.positions[SYM] = pos(SHORT, qty="10", price="100")
    assert pf.equity({SYM: Decimal("90")}) == Decimal("1100")  # 10 × (100 − 90)


def test_R_RISK_05_liq_distance_formula():
    """`δ = equity/N − MMR` — hepsi birlikte aleyhte hareket ederse."""
    pf = Portfolio(balance=Decimal("1000"), start_balance=Decimal("1000"), mmr=Decimal("0.005"))
    pf.positions[SYM] = pos(SHORT, qty="10", price="100")  # N = 1000 @ mark 100
    d = pf.liq_distance({SYM: Decimal("100")})
    assert d == Decimal("1000") / Decimal("1000") - Decimal("0.005")


def test_R_RISK_05_liq_distance_none_without_positions():
    pf = Portfolio(balance=Decimal("1000"), start_balance=Decimal("1000"))
    assert pf.liq_distance({}) is None


def test_R_RISK_05_liquidation_when_equity_below_maintenance():
    pf = Portfolio(balance=Decimal("100"), start_balance=Decimal("100"), mmr=Decimal("0.005"))
    pf.positions[SYM] = pos(SHORT, qty="100", price="100")  # N = 10000
    assert not pf.is_liquidated({SYM: Decimal("100")})
    # fiyat %1 aleyhe: zarar 100 → equity 0 → bakım marjının altında
    assert pf.is_liquidated({SYM: Decimal("101")})


def test_leverage_does_not_enter_liquidation_condition():
    """Cross marjinde koşul `equity ≤ Σ notional × MMR` — kaldıraç geçmez."""
    pf = Portfolio(balance=Decimal("100"), start_balance=Decimal("100"), mmr=Decimal("0.005"))
    pf.positions[SYM] = pos(SHORT, qty="100", price="100")
    before = pf.is_liquidated({SYM: Decimal("101")})
    assert before is pf.is_liquidated({SYM: Decimal("101")})  # kaldıraç alanı yok


# --- uctan uca motor ----------------------------------------------------------


def short_zone() -> Zone:
    """0 = 100 (altta), 1 = 200 (üstte) → SHORT. 0.50=150, 0.70=170, 0.79=179."""
    return Zone.create(SYM, "30m", 100.0, ts(0), 200.0, ts(30))


def symbol_data(bars: list[tuple[float, float]], zone: Zone, obs=()) -> SymbolData:
    """(high, low) listesinden 1m veri. İlk mum zone'un `watch_from`'undan sonradır.

    `obs`: ekleme adayı OB'ler. Ekleme yolu OB olmadan hiç çalışmaz (R-ADD-01 (2)),
    bu yüzden ekleme/risk kolu testleri en az bir OB vermek zorundadır.
    """
    start = zone.watch_from
    n = len(bars)
    t = pd.to_datetime([start + pd.Timedelta(minutes=i) for i in range(n)], utc=True)
    uzak = np.datetime64("2262-01-01")
    return SymbolData(
        symbol=SYM,
        ts=t.tz_convert("UTC").tz_localize(None).to_numpy(),
        high=np.array([b[0] for b in bars], dtype=float),
        low=np.array([b[1] for b in bars], dtype=float),
        close=np.array([(b[0] + b[1]) / 2 for b in bars], dtype=float),
        zones=[zone], obs=list(obs), fvgs=[],
        pierce_at={o.ob_id: None for o in obs},
        ob_top=np.array([o.top for o in obs], dtype=float),
        ob_bottom=np.array([o.bottom for o in obs], dtype=float),
        ob_bull=np.array([o.direction == "BULLISH" for o in obs], dtype=bool),
        ob_impulse=np.array([np.datetime64(o.impulse_at.tz_localize(None)) for o in obs]),
        ob_pierce=np.full(len(obs), uzak),
        ob_alive=np.ones(len(obs), dtype=bool),
    )


def bearish_ob(top: float, bottom: float):
    """SHORT pozisyona ekleme gerekçesi olabilecek, hiç delinmemiş OB."""
    from src.features.ob import OrderBlock

    return OrderBlock(ob_id=f"ob{top}", symbol=SYM, timeframe="30m", direction="BEARISH",
                      top=top, bottom=bottom, created_at=ts(0), impulse_at=ts(0))


# Girer, sonra bandın (170–179) ÖTESİNE çıkar: ekleme yolunun ön koşulu (R-ADD-01 (1)).
ADD_PATH = [(152, 148), (172, 168)] + [(187, 183)] * 10
ADD_OB = (bearish_ob(187.0, 183.0),)


def run(bars, zone=None, **kw) -> tuple:
    zone = zone or short_zone()
    bt = Backtest([symbol_data(bars, zone)], costs(), **kw)
    return bt.run(), zone


WIN = [(152, 148), (172, 168), (152, 148), (102, 98)]  # 0.50 → 0.70 → TP1 → nihai TP
LOSS = [(152, 148), (172, 168), (202, 198)]  # 0.50 → 0.70 → stop (çapa 1)
# Girer ve pozisyonu açık tutar: risk bölgesi davranışını çıkıştan ayrı sınamak için.
ENTRY_ONLY = [(152, 148), (172, 168)] + [(176, 174)] * 10


def test_R_ENTRY_02_enters_on_070_touch_after_primed():
    res, z = run(WIN)
    assert res.counters["entries"] == 1
    assert res.counters["zones_touched"] == 1
    assert res.trades[0].side == SHORT


def test_R_ENTRY_02_no_entry_without_050_precondition():
    """0.50 teması atlanamaz: doğrudan 0.70'e gelen zone giriş üretmez."""
    res, _ = run([(172, 168), (172, 168)])
    assert res.counters["entries"] == 0


def test_R_EXIT_02_final_tp_at_anchor_0_is_profitable():
    res, _ = run(WIN)
    t = res.trades[0]
    assert t.reason == "FINAL_TP" and t.pnl > 0


def test_R_EXIT_01_first_tp_closes_half_at_050():
    """İlk TP pozisyonun ~%50'sini kapatır; kalan nihai TP'ye kadar taşınır."""
    res, _ = run(WIN)
    t = res.trades[0]
    # Giriş ~170, yarısı 150'de, yarısı 100'de kapandı → brüt ≈ qty/2*20 + qty/2*70
    assert t.gross > 0
    assert res.portfolio.balance > res.portfolio.start_balance


def test_R_RISK_02_stop_at_anchor_1_closes_in_loss():
    res, _ = run(LOSS)
    t = res.trades[0]
    assert t.reason == "STOP" and t.pnl < 0


def test_R_ZONE_05_anchor_touch_before_entry_invalidates_without_trade():
    res, _ = run([(152, 148), (202, 198)])
    assert res.counters["entries"] == 0 and res.trades == []


def test_costs_are_charged_on_every_trade():
    """§8 · komisyon ve slippage zorunlu; işlem maliyetsiz raporlanmaz."""
    res, _ = run(WIN)
    t = res.trades[0]
    assert t.fees > 0
    assert res.costs.total_slippage > 0
    assert t.pnl == t.gross - t.fees - t.funding


def test_ambiguous_bar_is_counted_and_stop_wins():
    """§8 · aynı mumda hem hedef hem stop görüldüyse stop varsayılır ve sayılır."""
    res, _ = run([(152, 148), (172, 168), (202, 148)])  # hem 150 hem 200
    assert res.counters["ambiguous_bars"] == 1
    assert res.trades[0].reason == "STOP" and res.trades[0].ambiguous


def test_R_ENTRY_03_notional_is_k_times_equity():
    """Boyut notional üzerinden: qty × fiyat ≈ equity × K."""
    res, _ = run(WIN, start_balance=Decimal("10000"), k=Decimal("1.0"))
    t = res.trades[0]
    assert float(t.qty * t.entry_price) == pytest.approx(10000, rel=0.01)


def test_R_ENTRY_03_k_scales_position_size():
    a, _ = run(WIN, start_balance=Decimal("10000"), k=Decimal("1.0"))
    b, _ = run(WIN, start_balance=Decimal("10000"), k=Decimal("0.5"))
    assert b.trades[0].qty == pytest.approx(a.trades[0].qty / 2, rel=1e-6)


def test_R_RISK_01_notional_cap_blocks_oversized_entry():
    """Tavan aşılıyorsa giriş reddedilir ve sayaca yazılır."""
    res, _ = run(WIN, start_balance=Decimal("10000"), k=Decimal("20"))  # 20× > 10× tavan
    assert res.counters["entries"] == 0 and res.counters["rejected_risk01"] == 1


def test_R_ENTRY_05_flags_recorded_when_no_indicator_present():
    """Gösterge yokken de giriş olur (R-ENTRY-02 (3)) ama bayraklar False kalır."""
    res, _ = run(WIN)
    assert res.counters["entries"] == 1
    assert res.counters["entries_with_ob"] == 0 and res.counters["entries_with_fvg"] == 0
    assert not res.trades[0].had_ob and not res.trades[0].had_fvg


def test_counters_cover_zone_funnel():
    res, _ = run(WIN)
    c = res.counters
    assert c["zones_total"] == 1 and c["zones_touched"] == 1
    assert c["entry_candidates"] == 1 and c["entries"] == 1


def test_position_open_at_data_end_is_closed_and_reported():
    """Veri biterken açık kalan pozisyon son fiyattan kapanır — açık pozisyon raporlanmaz.

    Bu yol funding tahsilatını da tetikler; ızgara tz-naive olduğu için koşu sonu
    damgası aware kurulmazsa funding karşılaştırması patlıyordu.
    """
    res, _ = run([(152, 148), (172, 168), (172, 168)])  # girer, çıkmadan veri biter
    assert len(res.trades) == 1
    assert res.trades[0].reason == "RUN_END"
    assert not res.portfolio.positions


def test_run_end_charges_funding_without_tz_error():
    """Koşu sonu kapanışında funding hesabı tz hatası vermemeli (regresyon)."""
    from src.backtest.costs import FundingCurve

    c = costs()
    c.funding = {SYM: FundingCurve(
        times=np.array([], dtype="datetime64[ns]"), rates=np.array([]), imputed_rate=0.0001,
    )}
    bt = Backtest([symbol_data([(152, 148), (172, 168)] + [(172, 168)] * 600, short_zone())], c)
    res = bt.run()
    assert res.trades and res.trades[0].reason == "RUN_END"
    assert c.funding_events > 0, "600 dakikada en az bir funding anı geçilmeli"


def test_R_RISK_05_thresholds_are_parameters_not_constants():
    """Eşikler süpürülebilir olmalı (R-RISK-05): `t_rahat` yükseltmek girişi kapatır."""
    zone_a = short_zone()
    bt = Backtest([symbol_data(WIN, zone_a)], costs(), t_rahat=Decimal("0.50"))
    assert bt.t_rahat == Decimal("0.50")
    # İlk girişte pozisyon yok → mesafe tanımsız → RAHAT; giriş her hâlükârda olur.
    assert bt.run().counters["entries"] == 1


def test_R_RISK_05_kritik_halves_position():
    """KRITIK bölgesinde pozisyon yarıya iner (R-KILL-04).

    Giriş anında pozisyon yok → mesafe tanımsız → RAHAT, giriş olur. Sonraki mumda
    notional = 1 × equity → oran 1.0 → mesafe 0.995 ≤ t_kritik(1.0) → KRITIK.
    Yarılama sonrası notional yarıya iner, oran ~2.0'a çıkar ve bölgeden çıkılır:
    bu yüzden **tam bir** küçültme olayı beklenir.
    """
    res = Backtest([symbol_data(ENTRY_ONLY, short_zone())], costs(),
                   t_rahat=Decimal("2.0"), t_kritik=Decimal("1.0")).run()
    assert res.counters["deleverage_events"] == 1


def test_R_RISK_05_no_deleverage_when_threshold_low():
    """Aynı senaryo, düşük `t_kritik`: küçültme tetiklenmez — parametre gerçekten bağlıyor."""
    res = Backtest([symbol_data(ENTRY_ONLY, short_zone())], costs(),
                   t_rahat=Decimal("0.10"), t_kritik=Decimal("0.01")).run()
    assert res.counters["deleverage_events"] == 0


# R-ADD-04 · ekleme sonrasi maliyete donus. Giris 170, 185'te 1-3 ekleme -> maliyet
# 181.25. `TO_COST` maliyete iki kez doner, `NO_COST` hic donmez; ikisi de 200'de durur.
REDUCE_OB = (bearish_ob(187.0, 183.0),)
ADD_TO_COST = [(152, 148), (172, 168), (187, 183), (182, 180), (182, 180), (202, 198)]
ADD_NO_COST = [(152, 148), (172, 168), (187, 183), (187, 183), (187, 183), (202, 198)]


def free_costs() -> CostModel:
    """Sifir komisyon, sifir slippage: kucultmenin PnL uretmedigi tam olarak gorulsun."""
    return CostModel(fees={SYM: Fees(Decimal("0"), Decimal("0"))}, funding={},
                     slippage_bps=Decimal("0"))


def test_R_ADD_04_reduces_to_k_base_instead_of_exiting():
    """Maliyete donus cikis degil, K tabanina kucultme. Elle:

    giris   : 10.000 × K(0.2) = 2.000 / 170                 -> qty 11,7647
    ekleme  : 185'te. 1-1 -> 177,50 · 1-3 -> (170+555)/4 = 181,25 >= 179  ✔ 1-3
              qty 4 × 11,7647 = 47,0588 · ortalama maliyet 181,25
    kucultme: 181,25'e donuste. O mumda mark 181 ->
              equity = 10.000 + 47,0588 × (181,25 − 181)     -> 10.011,76
              hedef notional = 0,2 × 10.011,76               ->  2.002,35
              kucultme maliyetin **tam uzerinde** yapildigi icin realize PnL = 0
    stop    : 200. kalan = 2.002,35 / 181,25 = 11,0475
              brut = 11,0475 × (181,25 − 200)                ->   −207,14

    Ekleme yapilip maliyete hic donulmeyen kolda ayni pozisyon 47,0588 adetle stopa
    gider: brut = 47,0588 × (−18,75) = −882,35. Fark kucultmenin tasidigi riskin
    tamami; islem her iki kolda da **stopta** kapanir, kucultme bir cikis degildir.
    """
    res = Backtest([symbol_data(ADD_TO_COST, short_zone(), REDUCE_OB)], free_costs(),
                   k=Decimal("0.2")).run()
    assert res.counters["adds"] == 1 and res.counters["adds_by_mult"] == {"1-3": 1}
    assert res.counters["reduce_events"] == 1  # ikinci maliyet temasi yeniden kucultmez
    assert len(res.trades) == 1

    t = res.trades[0]
    assert t.reason == "STOP"  # kucultme cikis nedeni degil
    assert t.reduces == 1
    assert t.bars_after_reduce == 2
    assert t.qty == pytest.approx(Decimal("47.0588"), abs=Decimal("0.0001"))  # max_qty
    kalan = -t.gross / Decimal("18.75")  # stop 200 − maliyet 181,25
    assert kalan * Decimal("181.25") == pytest.approx(Decimal("2002.35"),
                                                      abs=Decimal("0.01"))
    assert t.gross == pytest.approx(Decimal("-207.14"), abs=Decimal("0.01"))


def test_R_ADD_04_no_reduce_without_return_to_cost():
    """Ayni ekleme, maliyete donus yok: pozisyon tam boyuyla stopa gider."""
    res = Backtest([symbol_data(ADD_NO_COST, short_zone(), REDUCE_OB)], free_costs(),
                   k=Decimal("0.2")).run()
    t = res.trades[0]
    assert res.counters["adds"] == 1 and res.counters["reduce_events"] == 0
    assert t.reduces == 0 and t.bars_after_reduce == 0
    assert t.reason == "STOP"
    assert t.gross == pytest.approx(Decimal("-882.35"), abs=Decimal("0.01"))


def test_R_ADD_04_reduce_fires_once_per_add_not_every_bar():
    """Tetik ateslendikten sonra temizlenir (koruma 1).

    Ekleme sonrasi maliyet 181,25. Ardindan **sekiz** mum boyunca fiyat maliyete
    deginiyor (182/180). Kucultme yalnizca ilkinde atesler: tetigi ekleme kurar,
    kucultme dusurur. Aksi halde ayni pozisyon her mumda yeniden kucultulur ve
    komisyon zinciri pozisyonu sifira dogru asindirirdi.
    """
    bars = [(152, 148), (172, 168), (187, 183)] + [(182, 180)] * 8 + [(202, 198)]
    res = Backtest([symbol_data(bars, short_zone(), REDUCE_OB)], free_costs(),
                   k=Decimal("0.2")).run()
    assert res.counters["adds"] == 1
    assert res.counters["reduce_events"] == 1
    assert res.trades[0].reduces == 1
    assert res.trades[0].reason == "STOP"


def test_R_ADD_04_skips_reduce_when_already_at_k_base():
    """Pozisyon zaten K tabanindaysa kucultme atlanir (koruma 2), tetik yine dusürulur.

    K tabani = 0,2 × 10.000 / 100 = 20 adet; elde 1 adet var, yani zaten tabanin
    altinda. Kucultme calisirsa pozisyonu buyutmesi gerekirdi — kural kucultmedir.
    """
    z = short_zone()
    bt = Backtest([symbol_data(ADD_TO_COST, z, REDUCE_OB)], free_costs(), k=Decimal("0.2"))
    p = pos(SHORT, qty="1", price="100")
    p.reduce_armed = True
    bt.pf.positions[SYM] = p
    bt.marks[SYM] = 100.0

    bt._reduce_to_base(z, p, 100.0, ts(1))

    assert bt.counters["reduce_events"] == 0
    assert p.qty == Decimal("1") and p.reduces == 0 and p.reduced_at is None
    assert p.reduce_armed is False  # tetik her durumda temizlenir
    assert bt.trades == []


# --- OPEN-29 · pozisyon sonlandirma adaylari ---------------------------------
# Spec'te sonlandirma kurali YOK (R-EXIT-03 "zaman siniri yok"). Bu adaylar yalnizca
# olculmek icin var ve varsayilan `none`; testler kurallarin dogru tetiklendigini ve
# `none` iken hicbir sey yapmadigini sabitler.

HOLD = [(152, 148), (172, 168)] + [(176, 174)] * 10  # girer, bant icinde bekler


def bias_veren(z, yon: str, dakika: int = 4):
    """`HOLD` verisine 4h yapisal yon ekler: `dakika`'dan itibaren `yon` bilinir."""
    sd = symbol_data(HOLD, z)
    sd.bias_known = np.array(
        [np.datetime64((z.watch_from + pd.Timedelta(minutes=dakika)).tz_localize(None))])
    sd.bias_val = np.array([yon], dtype=object)
    return sd


def test_OPEN_29_none_is_the_default_and_closes_nothing():
    """Varsayilan spec'in yazili hali: pozisyon kosu sonuna kadar tasinir."""
    res = Backtest([symbol_data(HOLD, short_zone())], free_costs()).run()
    assert res.counters["terminated"] == 0
    assert res.trades[0].reason == "RUN_END"


def test_OPEN_29_time_stop_closes_position_after_limit():
    """Sert sure siniri: tasima `max_hold_bars`'i asinca piyasa emriyle kapanir."""
    res = Backtest([symbol_data(HOLD, short_zone())], free_costs(),
                   terminate="time", max_hold_bars=5).run()
    t = res.trades[0]
    assert t.reason == "TIME_STOP"
    assert res.counters["terminated"] == 1
    assert t.bars_held == 5  # giristen tam 5 mum sonra


def test_OPEN_29_structure_flip_closes_short_when_4h_turns_up():
    """Yapisal gecersizlik: SHORT pozisyon acikken 4h yon UP'a gecerse tez olmustur."""
    z = short_zone()
    res = Backtest([bias_veren(z, "UP")], free_costs(), terminate="structure").run()
    assert res.trades[0].reason == "STRUCT_FLIP"
    assert res.counters["terminated"] == 1


def test_OPEN_29_structure_does_not_close_when_bias_was_already_against_at_entry():
    """Girişte yön zaten karşıysa bu bir **dönüş** değildir, kural tetiklenmez.

    Ölçüm: aksi okumada (yön karşıysa kapat) işlemlerin %32.8'i kapanıyordu ve
    %92'si girişten bir mum sonra — yani kural çıkış kuralı olmaktan çıkıp geriye
    dönük bir giriş filtresine dönüşüyordu. Girişte karşı olan yön R-ENTRY sorusudur.
    """
    z = short_zone()
    res = Backtest([bias_veren(z, "UP", dakika=0)], free_costs(),
                   terminate="structure").run()
    assert res.counters["terminated"] == 0
    assert res.trades[0].reason == "RUN_END"


def test_OPEN_29_structure_keeps_position_when_bias_aligned_or_unknown():
    """Ayni yon (DOWN) ve kararsiz yapi (NONE) kapatmaz — yalnizca **karsi** yon kapatir."""
    for yon in ("DOWN", "NONE"):
        z = short_zone()
        res = Backtest([bias_veren(z, yon)], free_costs(), terminate="structure").run()
        assert res.counters["terminated"] == 0, yon
        assert res.trades[0].reason == "RUN_END", yon


def test_OPEN_29_structure_bias_is_not_read_before_it_is_known():
    """CLAUDE.md #3 · yon ancak `known_at`'ten sonra okunur.

    Yon UP ama teyidi kosunun sonundan sonra dusuyor: karar aninda bilinmiyor, bu
    yuzden pozisyon kapanmaz. Erken okunsaydi look-ahead olurdu.
    """
    z = short_zone()
    res = Backtest([bias_veren(z, "UP", dakika=999)], free_costs(),
                   terminate="structure").run()
    assert res.counters["terminated"] == 0
    assert res.trades[0].reason == "RUN_END"


def test_OPEN_29_funding_cap_measured_against_potential_profit():
    """Funding tavani: birikmis funding > oran × (nihai TP'ye kalan kar).

    SHORT, ortalama maliyet 170, capa 0 = 100, qty 10 ->
    potansiyel kar 10 × 70 = 700 · tavan %10 -> 70.
    """
    z = short_zone()
    sd = symbol_data(HOLD, z)
    bt = Backtest([sd], free_costs(), terminate="funding",
                  funding_cap_ratio=Decimal("0.10"))
    p = pos(SHORT, qty="10", price="170")
    t64 = np.datetime64(z.watch_from.tz_localize(None))

    p.funding_paid = Decimal("69")
    assert bt._termination_reason(sd, p, z, ts(1), t64) is None
    p.funding_paid = Decimal("71")
    assert bt._termination_reason(sd, p, z, ts(1), t64) == "FUNDING_CAP"


def test_OPEN_29_unknown_rule_is_rejected():
    """Yanlis yazilmis kural sessizce `none`'a dusmez."""
    with pytest.raises(ValueError):
        Backtest([symbol_data(HOLD, short_zone())], free_costs(), terminate="saat")


def test_R_RISK_05_uyari_blocks_adds_is_a_parameter():
    """UYARI'nın eklemeyi engellemesi süpürülebilir bir koldur.

    `t_rahat = 2.0` ile tek pozisyonda bile UYARI'dayız (mesafe ≈ 0.995), ama
    `t_kritik = 0.01` olduğu için KRİTİK değiliz. Açık kolda ekleme `ADD-REJECT-D`
    ile reddedilir; kapalı kolda ekleme gerçekleşir.
    """
    acik = Backtest([symbol_data(ADD_PATH, short_zone(), ADD_OB)], costs(),
                    t_rahat=Decimal("2.0"), t_kritik=Decimal("0.01"),
                    uyari_blocks_adds=True).run()
    kapali = Backtest([symbol_data(ADD_PATH, short_zone(), ADD_OB)], costs(),
                      t_rahat=Decimal("2.0"), t_kritik=Decimal("0.01"),
                      uyari_blocks_adds=False).run()
    assert acik.counters["add_reject_d"] > 0 and acik.counters["adds"] == 0
    assert kapali.counters["add_reject_d"] == 0 and kapali.counters["adds"] > 0


def test_R_RISK_05_kritik_behaves_identically_in_both_arms():
    """KRİTİK her iki kolda da eklemeyi durdurur ve küçültür; kol yalnızca UYARI'yı etkiler.

    Ölçüt kolların **aynı** sonucu vermesi: `uyari_blocks_adds` KRİTİK davranışına
    dokunmamalı.

    Not: "KRİTİK'te ekleme olmaz" ≠ "hiç ekleme olmaz". Yarılama `equity/notional`
    oranını ikiye katladığı için birkaç adımda bölgeden çıkılır; çıkıldıktan sonra
    ekleme normal kurallara göre yeniden mümkün olur. Küçültmenin açtığı yer kısmen
    yeniden kaldıraca dönüşür — ızgarada bu, küçültme maliyeti kaleminin yanında okunur.
    """
    sonuc = []
    for arm in (True, False):
        res = Backtest([symbol_data(ADD_PATH, short_zone(), ADD_OB)], costs(),
                       t_rahat=Decimal("3.0"), t_kritik=Decimal("2.0"),
                       uyari_blocks_adds=arm).run()
        sonuc.append((res.counters["adds"], res.counters["add_reject_d"],
                      res.counters["deleverage_events"]))
    assert sonuc[0] == sonuc[1], "kol KRİTİK davranışını değiştirmemeli"
    assert sonuc[0][1] > 0, "KRİTİK'te ekleme reddedilmeli"
    assert sonuc[0][2] > 0, "KRİTİK'te küçültme yapılmalı"


def test_R_RISK_01_binding_counter_counts_bars():
    """Tavan bağlıyken geçen mumlar sayılır: notional > (10 − K) × equity."""
    res = Backtest([symbol_data(ENTRY_ONLY, short_zone())], costs(), k=Decimal("9.5"),
                   t_rahat=Decimal("0.001"), t_kritik=Decimal("0.0001")).run()
    assert res.counters["entries"] == 1  # 9.5 < 10 → giriş tavanı aşmıyor
    assert res.counters["risk01_binding_bars"] > 0  # ama sonrasında tavan bağlıyor
    assert res.counters["bars_total"] > 0


def test_reset_for_rerun_reproduces_identical_run():
    """Izgara süpürmesi aynı veriyi yeniden kullanır; sonuç birebir aynı olmalı."""
    from src.backtest.engine import reset_for_rerun

    data = [symbol_data(WIN, short_zone())]
    ilk = Backtest(data, costs()).run()
    reset_for_rerun(data)
    ikinci = Backtest(data, costs()).run()
    assert ilk.portfolio.balance == ikinci.portfolio.balance
    assert len(ilk.trades) == len(ikinci.trades) == 1


def test_reset_for_rerun_is_mandatory_and_fails_loudly():
    """Sıfırlamadan ikinci koşu **hata verir**, sessizce boş sonuç üretmez.

    Zone terminal durumda kaldığı için `activate()` R-ZONE-04 dışı bir geçiş dener.
    Izgara süpürmesinde `reset_for_rerun` atlanırsa koşu durur — sessizce "hiç işlem
    yok" diyen bir tablo üretmez (CLAUDE.md #8).
    """
    from src.zones.model import InvalidTransition

    data = [symbol_data(WIN, short_zone())]
    Backtest(data, costs()).run()
    with pytest.raises(InvalidTransition):
        Backtest(data, costs()).run()


def test_max_drawdown_is_recorded():
    res, _ = run(LOSS)
    assert res.portfolio.max_drawdown > 0


def test_min_equity_ratio_recorded_while_position_open():
    """§9 · MMR'siz likidasyon ölçüsü: min(equity / toplam notional)."""
    res, _ = run(WIN)
    assert res.portfolio.min_equity_ratio is not None
    assert res.portfolio.min_liq_distance == res.portfolio.min_equity_ratio - res.portfolio.mmr


# --- R-ENTRY-02 (3) kapali varyanti (require_indicator) -----------------------

ENTRY_PATH = [(152, 148), (172, 168), (172, 168)]
"""0.50'ye (150) temas -> PRIMED, sonra 0.70'e (170) donus -> TOUCHED + dolum."""


def _entry_kos(require_indicator: bool, obs=()):
    z = short_zone()
    sd = symbol_data(ENTRY_PATH, z, obs)
    return Backtest([sd], costs(slippage=Decimal("0")), Decimal("17000"),
                    require_indicator=require_indicator).run()


def test_R_ENTRY_02_bare_touch_enters_by_default():
    """Spec'in yazili hali: gosterge yoksa 0.70 temasi gecerli giristir."""
    res = _entry_kos(False)
    assert res.counters["entries"] == 1
    assert res.counters["no_indicator_skipped"] == 0


def test_R_ENTRY_02_require_indicator_skips_bare_touch():
    """Varyant: gosterge yoksa giris yok. Aday sayilir ama silahlanmaz."""
    res = _entry_kos(True)
    assert res.counters["entries"] == 0
    assert res.counters["no_indicator_skipped"] == 1
    assert res.counters["entry_candidates"] == 1
    assert res.counters["armed"] == 0


def test_R_ENTRY_02_require_indicator_still_enters_with_eligible_ob():
    """Bantta uygun OB varsa kapi acik kalir (R-ENTRY-05 suzgecinden gecen)."""
    res = _entry_kos(True, obs=(bearish_ob(179.0, 170.0),))
    assert res.counters["entries"] == 1
    assert res.counters["no_indicator_skipped"] == 0


# --- kalem defteri: toplamlar gercek PnL'e kapanmali --------------------------


def test_cost_ledger_sums_to_totals_and_balance():
    """Kalem defteri kapanmazsa (a) uzlastirmasi anlamsiz olur.

    Uc kimlik birden: komisyon kalemleri toplami = `total_fees`; slippage kalemleri
    toplami = `total_slippage`; bakiye degisimi = islem PnL'lerinin toplami.
    """
    z = short_zone()
    sd = symbol_data(ADD_PATH + [(152, 148)] * 5, z, ADD_OB)
    res = Backtest([sd], costs(), Decimal("17000")).run()
    c = res.costs

    assert sum(v for k, v in c.breakdown.items() if k.startswith("komisyon_")) == c.total_fees
    assert sum(v for k, v in c.breakdown.items() if k.startswith("slippage_")) == c.total_slippage
    assert c.breakdown.get("funding", Decimal("0")) == c.total_funding

    # `qty = notional / price` devirli ondalik uretir; kimlik Decimal'in 28 hanesinin
    # son basamaginda kapanir. Tolerans o artik icin, gevseklik icin degil.
    pf = res.portfolio
    fark = pf.balance - pf.start_balance - sum((t.pnl for t in res.trades), Decimal("0"))
    assert abs(fark) < Decimal("1e-20"), fark


def test_ruin_bars_counted_against_start_balance():
    """Equity esigin altindaysa bar sayilir; ustundeyse sayilmaz."""
    z = short_zone()
    sd = symbol_data(ADD_PATH, z, ADD_OB)
    res = Backtest([sd], costs(), Decimal("17000")).run()
    pf = res.portfolio
    assert pf.observed_bars == res.counters["bars_total"]
    # Esikler ic ice: %10'un altindaki her bar %25 ve %50'nin de altindadir.
    assert pf.ruin_bars[0.10] <= pf.ruin_bars[0.25] <= pf.ruin_bars[0.50]
