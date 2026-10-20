"""Catálogo de agentes de KAI.

Fase 1: sólo el orquestador conversacional está activo (chat con Claude). El resto
se declara con su estado real ("planned") para que la interfaz no simule
capacidades inexistentes. Se implementan en la Fase 3.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class AgentInfo:
    id: str
    name: str
    description: str
    status: Literal["active", "planned"]
    phase: int


AGENTS: tuple[AgentInfo, ...] = (
    AgentInfo("orchestrator", "KAI Orchestrator",
              "Interpreta solicitudes y responde mediante Claude. En Fase 1 opera como chat conversacional.",
              "active", 1),
    AgentInfo("planner", "KAI Planner", "Divide objetivos complejos en tareas y dependencias.", "planned", 3),
    AgentInfo("memory", "KAI Memory", "Recupera contexto y administra la memoria persistente.", "planned", 3),
    AgentInfo("research", "KAI Research", "Investiga con fuentes y herramientas autorizadas.", "planned", 3),
    AgentInfo("code", "KAI Code", "Ayuda a programar, analizar y modificar proyectos.", "planned", 3),
    AgentInfo("files", "KAI Files", "Organiza y procesa documentos y carpetas autorizadas.", "planned", 4),
    AgentInfo("automation", "KAI Automation", "Gestiona automatizaciones autorizadas en Windows.", "planned", 4),
)


def list_agents() -> list[dict]:
    return [asdict(a) for a in AGENTS]
