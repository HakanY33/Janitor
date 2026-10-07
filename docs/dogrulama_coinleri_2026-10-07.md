# Doğrulama coinleri — 2026-10-07

Son doğrulamanın sembolleri. **Bu coinlerin verisi geliştirme boyunca ne indirilir ne okunur.**
`src/data/collect.py` listeyi bu dosyadan okur; disk yolu (`_safe`) ve borsa çekimi (`fetch_ohlcv`)
bu sembollerde `DogrulamaKilidi` yükseltir. Dosya yoksa ya da liste 20 değilse her veri erişimi durur.

Son doğrulama: bu 20 coin × **2026-09-11 sonrası** veri. Kilit, o koşudan önce ayrı bir PR'la açılır.

**Seçim kuralı** (soğuk testin kuralı, `measurements/soguk.md`): BingX 24s hacim sıralaması
(2026-10-07 07:53 UTC, `fetch_tickers`, `/USDT:USDT` perpetual); **44. sıradan başla**; bugüne
kadar kullanılan 40 sembolü (`liquidity.json` + `liquidity_soguk.json`) ve kripto dışı kontratları
(`NCCO`/`NCSI`/`NCFX`/`NCSK`) atla; 20 sembol dolana kadar devam et → sıra 44–76. 20'sinin hepsi
2026-09-11 evren anlık görüntüsünde var; hiçbirinin diskte verisi yok, repoda adı geçmiyordu.

Atlananlar: JUP (50), DOT (53), ETHFI (57) kullanıldı; 10 kripto dışı (47, 48, 58, 60, 62, 63, 72–75).
Sıralama bugünün hacmiyle — survivorship taşır (soğuk testle aynı kabul).

| Sıra | Sembol | 24s hacim (M USDT) |
|---:|---|---:|
| 44 | `BCH/USDT:USDT` | 9,0 |
| 45 | `NMR/USDT:USDT` | 9,0 |
| 46 | `VIRTUAL/USDT:USDT` | 8,8 |
| 49 | `API3/USDT:USDT` | 8,6 |
| 51 | `HBAR/USDT:USDT` | 8,5 |
| 52 | `XPL/USDT:USDT` | 8,2 |
| 54 | `GRASS/USDT:USDT` | 7,8 |
| 55 | `TRUMP/USDT:USDT` | 7,8 |
| 56 | `LIGHTER/USDT:USDT` | 7,7 |
| 59 | `GRIFFAIN/USDT:USDT` | 7,4 |
| 61 | `NIL/USDT:USDT` | 7,3 |
| 64 | `NIGHT/USDT:USDT` | 7,2 |
| 65 | `PARTI/USDT:USDT` | 7,1 |
| 66 | `STX/USDT:USDT` | 7,1 |
| 67 | `POL/USDT:USDT` | 7,1 |
| 68 | `BEAT/USDT:USDT` | 7,1 |
| 69 | `LYN/USDT:USDT` | 6,9 |
| 70 | `AIO/USDT:USDT` | 6,9 |
| 71 | `AIN/USDT:USDT` | 6,9 |
| 76 | `BITLIGHT/USDT:USDT` | 6,8 |
