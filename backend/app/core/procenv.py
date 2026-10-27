"""Entorno para los programas que KAI abre.

KAI Core empaquetado (PyInstaller, un solo archivo) se descomprime en una carpeta temporal y deja en su
entorno variables `_PYI_*` que apuntan a ella. Si un programa abierto por KAI las hereda y a su vez es
una app de PyInstaller (por ejemplo, la propia KAI reabierta después de actualizarse), intenta usar esa
carpeta, que se borra cuando KAI se cierra: «Failed to load Python DLL … python312.dll».
`PYINSTALLER_RESET_ENVIRONMENT=1` es la forma documentada de que el programa hijo arranque de cero.
"""

from __future__ import annotations

import os

_PYI_PREFIXES = ("_PYI_", "_MEIPASS")


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(_PYI_PREFIXES)}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if extra:
        env.update(extra)
    return env
