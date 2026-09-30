"""Minimal paper döngüsünün ağsız çekirdeği — `docs/LIVE.md` §2–§6.

Ağ kabuğu (`scripts/paper.py`) kapanmış mumları getirir; karar, durum ve kayıt burada.
Karar kodu backtest'in `Backtest.step`'idir (Ö1), tespit `src/live/replay.kapanis`'tir (A2),
doluş `PaperAdapter` = `SimAdapter` + kayıt (Ö2, §4). `if paper_mode:` dalı yoktur.

**Durum (§3).** SQLite: gelen her kapanmış 1m ve 30m mum, imleç ve 30m kapanışlarında
motorun anlık görüntüsü. Bir dakikanın mumları ve imleç **tek transaction**'da yazılır.
Yeniden başlatma = son anlık görüntü + ondan sonraki kayıtlı dakikaların aynı `dakika`'dan
yeniden geçirilmesi. Paper'da borsa tarafı olmadığından bu, kesintisiz koşuyla aynı sonucu
verir (`tests/test_paper.py`, D2).

**Karar logu (`OPEN-54`).** Motor `ENTRY`, `ENTRY_REJECTED`, `EXIT` yazar (backtest'le aynı
satırlar). Çekirdek her kapanışta bekleyen emirleri **hevesle** hesaplar ve `ORDER`
(koy / iptal / yenile) ile `NO_ACTION` yazar; ağ kabuğu `DATA` ve `KILL` yazar.
`decision_id` satır içeriğinin `uuid5`'idir: çökmeden sonra yeniden yazılan satır aynı
kimliği taşır, okuyan tekilleştirir.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import Backtest
from src.execution.adapter import SimAdapter
from src.features.ids import NAMESPACE
from src.live.replay import TD, bos_sembol, kapanis
from src.zones.model import ZoneState as S

DAKIKA = np.timedelta64(1, "m")
KOVA30 = np.timedelta64(30, "m")


def _ns(t) -> int:
    return int(pd.Timestamp(t).value)


def _ts(ns: int) -> np.datetime64:
    return np.datetime64(int(ns), "ns")


class JsonlGunluk:
    """`{kok}/{yyyy-mm-dd}.jsonl`'e satır ekler (append-only). Gün satırın `ts`'inden."""

    def __init__(self, kok: Path, ek: dict | None = None):
        self.kok = Path(kok)
        self.kok.mkdir(parents=True, exist_ok=True)
        self.ek = ek or {}

    def __call__(self, satir: dict) -> None:
        satir = {**satir, **self.ek}
        govde = json.dumps(satir, sort_keys=True, default=str, ensure_ascii=False)
        satir = {"decision_id": uuid.uuid5(NAMESPACE, govde).hex, **satir}
        gun = str(satir.get("ts", ""))[:10] or "tarihsiz"
        with open(self.kok / f"{gun}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, default=str, ensure_ascii=False) + "\n")


class PaperAdapter(SimAdapter):
    """`SimAdapter` (P1) + giriş doluş denetimlerinin kaydı (`docs/LIVE.md` §4).

    Seviyeye ulaşan (dolan ya da P1'e göre dolmayan) her giriş denetimi bir satırdır;
    defter ve işlem akışı sonradan `ts` + sembol + seviye ile eşlenir. Doluş kararı
    `SimAdapter`'ınkiyle aynıdır — paper doluş sorusunu çözmez, veri biriktirir.
    """

    @classmethod
    def sar(cls, sim: SimAdapter, kayit) -> PaperAdapter:
        p = cls.__new__(cls)
        p.__dict__.update(sim.__dict__)
        p.kayit, p.an = kayit, None
        return p

    def entry_filled(self, symbol, level, high, low, close, sell) -> bool:
        dolu = super().entry_filled(symbol, level, high, low, close, sell)
        if self.kayit is not None:
            self.kayit({"ts": pd.Timestamp(self.an, tz="UTC").isoformat(), "symbol": symbol,
                        "tur": "giris", "taraf": "sell" if sell else "buy", "seviye": level,
                        "high": high, "low": low, "close": close, "p1_doldu": dolu})
        return dolu

    def __getstate__(self) -> dict:
        d = self.__dict__.copy()
        d["kayit"] = None
        return d


class Durum:
    """SQLite durumu. Mumlar ns tamsayı damgayla (açılış), imleç = işlenen son dakika."""

    def __init__(self, yol: Path):
        Path(yol).parent.mkdir(parents=True, exist_ok=True)
        # Ağ kabuğu `dakika`'yı iş parçacığında koşturur (tespit uzun sürer). Bağlantı
        # aynı anda tek iş parçacığından kullanılır (döngü onu bekler), eşzamanlı değil.
        self.db = sqlite3.connect(yol, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS bar1 (sym TEXT, ts INTEGER, o REAL, h REAL, l REAL,
                c REAL, v REAL, PRIMARY KEY (sym, ts));
            CREATE TABLE IF NOT EXISTS bar30 (sym TEXT, ts INTEGER, o REAL, h REAL, l REAL,
                c REAL, v REAL, PRIMARY KEY (sym, ts));
            CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS snap (id INTEGER PRIMARY KEY, imlec INTEGER, blob BLOB);
        """)

    def meta(self, k: str) -> str | None:
        r = self.db.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return r[0] if r else None

    def imlec(self) -> np.datetime64 | None:
        v = self.meta("imlec")
        return None if v is None else _ts(int(v))

    def yaz_30(self, sym: str, df: pd.DataFrame) -> None:
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO bar30 VALUES (?,?,?,?,?,?,?)",
                [(sym, _ns(r.ts), r.open, r.high, r.low, r.close, r.volume)
                 for r in df.itertuples()])

    def oku_30(self, sym: str) -> pd.DataFrame:
        df = pd.read_sql("SELECT ts, o AS open, h AS high, l AS low, c AS close, v AS volume "
                         "FROM bar30 WHERE sym = ? ORDER BY ts", self.db, params=(sym,))
        df["ts"] = pd.to_datetime(df.ts, unit="ns", utc=True)
        return df

    def yaz_dakika(self, t: np.datetime64, bars: dict[str, tuple], meta: dict) -> None:
        """Dakikanın mumları + imleç + meta, tek transaction (§3 yazma kuralı)."""
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO bar1 VALUES (?,?,?,?,?,?,?)",
                                [(s, _ns(t), *b) for s, b in bars.items()])
            for k, v in {**meta, "imlec": str(_ns(t))}.items():
                self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, v))

    def dakikalar(self, sonra: np.datetime64, kadar: np.datetime64):
        """`(sonra, kadar]` aralığındaki kayıtlı dakikalar, sırayla: (t, {sym: bar})."""
        rows = self.db.execute(
            "SELECT ts, sym, o, h, l, c, v FROM bar1 WHERE ts > ? AND ts <= ? ORDER BY ts, sym",
            (_ns(sonra), _ns(kadar))).fetchall()
        t, bars = None, {}
        for ts, sym, *b in rows:
            if t is not None and ts != t:
                yield _ts(t), bars
                bars = {}
            t = ts
            bars[sym] = tuple(b)
        if t is not None:
            yield _ts(t), bars

    def yaz_snap(self, imlec: np.datetime64, blob: bytes) -> None:
        with self.db:
            self.db.execute("DELETE FROM snap")
            self.db.execute("INSERT INTO snap (imlec, blob) VALUES (?, ?)", (_ns(imlec), blob))

    def oku_snap(self) -> tuple[np.datetime64, bytes] | None:
        r = self.db.execute("SELECT imlec, blob FROM snap").fetchone()
        return None if r is None else (_ts(r[0]), r[1])


