"""Salınım ve emir tipi kollarının davranış testleri (`scripts/levers.py` kolları).

Üçü de **spec'te yoktur** ve varsayılanları kapalıdır; yalnızca ölçülmek için var:

| kol | motor parametresi | ne yapar |
|---|---|---|
| B | `max_adds` | pozisyon ömrü boyunca ekleme tavanı (R-ADD-01/03 sayı sınırı koymaz) |
| B | `reduce_once` | R-ADD-04 küçültmesi pozisyon başına bir kez kurulur |
| C | `limit_orders` | giriş/TP/ekleme/küçültme limit emri: maker, slippage yok, 1 tick aşım |

Referans zone: `0 = 100` (altta), `1 = 200` (üstte) → SHORT.
`0.50 = 150` · `0.70 = 170` · `0.79 = 179`. Tick testlerde **1.0** seçildi: aşım
kuralının hangi mumda doldurup hangisinde doldurmadığı çıplak gözle okunsun diye.
"""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from src.backtest.costs import CostModel, Fees
from src.backtest.engine import Backtest
from src.backtest.portfolio import LONG, SHORT, Position
from src.zones.model import Zone
from tests.test_backtest import SYM, bearish_ob, short_zone, symbol_data, ts

# Ekleme yolunun OB'leri: her biri ayrı bir mumda dokunulur, her biri bir ekleme.
OB1, OB2, OB3 = bearish_ob(187.0, 183.0), bearish_ob(192.0, 188.0), bearish_ob(197.0, 193.0)

PRIMED_ENTER = [(152, 148), (172, 168)]  # 0.50 → PRIMED, 0.70 → TOUCHED + ENTERED @170


def free_costs(tick: str = "0") -> CostModel:
    """Sıfır komisyon/slippage: sayılan şey davranış, para değil. `tick` limit kolu için."""
    return CostModel(
        fees={SYM: Fees(Decimal("0"), Decimal("0"), Decimal(tick))},
        funding={}, slippage_bps=Decimal("0"),
    )


def real_costs(tick: str = "1") -> CostModel:
    """Borsa oranları (taker 5 bps, maker 2 bps) + 2 bps slippage varsayımı."""
    return CostModel(
        fees={SYM: Fees(Decimal("0.0005"), Decimal("0.0002"), Decimal(tick))},
        funding={}, slippage_bps=Decimal("2"),
    )


def kos(bars, costs=None, obs=(), **kw):
    """Ölçüm koşusuyla aynı yapılandırma: `K=0.2`, UYARI eklemeyi engellemez.

    UYARI engeli açık olsaydı üçüncü ekleme `ADD-REJECT-D`'ye takılır ve test
    ölçmek istediği tavanı değil risk bandını sınardı.
    """
    z = short_zone()
    return Backtest([symbol_data(bars, z, obs)], costs or free_costs(),
                    k=Decimal("0.2"), uyari_blocks_adds=False, **kw).run()


# --- B · ekleme tavanı --------------------------------------------------------

# Giriş 170. Üç OB üç ayrı mumda dokunuluyor → tavan yokken üç ekleme.
UC_EKLEME = PRIMED_ENTER + [(187, 183), (192, 188), (197, 193), (202, 198)]


def test_B_max_adds_kapaliyken_her_OB_ekleme_uretir():
    """`max_adds=None` (test fixture'ı): R-ADD kurallarının yazılı hâli, sınır yok."""
    res = kos(UC_EKLEME, obs=(OB1, OB2, OB3))
    assert res.counters["adds"] == 3
    assert res.counters["add_reject_cap"] == 0


def test_B_max_adds_tavani_uctuncu_eklemeyi_reddeder():
    res = kos(UC_EKLEME, obs=(OB1, OB2, OB3), max_adds=2)
    assert res.counters["adds"] == 2
    assert res.counters["add_reject_cap"] == 1  # üçüncü OB'ye dokunuldu, ekleme yok
    assert res.trades[0].adds == 2


def test_F1_v1_varsayilani_ekleme_kapali(monkeypatch):
    """Spec §3: v1'de ekleme kapali. Fixture'in `None`'u geri alininca motor 0 okur."""
    monkeypatch.undo()
    assert Backtest([symbol_data([], short_zone())], free_costs()).max_adds == 0


