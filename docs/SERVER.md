# Sunucu — `spread_logger` kullanıcı servisi

Emir defteri kayıtçısı (`scripts/spread_logger.py`) `179.61.147.81` üzerinde, **`janitor`
kullanıcısının systemd kullanıcı servisi** olarak çalışır. Root altında hiçbir Janitor
süreci yoktur. Kuruluş tarihi 2026-09-25.

Aynı makinede **Minecraft çalışıyor** (`vdsmc` kullanıcısı, `screen` oturumu `purpur`).
Makineyi yeniden başlatma, `apt upgrade` yapma. Güvenlik duvarına ve Minecraft'a dokunma.

| Ne | Nerede |
|---|---|
| Bağlantı | `ssh janitor@179.61.147.81` (yalnızca anahtar, parola kilitli) |
| Kod + veri | `/home/janitor/janitor` (`~/janitor`) |
| Defter verisi | `~/janitor/data/bingx/{sembol}/book/{yyyy-mm}.parquet` |
| Servis | `~/.config/systemd/user/janitor-spread-logger.service` |
| Stdout/stderr | `journalctl --user -u janitor-spread-logger` |
| Sembol hatası (JSONL) | `~/janitor/logs/collect/{tarih}.jsonl` |

`janitor` sudo grubunda değil. Kurulumdan sonraki hiçbir iş root istemez.

---

## Kurulum

### 1 · Root adımı (bir kez, `vdsmc` ile)

Kurulum boyunca root gereken tek adım bu. `vdsmc` bu PC'nin anahtarıyla girer. `sudo`
parolası `vdsmc`'nin parolasıdır ve hiçbir dosyaya yazılmaz.

```bash
ssh -t vdsmc@179.61.147.81
sudo NEEDRESTART_SUSPEND=1 apt-get install -y --no-install-recommends python3-venv
sudo useradd --create-home --shell /bin/bash janitor
sudo install -d -m 700 -o janitor -g janitor /home/janitor/.ssh
sudo tee /home/janitor/.ssh/authorized_keys < /dev/stdin   # bu PC'nin id_ed25519.pub'ı
sudo chown janitor: /home/janitor/.ssh/authorized_keys && sudo chmod 600 /home/janitor/.ssh/authorized_keys
sudo loginctl enable-linger janitor
```

- `apt-get install` önce `apt-get install -s python3-venv` ile simüle edildi: 4 yeni
  paket, **0 yükseltme**.
- `NEEDRESTART_SUSPEND=1`: Ubuntu 24.04'te `needrestart` apt'den sonra servisleri
  yeniden başlatabilir. Bu değişken onu bu çalıştırma için kapatır. Minecraft zaten
  bir servis değil, `vdsmc`'nin oturum scope'unda çalışıyor.
- `enable-linger`: `janitor`'ın kullanıcı systemd'si açılışta, oturum açılmadan kalkar.
  Makine yeniden başlarsa servis kendiliğinden döner.
- `useradd` parola atamaz. Hesap kilitli kalır (`passwd -S janitor` → `L`), yalnızca
  anahtarla girilir.

### 2 · Kod + veri (`janitor`, yerel repo kökünden, Git Bash)

```bash
tar czf - --exclude=__pycache__ src scripts requirements.txt data/bingx/*/book data/bingx/book_manifest.sha256 \
  | ssh janitor@179.61.147.81 'mkdir -p ~/janitor && tar xzf - -C ~/janitor'
ssh janitor@179.61.147.81 'cd ~/janitor && sha256sum -c data/bingx/book_manifest.sha256 && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt'
```

Bütünlük, servis başlamadan **önce** kontrol edildi. 2026-09-25'te 20/20 dosya `OK`
çıktı, satır sayısı 2.404 (yerelle aynı). Servis aynı ay dosyasına yazmaya başlayınca
manifest artık tutmaz. Bu beklenen bir durum.

