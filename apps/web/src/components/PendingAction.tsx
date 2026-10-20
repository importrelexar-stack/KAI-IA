import { useEffect, useState } from "react";
import { Check, ShieldAlert, X } from "lucide-react";
import { get, post, type Task } from "../lib/api";

/** Tarjeta para autorizar o rechazar, desde el chat, una acción que KAI dejó pendiente. */
export function PendingAction({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Task>(`/tasks/${taskId}`).then(setTask).catch(() => setTask(null));
  }, [taskId]);

  if (!task) return null;

  async function decide(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      setTask(await post<Task>(`/tasks/${taskId}/approval`, { approve }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const waiting = task.status === "awaiting_approval";
  const title = waiting ? "KAI necesita tu autorización"
    : task.status === "completed" ? "Acción ejecutada"
    : task.status === "cancelled" ? "Acción rechazada"
    : task.status === "failed" ? "La acción falló" : "Acción";
  return (
    <div className={`mt-2 rounded-xl border p-3 text-sm ${waiting ? "border-warn/50 bg-warn/5" : task.status === "completed" ? "border-ok/40" : "border-line"}`}>
      <div className="mb-1 flex items-center gap-2 font-medium">
        <ShieldAlert className={`h-4 w-4 ${waiting ? "text-warn" : "text-muted"}`} aria-hidden />
        {title}
      </div>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-sans text-xs text-muted">{task.description}</pre>
      {task.result && <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-ok">{task.result}</pre>}
      {task.error && <p className="mt-2 text-xs text-danger">{task.error}</p>}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      {waiting && (
        <div className="mt-2 flex gap-2">
          <button className="btn btn-primary" disabled={busy} onClick={() => void decide(true)}><Check className="h-4 w-4" />Autorizar</button>
          <button className="btn btn-danger" disabled={busy} onClick={() => void decide(false)}><X className="h-4 w-4" />Rechazar</button>
        </div>
      )}
    </div>
  );
}
