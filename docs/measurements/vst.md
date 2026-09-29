# BingX demo (VST) API araştırması — 2026-09-29

Emir gönderilmedi. Yalnızca herkese açık uçlar çağrıldı (anahtarsız).

## Erişim

- Uç: `https://open-api-vst.bingx.com/openApi/...`, yol ve şema gerçek uçla aynı.
  ccxt `set_sandbox_mode(True)` yalnızca bu alan adına geçiyor. Anahtar aynı kalıyor.
- Yalnızca vadeli (swap). ccxt: "sandbox is swap only".
- `quote/contracts` BTC-USDT: `tradeMinQuantity` 0,0001 · `tradeMinUSDT` 2 · maker %0,02 ·
  taker %0,05.
- Oran sınırı başlıkları: `X-RateLimit-Requests-Remain: 500`, pencere 10 sn (IP başına,
  genel uçlar). BingX duyurusu (2025-10-16): `/openApi/swap/v2/trade/order` → 10 istek/sn.
- Post-only: `timeInForce=PostOnly` (belgelerde var, VST'de denenmedi, anahtar yok).

## Anahtar güvenliği — DOĞRULANAMADI

BingX'te resmî bir "yalnızca demo" anahtarı belgesi bulunamadı. Tek kaynak üçüncü taraf bir
PHP kütüphanesi ("VST için ayrı anahtar oluşturun"), BingX'e atıf yok. BingX'in GitHub
sorunları (#7, #26) yanıtsız. ccxt aynı anahtarla yalnızca alan adını değiştiriyor.
**Varsayım: anahtar hesaba aittir, demo/gerçek ayrımı alan adıdır.** Demo'da emir veren bir
anahtar, alan adı değişince gerçek hesapta da emir verebilir.

Doğrulama (kullanıcı, kendi makinesinde): anahtarla gerçek alan adında **salt okunur**
`GET /openApi/swap/v2/user/balance`. Gerçek bakiye dönüyorsa anahtar gerçek hesaba ulaşıyor.
O durumda yalnızca bakiyesi 0 olan bir alt hesabın anahtarı + IP kısıtı kullanılır.

## VST ayrı bir piyasadır (sonuç)

10 × 1 sn örnek, 2026-09-29:

| | BTC-USDT | DOGE-USDT |
|---|---|---|
| VST − gerçek orta fiyat, medyan | −0,01 bps | **+11,9 bps** |
| VST spread, medyan | 0,36 bps | **25,8 bps** |
| İlk 5 alış kademesi hacmi VST / gerçek | 5,2 / 76,5 BTC | 19,4 M / 8,8 M DOGE |
| Ortak `fillId` (son 1.000 işlem) | **0** | **0** |

VST'nin kendi defteri ve kendi işlem akışı var (farklı `fillId` dizisi, bot boyutunda
işlemler). Demo emir, gerçek işlemlerle değil VST'nin sentetik likiditesiyle eşleşiyor.
Bu yüzden **demo doluşu `OPEN-37` kuyruk sorusunu cevaplayamaz**. Karşılaştırma VST
motorunun sadakatini ölçer, gerçek kuyruğu değil. DOGE'de fiyat bile 12 bps ayrışıyor.
Demo doluş testi (4. adım) yapılmadı.