### 3 · Servis (`janitor`)

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/janitor-spread-logger.service <<"EOF"
[Unit]
Description=Janitor emir defteri kayitcisi (spread + 5 kademe, dakikada bir)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/janitor
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/janitor/.venv/bin/python -m scripts.spread_logger --symbols BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT ZEC/USDT:USDT UNI/USDT:USDT XRP/USDT:USDT AVAX/USDT:USDT BNB/USDT:USDT GALA/USDT:USDT CRV/USDT:USDT NEAR/USDT:USDT HYPE/USDT:USDT SUI/USDT:USDT AAVE/USDT:USDT JUP/USDT:USDT DOGE/USDT:USDT INJ/USDT:USDT RUNE/USDT:USDT DOT/USDT:USDT ORDI/USDT:USDT
# Betik SIGINT (KeyboardInterrupt) ile tamponu yazar; SIGTERM'de finally calismaz.
KillSignal=SIGINT
TimeoutStopSec=60
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now janitor-spread-logger
```

- **`KillSignal=SIGINT`**: betik tamponu yalnızca `KeyboardInterrupt`'ta yazıyor.
  2026-09-25'te test edildi: `restart` → `cikista 40 satir yazildi`.
- **`Restart=always`**: çökme veya açılışta borsaya ulaşılamaması (`load_markets`)
  durumunda servis 10 saniye sonra yeniden başlar.
- **40 sembol (2026-09-30).** Spread ve işlem kayıtçıları orijinal 20'ye soğuk 20'yi
  (`liquidity_soguk.json`, `ohlcv30m` ile aynı liste) ekleyerek 40 sembol kaydeder
  (`HYPOTHESES.md` H1 sembol seti). Eski birimler `*.service.bak20` olarak duruyor. Soğuk
  20'nin defter/işlem kaydı 2026-09-30 10:19 UTC'de başladı.
- **Semboller elle yazıldı.** `liquidity.json` sunucuda yok. Sıralama yeniden yapılsa da
  kayıt listesi sabit kalmalı ki seri kesilmesin. Liste, yereldeki `liquidity.json`'ın
  ilk 20 sembolü (2026-09-25).

### 4 · `earliest` zamanlayıcısı (`janitor`)

Borsanın en eski mumunu günde bir kaydeder: 20 sembol × (1m, 30m) →
`~/janitor/logs/earliest/{tarih}.jsonl` (`scripts/earliest.py`). 2026-09-25'te kuruldu,
elle yapılan ilk koşuda 40 kayıt · 0 hata.

`~/.config/systemd/user/janitor-earliest.service`:

```ini
[Unit]
Description=Janitor en eski mum kaydi (1m + 30m, 20 sembol)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/janitor
Environment=PYTHONUNBUFFERED=1
ExecStart=%h/janitor/.venv/bin/python -m scripts.earliest --symbols <spread_logger ile ayni 20 sembol>
Nice=10
```

`~/.config/systemd/user/janitor-earliest.timer`:

```ini
[Unit]
Description=Janitor en eski mum kaydi, gunde bir

