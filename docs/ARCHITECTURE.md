# ARCHITECTURE

| | |
|---|---|
| **Versiyon** | v0.1 |
| **Durum** | Taslak |
| **Kapsam** | Araştırma + paper trading. Canlı işlem kapsam dışı. |

---

## 1. Temel ilke

**Karar deterministik koddadır. LLM karar hattının içinde değildir.**

Bunun sebebi ideolojik değil pratik: aynı girdiye farklı çıktı veren bir sistem backtest
edilemez. Backtest edilemeyen bir sistem doğrulanamaz.

LLM'in yeri aşağıda (§6) ayrıca tanımlı.

---

## 2. Katmanlar

```
┌─────────────────────────────────────────────────┐
│  1. DATA          Veri toplama + doğrulama      │
├─────────────────────────────────────────────────┤
│  2. FEATURES      İndikatör, OB, FVG, leg tespiti│
├─────────────────────────────────────────────────┤
│  3. ZONE STORE    Kalıcı zone nesneleri + FSM   │
├─────────────────────────────────────────────────┤
│  4. STRATEGY      Giriş / ekleme / çıkış kuralları│
├─────────────────────────────────────────────────┤
│  5. RISK          Sert sınırlar, kill switch    │  ◄── LLM buraya asla dokunmaz
├─────────────────────────────────────────────────┤
│  6. EXECUTION     Emir yönetimi, idempotency    │
├─────────────────────────────────────────────────┤
│  7. LEDGER        JSONL karar logu + SQLite state│
└─────────────────────────────────────────────────┘
```

Kural: bir katman yalnızca **altındaki** katmanı çağırır. RISK katmanı, STRATEGY'nin
kararını veto edebilir; tersi mümkün değildir.

---

## 3. Veri katmanı

**Toplama:** `ccxt` — OHLCV, funding rate, mark price, contract metadata.

**Saklama:** Parquet dosyaları, `data/{exchange}/{symbol}/{timeframe}/{yyyy-mm}.parquet`

**Sorgu:** DuckDB. Parquet'i doğrudan okur, ayrı bir veritabanı süreci gerekmez.

**Doğrulama — pazarlık konusu değil.** Her veri seti şu testlerden geçmeden kullanılamaz:

| Test | Kontrol |
|---|---|
| `test_no_gaps` | Timestamp serisinde eksik mum yok |
| `test_utc` | Tüm zaman damgaları UTC, tz-aware |
| `test_no_duplicates` | Aynı timestamp iki kez yok |
| `test_ohlc_sanity` | `low ≤ open,close ≤ high` her satırda |
| `test_no_zero_volume_runs` | Ardışık sıfır hacim serisi eşiği aşmıyor — **uyarı seviyesi** |
| `test_price_jumps` | Kalıcı olmayan fiyat sıçraması yok (kötü tick tespiti) |
| `test_symbol_survivorship` | Sembol listesi tarihsel, bugünün listesi değil |

### 3.1 Eşik tanımları

**Sıfır hacim serisi (`OPEN-18` kapandı).** Sabit eşik kullanılmaz. Düşük likiditeli bir
sembolde art arda birkaç sıfır hacimli 1m mumu normaldir, kesinti değildir.

- Seviye: **uyarı**, hata değil. Veriyi kullanılamaz yapmaz.
- Varsayılan eşik: **10 ardışık mum**
- Her sembol için **sıfır hacim oranı** metrik olarak kaydedilir. Oranı yüksek olan
  sembol zaten backtest için uygun değildir; bu ayrı bir eleme kriteridir.

**Fiyat sıçraması (`OPEN-19` kapandı).** Kötü tick ile gerçek hareketi ayıran şey
büyüklük değil **kalıcılıktır**:

- Kötü tick → sıçrar ve 1–2 mum içinde büyük ölçüde geri döner
- Gerçek hareket → yeni seviyede kalır

Kural: sıçrama eşiği aşıyor **ve** sonraki N mumda büyük kısmı geri alınıyorsa → şüpheli.

Eşik sabit yüzde değil, sembolün **kendi oynaklığına** göre verilir (son N mumun getiri
standart sapmasının katı). Böylece BTC ile bir memecoin aynı eşikle ölçülmez.
Sabit %20 gibi bir eşik kriptoda yanlış pozitif üretir — likidasyon kaskadlarında ve
yeni listelemelerde 1m'de %20 üstü hareket gerçekten olur.

**Şiddet modeli (`OPEN-20` kapandı).** Bir kontrolün ihlal *bulması* veri setini reddetmez.
Şiddeti **oran** belirler. Bu kural tüm kontroller için geçerlidir.

| Kontrol | Uyarı | Hata (veri seti kullanılamaz) |
|---|---|---|
| Fiyat sıçraması (şüpheli tick) | Her bulgu | Şüpheli mum oranı > **%0.1** |
| Sıfır hacim serisi | Her bulgu | Oran > **%1** |
| Eksik mum | Her bulgu | Eksik oranı > **%0.5** veya tek boşluk > 60 mum |
| UTC / mükerrer / OHLC tutarlılığı | — | **Her bulgu hata** (yapısal bozukluk) |

