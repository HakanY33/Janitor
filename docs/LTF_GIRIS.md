# Alt zaman dilimi girişi (5m) — tasarım

**Durum (2026-10-07):** kullanıcı soruları cevapladı ve varsayılanların çoğunu değiştirdi →
**spec v0.11'e girdi ve kodlandı** (`STRATEGY_SPEC.md` §0.1 OB, `R-ENTRY-02`, `R-RISK-02`,
`R-ADD-01/03`, `OPEN-67`). Ölçüm #31 + çıkarma kolları `docs/measurements/ltf_31.md`. Aşağıdaki
metin 2026-10-06 tasarımıdır; cevaplar en altta.

**Cevaplar (kullanıcı, 2026-10-07):** (1) "bantta geçerli OB varsa" → mevcut kesişim kuralı (§0.1)
ve `R-ENTRY-05`; OB'nin zone `PRIMED`'den önce doğmuş olması engel değil (yeni koşul eklenmedi,
mevcut okuma — kullanıcı ayrıca belirtmedi). Tasarımdaki "yalnızca
5m" yerine OB kaynakları 5m + 30m + 4h; OTE girişi (0.70) de kalır, ikisi birden varsa OB önceliklidir.
(2) her zaman dilimi kendi B2 swing'leriyle (yalnızca BoS için). (3)–(4) stop OB'nin high/low'u,
tampon yok; `1` her durumda kapatır; OTE girişinde stop `1`. (5) ilk dokunulacak kenar. (6) emir
zone ölene kadar yaşar, 0.50'ye dönüş iptal etmez. (7) %1 marjin × maks kaldıraç — maks kaldıraç
anahtarsız alınamıyor, `OPEN-67`. (8) ekleme açık: OTE girişinde giriş–`1` arası OB, 1-1, en fazla
3, `ADD-REJECT-E`, `R-ADD-04`. (9) boşluk muhafazakâr: eksik kaynak mumlu 5m/4h mumu OB/BoS'a
katılmaz (ajan kararı, kullanıcı sorulmadan istedi). Taban: spec v0.10 (#30 kurgusu: B2 + `son_supuren`, OB = 1. mumun
high–low'u, `OPEN-66` A1+B).

## Amaç

30m zone'un giriş bandında (0.70–0.79) 30m OB'yi beklemek yerine, girişi 5m'de oluşan yeni bir OB'ye
bağlamak. Beklenen kazanç: daha dar stop ve aynı hedeflerle daha yüksek R. Kullanıcının hedefiyle
uyumlu: az ama isabetli işlem. Bantta 5m OB oluşmazsa işlem yok.

## Akış

```
30m zone PRIMED (R-ZONE-*, değişmez)
   │  fiyat 0.70–0.79 bandında
   ▼
5m OB bekle ── aynı tanım: 3 mum + (c) ardışık değil + (d) 5m yapı kırılması
   │  yön zone'la aynı (SHORT zone → arz OB, LONG → talep OB)
   ▼
giriş: 5m OB'den bekleyen limit (R-ENTRY-02'nin "OB'den giriş"i, 5m OB ile)
stop:  5m OB'nin ötesi (SHORT: OB high'ının üstü · LONG: OB low'unun altı)
TP1:   30m zone'un 0.50'si (R-EXIT-01, ~%50 + breakeven) · nihai TP: 30m zone'un 0'ı (R-EXIT-02)
   │
   └─ bantta 5m OB yok / zone öldü / bant terk edildi → emir yok
```

## Parçalar ve mevcut koda yerleşim

| Parça | Nereden | Not |
|---|---|---|
| 5m mumları | 1m'den yeniden örnekleme (`collect` 5m toplamıyor) | Kapanmış 5m mumu ancak 5. 1m mumu kapanınca bilinir (CLAUDE.md #3). Sınırlar UTC 5 dk. |
| 5m OB | `detect_order_blocks(d5, sym, "5m")` | `R-ZONE-09` tespiti 5m ve üstünde izinli (`require_detect_tf`). `known_at` = 3. 5m mumunun kapanışı. |
| 5m A1 + B | `ob_kurallari(obs5, d5, swing5)` | Swing tanımı 5m'de **hangi aday?** (açık soru 2). |
| Uygunluk | `ob_eligible` + "bant içinde doğdu" | Yeni koşul: OB, zone `PRIMED` olduktan **sonra** ve fiyat banttayken bilinmiş olmalı (açık soru 1). |
| Emir | `Backtest.order_for` / `_hedef` | Bugünkü 30m OB yolu yerine 5m OB kenarı. Her 1m kapanışında yeniden hesap (`OPEN-41`) aynen. |
| Stop | `R-RISK-02` | **Çakışma:** spec "nihai stop her zaman `1` seviyesi" diyor. Bu tasarım iç stopu 5m OB'nin ötesine taşır → `R-RISK-02` değişmeli (açık soru 4). |
| Boyut | `R-ENTRY-03` | Notional sabit (1 × equity). Stop daralınca işlem başı risk küçülür; boyut riskten türetilmez (`OPEN-34` açık). |
| Sürtünme | `R-ENTRY-06` | Giriş→TP1 mesafesi 30m zone'dan gelir, değişmez; taban geçerli kalır. |

## Look-ahead denetimi (CLAUDE.md #3)

- 5m OB, kendi 3. 5m mumunun kapanışından önce kullanılamaz; BoS damgası kırılma mumunun kapanışı.
- "Bant içinde" koşulu 1m kapanışlarından değerlendirilir; 5m OB'nin bilindiği an ≥ bantta olunan an.
- Canlı ↔ backtest: 5m önek tespiti 30m'deki gibi `build_from_frames` / `replay.kapanis` yoluyla
  yapılır (tek kod yolu, `docs/LIVE.md` A2). Önek kararlılığı testle doğrulanmalı.

## Ölçüm planı (kod onaylandıktan sonra)

#31 = #30 + 5m giriş, aynı dilim, 20 sembol, 100 USDT. Rapor #30 ile aynı satır. Ayrıca: bantta 5m OB
oluşan zone oranı, stop mesafesinin leg'e oranı (30m `1`'e kıyasla), ortalama R. Fark #28/#29
gibi sembol-ay eşleşik bootstrap'la sınanır (`scripts/bootstrap_fark.py`).

