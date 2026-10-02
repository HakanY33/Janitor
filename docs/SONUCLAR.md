# SONUÇLAR — test edilen her strateji, tek satır

**Kural:** bundan sonraki her test (backtest, keşif, paper, ileriye dönük) buraya **bir satır**
olarak eklenir; satır silinmez, güvenilmez çıkarsa "güvenilir?" sütunu güncellenir ve nedeni
yazılır. Ayrıntı satırdaki kaynak belgededir.

**Okuma:**
- **100 $ →** başlangıç bakiyesi 100 $ olsaydı bitiş tutarı. #24'e kadar ölçümler 10.000 $
  ile yapıldı ve sütun oranla çevrildi (`100 × (1 + net / 10.000)`). **#25'ten itibaren hesap
  tabanı 100 USDT** (2026-10-02): koşu gerçekten 100 $ ile, borsanın miktar adımı ve asgari
  emriyle yapılır — oran çevirmesi küçük hesapta karşılanamayan emirleri saklıyordu. Sürtünme (komisyon, slippage, funding) dahil.
- **Kazanma** = net PnL > 0 olan işlemlerin oranı. "—" = o koşuda kaydedilmedi.
- **Deneme** = kronolojik sıra. Aynı belgede ölçülen kollar ardışık numaralanır.
- Dilim aksi yazılmadıkça **eğitim** (20 sembol, en eski %80, ~2025-07-31 → 2026-05-08).

**Güvenilir ölçüm** için üçü birden gerekir: (1) 30m look-ahead düzeltmesi (2026-09-29,
nesneler mum kapanışında bilinir), (2) `OPEN-41` (emir önceki kapanışta, boyut kapanış
görüntüsünden — eskiden dolum mumunun kapanışını görüyordu), (3) boşluklu mumda stop
(2026-09-30). Bunlardan önceki her satır **yalnızca tarih** içindir.