**Karantina, tamir değil.** Şüpheli mumlar veri setinden silinmez ve düzeltilmez.
Parquet'e `suspect: bool` sütunu yazılır. Tüketici katman karar verir:

- Backtest, **yalnızca** şüpheli bir mumun uç değeri tarafından tetiklenen giriş/çıkış üretmez
- Şüpheli muma temas eden işlem sayısı sonuç raporunda ayrı sayaç olarak görünür

Böylece bulgu kaybolmaz, ama 585 bin mumluk bir set 23 tick yüzünden çöpe gitmez.

**Uygunluk listesi.** Toplu indirme bittikten sonra `scripts/validate_all.py` tüm sembolleri
tarar ve sembol başına metrik raporu üretir (şüpheli oran, sıfır hacim oranı, eksik oranı,
kapsanan tarih aralığı). Bu rapor **backtest'e girecek sembol evrenini** belirler.
Toplu indirme sırasında satır içi doğrulama yapılmaz — ayrı bir toplu koşudur.

**Survivorship.** Bugünkü sembol listesiyle geçmişi test edersen, borsadan düşmüş
coinleri hiç görmezsin ve sonuçlar yapay olarak iyileşir. Geçmiş liste satın alınamaz —
**bugünden itibaren biriktirilir.** Günlük universe anlık görüntüsü bu yüzden
zaman duyarlıdır (§3.2).

### 3.2 Veri penceresi — zaman duyarlı

BingX'te 1m geçmişi sınırlı ve pencere **kayıyor** görünüyor (ölçüm: 2026-09-11 itibarıyla
en eski 1m mum 2025-07-31, ~13.4 ay; 30m ise ~20.7 ay).

Doğruysa: **bugün indirilmeyen geçmiş kalıcı olarak kaybolur.**

**Ölçüm (2026-09-25):** **1m kaymıyor**: 10,8 günde 20 sembolün hiçbirinde en eski mum değişmedi
(başlangıç 2025-07-31). **30m kayıyor**: günde 1 gün, pencere sabit 30.239 mum (~630 gün).
Ayrıntı `docs/measurements/earliest.md`. Sunucuda `janitor-earliest.timer` bu ölçümü günde bir kaydeder.

Bu yüzden aşağıdakiler diğer tüm geliştirme adımlarından **önce** gelir:

1. `earliest_timestamp` günlük kaydedilir — pencerenin gerçekten kaydığı doğrulanır
2. Hedef evrenin tam 1m geçmişi toplu indirilir (~9 MB/sembol × 967 ≈ 9 GB)
3. Günlük cron: universe anlık görüntüsü + artımlı mum toplama

**İkinci kaynak.** 13 ay, 3 haftaya kadar taşınan pozisyonlar için az (≈20 örtüşmeyen
pencere) ve tek rejim. Uzun tarihsel backtest için Binance 1m geçmişi değerlendirilecek;
BingX verisi son dönem doğrulaması olarak kalır. Her rapor hangi kaynakla üretildiğini
belirtir. `ccxt` zaten soyutladığı için maliyeti düşük.

---

## 4. Depolama kararı

Üç farklı ihtiyaç, üç farklı araç.

### 4.1 Karar logu → JSONL, append-only

`logs/decisions/{yyyy-mm-dd}.jsonl` — her satır bir karar olayı. Dosya asla değiştirilmez.

Neden JSON: karar kaydının şeması sürekli genişleyecek (yeni feature, yeni kural).
Şemasız append bunu ağrısız yapar. Grep'lenebilir, replay edilebilir, DuckDB doğrudan okur.

**Karar kaydı şeması:**

```json
{
  "decision_id": "uuid",
  "ts": "2026-09-10T14:32:00Z",
  "symbol": "BTC-USDT",
  "event": "ENTRY | ADD | ADD_REJECTED | EXIT | KILL | NO_ACTION",
  "zone_id": "uuid",

  "inputs": {
    "price": 63120.5,
    "atr_14": 380.2,
    "zone": { "bias": "LONG", "level_070": 63100, "level_079": 62850, "state": "TOUCHED" },
    "mtf_ob": { "tf": "15m", "found": true, "strength": 0.72 },
    "equity": 1013.44,
    "unrealized_pnl": -6.20,
    "open_margin_pct": 3.1
  },

  "rules_evaluated": [
    { "rule": "R-ADD-01", "result": "PASS" },
    { "rule": "ADD-REJECT-B", "result": "PASS", "detail": "3.1% < 10%" },
    { "rule": "ADD-REJECT-C", "result": "FAIL", "detail": "OB hacimle kırıldı: vol=4.2x avg" }
  ],

  "outcome": "ADD_REJECTED",
  "reason": "ADD-REJECT-C",

  "orders": [],
  "spec_version": "v0.1",
  "code_version": "git-sha"
}
```

**En kritik alan `inputs`.** Kararın çıktısı değil, girdisi loglanır. Bu olmadan
"neden böyle karar verdi" sorusu sonradan cevaplanamaz — sadece ne yaptığı görülür.

