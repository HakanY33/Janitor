"""Sembol verisi hazirligi ve disk onbellegi.

`SymbolData`, motorun tek bir sembol icin ihtiyac duydugu her seyi tasir: 1m fiyat
eksenleri, zone'lar, OB/FVG listeleri ve ekleme aramasinin vektorel dizinleri.
Hazirlik sembol basina ~45 sn (20 sembol ~17 dk) ve kosudan kosuya **degismez**;
bu yuzden diske pickle'lanir.

**Neden ayri modul.** Onbellek anahtari, uretilen veriye gercekten etki eden kodun
icerigidir. Bu kod `engine.py` icindeyken anahtar motorun tamamina bagliydi ve her
motor/strateji duzenlemesi 17 dakikalik yeniden kurulum demekti. Hazirlik kendi
modulune alininca anahtar `_src_closure` ile **bu dosyanin gercek import kapanisina**
daralir: `src/features/ob.py` degisirse onbellek duser, `src/backtest/engine.py`
degisirse dusmez.

**Bayat onbellek sessiz hata uretir**, bu yuzden anahtar iki sey birden tasir: kaynak
parquet dosyalarinin damgasi ve kapanistaki her dosyanin **icerigi**. `code_version()`
(git) kullanilmaz — kirli agacta sabit kalir ve degisen kodu goremez.
"""
from __future__ import annotations

import ast
import hashlib
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.data import collect
from src.features.fvg import detect_fvgs, replay
from src.features.ob import detect_order_blocks, pierce_time, replay_obs
from src.features.structure import htf_bias
from src.zones.detect import detect_zones
from src.zones.model import Zone

DETECT_TF = "30m"
STATE_TF = "1m"
TRAIN_FRAC = 0.80

CACHE_ROOT = Path("data/cache/symbols")
SRC_ROOT = Path(__file__).resolve().parents[1]
SEED = Path(__file__).resolve()  # kapanisin basladigi dosya (testte degistirilir)


@dataclass
class SymbolData:
    symbol: str
    ts: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    zones: list[Zone]
    obs: list
    fvgs: list
    pierce_at: dict[str, datetime | None]
    # Ekleme adayı OB aramasının vektörel dizinleri. Aynı arama, pozisyon açıkken her
    # 1m mumunda yapılıyor; OB listesi üzerinde Python döngüsü koşunun en sıcak yeriydi.
    ob_top: np.ndarray = field(default_factory=lambda: np.array([]))
    ob_bottom: np.ndarray = field(default_factory=lambda: np.array([]))
    ob_bull: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    ob_impulse: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"))
    ob_pierce: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"))
    ob_alive: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    # R-ZONE-10 · 4h yapisal yon. `bias_known` yonun **kullanilabilir** oldugu an
    # (teyit mumunun kapanisi); karar aninda yalnizca `bias_known <= t` olan son satir
    # gorulebilir (CLAUDE.md #3). `OPEN-29` yapisal gecersizlik adayi bunu okur.
    bias_known: np.ndarray = field(default_factory=lambda: np.array([], dtype="datetime64[ns]"))
    bias_val: np.ndarray = field(default_factory=lambda: np.array([], dtype=object))
    # 1m islem hacmi (baz varlik). `OPEN-36` kosullu taker kolu okur; defter verisi
    # olmadigi icin emrin onundeki kuyrugun **vekili**dir.
    volume: np.ndarray = field(default_factory=lambda: np.array([]))


def _build_symbol(
    symbol: str, exchange: str = "bingx", train_frac: float = TRAIN_FRAC
) -> SymbolData | None:
    """Bir sembolün tespit (30m) ve durum (1m) verisini hazırlar.

    Veri disiplini: 30m'in en eski `train_frac` dilimi alınır, 1m o pencereye kırpılır.
    Ayrılmış %20 **hiç okunmaz**. 1m kapsamı olmayan zone'lar elenir — R-ZONE-09 durum
    geçişlerini 1m'de şart koşuyor, 30m'e düşmek sessiz bir kural ihlali olurdu.
    """
    d30 = collect.read_parquet(exchange, symbol, DETECT_TF)
    if d30.empty:
        return None
    tr = d30.iloc[: int(len(d30) * train_frac)].reset_index(drop=True)
    if len(tr) < 1_000:
        return None
    end = tr.ts.iloc[-1]

    d1 = collect.read_parquet(exchange, symbol, STATE_TF)
    if d1.empty:
        return None
    d1 = d1[d1.ts <= end].reset_index(drop=True)
    if len(d1) < 1_000:
        return None

    obs = detect_order_blocks(tr, symbol, DETECT_TF)
    replay_obs(obs, tr)
    fvgs = detect_fvgs(tr, symbol, DETECT_TF)
    replay(fvgs, tr)
    zones = [z for z in detect_zones(tr, symbol, DETECT_TF)
             if d1.ts.iloc[0] <= z.watch_from <= d1.ts.iloc[-1]]
    zones.sort(key=lambda z: z.watch_from)

    pierce_at = {o.ob_id: pierce_time(o, tr) for o in obs}  # R-ADD-06 / ADD-REJECT-C
    bias = htf_bias(tr, symbol)  # R-ZONE-07/10 · 4h yon, `known_at` damgali
    uzak = np.datetime64("2262-01-01")  # delinmemiş OB: karşılaştırmada hep gelecekte
    return SymbolData(
        symbol=symbol,
        # İç zaman ekseni tz-naive UTC `datetime64`: tz-aware seri `to_numpy()`'da
        # object dizisine düşüyor ve karşılaştırmalar Timestamp'e geri dönüyordu.
        # Dışarıya çıkan her zaman damgası `pd.Timestamp(t, tz="UTC")` ile kurulur.
        ts=d1.ts.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy(),
        high=d1.high.to_numpy(),
        low=d1.low.to_numpy(),
        close=d1.close.to_numpy(),
        zones=zones,
        obs=obs,
        fvgs=fvgs,
        pierce_at=pierce_at,
        ob_top=np.array([o.top for o in obs], dtype=float),
        ob_bottom=np.array([o.bottom for o in obs], dtype=float),
        ob_bull=np.array([o.direction == "BULLISH" for o in obs], dtype=bool),
        ob_impulse=np.array([np.datetime64(o.impulse_at.tz_localize(None)) for o in obs]),
        ob_pierce=np.array([
            uzak if pierce_at[o.ob_id] is None
            else np.datetime64(pierce_at[o.ob_id].tz_localize(None)) for o in obs
        ]),
        ob_alive=np.ones(len(obs), dtype=bool),  # ekleme için kullanılınca düşer
        bias_known=bias.known_at.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy(),
        bias_val=bias.bias.to_numpy(dtype=object),
        volume=d1.volume.to_numpy(dtype=float),
    )


