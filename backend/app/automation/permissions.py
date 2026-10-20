"""Permisos de automatización: carpetas autorizadas, aplicaciones y scripts registrados,
y nivel de cada herramienta (permitir / preguntar / bloquear).

Principios:
- Nada es accesible por defecto: el usuario autoriza cada carpeta.
- Las carpetas del sistema, la carpeta de datos de KAI y los archivos sensibles se
  bloquean siempre, aunque estén dentro de una carpeta autorizada.
- No existe ejecución arbitraria de comandos: sólo aplicaciones y scripts registrados.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.errors import KaiError
from app.models.entities import SettingEntry

Level = Literal["allow", "ask", "deny"]

DEFAULT_LEVELS: dict[str, Level] = {
    "listar_carpeta": "allow",
    "buscar_archivos": "allow",
    "leer_archivo": "allow",
    "crear_carpeta": "ask",
    "escribir_archivo": "ask",
    "mover_archivo": "ask",
    "organizar_carpeta": "ask",
    "enviar_a_papelera": "ask",
    "abrir": "ask",
    "ejecutar_script": "ask",
}
# Herramientas que nunca se ejecutan sin confirmación, aunque el usuario elija "allow".
ALWAYS_ASK = {"enviar_a_papelera", "ejecutar_script"}

_KEY = "automation_permissions"


class FolderPermission(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    mode: Literal["read", "read_write"] = "read"


class AppEntry(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    command: str = Field(min_length=1, max_length=500, description="Ruta al .exe o nombre en el PATH")


class ScriptEntry(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    path: str = Field(min_length=1, max_length=500)
    timeout_seconds: int = Field(default=60, ge=5, le=600)

    @field_validator("path")
    @classmethod
    def _script_ext(cls, v: str) -> str:
        if Path(v).suffix.lower() not in (".ps1", ".bat", ".cmd", ".py"):
            raise ValueError("Sólo se pueden registrar scripts .ps1, .bat, .cmd o .py")
        return v


class Permissions(BaseModel):
    folders: list[FolderPermission] = Field(default_factory=list, max_length=30)
    apps: list[AppEntry] = Field(default_factory=list, max_length=50)
    scripts: list[ScriptEntry] = Field(default_factory=list, max_length=50)
    levels: dict[str, Level] = Field(default_factory=dict)

    def level(self, tool: str) -> Level:
        lvl = self.levels.get(tool, DEFAULT_LEVELS.get(tool, "ask"))
        if tool in ALWAYS_ASK and lvl == "allow":
            return "ask"
        return lvl


def _system_dirs() -> list[Path]:
    dirs: list[str | None] = []
    if sys.platform == "win32":
        dirs += [os.environ.get("SystemRoot", r"C:\Windows"), os.environ.get("ProgramFiles"),
                 os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramData")]
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs += [str(Path(appdata).parent)]  # AppData completo
    else:
        dirs += ["/etc", "/bin", "/sbin", "/usr", "/boot", "/proc", "/sys", "/dev", "/var/lib"]
    return [Path(d).resolve() for d in dirs if d]


SENSITIVE_NAMES = {".env", ".ssh", ".gnupg", ".aws", "id_rsa", "id_ed25519", ".git-credentials", ".npmrc",
                   ".pypirc", "credentials", "kai.db", "access_token"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".kdbx", ".ppk"}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PathGuard:
    """Resuelve rutas y verifica que estén dentro de una carpeta autorizada."""

    def __init__(self, perms: Permissions, protected: list[Path]) -> None:
        self.roots = [(Path(f.path).expanduser().resolve(), f.mode) for f in perms.folders]
        self.protected = [p.resolve() for p in protected] + _system_dirs()

    def resolve(self, raw: str, *, write: bool = False) -> Path:
        if not self.roots:
            raise KaiError("No hay carpetas autorizadas. Agregalas en Archivos → Permisos.",
                           code="no_folders", status_code=403)
        raw = (raw or "").strip().strip('"')
        if not raw:
            raise KaiError("Falta la ruta.", code="invalid_path", status_code=422)
        p = Path(raw).expanduser()
        if not p.is_absolute():
            # Relativa a la primera carpeta autorizada
            p = self.roots[0][0] / p
        p = p.resolve()
        root = next(((r, m) for r, m in self.roots if _inside(p, r)), None)
        if root is None:
            raise KaiError(f"La ruta «{raw}» está fuera de las carpetas autorizadas.", code="path_not_allowed",
                           status_code=403)
        if write and root[1] != "read_write":
            raise KaiError(f"La carpeta «{root[0]}» está autorizada sólo para lectura.", code="read_only",
                           status_code=403)
        for prot in self.protected:
            if _inside(p, prot):
                raise KaiError("Esa ubicación está protegida y KAI no puede acceder.", code="path_protected",
                               status_code=403)
        rel_parts = p.relative_to(root[0]).parts
        if any(part.lower() in SENSITIVE_NAMES for part in rel_parts) or p.suffix.lower() in SENSITIVE_SUFFIXES:
            raise KaiError("Por seguridad, KAI no accede a archivos de credenciales o claves.",
                           code="path_sensitive", status_code=403)
        return p

    def root_of(self, p: Path) -> Path:
        return next(r for r, _ in self.roots if _inside(p, r))


def validate_folder(raw: str, protected: list[Path]) -> str:
    p = Path(raw.strip().strip('"')).expanduser()
    if not p.is_absolute():
        raise KaiError(f"«{raw}» no es una ruta absoluta.", code="invalid_folder", status_code=422)
    p = p.resolve()
    if not p.is_dir():
        raise KaiError(f"La carpeta «{raw}» no existe.", code="invalid_folder", status_code=422)
    if p.parent == p:
        raise KaiError("No se puede autorizar una unidad completa: elegí una carpeta.", code="invalid_folder",
                       status_code=422)
    if p == Path.home().resolve():
        raise KaiError("No se puede autorizar la carpeta de usuario completa: elegí una subcarpeta "
                       "(Documentos, Escritorio, un proyecto…).", code="invalid_folder", status_code=422)
    for prot in [*(x.resolve() for x in protected), *_system_dirs()]:
        if _inside(p, prot) or _inside(prot, p):
            raise KaiError("Esa carpeta contiene o es una ubicación protegida.", code="invalid_folder",
                           status_code=422)
    return str(p)


def resolve_app(entry: AppEntry) -> str:
    cmd = entry.command.strip().strip('"')
    if Path(cmd).is_absolute():
        if not Path(cmd).is_file():
            raise KaiError(f"No existe el programa «{cmd}».", code="app_not_found", status_code=422)
        return cmd
    found = shutil.which(cmd)
    if not found:
        raise KaiError(f"No se encontró «{cmd}» en este equipo.", code="app_not_found", status_code=422)
    return found


def get_permissions(db: Session) -> Permissions:
    row = db.get(SettingEntry, _KEY)
    if row is None or not isinstance(row.value, dict):
        return Permissions()
    try:
        return Permissions.model_validate(row.value)
    except ValueError:
        return Permissions()


def save_permissions(db: Session, perms: Permissions, protected: list[Path]) -> Permissions:
    seen: set[str] = set()
    folders = []
    for f in perms.folders:
        path = validate_folder(f.path, protected)
        if path.lower() not in seen:
            seen.add(path.lower())
            folders.append(FolderPermission(path=path, mode=f.mode))
    for s in perms.scripts:
        sp = Path(s.path).expanduser()
        if not sp.is_absolute() or not sp.is_file():
            raise KaiError(f"El script «{s.path}» no existe.", code="script_not_found", status_code=422)
    for name in perms.levels:
        if name not in DEFAULT_LEVELS:
            raise KaiError(f"Herramienta desconocida: {name}", code="invalid_tool", status_code=422)
    names = [a.name.lower() for a in perms.apps] + [s.name.lower() for s in perms.scripts]
    if len(names) != len(set(names)):
        raise KaiError("Hay nombres repetidos entre aplicaciones o scripts.", code="duplicate_name", status_code=422)
    clean = Permissions(folders=folders, apps=perms.apps, scripts=perms.scripts, levels=perms.levels)
    row = db.get(SettingEntry, _KEY)
    if row is None:
        db.add(SettingEntry(key=_KEY, value=clean.model_dump()))
    else:
        row.value = clean.model_dump()
    db.commit()
    return clean
