# Hata avı — #2, #6, #9 (2026-10-02)

Kaynak: v1 inceleme koşusu (`logs/inceleme/f1_v1_eski.pkl`, iz `53adb0b69c4248f9`), 1m BingX
verisi. Zone 1m ile `watch_from`'dan yeniden oynatıldı (betik oturum karalamasında, sonuç
aşağıda). Saatler UTC. "İzleme öncesi" = `anchor_1` 30m mumunun kapanışı → `watch_from`
(pivot teyidi; bot zone'u henüz bilmiyor).

## #2 · SUI LONG · −2,81 R — **hata değil**

Çapa 0 = 2,6318 (01:30 mumu), çapa 1 = 2,584 (02:30 mumu, 1m 02:50). 0.50 = 2,6079 · 0.70 = 2,59834.

| 1m | Olay | Zone |
|---|---|---|
| 03:04 | 0.50 teması | *izleme öncesi* |
| 03:10 | 0.70 teması | *izleme öncesi* |
| 03:26 | 0.50 teması | *izleme öncesi* |
| 04:00 | izleme başlar (pivot teyidi 03:30 mumunun kapanışı) | ACTIVE |
| 04:49 | 0.50 teması | PRIMED, 0.70'te bekleyen alış |
| 05:04–05:29 | 0.50 çevresinde (30m 05:00 mumu, tepe 2,6087) | PRIMED |
| 05:31 | 0.70 teması, emir doldu 2,59834 | ENTERED |
| 05:31–05:44 | en yüksek 2,6008 — **0.50'ye (2,6079) çıkmadı** | ENTERED |
| 05:45 | dip 2,5456, `1` kırıldı → stop | CLOSED |
| 06:43 | 0.50 teması (stoptan sonra) | — |

Grafikte görülen "0.5 → 0.7 → 0.5" dizisi **03:04–03:26**'da, bot zone'u bilmeden (pivot
teyidinden önce) oldu. Girişten sonra 0.50 gelmedi. 30m grafikte 05:00 mumu 0.50'ye değiyor
ama o temaslar girişten **önce**; 05:30 mumu hem girişi hem stopu içeriyor. Kurala aykırılık
yok; teyit penceresinde oynayan setup'ın ne olacağı spec'te tanımsız → **`OPEN-61`**
(F1'de işlemlerin %45'i böyle).

## #6 · ORDI LONG · −2,44 R — **hata değil**

Çapa 0 = 5,465 (18:30), çapa 1 = 5,253 (20:30, 1m 20:34). 0.50 = 5,359 · 0.70 = 5,3166.

| 1m | Olay | Zone |
|---|---|---|
| 20:41–21:41 | 0.50 → 0.70 → 0.50 dizisi | *izleme öncesi* |
| 22:00 | izleme başlar | ACTIVE |
| 01:09 | 0.50 teması | PRIMED |
| 01:09–09:26 | 8 saat 0.50 çevresinde; 09:05–09:26 0.50 temasları (30m 09:00 mumu tepe 5,389) | PRIMED |
| 09:33 | 0.70 teması, emir doldu 5,3166 | ENTERED |
| 09:34 | O 5,311 · dip **5,103** · K 5,166 — `1` kırıldı → stop (eski kural: kapanıştan, 5,1650) | CLOSED |
| 09:44–09:45 | 5,349 → 5,378: 0.50 teması, **stoptan 10 dk sonra** | — |

30m 09:30 mumu (A 5,339 · Y 5,424 · D 5,103 · K 5,371) giriş, stop ve 0.50'ye dönüşün üçünü
de içeriyor; mumda sıra görünmüyor. 1m'de sıra: önce düşüş ve stop, sonra yükseliş. Kurala
aykırılık yok. Yeni stop kuralıyla (seviyeden) bu işlemin kaybı −2,44 R'den ~−1 R'ye iner.

## #9 · NEAR SHORT · −2,42 R — **gerçek hata, düzeltildi**

Çapa 0 = 1,149 (17:00 dibi), çapa 1 = 1,175 (21:30 tepesi). 0.50 = 1,162 · 0.70 = 1,1672.

| 30m / 1m | Olay | Zone (eski kod) | Doğrusu |
|---|---|---|---|
| 22:00 mumu (D 1,161) | 0.50 teması | *görülmüyor* | — |
| 22:30 mumu (D **1,130**) | **`0` (1,149) kırıldı** | *görülmüyor* | INVALIDATED |
| 23:00 | izleme başlar (teyit 22:30 mumunun kapanışı) | ACTIVE → aynı dk 0.50 → PRIMED | — |
| 00:17 | 0.70 teması, short 1,1672 | ENTERED | işlem yok |
| 00:19 | tepe 1,186, `1` kırıldı → stop | CLOSED | — |

Kullanıcının okuması ("0, 0.5'e değmeden kırıldı") sırayı biraz farklı veriyor — 1m'de 0.50
22:00 mumunda, `0` 22:30 mumunda — ama sonuç aynı: `0` girişten önce alındı, R-ZONE-05 gereği
zone ölü. **Neden:** zone `watch_from`'dan önceki mumları hiç görmüyordu (R-ZONE-09), pivot
teyit penceresindeki çapa teması sayılmıyordu. O pencerenin mumları `watch_from`'da
kapanmıştır; görmemek gerekmiyordu.

**Düzeltme:** `src/zones/detect.py:izleme_oncesi_oldu` — teyit penceresinde `0`'a veya `1`'e
ulaşılmışsa zone kurulmaz (backtest, oynatma ve paper aynı `detect_zones`'tan geçer).
Testler `tests/test_zone_detect.py::test_R_ZONE_05_*` (3). **Etki:** v1 koşusunun 3.565
işleminden **96**'sı (%2,7; 55 kazanan, 37 stop), net toplamı −117 $ (10.000 $ hesap). 30
incelenen işlemden yalnızca #9.