`rules_evaluated` alanı, botun "düşünce tarzını" verir: hangi kural bakıldı, hangisi geçti,
hangisi engelledi. Reddedilen kararlar da loglanır — sadece yapılan işlemler değil.

### 4.2 Canlı durum → SQLite

`state.db`. Transaction ve çökme sonrası kurtarma gerektiren her şey:

| Tablo | İçerik |
|---|---|
| `zones` | Zone nesneleri ve durumları (R-ZONE-01) |
| `positions` | Açık pozisyonlar, ortalama maliyet, ekleme sayısı |
| `orders` | Gönderilen emirler, `client_order_id`, durum |
| `daily_reference` | Gün açılış equity'si (R-RISK-03) |
| `kill_events` | Kill switch tetiklenmeleri |

SQLite seçilme sebebi: tek dosya, sunucu süreci yok, ACID garantili. 2GB VDS için fazlasıyla yeterli.
Ölçek sorunu çıkarsa Postgres'e geçiş kolay.

### 4.3 Analiz → DuckDB

Ayrı bir saklama değil, sorgu motoru. Log ve veri dosyalarını yerinde okur:

```sql
SELECT reason, count(*)
FROM read_json_auto('logs/decisions/*.jsonl')
WHERE outcome = 'ADD_REJECTED'
GROUP BY reason ORDER BY 2 DESC;
```

ETL yok, senkron sorunu yok.

---

## 5. Emir yönetimi

Eski repodaki hataların tekrarlanmaması için zorunlu kurallar:

| Kural | Gerekçe |
|---|---|
| Her emir bir `client_order_id` taşır | Retry çift pozisyon açmasın |
| TP/SL emirleri `reduceOnly` | Biri dolduğunda diğeri ters pozisyon açmasın |
| Emir gönderildi + teyit alınamadı → R-KILL-02 | Belirsiz pozisyon durumu en tehlikeli hâl |
| Miktar ve fiyat hassasiyeti borsadan çekilir | Elle yazılmış ondalık tablosu yasak (`tickSize`, `stepSize`) |
| Fiyatlar hiçbir zaman string'e format'lanıp geri parse edilmez | Sayı sayı olarak taşınır, sadece ekranda format'lanır |
| Her emir sonrası pozisyon uzlaşması | Borsa durumu ile yerel durum karşılaştırılır (R-KILL-03) |

**Paper trading modu:** aynı kod yolu, sahte broker. Gerçek borsaya emir giden tek yer
`ExecutionAdapter` arayüzü. `PaperAdapter` ve `LiveAdapter` aynı arayüzü uygular.
Böylece paper'da test edilen kod ile canlıda çalışan kod aynı olur.

---

## 6. LLM'in yeri

LLM üç yerde kullanılır, hiçbiri karar hattında değil:

**6.1 — Araştırma asistanı (oturum içi).** Kural formalizasyonu, kod yazımı, backtest
sonucu yorumlama. Yani şu an yaptığımız iş.

**6.2 — Bağımsız denetçi (Gemini).** Farklı model = farklı kör nokta. Görev tanımı:
kodda ve backtest sonuçlarında look-ahead bias, overfitting, veri sızıntısı aramak.
Onaylamak değil, kırmak.

**6.3 — Yapılandırılmamış veri → feature.** Haber, duyuru, borsa bildirimi gibi metinleri
sayısal feature'a çevirmek. Çıktısı **yapılandırılmış JSON** olmalı, serbest metin değil.
Bu katman devreye alınırsa: çıktısı diğer feature'lar gibi loglanır, ve LLM erişilemez
durumdayken bot çalışmaya devam eder (feature eksik olarak işaretlenir, karar buna göre verilir).

**Yasak:** LLM'in pozisyon açma/kapatma/boyutlandırma kararı vermesi, risk sınırını
değiştirmesi, kill switch'i devre dışı bırakması.

**Ayrıca yasak:** botun kendi loglarına bakıp parametrelerini otomatik ayarlaması.
Küçük örneklem üzerinde overfit etmenin en hızlı yolu. Log insan analizi içindir;
değişiklik yeni bir spec versiyonu olarak yapılır.

---

## 7. Ortam

| Aşama | Nerede | Not |
|---|---|---|
| Veri toplama, backtest, araştırma | Lokal PC | Uptime gerekmiyor, hız önemli |
| Paper trading | VDS 2–4GB | 7/24 uptime şart, PC uyur |
| Canlı | Kapsam dışı | Paper sonuçları değerlendirildikten sonra ayrıca ele alınır |

Ücretsiz hosting kullanılmaz: süreçleri sessizce uyutur/öldürür, paper trading koşusunu
fark edilmeden bozar.

**VDS üzerinde zorunlu:** process supervisor (systemd), heartbeat izleme, dışarıdan
erişilebilir acil durdurma. R-RISK-02 gereği stop borsada olmadığı için, botun ayakta
olduğunu bilmek kritik.

---

## 8. Sürümleme

- Her karar kaydı `spec_version` ve `code_version` taşır
- `STRATEGY_SPEC.md` değişirse versiyon artar ve önceki backtest sonuçları geçersiz sayılır
- Backtest sonuçları hangi spec versiyonuyla üretildiği belirtilmeden raporlanmaz
