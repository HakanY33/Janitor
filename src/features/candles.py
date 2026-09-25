"""Mum gövdesi istatistikleri — OB ve FVG'nin ortak paydası.

Spec: §0.1 (impuls tanımı), R-ADD-06 (normalden büyük gövde), R-ENTRY-05 (FVG genişliği).

`reference_body` iki ayrı kuralın paydasıdır: impuls eşiği (`IMPULSE_MULT × medyan`) ve
FVG genişlik eşiği (`0.44 × medyan`). İkisi de "son 20 mumun medyan gövdesi" diyor, aynı
seri olmalı. Burada durmasının tek sebebi budur — `ob.py` `fvg.py`'yi içe aktardığı için
paydanın ikisinden birinde yaşaması döngüsel bağımlılık üretirdi.
"""
from __future__ import annotations

import pandas as pd

BODY_LOOKBACK = 20  # referans gövde medyanının penceresi


def reference_body(df: pd.DataFrame, lookback: int = BODY_LOOKBACK) -> pd.Series:
    """Geçmiş mumların medyan gövdesi. `shift(1)`: mum kendi eşiğini yükseltemez.

    İlk mumlarda NaN döner; NaN ile yapılan her karşılaştırma False olduğu için
    yetersiz geçmişte ne impuls ne de geniş FVG tespit edilir (CLAUDE.md #3'ün
    yan faydası: eşik, henüz bilinmeyen bir geçmişten türetilemez).
    """
    body = (df.close - df.open).abs()
    return body.rolling(lookback, min_periods=5).median().shift(1)