class PaperCore:
    """Bir kapanmış dakikayı işler. Ağ bilmez; testte sentetik mumla beslenir."""

    def __init__(self, bt: Backtest, durum: Durum, baslangic: pd.Timestamp,
                 karar=None, dolum=None):
        self.bt, self.durum, self.baslangic = bt, durum, baslangic
        self.semboller = list(bt.data)
        self.d30 = {s: durum.oku_30(s) for s in self.semboller}
        self.uygulanan = {s: 0 for s in self.semboller}  # tespite verilmiş 30m mum sayısı
        self.emirler: dict[str, tuple | None] = {}  # zone -> son bildirilen emir
        self.karar_yazici = karar
        self.baglan(karar, dolum)

    def baglan(self, karar, dolum) -> None:
        self.karar_yazici = karar
        self.bt.log = karar
        if isinstance(self.bt.exec, PaperAdapter):
            self.bt.exec.kayit = dolum

    @classmethod
    def yeni(cls, durum: Durum, semboller: list[str], costs, baslangic: pd.Timestamp,
             karar=None, dolum=None, **kw) -> PaperCore:
        bt = Backtest([bos_sembol(s) for s in semboller], costs, **kw)
        bt.exec = PaperAdapter.sar(bt.exec, dolum)
        bt.start()
        durum.yaz_dakika(np.datetime64(baslangic.tz_convert("UTC").tz_localize(None)) - DAKIKA,
                         {}, {"baslangic": baslangic.isoformat()})
        return cls(bt, durum, baslangic, karar, dolum)

    @classmethod
    def geri_yukle(cls, durum: Durum, karar=None, dolum=None) -> PaperCore:
        """Son anlık görüntü + sonraki kayıtlı dakikalar. Görüntü yoksa baştan oynatılır."""
        snap = durum.oku_snap()
        if snap is None:
            raise RuntimeError("anlık görüntü yok — ilk 30m kapanışından önce çökmüş; "
                               "durum dosyası silinip yeni başlatılmalı")
        imlec_snap, blob = snap
        durum_ = pickle.loads(blob)
        core = cls.__new__(cls)
        core.__dict__.update(durum_)
        core.durum = durum
        core.d30 = {s: durum.oku_30(s) for s in core.semboller}
        core.baglan(None, None)  # yeniden oynatılan dakikaların satırları zaten yazıldı
        for t, bars in durum.dakikalar(imlec_snap, durum.imlec()):
            core.dakika(t, bars, kaydet=False)
        core.baglan(karar, dolum)
        return core

    def otuz(self, sym: str, df: pd.DataFrame) -> None:
        """Yeni kapanmış 30m mumları. Tespite `dakika` içinde, kapanış anı gelince verilir."""
        if df.empty:
            return
        self.durum.yaz_30(sym, df)
        self.d30[sym] = self.durum.oku_30(sym)

    def dakika(self, t: np.datetime64, bars: dict[str, tuple], kaydet: bool = True) -> None:
        """Kapanmış 1m dakikası `t` (açılış). `bars`: {sym: (o, h, l, c, v)}.

        Sıra: `t`'ye kadar kapanan 30m'ler tespitte → `step(t)` → `t + 1m`'de kapanan 30m'ler
        tespite → o kapanıştaki emirler. Emirler, kapanışta bilinen her şeyi görmeli
        (gösterge önbelleği 30m kovası başına bir kez hesaplar).
        """
        self._tespit(t)
        if isinstance(self.bt.exec, PaperAdapter):
            self.bt.exec.an = t
        self.bt.step(t, bars)
        self._tespit(t + DAKIKA)
        self._emir_olaylari(t + DAKIKA)
        if kaydet:
            self.durum.yaz_dakika(t, bars, {})
        if (t + DAKIKA).astype("datetime64[m]").astype(int) % 30 == 0:
            self.durum.yaz_snap(t, pickle.dumps(self._goruntu(), pickle.HIGHEST_PROTOCOL))

    def _tespit(self, an: np.datetime64) -> None:
        """Kapanışı `≤ an` olan 30m mumları artımlı tespite verir (A2, `replay.oynat` ile aynı)."""
        for s in self.semboller:
            kapanislar = (self.d30[s].ts + TD).dt.tz_convert("UTC").dt.tz_localize(None)
            n = int(np.searchsorted(kapanislar.to_numpy(), an, side="right"))
            if n > self.uygulanan[s]:
                self.uygulanan[s] = n
                kapanis(self.bt, s, self.d30[s].iloc[:n].reset_index(drop=True),
                        self.baslangic)

    def _goruntu(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()
             if k not in ("durum", "d30", "karar_yazici")}
        return d

    def _emir_olaylari(self, kapanis_an: np.datetime64) -> None:
        """Her kapanışta bekleyen emirler (`OPEN-41`, `order_for`) ve `NO_ACTION`.

        Kayıttır, karar değildir: dolum backtest'teki tembel yoldan olur ve aynı saf
        fonksiyonu çağırır. Emir defteri (`self.emirler`) yazıcı yokken de güncellenir:
        yeniden oynatmadan sonra aynı emir ikinci kez "KOY" diye yazılmasın.
        """
        yaz = self.karar_yazici or (lambda satir: None)
        at = pd.Timestamp(kapanis_an, tz="UTC")
        yazilan: set[str] = set()
        canli: set[str] = set()
        for s in self.semboller:
            sd = self.bt.data[s]
            for z in self.bt._active.get(s, []):
                if z.state not in (S.PRIMED, S.TOUCHED):
                    continue
                canli.add(z.zone_id)
                emir, neden = self.bt.order_for(z, sd, at)
                yeni = None if emir is None else (emir["hedef"], str(emir["qty"]))
                eski = self.emirler.get(z.zone_id)
                if yeni != eski:
                    eylem = "KOY" if eski is None else ("IPTAL" if yeni is None else "YENILE")
                    yaz({
                        "ts": at.isoformat(), "symbol": s, "event": "ORDER", "zone_id": z.zone_id,
                        "outcome": eylem, "reason": neden,
                        "orders": [] if yeni is None else [{"fiyat": yeni[0], "qty": yeni[1],
                                                            "tur": "giris", "limit": True}]})
                    self.emirler[z.zone_id] = yeni
                    yazilan.add(s)
        for zid in [z for z, e in self.emirler.items() if z not in canli]:
            if self.emirler.pop(zid) is not None:
                yaz({"ts": at.isoformat(), "event": "ORDER", "zone_id": zid,
                                   "outcome": "IPTAL", "reason": "zone_bitti"})
        for s in self.semboller:
            bakildi = s in self.bt.pf.positions or any(
                z.state in (S.PRIMED, S.TOUCHED) for z in self.bt._active.get(s, []))
            if bakildi and s not in yazilan:
                yaz({"ts": at.isoformat(), "symbol": s, "event": "NO_ACTION",
                                   "outcome": "NO_ACTION"})
