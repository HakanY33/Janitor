# Ölçüm · Tanı koşusu

Kural metni: `docs/STRATEGY_SPEC.md` — `R-ENTRY-02`, `R-ADD-04`, §8 (maliyet modeli,
zorunlu sayaçlar). Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır.

**Yapılandırma:** 20/20 sembol · en eski %80 · `K=0.25` · `T_rahat=0.50` ·
`T_kritik=0.08` · UYARI eklemeyi engellemiyor · MMR=0.005 · başlangıç bakiye 10.000.
`OPEN-27` daraltılmış çarpan kuralı, `OPEN-28` KRİTİK'te yarılama. Hiçbir eşik aranmadı.

---

## Brüt / net beklenti

| Kalem | Değer |
|---|---|
| İşlem sayısı (brüt koşu) | 6.866 |
| Brüt PnL toplam (sıfır maliyet) | +18.105,60 (%181,1) |
| **Brüt beklenti / işlem** | **12,61 bps** |
| **Gidiş-dönüş maliyeti / işlem** | **14,77 bps** |
| **Net beklenti / işlem** | **−2,17 bps** |

Maliyet dağılımı: komisyon **10,44 bps** · slippage **4,18 bps** · funding **0,16 bps**.

Başabaş için gereken brüt beklenti 14,77 bps/işlem; mevcut 12,61 → **açık −2,17 bps**.
Model maliyetten önce kâr ediyor, maliyetten sonra etmiyor. Aradaki fark dar — yani
sorun modelin yönünde değil, **işlem sayısında ve maliyet tarafında**.

## Girişlerin kaynağı — `R-ENTRY-02` dalları

Dal ataması kuralın önceliğine göre: OB varsa OB, yoksa FVG, o da yoksa çıplak 0.70.

| Dal | Adet | Pay | Toplam net | Ort bps | Kazanan | TP1 |
|---|---|---|---|---|---|---|
| (1) OB'den | 81 | **1,1%** | +86,16 | **+34,5** | 67,9% | 71,6% |
| (2) FVG'den | 1.276 | 17,3% | −1.344,21 | +5,0 | 55,2% | 67,0% |
| (3) çıplak 0.70 | 6.040 | **81,7%** | −8.719,18 | **−3,9** | 49,8% | 61,3% |

**Bu tablo stratejinin en güçlü sinyali.** Göstergeli girişler kârlı, çıplak temas
zararlı — ama hacmin %82'si çıplak temas. `R-ENTRY-02`'nin (3) maddesi ("gösterge
yoksa 0.70 teması geçerli giriştir") girişi kapılamadığı için `R-ENTRY-05` süzgeçleri
işlem sayısını azaltmıyor, yalnızca **etiketliyor**.

> OB dalı n=81 — küçük örnek, tek başına karar dayanağı değil. FVG dalı (n=1.276)
> pozitif ortalamaya rağmen toplamda negatif: dağılımın kuyruğu taşıyor.

## Dağılım

| Koşu | n | Medyan | Ortalama |
|---|---|---|---|
| BRÜT (sıfır maliyet) | 6.866 | 14,1 bps | 12,6 bps |
| NET (gerçek maliyet) | 7.397 | 0,5 bps | −1,9 bps |

## Likidasyon (§8 zorunlu sayaçlar)

Koşu içi likidasyon **0**. KRİTİK küçültme olayı 1, realize PnL −1,12.
min(equity / toplam notional) **%9,46** · min likidasyon mesafesi (MMR=0.005) **%8,96**.
MMR duyarlılığı %0,4 → %2,5 aralığının tamamında hayatta kalıyor.
MMR borsadan çekilemedi (kimlik doğrulama ister); birincil ölçü MMR'siz orandır.

---

**Üreten betik:** `scripts/diagnose.py`
**Ham çıktı:** `logs/diagnose.txt`, `logs/diagnose_trades.csv`, `logs/diagnose_add.txt`