## Açık sorular

1. **"Bant içindeyken" ne demek?** (a) 5m OB'nin bölgesi bandı kesiyor mu, (b) OB bilindiği anda fiyat
   bantta mı, (c) OB'nin üç mumu da bant içinde mi? Zone `PRIMED` olmadan önce doğmuş 5m OB sayılır mı?
2. **5m'de swing tanımı:** BoS için 5m swing'leri hangi kuralla — B2 (ATR zigzag, `k = 2`) 5m'de mi,
   yoksa 30m swing'leri mi (30m'de son karşı swing'i kıran 5m hareketi)?
3. **Stopun konumu:** OB'nin high/low'u mu, artı tampon mu (tick, ATR payı, spread)? Stop 30m `1`'den
   uzaksa (bandın derin tarafında 5m OB) hangisi geçerli?
4. **`R-RISK-02` ile ilişki:** iç stop 5m OB'ye taşınırsa `1` seviyesi ne olur — zone ölümü (`1`
   teması) ayrıca pozisyonu kapatır mı? Felaket stopu `1.10`'da kalır mı, 5m stopa göre mi ölçeklenir?
5. **Birden çok 5m OB:** bantta ardışık olmayan birden fazla geçerli 5m OB oluşursa hangisinden girilir
   (ilk, en derin, en son)? Giriş dolmadan yeni OB gelirse emir taşınır mı?
6. **Mitigasyon / emir ömrü:** 5m OB mitige olup emir dolmazsa (fiyat dokunup döndü) zone için yeni
   5m OB beklenir mi, yoksa zone tüketilmiş mi sayılır?
7. **Boyut:** stop daralınca notional sabit mi kalsın (risk küçülür), yoksa risk sabitlenip notional mı
   büyüsün? İkincisi `OPEN-34` ve `R-RISK-05` (likidasyon tamponu) ile birlikte ele alınmalı.
8. **Ekleme (`R-ADD-*`):** v1'de kapalı; 5m girişle de kapalı mı kalır?
9. **Veri:** 5m 1m'den türetilecek — 1m boşluklarında (eksik dakika) 5m mumu kurulur mu, atlanır mı?
