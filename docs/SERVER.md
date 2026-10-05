# Sunucu — `spread_logger` kullanıcı servisi

> **2026-10-05 · Sunucu 12 Ekim'de kapanıyor, yeni sunucu alınmayacak (kullanıcı).** Kayıt PC'ye
> taşınıyor: aşağıda **"Sunucu kapanışı — PC'ye geçiş"**. TR-SSD 2 göç planı iptal. Bu belgenin
> geri kalanı 10-12'ye kadar çalışan sunucunun kaydıdır.

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

**`OPEN-59` kapandı (2026-09-30).** Funding anları artık sembolün borsadan gelen aralığıyla
(`fundingIntervalHours`, `fees.json` → `funding_h`): kapsam içinde ölçülen anlar, dışında o
aralıkla ızgara. 40 sembolün **12'si 4 saatlik** (HYPE, JUP, ORDI, ENA, KAS, WIF, BANANA,
NOT, IMX, ETHFI, 1000BONK, TURBO). `funding_h` yoksa `load_funding` hata verir.

**Kod güncellemesinde sıra:** yeni kod → önce `systemctl --user start janitor-funding.service`
(`fees.json`'a `funding_h` yazar) → sonra `restart janitor-paper`. Tersi sırada paper'ın
ilk funding tazelemesi `KeyError` ile düşer. Zamanlayıcı `--symbols` ile yalnızca 20 sembol
yazıyor; H1 (40 sembol) maliyet modelini yerel `fees.json`'dan (40) okur — sunucudaki
dosya PC'ye çekilirse üzerine yazmasın ya da zamanlayıcı 40 sembole genişletilsin.

### 7 · Paper döngüsü (`janitor-paper`) — kuruldu 2026-09-30 10:19 UTC · **DURDURULDU 2026-10-01**

> **Durduruldu ve devre dışı (2026-10-01 14:10 UTC, kullanıcı).** Bellek büyümesi
> `MemoryMax=700M`'yi her ~1,5 saatte aşıyordu (`paper_yeniden.log`: 11:36 ve 13:06
> `oom-kill`); makinede swap kullanımı Minecraft'la ortak belleği sıkıştırıyordu.
> `systemctl --user stop` + `disable`: ne `Restart=always` ne açılış onu geri getirmez.
>
> **Kural (kullanıcı, 2026-10-01):** paper **hiçbir sunucuda** çalışmaz, ta ki **ardışık
> 3 tespit döngüsünde bellek düz** kalana kadar. Bu sunucuda (Minecraft) paper **kapalı
> kalır**. TR-SSD 2'de kabul ölçümü göç sırasının 3. adımıdır (`scripts/sizinti.py`).
>
> **Teşhis (2026-10-01, lokal, `scripts/sizinti.py --iz`):** referans sızıntısı yok
> (tracemalloc Δ döngü 2–3: +0,03 / +0,02 MB). Her 30m kapanışı tüm geçmişi yeniden
> kuruyor; büyük geçici tahsis iş parçacığında (`to_thread`) yapılıyor → glibc
> parçalanması. **İki satırlık önlem:** birimde `MALLOC_ARENA_MAX=2`, her 30m tespitinden
> sonra `malloc_trim(0)` (`scripts/paper.py` `bellek_birak`, yalnızca Linux). Yetmezse
> artımlı tespit (`LIVE.md` §2 "Artımlı tespit — ertelendi").

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
# glibc arena sayisini sinirlar; 30m tespitinden sonra malloc_trim(0) ile birlikte (2026-10-01)
Environment=MALLOC_ARENA_MAX=2
EnvironmentFile=%h/.config/janitor-paper.env
ExecStart=%h/janitor/.venv/bin/python -m scripts.paper --symbols <spread_logger ile ayni 20 sembol>
Restart=always
RestartSec=30
# Gecici onlem (2026-09-30): bellek buyumesi arastirilirken 4 saatte bir kayitli durumdan
# yeniden baslar (D2). Her baslama ve durus logs/paper_yeniden.log'a yazilir.
RuntimeMaxSec=4h
ExecStartPre=/bin/sh -c 'echo "$(date -u +%%FT%%TZ) basladi" >> %h/janitor/logs/paper_yeniden.log'
ExecStopPost=/bin/sh -c 'echo "$(date -u +%%FT%%TZ) durdu sonuc=$SERVICE_RESULT kod=$EXIT_CODE/$EXIT_STATUS" >> %h/janitor/logs/paper_yeniden.log'
MemoryMax=<yerel tepe x 1,5>
Nice=10

