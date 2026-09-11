# CLAUDE.md

Bu dosya, bu repoda çalışan her AI ajanının uyması gereken kuralları içerir.
Kod yazmadan önce oku. Şüphede kalırsan sor, tahmin etme.

---

## Proje

**Janitor** — OTE (likidite süpürme sonrası dönüş) modeline dayalı kripto vadeli işlem botu.
**Mevcut aşama: araştırma ve paper trading. Gerçek para kapsam dışı.**

Otorite sırası — çelişki varsa üstteki kazanır:

1. `docs/STRATEGY_SPEC.md` — strateji kuralları
2. `docs/ARCHITECTURE.md` — sistem tasarımı
3. Bu dosya — kodlama kuralları
4. Kod

**Spec'te olmayan bir davranışı kod uydurmaz.** Eksik bir kural fark edersen, makul bir
varsayımla doldurma; `OPEN-XX` olarak işaretle ve sor.

---

## Değişmez kurallar

Bunlar tartışmaya kapalı. İhlal eden PR reddedilir.

### 1. LLM karar hattında yer almaz
Pozisyon açma, kapatma, boyutlandırma ve risk kararları **deterministik koddadır**.
Hiçbir kod yolu bir dil modelinin çıktısına bağlı olarak emir üretmez.

### 2. Risk katmanı veto yetkisine sahiptir
`RISK` katmanı `STRATEGY`'nin kararını reddedebilir. Tersi mümkün değildir.
`R-RISK-05` (likidasyon tamponu) hiçbir koşulda atlanamaz, hiçbir bayrakla kapatılamaz.

### 3. Look-ahead bias yasak
Bir karar, karar anında mevcut olmayan hiçbir veriyi kullanamaz. Bu özellikle şunları kapsar:
- Kapanmamış mumun kapanış değeri
- `ta.pivothigh` benzeri, N mum sonra teyitlenen değerlerin erken kullanımı
- Geleceğe bakan `shift(-n)`, `iloc[i+1]`, ileriye doğru `fillna`

Her feature fonksiyonu, "bu değer T anında biliniyor muydu" testinden geçmeli.

### 4. Fiyat ve miktar sayıdır
Sayılar hiçbir zaman ekran metnine çevrilip geri parse edilmez. Formatlama yalnızca
sunum katmanında yapılır.

**`Decimal` nerede zorunlu:** para hesabı — pozisyon boyutu, notional, PnL, ortalama
maliyet, emir miktarı ve emir fiyatı. Yani borsaya giden veya hesabı etkileyen her sayı.

**`float64` nerede serbest:** ham piyasa verisi ve indikatör hesabı. ccxt zaten float
döndürür; `Decimal`'e çevirmek var olmayan hassasiyeti uydurmak olur.

Sınır `execution` katmanıdır: emir üretilirken değerler `Decimal`'e çevrilir ve borsanın
`tickSize` / `stepSize` değerlerine yuvarlanır.

### 5. Borsa parametreleri borsadan gelir
`tickSize`, `stepSize`, `quantityPrecision`, `maxLeverage`, komisyon oranları — hepsi
API'den çekilir ve önbelleklenir. Kodda elle yazılmış hassasiyet tablosu bulunamaz.

### 6. Her emir idempotenttir
Her emir bir `client_order_id` taşır. Retry çift pozisyon açamaz.

### 7. TP/SL emirleri `reduceOnly`
Aksi hâlde biri dolduğunda diğeri ters pozisyon açar.

### 8. Sessiz hata yasak
`except: pass` veya sadece `print` yapan `catch` bloğu yazılmaz. Her hata ya işlenir
ya yükseltilir ya da kill switch tetikler. Emir gönderildi ama teyit alınamadıysa
bu **en yüksek öncelikli** kill switch koşuludur (`R-KILL-02`).

### 9. Paper ve live aynı kod yolunu kullanır
Gerçek borsaya emir giden tek yer `ExecutionAdapter` arayüzüdür.
`PaperAdapter` ve `LiveAdapter` aynı arayüzü uygular. Strateji kodunda
`if paper_mode:` dalı bulunamaz.

### 10. Sır yok
API anahtarı, token, parola kodda veya commit'te yer almaz. Yalnızca ortam değişkeni.
`.env` `.gitignore`'dadır.