[Timer]
OnCalendar=*-*-* 03:00:00 UTC
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload && systemctl --user enable --now janitor-earliest.timer
```

`Persistent=true`: makine 03:00'te kapalıysa kaçan koşu açılışta yapılır.
Kontrol için `systemctl --user list-timers` ve `journalctl --user -u janitor-earliest -n 5`.
Kayıtları okumak için:
`ssh janitor@179.61.147.81 'cat ~/janitor/logs/earliest/*.jsonl'`

### 5 · 30m artımlı toplama (`janitor`)

Borsanın 30m penceresi günde bir gün kayıyor (`docs/measurements/earliest.md`). Sunucu
arşivi her gün ilerleyerek büyür. `janitor-ohlcv30m.service` 40 sembolde (orijinal 20 +
soğuk 20) `python -m scripts.backfill --timeframe 30m` çalıştırır. Betik artımlıdır:
tamamlanmış ayları atlar, yarım ayı son mumdan sürdürür. Veri
`~/janitor/data/bingx/{sembol}/30m/` altında. Zamanlayıcı `janitor-ohlcv30m.timer` her gün
03:30 UTC'de çalışır (`Persistent=true`). İlk koşu 2026-09-25'te yapıldı: 40/40 sembol,
0 hata. Birim dosyaları 4. adımdakiyle aynı yapıda.

### 6 · İşlem akışı kayıtçısı (`janitor`)

`scripts/trades_logger.py`: BingX herkese açık işlem akışından her işlem (id, zaman,
fiyat, miktar, agresör tarafı). 40 sembol (spread_logger ile aynı liste, 2026-09-30'dan beri), 5 sn'de bir
REST yoklaması, 5 dakikada bir yazım. 2026-09-27'de kuruldu.

| Ne | Nerede |
|---|---|
| Veri | `~/janitor/data/bingx/{sembol}/trades/{yyyy-mm-dd}.parquet` |
| Servis | `~/.config/systemd/user/janitor-trades-logger.service` |
| Kaçırılan işlem | `~/janitor/logs/collect/{tarih}.jsonl`, `"job": "trades_gap"` |

Birim dosyası `janitor-spread-logger.service` ile aynı yapıda (`KillSignal=SIGINT`,
`Restart=always`). Yalnızca `ExecStart` farklı:
`python -m scripts.trades_logger --symbols <spread_logger ile aynı 20 sembol>`.
Kurulumda yalnızca `scripts/trades_logger.py` kopyalandı (`scp`).

- **Geçmiş yok.** Uç yalnızca son 1.000 işlemi verir; `fromId` / `startTime` /
  `endTime` yok sayılır. Veri yalnızca servisin çalıştığı süre boyunca birikir.
- **Boşluk görünürdür.** `fillId` sembol başına ardışık. Kimlik atlarsa kaç işlemin
  kaçırıldığı yazılır. Yeniden başlatmada diskteki son kimlikten devam edilir, aradaki
  boşluk da sayılır.
- **Delta:** `python -m scripts.trades_logger --delta BTC/USDT:USDT 2026-09-27` →
  dakika bazlı `buy`, `sell`, `delta`, `n`, `cum_delta` (`minute_delta`).

## Doğrulama

```bash
ssh janitor@179.61.147.81 'systemctl --user is-active janitor-spread-logger; journalctl --user -u janitor-spread-logger -n 5 --no-pager'
```

Tampon 30 dakikada bir yazılır. Journal'da her 30 dakikada bir `600 satir yazildi`
satırı görünmeli.

## Veriyi PC'ye çekme — günde bir

```powershell
python -m scripts.pull_book
```

- Defter (`book/`) ve işlem (`trades/`) dosyalarını çeker.
- Sunucudaki SHA-256 listesiyle karşılaştırır. Aynı dosyalar atlanır, yalnızca
  değişenler iner (bulunulan ayın dosyası her gün değişir).
- Her dosyayı indirdikten sonra özetini doğrular ve atomik olarak yerine koyar.
- Yerel dosyada sunucuda olmayan bir dakika (defter) ya da `id` (işlem) varsa dosyanın **üzerine yazmaz** ve hata
  koduyla biter.

Günlük çalıştırma için Windows Görev Zamanlayıcı (PowerShell, bir kez):

```powershell
$a = New-ScheduledTaskAction -Execute "python" -Argument "-m scripts.pull_book" -WorkingDirectory "C:\Users\Hakan\Desktop\Projects\Janitor"
$t = New-ScheduledTaskTrigger -Daily -At 09:00
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "Janitor pull_book" -Action $a -Trigger $t -Settings $s
```

`-StartWhenAvailable`: PC saat 09:00'da kapalıysa görev ilk açılışta çalışır. Sunucu
veriyi tuttuğu için bir günlük gecikme veri kaybettirmez.

### 6b · Funding toplayıcısı (`janitor-funding.timer`) — kuruldu 2026-09-30

Paper döngüsü funding eğrilerini her 30m kapanışında diskten okur (`scripts/paper.py`
`funding_tazele`); diske yazan bu zamanlayıcıdır. Yoksa eğri kurulumdaki kopyada donar,
sonraki anlar aleyhte **atanır** ve döngü `DATA` / `funding_bayat` yazar.
`scripts/funding.py` her koşuda `fees.json`'u da yeniler.

`~/.config/systemd/user/janitor-funding.service`: 4. adımdaki `earliest` servisiyle aynı
yapıda (`Type=oneshot`, `Nice=10`), yalnızca
`ExecStart=%h/janitor/.venv/bin/python -m scripts.funding --symbols <spread_logger ile ayni 20 sembol>`.

`~/.config/systemd/user/janitor-funding.timer`:

```ini
[Unit]
Description=Janitor funding orani toplama, 4 saatte bir