[Install]
WantedBy=default.target
```

- **Yeniden başlatma güvenli:** durum `data/paper/f1.db`'de; süreç son anlık görüntüden
  devam eder ve aradaki dakikaları REST'ten yetişir (`docs/LIVE.md` §3).
- **`MALLOC_ARENA_MAX=2`** (2026-10-01): mevcut sunucunun birim dosyasına da eklendi
  (`daemon-reload`, servis başlatılmadı; yedek `janitor-paper.service.bak-arena`).
  `malloc_trim(0)` kodda, birimde değil.
- **`RuntimeMaxSec=4h` geçici** (2026-09-30, kullanıcı): bellek büyümesi çözülene kadar.
  `logs/paper_yeniden.log` satırları: `durdu sonuc=timeout` = planlı 4 saat, `oom-kill` =
  bellek sınırı, `exit-code` = süreç hatası. Kalkınca bu satırlar birimden silinir.
- **Kod hatasından doğan R-KILL-01** kendiliğinden kalkmaz (veri kaynaklı olan kalkar, spec §6):
  `systemctl --user stop janitor-paper`, sonra bir kez
  `.venv/bin/python -m scripts.paper --kill-kaldir --symbols ...` (insan kararı, spec §6).
- 30m kapanışlarında tespit 20 sembolde ~3–4 dk CPU alır (`Nice=10`: Minecraft öncelikli).

## PC yedek planı — sunucu uzatılmazsa

Amaç: H1 dilimi (10-01 → 12-31, uzarsa 03-31) boyunca işlem akışı kaydı **kesintisiz**.
İşlem akışının geçmişi yok (son 1.000 işlem); PC'nin kapalı olduğu her dakika kalıcı kayıptır
ve H1'de o temas `dislandi_bosluk` olur. Aşağıdakilerin hepsi yönetici PowerShell'inde, bir kez.

**Ön koşul (2026-10-05'te değişti).** Sunucu ile PC artık **aynı anda** kaydeder: PC ayrı köke
(`-Kok göç\pc\data`) yazar, `scripts/birlestir.py` ikisini `id`'ye göre birleştirir. Sıra
aşağıda "Sunucu kapanışı — PC'ye geçiş". Aşağıdaki 1–4. adımlar (uyku, güncelleme, açılış
görevi, boşluk izleme) geçerliliğini korur; görev kaydında `-Kok` parametresi geçiştekiyle aynı olmalı.

**1 · Uyku, hazırda bekletme, kapak.**

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /hibernate off                       # hızlı başlatmayı da kapatır
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # kapak: hiçbir şey yapma
powercfg /setactive SCHEME_CURRENT
powercfg /a                                   # doğrula: "Hibernate" yok
```

Yalnızca prizde (`-ac`); pilde uyumak doğru davranıştır. Ağ bağdaştırıcısında "güç tasarrufu
için bu aygıtı kapat" (Aygıt Yöneticisi → ağ kartı → Güç Yönetimi) kaldırılır.

**2 · Windows Update yeniden başlatması.** Önlenemez, yalnızca ertelenir ve **kurtarılır**:

```powershell
$k = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
New-Item $k -Force | Out-Null
Set-ItemProperty $k NoAutoRebootWithLoggedOnUsers 1 -Type DWord   # oturum açıkken zorla yok
```

Ayarlar → Windows Update → Etkin saatler: el ile 18 saatlik pencere. Asıl güvence 3. adım:
yeniden başlatma olsa da kayıtçı **oturum açılmadan** geri gelir. Kesintiyi bir yeniden başlatma
süresine (~2–5 dk) indirir, sıfırlamaz.

**3 · Kayıtçılar Windows açılışında (oturum açmadan).** `scripts/pc_kayit.ps1` kayıtçıyı
döngüde çalıştırır: çıkarsa (ağ, hata) 30 sn sonra yeniden, her çıkış `logs/pc-*.log`'a.

```powershell
$dir = "C:\Users\Hakan\Desktop\Projects\Janitor"
$py  = (Get-Command python).Source
$p   = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
$set = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew `
         -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
         -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$t   = New-ScheduledTaskTrigger -AtStartup
