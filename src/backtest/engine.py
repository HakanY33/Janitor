"""Uçtan uca backtest motoru: zone → giriş → ekleme → çıkış → risk.

Spec: R-ENTRY-02/03/05, R-ADD-01/02/03/04, R-EXIT-01/02, R-RISK-01/02/03/05,
R-ZONE-04/05/09, §8 (intrabar belirsizliği, maliyet modeli), §9 (zorunlu sayaçlar).

**Neden kendi motoru.** CLAUDE.md "mevcut kütüphane değerlendirilmeden sıfırdan motor
yazma" diyor; değerlendirme yapıldı ve kayda geçiyor:

| Kütüphane | Neden yetmiyor |
|---|---|
| `backtesting.py` | Tek enstrüman; portföy seviyesinde cross marjin ve likidasyon yok |
| `vectorbt` | Vektörel; buradaki mantık yol bağımlı (ekleme, durum makinesi, ortak teminat) |
| `backtrader` | Çok enstrüman var ama perpetual funding, cross likidasyon ve sembol başına maks kaldıraç yok; broker'ı baştan yazmak gerekirdi |
| `nautilus_trader` | Marjin modeli var ama ağır bir bağımlılık; OTE/zone mantığı yine bizde kalırdı |

Ortak eksik, bu koşunun **ölçmek için var olduğu** şey: 20 korelasyonlu sembolde
cross marjin portföy likidasyonu (R-RISK-05, §9). Hiçbiri bunu vermiyor, hepsinde
pozisyon/risk motorunu yine biz yazardık. Bu yüzden minimal bir olay döngüsü yazıldı;
kütüphane eklenmedi (hiçbiri kurulu da değil).

**Zaman modeli (R-ZONE-09).** Geometri ve gösterge tespiti 30m; durum geçişleri 1m.
Döngü **küresel** bir 1m zaman çizgisinde ilerler, sembol sembol değil — cross marjinde
equity tüm sembolleri birbirine bağlar ve likidasyon portföy seviyesinde olur.

**Intrabar belirsizliği (§8).** Bir 1m mumunda hem TP hem stop seviyesine dokunulmuşsa
işlem `ambiguous` işaretlenir, **stop önce** varsayılır ve ayrı sayaçta raporlanır.
`Zone.on_bar` zaten aynı kötümser sırayı uygular (öldürme ilerlemeye baskındır).

**Spec'te tanımsız kalan yerler** — en muhafazakâr yorum seçildi, raporda yazılı:

1. `ADD-REJECT-A` "öngörülen dönüş noktası" sayısallaştırılmamış. Burada dönüş noktası
   modelin kendi ilk hedefi olan `0.50` alınır: ekleme sonrası maliyet, `0.50`'ye dönüşte
   maliyetler düşüldükten sonra kâr bırakmıyorsa ekleme reddedilir.
2. `R-ADD-03` çarpan seçimi: dört çarpan (1-1, 1-3, 1-5, 1-10) arasından, ortalama
   maliyeti `0.79` seviyesinin ötesine — nihai stopun (`1`) tarafına — çeken **en
   küçük** olanı seçilir; hiçbiri çekemiyorsa ekleme yapılmaz. Spec'teki "fiyatın en
   fazla gideceği tahmin edilen nokta" sayısallaşmadığı için modelin kendi
   geometrisindeki karşılığı alındı (`OPEN-27` daraltıldı, kapanmadı).
3. `R-ENTRY-02` (3) "gösterge yoksa 0.70 teması geçerli giriştir" dediği için OB/FVG
   **girişi kapılamaz**. R-ENTRY-05 süzgeçleri bu yüzden işlem sayısını azaltmaz,
   girişin *niteliğini* etiketler; sayaçlar ikisini ayrı raporlar.
4. `R-ADD-04` küçültmesinin hedefi: "K tabanı" `K × equity` notional olarak alınır
   ve equity küçültme anında ölçülür (bkz. `_reduce_to_base`). Küçültme bir çıkış
   değildir; kalan kısım stop `1` / TP `0.50` / TP `0` ile devam eder ve raporda
   ayrı sayılır.
5. **Sembol başına tek pozisyon.** `R-ZONE-06` pozisyon sayısına sınır koymuyor, ama
   aynı sembolde aynı anda iki zone TOUCHED olabiliyor. Borsada tek yönlü modda bunlar
   zaten tek pozisyonda netleşirdi; ikinci zone sessizce atlanır. Bu bir spec kuralı
   değil, modelleme tercihidir ve sayaçta `entry_candidates > entries` farkının bir
   kısmını açıklar.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from src.backtest.costs import CostModel, build_cost_model
from src.backtest.loader import (  # noqa: F401  (geriye donuk yeniden disari verme)
    DETECT_TF,
    STATE_TF,
    TRAIN_FRAC,
    SymbolData,
    load_symbol,
    reset_for_rerun,
)
from src.backtest.portfolio import LONG, SHORT, Portfolio, Position
from src.execution.adapter import ENTRY_FILLS, SimAdapter, emir_miktari  # noqa: F401  (ENTRY_FILLS yeniden disari)
from src.strategy.entry import band, eligible_fvgs, eligible_obs
from src.zones.model import STATE_BAR, TERMINAL, Zone, ZoneState as S

K_STANDARD = Decimal("1.0")  # R-ENTRY-03 · standart notional katsayısı
NOTIONAL_CAP = Decimal("10")  # R-RISK-01 · toplam notional tavanı (× equity)
TP1_FRACTION = Decimal("0.5")  # R-EXIT-01 · ilk TP'de kapatılan oran
ADD_MULTIPLIERS = (Decimal("1"), Decimal("3"), Decimal("5"), Decimal("10"))
"""R-ADD-03 · ekleme çarpanları (1-1, 1-3, 1-5, 1-10), mevcut pozisyonun katları.

Seçim kuralı: ortalama maliyeti **zone'un 1 seviyesine doğru, 0.79'un ötesine**
çeken en küçük çarpan. Hiçbiri çekemiyorsa ekleme yapılmaz.