def test_F1_max_adds_sifir_ekleme_ve_kucultme_uretmez():
    """F1 · `max_adds=0` hiç ekleme yok; ekleme olmayınca R-ADD-04 küçültmesi de kurulmaz."""
    res = kos(IKI_SALINIM, obs=(OB1, OB2), max_adds=0)
    assert res.counters["adds"] == 0 and res.counters["reduce_events"] == 0
    assert res.counters["add_reject_cap"] >= 1
    assert res.trades[0].adds == 0 and res.trades[0].reason == "STOP"


# F2 · referans zone leg'i |200 - 100| / 100 = 1.0
def test_F2_esik_alti_leg_giris_uretmez():
    res = kos(STOP_YOLU, min_leg_pct=1.0)  # esit = esik alti (alt tertil `<=`)
    assert res.counters["entries"] == 0 and res.counters["leg_skipped"] == 1


def test_F2_esik_ustu_leg_girer():
    res = kos(STOP_YOLU, min_leg_pct=0.99)
    assert res.counters["entries"] == 1 and res.counters["leg_skipped"] == 0


# --- B · küçültme bir kez -----------------------------------------------------

# Giriş 170 → ekleme 185 (1-3, maliyet 181,25) → maliyete dönüş (küçültme 1) →
# ekleme 190 (1-1, maliyet 185,625) → maliyete dönüş (küçültme 2) → stop.
IKI_SALINIM = PRIMED_ENTER + [(187, 183), (182, 180), (192, 188), (187, 185), (202, 198)]


def test_B_reduce_once_kapaliyken_her_ekleme_tetigi_yeniden_kurar():
    """Spec'in yazılı hâli: `R-ADD-04` her eklemeden sonra geçerlidir."""
    res = kos(IKI_SALINIM, obs=(OB1, OB2))
    assert res.counters["adds"] == 2
    assert res.counters["reduce_events"] == 2


def test_B_reduce_once_ikinci_kucultmeyi_kurmaz():
    res = kos(IKI_SALINIM, obs=(OB1, OB2), reduce_once=True)
    assert res.counters["adds"] == 2  # ekleme etkilenmez, yalnızca küçültme tetiği
    assert res.counters["reduce_events"] == 1
    assert res.trades[0].reduces == 1


# --- C · limit emri: 1 tick aşım ---------------------------------------------

# Her seviyeye önce **dokunan** sonra **1 tick geçen** bir mum: temas dolum değildir.
TICK_YOLU = [
    (152, 148),      # 0.50 → PRIMED
    (170.5, 169.5),  # 0.70 → TOUCHED; satış limiti 170, aşım 171 değil → dolmaz
    (172, 168),      # 172 >= 171 → giriş dolar, tam 170'ten
    (152, 149.5),    # TP1 150'ye dokundu, 149 altına inmedi → dolmaz
    (152, 148),      # 148 <= 149 → TP1 dolar
    (102, 99.5),     # nihai TP 100'e dokundu, 99 altına inmedi → dolmaz
    (102, 98),       # 98 <= 99 → nihai TP dolar
]


def test_C_limit_kapaliyken_temas_doldurur():
    """Referans davranış: piyasa emri, temas yeter — aynı mumlar, aşım aranmaz."""
    res = kos(TICK_YOLU, costs=free_costs())
    assert res.counters["limit_miss_giris"] == 0
    assert res.counters["limit_miss_tp"] == 0
    t = res.trades[0]
    assert t.reason == "FINAL_TP" and t.reached_tp1
    # Giriş 0.70'e **dokunulan** mumda olur; limit kolunda bir mum sonra oluyordu.
    assert t.bars_held == 4  # 0.70 teması (i=1) → nihai TP teması (i=5)


