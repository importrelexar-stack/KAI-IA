"""Operaciones de archivos dentro de carpetas autorizadas.

Todas reciben rutas ya validadas por `PathGuard`. Ninguna sobrescribe ni borra de forma
definitiva: lo que se elimina va a la Papelera de reciclaje.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.errors import KaiError

MAX_LIST = 300
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_FILES = 20_000
MAX_READ_CHARS = 60_000
MAX_WRITE_BYTES = 2 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".log", ".ini", ".cfg", ".yaml",
                 ".yml", ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".sql", ".ps1", ".bat", ".sh", ".toml", ".rtf"}
WRITABLE_SUFFIXES = {".txt", ".md", ".csv", ".json", ".html", ".xml", ".yaml", ".yml", ".log"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "$recycle.bin", "system volume information"}


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def list_dir(path: Path, pattern: str | None = None) -> list[dict[str, Any]]:
    if not path.is_dir():
        raise KaiError(f"«{path}» no es una carpeta.", code="not_a_folder", status_code=404)
    out: list[dict[str, Any]] = []
    entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    for e in entries:
        if pattern and not fnmatch.fnmatch(e.name.lower(), pattern.lower()):
            continue
        try:
            is_dir = e.is_dir()
            out.append({"nombre": e.name, "tipo": "carpeta" if is_dir else "archivo",
                        "tamano": None if is_dir else _fmt_size(e.stat().st_size), "modificado": _mtime(e)})
        except OSError:
            continue
        if len(out) >= MAX_LIST:
            break
    return out


def search(root: Path, name_pattern: str | None, text: str | None, max_depth: int = 8) -> list[dict[str, Any]]:
    if not name_pattern and not text:
        raise KaiError("Indicá un nombre o un texto a buscar.", code="empty_search", status_code=422)
    pattern = (name_pattern or "*").lower()
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"
    needle = text.lower() if text else None
    results: list[dict[str, Any]] = []
    scanned = 0
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        if len(d.parts) - base_depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [n for n in dirnames if n.lower() not in SKIP_DIRS and not n.startswith(".")]
        for fname in filenames:
            scanned += 1
            if scanned > MAX_SEARCH_FILES:
                return results
            if not fnmatch.fnmatch(fname.lower(), pattern):
                continue
            fp = d / fname
            if needle:
                if fp.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    if fp.stat().st_size > 2 * 1024 * 1024:
                        continue
                    if needle not in fp.read_text(encoding="utf-8", errors="ignore").lower():
                        continue
                except OSError:
                    continue
            results.append({"ruta": str(fp), "tamano": _fmt_size(fp.stat().st_size), "modificado": _mtime(fp)})
            if len(results) >= MAX_SEARCH_RESULTS:
                return results
    return results


def read_text(path: Path) -> tuple[str, bool]:
    """Devuelve (texto, truncado). Soporta texto plano, PDF y DOCX."""
    if not path.is_file():
        raise KaiError(f"No existe el archivo «{path.name}».", code="not_found", status_code=404)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(path))
            parts = []
            for i, page in enumerate(reader.pages[:50]):
                parts.append(f"[Página {i + 1}]\n{page.extract_text() or ''}")
                if sum(len(x) for x in parts) > MAX_READ_CHARS:
                    break
            text = "\n\n".join(parts)
        except Exception as e:  # noqa: BLE001
            raise KaiError(f"No se pudo leer el PDF: {e}", code="unreadable", status_code=422) from e
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
            xml = re.sub(r"</w:p>", "\n", xml)
            text = re.sub(r"<[^>]+>", "", xml)
        except (KeyError, zipfile.BadZipFile) as e:
            raise KaiError("No se pudo leer el documento de Word.", code="unreadable", status_code=422) from e
    elif suffix in TEXT_SUFFIXES or not suffix:
        if path.stat().st_size > 5 * 1024 * 1024:
            raise KaiError("El archivo es demasiado grande para leerlo (máx. 5 MB).", code="too_large",
                           status_code=413)
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            raise KaiError("Parece un archivo binario: no se puede leer como texto.", code="binary", status_code=422)
        text = raw.decode("utf-8", errors="replace")
    else:
        raise KaiError(f"No sé leer archivos {suffix}. Formatos: texto, PDF y Word (.docx).", code="unsupported",
                       status_code=422)
    truncated = len(text) > MAX_READ_CHARS
    return text[:MAX_READ_CHARS], truncated


def make_dir(path: Path) -> str:
    if path.exists():
        raise KaiError(f"Ya existe «{path.name}».", code="exists", status_code=409)
    path.mkdir(parents=True)
    return f"Carpeta creada: {path}"


def write_file(path: Path, content: str, overwrite: bool) -> str:
    if path.suffix.lower() not in WRITABLE_SUFFIXES:
        raise KaiError(f"Sólo se pueden crear archivos de texto ({', '.join(sorted(WRITABLE_SUFFIXES))}).",
                       code="unsupported", status_code=422)
    data = content.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        raise KaiError("El contenido supera 2 MB.", code="too_large", status_code=413)
    if path.exists() and not overwrite:
        raise KaiError(f"Ya existe «{path.name}». Para reemplazarlo hace falta pedirlo explícitamente.",
                       code="exists", status_code=409)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.stem}.kai-backup-{datetime.now():%Y%m%d%H%M%S}{path.suffix}")
        shutil.copy2(path, backup)
        path.write_bytes(data)
        return f"Archivo reemplazado: {path} (copia de seguridad: {backup.name})"
    path.write_bytes(data)
    return f"Archivo creado: {path}"


def move(src: Path, dst: Path) -> str:
    if not src.exists():
        raise KaiError(f"No existe «{src.name}».", code="not_found", status_code=404)
    if dst.exists() and dst.is_dir():
        dst = dst / src.name
    if dst.exists():
        raise KaiError(f"Ya existe «{dst}»: KAI no sobrescribe archivos.", code="exists", status_code=409)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Movido: {src} → {dst}"


CATEGORIES = {
    "Documentos": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"},
    "Planillas": {".xls", ".xlsx", ".csv", ".ods"},
    "Presentaciones": {".ppt", ".pptx", ".odp"},
    "Imagenes": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "Audio": {".mp3", ".wav", ".ogg", ".m4a", ".flac"},
    "Comprimidos": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Instaladores": {".exe", ".msi"},
}


def plan_organize(folder: Path, criterion: str) -> list[dict[str, str]]:
    """Plan de movimientos (sin ejecutar) para ordenar los archivos sueltos de una carpeta."""
    if not folder.is_dir():
        raise KaiError(f"«{folder}» no es una carpeta.", code="not_a_folder", status_code=404)
    moves: list[dict[str, str]] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        if criterion == "fecha":
            sub = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m")
        else:
            ext = f.suffix.lower()
            sub = next((cat for cat, exts in CATEGORIES.items() if ext in exts), "Otros")
        target = folder / sub / f.name
        if not target.exists():
            moves.append({"origen": str(f), "destino": str(target)})
        if len(moves) >= 500:
            break
    return moves


def to_trash(path: Path) -> str:
    if not path.exists():
        raise KaiError(f"No existe «{path.name}».", code="not_found", status_code=404)
    from send2trash import send2trash

    send2trash(str(path))
    return f"Enviado a la papelera: {path}"


def open_path(target: str) -> str:
    """Abre un archivo/carpeta (ya validado) o un programa registrado con la aplicación del sistema."""
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603, S607
    return f"Abierto: {target}"


def launch_app(executable: str) -> str:
    subprocess.Popen([executable], close_fds=True)  # noqa: S603 - sólo programas registrados por el usuario
    return f"Aplicación iniciada: {Path(executable).name}"


def run_script(path: Path, timeout: int) -> tuple[bool, str]:
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    elif suffix in (".bat", ".cmd"):
        cmd = ["cmd", "/c", str(path)]
    elif suffix == ".py":
        cmd = [sys.executable, str(path)]
    else:
        raise KaiError("Tipo de script no soportado.", code="unsupported", status_code=422)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=str(path.parent),  # noqa: S603
                              text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, f"El script superó el tiempo máximo ({timeout} s) y se detuvo."
    output = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    if len(output) > 8000:
        output = output[:8000] + "\n…(salida truncada)"
    return proc.returncode == 0, f"Código de salida {proc.returncode}.\n{output}".strip()