`OPEN-27` bu kuralla kapanmıyor, daraltılıyor: spec "fiyatın en fazla gideceği
tahmin edilen nokta" diyor ve o nokta sayısallaştırılmadı. Burada modelin kendi
geometrisindeki en yakın karşılığı alınır — giriş bandının üst ucu (`0.79`), yani
maliyet bandın ötesine, nihai stopun (`1`) tarafına çekilmiş olur. Daha katı bir
okuma (maliyet `1`'i geçsin) ağırlıklı ortalamayla hiçbir çarpanda erişilemez;
daha gevşeği (maliyet `1`'in altında kalsın) her zaman sağlanır ve kural ölür."""
FUNDING_INTERVAL = pd.Timedelta("8h")
"""Funding egrisi olmayan sembolde tahsilat araligi; egri varsa onun `interval`'i
(`OPEN-59`, sembol basina borsadan). Eskiden funding yalnizca cikista tek seferde isleniyordu;
`OPEN-29` funding tavani kurali birikmis maliyeti **pozisyon acikken** okumak zorunda
oldugu icin tahsilat gercek takvimine tasindi. Toplam maliyet ayni, zamanlamasi dogru:
funding 8 saatte bir nakit akisidir ve equity'yi o anda etkiler."""
_FUNDING_NP = np.timedelta64(FUNDING_INTERVAL.value, "ns")
_KOVA_NS = pd.Timedelta(DETECT_TF).value  # gösterge önbelleği kovası (`_gosterge`)

TERMINATE_NONE = "none"
TERMINATE_TIME = "time"
TERMINATE_STRUCTURE = "structure"
TERMINATE_FUNDING = "funding"
TERMINATION_RULES = (TERMINATE_NONE, TERMINATE_TIME, TERMINATE_STRUCTURE, TERMINATE_FUNDING)
"""`OPEN-29` · pozisyon sonlandirma kurali adaylari. Spec'te **yok**: R-EXIT-03 "zaman
siniri yok" diyor. Bu yuzden hicbiri varsayilan degildir; `none` spec'in yazili halidir
ve digerleri yalnizca olculmek icin vardir (CLAUDE.md: spec'te olmayan davranis
uydurulmaz, OPEN olarak isaretlenir)."""

MAX_HOLD_BARS = 21 * 1440  # `time` adayi · 21 gun (R-EXIT-03'un "3 haftaya kadar gozlem")
FUNDING_CAP_RATIO = Decimal("0.10")  # `funding` adayi · birikmis funding / potansiyel kar

TP_REASONS = frozenset({"TP1", "FINAL_TP"})
"""R-EXIT-01/02 · kar alma kapanislari. `tp_market` kolunda bunlar piyasa emridir."""

MAKER_REASONS = frozenset({"TP1", "FINAL_TP", "REDUCE"})
"""Limit emri kolunda (`limit_orders`) maker komisyonu ödeyen kapanışlar.

Geri kalan her kapanış piyasa emridir ve taker + slippage öder: nihai stop, maliyete
çekilmiş stop (BREAKEVEN), likidasyon, R-RISK-05 küçültmesi, koşu sonu ve OPEN-29
sonlandırması. Hepsi "fiyat geldi, hemen çık" emridir; limit koyup beklenmez."""

KALEM = {"TP1": "tp1", "FINAL_TP": "tp_nihai", "REDUCE": "kucultme",
         "DELEVERAGE": "delev", "STOP": "stop", "BREAKEVEN": "breakeven"}
"""Kapanış nedeni → maliyet defteri kalemi. Listede olmayan (RUN_END, LIQUIDATION,
sonlandırma) `cikis` kalemine düşer. Kalemler ayrı çünkü limit kolunda aynı `cikis`
içinde maker (TP) ve taker (stop) komisyonu karışıyordu."""

MAX_ADDS: int | None = 0
"""v1 varsayilan yapilandirmasi · **ekleme kapali** (spec §3 "v1'de ekleme kapalidir").
`R-ADD-*` kurallari silinmedi; `None` verilince aynen calisirlar. Gerekce:
`docs/measurements/f_kollari.md` — ekleme sonucu degistirmiyor, kaybedeni buyutuyor.
Kurulus aninda okunur (`STOP_LOSS_CAP` gibi): testler ekleme yolunu sinamak icin
sabiti gecici olarak `None` yapar."""

_VARSAYILAN = object()

SURTUNME_KAT = Decimal("3")
"""R-ENTRY-06 · girişten TP1'e mesafe, gidiş-dönüş maliyetinin bu katından küçükse giriş
yok (kullanıcı kuralı 2026-10-02: "tatmin etmeyen hareket için komisyon ödenmez")."""

STOP_LOSS_CAP = Decimal("0.03")
"""`ADD-REJECT-E` · pozisyonun nihai stopa giderse kaybedeceği tutarın equity'ye oranı
tavanı (`L`). `0` = kural kapalı.

`R-RISK-01` **notional** tavanıdır ve ekleme boyutunu bağlamaz: çarpan merdiveni
(`R-ADD-03`) çarpımsal olduğu için iki ekleme girişin 24 katına çıkabiliyor ve equity
pozisyonla birlikte düştüğü için `10 × equity` tavanı hiç değmiyor. Ölçümde tek bir
pozisyon (ORDI) hesabın toplam kaybından fazlasını taşıdı.
`ADD-REJECT-E` tavanı *notional*'a değil **stopta realize olacak kayba** koyar.

`L = %3` ölçümle seçildi (`docs/measurements/add_reject_e.md`). Seçim **net PnL'e
göre değil**: net üç `L` değerinde ayırt edilemiyor (−176 / −727 / −186, sıralama
monoton bile değil). Seçim, kuralın var olma nedeni olan **kuyruk riskine** göre
yapıldı — maks drawdown `L`'de monoton: kapalı %63,6 → %10'da %27,6 → %5'te %26,5 →
%3'te %24,1, ve ×1.5 maliyet stresinde de monoton kalıyor (%30,7 vs %39,8).

`0` = kural kapalı. Test paketi `tests/conftest.py` ile bunu geçici olarak sıfırlar:
testlerin sentetik zone geometrisi (leg, fiyatın %59'u) hiçbir makul `L` değerinde
pozisyon açtırmaz."""

T_RAHAT = Decimal("0.50")  # R-RISK-05 · başlangıç değeri (OPEN-17)
T_KRITIK = Decimal("0.15")
DAILY_LOSS_LIMIT = Decimal("0.10")  # R-RISK-03 · OPEN-16 başlangıç %10


@dataclass(frozen=True)
class EntryRule:
    """Giriş seviyesi varyantı. `R-ENTRY-02`'nin tetiğini değiştirir, kuralı değil.

    Zone'un `TOUCHED`'a geçmesi (0.70 teması) **her varyantta ön koşuldur** — bu
    `R-ZONE-04`'ün durum makinesidir ve dokunulmaz. Varyant yalnızca bekleyen giriş
    emrinin fiyatını değiştirir (`OPEN-41`: emir `PRIMED` kapanışında konur).

    | kind | emir fiyatı |
    |---|---|
    | `level` | `ratio` fib seviyesi |
    | `indicator` | bantta uygun OB varsa onun **ilk dokunulan** kenarı, yoksa `ratio` (FVG v0.8'den beri fiyat belirlemez) |

    Eski `window` varyantı ("temastan sonra N mum en iyi fiyatı izle") temasla kurulduğu
    için bekleyen emir modelinde tanımsızdır; `OPEN-41` ile silindi.
    """

    name: str
    kind: str  # level | indicator
    ratio: Decimal = Decimal("0.70")  # level ve indicator yedeği için fib oranı


ENTRY_070 = EntryRule("0.70 ilk temas", "level", Decimal("0.70"))
ENTRY_075 = EntryRule("0.75 teması", "level", Decimal("0.75"))
ENTRY_079 = EntryRule("0.79 teması", "level", Decimal("0.79"))
ENTRY_IND = EntryRule("OB varsa oradan, yoksa 0.79", "indicator", Decimal("0.79"))

ENTRY_VARIANTS = (ENTRY_070, ENTRY_075, ENTRY_079, ENTRY_IND)


@dataclass
class Trade:
    """Kapanmış bir işlem. `reason` çıkışın hangi kuraldan geldiğini söyler."""

    symbol: str
    zone_id: str
    side: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: Decimal
    exit_price: Decimal
    qty: Decimal
    pnl: Decimal  # komisyon ve funding düşülmüş
    gross: Decimal
    fees: Decimal
    funding: Decimal
    reason: str  # FINAL_TP | STOP | BREAKEVEN | LIQUIDATION | DELEVERAGE | RUN_END
    adds: int
    ambiguous: bool
    had_ob: bool  # R-ENTRY-05 · girişte uygun OB var mıydı
    had_fvg: bool
    bars_held: int
    reached_tp1: bool = False  # R-EXIT-01 · 0.50'ye ulaşıp kısmi kâr alındı mı
    reduces: int = 0  # R-ADD-04 · kaç kez K tabanına indirildi (0 = hiç küçültülmedi)
    bars_after_reduce: int = 0  # ilk küçültmeden çıkışa kadar geçen 1m mum
    band_pos: float = 0.0  # dolumun bant içi konumu: 0.0 = 0.70, 1.0 = 0.79
    mae_leg: float = 0.0       # maks aleyhte sapma, leg boyunun orani
    mae_equity: float = 0.0    # maks aleyhte sapma, equity yuzdesi
    min_liq_dist: float | None = None  # islem boyunca en dusuk likidasyon mesafesi
    entry_qty: Decimal = Decimal("0")  # ilk giris miktari; `qty` tepe miktardir
    # `R-ZONE-08` bolunmus ic validasyonun aday ozellikleri — karar aninda bilinen
    # degerler (CLAUDE.md #3). Hicbiri motorun kararina girmez, yalnizca raporlanir.
    entry_bias: str = "NONE"  # R-ZONE-10 · giriste bilinen 4h yapisal yon
    touch_count: int = 0      # R-ZONE-01 · dolum anindaki bant temasi sayisi
    leg_pct: float = 0.0      # |capa_1 - capa_0| / capa_0 — leg buyuklugu


@dataclass
class Result:
    trades: list[Trade]
    portfolio: Portfolio
    costs: CostModel
    equity_curve: list[tuple[datetime, float]]
    counters: dict = field(default_factory=dict)
    deleverage_realized: Decimal = Decimal("0")  # R-RISK-05 kucultmelerinde realize PnL


class Backtest:
    """Küresel 1m zaman çizgisinde ilerleyen olay döngüsü."""

    def __init__(
        self,
        data: list[SymbolData],
        costs: CostModel,
        start_balance: Decimal = Decimal("10000"),
        k: Decimal = K_STANDARD,
        mmr: Decimal = Decimal("0.005"),
        t_rahat: Decimal = T_RAHAT,
        t_kritik: Decimal = T_KRITIK,
        uyari_blocks_adds: bool = True,
        entry_rule: EntryRule = ENTRY_070,
        progress_every: int = 0,
        terminate: str = TERMINATE_NONE,
        max_hold_bars: int = MAX_HOLD_BARS,
        funding_cap_ratio: Decimal = FUNDING_CAP_RATIO,
        require_indicator: bool = False,
        max_adds=_VARSAYILAN,
        reduce_once: bool = False,
        limit_orders: bool = False,
        tp_offset: float = 0.0,
        tp_market: bool = False,
        stop_loss_cap: Decimal | None = None,
        breakeven_fees: bool = True,
        min_leg_pct: float = 0.0,
        taker_frac: float = 0.0,
        taker_vol_frac: float = 0.0,
        taker_kinds: frozenset[str] = frozenset({"giris", "tp1", "tp_nihai"}),
        entry_fill: str = "tick1",
    ):
        if terminate not in TERMINATION_RULES:
            raise ValueError(f"bilinmeyen sonlandirma kurali: {terminate}")
        self.terminate = terminate
        self.max_hold_bars = max_hold_bars
        self.funding_cap_ratio = funding_cap_ratio
        # Koşu gözlemsiz bırakılmaz: `progress_every > 0` ise her N mumda bir satır
        # `stderr`'e düşer (ilerleme, açık pozisyon, ekleme, küçültme, ETA). Rapor
        # metnine karışmasın diye `stdout` değil `stderr`.
        self.progress_every = progress_every
        self._t0 = time.time()
        self.data = {d.symbol: d for d in data}
        self.costs = costs
        self.k = k
        self.t_rahat = t_rahat  # R-RISK-05 · ızgara süpürmesinde değişir
        self.t_kritik = t_kritik
        # R-RISK-05 UYARI'nın eklemeye etkisi. `True` spec'in yazılı hâlidir
        # ("ekleme reddedilir · ADD-REJECT-D"). `False` süpürme varyantıdır: UYARI
        # yalnızca **yeni zone'a giriş** açmayı durdurur, mevcut pozisyona ekleme
        # R-RISK-01 ve R-ADD-02'nin diğer kurallarına tabi olarak sürer.
        # KRITIK her iki hâlde de her şeyi durdurur ve küçültmeyi uygular.
        self.uyari_blocks_adds = uyari_blocks_adds
        # `R-ENTRY-02` (3) kapali varyanti — **spec'ten sapar**, olcmek icindir.
        # Spec "gosterge yoksa 0.70 temasi gecerli giristir" diyor, yani giris
        # kapilanamaz. `True` yapildiginda yalnizca bantta uygun OB bulunan (v0.8; eskiden OB veya FVG)
        # zone'lara girilir; teshis kosusu hacmin %82'sinin ciplak temas oldugunu ve
        # o dalin net negatif oldugunu gosterdigi icin olculuyor (OPEN-30 adayi).
        self.require_indicator = require_indicator
        # --- salinim ve emir tipi kollari (spec'te yok, olcmek icin) ---------
        # `max_adds`: pozisyon omru boyunca en fazla bu kadar ekleme; `None` = sinir
        # yok, `0` = ekleme hic yok (F1 kolu). R-ADD-01/03 ekleme sayisina sinir
        # koymuyor; salinimin maliyeti olculdugu icin var.
        self.max_adds = MAX_ADDS if max_adds is _VARSAYILAN else max_adds
        # F2 kolu · asgari leg esigi: `|capa_1 - capa_0| / capa_0` bu degerin **altinda
        # veya esit** olan zone giris uretmez. Spec'te yok, olcmek icin; `0` = kapali.
        # Leg geometrisi zone tespitinde sabitlenir — karar aninda bilinir (CLAUDE.md #3).
        self.min_leg_pct = min_leg_pct
        self._vol: dict[str, float] = {}
        self._acilis: dict[str, float] = {}  # sembol -> bu 1m mumun açılışı
        # `reduce_once`: R-ADD-04 kucultmesi pozisyon basina bir kez tetiklenir ve
        # sonraki eklemeler tetigi **yeniden kurmaz**.
        self.reduce_once = reduce_once
        # `limit_orders`: giris, TP1, nihai TP, ekleme ve kucultme limit emridir —
        # maker komisyonu, slippage yok, ve seviye 1 tick gecilmeden dolmus sayilmaz.
        # Stop ve diger zorunlu cikislar piyasa emri kalir (bkz. MAKER_REASONS).
        self.limit_orders = limit_orders
        # `tp_offset`: TP'ler seviyenin kac leg **onune** konur (R-EXIT-01/02, orijinal
        # kural "donusun hemen altina"). `tp_market`: TP'ler limit degil, temasla
        # tetiklenen piyasa emridir — taker + slippage oder ve 1 tick asim aranmaz.
        # Giris, ekleme, kucultme ve stop bu iki bayraktan etkilenmez.
        self.tp_offset = tp_offset
        self.tp_market = tp_market
        # ADD-REJECT-E · pozisyon seviyesinde stop kaybi tavani (`L`). `0` = kapali.
        # Varsayilan **kurulus aninda** modul sabitinden okunur (imzada baglanmaz):
        # olcum betikleri degeri acikca verir, testler sabiti gecici olarak sifirlar.
        self.stop_loss_cap = STOP_LOSS_CAP if stop_loss_cap is None else stop_loss_cap
        # R-EXIT-01 · "stop maliyete cekilir" ham ortalama maliyet mi, yoksa **islem
        # ucreti dahil** maliyet mi? `OPEN-35` kapandi: ucret dahil. Kural ilk TP'nin
        # alt sinirini "islem ucretlerini karsilayacak kadar" diye veriyor; ham
        # maliyette kapanan her pozisyon gidis-donus komisyonu kadar zarardir.
        # `True` (varsayilan) breakeven'i o kadar kar tarafina oteler; `False` ham
        # maliyet — yalnizca eski olcumleri yeniden uretmek icin.
        self.breakeven_fees = breakeven_fees
        self._maker_reasons = MAKER_REASONS - TP_REASONS if tp_market else MAKER_REASONS
        # Doluş kararı `ExecutionAdapter` arkasında (docs/LIVE.md Ö2). Backtest'in
        # modeli `SimAdapter`; TP 1 tick kuralı zone'a oradan verilir.
        self.exec = SimAdapter(
            {s_: float(costs.fees[s_].tick) for s_ in self.data} if limit_orders else {},
            limit_orders=limit_orders, entry_fill=entry_fill, taker_frac=taker_frac,
            taker_vol_frac=taker_vol_frac, taker_kinds=taker_kinds, tp_market=tp_market,
        )
        self.tp_offset = tp_offset
        for sd_ in self.data.values():
            for z_ in sd_.zones:
                self._hazirla(z_, sd_.symbol)
        self.entry_rule = entry_rule
        if entry_rule.kind not in ("level", "indicator"):
            raise ValueError(f"bilinmeyen giris varyanti: {entry_rule.kind}")
        # OPEN-41 · bekleyen giriş emri defteri (sayaçlar için; emrin kendisi `order_for`).
        self._armed: set[str] = set()  # emri en az bir kez aktif olan zone
        self._red: set[tuple[str, str]] = set()  # (zone, neden) — neden başına bir kez sayılır
        self._dokundu: set[str] = set()  # emir aktifken fiyata dokunuldu, dolmadı
        self._hedefe_dokunan: set[str] = set()  # emir fiyatına ulaşıldı (emir olsun olmasın)
        self._girilen: set[str] = set()
        self._temas: set[str] = set()  # TOUCHED'a geçen zone
        self._gosterge_onbellek: dict[str, tuple] = {}  # zone -> (30m kovası, ob, fvg, hedef)
        self._bant_onbellek: dict[str, tuple] = {}  # zone -> ((n_ob, n_fvg), bant OB, bant FVG)
        self._snap: dict | None = None  # son 1m kapanışının portföy görüntüsü (`_kapanis`)
        self.log = None  # karar logu yazıcısı (callable); backtest'te yok
        self.kill: str | None = None  # R-KILL-01 aktifse nedeni; toparlanma scripts/paper.py (spec §6)
        self.pf = Portfolio(balance=start_balance, start_balance=start_balance, mmr=mmr)
        self.pf.peak_equity_f = float(start_balance)
        self.trades: list[Trade] = []
        self.equity_curve: list[tuple[datetime, float]] = []
        self.marks: dict[str, float] = {}
        self.entry_ctx: dict[str, dict] = {}  # zone_id -> giriş bağlamı
        self.used_add_obs: set[str] = set()
        self.deleverage_realized = Decimal("0")
        self.counters = {
            "entry_candidates": 0, "entries": 0, "entries_with_ob": 0,
            "no_indicator_skipped": 0, "leg_skipped": 0,
            "entries_with_fvg": 0, "rejected_risk01": 0, "rejected_risk05": 0,
            "rejected_risk03": 0, "adds": 0, "add_reject_a": 0, "add_reject_b": 0,
            "add_reject_c": 0, "add_reject_d": 0, "ambiguous_bars": 0,
            "zones_total": 0, "zones_primed": 0, "zones_touched": 0,
            "liquidations": 0, "kill_wins": 0, "skipped_progress": 0,
            "deleverage_events": 0, "risk01_binding_bars": 0,
            "armed": 0, "unfilled": 0, "add_reject_mult": 0, "reduce_events": 0,
            "adds_by_mult": {},
            "bars_with_position": 0, "bars_total": 0,
            "terminated": 0,  # OPEN-29 · sonlandirma kuraliyla kapanan pozisyon
            "add_reject_cap": 0,  # B kolu · ekleme tavani
            "add_reject_e": 0,  # ADD-REJECT-E · stop kaybi tavani (ekleme)
            "entry_reject_e": 0,  # ADD-REJECT-E · ayni tavan ilk girise uygulandi
            "rejected_surtunme": 0,  # R-ENTRY-06 · TP1 mesafesi < 3 × gidiş-dönüş maliyeti
            # Limit kolu · seviyeye dokunulup 1 tick gecilmedigi icin dolmayan emirler.
            # `unfilled` (giris hedefine hic dokunulmadi) bundan ayridir.
            "limit_miss_giris": 0, "limit_miss_ekleme": 0,
            "limit_miss_kucultme": 0, "limit_miss_tp": 0,
            # OPEN-36 · taker'a dusen limit emri, tur basina
            "taker_giris": 0, "taker_tp1": 0, "taker_tp_nihai": 0, "taker_kucultme": 0,
            # OPEN-37 · giris hedefine dokunuldu ama emir zone bitene kadar dolmadi.
            # `unfilled` artik yalnizca hedefe **hic** dokunulmayanlardir.
            "kacan_giris": 0,
            # OPEN-41 · zone'u `1` çapasıyla öldüren mumda bekleyen emir doldu, aynı mumda stop
            "kill_bar_fills": 0,
            "rejected_kill": 0,  # R-KILL-01 açıkken emir fiyatına ulaşan zone
            # Borsa kısıtı (adım, asgari miktar/tutar) karşılanmadı: giriş / kısmi kapanış
            "rejected_min_order": 0, "rejected_min_close": 0,
        }
        self._day_start_equity = float(start_balance)
        self._day_blocked = False

    # --- yardimcilar ---------------------------------------------------------

    def _taker_mi(self, symbol: str, zone_id: str, tur: str, qty: Decimal) -> bool:
        """OPEN-36 · bu limit emri taker'a dustu mu (`SimAdapter.taker`). Duserse sayac."""
        dus = self.exec.taker(symbol, zone_id, tur, qty, self._vol.get(symbol, 0.0))
        if dus:
            self.counters[f"taker_{tur}"] += 1
        return dus

    def _stop_loss(self, z: Zone, qty: Decimal, avg: Decimal) -> Decimal:
        """`ADD-REJECT-E` · pozisyon nihai stopa (`1`) giderse realize olacak kayıp.

        Spec formülü `toplam notional × |stop − maliyet| / maliyet`; notional
        `qty × maliyet` olduğu için `qty × |stop − maliyet|`e sadeleşir. Sadeleşmiş
        hâli kullanılır — bölme artığı yok ve ölçü doğrudan paradır.
        """
        return qty * abs(Decimal(str(z.anchor_1_price)) - avg)

    def _breakeven(self, z: Zone, pos: Position) -> float:
        """R-EXIT-01 · ilk TP sonrası maliyete çekilen stop seviyesi.

        `OPEN-35` kapandı: "maliyet" işlem ücreti dahildir. `breakeven_fees`
        kapalıyken **ham ortalama maliyet** (eski ölçümler). Açıkken (varsayılan) seviye, kalan miktarın gidiş-dönüş **komisyonunu** karşılayacak kadar
        kâr tarafına ötelenir: giriş oranı (limit kolunda maker, aksi hâlde taker) +
        çıkış oranı (breakeven bir piyasa emridir, daima taker). `qty × maliyet × oran`
        tam bu ötelemeyle karşılanır.

        Slippage **kapsam dışıdır**: ölçülmüş bir borsa oranı değil, varsayımdır (§8).
        Öteleme yalnızca yayınlanan komisyonu karşılar; artan sürtünme raporda ayrı.

        Öteleme ilk TP seviyesini geçemez — geçerse "piyasanın üstüne stop" olurdu.
        """
        be = float(pos.avg_price)
        if not self.breakeven_fees:
            return be
        f = self.costs.fees[pos.symbol]
        rt = float((f.maker if self.limit_orders else f.taker) + f.taker)
        if pos.side == LONG:
            return min(be * (1 + rt), z.tp_050)
        return max(be * (1 - rt), z.tp_050)

    def _risk05_zone(self) -> str:
        """R-RISK-05 · RAHAT / UYARI / KRITIK."""
        d = self.pf.liq_distance_f(self.marks)
        if d is None:
            return "RAHAT"
        if d <= float(self.t_kritik):
            return "KRITIK"
        return "UYARI" if d <= float(self.t_rahat) else "RAHAT"

    def _deleverage(self, ts: pd.Timestamp) -> None:
        """R-RISK-05 KRITIK · "pozisyon küçültülür" + `R-KILL-04`.

        **Küçültme miktarı spec'te yok.** En muhafazakâr ve sonlanan yorum seçildi:
        KRITIK'te kalındığı her mumda **her pozisyon yarıya** indirilir. Tekrarlandıkça
        kaldıraç hızla düşer ve bölgeden çıkılır; hedef notional hesaplamak eşiğin tam
        üstüne oturup mum başına salınım üretiyordu.

        Bu olmadan `T_kritik` ölü bir parametredir: UYARI de KRITIK de yalnızca yeni
        pozisyonu ve eklemeyi engeller, ikisi arasında davranış farkı kalmaz.
        """
        self.counters["deleverage_events"] += 1
        for symbol in list(self.pf.positions):
            pos = self.pf.positions[symbol]
            z = self._zone_of(pos)
            if z is None:
                continue
            self._close(z, pos, self.marks[symbol], ts, "DELEVERAGE", fraction=Decimal("0.5"))
            if symbol not in self.pf.positions and z.state not in TERMINAL:
                z.transition(S.CLOSED, ts)

    def _daily_loss_hit(self) -> bool:
        """R-RISK-03 · gün içi zarar eşiği aşıldıysa yeni pozisyon açılmaz."""
        if self._day_blocked:
            return True
        if self._day_start_equity <= 0:
            return False
        change = (self.pf.equity_f(self.marks) - self._day_start_equity) / self._day_start_equity
        if change <= -float(DAILY_LOSS_LIMIT):
            self._day_blocked = True
        return self._day_blocked

    # --- giris ---------------------------------------------------------------

    def _fib(self, z: Zone, ratio: Decimal) -> float:
        """Çapalardan fib seviyesi. R-ZONE-03 · lineer."""
        return z.anchor_0_price + float(ratio) * (z.anchor_1_price - z.anchor_0_price)

    def _band_pos(self, z: Zone, price: float) -> float:
        """Fiyatın bant içi konumu: 0.0 = 0.70 · 1.0 = 0.79."""
        a, b = self._fib(z, Decimal("0.70")), self._fib(z, Decimal("0.79"))
        return (price - a) / (b - a) if b != a else 0.0

    def _gosterge(self, z: Zone, sd: SymbolData, at: pd.Timestamp) -> tuple[bool, bool, float]:
        """`at`'te bantta uygun OB / FVG var mı ve emir fiyatı (R-ENTRY-02, R-ENTRY-05).

        Gösterge damgalarının hepsi (`known_at`, `mitigated_at`, `filled_at`) 30m
        kapanışıdır: sonuç bir 30m kovası içinde değişmez. Kova başına bir kez hesaplanır —
        yaklaşım değil, birebir aynı sonuç. ponytail: hizasız damga gelirse önbellek yanılır;
        `known_at` her zaman TF kapanışı olduğu sürece geçerli. **Canlıda şart:** kovanın
        30m kapanışındaki artımlı tespit, o kovadaki ilk değerlendirmeden önce bitmeli
        (`PaperCore.dakika` sırası; ters sıra eski listeyi önbelleğe alır — `test_paper`).
        """
        kova = at.value // _KOVA_NS
        c = self._gosterge_onbellek.get(z.zone_id)
        if c is not None and c[0] == kova:
            return c[1:]
        obs, fvgs = self._bantta(z, sd)
        had_ob = bool(eligible_obs(obs, z, at))
        had_fvg = bool(eligible_fvgs(fvgs, z, at))
        sonuc = (had_ob, had_fvg, self._hedef(z, sd, at))
        self._gosterge_onbellek[z.zone_id] = (kova, *sonuc)
        return sonuc

    def _bantta(self, z: Zone, sd: SymbolData) -> tuple[list, list]:
        """Giriş bandını kesen OB/FVG'ler (§0.1 kesişim). Geometri sabit: zone başına bir kez;
        liste büyürse (canlıda yeni tespit) yeniden. Zaman koşulları `eligible_*`'da kalır."""
        anahtar = (len(sd.obs), len(sd.fvgs))
        c = self._bant_onbellek.get(z.zone_id)
        if c is None or c[0] != anahtar:
            lo, hi = band(z)
            c = (anahtar, [o for o in sd.obs if o.bottom <= hi and o.top >= lo],
                 [f for f in sd.fvgs if f.bottom <= hi and f.top >= lo])
            self._bant_onbellek[z.zone_id] = c
        return c[1], c[2]

    def _hedef(self, z: Zone, sd: SymbolData, at: pd.Timestamp) -> float:
        """Giriş emrinin fiyatı, `at`'te bilinen bilgiyle (varyanta göre)."""
        r = self.entry_rule
        if r.kind == "level":
            return self._fib(z, r.ratio)
        # indicator · R-ENTRY-02: önce OB, yoksa çıplak seviye. FVG fiyat belirlemez (OPEN-65).
        # Kenar seçimi: fiyatın **ilk dokunacağı** kenar — SHORT bandı aşağıdan
        # yukarı, LONG yukarıdan aşağı kat eder. Bu hem nedenseldir hem de
        # göstergenin kötü tarafıdır (short için düşük, long için yüksek).
        short = z.bias == "SHORT"
        band_low, band_high = sorted((self._fib(z, Decimal("0.70")),
                                      self._fib(z, Decimal("0.79"))))
        obs, _ = self._bantta(z, sd)
        adaylar = [(o.bottom, o.top) for o in eligible_obs(obs, z, at)]
        if not adaylar:
            return self._fib(z, r.ratio)
        kenarlar = [b for b, _ in adaylar] if short else [t for _, t in adaylar]
        hedef = min(kenarlar) if short else max(kenarlar)
        return min(max(hedef, band_low), band_high)  # bant dışına taşma

    def order_for(self, z: Zone, sd: SymbolData, at: pd.Timestamp) -> tuple[dict | None, str | None]:
        """R-ENTRY-02 · `OPEN-41` · `at` kapanışında bu zone'un bekleyen giriş emri.

        Saf fonksiyon: yalnızca `at`'te bilinen göstergeler (`known_at <= at`) ve o
        kapanıştaki portföy görüntüsü (`self._snap`). Emir yoksa ikinci değer nedendir
        (sayaç adı; `None` = sayılmayan neden, ör. sembolde pozisyon var).

        Canlı döngü bunu her 1m kapanışında çağırır ve emri koyar / iptal eder / yeniler.
        Backtest aynı fonksiyonu yalnızca sonraki mum emir fiyatına ulaştığında çağırır:
        emrin fiyatı, kapısı ve boyutu yalnızca `at` durumuna bağlı olduğu için sonuç
        aynıdır. ponytail: her kapanışta her zone'u hesaplamak koşuyu saatlere çıkarırdı.
        """
        if self.kill is not None:  # R-KILL-01 · yeni giriş yok, bekleyen emirler iptal (§6)
            return None, "rejected_kill"
        s = self._snap
        had_ob, had_fvg, hedef = self._gosterge(z, sd, at)
        if self.require_indicator and not had_ob:  # kapı yalnızca OB (v0.8, OPEN-65)
            return None, "no_indicator_skipped"  # R-ENTRY-02 (3) kapali
        if self.min_leg_pct and \
                abs(z.anchor_1_price - z.anchor_0_price) / z.anchor_0_price <= self.min_leg_pct:
            return None, "leg_skipped"  # F2 kolu · esik alti leg
        if self._surtunme_yetersiz(z, hedef):
            return None, "rejected_surtunme"  # R-ENTRY-06
        if z.symbol in s["pozisyon"]:  # sembol başına tek pozisyon (modelleme tercihi 5)
            return None, None
        if s["gun_blok"]:
            return None, "rejected_risk03"
        if s["risk05"] != "RAHAT":  # R-RISK-05 · UYARI/KRITIK'te yeni pozisyon yok
            return None, "rejected_risk05"
        equity = s["equity"]
        if equity <= 0:
            return None, None
        notional = equity * self.k  # R-ENTRY-03 · ölçü birimi notional
        if s["notional"] + notional > NOTIONAL_CAP * equity:
            return None, "rejected_risk01"  # R-RISK-01
        f = self.costs.fees[z.symbol]
        qty = emir_miktari(notional / Decimal(str(hedef)), Decimal(str(hedef)),
                           f.step, f.min_qty, f.min_cost)
        if qty is None:
            return None, "rejected_min_order"
        notional = qty * Decimal(str(hedef))
        # ADD-REJECT-E ilk girise de uygulanir (R-ADD-02).
        if self.stop_loss_cap and \
                self._stop_loss(z, qty, Decimal(str(hedef))) > self.stop_loss_cap * equity:
            return None, "entry_reject_e"
        return {"hedef": hedef, "qty": qty, "notional": notional,
                "had_ob": had_ob, "had_fvg": had_fvg}, None

    def _surtunme_yetersiz(self, z: Zone, hedef: float) -> bool:
        """R-ENTRY-06 · `hedef` → TP1 mesafesi < `SURTUNME_KAT` × gidiş-dönüş maliyeti.

        Gidiş-dönüş = giriş + TP1 çıkışı, motorun kendi maliyet modeliyle: limit kolunda
        maker komisyonu (slippage yok), aksi hâlde taker + slippage, iki bacak.
        """
        f = self.costs.fees[z.symbol]
        bacak = f.maker if self.limit_orders else             f.taker + self.costs.slippage_bps / Decimal("10000")
        mesafe = Decimal(str(abs(z.tp_050 - hedef) / hedef))
        return mesafe < SURTUNME_KAT * 2 * bacak

    def _try_fill(self, z: Zone, sd: SymbolData, ts: pd.Timestamp, high: float,
                  low: float, t64: np.datetime64, kill: bool = False) -> None:
        """Bekleyen giriş emri bu mumda doldu mu; dolduysa pozisyonu açar.

        Emir bir önceki kapanışta (`ts` = bu mumun açılışı) konmuştu (`OPEN-41`).
        `kill`: bu mum zone'u `1` çapasıyla öldürdü. Emir geçildiyse dolmuştur ve aynı
        mumda iç stoptan çıkılır (§8 "stop önce"; iç stop mum kapanışında).
        """
        hedef = self._gosterge(z, sd, ts)[2]
        short = z.bias == "SHORT"
        if not (high >= hedef if short else low <= hedef):  # mum emir fiyatına ulaşmadı
            return
        self._hedefe_dokunan.add(z.zone_id)
        emir, neden = self.order_for(z, sd, ts)
        if emir is None:
            if neden is not None and (z.zone_id, neden) not in self._red:
                self._red.add((z.zone_id, neden))
                self.counters[neden] += 1
                self._karar("ENTRY_REJECTED", z, ts, reason=neden, hedef=hedef)
            return
        if z.zone_id not in self._armed:
            self._armed.add(z.zone_id)
            self.counters["armed"] += 1
        # Giris limit emridir: SHORT bant yukaridan satilir, LONG asagidan alinir.
        if not self.exec.entry_filled(z.symbol, hedef, high, low, self.marks[z.symbol],
                                      sell=short):
            self.counters["limit_miss_giris"] += 1  # dokundu, kriter tutmadi
            self._dokundu.add(z.zone_id)
            return
        if z.symbol in self.pf.positions:  # aynı dakikada başka zone doldu
            return

        side = LONG if z.bias == "LONG" else SHORT
        qty, notional = emir["qty"], emir["notional"]
        # Limit kolunda dolum tam limit fiyatindandir: slippage yok, komisyon maker —
        # OPEN-36 stresinde taker'a dusmediyse.
        maker = self.limit_orders and not self._taker_mi(z.symbol, z.zone_id, "giris", qty)
        price = (Decimal(str(hedef)) if maker
                 else self.costs.fill_price(Decimal(str(hedef)), side, opening=True))
        fee = self.costs.fee(z.symbol, qty * price, "giris", maker=maker)
        if not maker:
            self.costs.apply_slippage_cost(qty, Decimal(str(hedef)), "giris")
        self.pf.balance -= fee

        pos = Position(
            symbol=z.symbol, zone_id=z.zone_id, side=side, qty=qty, avg_price=price,
            opened_at=ts, last_funding_at=ts, fees_paid=fee, max_qty=qty,
            # OPEN-29 · girişteki yapısal yön burada dondurulur: sonlandırma kuralı
            # "yön **döndü** mü" diye sorar, "yön karşı mı" diye değil. Girişte zaten
            # karşı olan yön bir giriş filtresi sorusudur (R-ENTRY), çıkış değil.
            entry_bias=self._bias_now(sd, t64),
        )
        self.pf.positions[z.symbol] = pos
        self._girilen.add(z.zone_id)
        if not kill:
            z.enter(ts)
        self.entry_ctx[z.zone_id] = {
            "had_ob": emir["had_ob"], "had_fvg": emir["had_fvg"], "entry_price": price,
            "entry_qty": qty,  # tepe/baslangic notional orani icin (salinim olcumu)
            "entry_ts": ts, "ambiguous": kill, "band_pos": self._band_pos(z, hedef),
            # R-ZONE-08 aday ozellikleri, **dolum aninda** okunur.
            "touch_count": z.touch_count,
            "leg_pct": abs(z.anchor_1_price - z.anchor_0_price) / z.anchor_0_price,
        }
        self.counters["entries"] += 1
        self.counters["entries_with_ob"] += emir["had_ob"]
        self.counters["entries_with_fvg"] += emir["had_fvg"]
        self._karar("ENTRY", z, ts, hedef=hedef, fiyat=price, qty=qty, maker=maker,
                    had_ob=emir["had_ob"], had_fvg=emir["had_fvg"], kill_bar=kill)
        if kill:
            self.counters["kill_bar_fills"] += 1
            self._close(z, pos, self._stop_fiyati(z.symbol, z.anchor_1_price, high, low),
                        ts + STATE_BAR, "STOP")

    def _karar(self, event: str, z: Zone, ts, **alanlar) -> None:
        """Karar logu satırı (`ARCHITECTURE.md` §4.1, `OPEN-54`). `self.log` yoksa hiçbir şey.

        Kararın **girdisi** yazılır: o anki kapanış görüntüsü (`_snap`) ve zone durumu.
        Kimlik, sürüm ve yazma `self.log`'un işidir (`src/live/paper.py:KararLogu`).
        """
        if self.log is None:
            return
        s = self._snap or {}
        self.log({
            "ts": pd.Timestamp(ts).isoformat(), "symbol": z.symbol, "event": event,
            "zone_id": z.zone_id,
            "inputs": {
                "price": self.marks.get(z.symbol),
                "equity": str(s.get("equity")), "notional": str(s.get("notional")),
                "risk05": s.get("risk05"), "gun_blok": s.get("gun_blok"), "kill": self.kill,
                "zone": {"bias": z.bias, "state": z.state.value, "level_050": z.level_050,
                         "level_070": z.level_070, "level_079": z.level_079,
                         "anchor_0": z.anchor_0_price, "anchor_1": z.anchor_1_price},
            },
            "outcome": event,
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in alanlar.items()},
        })

    def __getstate__(self) -> dict:
        """Durum anlık görüntüsü (`src/live/paper.py`): log yazıcısı dosya tutar, taşınmaz."""
        d = self.__dict__.copy()
        d["log"] = None
        return d

    def _stop_fiyati(self, symbol: str, seviye: float, high: float, low: float) -> float:
        """İç stopun (R-RISK-02) doluş fiyatı, slippage öncesi.

        Mum seviyeye dokunduysa stop intrabar tetiklenir: **seviyeden** (kullanıcı kararı
        2026-10-02; eskiden kapanıştan, `OPEN-42`). Dokunmadan boşlukla geçtiyse
        **açılıştan** (muhafazakâr, 2026-09-30). Slippage `_close`'ta eklenir.
        """
        return seviye if low <= seviye <= high else self._acilis[symbol]

    # --- ekleme --------------------------------------------------------------

    def _select_multiplier(self, z: Zone, pos: Position, price: Decimal) -> Decimal | None:
        """R-ADD-03 · maliyeti `0.79`'un ötesine çeken **en küçük** çarpan; yoksa `None`.

        SHORT'ta maliyet yukarı (nihai stop `1`'e doğru), LONG'da aşağı çekilir. Eşiği
        geçiren ilk çarpan seçilir — "temkinli taraf tercih edilir" (R-ADD-03) gereği
        gereğinden büyük çarpan alınmaz.
        """
        hedef = Decimal(str(self._fib(z, Decimal("0.79"))))
        short = pos.side == SHORT
        for m in ADD_MULTIPLIERS:
            eklenen = pos.qty * m
            yeni = (pos.avg_price * pos.qty + price * eklenen) / (pos.qty + eklenen)
            if (yeni >= hedef) if short else (yeni <= hedef):
                return m
        return None

    def _track_excursion(self, z: Zone, pos: Position, high: float, low: float) -> None:
        """İşlemin maksimum aleyhte sapması (MAE) — leg oranı ve equity yüzdesi olarak.

        Aleyhte uç, ortalama maliyete göre ölçülür; ekleme maliyeti değiştirdiği için
        MAE de ekleme sonrası yeni tabana göre büyümeye devam eder.
        """
        avg = float(pos.avg_price)
        sapma = (high - avg) if pos.side == SHORT else (avg - low)
        if sapma <= 0:
            return
        leg = abs(z.anchor_1_price - z.anchor_0_price)
        if leg > 0:
            pos.mae_leg = max(pos.mae_leg, sapma / leg)
        eq = self.pf.equity_f(self.marks)
        if eq > 0:
            pos.mae_equity = max(pos.mae_equity, float(pos.qty) * sapma / eq)

    def _try_add(self, z: Zone, sd: SymbolData, pos: Position, ts: pd.Timestamp,
                 high: float, low: float, t64: np.datetime64) -> None:
        """R-ADD-01 izin koşulları, R-ADD-02 red kodları, R-ADD-03 çarpan.

        Red sayaçları **ekleme denemesi başına** artar, taranan OB başına değil:
        aksi hâlde aynı reddi her mumda yeniden sayıp sayaçları şişiriyordu.
        """
        band_low, band_high = sorted((z.level_070, z.level_079))
        price_f = self.marks[z.symbol]
        # (1) fiyat giriş bandının ötesinde — pozisyon eksi bölgede
        if pos.side == SHORT and price_f <= band_high:
            return
        if pos.side == LONG and price_f >= band_low:
            return
        if not len(sd.obs):
            return

        # (2) yöne uygun, bilinen, temas edilen OB (vektörel — sıcak yol)
        dokunan = (
            sd.ob_alive
            & (sd.ob_bull == (pos.side == LONG))
            & (sd.ob_known <= t64)
            & (sd.ob_bos <= t64)  # OPEN-66 (B)
            & (sd.ob_gecersiz > t64)  # OPEN-66 (A1)
            & (sd.ob_bottom <= high)
            & (sd.ob_top >= low)
        )
        if not dokunan.any():
            return
        # ADD-REJECT-C · hacimle delinmiş OB'den dönüt beklenmez (R-ADD-06)
        secilebilir = dokunan & (sd.ob_pierce > t64)
        if not secilebilir.any():
            self.counters["add_reject_c"] += 1
            return
        j = int(np.flatnonzero(secilebilir)[0])
        aday = sd.obs[j]
        # B kolu · pozisyon omru boyunca ekleme tavani. Spec'te yok; salinimin
        # maliyeti olculdugu icin var, varsayilani kapali (`max_adds = 0`).
        if self.max_adds is not None and pos.adds >= self.max_adds:
            self.counters["add_reject_cap"] += 1
            return
        if self.limit_orders:
            # C kolu · ekleme limit emridir ve OB'nin **ilk dokunulan** kenarina
            # konur: SHORT bandi asagidan yukari, LONG yukaridan asagi kat eder.
            # Dolum icin kenarin 1 tick asilmasi gerekir; dolmazsa ekleme yok.
            kenar = aday.bottom if pos.side == SHORT else aday.top
            if not self.exec.limit_filled(z.symbol, kenar, high, low, sell=(pos.side == SHORT)):
                self.counters["limit_miss_ekleme"] += 1
                return
            price_f = kenar
        # (3) R-ADD-05 "tek OB tek başına yeterlidir" — güç bayrakları ek sinyaldir,
        # izin şartı değil. Bu yüzden burada kapı olarak kullanılmaz.

        # (5) / ADD-REJECT-D · likidasyon tamponu.
        # KRITIK daima durdurur. UYARI'nın eklemeyi durdurup durdurmadığı süpürme
        # boyutudur (`uyari_blocks_adds`); kapalıyken ekleme R-RISK-01 tavanına ve
        # ADD-REJECT-A/B/C'ye tabi olarak devam eder.
        bolge = self._risk05_zone()
        if bolge == "KRITIK" or (bolge == "UYARI" and self.uyari_blocks_adds):
            self.counters["add_reject_d"] += 1
            return

        equity = Decimal(str(self.pf.equity_f(self.marks)))
        price = (Decimal(str(price_f)) if self.limit_orders
                 else self.costs.fill_price(Decimal(str(price_f)), pos.side, opening=True))
        if equity <= 0:
            return
        carpan = self._select_multiplier(z, pos, price)
        if carpan is None:  # hiçbir çarpan maliyeti yeterince çekmiyor → ekleme yok
            self.counters["add_reject_mult"] += 1
            return
        add_qty = pos.qty * carpan
        if Decimal(str(self.pf.total_notional_f(self.marks))) + add_qty * price > NOTIONAL_CAP * equity:
            self.counters["add_reject_b"] += 1  # ADD-REJECT-B · notional tavanı
            return

        # ADD-REJECT-A · ekleme sonrası maliyet, 0.50'ye dönüşte kâr bırakmalı
        total = pos.qty + add_qty
        new_avg = (pos.avg_price * pos.qty + price * add_qty) / total
        tp1 = Decimal(str(z.tp_050))  # gercek ilk hedef: `tp_offset` uygulanmis
        gross = total * ((tp1 - new_avg) if pos.side == LONG else (new_avg - tp1))
        oran = (self.costs.fees[z.symbol].maker if self.limit_orders
                else self.costs.fees[z.symbol].taker)  # ADD-REJECT-A esigi kendi komisyonuyla
        if gross <= total * tp1 * oran * Decimal("2"):
            self.counters["add_reject_a"] += 1
            return

        # ADD-REJECT-E · ekleme sonrasi pozisyonun stopta kaybedecegi tutar tavani
        # asiyorsa ekleme reddedilir. R-RISK-01'den farki: olcu notional degil,
        # **stopta realize olacak kayip**; carpimsal merdiveni baglayan budur.
        if self.stop_loss_cap and self._stop_loss(z, total, new_avg) > self.stop_loss_cap * equity:
            self.counters["add_reject_e"] += 1
            return

        fee = self.costs.fee(z.symbol, add_qty * price, "ekleme", maker=self.limit_orders)
        if not self.limit_orders:
            self.costs.apply_slippage_cost(add_qty, Decimal(str(price_f)), "ekleme")
        self.pf.balance -= fee
        pos.fees_paid += fee
        pos.add(add_qty, price)
        if self.reduce_once and pos.reduces:
            # B kolu · kucultme pozisyon basina bir kez tetiklenir; `Position.add`
            # tetigi her eklemede yeniden kuruyor, burada geri alinir.
            pos.reduce_armed = False
        sd.ob_alive[j] = False  # aynı OB ikinci kez ekleme gerekçesi olmaz
        self.counters["adds"] += 1
        anahtar = f"1-{int(carpan)}"  # normalize() 10 icin "1E+1" uretiyordu
        self.counters["adds_by_mult"][anahtar] =             self.counters["adds_by_mult"].get(anahtar, 0) + 1

    # --- cikis ---------------------------------------------------------------

    def _charge_funding(self, pos: Position, ts: pd.Timestamp) -> None:
        """Son tahsilattan bu yana biriken funding'i işler.

        Notional, aralıktaki **son** hâliyle alınır; ekleme aralığın ortasında olduysa
        bu, ekleme öncesi funding'i de büyük notional üzerinden sayar — kötümser taraf.
        Kısmi çıkışta (TP1) tahsilat yapıldığı için küçülme tersine işlemez.
        """
        cost = self.costs.funding_cost(
            pos.symbol, pos.side, pos.qty * pos.avg_price, pos.last_funding_at, ts
        )
        pos.funding_paid += cost
        self.pf.balance -= cost
        pos.last_funding_at = ts

    def _close(self, z: Zone, pos: Position, price_level: float, ts: pd.Timestamp,
               reason: str, fraction: Decimal = Decimal("1")) -> None:
        """Pozisyonun tamamını veya bir kısmını kapatır, maliyetleri işler.

        Kısmi kapanışın miktarı borsa adımına yuvarlanır; asgariyi karşılamıyorsa emir
        gönderilmez, `rejected_min_close` sayılır ve pozisyon olduğu gibi kalır.
        Tam kapanış (`reduceOnly`, kalan miktarın tamamı) kısıta takılmaz.
        """
        if fraction < 1:
            f = self.costs.fees[pos.symbol]
            q = emir_miktari(pos.qty * fraction, Decimal(str(price_level)),
                             f.step, f.min_qty, f.min_cost)
            if q is None:
                self.counters["rejected_min_close"] += 1
                self._karar("EXIT_REJECTED", z, ts, reason=reason, seviye=price_level)
                return
            fraction = q / pos.qty
        # OPEN-62 · iç stopta seviye ile gerçekleşen çıkış farkı loga yazılır (paper ölçer,
        # canlıda aynı alan gerçek doluştan gelir). Pozisyon değişmeden önce okunur.
        stop_seviye = (z.anchor_1_price if reason == "STOP"
                       else self._breakeven(z, pos) if reason == "BREAKEVEN" else None)
        self._charge_funding(pos, ts)
        # Limit kolunda TP'ler ve kucultme limit emridir: kendi fiyatindan dolar,
        # slippage yok, maker komisyonu. Stop ve zorunlu cikislar piyasa emridir.
        kalem = KALEM.get(reason, "cikis")
        maker = (self.limit_orders and reason in self._maker_reasons
                 and not self._taker_mi(pos.symbol, z.zone_id, kalem, pos.qty * fraction))
        price = (Decimal(str(price_level)) if maker
                 else self.costs.fill_price(Decimal(str(price_level)), pos.side, opening=False))
        qty = pos.qty * fraction
        pnl = pos.reduce(qty, price)
        # Kalem: ayni fonksiyon hem cikis hem kucultme yapiyor; para nereye gittigi
        # ancak bu ayrimla okunabiliyor (R-ADD-04 kucultmesi vs R-RISK-05 delev).
        fee = self.costs.fee(pos.symbol, qty * price, kalem, maker=maker)
        if not maker:
            self.costs.apply_slippage_cost(qty, Decimal(str(price_level)), kalem)
        pos.fees_paid += fee
        self.pf.balance += pnl - fee
        if reason == "DELEVERAGE":
            # R-RISK-05 yapısal maliyeti: aleyhte hareketin dibinde zorla küçültmek.
            # Likidasyon riskinin karşısına konabilmesi için ayrı kalem (spec §4 notu).
            self.deleverage_realized += pnl - fee
        self._karar("EXIT", z, ts, reason=reason, seviye=price_level, fiyat=price, qty=qty,
                    kalan=pos.qty, pnl=pnl - fee, maker=maker,
                    **({} if stop_seviye is None else
                       {"stop_seviye": stop_seviye,
                        "stop_fark": price - Decimal(str(stop_seviye))}))

        if pos.qty > 0:
            return  # kısmi çıkış — pozisyon açık kalır
        ctx = self.entry_ctx.pop(z.zone_id, {})
        self.trades.append(Trade(
            symbol=pos.symbol, zone_id=z.zone_id, side=pos.side,
            entry_ts=ctx.get("entry_ts", pos.opened_at), exit_ts=ts,
            entry_price=ctx.get("entry_price", pos.avg_price), exit_price=price,
            qty=pos.max_qty, pnl=pos.realized - pos.fees_paid - pos.funding_paid,
            gross=pos.realized, fees=pos.fees_paid, funding=pos.funding_paid,
            reason=reason, adds=pos.adds, ambiguous=ctx.get("ambiguous", False),
            had_ob=ctx.get("had_ob", False), had_fvg=ctx.get("had_fvg", False),
            bars_held=int((ts - pos.opened_at) / pd.Timedelta(STATE_TF)),
            reached_tp1=pos.tp1_done,
            reduces=pos.reduces,
            bars_after_reduce=(
                0 if pos.reduced_at is None
                else int((ts - pos.reduced_at) / pd.Timedelta(STATE_TF))
            ),
            band_pos=ctx.get("band_pos", 0.0),
            mae_leg=pos.mae_leg, mae_equity=pos.mae_equity,
            min_liq_dist=pos.min_liq_dist,
            entry_qty=ctx.get("entry_qty", pos.max_qty),
            entry_bias=pos.entry_bias,
            touch_count=ctx.get("touch_count", 0),
            leg_pct=ctx.get("leg_pct", 0.0),
        ))
        self.pf.positions.pop(pos.symbol, None)

    def _bias_now(self, sd: SymbolData, t64: np.datetime64) -> str:
        """R-ZONE-10 · karar aninda **bilinen** 4h yon; yoksa `NONE`."""
        i = int(np.searchsorted(sd.bias_known, t64, side="right")) - 1
        return "NONE" if i < 0 else str(sd.bias_val[i])

    def _termination_reason(self, sd: SymbolData, pos: Position, z: Zone,
                            ts: pd.Timestamp, t64: np.datetime64) -> str | None:
        """`OPEN-29` · pozisyonu sonlandiran kural, yoksa `None`.

        Uc aday, spec'te **hicbiri yok** (R-EXIT-03 zaman siniri tanimamis):

        | kural | kapatma kosulu |
        |---|---|
        | `time` | tasima suresi `max_hold_bars`'i (21 gun) asti |
        | `structure` | 4h yapisal yon pozisyonun karsisina gecti (R-ZONE-10) |
        | `funding` | birikmis funding > oran × potansiyel kar (nihai TP'ye kalan) |

        `structure`'da `NONE` kapatmaz: yon **karsi tarafa** gecmis olmali. Yapinin
        kararsiz oldugu donem tezin oldugu anlamina gelmez.
        """
        if self.terminate == TERMINATE_TIME:
            if (ts - pos.opened_at) >= pd.Timedelta(minutes=self.max_hold_bars):
                return "TIME_STOP"
            return None
        if self.terminate == TERMINATE_STRUCTURE:
            yon = self._bias_now(sd, t64)
            karsi = "UP" if pos.side == SHORT else "DOWN"
            # Girişte yön **zaten** karşıysa bu bir dönüş değildir: pozisyon baştan
            # yapıya karşı açılmıştır ve onu kapatmak sonlandırma değil, geriye dönük
            # giriş filtresi olurdu. Ölçüldü: o okumada işlemlerin %32.8'i kapanıyor
            # ve %92'si girişten **bir mum** sonra — yani kural çıkış değil, giriş
            # kuralı hâline geliyordu.
            if yon == karsi and pos.entry_bias != karsi:
                return "STRUCT_FLIP"
            return None
        if self.terminate == TERMINATE_FUNDING:
            # Potansiyel kar: nihai TP (capa 0) ile ortalama maliyet arasi × miktar.
            hedef = Decimal(str(z.anchor_0_price))
            fark = (hedef - pos.avg_price) if pos.side == LONG else (pos.avg_price - hedef)
            potansiyel = pos.qty * fark
            if potansiyel > 0 and pos.funding_paid > self.funding_cap_ratio * potansiyel:
                return "FUNDING_CAP"
            return None
        return None

    def _reduce_to_base(self, z: Zone, pos: Position, price_level: float,
                        ts: pd.Timestamp) -> None:
        """R-ADD-04 · ekleme sonrası maliyete dönüşte pozisyon `K` tabanına indirilir.

        **Çıkış değil, durum geçişi.** Kalan kısım nihai stop (`1`), ilk TP (`0.50`) ve
        nihai TP (`0`) ile yoluna devam eder; zone durumu değişmez, işlem kapanmaz.
        Ortalama maliyet küçültmeden **etkilenmez** (`Position.reduce` maliyeti
        değiştirmez), bu yüzden kalan kısmın hedefleri ve stopu aynı yerdedir.

        Hedef boyut R-ENTRY-03'ün standart girişidir: `K × equity` notional. Spec
        "hangi equity" demiyor; küçültme anındaki equity alınır — o an fiyat ortalama
        maliyette olduğu için bu pozisyon *düz* iken ölçülen equity'dir, yani yeni bir
        giriş açılsa alacağı boyutun aynısı.

        Küçültme tetiği düşer; yeni bir ekleme (`Position.add`) yeniden kurar. Hedef
        mevcut miktardan büyükse (K tabanının altına düşülmüş) hiçbir şey yapılmaz —
        kural küçültmedir, büyütme değil.
        """
        equity = Decimal(str(self.pf.equity_f(self.marks)))
        pos.reduce_armed = False
        if equity <= 0:
            return
        hedef_qty = equity * self.k / Decimal(str(price_level))
        if hedef_qty >= pos.qty:
            return
        pos.reduces += 1
        if pos.reduced_at is None:
            pos.reduced_at = ts
        self.counters["reduce_events"] += 1
        self._close(z, pos, price_level, ts, "REDUCE",
                    fraction=(pos.qty - hedef_qty) / pos.qty)

    def _liquidate(self, ts: pd.Timestamp) -> None:
        """R-RISK-05 / R-KILL-04 · cross marjinde hesap likide olur: hepsi kapanır."""
        self.counters["liquidations"] += 1
        self.pf.liquidation_events += 1
        for symbol in list(self.pf.positions):
            pos = self.pf.positions[symbol]
            z = self._zone_of(pos)
            if z is None:
                self.pf.positions.pop(symbol, None)
                continue
            self._close(z, pos, self.marks[symbol], ts, "LIQUIDATION")
            if z.state not in TERMINAL:
                z.transition(S.CLOSED, ts)

    def _zone_of(self, pos: Position) -> Zone | None:
        for z in self._active.get(pos.symbol, []):
            if z.zone_id == pos.zone_id:
                return z
        return None

    # --- dongu ---------------------------------------------------------------

    def _progress(self, gi: int, toplam: int, t: np.datetime64) -> None:
        """Her `progress_every` mumda bir ilerleme satırı (stderr)."""
        gecen = time.time() - self._t0
        pay = (gi + 1) / toplam
        kalan = gecen / pay - gecen if pay > 0 else 0.0
        print(
            f"    [{pay * 100:5.1f}%] mum {gi + 1:>10,}/{toplam:,}  "
            f"{str(t)[:16]}  açık {len(self.pf.positions):>2}  "
            f"ekleme {self.counters['adds']:>6,}  küçültme {self.counters['reduce_events']:>6,}  "
            f"işlem {len(self.trades):>6,}  geçen {gecen / 60:>5.1f} dk  "
            f"kalan ~{kalan / 60:>5.1f} dk",
            file=sys.stderr, flush=True,
        )

    def start(self) -> None:
        """Koşu durumunu kurar. `run` ve canlı döngü `step`'ten önce bir kez çağırır."""
        self._symbols = list(self.data)
        self._zptr = {s: 0 for s in self._symbols}
        self._active: dict[str, list[Zone]] = {s: [] for s in self._symbols}
        self._watch64 = {s: self._watch_dizisi(self.data[s].zones) for s in self._symbols}
        self._onceki_gun = None

    def _hazirla(self, z: Zone, symbol: str) -> None:
        z.tp_offset = self.tp_offset
        z.tp_tick = self.exec.tp_tick(symbol)

    @staticmethod
    def _watch_dizisi(zones: list[Zone]) -> np.ndarray:
        return np.array([np.datetime64(z.watch_from.tz_localize(None)) for z in zones],
                        dtype="datetime64[ns]")

    def add_zones(self, symbol: str, zones: list[Zone]) -> None:
        """Canlı döngü · 30m kapanışında yeni tespit edilen zone'ları ekler (`docs/LIVE.md` A2).

        Yeni zone'un `known_at`'i son kapanıştır, izlenmekte olanlarınkinden önce olamaz:
        liste `watch_from` sırasında kalır ve `step`'in işaretçisi bozulmaz.
        """
        sd = self.data[symbol]
        for z in sorted(zones, key=lambda z: z.watch_from):
            self._hazirla(z, symbol)
            sd.zones.append(z)
        self._watch64[symbol] = self._watch_dizisi(sd.zones)

    def step(self, t: np.datetime64, bars: dict[str, tuple]) -> None:
        """Bir kapanmış 1m dakikasını işler — backtest ve canlı döngünün **tek** gövdesi.

        `docs/LIVE.md` Ö1. `t`: dakikanın açılış damgası (tz-naive UTC `datetime64`).
        `bars`: o dakikada mumu olan semboller → `(open, high, low, close, volume)`;
        `volume` yoksa `None`. Mumu olmayan sembol o dakikada işlenmez (`OPEN-46`).
        Semboller `self.data` sırasıyla işlenir (§2 dakika bariyeri).

        `pd.Timestamp` kurmak 1m çözünürlükte pahalıdır ve mumların çoğunda hiçbir
        olay yoktur. Bu yüzden karşılaştırmalar numpy datetime64 üzerinde yapılır ve
        Timestamp yalnızca gerçekten bir olay varken kurulur.
        """
        if self._snap is None:
            self._kapanis(t)

        ts: pd.Timestamp | None = None
        for s in self._symbols:
            bar = bars.get(s)
            if bar is None:
                continue
            sd = self.data[s]
            acilis, high, low, close, volume = bar
            self.marks[s] = close
            self._acilis[s] = acilis
            if volume is not None:
                self._vol[s] = volume

            # izlemeye girenler (R-ZONE-09 · WATCH_FROM)
            w = self._watch64[s]
            while self._zptr[s] < len(sd.zones) and w[self._zptr[s]] <= t:
                z = sd.zones[self._zptr[s]]
                z.activate()
                self._active[s].append(z)
                self._zptr[s] += 1

            if not self._active[s]:
                continue
            if ts is None:
                ts = pd.Timestamp(t, tz="UTC")

            kalan = []
            for z in self._active[s]:
                self._step_zone(z, sd, ts, high, low, t)
                if z.state in TERMINAL:
                    if z.zone_id in self._girilen:
                        pass
                    elif z.zone_id in self._dokundu:
                        self.counters["kacan_giris"] += 1  # emir fiyatına dokunuldu, dolmadı
                    elif z.zone_id in self._temas and z.zone_id not in self._hedefe_dokunan:
                        self.counters["unfilled"] += 1  # TOUCHED oldu, emir fiyatı hiç gelmedi
                    self.counters["kill_wins"] += z.kill_wins
                    self.counters["skipped_progress"] += z.skipped_progress
                    if z.primed_at is not None:
                        self.counters["zones_primed"] += 1
                else:
                    kalan.append(z)
            self._active[s] = kalan

        if self.pf.positions:
            # Funding gercek takviminde tahsil edilir (8 saat). Cikista tek seferde
            # islemek toplami dogru verir ama equity'yi butun pozisyon boyunca
            # yanlis yerde tutar — ve `funding` sonlandirma adayi birikmis maliyeti
            # pozisyon acikken okumak zorundadir.
            _ts_f: pd.Timestamp | None = None
            for _p in self.pf.positions.values():
                _c = self.costs.funding.get(_p.symbol)
                _adim = np.timedelta64(_c.interval.value, "ns") if _c else _FUNDING_NP
                if t - np.datetime64(_p.last_funding_at.tz_localize(None)) >= _adim:
                    if _ts_f is None:
                        _ts_f = pd.Timestamp(t, tz="UTC")
                    self._charge_funding(_p, _ts_f)
            if self.pf.is_liquidated_f(self.marks):
                self._liquidate(pd.Timestamp(t, tz="UTC"))
            elif self._risk05_zone() == "KRITIK":
                self._deleverage(pd.Timestamp(t, tz="UTC"))
            # R-RISK-01 · tavan yeni girişi bu mumda bağlıyor mu (rapor sayacı):
            # notional + K × equity > 10 × equity  <=>  notional > (10 − K) × equity
            eq = self.pf.equity_f(self.marks)
            if self.pf.total_notional_f(self.marks) > float(NOTIONAL_CAP - self.k) * eq:
                self.counters["risk01_binding_bars"] += 1
        if self.pf.positions:
            d = self.pf.liq_distance_f(self.marks)
            if d is not None:
                for _p in self.pf.positions.values():
                    _p.min_liq_dist = d if _p.min_liq_dist is None else min(_p.min_liq_dist, d)
        self.counters["bars_with_position"] += bool(self.pf.positions)
        self.counters["bars_total"] += 1
        self.pf.observe(self.marks)
        self._kapanis(t + np.timedelta64(1, "m"))

    def _kapanis(self, an: np.datetime64) -> None:
        """1m kapanışı `an`: gün sınırı (R-RISK-03) ve bekleyen emirlerin dayandığı portföy
        görüntüsü (`OPEN-41`). Sonraki mumdaki her giriş kararı yalnızca bunu okur."""
        gun = an.astype("datetime64[D]")
        if gun != self._onceki_gun:
            self._onceki_gun = gun
            self._day_start_equity = self.pf.equity_f(self.marks)
            self._day_blocked = False
        self._snap = {
            "equity": Decimal(str(self.pf.equity_f(self.marks))),
            "notional": Decimal(str(self.pf.total_notional_f(self.marks))),
            "risk05": self._risk05_zone(),
            "gun_blok": self._daily_loss_hit(),
            "pozisyon": frozenset(self.pf.positions),
        }

    def run(self) -> Result:
        """Parquet ızgarasını dakika dakika `step`'e besler."""
        self.start()
        grid = np.unique(np.concatenate([self.data[s].ts for s in self._symbols]))
        ptr = {s: 0 for s in self._symbols}
        for gi in range(len(grid)):
            t = grid[gi]
            if self.progress_every and gi % self.progress_every == 0:
                self._progress(gi, len(grid), t)
            bars = {}
            for s in self._symbols:
                sd = self.data[s]
                i = ptr[s]
                if i >= len(sd.ts) or sd.ts[i] != t:
                    continue
                ptr[s] = i + 1
                bars[s] = (float(sd.open[i]), float(sd.high[i]), float(sd.low[i]),
                           float(sd.close[i]),
                           float(sd.volume[i]) if len(sd.volume) else None)
            self.step(t, bars)
            if gi % 1440 == 0:
                self.equity_curve.append((pd.Timestamp(t, tz="UTC"), self.pf.equity_f(self.marks)))
        return self.finish(pd.Timestamp(grid[-1], tz="UTC"))

    def finish(self, son: pd.Timestamp) -> Result:
        """Koşu sonu: açık kalanlar son fiyattan `RUN_END` ile kapatılır (A9)."""
        for symbol in list(self.pf.positions):
            pos = self.pf.positions[symbol]
            z = self._zone_of(pos)
            if z is not None:
                self._close(z, pos, self.marks[symbol], son, "RUN_END")
            else:
                self.pf.positions.pop(symbol, None)

        self.counters["zones_total"] = sum(len(sd.zones) for sd in self.data.values())
        self.counters["limit_miss_tp"] = sum(
            z.tp_tick_miss for sd in self.data.values() for z in sd.zones
        )
        return Result(self.trades, self.pf, self.costs, self.equity_curve, self.counters,
                      self.deleverage_realized)

    def _step_zone(self, z: Zone, sd: SymbolData, ts: pd.Timestamp, high: float, low: float,
                   t64: np.datetime64) -> None:
        """Bir zone'u bir 1m mumla ilerletir ve doğan olayları uygular."""
        before = z.state
        pos = self.pf.positions.get(z.symbol)
        pos = pos if pos is not None and pos.zone_id == z.zone_id else None

        # §8 · intrabar belirsizliği: aynı mumda hem hedef hem stop görüldü mü
        if pos is not None:
            hit_stop = z.stop_reached(high, low)
            hedef = z.tp_final if z.state is S.TP1_HIT else z.tp_050
            hit_target = low <= hedef <= high or low <= z.tp_final <= high
            if hit_stop and hit_target:
                self.counters["ambiguous_bars"] += 1
                ctx = self.entry_ctx.get(z.zone_id)
                if ctx is not None:
                    ctx["ambiguous"] = True

        z.on_bar(high, low, ts)
        after = z.state
        if after is before:
            if pos is not None:
                self._track_excursion(z, pos, high, low)
            # OPEN-29 · sonlandirma kurali her seyden once: bu bir cikistir ve
            # cikis, ekleme/kucultmeye baskindir. `none` iken hicbir sey yapmaz.
            if pos is not None and self.terminate != TERMINATE_NONE:
                neden = self._termination_reason(sd, pos, z, ts, t64)
                if neden is not None:
                    self.counters["terminated"] += 1
                    self._close(z, pos, self.marks[z.symbol], ts, neden)
                    if z.state not in TERMINAL:
                        z.transition(S.CLOSED, ts)
                    return
            # R-ADD-04 · ekleme sonrasi fiyat ortalama maliyete donerse pozisyon
            # K tabanina indirilir. Cikis degil, durum gecisi: zone acik kalir.
            if pos is not None and not pos.tp1_done and pos.reduce_armed:
                maliyet = float(pos.avg_price)
                # Kucultme bir azaltma emridir: LONG'da satis, SHORT'ta alis.
                if self.exec.limit_filled(z.symbol, maliyet, high, low,
                                      sell=(pos.side == LONG)):
                    self._reduce_to_base(z, pos, maliyet, ts)
                    return
                if low <= maliyet <= high:
                    self.counters["limit_miss_kucultme"] += 1
            if pos is not None and pos.tp1_done:
                # R-EXIT-01 · ilk TP sonrası stop maliyete çekilir.
                be = self._breakeven(z, pos)
                if (low <= be) if pos.side == LONG else (high >= be):  # temas ya da boşluk
                    # İç stop (R-RISK-02): intrabar tetik, seviyeden (boşlukta açılıştan).
                    kapanis = ts + STATE_BAR
                    self._close(z, pos, self._stop_fiyati(z.symbol, be, high, low), kapanis,
                                "BREAKEVEN")
                    if z.state not in TERMINAL:
                        z.transition(S.CLOSED, kapanis)
                    return
            if z.state is S.TOUCHED:  # varyant dolumu bekliyor
                self._try_fill(z, sd, ts, high, low, t64)
            if pos is not None and z.state in (S.ENTERED, S.TP1_HIT):
                self._try_add(z, sd, pos, ts, high, low, t64)
            return

        if after is S.TOUCHED:
            self.counters["zones_touched"] += 1
            self.counters["entry_candidates"] += 1
            self._temas.add(z.zone_id)
            self._try_fill(z, sd, ts, high, low, t64)
        elif after is S.INVALIDATED and before in (S.PRIMED, S.TOUCHED) \
                and z.stop_reached(high, low):
            # OPEN-41 · bekleyen emir `PRIMED` kapanışından beri defterde: `1`'e giden mum
            # onu da geçti. Dolum + aynı mumda iç stop (§8 stop önce).
            self._try_fill(z, sd, ts, high, low, t64, kill=True)
        elif after is S.TP1_HIT and pos is not None:
            # R-EXIT-01 · 0.50'de pozisyonun ~%50'si, stop maliyete
            self._close(z, pos, z.tp_050, ts, "TP1", fraction=TP1_FRACTION)
            if z.symbol in self.pf.positions:
                self.pf.positions[z.symbol].tp1_done = True
        elif after is S.CLOSED and pos is not None:
            # Çapa teması: 0 = nihai TP, 1 = nihai stop. İkisi de vurulduysa stop kazanır (§8).
            # Nihai TP borsada bekleyen limittir, seviyeden dolar. Nihai stop iç stoptur
            # (R-RISK-02): intrabar tetik, seviyeden + slippage (boşlukta açılıştan).
            if z.stop_reached(high, low):  # temas ya da boşluk; ikisi birden → stop (§8)
                self._close(z, pos, self._stop_fiyati(z.symbol, z.anchor_1_price, high, low),
                            ts + STATE_BAR, "STOP")
            else:
                self._close(z, pos, z.tp_final, ts, "FINAL_TP")


def run_backtest(
    symbols: list[str],
    exchange: str = "bingx",
    train_frac: float = TRAIN_FRAC,
    start_balance: Decimal = Decimal("10000"),
    k: Decimal = K_STANDARD,
    mmr: Decimal = Decimal("0.005"),
    slippage_bps: Decimal | None = None,
    t_rahat: Decimal = T_RAHAT,
    t_kritik: Decimal = T_KRITIK,
    uyari_blocks_adds: bool = True,
    entry_rule: EntryRule = ENTRY_070,
    progress_every: int = 0,
    terminate: str = TERMINATE_NONE,
) -> tuple[Result, list[str]]:
    """Sembolleri hazırlar ve motoru koşturur. Dönen ikinci değer atlanan sembollerdir."""
    costs = build_cost_model(symbols, exchange, **(
        {"slippage_bps": slippage_bps} if slippage_bps is not None else {}
    ))
    data, skipped = [], []
    for s in symbols:
        sd = load_symbol(s, exchange, train_frac)
        (data.append(sd) if sd is not None else skipped.append(s))
    if not data:
        raise RuntimeError("hiçbir sembolde 30m + 1m veri yok")
    return Backtest(data, costs, start_balance, k, mmr, t_rahat, t_kritik,
                    uyari_blocks_adds, entry_rule, progress_every,
                    terminate).run(), skipped