[Timer]
OnCalendar=*-*-* 00/4:05:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload && systemctl --user enable --now janitor-funding.timer
systemctl --user start janitor-funding.service   # ilk koşu, paper'dan önce
```

4 saat: 8 saatlik funding anından en geç ~4 saat sonra disktedir; 9 saatlik bayatlık
eşiği bir kaçan koşuyu tolere eder. İlk koşu 2026-09-30 10:19 UTC: 20/20 sembol.

**Bilinen açık:** bazı semboller 4 saatlik funding aralığında (ORDI: 1.000 kayıt yalnızca
2026-04-16'ya iniyor). `costs.py` `FUNDING_INTERVAL = 8h` sabit ızgara kullanıyor; bu
sembollerde funding anlarının yarısı sayılmıyor (`OPEN-59`).

### 7 · Paper döngüsü (`janitor-paper`) — kuruldu 2026-09-30 10:19 UTC

Kullanıcı kararıyla yerel 24 saat bitmeden kuruldu; 24 saatlik ölçüm sunucuda yapılır
(`OPEN-55`). `MemoryMax=700M`: yerel ilk 2 saatin tepesi 459 MB × 1,5 ≈ 690. Emir
göndermez, anahtar yok. 20 sembol (F1 evreni; kayıtçılar 40).

24 saat sonra rapor:

```bash
ssh janitor@179.61.147.81 'cd ~/janitor && .venv/bin/python -m scripts.kalp_ozet'
```

Sunucuda gerekenler (spread/trades kayıtçılarında olmayan): `fees.json`, sembollerin
`funding/` parquet'leri ve onları güncel tutan §6b zamanlayıcısı, `docs/STRATEGY_SPEC.md`
(`spec_version`), sürüm (git yok → `JANITOR_CODE_VERSION`). 30m geçmişi sunucuda zaten
`janitor-ohlcv30m.timer` ile güncel.

```bash
V=$(git rev-parse --short HEAD)$(git diff --quiet || echo +kirli)
tar czf - --exclude=__pycache__ src scripts requirements.txt docs/STRATEGY_SPEC.md \
    data/bingx/fees.json data/bingx/*/funding \
  | ssh janitor@179.61.147.81 'tar xzf - -C ~/janitor'
ssh janitor@179.61.147.81 "cd ~/janitor && .venv/bin/pip install -q -r requirements.txt && echo JANITOR_CODE_VERSION=$V > ~/.config/janitor-paper.env"
```

`~/.config/systemd/user/janitor-paper.service`:

```ini
[Unit]
Description=Janitor paper dongusu (F1, WS 1m + REST 30m)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/janitor
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=%h/.config/janitor-paper.env
ExecStart=%h/janitor/.venv/bin/python -m scripts.paper --symbols <spread_logger ile ayni 20 sembol>
Restart=always
RestartSec=30
MemoryMax=<yerel tepe x 1,5>
Nice=10

[Install]
WantedBy=default.target
```

- **Yeniden başlatma güvenli:** durum `data/paper/f1.db`'de; süreç son anlık görüntüden
  devam eder ve aradaki dakikaları REST'ten yetişir (`docs/LIVE.md` §3).
- **R-KILL-01** kendiliğinden kalkmaz: `systemctl --user stop janitor-paper`, sonra bir kez
  `.venv/bin/python -m scripts.paper --kill-kaldir --symbols ...` (insan kararı, spec §6).
- 30m kapanışlarında tespit 20 sembolde ~3–4 dk CPU alır (`Nice=10`: Minecraft öncelikli).

## Göç planı — Xeon sunucusu

Amaç: kayıtçılar ve paper döngüsü mevcut sunucudan (`179.61.147.81`, Minecraft ile ortak)
Xeon'a taşınır. **Veri serisi kesilmez**: işlem akışının geçmişi yok (son 1.000 işlem),
kaçan dakika kalıcıdır.

### Sıra (bağlayıcı)

1. **Xeon, Minecraft sunucusu kapanmadan önce kurulur.** Eski sunucuya bu süreçte
   dokunulmaz (Minecraft dahil). Kapanış tarihi 48 saatlik örtüşmeye yetmeyecekse ne
   yapılacağı açık (`OPEN-60`).
2. Xeon'da §1–§7 aynen: `janitor` kullanıcısı (sudo yok, `enable-linger`), `~/janitor`,
   `.venv`, birim dosyaları **aynı sembol listeleriyle** (40 kayıtçı, 20 paper/funding).
   Kod aynı `tar` akışıyla; iki sunucuda `sha256sum scripts/*.py src/**/*.py` eşit olmalı.
3. **Tüm kayıtçılar iki sunucuda en az 48 saat örtüşerek çalışır:** `spread-logger`,
   `trades-logger`, `earliest.timer`, `ohlcv30m.timer`, `funding.timer`, `paper`. Xeon'un
   paper'ı ayrı durum dosyasıyla koşar (`--db data/paper/f1_xeon.db`), eski sunucunun
   durumuna dokunmaz.
4. Örtüşme kontrolü (aşağıda) geçerse **geçiş**: `pull_book` / zamanlayıcı Xeon'a döner,
   eski sunucuda servisler `stop` (SIGINT, tampon yazılır), son bir kez eskiden çekilir,
   birleştirilir.
5. Paper devamlılığı: eski `janitor-paper` durdurulur, `data/paper/f1.db` ve `logs/decisions`,
   `logs/fills`, `logs/paper` Xeon'a kopyalanır, Xeon'da `f1_xeon.db` koşusu durdurulup
   `f1.db` ile başlatılır. Aradaki dakikalar REST'ten yetişilir (`LIVE.md` §3) — kill değil.
6. Eski sunucudaki `~/janitor/data` birleştirmeden sonra **silinmez**: özet listesi
   (`sha256sum`) PC'ye alınır, silme ayrı ve açık bir karardır.

### Veri birleştirme

Her sunucu PC'de **ayrı köke** çekilir, doğrudan `data/`'ya değil (`pull_book` üzerine yazma
koruması iki kaynağı çakışma sayıp durur):

```powershell
python -m scripts.pull_book --host janitor@179.61.147.81 --root göç/eski
python -m scripts.pull_book --host janitor@<xeon>       --root göç/xeon
```

| Veri | Anahtar | Birleştirme | Çakışma |
|---|---|---|---|
| İşlem `trades/` | sembol + `id` (`fillId`, ardışık) | birleşim, `id`'ye göre tekil | aynı `id` farklı `ts/price/qty/side` → **hata**, dosya yazılmaz |
| Defter `book/` | sembol + `ts` dakikası | birleşim; aynı dakika iki kaynakta varsa **geçişe kadar eski**, sonra Xeon (kaynak kolonu `host`) | aynı dakikanın farklı değeri beklenir (farklı anlık görüntü) — hata değil, sayılır |
| 30m OHLCV | sembol + `ts` | birleşim | kapanmış mum iki kaynakta farklıysa **hata** (REST aynı mumu vermeli) |
| funding | sembol + `ts` | birleşim | farklı oran → **hata** |
| `earliest` | tarih + sembol + TF | iki sunucunun satırları ayrı saklanır | fark borsanın penceresi hakkında bilgi — raporlanır |

Birleştirme betiği (`scripts/birlestir.py`) **göçten önce** yazılır, sentetik iki kaynakla
test edilir (çakışma, boşluk, tekrar). Şu an yok.

### Tekrar (örtüşme) kontrolü — geçiş kapısı

48 saatlik örtüşme penceresinde, sembol başına:

1. **İşlem akışı:** iki kaynağın `id` kümeleri. Birleşimdeki `id` boşlukları
   (`trades_gap` yöntemi) her kaynağın tek başına boşluğundan **az ya da eşit** olmalı.
   Yalnızca bir kaynakta olan `id` sayısı ve o kaynağın boşluk kaydı eşleşmeli
   (açıklanamayan fark → geçiş yok). Çakışan `id` = 0.
2. **Defter:** dakika kapsaması iki kaynakta ≥ %99; eksik dakikalar `logs/collect/`
   hatalarıyla açıklanmalı.
3. **30m / funding:** çakışan satırlarda fark = 0.
4. **Paper:** iki döngünün karar logunda aynı `(ts, event, symbol, outcome)` kümeleri; fark
   varsa nedeni (REST farkı, `DATA` olayı, kill) yazılmadan geçiş yok.
5. **Disk ve bellek:** Xeon'da `du -sh data/bingx`, `systemctl --user status` bellek
   tepeleri; `kalp_ozet` iki sunucuda.

Sonuç `docs/measurements/goc.md`'ye yazılır; bir madde kalırsa örtüşme uzar, geçiş olmaz.

## İşletim (`janitor` ile)

| İş | Komut |
|---|---|
| Durum | `systemctl --user status janitor-spread-logger` |
| Durdur (tampon yazılır) | `systemctl --user stop janitor-spread-logger` |
| Yeniden başlat | `systemctl --user restart janitor-spread-logger` |
| Son 100 satır | `journalctl --user -u janitor-spread-logger -n 100` |
| Sembol hataları | `tail ~/janitor/logs/collect/$(date -u +%F).jsonl` |
| Kod güncelle | 2. adımdaki `tar` satırını yalnızca `src scripts requirements.txt` ile çalıştır, ardından `restart` |

**Kesinti.** `stop` ve `restart` sırasında tampon yazılır. Kaybolan şey yalnızca
servisin kapalı olduğu dakikalardır. Elektrik kesilmesi veya `kill -9` gibi sert
kapanmada en fazla 30 dakikalık tampon da gider (`--flush-every` ile kısaltılabilir).
