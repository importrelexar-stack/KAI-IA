"""Aplicaciones instaladas en Windows que KAI puede abrir por nombre («abrí Excel»).

Fuente: las entradas del menú Inicio (`Get-StartApps`, incluye las apps de Microsoft Store), y si eso no
está disponible, los accesos directos (.lnk) de las carpetas del menú Inicio.

Seguridad: sólo se abre una entrada que figura en ese catálogo, tal como la registró Windows, sin
argumentos. KAI no puede pasar parámetros ni ejecutar comandos: es lo mismo que hacer clic en el menú Inicio.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import KaiError

log = logging.getLogger(__name__)

CACHE_SECONDS = 300
_SKIP = re.compile(r"\b(uninstall|desinstalar|desinstalación|readme|léame|help|ayuda|documentation|"
                   r"documentación|release notes|website|sitio web)\b", re.I)
_SAFE_APPID = re.compile(r"^[^\"\r\n\x00<>|&^%]{1,300}$")
# Nombres que la gente dice y cómo suelen figurar en el menú Inicio (Windows en español o en inglés)
ALIASES = {
    "calculadora": ["calculator"], "calculator": ["calculadora"],
    "bloc de notas": ["notepad"], "notepad": ["bloc de notas"],
    "explorador": ["explorador de archivos", "file explorer"], "explorador de archivos": ["file explorer"],
    "configuracion": ["settings"], "ajustes": ["configuracion", "settings"],
    "word": ["microsoft word"], "excel": ["microsoft excel"], "powerpoint": ["microsoft powerpoint"],
    "outlook": ["microsoft outlook", "outlook (new)"], "edge": ["microsoft edge"], "chrome": ["google chrome"],
    "paint": ["paint"], "recortes": ["recortes", "snipping tool"], "fotos": ["fotos", "photos"],
    "consola": ["terminal", "windows terminal"], "terminal": ["windows terminal"],
}


@dataclass(frozen=True)
class InstalledApp:
    name: str
    app_id: str = ""       # AppUserModelID / ruta de Get-StartApps → shell:AppsFolder\<id>
    shortcut: str = ""     # o un acceso directo .lnk del menú Inicio


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9+#]+", " ", t).strip()


def _from_start_apps() -> list[InstalledApp]:
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],  # noqa: S603, S607
                          capture_output=True, timeout=20, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    data = json.loads(proc.stdout)
    rows = data if isinstance(data, list) else [data]
    return [InstalledApp(name=str(r["Name"]), app_id=str(r["AppID"])) for r in rows
            if r.get("Name") and r.get("AppID") and _SAFE_APPID.match(str(r["AppID"]))]


def _from_shortcuts() -> list[InstalledApp]:
    roots = [Path(os.environ.get(v, "")) / "Microsoft/Windows/Start Menu/Programs" for v in ("PROGRAMDATA", "APPDATA")]
    apps = []
    for root in roots:
        if root.is_dir():
            apps += [InstalledApp(name=p.stem, shortcut=str(p)) for p in root.rglob("*.lnk")]
    return apps


class AppCatalog:
    def __init__(self) -> None:
        self._cache: tuple[float, list[InstalledApp]] | None = None
        self._refreshing = threading.Lock()

    def apps(self) -> list[InstalledApp]:
        """Lista en caché; si venció, se devuelve la anterior y se actualiza en segundo plano (sin demoras)."""
        if sys.platform != "win32":
            return []
        if self._cache:
            if time.monotonic() - self._cache[0] >= CACHE_SECONDS and self._refreshing.acquire(blocking=False):
                threading.Thread(target=self._refresh_bg, daemon=True, name="kai-apps").start()
            return self._cache[1]
        return self.refresh()

    def _refresh_bg(self) -> None:
        try:
            self.refresh()
        finally:
            self._refreshing.release()

    def refresh(self) -> list[InstalledApp]:
        try:
            found = _from_start_apps()
        except Exception:  # noqa: BLE001
            log.warning("Get-StartApps no está disponible; se usan los accesos del menú Inicio", exc_info=True)
            found = []
        found = found or _from_shortcuts()
        unique = {normalize(a.name): a for a in found if not _SKIP.search(a.name)}
        result = sorted(unique.values(), key=lambda a: a.name.lower())
        self._cache = (time.monotonic(), result)
        return result

    def find(self, query: str, min_score: int = 1) -> InstalledApp:
        """La aplicación que mejor coincide con lo que pidió la persona (o un error con opciones).
        `min_score` sube la exigencia (60 = el nombre contiene todas las palabras pedidas)."""
        apps = self.apps()
        if not apps:
            raise KaiError("No pude leer las aplicaciones instaladas (sólo funciona en Windows).",
                           code="apps_unavailable", status_code=409)
        q = normalize(query)
        if not q:
            raise KaiError("Decime qué aplicación querés abrir.", code="invalid", status_code=422)
        queries = [q] + [normalize(a) for a in ALIASES.get(q, [])]
        scored: list[tuple[int, InstalledApp]] = []
        for app in apps:
            n = normalize(app.name)
            best = 0
            for i, qq in enumerate(queries):
                penalty = 5 if i else 0  # el nombre tal cual pesa más que un alias
                words = qq.split()
                if n == qq:
                    s = 100
                elif n.startswith(qq + " ") or n.endswith(" " + qq):
                    s = 80
                elif all(w in n.split() for w in words):
                    s = 60
                elif qq in n:
                    s = 40
                else:
                    s = 0
                best = max(best, s - penalty if s else 0)
            if best:
                scored.append((best, app))
        if not scored:
            raise KaiError(f"No encontré una aplicación instalada que se llame «{query}».", code="app_not_found",
                           status_code=404)
        scored.sort(key=lambda x: (-x[0], len(x[1].name)))
        top_score = scored[0][0]
        if top_score < min_score:
            raise KaiError(f"No encontré una aplicación instalada que se llame «{query}».", code="app_not_found",
                           status_code=404)
        tied = [a for s, a in scored if s == top_score]
        if top_score < 95 and len(tied) > 1:
            names = ", ".join(f"«{a.name}»" for a in tied[:6])
            raise KaiError(f"Hay varias aplicaciones que coinciden con «{query}»: {names}. ¿Cuál abro?",
                           code="ambiguous", status_code=409)
        return scored[0][1]


def launch(app: InstalledApp) -> str:
    """Abre la entrada del menú Inicio, sin argumentos (igual que hacer clic en ella)."""
    if sys.platform != "win32":
        raise KaiError("Abrir aplicaciones instaladas sólo funciona en Windows.", code="unsupported", status_code=409)
    if app.app_id:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app.app_id}"], close_fds=True)  # noqa: S603, S607
    else:
        os.startfile(app.shortcut)  # type: ignore[attr-defined]  # noqa: S606
    return f"Abrí «{app.name}»."


catalog = AppCatalog()