### 11. Git işlemleri kullanıcıya aittir
`git add`, `git commit`, `git push`, `git checkout`, `git merge`, `git rebase`, `git reset`
**çalıştırılmaz.** Branch açılmaz, PR oluşturulmaz. Tüm versiyon kontrolü kullanıcıya aittir.

`git status`, `git diff`, `git log` okuma amaçlı serbesttir.

Bir iş bitince ne değiştiğini özetle ve bırak — commit mesajı önerebilirsin, ama commit'i
atmazsın. Bu kural `.claude/settings.json` içinde de zorlanır.

---

## Repo yapısı

```
trade-bot/
├── CLAUDE.md
├── docs/
│   ├── STRATEGY_SPEC.md
│   └── ARCHITECTURE.md
├── src/
│   ├── data/          Toplama, saklama, doğrulama
│   ├── features/      İndikatör, OB, FVG, leg tespiti
│   ├── zones/         Zone store, durum makinesi
│   ├── strategy/      Giriş/ekleme/çıkış kuralları
│   ├── risk/          Sert sınırlar, kill switch
│   ├── execution/     ExecutionAdapter, emir yönetimi
│   └── ledger/        JSONL log, SQLite state
├── tests/
├── scripts/
├── data/              .gitignore
└── logs/              .gitignore
```

Katman yalnızca **altındaki** katmanı çağırır. `strategy` doğrudan `execution` çağırmaz;
`risk` üzerinden geçer.

---

## Kural izlenebilirliği

Spec'teki bir kuralı uygulayan her fonksiyon, kural ID'sini docstring'inde taşır:

```python
def check_add_allowed(position, zone, market) -> AddDecision:
    """Ekleme izni kontrolü.

    Spec: R-ADD-01 (izin koşulları), R-ADD-02 (red koşulları)
    """
```

Her kuralın en az bir testi vardır ve test adı kural ID'sini içerir:
`test_R_ADD_02_rejects_when_notional_cap_exceeded`

---

## Test kuralları

- Yeni davranış → önce test, sonra kod
- Veri doğrulama testleri (`ARCHITECTURE.md` §3) her veri seti için çalışır
- Zone durum makinesi için geçersiz geçişler açıkça test edilir
- Backtest sonuçları `spec_version` ve `code_version` olmadan raporlanmaz

**Ağa çıkan test yazılmaz.** Borsa yanıtları fixture olarak saklanır.

---

## Loglama

Her karar `logs/decisions/{tarih}.jsonl` dosyasına bir satır olarak yazılır.
Şema `ARCHITECTURE.md` §4.1'de.

Kritik: **kararın girdisi loglanır, sadece çıktısı değil.** `inputs` alanı, kararın
alındığı andaki tüm feature değerlerinin anlık görüntüsünü içerir. `rules_evaluated`
alanı hangi kuralın geçtiğini/kaldığını gösterir.

Reddedilen kararlar da loglanır — sadece açılan işlemler değil.

---

## Yapılmayacaklar

- Spec kapalı olmayan bir kuralı "makul varsayımla" doldurmak
- Otomatik parametre optimizasyonu / self-tuning (overfitting)
- Komisyon, funding veya slippage modellenmeden backtest sonucu raporlamak
- `data/` altındaki dosyaları commit etmek
- Sıfırdan backtest motoru yazmak — mevcut kütüphane değerlendirilmeden
- Mobil/arayüz kodu — v1 kapsamı dışında

---

## Çalışma sırası (v1)

Sıra bağlayıcıdır. Bir adım tamamlanmadan sonrakine geçilmez.

| # | Adım | Çıktı |
|---|---|---|
| 1 | Veri toplama + doğrulama testleri | `src/data/`, geçen test suite |
| 2 | Zone store + durum makinesi | `src/zones/`, R-ZONE-* testleri |
| 3 | Feature katmanı (OB, FVG, leg) | `src/features/` |
| 4 | Strateji kuralları | `src/strategy/`, R-ENTRY/ADD/EXIT testleri |
| 5 | Risk katmanı + kill switch | `src/risk/` |
| 6 | Backtest + zorunlu sayaçlar | `scripts/backtest.py` |
| 7 | PaperAdapter + canlı döngü | `src/execution/` |

**Şu an: adım 1.**
