"""Catálogo de agentes de KAI con su estado real.

El orquestador es Claude con tool use: decide qué herramientas usar. Los agentes
Memory, Planner y Research son conjuntos de herramientas con límites de pasos,
tiempo y tokens por solicitud. Files y Automation operan dentro de los permisos del usuario; Code llega más adelante.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.agents.tools import TOOLS
from app.schemas.settings import Preferences

Status = Literal["active", "disabled", "planned"]


@dataclass(frozen=True)
class AgentInfo:
    id: str
    name: str
    description: str
    status: Status
    phase: int
    tools: tuple[str, ...] = ()


def _tools(agent: str) -> tuple[str, ...]:
    return tuple(t.name for t in TOOLS if t.agent == agent)


def list_agents(prefs: Preferences) -> list[dict]:
    on: Status = "active" if prefs.agents_enabled else "disabled"
    agents = (
        AgentInfo("orchestrator", "KAI Orchestrator",
                  "Interpreta cada pedido y decide qué herramientas usar (Claude con tool use), con límite de "
                  f"{prefs.max_tool_iterations} pasos por respuesta.", "active", 1),
        AgentInfo("memory", "KAI Memory",
                  "Recupera contexto de la memoria y los proyectos; propone qué recordar (con tu aprobación).",
                  on if prefs.memory_enabled else "disabled", 3, _tools("memory")),
        AgentInfo("planner", "KAI Planner", "Divide objetivos complejos en tareas con dependencias y prioridades.",
                  on, 3, _tools("planner")),
        AgentInfo("research", "KAI Research",
                  "Busca información actual en la web y lee páginas (búsqueda y lectura web de Anthropic, con costo "
                  "por uso). Se activa en Integraciones.",
                  "active" if prefs.agents_enabled and (prefs.web_search_enabled or prefs.web_fetch_enabled)
                  else "disabled", 3,
                  tuple(n for n, on_ in (("web_search", prefs.web_search_enabled), ("web_fetch", prefs.web_fetch_enabled))
                        if on_) or ("web_search", "web_fetch")),
        AgentInfo("integrations", "KAI Integraciones",
                  "Usa las herramientas de los servidores MCP que conectaste (calendario, correo, notas, etc.). "
                  "Lo que no es de solo lectura pide tu autorización.", on, 6),
        AgentInfo("files", "KAI Files",
                  "Lista, busca, lee (texto, PDF, Word) y organiza archivos sólo dentro de las carpetas que autorizaste. "
                  "Lo que modifica algo pide confirmación según los permisos.", on, 4, _tools("files")),
        AgentInfo("automation", "KAI Automation",
                  "Abre aplicaciones de Windows por nombre (las del menú Inicio), archivos y scripts registrados según tus permisos.",
                  on, 4, _tools("automation")),
        AgentInfo("code", "KAI Code", "Ayuda a programar, analizar y modificar proyectos.", "planned", 6),
    )
    return [asdict(a) for a in agents]
