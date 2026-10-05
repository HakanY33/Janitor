# Göç — sunucudan PC'ye (2026-10-05 → 10-12)

Plan: `docs/SERVER.md` "Sunucu kapanışı — PC'ye geçiş". TR-SSD 2 göçü iptal (kullanıcı, 2026-10-05).

## Paralel kayıt doğrulaması — 2026-10-05

- PC kayıtçıları (trades + spread, 40 sembol) **06:37 UTC**'de `göç/pc/data` köküne başladı
  (`scripts/pc_kayit.ps1 -Kok`, `JANITOR_DATA_ROOT`). İlk deneme (06:31) konsolsuz ayrık
  süreçle başlatıldı ve hemen öldü; gizli konsolla (`CREATE_NO_WINDOW`) yeniden başlatıldı.
- Sunucunun `trades/2026-10-05.parquet` dosyaları 06:49'da tek `tar` ile `göç/kontrol`'e çekildi
  (toplu `pull_book` aynı dakikada `tar` çıkış 2 ile düştü — dosyalar 5 dk'da bir yeniden yazılıyor).
- `python -m scripts.birlestir --kaynak sunucu=göç/kontrol --kaynak pc=göç/pc --hedef göç/bos --gecis 2026-10-05T07:00Z --kuru`:
  **40/40 sembolde ortak `id`** (sembol başına 2.427–5.894), çakışma (aynı `id` farklı içerik) **0**,
  PC'de eksik `id` 0. Sunucuda eksik `id`: ADA 1.387, BTC 2, NEAR 1, WLD 1 (PC başlamadan önceki
  saatlerde; sunucunun kendi boşluğu). PC'de olup sunucu dosyasında olmayan 353–1.260 `id` =
  sunucunun son 5 dk'lık yazılmamış tamponu.

**Sonuç: paralel kayıt doğrulandı** (göç asgari şartı, `OPEN-60` kuralı).

## Son çekim — 2026-10-11

Bekliyor.
