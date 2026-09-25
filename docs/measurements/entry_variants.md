# Ölçüm · Giriş seviyesi varyantları

Kural metni: `docs/STRATEGY_SPEC.md` — `R-ENTRY-02`, `R-ENTRY-05`.
Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır.

Soru: `R-ENTRY-02`'nin **tetiği** değiştirilirse beklenti değişiyor mu? Zone'un
`TOUCHED`'a geçmesi (0.70 teması) her varyantta ön koşuldur — değişen yalnızca
"dolum hangi fiyatta olsun".

---

## 20 sembol — tam koşu (kesildi)

Koşu makine uykusu yüzünden **1/5 varyantta** durdu. Elde olan tek satır:

| Varyant | Giriş | Brüt bps | Net bps | Gidiş-dönüş maliyet |
|---|---|---|---|---|
| 0.70 ilk temas | 3.122 | **+0.78** | **−9.41** | 14.27 bps |

## 1 sembol (BTC) — tam ızgara

Beş varyant da koştu. Sembol sayısı düşük, mutlak rakam değil **sıralama** okunmalı:

| Varyant | Giriş | Dolum | Bant konumu | Brüt bps | Net bps | Net getiri |
|---|---|---|---|---|---|---|
| 0.70 ilk temas | 566 | 79.5% | 0.000 | **+0.17** | −14.10 | −71.4% |
| 0.75 teması | 516 | 72.5% | 0.556 | **+0.31** | −13.71 | −65.4% |
| 0.79 teması | 487 | 68.4% | 1.000 | −0.88 | −15.47 | −66.5% |
| bant içi 3 mum, en iyi fiyat | 493 | 69.2% | 0.527 | −1.21 | −15.42 | −69.3% |
| OB/FVG varsa oradan, yoksa 0.79 | 505 | 70.9% | 0.810 | −1.03 | −15.67 | −68.9% |

**Sonuç: brüt edge giriş seviyesinden bağımsız ve ≈ 0.** Beş varyantın brüt beklentisi
−1.2 ile +0.3 bps arasında; gidiş-dönüş maliyeti her koşuda ~14 bps. Daha iyi bir giriş
seviyesi aramak bu tabloya göre boş bir arama — mekanik OTE'nin kendisinde maliyeti
karşılayacak bir kenar yok.

Bant içinde derine inmek dolum oranını düşürüyor (79.5% → 68.4%) ama fiyat avantajı
bunu telafi etmiyor.

> **Nedensellik notu.** "Pencerede görülen en iyi fiyattan gir" kelimesi kelimesine
> uygulanırsa look-ahead olur (CLAUDE.md #3). Nedensel karşılığı uygulandı: pencere
> boyunca en iyi fiyat izlenir, pencere bitince o seviyeye limit konur ve fiyat oraya
> geri gelirse dolar. Dolmayan girişler sayaçta görünür.

---

**Üreten betik:** `scripts/entry_variants.py`
**Ham çıktı:** `logs/entry_variants.csv`, `logs/ev_smoke.txt`