class RelativeImportError(RuntimeError):
    """Kapanis hesabi goreli import'i cozemez — sessizce atlamak bayat onbellek demek."""


@lru_cache(maxsize=None)
def _src_closure(seed: Path, src_root: Path) -> tuple[Path, ...]:
    """`seed`'in `src.*` altindaki gecisli import kapanisi, kendisi dahil.

    AST ile okunur; modul **import edilmez**. Anahtarin kapsami budur: yalnizca
    `_build_symbol`'un gercekten dokundugu dosyalar. Motor (`engine.py`) ve strateji
    (`strategy/entry.py`) buraya girmez — onlari degistirmek onbellegi dusurmez.

    Goreli import (`from . import x`) ile karsilasilirsa **hata verilir**: sessizce
    atlamak, gorunmeyen bir bagimliligin onbellegi bayatlatmasi demektir (CLAUDE.md #8).
    """
    def yol(mod: str) -> Path | None:
        p = src_root.joinpath(*mod.split(".")[1:])  # "src.features.ob" -> src/features/ob
        for c in (p.with_suffix(".py"), p / "__init__.py"):
            if c.exists():
                return c
        return None

    gorulen: set[Path] = set()
    yigin = [seed.resolve()]
    while yigin:
        f = yigin.pop()
        if f in gorulen:
            continue
        gorulen.add(f)
        for node in ast.walk(ast.parse(f.read_bytes())):
            adlar: list[str] = []
            if isinstance(node, ast.Import):
                adlar = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise RelativeImportError(f"{f}: goreli import kapanista cozulemez")
                if node.module:
                    adlar = [node.module] + [f"{node.module}.{n.name}" for n in node.names]
            for m in adlar:
                if m.startswith("src.") and (q := yol(m)):
                    yigin.append(q)
    return tuple(sorted(gorulen))


def _cache_key(symbol: str, exchange: str, train_frac: float) -> str:
    """Kaynak parquet damgalari + import kapanisindaki kodun icerigi."""
    h = hashlib.sha256(f"{symbol}|{exchange}|{train_frac}|{DETECT_TF}|{STATE_TF}".encode())
    base = collect.DATA_ROOT / exchange / collect._safe(symbol)
    for tf in (DETECT_TF, STATE_TF):
        for f in sorted((base / tf).glob("*.parquet")):
            st = f.stat()
            h.update(f"{f.name}|{st.st_mtime_ns}|{st.st_size}".encode())
    for f in _src_closure(SEED, SRC_ROOT):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def load_symbol(
    symbol: str, exchange: str = "bingx", train_frac: float = TRAIN_FRAC
) -> SymbolData | None:
    """`_build_symbol`, sembol basina diske onbelleklenmis hali.

    Yazma atomiktir (`os.replace`): uzun kosu ortasinda oldurulurse yarim pickle
    kalmaz — bozuk onbellegin sessiz hatasi tam da onlenmek istenen sey.
    """
    path = CACHE_ROOT / f"{collect._safe(symbol)}-{_cache_key(symbol, exchange, train_frac)}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())

    sd = _build_symbol(symbol, exchange, train_frac)  # None = veri yok; o da onbelleklenir
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    for eski in CACHE_ROOT.glob(f"{collect._safe(symbol)}-*.pkl"):
        eski.unlink()  # anahtar degisti, eskisi bir daha tutmayacak
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(sd, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, path)
    return sd


def reset_for_rerun(data: list[SymbolData]) -> None:
    """Aynı `SymbolData`'yı ikinci bir koşuda kullanılabilir hâle getirir.

    Motor iki şeyi kalıcı olarak değiştirir: zone'ların durum makinesi ve `ob_alive`
    (ekleme gerekçesi olarak tüketilen OB'ler). Izgara süpürmesinde veri hazırlığı —
    parquet okuma, zone/OB/FVG tespiti, `pierce_time` — hücrelerin **tamamında aynı**
    ve açık ara en pahalı kısım; bu yüzden bir kez yüklenip her hücrede sıfırlanır.

    Zone'lar aynı çapalardan ve aynı `zone_id` ile yeniden kurulur: kimlik korunur,
    durum sıfırlanır.
    """
    for sd in data:
        sd.zones = [
            Zone.create(
                symbol=z.symbol, timeframe=z.timeframe,
                anchor_0_price=z.anchor_0_price, anchor_0_time=z.anchor_0_time,
                anchor_1_price=z.anchor_1_price, anchor_1_time=z.anchor_1_time,
                pivot_confirmed_at=z.pivot_confirmed_at, hysteresis=z.hysteresis,
                zone_id=z.zone_id,
            )
            for z in sd.zones
        ]
        if len(sd.ob_alive):
            sd.ob_alive[:] = True
