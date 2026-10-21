"""Órdenes que KAI resuelve al instante, sin consultar al modelo.

Hoy: «abrí Excel», «abrime la calculadora», «iniciá Chrome». Si el pedido es más que abrir una
aplicación (por ejemplo «abrí Excel y armá una planilla»), si nombra un archivo o si la aplicación no
se identifica con seguridad, se sigue el camino normal (Claude decide y usa las herramientas).
Se respetan los mismos permisos que la herramienta abrir_aplicacion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents import automation_tools as at
from app.automation import apps_catalog
from app.automation.permissions import get_permissions
from app.core.errors import KaiError

_OPEN = re.compile(
    r"^\s*(?:(?:hey|ey|che|hola)\s+kai\s*[,:]?\s*)?(?:por\s+favor\s*,?\s*)?"
    r"(?:abr[ií]me|abr[ií]|abrir|abre|ejecut[aá]|inici[aá]|lanz[aá]|arranc[aá])\s+"
    r"(?:(?:la|el|una|un|mi)\s+)?(?:(?:aplicaci[oó]n|app|programa)\s+(?:de\s+)?)?"
    r"(?P<name>[^,.;:!?¿¡\n]{1,60}?)\s*(?:,?\s*por\s+favor)?\s*[.!]*\s*$",
    re.I,
)
# Si aparece algo de esto, no es «abrir una aplicación» a secas: decide el modelo.
_NOT_APP = re.compile(r"(\barchivo\b|\bcarpeta\b|\bdocumento\b|\bp[aá]gina\b|\bweb\b|[\\/]|\.\w{2,4}$|"
                      r"\by\b|\be\b|\bcon\b|\bpara\b|\bdespu[eé]s\b|\bluego\b|https?)", re.I)


@dataclass
class QuickResult:
    tool: str
    summary: str
    ok: bool
    reply: str


def app_name_in(message: str) -> str | None:
    m = _OPEN.match(message)
    if not m:
        return None
    name = m.group("name").strip()
    if not name or _NOT_APP.search(name) or len(name.split()) > 4:
        return None
    return name


def try_open_app(db: Session, message: str) -> QuickResult | None:
    """Abre la aplicación pedida sin pasar por el modelo, o None para seguir el camino normal."""
    name = app_name_in(message)
    if name is None:
        return None
    perms = get_permissions(db)
    if perms.level("abrir_aplicacion") != "allow":
        return None  # «preguntar» o «bloquear»: lo maneja el flujo normal (tarea a autorizar / aviso)
    registered = next((a for a in perms.apps if a.name.lower() == name.lower()), None)
    if registered is None:
        if not perms.start_menu_apps:
            return None
        try:
            apps_catalog.catalog.find(name, min_score=60)
        except KaiError:
            return None  # no está o es ambiguo: que el modelo pregunte o busque otra forma
    try:
        ok, result = at.execute("abrir_aplicacion", {"nombre": name}, perms, [])
    except KaiError as e:
        return QuickResult("abrir_aplicacion", f"abrir_aplicacion: {e.message}", False, e.message)
    opened = result.removeprefix("Abrí ").removeprefix("Aplicación iniciada: ").rstrip(".")
    return QuickResult("abrir_aplicacion", result, ok, f"Listo, abrí {opened}.")
