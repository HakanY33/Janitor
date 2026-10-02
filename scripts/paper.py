"""Minimal paper döngüsü — ağ kabuğu. `docs/LIVE.md` §2–§4. **Emir göndermez, anahtar istemez.**

    python -m scripts.bg scripts.paper                  # yerel, arka planda
    python -m scripts.paper --kill-kaldir               # R-KILL-01'i insan kaldırır (§6)

Karar, durum ve kayıt `src/live/paper.py`'de (ağsız, test edilir). Burada yalnızca veri:

* **WS 1m kline** (`OPEN-45`): kapanış bayrağı yok. `m` mumu, `m+1`'in ilk mesajı gelince
  kapanmış sayılır. WS **zamanlama ve canlılık** içindir; `step`'e giden mum **REST**'ten
  gelir (backtest verisiyle aynı kaynak). WS'in son görüntüsü kapanmış mumun son hâli
  olmayabilir: WS ↔ REST farkı `DATA` olayı olarak yazılır, kill değildir (`OPEN-47`,
  spec §6).
* **REST 1m / 30m:** bir mum, REST bir sonrakini de döndürünce kesinleşmiş sayılır.
* **Bariyer** `B = 10 sn` · **sessizlik** `P = 30 sn` → yeniden bağlan · **kopma** `60 sn` →
  `R-KILL-01` (`OPEN-48`). REST üstel beklemeyle ~60 sn cevap vermezse `R-KILL-01`.
* **R-KILL-01 toparlanması** (spec §6, 2026-09-30): imleç canlıya yetiştikten sonra
  `TEMIZ_DAKIKA = 10` ardışık temiz canlı dakika (her sembolün REST mumu var, WS bağlı) →
  kill kalkar, `RESUME` olayı. Beklenmeyen hata (kod) kendiliğinden kalkmaz: insan.
* **Yetişme:** imleç geride kaldıysa (ilk başlangıç, yeniden başlatma, gecikme) aradaki
  dakikalar REST'ten alınır ve sırayla işlenir. Paper'da bu kesintisiz koşuyla aynıdır.
* **Isınma yok:** başlangıçtan önce izlemeye girmiş zone izlenmez (`replay.kapanis`
  süzgeci). İlk işlemler yeni zone'larla gelir.
* **Funding:** toplayıcı (`scripts.funding`, sunucuda `janitor-funding.timer`) diske yazar;
  döngü eğrileri her 30m kapanışında diskten tazeler. Son ölçülen funding 9 saatten eskiyse
  `DATA` olayı (`funding_bayat`): o anlar `costs.py` kuralıyla aleyhte atanır, sessizce değil.
* 30m tespiti her kapanışta tüm geçmişte (`OPEN-53`); 20 sembolde dakikalar sürebilir, o
  sürede dakikalar gecikir ama kaybolmaz (REST).

Kayıtlar: `logs/decisions/` (karar logu) · `logs/fills/` (PaperAdapter) ·
`logs/paper/{gün}.log` (kalp atışı: gecikme, pozisyon, equity, bellek) · durum
`data/paper/f1.db`.
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import gzip
import json
import sys
import time
import traceback
from decimal import Decimal
from pathlib import Path

import aiohttp
import numpy as np
import pandas as pd

from scripts.backtest import code_version, spec_version
from scripts.slippage_stres import F1_TABANI
from src.backtest.costs import build_cost_model, load_funding
from src.data import collect
from src.live.paper import DAKIKA, Durum, JsonlGunluk, PaperCore

WS_URL = "wss://open-api-swap.bingx.com/swap-market"
B_SN, P_SN, KOPMA_SN, OTUZ_BEKLE_SN = 10, 30, 60, 120
REST_BEKLE = (2, 4, 8, 16, 30)  # toplam 60 sn, sonra R-KILL-01
TEMIZ_DAKIKA = 10
F1 = dict(start_balance=Decimal("10000"), k=Decimal("0.25"), mmr=Decimal("0.005"),
          t_rahat=Decimal("0.50"), t_kritik=Decimal("0.08"), uyari_blocks_adds=False,
          **F1_TABANI)


def rss_mb() -> float:
    """Süreç belleği (MB) — `OPEN-55` ölçümü. psutil yok: Linux /proc, Windows psapi."""
    try:
        if sys.platform == "win32":
            class PMC(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + \
                           [(n, ctypes.c_size_t) for n in (
                               "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
            c = PMC()
            c.cb = ctypes.sizeof(c)
            k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
            k32.GetCurrentProcess.restype = ctypes.c_void_p  # 64-bit sözde tutamaç
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC),
                                                   ctypes.c_ulong]
            psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
            return c.WorkingSetSize / 2**20
        for satir in open("/proc/self/status"):
            if satir.startswith("VmRSS:"):
                return int(satir.split()[1]) / 1024
    except OSError:
        pass
    return float("nan")


def bellek_birak() -> None:
    """30m tespitinden sonra glibc'nin boş yığınını işletim sistemine geri verir.

    Tespit her kapanışta tüm geçmişi yeniden kurar; büyük geçici tahsis RSS'te kalıyordu
    (parçalanma, referans sızıntısı değil — `SERVER.md` §7). Birimdeki `MALLOC_ARENA_MAX=2`
    ile birlikte. glibc yalnızca Linux'ta: başka platformda iş yok. Linux'ta libc
    yüklenemezse hata yükselir (CLAUDE.md #8).
    """
    if sys.platform.startswith("linux"):
        ctypes.CDLL("libc.so.6").malloc_trim(0)


def ws_adi(s: str) -> str:
    return s.split(":")[0].replace("/", "-")  # BTC/USDT:USDT -> BTC-USDT


def t64(ms: int) -> np.datetime64:
    return np.datetime64(int(ms), "ms").astype("datetime64[ns]")


def ms(t: np.datetime64) -> int:
    return int(t.astype("datetime64[ms]").astype(np.int64))


def rest(ex, s: str, tf: str, since: np.datetime64, limit: int = 1000) -> list:
    """REST OHLCV, üstel bekleme (`REST_BEKLE`, ~60 sn). Sonra hata yükselir (çağıran
    `R-KILL-01` yazar, CLAUDE.md #8)."""
    for bekle in REST_BEKLE:
        try:
            return ex.fetch_ohlcv(s, tf, since=ms(since), limit=limit)
        except Exception:  # noqa: BLE001 — son denemede yükselir
            time.sleep(bekle)
    return ex.fetch_ohlcv(s, tf, since=ms(since), limit=limit)


def kesin_mumlar(ex, s: str, tf: str, since: np.datetime64, kadar: np.datetime64) -> pd.DataFrame:
    """`[since, kadar]` açılışlı, **kesinleşmiş** mumlar (REST sonrakini de döndürdüyse)."""
    satirlar: list = []
    bas = since
    while True:
        r = rest(ex, s, tf, bas)
        if not r:
            break
        satirlar += r
        son = t64(r[-1][0])
        if son >= kadar or len(r) < 2:
            break
        bas = son + np.timedelta64(pd.Timedelta(tf).value, "ns")
    df = pd.DataFrame(satirlar, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts").sort_values("ts")
    if df.empty:
        return df.assign(ts=pd.to_datetime(df.ts, unit="ms", utc=True))
    en_son = df.ts.max()
    df = df[(df.ts < en_son) & (df.ts >= ms(since)) & (df.ts <= ms(kadar))]  # en son: sürüyor
    return df.assign(ts=pd.to_datetime(df.ts, unit="ms", utc=True)).reset_index(drop=True)


class Ws:
    """WS durumu: sembol başına görülen en son mum açılışı ve o mumun son görüntüsü."""

    def __init__(self, semboller: list[str]):
        self.ad = {ws_adi(s): s for s in semboller}
        self.son_T: dict[str, int] = {}
        self.goruntu: dict[tuple[str, int], tuple] = {}
        self.son_mesaj = time.time()
        self.kopuk_bas: float | None = time.time()

    async def calis(self) -> None:
        while True:
            try:
                async with aiohttp.ClientSession() as oturum:
                    async with oturum.ws_connect(WS_URL, heartbeat=None) as ws:
                        for i, a in enumerate(self.ad):
                            await ws.send_str(json.dumps(
                                {"id": f"k{i}", "reqType": "sub", "dataType": f"{a}@kline_1m"}))
                        self.kopuk_bas = None
                        while True:
                            msg = await ws.receive(timeout=P_SN)
                            if msg.type not in (aiohttp.WSMsgType.BINARY, aiohttp.WSMsgType.TEXT):
                                raise ConnectionError(f"ws: {msg.type}")
                            veri = msg.data
                            txt = gzip.decompress(veri).decode() if isinstance(veri, bytes) else veri
                            self.son_mesaj = time.time()
                            if txt == "Ping":
                                await ws.send_str("Pong")
                                continue
                            d = json.loads(txt)
                            s = self.ad.get(d.get("s") or "")
                            for k in d.get("data") or []:
                                T = int(k["T"])
                                self.son_T[s] = max(self.son_T.get(s, 0), T)
                                self.goruntu[(s, T)] = tuple(float(k[x]) for x in "ohlcv")
            except Exception as e:  # noqa: BLE001 — kopma: yeniden bağlan, süre izlenir
                if self.kopuk_bas is None:
                    self.kopuk_bas = time.time()
                print(f"  ws kopuk: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                await asyncio.sleep(2)

    def kopuk_sn(self) -> float:
        sessiz = time.time() - self.son_mesaj
        kopuk = 0.0 if self.kopuk_bas is None else time.time() - self.kopuk_bas
        return max(kopuk, sessiz if sessiz > P_SN else 0.0)


class Dongu:
    def __init__(self, core: PaperCore, ex, ws: Ws, karar: JsonlGunluk, kalp: Path):
        self.core, self.ex, self.ws, self.karar, self.kalp = core, ex, ws, karar, kalp
        self.semboller = core.semboller
        self.temiz = 0  # R-KILL-01'den sonra ardışık temiz canlı dakika
        self.toparlanir = True  # kill kendiliğinden kalkabilir mi (beklenmeyen hata: hayır)

    def kill(self, neden: str, toparlanir: bool = True) -> None:
        self.temiz = 0
        self.toparlanir = self.toparlanir and toparlanir
        if self.core.bt.kill is None:
            self.core.bt.kill = f"R-KILL-01: {neden}"
            self.karar({"ts": pd.Timestamp.now(tz="UTC").isoformat(), "event": "KILL",
                        "outcome": "R-KILL-01", "reason": neden})
            print(f"  R-KILL-01: {neden}", file=sys.stderr, flush=True)

    def izle(self, t: np.datetime64, temiz: bool) -> None:
        """R-KILL-01 toparlanması: `TEMIZ_DAKIKA` ardışık temiz canlı dakikada kill kalkar.

        Yalnızca bu döngünün koyduğu R-KILL-01 kalkar; R-KILL-02/03 ve beklenmeyen hata insan
        ister (spec §6). Temiz olmayan dakika sayacı sıfırlar.
        """
        bt = self.core.bt
        if bt.kill is None:
            self.temiz, self.toparlanir = 0, True
            return
        if not (self.toparlanir and bt.kill.startswith("R-KILL-01")):
            return
        self.temiz = self.temiz + 1 if temiz else 0
        if self.temiz >= TEMIZ_DAKIKA:
            self.karar({"ts": pd.Timestamp(t, tz="UTC").isoformat(), "event": "RESUME",
                        "outcome": "R-KILL-01_KALKTI", "reason": bt.kill,
                        "temiz_dakika": self.temiz})
            print(f"  RESUME: {bt.kill}", file=sys.stderr, flush=True)
            bt.kill, self.temiz = None, 0

    def veri(self, t: np.datetime64, neden: str, **alan) -> None:
        self.karar({"ts": pd.Timestamp(t, tz="UTC").isoformat(), "event": "DATA",
                    "outcome": neden, **alan})

    async def calis(self) -> None:
        while True:
            await asyncio.sleep(1)
            try:
                await self.tur()
            except Exception:  # noqa: BLE001 — beklenmeyen: kayıt + kill, süreç ayakta kalır
                traceback.print_exc()
                self.kill("beklenmeyen hata: " + traceback.format_exc(limit=1).strip()[-200:],
                          toparlanir=False)
                await asyncio.sleep(30)

    async def tur(self) -> None:
        if self.ws.kopuk_sn() > KOPMA_SN:
            self.kill(f"ws {self.ws.kopuk_sn():.0f} sn kopuk")
        simdi = np.datetime64(pd.Timestamp.now(tz="UTC").tz_localize(None), "ns")
        son_kapali = simdi.astype("datetime64[m]").astype("datetime64[ns]") - DAKIKA
        m = self.core.durum.imlec() + DAKIKA
        if m > son_kapali:
            return
        if m == son_kapali:  # canlı: bariyer (§2)
            hepsi = all(self.ws.son_T.get(s, 0) > ms(m) for s in self.semboller)
            if not hepsi and simdi < m + DAKIKA + np.timedelta64(B_SN, "s"):
                return
        try:
            bir = {s: await asyncio.to_thread(kesin_mumlar, self.ex, s, "1m", m, son_kapali)
                   for s in self.semboller}
            for s in self.semboller:
                d30 = self.core.d30[s]
                bas = (np.datetime64(d30.ts.iloc[-1].tz_localize(None), "ns")
                       + np.timedelta64(30, "m")) if len(d30) else m - np.timedelta64(60, "D")
                if bas + np.timedelta64(30, "m") <= son_kapali + DAKIKA:  # yeni 30m kapanmış olabilir
                    self.core.otuz(s, await asyncio.to_thread(kesin_mumlar, self.ex, s, "30m",
                                                              bas, son_kapali))
        except Exception as e:  # noqa: BLE001
            self.kill(f"REST: {type(e).__name__}: {e}"[:200])
            await asyncio.sleep(3)
            return
        # Yalnızca **her** sembolde kesinleşmiş dakikalar işlenir. Hiç mumu gelmeyen sembol
        # 2 dk beklenir, sonra o dakikalar onsuz işlenir (OPEN-46, `DATA` olayı).
        sonlar = [np.datetime64(df.ts.max().tz_localize(None), "ns") for df in bir.values()
                  if len(df)]
        if not sonlar:
            await asyncio.sleep(3)
            return
        bos = [s for s, df in bir.items() if df.empty]
        kadar = min(sonlar)
        if bos and simdi < m + DAKIKA + np.timedelta64(OTUZ_BEKLE_SN, "s"):
            await asyncio.sleep(3)
            return
        mod = "canli" if m == son_kapali else "yetisme"
        self.karar.ek["mod"] = mod
        t = m
        while t <= kadar:
            sinir = (t + DAKIKA).astype("datetime64[m]").astype(int) % 30 == 0
            if sinir and not self.otuz_hazir(t + DAKIKA):
                if simdi < t + DAKIKA + np.timedelta64(OTUZ_BEKLE_SN, "s"):
                    await asyncio.sleep(3)
                    return  # 30m mumu henüz kesin değil; bu dakika sonra işlenir
                self.kill(f"30m mumu gelmedi: kapanış {t + DAKIKA}")
            if sinir:
                self.funding_tazele(t + DAKIKA)
            bars = {}
            temiz = mod == "canli" and self.ws.kopuk_sn() <= P_SN
            for s in self.semboller:
                df = bir[s]
                r = df[df.ts == pd.Timestamp(t, tz="UTC")]
                if r.empty:
                    self.veri(t, "mum_yok", symbol=s)  # OPEN-46: sembol bu dakikayı atlar
                    temiz = False
                    continue
                bars[s] = tuple(float(x) for x in r.iloc[0][["open", "high", "low", "close",
                                                              "volume"]])
                w = self.ws.goruntu.pop((s, ms(t)), None)
                if w is not None and w != bars[s]:
                    self.veri(t, "ws_rest_fark", symbol=s, ws=w, rest=bars[s])
            c0 = time.time()
            # İş parçacığında: 30m tespiti dakikalar sürebilir; WS ping/pong beklemesin.
            self.izle(t, temiz)  # kill kalkarsa bu dakikanın kapanış emirleri de geçerli
            await asyncio.to_thread(self.core.dakika, t, bars)
            if sinir:
                bellek_birak()
            self.kalp_yaz(t, simdi, time.time() - c0, mod)
            t = t + DAKIKA

    def funding_tazele(self, an: np.datetime64) -> None:
        for s in self.semboller:
            c = self.core.bt.costs.funding[s] = load_funding(s)
            if not len(c.times) or c.times[-1] < an - np.timedelta64(9, "h"):
                self.veri(an, "funding_bayat", symbol=s,
                          son=str(c.times[-1])[:16] if len(c.times) else None)

    def otuz_hazir(self, kapanis: np.datetime64) -> bool:
        bar = pd.Timestamp(kapanis - np.timedelta64(30, "m"), tz="UTC")
        return all(len(d) and d.ts.iloc[-1] >= bar for d in self.core.d30.values())

    def kalp_yaz(self, t, simdi, sure, mod) -> None:
        bt = self.core.bt
        satir = {
            "dakika": str(t)[:16], "gecikme_sn": round(float((simdi - t) / np.timedelta64(1, "s")) - 60, 1),
            "islem_sn": round(sure, 2), "mod": mod, "acik": len(bt.pf.positions),
            "equity": round(bt.pf.equity_f(bt.marks), 2), "islem": len(bt.trades),
            "zone_aktif": sum(len(v) for v in bt._active.values()),
            "rss_mb": round(rss_mb(), 1), "kill": bt.kill,
        }
        self.kalp.parent.mkdir(parents=True, exist_ok=True)
        with open(self.kalp.parent / f"{str(t)[:10]}.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Minimal paper döngüsü (F1)")
    p.add_argument("--symbols", nargs="*")
    p.add_argument("--db", default="data/paper/f1.db")
    p.add_argument("--kill-kaldir", action="store_true", help="R-KILL-01'i kaldır (insan)")
    a = p.parse_args()
    from scripts.measure_ob import liquidity_symbols
    semboller = a.symbols or liquidity_symbols(20)
    karar = JsonlGunluk(Path("logs/decisions"),
                        {"spec_version": spec_version(), "code_version": code_version()})
    dolum = JsonlGunluk(Path("logs/fills"))
    durum = Durum(Path(a.db))
    ex = collect.exchange("bingx")
    if durum.oku_snap() is not None:
        core = PaperCore.geri_yukle(durum, karar=karar, dolum=dolum)
        print(f"  geri yüklendi, imleç {durum.imlec()}", file=sys.stderr, flush=True)
    else:
        baslangic = pd.Timestamp.now(tz="UTC").floor("min")
        core = PaperCore.yeni(durum, semboller, build_cost_model(semboller, "bingx"),
                              baslangic, karar=karar, dolum=dolum, **F1)
        son = np.datetime64(baslangic.tz_localize(None), "ns")
        for s in semboller:  # 30m geçmişi: diskteki parquet + REST ile kalan
            d = collect.read_parquet("bingx", s, "30m")
            d = d[d.ts + pd.Timedelta("30m") <= baslangic]
            bas = (np.datetime64(d.ts.iloc[-1].tz_localize(None), "ns") + np.timedelta64(30, "m")
                   if len(d) else son - np.timedelta64(60, "D"))
            ek = kesin_mumlar(ex, s, "30m", bas, son)
            core.otuz(s, pd.concat([d[["ts", "open", "high", "low", "close", "volume"]], ek],
                                   ignore_index=True))
            print(f"  {s}: 30m {len(d)} disk + {len(ek)} REST", file=sys.stderr, flush=True)
        print(f"  yeni başlangıç {baslangic}", file=sys.stderr, flush=True)
    if a.kill_kaldir and core.bt.kill is not None:
        karar({"ts": pd.Timestamp.now(tz="UTC").isoformat(), "event": "KILL",
               "outcome": "KALDIRILDI", "reason": core.bt.kill})
        core.bt.kill = None
    ws = Ws(core.semboller)
    dongu = Dongu(core, ex, ws, karar, Path("logs/paper/kalp.log"))

    async def hepsi():
        await asyncio.gather(ws.calis(), dongu.calis())

    asyncio.run(hepsi())
    return 0


if __name__ == "__main__":
    sys.exit(main())
