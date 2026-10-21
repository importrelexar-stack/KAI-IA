"""Actualizaciones de la app de escritorio.

El workflow «App de escritorio» publica en la release fija `kai-ai-windows` el instalador y un
`latest.json` con la versión, el número de build y el SHA-256 del instalador. KAI compara ese build con
el suyo y, en la app instalada (sólo cuando la persona toca «Actualizar» y confirma), descarga el
instalador nuevo, verifica el SHA-256 y deja un ayudante que espera a que KAI se cierre, instala en
silencio (instalación por usuario: no pide administrador) y vuelve a abrir la app.

Seguridad: sólo se descarga desde las releases de este repositorio (HTTPS), y el archivo se descarta si
el SHA-256 no coincide con el publicado.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from app import __version__
from app.core.config import FROZEN
from app.core.errors import KaiError
from app.core.procenv import child_env

log = logging.getLogger(__name__)

REPO = "importrelexar-stack/KAI-IA"
RELEASE_PREFIX = f"https://github.com/{REPO}/releases/download/"
MANIFEST_URL = os.environ.get("KAI_UPDATE_MANIFEST", f"{RELEASE_PREFIX}kai-ai-windows/latest.json")
CACHE_SECONDS = 600
AUTO_INTERVAL = 3600       # cada cuánto busca versiones nuevas sola (con «actualizar automáticamente»)
AUTO_FIRST_DELAY = 90      # primera búsqueda, poco después de abrir KAI
IDLE_SECONDS = 180         # instala recién cuando nadie la usó en estos segundos (sin cortar una charla)
UPDATE_EXIT_CODE = 75  # la app de escritorio lo reconoce y muestra «Actualizando…» en lugar de un error


def current_build() -> tuple[int, str]:
    """Número de build y commit de esta instalación (0 = instalación desde el código)."""
    try:
        from app import _build  # generado por el CI antes de empaquetar

        return int(_build.BUILD), str(_build.SHA)
    except Exception:  # noqa: BLE001
        return 0, ""


def _vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def is_newer(latest: dict[str, Any], version: str, build: int) -> bool:
    lb = int(latest.get("build") or 0)
    if build and lb:
        return lb > build
    return _vtuple(str(latest.get("version", "0"))) > _vtuple(version)


class Updater:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # en las pruebas: transporte simulado, sin red
        self._cache: tuple[float, dict[str, Any]] | None = None
        self.state: dict[str, Any] = {"phase": "idle"}
        self._task: asyncio.Task[None] | None = None
        self.after_launch: Any = None  # lo fija main.run(): cierre ordenado de KAI Core
        self._install_now = False

    @property
    def can_install(self) -> bool:
        return FROZEN and sys.platform == "win32"

    async def manifest(self, force: bool = False) -> dict[str, Any]:
        if self._cache and not force and time.monotonic() - self._cache[0] < CACHE_SECONDS:
            return self._cache[1]
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15, transport=self._transport) as client:
                r = await client.get(MANIFEST_URL)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise KaiError(f"No se pudo consultar si hay actualizaciones: {type(e).__name__}.", code="update_check_failed",
                           status_code=502) from e
        if not isinstance(data, dict) or "version" not in data:
            raise KaiError("La información de actualización no es válida.", code="update_check_failed", status_code=502)
        self._cache = (time.monotonic(), data)
        return data

    async def check(self, force: bool = False) -> dict[str, Any]:
        build, sha = current_build()
        latest = await self.manifest(force)
        return {
            "current": {"version": __version__, "build": build, "sha": sha[:7]},
            "latest": {k: latest.get(k) for k in ("version", "build", "sha", "notes", "published_at", "size")},
            "available": is_newer(latest, __version__, build),
            "can_install": self.can_install,
            "state": self.state,
        }

    def start_install(self) -> None:
        if not self.can_install:
            raise KaiError("La actualización automática es para la app de escritorio. Si instalaste desde el código, "
                           "ejecutá actualizar.bat.", code="update_not_supported", status_code=409)
        if self._task and not self._task.done():
            if self.state.get("phase") == "ready":
                self._install_now = True  # ya bajada por la actualización automática: se instala ya
                return
            raise KaiError("Ya se está descargando la actualización.", code="busy", status_code=409)
        self._task = asyncio.create_task(self._install())

    async def _install(self, wait_idle: Any = None) -> None:
        try:
            latest = await self.manifest(force=True)
            url, expected = str(latest.get("url", "")), str(latest.get("sha256", "")).lower()
            if not url.startswith(RELEASE_PREFIX) or len(expected) != 64:
                raise KaiError("La actualización publicada no es válida.", code="update_invalid")
            target = await self.download(url, expected)
            if wait_idle is not None:
                self.state = {"phase": "ready", "version": latest.get("version")}
                await wait_idle()
            self.state = {"phase": "launching"}
            launch_installer(target)
            self.state = {"phase": "launched", "version": latest.get("version")}
            if self.after_launch:
                await asyncio.sleep(1.5)  # deja que la interfaz lea el estado antes de cerrar
                self.after_launch()
        except KaiError as e:
            self.state = {"phase": "error", "error": e.message}
        except Exception as e:  # noqa: BLE001
            log.exception("Actualización")
            self.state = {"phase": "error", "error": f"{type(e).__name__}: {e}"[:300]}

    # ---------- Actualización automática ----------

    async def auto_loop(self, enabled: Any, is_idle: Any) -> None:
        """Busca versiones nuevas cada hora; si hay, la descarga y la instala cuando KAI está sin uso.
        `enabled()` lee la preferencia; `is_idle()` dice si nadie está usando KAI en este momento."""
        if not self.can_install:
            return
        await asyncio.sleep(AUTO_FIRST_DELAY)
        while True:
            try:
                await self.auto_once(enabled, is_idle)
            except Exception:  # noqa: BLE001
                log.warning("Búsqueda automática de actualizaciones", exc_info=True)
            await asyncio.sleep(AUTO_INTERVAL)

    async def auto_once(self, enabled: Any, is_idle: Any) -> bool:
        if not self.can_install or not enabled():
            return False
        if self._task and not self._task.done():
            return False
        try:
            info = await self.check(force=True)
        except KaiError:
            return False  # sin Internet: se reintenta en la próxima vuelta
        if not info["available"]:
            return False
        log.info("Actualización automática: hay una versión nueva (%s)", info["latest"].get("version"))

        async def wait_idle() -> None:
            while not is_idle() and not self._install_now:
                await asyncio.sleep(5 if self._install_now else 30)

        self._task = asyncio.create_task(self._install(wait_idle))
        await self._task
        return True

    async def download(self, url: str, expected_sha256: str, dest_dir: Path | None = None) -> Path:
        dest_dir = dest_dir or Path(tempfile.gettempdir()) / "KAI-update"
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / "Instalar-KAI-AI.exe"
        digest = hashlib.sha256()
        done = 0
        self.state = {"phase": "downloading", "progress": 0.0}
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30, read=120),
                                     transport=self._transport) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                with open(target.with_suffix(".part"), "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 20):
                        f.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if total:
                            self.state = {"phase": "downloading", "progress": round(done / total, 3)}
        part = target.with_suffix(".part")
        if digest.hexdigest() != expected_sha256:
            part.unlink(missing_ok=True)
            raise KaiError("La descarga no coincide con la versión publicada (SHA-256). Se descartó.",
                           code="update_checksum")
        part.replace(target)
        return target


def helper_script(installer: Path, app_pid: str, app_exe: Path) -> str:
    """Script del ayudante (cmd): espera, cierra la ventana de KAI, instala en silencio y la vuelve a abrir.
    `ping` hace de pausa porque `timeout` no funciona sin consola."""
    lines = ["@echo off", "rem KAI AI: instala la actualización descargada y vuelve a abrir KAI.",
             "ping -n 4 127.0.0.1 >nul"]
    if app_pid.isdigit():
        lines.append(f"taskkill /PID {app_pid} /F >nul 2>&1")
        lines.append("ping -n 3 127.0.0.1 >nul")
    lines.append(f'"{installer}" /S')
    if app_exe.exists():
        lines.append(f'start "" "{app_exe}"')
    return "\r\n".join(lines) + "\r\n"


def launch_installer(path: Path) -> None:
    """Deja corriendo el ayudante en un proceso independiente (sigue aunque KAI se cierre)."""
    here = Path(sys.executable).parent  # <instalación>\kai-core\kai-core.exe (antes: junto a la app)
    app_exe = next((d / "kai-desktop.exe" for d in (here.parent, here) if (d / "kai-desktop.exe").exists()),
                   here.parent / "kai-desktop.exe")
    script = path.with_name("instalar-actualizacion.cmd")
    script.write_text(helper_script(path, os.environ.get("KAI_PARENT_PID", ""), app_exe), encoding="mbcs"
                      if sys.platform == "win32" else "utf-8")
    cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(script)]
    base = 0
    if sys.platform == "win32":
        base = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        try:  # fuera del grupo de procesos de la app, para que no se cierre junto con ella
            subprocess.Popen(cmd, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB,  # type: ignore[attr-defined]
                             close_fds=True, env=child_env())  # noqa: S603 - ruta propia, verificada
            return
        except OSError:
            pass
    subprocess.Popen(cmd, creationflags=base, close_fds=True, env=child_env())  # noqa: S603
