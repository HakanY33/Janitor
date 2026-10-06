# v4 puanı

Kaynak `docs/inceleme/v4/etiketler.json` · `scripts/v4_puan.py` · ön kayıt `docs/inceleme/v2/adaylar.md` (2026-10-05 ek): `B2` + `son_supuren`, eşik %28.

## (a) OTE — ön kayıtlı doğrulama

**GEÇTİ** — çift isabet **8/12 (67%)**, eşik %28.

| ölçüt | değer |
|---|---:|
| setup'lı / setup yok | 12 / 18 |
| 0 geri çağırma | 12/12 |
| 1 geri çağırma | 12/12 |
| yanlış alarm (rastgele, setup yok) | 7/18 |
| teyit gecikmesi medyanı (saat) | 1.5 |
| 0.50 teması eğitim diliminde yok | 1 |
| isabet eden anlar | r03, r06, r07, r09, r13, r14, r18, r22 |

## (b) OB etiketleri (açıklayıcı)

Motorun gösterdiği 234 OB: doğru 147, yanlış 84, etiketsiz 3 → **doğruluk 64%**. Kaçırılan (kullanıcının eklediği) 0 (bunların 0'i motorun bir OB'siyle aynı 1. mum). OB adımı açılmayan an: 11.

| özellik (medyan) | doğru | yanlış |
|---|---:|---:|
| OB sayısı | 147 | 84 |
| talep / toplam | 67/147 | 44/84 |
| karar anında mitige | 122/147 | 74/84 |
| genişlik (bps) | 71.01 | 58.74 |
| yaş (mum, karara) | 135.00 | 142.50 |
| mitigasyona kadar (mum) | 4.50 | 2.00 |
| 2. mum gövdesi / medyan gövde | 3.00 | 2.51 |
| 1–3. mum boşluğu / medyan gövde | 1.00 | 0.59 |

