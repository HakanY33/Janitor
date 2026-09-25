# Ölçüm · Hipotez testleri

Kural metni: `docs/STRATEGY_SPEC.md` — `R-ADD-05`, `R-ZONE-02`, `R-ZONE-07`.
Bu dosya yalnızca ölçüm sonuçlarını ve gerekçelerini taşır.

---

## Hipotez testi sonuçları (2026-09)

20 sembol, 30m, en eski %80, 19.917 OB. Menzil tabanı impuls kapanışı.

| Hipotez | Kaynak | Sembol tutarlılığı | Sonuç |
|---|---|---|---|
| İçinde dolmamış FVG → geniş menzil | `R-ADD-05` | 1/20 | **Gürültü** |
| Ters yönlü OB → dar menzil | `R-ADD-05` | 20/20 | Doğrulandı, etki ~0.1 sd |
| Ardışık OB serisi → dar menzil | `R-ADD-05` | 0/20 | **Ters yönde tutarlı** |
| 4h+ yön uyumu → geniş menzil | `R-ZONE-07` | 20/20 | Doğrulandı, etki ~0.1 sd |
| Likidite süpürmesi → güçlü OB | `R-ZONE-02` | — | **Ölçüm artefaktı** |

## Metodolojik notlar — sonraki ölçümlerde de geçerli

1. **Havuzlanmış t istatistiği şişiktir.** Kripto sembolleri yüksek korelasyonlu;
   19.917 gözlem 19.917 bağımsız gözlem değil. Dürüst ölçü **sembol tutarlılığıdır**.
2. **Menzil tabanı sonucu belirler.** Taban OB sınırı alındığında süpürme hipotezi
   yapay bir etki üretiyordu (−0.67 → +0.03). İmpuls kapanışı tabanı doğru olanıdır;
   diğer etkiler de bu tabanda yarıya iniyor.
3. **Menzil, "çalışma"nın vekilidir ve muhtemelen yanlış vekil.** Stratejinin gerçek
   ölçütü ikili: *OB'den girilseydi, geçersiz olmadan `0.50`'ye ulaşır mıydı?*
   Hipotezler bu metrikle tekrar ölçülmeden çürütülmüş sayılmaz — özellikle
   "ardışık OB" maddesi.

---

**Üreten betik:** `scripts/measure_ob.py c`