def test_C_limit_acikken_temas_yetmez_1_tick_gerekir():
    res = kos(TICK_YOLU, costs=free_costs("1"), limit_orders=True)
    assert res.counters["limit_miss_giris"] == 1  # 170'e dokundu, 171'i görmedi
    assert res.counters["limit_miss_tp"] == 2     # TP1 ve nihai TP birer kez
    t = res.trades[0]
    assert t.reason == "FINAL_TP"
    assert t.entry_price == Decimal("170")  # limit fiyatı: slippage yok
    assert t.reached_tp1


def test_C_limit_kolunda_slippage_yok_ve_komisyon_maker():
    """Giriş/TP1/nihai TP limit emri: defterde slippage kalemi hiç açılmaz."""
    res = kos(TICK_YOLU, costs=real_costs("1"), limit_orders=True)
    assert res.costs.total_slippage == Decimal("0")
    assert not [k for k in res.costs.breakdown if k.startswith("slippage_")]
    assert set(res.costs.breakdown) == {"komisyon_giris", "komisyon_tp1", "komisyon_tp_nihai"}
    # maker 2 bps: giriş notional 2.000 → 0,40
    assert res.costs.breakdown["komisyon_giris"] == pytest.approx(
        Decimal("0.4"), abs=Decimal("0.001"))


# Aynı yol ama stopla biter: stop limit emri değildir, taker + slippage öder.
STOP_YOLU = PRIMED_ENTER + [(202, 198)]


def test_C_stop_limit_kolunda_da_taker_ve_slippageli():
    res = kos(STOP_YOLU, costs=real_costs("1"), limit_orders=True)
    assert res.trades[0].reason == "STOP"
    assert res.costs.breakdown["slippage_stop"] > 0
    # taker 5 bps, maker 2 bps: aynı notional'de stop komisyonu girişinkinin katı
    assert res.costs.breakdown["komisyon_stop"] > res.costs.breakdown["komisyon_giris"]


def test_C_tick_bilinmiyorsa_limit_kolu_kosmaz():
    """CLAUDE.md #5/#8 — adım uydurulmaz, kol hata verir."""
    with pytest.raises(ValueError, match="tick"):
        kos(TICK_YOLU, costs=free_costs("0"), limit_orders=True)


# --- D kollari · TP yerlesimi (R-EXIT-01/02) ----------------------------------

def long_zone() -> Zone:
    """0 = 200 (ustte), 1 = 100 (altta) -> LONG. span negatif; oteleme asagi gider."""
    return Zone.create(SYM, "30m", 200.0, ts(0), 100.0, ts(30))


def test_D_tp_offset_yonu_her_iki_biasta_da_erken_cikistir():
    """Oteleme fib oraninda; fiyatta SHORT'ta yukari, LONG'da asagi — ikisi de erken.

    leg 100. SHORT: 0.50 (150) -> 152, 0 (100) -> 102.
    LONG:      0.50 (150) -> 148, 0 (200) -> 198.
    Fiyat bandi `1` tarafindan `0` tarafina kat eder; otelenmis TP her iki yonde de
    fiyatin **once** gordugu seviyedir.
    """
    z = short_zone()
    z.tp_offset = 0.02
    assert (z.tp_050, z.tp_final) == (152.0, 102.0)
    lz = long_zone()
    lz.tp_offset = 0.02
    assert (lz.tp_050, lz.tp_final) == (148.0, 198.0)


def test_D_tp_offset_sifirken_spec_seviyeleri_aynen_kalir():
    z = short_zone()
    assert (z.tp_050, z.tp_final) == (z.level_050, z.anchor_0_price) == (150.0, 100.0)


# 0.50'ye (150) hic inmeyen ama 152'yi goren bir mum: oteleme tek fark.
ERKEN_TP = PRIMED_ENTER + [(153, 151.5), (202, 198)]


def test_D_tp_offset_yokken_150_gorulmez_ve_islem_stopa_gider():
    res = kos(ERKEN_TP)
    t = res.trades[0]
    assert not t.reached_tp1 and t.reason == "STOP"


def test_D_tp_offset_ile_ayni_mum_TP1_doldurur():
    res = kos(ERKEN_TP, tp_offset=0.02)
    t = res.trades[0]
    assert t.reached_tp1  # 152 goruldu; spec seviyesi 150 hic gelmedi
    assert t.reason == "STOP"  # kalan yarisi yine stopa gider


