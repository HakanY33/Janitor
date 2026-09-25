# Sembol soğuk testi + kriter 2 (yeni tanım)

**Tarih:** 2026-09-25 · **spec** v0.4 · **kod** 75518a4+kirli · betik `scripts/soguk.py`
· çıktı `logs/soguk.txt`, `logs/soguk.csv`

F1 dondurulmuş: hiçbir parametre değişmedi. **Ayrılmış %20 okunmadı.**

## Kümeler

- **ORİJİNAL:** `liquidity.json` (2026-09-11 hacim sıralaması, ilk 20). Bugüne kadarki
  bütün ölçümler bu küme üzerinde yapıldı.
- **YENİ (soğuk):** `data/bingx/liquidity_soguk.json`. Seçim kuralı koşudan önce
  sabitlendi: 2026-09-25 hacim sıralamasında **21. sıradan başla**, orijinal 20'yi ve
  kripto dışı kontratları (NCCO/NCSI/NCFX/NCSK) atla, 20 sembol dolana kadar devam et.
  Sonuç: sıra 21–43 → ADA, TRX, APT, ARB, PEOPLE, ENA, KAS, WIF, APE, BANANA, NOT, WLD, ENS,
  IMX, ETHFI, DYDX, 1000BONK, CFX, TURBO, LDO. Hiçbiri daha önce kullanılmadı.
  - Orijinallerin 3'ü bugün 23, 35 ve 36. sırada. Bu yüzden 21–40 bandı 43'e kadar uzadı.
  - İlk koşuda `NCSINASDAQ1002USD` (Nasdaq endeksi) 28. sıraya düştü. Mevcut filtre
    (`NON_CRYPTO = ("NCCO",)`) onu kaçırıyordu. Seçimden elle çıkarıldı.
- 1m ve 30m backfill: 20/20 sembol. 1m verisi 2025-07-31 16:00'dan başlıyor.
  Mükerrer satır yok. Her sembolde tek 5 dakikalık boşluk var, 20'sinde de aynı.

## Dönem

İki küme de **2026-05-08 13:00 UTC'de** biter. Bu, orijinalin %80 kesimidir. 30m penceresi
borsada kaydığı için (`earliest.md`) yeni sembollerin 30m'i 14 gün geç başlıyor. Aynı %80
oranı onları ~14 gün geç keser ve orijinalin ayrılmış döneminin takvimine girerdi. Yeni
küme bu yüzden oranla değil, takvimle kesildi: `train_frac` = 0,778, test
`tests/test_soguk.py`. İşlem dönemi, 1m başlangıcından (2025-07-31) kesime kadar iki
kümede aynı.

## Sonuçlar

| ölçü | ORİJ F1 | YENİ F1 | ORİJ K2-eski | YENİ K2-eski | ORİJ K2-yeni | YENİ K2-yeni |
|---|---:|---:|---:|---:|---:|---:|
| **net PnL** | +2.376 | **+4.187** | −206 | +1.443 | **+157** | **+1.021** |
| brüt / sürtünme | 1,535 | 1,920 | 0,970 | 1,242 | 1,033 | 1,200 |
| kazanan sembol | 15/20 | 15/20 | 12/20 | 14/20 | 11/20 | 12/20 |
| maks drawdown | %11,9 | %13,2 | %15,5 | %16,4 | %17,3 | %18,7 |
| iflas (bar < %50 / %25 / %10) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| H1 net | +1.697 | +1.157 | +389 | −58 | +780 | +19 |
| H2 net | +679 | **+3.030** | −595 | +1.502 | **−623** | +1.001 |
| işlem | 2.251 | 2.261 | 2.254 | 2.263 | 2.230 | 2.223 |
| kaçan giriş | 31 | 32 | 31 | 32 | 56 | 67 |

- **K2-eski:** komisyon ve slippage ×1,5.
- **K2-yeni:** komisyon kesin, slippage ×3, giriş P2 (2 tick). Sonuç görülmeden
  sabitlendi (STRATEGY_SPEC §8 Kabul kriterleri).
- **Yarı kesimi:** ORİJ F1'in medyan girişi (2025-12-14 14:34), iki kümede de aynı.
- Likidasyon her kolda 0. Kalemler her kolda kapanıyor.

YENİ F1'de sembol başına net: kaybedenler ARB −537, APT −448, LDO −405, TRX −347,
ENA −155; en çok kazanan CFX +935. Tam liste `logs/soguk.txt`'de.

## Okuma

1. **F1 soğuk kümede ayakta.** Net +4.187, brüt/sürtünme 1,92, 15/20 sembol kazanıyor.
   Orijinalde gördüğümüz sonuç, seçilen 20 sembole özgü değil.
2. **Yeni kriter 2 iki kümede de geçiyor (net > 0)**: orijinalde +157, yenide +1.021.
   Orijinaldeki geçiş **kıl payı**: brüt/sürtünme 1,033, başlangıç bakiyesinin %1,6'sı.
3. **Eski ×1,5 kriteri** orijinalde kalıyor (−206), yenide geçiyor (+1.443).
4. **Yarılar tutarsız.** Orijinalde kâr ilk yarıda. K2-yeni'nin ikinci yarısı −623.
   Yenide kâr ikinci yarıda: F1'in H2'si +3.030, K2-yeni'nin H1'i yalnızca +19. İki
   küme, aynı takvim yarılarında zıt yönde güçlü. Sonuç zamana dağılmıyor, rejime bağlı
   görünüyor.
5. **Sınır.** Yeni küme de bugünün hacmiyle seçildi. Orijinaldeki survivorship yanlılığı
   burada da var. Kaçan giriş sayısı P2 altında yenide daha fazla (67): tick'i büyük
   semboller 2 tick'e daha duyarlı.

Hangi kümenin bağlayıcı olduğu tanımlı değil (`OPEN-39`). Karar kullanıcının.
