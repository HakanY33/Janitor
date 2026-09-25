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

- Sunucudaki SHA-256 listesiyle karşılaştırır. Aynı dosyalar atlanır, yalnızca
  değişenler iner (bulunulan ayın dosyası her gün değişir).
- Her dosyayı indirdikten sonra özetini doğrular ve atomik olarak yerine koyar.
- Yerel dosyada sunucuda olmayan bir dakika varsa dosyanın **üzerine yazmaz** ve hata
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
