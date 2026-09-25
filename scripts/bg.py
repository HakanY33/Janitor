"""Uzun kosuyu terminalden bagimsiz baslatir; cikti log dosyasina gider.

    python -m scripts.bg scripts.sweep --limit 20
    python -m scripts.bg scripts.terminate

Terminal kapansa da surer, konsola hic yazmaz ve kostugu surece makineyi uyanik
tutar. Ucu de ayni ariza icindir:

* **Terminal kapanmasi** — cocuk `DETACHED_PROCESS` ile kendi oturumunda kosar.
* **Konsol donmasi** — Windows konsolunda QuickEdit ile bir yere tiklanirsa
  bir sonraki yazma bloklanir ve surec sessizce durur. Cikti dosyaya gidince
  konsol denklemden cikar.
* **Uyku** — `SetThreadExecutionState` bosta uyumayi engeller. Kapak kapatma ve
  elle uyutma (`Sleep Reason: Application API`) bundan etkilenmez; onlar hala
  kosuyu durdurur.
"""
from __future__ import annotations

import ctypes
import os
import runpy
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MARKER = "JANITOR_BG"
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def keep_awake() -> None:
    """Surec yasadigi surece bosta uyumayi engelle (cikista kendiliginden duser)."""
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    module, args = sys.argv[1], sys.argv[2:]

    if os.environ.get(MARKER):  # cocuk: asil isi burada yap
        keep_awake()
        sys.argv = [module, *args]
        runpy.run_module(module, run_name="__main__")
        return 0

    log = Path("logs") / f"{module.rsplit('.', 1)[-1]}-{datetime.now():%Y%m%d-%H%M%S}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as f:
        p = subprocess.Popen(
            [sys.executable, "-u", "-m", "scripts.bg", module, *args],
            stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, MARKER: "1"},
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            start_new_session=(sys.platform != "win32"),
        )
    print(f"pid {p.pid}  ->  {log}")
    print(f"izle:  Get-Content -Wait -Tail 20 {log}")
    print(f"durdur: Stop-Process -Id {p.pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
