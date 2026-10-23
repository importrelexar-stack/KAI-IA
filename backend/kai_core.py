"""Punto de entrada de KAI Core empaquetado (sidecar de la app de escritorio)."""

from __future__ import annotations

import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Ejecutable sin consola (doble clic en Windows): stdout/stderr no existen. Los registros
    # de KAI igual se escriben en data/logs/kai.log.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
    from app.main import run

    run()