# --- D4 · TP piyasa emri ------------------------------------------------------

# TP seviyelerine dokunan ama 1 tick asmayan mumlar: limit kolunda kacar, piyasa kolunda dolar.
TP_TEMAS = [(152, 148), (170.5, 169.5), (172, 168), (152, 149.5), (102, 99.5)]


def test_D4_limit_kolunda_TP_temasi_doldurmaz():
    res = kos(TP_TEMAS, costs=real_costs("1"), limit_orders=True)
    assert res.counters["limit_miss_tp"] == 2
    assert res.trades[0].reason == "RUN_END"  # pozisyon acik kaldi, kosu sonunda kapandi


def test_D4_tp_market_temasla_dolar_ve_taker_slippage_oder():
    res = kos(TP_TEMAS, costs=real_costs("1"), limit_orders=True, tp_market=True)
    t = res.trades[0]
    assert res.counters["limit_miss_tp"] == 0
    assert t.reason == "FINAL_TP" and t.reached_tp1
    b = res.costs.breakdown
    assert b["slippage_tp1"] > 0 and b["slippage_tp_nihai"] > 0  # piyasa emri
    # Giris hala limit: 2.000 notional x maker 2 bps = 0,40 (taker olsa 1,00 olurdu)
    assert b["komisyon_giris"] == pytest.approx(Decimal("0.4"), abs=Decimal("0.001"))
    assert "slippage_giris" not in b


# --- ADD-REJECT-E · pozisyon seviyesinde stop kaybi tavani --------------------
#
# Referans zone: giris 170, nihai stop 200 -> birim basina 30 kayip.
# K=0.2, equity 10.000 -> notional 2.000, qty 11,7647.
# Ilk girisin stopta kaybi: 11,7647 x 30 = 352,94  ->  equity'nin **%3,53**'u.
# Ekleme 185'te (1-3): toplam 47,0588, maliyet 181,25.
# Eklemeden sonra stopta kayip: 47,0588 x 18,75 = 882,35; o andaki equity ~9.824
# (mark 185, acik zarar -176) -> **%8,98**.

def test_ADD_REJECT_E_kapaliyken_giris_ve_ekleme_yapilir():
    """Varsayilan `0` spec'in yazili hali: tavan yok."""
    res = kos(UC_EKLEME, obs=(OB1,))
    assert res.counters["entries"] == 1 and res.counters["adds"] == 1
    assert res.counters["entry_reject_e"] == 0 and res.counters["add_reject_e"] == 0


def test_ADD_REJECT_E_ilk_girisi_de_kapsar():
    """%3 tavan: girisin kendi stop kaybi %3,53 — pozisyon hic acilmaz."""
    res = kos(UC_EKLEME, obs=(OB1,), stop_loss_cap=Decimal("0.03"))
    assert res.counters["entry_reject_e"] == 1
    assert res.counters["entries"] == 0 and res.trades == []


def test_ADD_REJECT_E_giris_gecer_ekleme_reddedilir():
    """%8 tavan: giris %3,53 ile gecer, ekleme %8,98 ile takilir."""
    res = kos(UC_EKLEME, obs=(OB1,), stop_loss_cap=Decimal("0.08"))
    assert res.counters["entries"] == 1
    assert res.counters["adds"] == 0 and res.counters["add_reject_e"] == 1
    assert res.trades[0].adds == 0  # pozisyon giris boyutuyla stopa gitti


def test_ADD_REJECT_E_tavan_yeterince_genisse_ekleme_gecer():
    """%10 tavan: ekleme sonrasi %8,98 < %10 — kural baglamaz."""
    res = kos(UC_EKLEME, obs=(OB1,), stop_loss_cap=Decimal("0.10"))
    assert res.counters["adds"] == 1 and res.counters["add_reject_e"] == 0


