"""Deterministik kimlik: aynı girdi, her koşuda ve her makinede aynı `uuid5`.

`docs/LIVE.md` Ö3: canlıda her 30m kapanışında yeniden tespit edilen zone/OB/FVG'nin
"zaten bilinen" olduğu ancak kimlik girdiden türetilirse anlaşılır. Parite testi
(D0/D1) de kimlikle eşleştirir. Girdi, nesneyi tespit anında belirleyen alanlardır
(sembol, TF, çapa zamanları ve fiyatları) — sonradan değişen durum girmez.
"""
from __future__ import annotations

import uuid

NAMESPACE = uuid.UUID("5f0c1d0e-6a1b-5c3e-9f47-6a616e69746f")  # sabit; değişirse tüm kimlikler değişir


def stable_id(kind: str, *parts) -> str:
    """`kind|p1|p2|...` metninin `uuid5`'i, hex. Float `repr` ile yazılır (kayıpsız)."""
    metin = "|".join([kind, *(repr(float(p)) if isinstance(p, float) else str(p) for p in parts)])
    return uuid.uuid5(NAMESPACE, metin).hex