foreach ($k in "trades", "spread") {
  $a = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $dir -Argument `
         "-NoProfile -ExecutionPolicy Bypass -File scripts\pc_kayit.ps1 -Kayitci $k -Python `"$py`""
  Register-ScheduledTask -TaskName "Janitor $k" -Action $a -Trigger $t -Principal $p -Settings $set
}
Start-ScheduledTask "Janitor trades"; Start-ScheduledTask "Janitor spread"
```

`S4U`: oturum açılmadan, parola saklamadan çalışır (yalnızca genel internete çıkar, yeter).
`IgnoreNew`: ikinci kopya açılmaz — aynı sembolü iki süreç yazmaz. `ExecutionTimeLimit 0`:
72 saat sonra öldürülmez. Durdurmak: `Stop-ScheduledTask "Janitor trades"` (tampon en fazla
`--flush-every` = 5 dk kaybolur). Sembol listesi betikte: `liquidity.json` ilk 20 +
`liquidity_soguk.json` ilk 20 = sunucudaki 40.

Doğrulama: yeniden başlat, **oturum açmadan** 5 dk bekle, sonra
`Get-ScheduledTask "Janitor *" | Get-ScheduledTaskInfo` (`LastTaskResult` 267009 = çalışıyor) ve
en yeni `data\bingx\*\trades\*.parquet` zamanı.

**4 · Boşluk izleme.** Kayıtçı her `fillId` atlamasını `logs/collect/{gün}.jsonl`'a
`trades_gap` olarak yazar. Günlük (içerik değil, yalnızca bütünlük — H1 §6):

```powershell
$g = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
Select-String "logs\collect\$g.jsonl" -Pattern '"trades_gap"' | Measure-Object | % Count
Get-ChildItem data\bingx\*\trades\$g.parquet | Sort LastWriteTime | Select -First 3 Name, LastWriteTime
Select-String "logs\pc-trades-*.log" -Pattern "cikti" | Select -Last 5    # yeniden başlamalar
```

Alarm eşiği: en eski dosyanın `LastWriteTime`'ı 10 dk'dan eskiyse (yazım 5 dk'da bir) o
sembolün kaydı durmuş; `cikti` satırı sık görünüyorsa ağ ya da borsa sorunu.

**Bilinen sınırlar.** Elektrik kesintisi (UPS yok) ve ev interneti kopması kapsanmaz;
ikisi de `trades_gap` olarak sayılır. Paper döngüsü bu plana dahil değil (H1 için gerekmez).

## Sunucu kapanışı — PC'ye geçiş (2026-10-05)

Sunucu **2026-10-12**'de kapanıyor, yerine sunucu yok. H1 dilimi (10-01 → 12-31) işlem akışını
PC kaydeder. Paper taşınmaz (2026-10-01'den beri kapalı). Sıra:

| # | Ne | Durum |
|---|---|---|
| 1 | PC kayıtçıları **ayrı köke**: `scripts\pc_kayit.ps1 -Kayitci trades` / `spread -Kok göç\pc\data` (`JANITOR_DATA_ROOT`). Ayrı kök şart: `data/`'da sunucudan çekilmiş bugünkü dosyalar var; PC onlara eklerse ortak `id` sayısı şişer ve `pull_book` çakışıp durur | **Başladı 2026-10-05 06:37 UTC** (gizli konsolla ayrık süreç; oturum kapanınca/yeniden başlatmada **durur**) |
| 2 | Paralel kayıt doğrulaması: sunucunun bugünkü işlem dosyaları ayrı köke (`göç/kontrol`), `birlestir --kaynak sunucu=göç/kontrol --kaynak pc=göç/pc --hedef göç/bos --kuru` | **Geçti 2026-10-05 06:50 UTC: 40/40 sembolde ortak `id`** (sembol başına ~2.400–5.900), çakışma 0, PC'de eksik `id` 0 |
| 3 | **Kullanıcı (yönetici PowerShell):** açılış görevleri — "PC yedek planı" 1–3. adımlar, `-Argument` sonuna `-Kok göç\pc\data`. Önce 1. satırdaki süreçleri durdur (aynı sembolü iki süreç yazmasın): `Get-CimInstance Win32_Process \| ? CommandLine -like '*pc_kayit*' \| % { Stop-Process $_.ProcessId }` ve alt `python` süreçleri; sonra `Start-ScheduledTask`. Durdurma–başlatma arası birkaç saniye: kayıtçı açılışta son 1.000 işlemi çeker | bekliyor |
| 4 | **Sunucudaki zamanlayıcıların PC karşılığı** (sunucu kapanınca dururlar): `funding` (4 saatte bir, `python -m scripts.funding`), `ohlcv30m` (günde bir), `earliest` (günde bir). Görev Zamanlayıcı'da kullanıcı görevi; komutlar §4–§6b'deki `ExecStart` satırlarıyla aynı | bekliyor (karar: kullanıcı) |
| 5 | 10-05 → 10-11: günlük `pull_book` **`data/`'ya değil** `--root göç/eski`'ye (ya da hiç). Sunucunun dosyası 5 dk'da bir yeniden yazıldığı için toplu `tar` çıkış 2 verebilir (2026-10-05'te görüldü); o gün tekrar dene | — |
| 6 | **2026-10-11 — son çekim.** (a) Sunucuda kayıtçıları durdur, tampon yazılsın: `systemctl --user stop janitor-trades-logger janitor-spread-logger` + `systemctl --user stop janitor-earliest.timer janitor-ohlcv30m.timer janitor-funding.timer`. (b) `python -m scripts.pull_book --root göç/eski` (artık dosya değişmez, toplu `tar` tutar). (c) `ssh janitor@179.61.147.81 'cd janitor && tar cf - data logs' > göç/eski/tum.tar` — 30m, funding, earliest, loglar dahil **her şey**; PC'de `tar tf` ile sayım + `ssh ... 'cd janitor && find data -type f \| xargs sha256sum' > göç/eski/manifest.sha256` ve yerelde `sha256sum -c`. (d) `birlestir --kaynak eski=göç/eski --kaynak pc=göç/pc --gecis <a'daki durdurma anı> --kuru` → 40/40 ortak `id`, hata 0 → yaz (hedef `data/`). (e) PC görevlerini durdur, `-Kok data` ile yeniden kaydet ve başlat; `birlestir`'i bir kez daha koş (aradaki `göç/pc` artığı, idempotent) | 10-11 |
| 7 | 10-12: sunucu kapanır. Sunucudaki veri silinmez; manifest PC'de | 10-12 |