def test_ADD_REJECT_E_olcusu_notional_degil_stop_kaybidir():
    """`R-RISK-01`'den farki: ayni notional, farkli stop mesafesi -> farkli karar.

    Stopu girise **yakin** bir zone'da ayni notional cok daha az risk tasir.
    0 = 100 / 1 = 176 zone'unda 0.70 = 153,2 ve stop mesafesi 22,8 (30 yerine);
    ayni K ile stop kaybi %2,98'e duser ve %3 tavanini gecer.
    """
    dar = Zone.create(SYM, "30m", 100.0, ts(0), 176.0, ts(30))
    bars = [(139, 137), (154, 152)] + [(160, 158)] * 3  # 0.50=138 -> 0.70=153,2
    res = Backtest([symbol_data(bars, dar)], free_costs(), k=Decimal("0.2"),
                   uyari_blocks_adds=False, stop_loss_cap=Decimal("0.03")).run()
    assert res.counters["entries"] == 1 and res.counters["entry_reject_e"] == 0


# --- R-EXIT-01 · breakeven stop ve islem ucreti -------------------------------
#
# Kuralin orijinal tanimi ilk TP'nin alt sinirini "islem ucretlerini karsilayacak
# kadar" diye veriyor ve "sonrasinda stop maliyete cekilir" diyor. Ham ortalama
# maliyette kapanan yarinin brutu **sifirdir**: odenen gidis-donus komisyonu net
# zarar kalir. `breakeven_fees` seviyeyi o komisyon kadar kar tarafina oteler.
#
# Referans zone SHORT, giris 170, tp_050 = 150. Limit kolunda gidis-donus orani
# maker 2 bps (giris) + taker 5 bps (breakeven piyasa emridir) = **7 bps**
# -> otelenmis seviye 170 x 0.9993 = 169,881.

BE_ORAN = Decimal("0.0007")  # maker giris + taker cikis


def fee_only(tick: str = "1") -> CostModel:
    """Borsa komisyonu var, slippage **yok** — otelemenin tam karsiligi okunsun.

    Slippage varsayimdir (§8) ve oteleme onu kapsamaz; sifirlanmazsa iki kol
    arasindaki fark komisyon degil komisyon+slippage olurdu.
    """
    return CostModel(
        fees={SYM: Fees(Decimal("0.0005"), Decimal("0.0002"), Decimal(tick))},
        funding={}, slippage_bps=Decimal("0"),
    )


# TP1 (150) doldu, sonra fiyat maliyete **geri gelmeden** 169,9'a kadar yukseldi.
BE_ERKEN = PRIMED_ENTER + [(152, 148), (169.9, 169.5)]
# TP1 doldu, sonra ham maliyet (170) de goruldu: iki kol da ayni mumda kapanir.
BE_TAM = PRIMED_ENTER + [(152, 148), (170.5, 169.0)]


def test_R_EXIT_01_breakeven_varsayilan_ucret_dahildir():
    """`OPEN-35` kapandi: varsayilan seviye ucret dahil maliyet; ham yalnizca acikca."""
    t = kos(BE_TAM, costs=fee_only(), limit_orders=True).trades[0]
    assert t.reason == "BREAKEVEN"
    assert t.exit_price == pytest.approx(Decimal("170") * (1 - BE_ORAN))
    ham = kos(BE_TAM, costs=fee_only(), limit_orders=True, breakeven_fees=False).trades[0]
    assert ham.exit_price == Decimal("170")


def test_R_EXIT_01_breakeven_otelemesi_maliyete_donmeden_tetikler():
    """Oteleme kar tarafinda: fiyat ham maliyete varmadan stop calisir."""
    ham = kos(BE_ERKEN, costs=fee_only(), limit_orders=True,
              breakeven_fees=False).trades[0]
    otel = kos(BE_ERKEN, costs=fee_only(), limit_orders=True,
               breakeven_fees=True).trades[0]
    assert ham.reason == "RUN_END"  # 170 hic gelmedi, pozisyon acik kaldi
    assert otel.reason == "BREAKEVEN"


def test_R_EXIT_01_breakeven_otelemesi_gidis_donus_komisyonunu_karsilar():
    ham = kos(BE_TAM, costs=fee_only(), limit_orders=True,
              breakeven_fees=False).trades[0]
    otel = kos(BE_TAM, costs=fee_only(), limit_orders=True,
               breakeven_fees=True).trades[0]
    assert otel.exit_price == pytest.approx(Decimal("170") * (1 - BE_ORAN))
    # Ham kolda breakeven yarisinin brutu 0; oteleme tam komisyon kadar brut uretir.
    yari = ham.qty / 2
    assert otel.gross - ham.gross == pytest.approx(yari * Decimal("170") * BE_ORAN)
    assert otel.pnl > ham.pnl


