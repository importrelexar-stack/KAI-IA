# -*- mode: python ; coding: utf-8 -*-
# Empaqueta KAI Core (backend + interfaz compilada) en un ejecutable para la app de escritorio.
#   pyinstaller kai-core.spec --noconfirm
# Requiere apps/web/dist compilada. Si están instalados los motores de voz, también se incluyen.
import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve()
WEB = ROOT.parent / "apps" / "web" / "dist"
if not (WEB / "index.html").is_file():
    raise SystemExit("Falta apps/web/dist: compilá la interfaz antes de empaquetar.")

datas = [(str(WEB), "web")]
binaries = []
hiddenimports = collect_submodules("uvicorn") + collect_submodules("app") + [
    "keyring.backends.Windows", "keyring.backends.SecretService", "keyring.backends.macOS", "keyring.backends.fail",
]
# mcp.cli es la herramienta de consola de MCP (requiere typer) y KAI no la usa.
hiddenimports += collect_submodules("mcp", filter=lambda name: name != "mcp.cli" and not name.startswith("mcp.cli."))
for pkg in ("faster_whisper", "ctranslate2", "piper", "onnxruntime", "av", "tokenizers", "huggingface_hub"):
    if importlib.util.find_spec(pkg) is not None:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h

name = os.environ.get("KAI_SIDECAR_NAME", "kai-core")
a = Analysis(["kai_core.py"], pathex=[str(ROOT)], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "pytest", "matplotlib"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=name, debug=False, strip=False, upx=False,
          console=sys.platform != "win32" or os.environ.get("KAI_SIDECAR_CONSOLE") == "1",
          runtime_tmpdir=None)