Sonuç `docs/measurements/goc.md`'ye: 2. ve 6d'nin raporları, son çekim anı, sha256 sonucu.

## Göç planı — verunix TR-SSD 2 (Ubuntu 24.04) · **İPTAL 2026-10-05**

> Yeni sunucu alınmayacak (kullanıcı). Bölüm yalnızca kayıt için; yerine "Sunucu kapanışı — PC'ye geçiş".

Amaç: kayıtçılar ve paper döngüsü mevcut sunucudan (`179.61.147.81`, Minecraft ile ortak)
TR-SSD 2'ye taşınır. **Veri serisi kesilmez**: işlem akışının geçmişi yok (son 1.000 işlem),
kaçan dakika kalıcıdır.

**Süre (kullanıcı, 2026-09-30).** Sabit tarih yok. Kurulum (§0–§7) yaklaşık **bir saat**.
**Örtüşme**, TR-SSD 2'de kayıtçılar başladıktan eski sunucu kapanana kadar geçen süredir —
ne kadarsa o kadar. **Asgari şart:** iki sunucunun paralel kaydı doğrulanmış olmalı, yani
**aynı işlem kimlikleri (`fillId`) iki tarafta da görünüyor** (`birlestir --kuru` →
"iki sunucuda ortak id" her sembolde > 0). Bu şart sağlanmadan eski sunucu kapanırsa göç
"doğrulanmamış" olarak kaydedilir. `OPEN-60` bu kuralla kapandı.

### 0 · İlk adım: BingX API erişimi (TR-SSD 2 hazır olunca, kurulumdan önce)

Sunucu Türkiye'de; BingX'in o IP'den erişilebilir olduğu **varsayılmaz**. Kurulumdan önce,
`root`/ilk kullanıcıyla, venv gerekmeden:

```bash
for u in "https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex?symbol=BTC-USDT" \
         "https://open-api.bingx.com/openApi/swap/v2/quote/trades?symbol=BTC-USDT&limit=5" \
         "https://open-api.bingx.com/openApi/swap/v2/quote/depth?symbol=BTC-USDT&limit=5" \
         "https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol=BTC-USDT&interval=30m&limit=2"; do
  curl -sS -m 15 -o /tmp/b.json -w "%{http_code} %{time_total}s " "$u"; head -c 120 /tmp/b.json; echo
done
python3 - <<'PY'   # WS (paper): el sıkışma, yalnızca stdlib
import asyncio, ssl
async def main():
    r, w = await asyncio.wait_for(asyncio.open_connection("open-api-swap.bingx.com", 443,
                                  ssl=ssl.create_default_context()), 15)
    w.write(b"GET /swap-market HTTP/1.1\r\nHost: open-api-swap.bingx.com\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n")
    print((await asyncio.wait_for(r.readline(), 15)).decode().strip())
asyncio.run(main())
PY
```

Geçer: dört REST satırı `200` ve JSON'da `"code":0`, WS satırı `HTTP/1.1 101`. `403`/`451`,
coğrafi engel mesajı ya da zaman aşımı → **kurulum yapılmaz**, sunucu H1 için kullanılamaz
(işlem akışı REST'ten); karar kullanıcının. Kurulumdan sonra ayrıca `.venv` ile ccxt yoklaması:
`.venv/bin/python -c "import ccxt; e=ccxt.bingx(); e.load_markets(); print(len(e.fetch_trades('ORDI/USDT:USDT')), e.fetch_funding_rate('ORDI/USDT:USDT')['info']['fundingIntervalHours'])"`.

### Sıra (bağlayıcı, kullanıcı 2026-10-01)

Eski sunucuya bu süreçte dokunulmaz (Minecraft dahil). TR-SSD 2 olabildiğince erken kurulur
(örtüşme o kadar uzar). `janitor` kullanıcısı (sudo yok, `enable-linger`), `~/janitor`,
`.venv`, birim dosyaları **aynı sembol listeleriyle** (40 kayıtçı, 20 funding/paper). Kod aynı
`tar` akışıyla; iki sunucuda `sha256sum scripts/*.py src/**/*.py` eşit olmalı.

1. **BingX erişim kontrolü** (§0). Geçmezse kurulum yok.
2. **Kayıtçılar + bellek örnekleyici:** §3 `spread-logger`, §6 `trades-logger`,
   `janitor-bellek-ornek.service` (`logs/bellek/ornek.sh`, dakikada bir rss+swap →
   `logs/bellek/rss2.log`). Ardından §4–§6b zamanlayıcıları (`earliest`, `ohlcv30m`, `funding`).
3. **Paralel kayıt doğrulaması:** her sembolde iki sunucunun ortak işlem kimliği (`fillId`)
   sayısı > 0 (`birlestir --kuru`, aşağıda 1a). Kayıttan ~10 dk sonra yapılabilir.
4. **Bellek kabulü (paper'dan önce):** `scripts/sizinti.py` ile, iki satırlık önlem açıkken,
   paper'ın 20 sembolünde ısınma + 3 tespit döngüsü:
   ```bash
   MALLOC_ARENA_MAX=2 nice -n 10 .venv/bin/python -m scripts.sizinti --symbols <paper ile ayni 20 sembol>
   ```
   Gerekenler §7'deki gibi (`fees.json`, `funding/`, 30m geçmişi). Çıktı ve döngü süreleri
   `docs/measurements/goc.md`'ye yazılır.
5. **Karar:** `GECTI` (her döngünün RSS'i 1. döngünün ±10 MB'ı içinde) → §7 birimi kurulur,
   paper ayrı durum dosyasıyla açılır (`--db data/paper/f1_yeni.db`), ilk 3 gerçek döngüde
   `rss2.log` ile teyit. `KALDI` → paper açılmaz, artımlı tespite geçilir (`LIVE.md` §2).
   Döngü süresi > 10 dk çıkarsa da artımlı tespit tetiklenir.
6. Örtüşme kontrolü (aşağıda) geçerse **geçiş**: `pull_book` / zamanlayıcı TR-SSD 2'ye döner,
   eski sunucuda servisler `stop` (SIGINT, tampon yazılır), son bir kez eskiden çekilir,
   birleştirilir. Eski sunucuda paper 2026-10-01'den beri kapalı: `f1.db` taşınmaz; TR-SSD 2'nin
   paper'ı (açıldıysa) kendi durumuyla sürer.
7. Eski sunucudaki `~/janitor/data` birleştirmeden sonra **silinmez**: özet listesi
   (`sha256sum`) PC'ye alınır, silme ayrı ve açık bir karardır.

### Veri birleştirme

Her sunucu PC'de **ayrı köke** çekilir, doğrudan `data/`'ya değil (`pull_book` üzerine yazma
koruması iki kaynağı çakışma sayıp durur):

```powershell
python -m scripts.pull_book --host janitor@179.61.147.81 --root göç/eski
python -m scripts.pull_book --host janitor@<tr-ssd-2>       --root göç/yeni
```

| Veri | Anahtar | Birleştirme | Çakışma |
|---|---|---|---|
| İşlem `trades/` | sembol + `id` (`fillId`, ardışık) | birleşim, `id`'ye göre tekil | aynı `id` farklı `ts/price/qty/side` → **hata**, dosya yazılmaz |
| Defter `book/` | sembol + `ts` dakikası | birleşim; aynı dakika iki kaynakta varsa **geçişe kadar eski**, sonra TR-SSD 2 (kaynak kolonu `host`) | aynı dakikanın farklı değeri beklenir (farklı anlık görüntü) — hata değil, sayılır |
| 30m OHLCV | sembol + `ts` | birleşim | kapanmış mum iki kaynakta farklıysa **hata** (REST aynı mumu vermeli) |
| funding | sembol + `ts` | birleşim | farklı oran → **hata** |
| `earliest` | tarih + sembol + TF | iki sunucunun satırları ayrı saklanır | fark borsanın penceresi hakkında bilgi — raporlanır |

Birleştirme `scripts/birlestir.py` (2026-09-30, `tests/test_birlestir.py` sentetik: boşluk
doldurma, çakışma → dosya yazılmaz, hedefteki satır korunur, defter önceliği geçişte döner,
ikinci koşu boş). Önce `--kuru` (geçiş kapısı raporu), sonra yaz:

```powershell
python -m scripts.birlestir --kaynak eski=göç/eski --kaynak yeni=göç/yeni --gecis <geçiş anı, UTC> --kuru
```

Sıra önemli: ilk `--kaynak` eski sunucu. Hedefteki mevcut `data/` en düşük öncelikli kaynak
sayılır; hiçbir satır silinmez. İlk yazımda defter dosyalarına `host` kolonu eklenir.
`pull_book` 30m ve funding'i çekmez; o ikisi için sunucudan `data/*/*/{30m,funding}` ayrıca
`scp`/`tar` ile aynı köklere alınır.

### Tekrar (örtüşme) kontrolü — geçiş kapısı

Örtüşme penceresinde, sembol başına. **Yalnızca 1a bağlayıcıdır** (asgari şart); geri
kalanlar süre yettiği kadar ölçülür ve kaydedilir, geçişi durdurmaz.

1a. **Paralel kayıt (bağlayıcı):** her sembolde iki sunucunun ortak `id` sayısı > 0
   (`python -m scripts.birlestir ... --kuru`, "paralel kayıt" satırı). Yeni sunucu kayda
   başladıktan ~10 dk sonra ilk kontrol yapılabilir (yazım 5 dk'da bir).
1b. **İşlem akışı:** iki kaynağın `id` kümeleri. Birleşimdeki `id` boşlukları
   (`trades_gap` yöntemi) her kaynağın tek başına boşluğundan **az ya da eşit** olmalı.
   Yalnızca bir kaynakta olan `id` sayısı ve o kaynağın boşluk kaydı eşleşmeli
   (açıklanamayan fark → geçiş yok). Çakışan `id` = 0.
2. **Defter:** dakika kapsaması iki kaynakta ≥ %99; eksik dakikalar `logs/collect/`
   hatalarıyla açıklanmalı.
3. **30m / funding:** çakışan satırlarda fark = 0.
4. **Paper** (2026-10-01'den beri uygulanamaz: eski sunucuda paper kapalı): iki döngünün karar logunda aynı `(ts, event, symbol, outcome)` kümeleri; fark
   varsa nedeni (REST farkı, `DATA` olayı, kill) yazılmadan geçiş yok.
5. **Disk ve bellek:** TR-SSD 2'de `du -sh data/bingx`, `systemctl --user status` bellek
   tepeleri; `kalp_ozet` iki sunucuda.

Sonuç `docs/measurements/goc.md`'ye yazılır: 1a'nın sonucu, örtüşme süresi ve ölçülebilen
diğer maddeler. 1a sağlanmışsa geçiş eski sunucunun kapanışıyla olur.

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
