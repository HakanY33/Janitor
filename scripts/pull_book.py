"""Sunucudaki emir defteri verisini yerel `data/` altina ceker. Gunde bir.

    python -m scripts.pull_book
    python -m scripts.pull_book --host janitor@179.61.147.81

1. Sunucuda `sha256sum data/*/*/book/*.parquet` (tek SSH baglantisi).
2. Yerelde ayni SHA-256'ya sahip dosya atlanir. Biten aylar bir kez iner; icinde
   bulunulan ayin dosyasi her gun degistigi icin her gun yeniden iner.
3. Kalanlar tek `tar` akisiyla gelir. Her dosya once gecici dosyaya yazilir, ozeti
   dogrulanir, sonra `os.replace` ile yerine konur (yarim dosya kalmaz).

**Uzerine yazma korumasi.** Yerel dosyada sunucuda olmayan bir dakika varsa (ornegin
yerel kayitci da kostu), dosya degistirilmez ve betik hata koduyla biter. Veri
kaybetmektense durmak tercih edilir (CLAUDE.md #8).

Sunucu dosyayi 30 dakikada bir yeniden yazar. Ozet ile indirme arasinda yazim olursa
ozet tutmaz; o dosya bir tur daha denenir.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pandas as pd

HOST = "janitor@179.61.147.81"
REMOTE_ROOT = "janitor"  # sunucuda ~/janitor
PATTERN = "data/*/*/book/*.parquet"
TUR = 3  # ozet tutmayan dosya icin deneme sayisi

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_sums(text: str) -> dict[str, str]:
    """`sha256sum` ciktisi -> {goreli yol: ozet}."""
    out = {}
    for line in text.splitlines():
        if line.strip():
            h, p = line.split(maxsplit=1)
            out[p.lstrip("*")] = h
    return out


def plan(remote: dict[str, str], root: Path) -> list[str]:
    """Inmesi gereken yollar: yerelde yok ya da ozeti farkli."""
    return [p for p, h in sorted(remote.items())
            if not (root / p).exists() or sha256(root / p) != h]


def install(data: bytes, dest: Path, expected: str) -> None:
    """Ozeti dogrular, yerel dakikalari korur, atomik yazar. Tutmazsa `ValueError`."""
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{dest}: SHA-256 tutmadi (sunucu yazarken okunmus olabilir)")
    if dest.exists():
        yeni = set(pd.read_parquet(io.BytesIO(data)).ts)
        eksik = set(pd.read_parquet(dest).ts) - yeni
        if eksik:
            raise RuntimeError(f"{dest}: yerelde sunucuda olmayan {len(eksik)} dakika var "
                               f"({min(eksik)} ..). Uzerine yazilmadi.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def ssh(host: str, cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "BatchMode=yes", host, cmd],
                          capture_output=True, check=True, **kw)


def main() -> int:
    p = argparse.ArgumentParser(description="Sunucudan defter verisi cek")
    p.add_argument("--host", default=HOST)
    p.add_argument("--root", type=Path, default=Path("."))
    a = p.parse_args()

    hata: set[str] = set()
    indi = atlandi = 0
    for tur in range(1, TUR + 1):
        remote = parse_sums(ssh(a.host, f"cd {REMOTE_ROOT} && sha256sum {PATTERN}",
                                text=True).stdout)
        gerek = plan(remote, a.root)
        if tur == 1:
            atlandi = len(remote) - len(gerek)
        if not gerek:
            break
        arsiv = ssh(a.host, f"cd {REMOTE_ROOT} && tar cf - " + " ".join(gerek)).stdout
        tekrar = []
        with tarfile.open(fileobj=io.BytesIO(arsiv)) as tf:
            for m in tf.getmembers():
                try:
                    install(tf.extractfile(m).read(), a.root / m.name, remote[m.name])
                    indi += 1
                    print(f"  indi  {m.name}")
                except ValueError as exc:
                    tekrar.append(m.name)
                    print(f"  tekrar ({tur}/{TUR}): {exc}", file=sys.stderr)
                except RuntimeError as exc:
                    hata.add(m.name)
                    print(f"  HATA  {exc}", file=sys.stderr)
        if not tekrar:
            break
    else:
        hata.update(tekrar)
        print(f"  HATA  {TUR} turda ozeti tutmayan: {', '.join(tekrar)}", file=sys.stderr)

    print(f"{indi} indi · {atlandi} zaten guncel · {len(hata)} hata")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