def _pozisyon(side: str, avg: str) -> Position:
    return Position(symbol=SYM, zone_id="z", side=side, qty=Decimal("1"),
                    avg_price=Decimal(avg), opened_at=ts(0), last_funding_at=ts(0))


def test_R_EXIT_01_breakeven_otelemesi_her_iki_yonde_de_kar_tarafinadir():
    """SHORT'ta asagi, LONG'da yukari — isaret hatasi stopu piyasanin yanlis
    tarafina koyar, bu yuzden iki yon de dogrudan sinanir. Taker yolu: 10 bps."""
    sz, lz = short_zone(), long_zone()
    bt = Backtest([symbol_data([], sz)], fee_only(), breakeven_fees=True)
    assert bt._breakeven(sz, _pozisyon(SHORT, "170")) == pytest.approx(169.83)
    assert bt._breakeven(lz, _pozisyon(LONG, "130")) == pytest.approx(130.13)


def test_R_EXIT_01_breakeven_otelemesi_ilk_TP_seviyesini_gecmez():
    """Komisyon absurt buyukse oteleme TP1'i gecerdi: "piyasanin ustune stop"."""
    absurt = CostModel(fees={SYM: Fees(Decimal("0.5"), Decimal("0.5"), Decimal("1"))},
                       funding={}, slippage_bps=Decimal("0"))
    sz = short_zone()
    bt = Backtest([symbol_data([], sz)], absurt, breakeven_fees=True)
    assert bt._breakeven(sz, _pozisyon(SHORT, "170")) == sz.tp_050


# --- OPEN-36 · maker dolus stresi: limit emri taker'a duser ------------------
#
# TICK_YOLU: giris 170, TP1 150, nihai TP 100 — uc limit emri, hepsi 1 tick asimla dolar.
# Dusen emir ayni mumda dolar ama taker komisyonu + slippage oder.

def test_OPEN_36_oran_sifirken_hic_emir_dusmez():
    res = kos(TICK_YOLU, costs=real_costs("1"), limit_orders=True)
    assert res.costs.total_slippage == Decimal("0")
    assert all(res.counters[f"taker_{k}"] == 0 for k in ("giris", "tp1", "tp_nihai"))


def test_OPEN_36_oran_birken_uc_emir_de_taker_oder():
    res = kos(TICK_YOLU, costs=real_costs("1"), limit_orders=True, taker_frac=1.0)
    b = res.costs.breakdown
    assert {"slippage_giris", "slippage_tp1", "slippage_tp_nihai"} <= set(b)
    assert all(res.counters[f"taker_{k}"] == 1 for k in ("giris", "tp1", "tp_nihai"))
    # taker 5 bps: giris notional 2.000 -> komisyon 1,00 (maker olsa 0,40)
    assert b["komisyon_giris"] == pytest.approx(Decimal("1.0"), abs=Decimal("0.01"))
    assert res.trades[0].reason == "FINAL_TP"  # zamanlama degismez


def test_OPEN_36_tur_filtresi_yalnizca_secilen_emri_dusurur():
    res = kos(TICK_YOLU, costs=real_costs("1"), limit_orders=True, taker_frac=1.0,
              taker_kinds=frozenset({"tp1"}))
    b = res.costs.breakdown
    assert "slippage_tp1" in b
    assert "slippage_giris" not in b and "slippage_tp_nihai" not in b


def test_OPEN_36_rastgele_dusme_ic_icedir():
    """%10'da dusen her emir %25'te de duser — kollar arasi fark orandan gelir."""
    bt = Backtest([symbol_data([], short_zone())], free_costs())
    ids = [f"z{i}" for i in range(2_000)]

    def dusen(p):
        bt.taker_frac = p
        return {z for z in ids if bt._taker_mi(SYM, z, "giris", Decimal("1"))}

    d10, d25 = dusen(0.10), dusen(0.25)
    assert d10 <= d25
    assert 0.07 < len(d10) / len(ids) < 0.13  # oran kabaca tutuyor


