"""Catálogo de agentes de KAI con su estado real.

El orquestador es Claude con tool use: decide qué herramientas usar. Los agentes
Memory, Planner y Research son conjuntos de herramientas con límites de pasos,
tiempo y tokens por solicitud. Code, Files y Automation llegan en fases posteriores.
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
                  "Busca información actual en la web (búsqueda web de Anthropic, con costo por búsqueda). "
                  "Se activa en Configuración.",
                  "active" if prefs.agents_enabled and prefs.web_search_enabled else "disabled", 3, ("web_search",)),
        AgentInfo("code", "KAI Code", "Ayuda a programar, analizar y modificar proyectos.", "planned", 4),
        AgentInfo("files", "KAI Files", "Organiza y procesa documentos y carpetas autorizadas.", "planned", 4),
        AgentInfo("automation", "KAI Automation", "Gestiona automatizaciones autorizadas en Windows.", "planned", 4),
    )
    return [asdict(a) for a in agents]
