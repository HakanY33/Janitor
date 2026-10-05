# Swing tespiti — aday tanımlar ve seçim ölçütü

**Tarih:** 2026-10-02 · **Durum:** ön kayıt. Etiketler (`etiketler.json`) gelmeden yazıldı;
etiketler görüldükten sonra tanım, parametre ızgarası ve ölçüt **değiştirilmez**.
Uygulama yok — kod etiketler gelince, yalnızca bu dört aday için yazılır.

## Sorun

Kullanıcı 30 işlemin 28'inde OTE çapalarını yanlış buldu; doğru çizilen ikisi (#25, #30)
kazandı. Mevcut tanım (`src/features/structure.py`): fraktal `N = 2` (5 mumluk pencere) +
`0.5 × ATR(14)` yer değiştirme, 30m. Bu çok yerel: 2,5 saatlik pencerede her kıpırtı swing
olur, "süpürme" (`swept`) bir önceki *küçük* swing'in aşılması demek olur.

Kullanıcının tarifi (R-ZONE-02 ile aynı): **bakılan bölgedeki en yüksek / en düşük noktalar,
kendinden önceki likiditeyi almış uçlar.** Notlardan iki ek ipucu: "grafiğe genişten bak"
(#4, #5, #8, #23) ve "hacimsiz, yatay giden mumlarda setup yok" (#13, #17, #30).

## Adaylar

Hepsi 30m'de, nedensel (teyit anı `known_at` taşır, CLAUDE.md #3). Leg seçimi
(`zones/detect.py`: `anchor_1` = süpüren swing, `anchor_0` = R-ZONE-10 penceresindeki en uç
karşı swing) **aynı kalır**; değişen yalnızca swing listesi. Her adayın ızgarası en fazla
iki değer — 30 etikete parametre uydurmamak için.

| | Tanım | Izgara | Teyit gecikmesi |
|---|---|---|---|
| **A · Büyük fraktal** | `high[i]`, önceki ve sonraki `N` mumun high'larından büyük; yer değiştirme filtresi aynı (`0.5 × ATR`) | `N` ∈ {6, 12} (3 / 6 saat) | `N` mum |
| **B · ATR zigzag** | Fraktal yok. Koşan uç izlenir; fiyat uçtan `k × ATR(14)` geri çekilince uç swing olarak kabul edilir ve yön döner | `k` ∈ {2, 3} | içsel (geri çekilme süresi) |
| **C · Pencerenin ucu + süpürme** | `i` mumu, `[i − L, i + M]` penceresinin en yüksek high'ı **ve** pencere içinde daha önce kabul edilmiş bir swing high'ı aşmış (likidite almış). Low simetrik. `M = 4` sabit | `L` ∈ {96, 336} (2 gün / 1 hafta) | `M` mum |
| **D · 4h çapa, 30m zaman** | Mevcut tanım (`N = 2`, `0.5 × ATR`) 4h mumlarda; çapa fiyatı 4h ucu, zamanı o ucu üreten 30m mum | — | 2 × 4h |

Notlar:

- **C** kullanıcının tarifine en yakın olanı: "bölgedeki en uç" = `L` penceresinin ucu,
  "likiditeyi almış" = pencerede daha önceki bir swing'i aşmış.
- **D** karşılaştırma için: kullanıcı #8'de "4h'ta OTE bulup alt zamana inmek — biz bunu
  yapmıyoruz, genişten bakıp doğru likidite bölgesinden çizeriz" dedi. D o yolun ucuz
  vekili; kazanırsa bu bir bulgudur, kural değil.
- Gecikme bedeli gerçek: büyük pencere çapayı daha geç bilir. Ölçüt bunu "zamanında"
  şartıyla cezalandırır (aşağıda); aksi hâlde en geniş pencere hep kazanırdı.
- "Hacimsiz/yatay setup yok" bir **zone filtresidir**, swing tanımı değil — bu
  karşılaştırmaya girmez, ayrı ele alınır.

## Ölçüt — doğru çapayı bulma oranı

Etiket: işlem başına doğru `0` (30m mum açılışı UTC + fiyat), doğru `1`, ya da "setup yok".

**Eşleşme.** Adayın swing listesinde, etiketle **aynı tipte** (tepe/dip) ve zamanı etiket
mumundan en çok **±2 mum** (±1 saat) uzakta bir swing varsa o çapa bulunmuştur. Fiyat ayrıca
aranmaz — swing'in fiyatı zaten o mumun ucudur; ±2 mum, kullanıcının komşu mumu seçmesini tolere eder.

**Birincil ölçüt — çift isabet oranı:**

```
isabet = adayın kurduğu zone'lardan biri iki çapayı da eşleştiriyor
         VE o zone'un known_at'i ≤ etiketli leg'de 1'den sonraki ilk 0.50 teması (1m)
oran   = isabet sayısı / setup'lı etiket sayısı
```

"Zamanında" şartı olmadan doğru çapayı geç bulan tanım ödüllendirilirdi — o zone'a giriş
zaten kaçmıştır.

**İkincil ölçütler** (eşitlikte, sırayla):

1. **Yanlış alarm:** "setup yok" etiketli işlemlerde, bot'un giriş anında bu adayın bant
   (`0.70–0.79`) içinde aktif bir zone'u var mı. Oran düşük olan iyi.
2. **Tek çapa geri çağırma:** `0` ve `1` ayrı ayrı bulunma oranı (çift isabet sıfıra yakınsa
   hangi çapanın kaçtığını söyler).
3. **Teyit gecikmesi:** isabet eden zone'larda `known_at − anchor_1` medyanı. Kısa olan iyi.

**Rapor** (yalnızca bilgi, seçime girmez): sembol-ay başına zone sayısı.

**Seçim kuralı.** En yüksek çift isabet oranı. Fark **≤ 2 işlem** (30'da) ise eşit sayılır
ve ikincil ölçütlere geçilir. Seçim **kâra göre yapılmaz**; seçilen tanımla backtest
ayrı bir adımdır ve sonucu bu seçimi değiştirmez.

**Örneklem uyarısı.** 30 etiketle %50 civarında bir oranın standart hatası ~%9; 2–3 işlemlik
fark gürültüdür. Öneri: seçim bu 30 ile yapılır, sonra **aynı tohumla seçilmemiş ikinci bir
30** etiketlenip seçilen adayın oranı orada bir kez doğrulanır. Doğrulamada oran birinci
30'un yarısının altına düşerse seçim geçersiz sayılır.

## Bilinen sınır

Etiketler insan gözüyle, sonradan bakılarak konur: kullanıcı grafiğin sağını görür. Ölçüt
yalnızca "zamanında" şartıyla bunu kısmen dengeler; çapanın kendisinin o an bilinebilir
olup olmadığını ölçmez. Etiketlenen çapa hiçbir nedensel tanımla zamanında bulunamıyorsa
bu da bir bulgudur (o setup canlıda yakalanamaz).

## Not — 2026-10-05: v4'ün amacı değişti (v4 etiketleri görülmeden yazıldı)

v4 (`docs/inceleme/v4/`, 30 rastgele an, tohum 20261005) **B3'ü olduğu gibi doğrulamak için
kullanılmayacak.** v3 teşhisi (`docs/inceleme/v3/eslestirme_teshis.md`) çift isabetin düşük
kalmasının nedenini swing tanımında değil **leg eşleştirmesinde** buldu: B3'te 44 setup'ın 22'si,
B2'de 32'si "yanlış 0" — kullanıcının `1`'i doğru bulunuyor, ama `anchor_0` daha yeni ve daha az
uç bir karşı swing'den alınıyor. Kullanıcının 0'ı motorunkinden B3'te 20/22, B2'de 32/32 daha
eski ve neredeyse hep motorun aday penceresinin (`_anchor_0`: "1'in aştığı aynı tip swing → 1")
solunda. Kullanıcının 0'ı çoğunlukla kendisi süpüren (`swept`) bir swing (B2 36/43).

v4, bu teşhisten çıkan **yeni eşleştirme kuralını** doğrulamak için kullanılır. Kural, v4
etiketleri açılmadan önce kullanıcı onayıyla buraya yazılır ve sonra değişmez. Teşhisin önerdiği
aday (örneklem içi, v3'e bakılarak bulundu — bu yüzden doğrulama şart):

- **`anchor_0` = `anchor_1`'den önceki son süpüren (`swept`) karşı swing** (pencere sınırı yok;
  süpüren yoksa son karşı swing). Swing listesi B2 (ATR zigzag `k = 2`).
- v3'te (örneklem içi) çift isabet: B2 **25/44**, B3 23/44 (mevcut kuralla B3 15/44). Ölçüt,
  eşleşme ve zamanında şartı aynı.

Doğrulama ölçütü: v4'teki setup'larda çift isabet oranı, v3'teki örneklem içi oranın (%57)
yarısının altına düşerse (< %28) kural geçersiz sayılır. Seçim yine kâra göre yapılmaz.

### 2026-10-05 (ek) — kural kesinleşti, v4 etiketleri açılmadan

Kullanıcı onayı: **"0 = 1'den önceki, kendisi de likidite almış son karşı swing, pencere sınırı
olmadan"** (süpüren yoksa son karşı swing). Kod: R-ZONE-10 seçeneği `son_supuren`
(`src/zones/detect.py:ANCHOR0`); varsayılan `pencere` değişmedi. v3'te ön kayıt ölçütleriyle
B2/B3 (`docs/inceleme/v3/swing_secim_son_supuren.md`): çift isabet B2 25/44, B3 23/44 → eşit
(≤ 2), yanlış alarm B2 0/6 · B3 2/6 → **seçilen B2 + `son_supuren`**. v4'te bu ikili bir kez
ölçülür; çift isabet < %28 → geçersiz. Bu metin bundan sonra değişmez.

v4 sayfası ayrıca OB etiketleri toplar (OTE'den sonra, ayrı alanlar); onlar bu ölçüte girmez.