def test_OPEN_36_hacim_kolu_buyuk_emri_dusurur():
    """Emir miktari 1m hacminin `taker_vol_frac` oranini asarsa taker.

    Giris qty = 2.000 / 170 = 11,76. Hacim 100 -> %10 esigi 10 < 11,76 -> duser;
    hacim 1.000 -> esik 100 -> dolar (maker).
    """
    def kos_hacim(v):
        sd = symbol_data(TICK_YOLU, short_zone())
        sd.volume = np.full(len(TICK_YOLU), v, dtype=float)
        return Backtest([sd], real_costs("1"), k=Decimal("0.2"), uyari_blocks_adds=False,
                        limit_orders=True, taker_vol_frac=0.10,
                        taker_kinds=frozenset({"giris"})).run()

    assert kos_hacim(100.0).counters["taker_giris"] == 1
    assert kos_hacim(1_000.0).counters["taker_giris"] == 0


# --- OPEN-37 · post-only giris: dolmazsa islem yok, kovalama yok -------------
#
# Giris satis limiti 170 (tick 1). Uc dolus kriteri yalnizca **giris**e uygulanir;
# TP'ler 1 tick asimla kalir. Kacan giris = fiyat 170'e dokundu ama emir hic dolmadi.

POST_ONLY_1TICK = [(152, 148), (171, 169), (152, 148), (102, 98)]  # 171: 1 tick, 2 degil
POST_ONLY_DONUS = [(152, 148), (172, 160), (152, 148), (102, 98)]  # 171'i gecti, kapanis 166


def test_OPEN_37_tick1_mevcut_davranis_1_tick_asimla_dolar():
    res = kos(POST_ONLY_1TICK, costs=free_costs("1"), limit_orders=True)
    assert res.counters["entries"] == 1 and res.counters["kacan_giris"] == 0


def test_OPEN_37_tick2_1_tick_asimi_doldurmaz_ve_kacan_sayilir():
    res = kos(POST_ONLY_1TICK, costs=free_costs("1"), limit_orders=True, entry_fill="tick2")
    assert res.counters["entries"] == 0 and not res.trades
    assert res.counters["kacan_giris"] == 1  # dokundu, dolmadi, zone bitti
    assert res.counters["unfilled"] == 0     # "hic dokunulmadi" degil


def test_OPEN_37_kapanis_ayni_mumda_geri_donen_mum_doldurmaz():
    res = kos(POST_ONLY_DONUS, costs=free_costs("1"), limit_orders=True, entry_fill="kapanis")
    assert res.counters["entries"] == 0 and res.counters["kacan_giris"] == 1
    # ayni mum tick1'de dolar
    assert kos(POST_ONLY_DONUS, costs=free_costs("1"), limit_orders=True).counters["entries"] == 1


def test_OPEN_37_kapanis_seviyenin_otesinde_kalan_mum_doldurur():
    # TICK_YOLU'nun (172, 168) mumu: kapanis 170 = seviye, geri donmedi
    res = kos(TICK_YOLU, costs=free_costs("1"), limit_orders=True, entry_fill="kapanis")
    assert res.counters["entries"] == 1 and res.counters["kacan_giris"] == 0
    assert res.trades[0].entry_price == Decimal("170")


def test_OPEN_37_gec_dolan_giris_kacan_sayilmaz():
    """Kovalama yok ama emir yerinde bekler: sonraki mumda dolarsa islem acilir."""
    yol = [(152, 148), (171, 169), (173, 167), (152, 148), (102, 98)]
    res = kos(yol, costs=free_costs("1"), limit_orders=True, entry_fill="tick2")
    assert res.counters["entries"] == 1 and res.counters["kacan_giris"] == 0


def test_OPEN_37_bilinmeyen_kriter_reddedilir():
    with pytest.raises(ValueError):
        kos(TICK_YOLU, costs=free_costs("1"), limit_orders=True, entry_fill="yok")