| # | Tarih | Strateji | 100 $ → | Değişim | Kazanma | İşlem | Güvenilir? | Neden | Kaynak |
|---|---|---|---:|---:|---:|---:|---|---|---|
| 1 | 2026-09-21 | OTE A — mevcut hâl (ekleme sınırsız) | 0,26 $ | −99,7% | — | 7.413 | Hayır | 30m look-ahead | `measurements/levers.md` |
| 2 | 2026-09-21 | OTE B — A + ekleme tavanı 3, tek küçültme | 0,53 $ | −99,5% | — | 5.360 | Hayır | 30m look-ahead | `measurements/levers.md` |
| 3 | 2026-09-21 | OTE C — B + limit emirleri (maker) | 1,81 $ | −98,2% | — | 7.414 | Hayır | 30m look-ahead | `measurements/levers.md` |
| 4 | 2026-09-21 | OTE D — C + gösterge kapısı (yalnızca OB/FVG) | 47,82 $ | −52,2% | — | 2.208 | Hayır | 30m look-ahead | `measurements/levers.md` |
| 5 | 2026-09-21 | D2 — D, TP 0,02 leg önde | 46,57 $ | −53,4% | — | 2.220 | Hayır | 30m look-ahead | `measurements/tp_placement.md` |
| 6 | 2026-09-21 | D3 — D, TP 0,05 leg önde | 46,69 $ | −53,3% | — | 2.261 | Hayır | 30m look-ahead | `measurements/tp_placement.md` |
| 7 | 2026-09-21 | D4 — D, TP temasla piyasa emri | 44,61 $ | −55,4% | — | 2.207 | Hayır | 30m look-ahead | `measurements/tp_placement.md` |
| 8 | 2026-09-21 | E10 — D + stop kaybı tavanı %10 | 98,14 $ | −1,9% | — | 2.211 | Hayır | 30m look-ahead | `measurements/add_reject_e.md` |
| 9 | 2026-09-21 | E5 — D + stop kaybı tavanı %5 | 92,73 $ | −7,3% | — | 2.217 | Hayır | 30m look-ahead | `measurements/add_reject_e.md` |
| 10 | 2026-09-21 | E3 — D + stop kaybı tavanı %3 | 98,24 $ | −1,8% | — | 2.221 | Hayır | 30m look-ahead | `measurements/add_reject_e.md` |
| 11 | 2026-09-24 | F1 — E3 + breakeven ücretli + ekleme kapalı | 123,76 $ | +23,8% | %65,7 | 2.251 | Hayır | 30m look-ahead; kâr tamamen ondan geliyordu | `measurements/f_kollari.md`, `neden.md` |
| 12 | 2026-09-24 | F2 — E3 + asgari leg %1,938 | 102,44 $ | +2,4% | — | 1.418 | Hayır | 30m look-ahead | `measurements/f_kollari.md` |
| 13 | 2026-09-25 | F1, soğuk 20 sembol | 141,87 $ | +41,9% | %63,5 | 2.261 | Hayır | 30m look-ahead | `measurements/soguk.md` |
| 14 | 2026-09-25 | F1, ayrılmış dilim (orijinal 20) | 87,13 $ | −12,9% | %62,8 | 962 | Hayır | 30m look-ahead; ayrılmış dilim bir kez okundu | `measurements/ayrilmis.md` |
| 15 | 2026-09-25 | F1, ayrılmış dilim (soğuk 20) | 91,49 $ | −8,5% | %60,2 | 832 | Hayır | 30m look-ahead | `measurements/ayrilmis.md` |
| 16 | 2026-09-29 | A, düzeltilmiş damga | 0,02 $ | −100,0% | — | 6.560 | Kısmen | damga düzeltildi; `OPEN-41` yok (girişte dolum mumunun kapanışı) | `measurements/damga.md` |
| 17 | 2026-09-29 | C, düzeltilmiş damga | 0,64 $ | −99,4% | — | 6.387 | Kısmen | aynı; ayrıca ekleme merdiveni | `measurements/damga.md` |
| 18 | 2026-09-29 | D, düzeltilmiş damga | 15,65 $ | −84,3% | — | 2.741 | Kısmen | aynı | `measurements/damga.md` |
| 19 | 2026-09-29 | E3, düzeltilmiş damga | 38,35 $ | −61,6% | — | 2.769 | Kısmen | aynı | `measurements/damga.md` |
| 20 | 2026-09-29 | F1, düzeltilmiş damga | 54,81 $ | −45,2% | — | 2.833 | Kısmen | aynı | `measurements/damga.md` |
| 21 | 2026-09-29 | F1 kapısız (gösterge kapısı açık), düzeltilmiş damga | 11,80 $ | −88,2% | — | 9.239 | Kısmen | aynı | `measurements/damga.md` |
| 22 | 2026-09-30 | **F1 dürüst** — düzeltilmiş damga + `OPEN-41` + boşluklu stop | **13,54 $** | **−86,5%** | %53,2 | 3.565 | **Evet** | üç düzeltme de var; eğitim dilimi, sürtünme dahil; parmak izi `7ce05ad1a47d5523`. 2026-10-01 yeniden koşu (`OPEN-59` funding'iyle): aynı 3.565 giriş/çıkış, net −8.649 (Δ −2,46), iz `53adb0b69c4248f9` | `measurements/damga.md`, `logs/f1check/f1_bosluk.json`, `inceleme/` |
| 23 | 2026-09-30 | H2 — 4h unmitige OB, post-only yakın kenar, 2R, %3 stop | 0,00 $ | −100,0% | %27,9 | 1.335 | Evet (keşif) | ön kayıtlı, sıfır ayar; brüt de negatif (R ort −0,16) → ileriye dönük testten çıkarıldı | `HYPOTHESES.md`, `logs/h2_kesif.txt` |
| 24 | 2026-10-02 | F1 dürüst, spec v0.6 — iç stop/breakeven **seviyeden** (`R-RISK-02`) + izleme öncesi `0`/`1` teması zone'u öldürür (`R-ZONE-05`) | 16,95 $ | −83,1% | %53,5 | 3.472 | Evet | 10.000 $ ile; v1'e (#22) göre net +344 (stop kuralı + 96 ölü zone'un işlemi gitti). Parmak izi `dab9806c1711231d` | `inceleme/v2/hata_avi.md`, `logs/inceleme/f1_10000.pkl` |
| 25 | 2026-10-02 | **F1, 100 USDT tabanı** — #24 + borsa miktar adımı ve asgari emir (`R-ENTRY-03`) | **27,92 $** | **−72,1%** | %48,1 | 2.987 | Evet | **gerçek 100 $ başlangıç** (oran değil). Asgariyi karşılamayan giriş 535, kısmi TP 247 (`OPEN-63`: pozisyon tam kalır, stop maliyete) reddedildi ve sayıldı. Asgari/adım **bugünkü** borsa değerleri, geçmişe uygulandı. Parmak izi `def2048dc13a8fdb` | `logs/inceleme/f1_100.pkl` |
