import type { TaskStatus } from "./api";

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pendiente",
  awaiting_approval: "Esperando autorización",
  running: "En ejecución",
  completed: "Completada",
  failed: "Fallida",
  cancelled: "Cancelada",
};

export const TASK_TONE: Record<TaskStatus, "muted" | "warn" | "info" | "ok" | "danger"> = {
  pending: "muted", awaiting_approval: "warn", running: "info", completed: "ok", failed: "danger", cancelled: "muted",
};
