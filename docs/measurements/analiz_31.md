# #31 açıklayıcı analizler

Kaynak `scripts/analiz_31.py`, `logs/inceleme/ltf31_31.pkl` (parmak izi `e8c2b0e8922f388a`, spec v0.11, kod 6362510+kirli). Açıklayıcıdır, kural değiştirmez.

## 1 · İşlem sıklığı

3317 işlem, 2025-08-01 → 2026-07-05 (339 gün, 49 hafta), 19 sembol (ETH'de hiç işlem yok). Giriş zamanına göre.

| ölçü | ortalama | medyan | %90 | en çok | sıfır olan |
|---|---:|---:|---:|---:|---:|
| günlük işlem (tüm semboller) | 9.8 | 9 | 19.0 | 39 (2026-02-08) | 32 gün |
| haftalık işlem (tüm semboller) | 67.7 | 71 | 98.0 | 118 | 0 hafta |
| sembol başına haftalık | 4.45 | 4.72 | 5.3 | 5.76 (HYPE) | — |

Sembol-gün başına 0.65 işlem. Tutma süresi (saat): medyan 3.2, %25 1.1, %75 9.3; 1 saatten kısa 24%, 15 dakikadan kısa 8%.
Zone başına işlem: 3317 zone, ortalama 1.00, en çok 1; birden fazla işlem açılan zone 0 (0%), bu zone'lardaki işlem 0 (0%).
Portföyde en az bir açık pozisyon olan 1m mumu: 95% (`bars_with_position` / `bars_total`).

**En yoğun 5 hafta:**

| hafta (Pzt) | işlem | en çok sembol |
|---|---:|---|
| 2025-11-24 | 118 | NEAR 12, SUI 10, BTC 10 |
| 2026-02-02 | 118 | CRV 10, XRP 8, JUP 8 |
| 2026-04-20 | 113 | XRP 12, SUI 10, HYPE 10 |
| 2026-03-02 | 101 | NEAR 12, DOT 10, HYPE 10 |
| 2025-12-08 | 98 | INJ 8, DOGE 8, ZEC 7 |

**Sembol başına** (işlem / hafta):

HYPE 5.8 · BTC 5.3 · SOL 5.3 · DOGE 5.2 · CRV 5.2 · BNB 4.9 · XRP 4.9 · NEAR 4.8 · DOT 4.8 · JUP 4.7 · ZEC 4.6 · GALA 4.6 · UNI 4.6 · ORDI 4.6 · RUNE 4.5 · SUI 4.5 · INJ 4.2 · AVAX 1.3 · AAVE 0.7

## 4a · v4: motorun aktif zone'u ↔ kullanıcının setup'ı

Kullanıcı **12/30** setup var. Motor: karar anında aktif zone'u olan an **8/30**, 0.50'ye ulaşmış (PRIMED — OTE emri bekliyor) **8/30**, bantta (0.70–0.79 temas) **11/30**, ikisinden biri **19/30**.

| | kullanıcı setup var (12) | setup yok (18) |
|---|---:|---:|
| motorda aktif zone var | 5 | 3 |
| aktif zone yok | 7 | 15 |
| PRIMED zone var | 5 | 3 |
| bantta zone var | 4 | 7 |
| **aktif ya da bantta** (motor “setup var”) | 9 | 10 |

Aktif = bilinen, `0`/`1`'i ihlal edilmemiş ve 0.70'e karardan önce değmemiş (değdiyse motor o zone'da işlemini yapmış olurdu; spec dışı zone ölümleri — sonlandırma, kill — sayılmadı). PRIMED = aktif ve 0.50'ye ulaşmış (v0.11'de OTE emri zone ölene kadar durur → bu anlarda motorun bekleyen emri var). Kullanıcının setup'ı ile motorun zone'unun **aynı leg** olduğu kontrol edilmedi (o, v4 puanının çift isabetidir: 8/12).

<details><summary>30 an</summary>

| an | sembol | karar | kullanıcı | aktif zone | PRIMED | bantta |
|---|---|---|---|---:|---:|---|
| r01 | JUP | 2025-08-05 12:30 | var | 2 | 2 | — |
| r02 | ETH | 2025-08-10 08:00 | yok | 0 | 0 | evet |
| r03 | AAVE | 2025-08-10 09:00 | var | 2 | 1 | — |
| r04 | JUP | 2025-08-14 13:00 | yok | 0 | 0 | — |
| r05 | AVAX | 2025-08-22 10:00 | yok | 0 | 0 | evet |
| r06 | ORDI | 2025-08-24 08:00 | var | 0 | 0 | — |
| r07 | INJ | 2025-08-27 05:30 | var | 0 | 0 | evet |
| r08 | CRV | 2025-09-03 02:30 | yok | 0 | 0 | — |
| r09 | GALA | 2025-09-06 03:30 | var | 0 | 0 | — |
| r10 | DOT | 2025-09-22 12:00 | yok | 0 | 0 | evet |
| r11 | GALA | 2025-10-08 17:30 | yok | 0 | 0 | — |
| r12 | AVAX | 2025-10-12 07:00 | yok | 1 | 1 | — |
| r13 | JUP | 2025-10-23 17:00 | var | 2 | 2 | — |
| r14 | JUP | 2025-10-29 01:00 | var | 0 | 0 | evet |
| r15 | RUNE | 2025-11-12 07:30 | var | 1 | 1 | — |
| r16 | RUNE | 2025-11-13 18:30 | yok | 1 | 1 | — |
| r17 | ZEC | 2025-11-18 11:30 | yok | 0 | 0 | — |
| r18 | XRP | 2025-11-18 15:30 | var | 1 | 1 | — |
| r19 | HYPE | 2025-11-20 20:00 | yok | 0 | 0 | — |
| r20 | BNB | 2025-12-03 20:30 | yok | 0 | 0 | — |
| r21 | SUI | 2025-12-10 14:30 | yok | 0 | 0 | — |
| r22 | GALA | 2025-12-18 23:30 | var | 0 | 0 | evet |
| r23 | XRP | 2026-01-12 04:00 | yok | 1 | 1 | — |
| r24 | BTC | 2026-01-28 20:30 | yok | 0 | 0 | evet |
| r25 | NEAR | 2026-02-15 23:00 | yok | 0 | 0 | evet |
| r26 | DOGE | 2026-02-19 04:00 | yok | 0 | 0 | evet |
| r27 | GALA | 2026-03-20 05:30 | yok | 0 | 0 | evet |
| r28 | SUI | 2026-03-20 14:00 | var | 0 | 0 | — |
| r29 | XRP | 2026-04-06 15:00 | yok | 0 | 0 | — |
| r30 | SOL | 2026-04-18 00:00 | var | 0 | 0 | evet |

</details>

## 4b · OTE girişleri ↔ 4h yapı yönü (R-ZONE-10)

#31'in 3129 OTE girişi (OB girişleri hariç), girişte bilinen 4h yön (`entry_bias`). Kural uygulanmadı; brüt = fiyat PnL'i (slippage içinde), net = brüt − komisyon − funding.

| grup | işlem | pay | kazanma | brüt $ | brüt/işlem $ | net $ |
|---|---:|---:|---:|---:|---:|---:|
| uyumlu | 852 | %27 | %51,8 | -5,43 | -0,0064 | -12,91 |
| ters | 1114 | %36 | %51,3 | +4,28 | +0,0038 | -5,84 |
| belirsiz | 1163 | %37 | %48,9 | -25,50 | -0,0219 | -36,33 |

Tek koşu, örneklem içi, bootstrap yok — gruplar arası fark gürültü olabilir.

