"""Giriş kuralları — gösterge uygunluğu ve tetik.

Spec: R-ENTRY-05 (OB/FVG uygunluğu), R-ENTRY-02 (tetik), R-ZONE-03 (giriş bandı),
§0 (bias).

**R-ENTRY-05 iki ölçüt koyar ve ikisi de nedenseldir** — karar anında bilinirler:

| Gösterge | Ölçüt |
|---|---|
| OB | **unmitige**: fiyat gövdeye hiç dönmemiş olmalı (bir kez uğradıysa tüketilmiş) |
| FVG | karar anında **dolmamış** *ve* genişlik ≥ `MIN_FVG_WIDTH_RATIO × medyan gövde` |

Spec'in altını çizdiği şey: "20 mum dayandı" gibi geriye dönük bir ölçüt
**kullanılamaz**, çünkü karar anında bilinemez. Buradaki her iki ölçüt de
`at` parametresine göre değerlendirilir ve o andan sonraki hiçbir olayı görmez.

**Yön eşleşmesi.** R-ENTRY-02 (1) "yöne uygun **OB**" der; FVG için (2) yalnızca
"bantta FVG varsa" der. Spec'te olmayan bir kısıt eklenmez (CLAUDE.md), bu yüzden
yön eşleşmesi OB'ye uygulanır, FVG'ye uygulanmaz. Zone bias'ı gösterge yönüne
şöyle çevrilir: `LONG` → `BULLISH` (talep bloğu), `SHORT` → `BEARISH` (arz bloğu).
"""
from __future__ import annotations

from datetime import datetime

from src.features.fvg import BEARISH, BULLISH, FVG
from src.features.ob import OrderBlock
from src.zones.model import Zone

MIN_FVG_WIDTH_RATIO = 0.44
"""R-ENTRY-05 · FVG genişliği / son 20 mumun medyan gövdesi için alt sınır.

Ölçüm dayanağı spec'te: 20 sembol / 30m / en eski %80 / 92.439 FVG. "Dolmamış" şartıyla
birlikte OB tabanına (23.5 mum/OB) denk yoğunluk veren dilim.
"""

BIAS_TO_DIRECTION = {"LONG": BULLISH, "SHORT": BEARISH}


def band(zone: Zone) -> tuple[float, float]:
    """R-ZONE-03 · giriş bandı `0.70–0.79`, (alt, üst) olarak sıralı."""
    return min(zone.level_070, zone.level_079), max(zone.level_070, zone.level_079)


def _overlaps(top: float, bottom: float, band_low: float, band_high: float) -> bool:
    """§0.1 · "kesişim yeterlidir, tam kapsama aranmaz"."""
    return bottom <= band_high and top >= band_low


def ob_eligible(ob: OrderBlock, zone: Zone, at: datetime) -> bool:
    """R-ENTRY-05 · OB `at` anında giriş adayı mı.

    Dört koşul: bilinebilir olmuş · yöne uygun · giriş bandını kesiyor · unmitige.
    """
    if ob.impulse_at > at:  # OB henüz bilinmiyor (CLAUDE.md #3)
        return False
    if ob.direction != BIAS_TO_DIRECTION[zone.bias]:  # R-ENTRY-02 (1) · yöne uygun
        return False
    if not _overlaps(ob.top, ob.bottom, *band(zone)):
        return False
    # R-ENTRY-05 · fiyat bir kez uğradıysa bölge tüketilmiştir.
    return ob.mitigated_at is None or ob.mitigated_at > at


def fvg_eligible(fvg: FVG, zone: Zone, at: datetime, min_ratio: float = MIN_FVG_WIDTH_RATIO) -> bool:
    """R-ENTRY-05 · FVG `at` anında giriş adayı mı.

    Dört koşul: bilinebilir olmuş · giriş bandını kesiyor · dolmamış · yeterince geniş.
    Yön eşleşmesi aranmaz (bkz. modül docstring).
    """
    if fvg.created_at > at:
        return False
    if not _overlaps(fvg.top, fvg.bottom, *band(zone)):
        return False
    if not (fvg.filled_at is None or fvg.filled_at > at):  # karar anında dolmamış
        return False
    # Payda tanımsızsa (`width_ratio is None`) oran yoktur; eşik geçilemez.
    return fvg.width_ratio is not None and fvg.width_ratio >= min_ratio


def eligible_obs(obs, zone: Zone, at: datetime) -> list[OrderBlock]:
    return [o for o in obs if ob_eligible(o, zone, at)]


def eligible_fvgs(fvgs, zone: Zone, at: datetime, min_ratio: float = MIN_FVG_WIDTH_RATIO) -> list[FVG]:
    return [f for f in fvgs if fvg_eligible(f, zone, at, min_ratio)]
