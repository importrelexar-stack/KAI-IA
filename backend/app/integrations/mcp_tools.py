"""Uso de herramientas MCP desde el chat, con el mismo esquema de autorización de la Fase 4."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agents.tools import ToolContext, ToolOutcome
from app.automation import tasks as task_engine
from app.core.errors import KaiError
from app.integrations.mcp_manager import McpManager, format_result
from app.models.entities import Task


def _preview(server: str, tool: str, args: dict[str, Any]) -> str:
    shown = json.dumps(args, ensure_ascii=False, indent=1)
    if len(shown) > 1500:
        shown = shown[:1500] + "…"
    return f"Integración «{server}»: {tool}\n{shown}"


async def handle(manager: McpManager, c: ToolContext, claude_name: str, raw: Any) -> ToolOutcome:
    found = manager.tool_map().get(claude_name)
    if found is None:
        return ToolOutcome("Esa integración ya no está disponible.", f"{claude_name}: no disponible", ok=False)
    conn, tool = found
    args = raw if isinstance(raw, dict) else {}
    server = conn.config.name
    level = manager.level(conn.config, tool)
    if level == "deny":  # por si cambió entre el listado y la llamada
        return ToolOutcome(f"La herramienta {tool.name} está bloqueada.", f"{server}/{tool.name}: bloqueada", ok=False)
    if level == "ask":
        preview = _preview(server, tool.name, args)
        task = task_engine.create_task(c.db, title=f"{server}: {tool.name}"[:200], description=preview, priority=1,
                                       requires_approval=True, created_by="kai")
        task.action = {"kind": "mcp", "tool": f"{server}/{tool.name}", "server_id": conn.config.id,
                       "mcp_tool": tool.name, "args": args, "conversation_id": c.conversation_id}
        c.db.commit()
        task = task_engine.transition(c.db, task.id, task_engine.TaskStatus.AWAITING_APPROVAL,
                                      note="acción de integración solicitada por KAI")
        c.created_tasks.append(task.id)
        c.publish({"type": "task", "id": task.id, "status": task.status, "title": task.title})
        return ToolOutcome(
            f"Pendiente de autorización del usuario (tarea {task.id}): {preview}\nNo se ejecutó todavía.",
            f"Pidió autorización: {server} → {tool.name}", True, task.id)
    try:
        ok, text = format_result(server, await conn.call(tool.name, args))
    except KaiError as e:
        return ToolOutcome(e.message, f"{server}/{tool.name}: {e.message}", ok=False)
    except Exception as e:  # noqa: BLE001 - un servidor externo no debe cortar la respuesta
        return ToolOutcome(f"La integración falló: {type(e).__name__}: {e}"[:500], f"{server}/{tool.name}: falló",
                           ok=False)
    return ToolOutcome(text, f"{server}: {tool.name}" + ("" if ok else " (error)"), ok)


def run_approved(db: Session, task: Task, manager: McpManager) -> Task:
    """Ejecuta una acción MCP autorizada (desde el endpoint de aprobación, que corre en un hilo)."""
    from app.agents.automation_tools import _notify_conversation

    action = task.action or {}
    task = task_engine.transition(db, task.id, task_engine.TaskStatus.RUNNING, note="autorizada por el usuario")
    try:
        ok, result = manager.call_from_thread(action["server_id"], action["mcp_tool"], action.get("args") or {})
    except KaiError as e:
        ok, result = False, e.message
    except Exception as e:  # noqa: BLE001
        ok, result = False, f"Error de la integración: {type(e).__name__}: {e}"[:500]
    task.tools_used = [*(task.tools_used or []), action.get("tool", "")]
    db.commit()
    target = task_engine.TaskStatus.COMPLETED if ok else task_engine.TaskStatus.FAILED
    task = task_engine.transition(db, task.id, target, result=result if ok else None, error=None if ok else result)
    _notify_conversation(db, action.get("conversation_id"), ok, task.title, result)
    return task
