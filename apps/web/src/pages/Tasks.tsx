import { useEffect, useState } from "react";
import { Badge, Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { post, type Task, type TaskStatus } from "../lib/api";
import { TASK_LABEL as LABEL, TASK_TONE as TONE } from "../lib/taskStatus";
const NEXT: Record<TaskStatus, TaskStatus[]> = {
  pending: ["awaiting_approval", "running", "cancelled"],
  awaiting_approval: ["cancelled"],
  running: ["completed", "failed", "cancelled"],
  completed: [],
  failed: ["pending"],
  cancelled: [],
};
const PRIORITY = { 1: "Alta", 2: "Media", 3: "Baja" } as const;

export function TasksPage({ refreshKey }: { refreshKey: number }) {
  const tasks = useApi<Task[]>("/tasks?limit=200");
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", description: "", priority: 2, requires_approval: false });

  useEffect(() => { void tasks.reload(); }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); await tasks.reload(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <div>
      <PageHeader title="Automatizaciones y tareas" subtitle="Motor de tareas por estados con autorizaciones e historial." />
      <div className="mb-4">
        <Notice>
          Acá quedan las tareas y las acciones que KAI propone. Las que modifican algo (archivos, scripts, integraciones) esperan tu autorización antes de ejecutarse; abrir aplicaciones y leer archivos autorizados no la necesitan, salvo que lo cambies en Archivos.</Notice>
      </div>
      {error && <div className="mb-4"><Notice tone="danger">{error}</Notice></div>}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <Card title="Tareas">
          {tasks.data?.length ? (
            <ul className="divide-y divide-line">
              {tasks.data.map((t) => (
                <li key={t.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{t.title}</span>
                    <Badge tone={TONE[t.status]}>{LABEL[t.status]}</Badge>
                    <Badge>{PRIORITY[t.priority as 1 | 2 | 3]}</Badge>
                    {t.requires_approval && <Badge tone="warn">Requiere autorización</Badge>}
                    {t.created_by === "kai" && <Badge tone="info">Creada por KAI</Badge>}
                    <span className="ml-auto text-xs text-muted">{formatDate(t.created_at)}</span>
                  </div>
                  {t.description && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{t.description}</p>}
                  {t.depends_on?.length > 0 && (
                    <p className="mt-1 text-xs text-muted">Depende de: {t.depends_on.map((d) => tasks.data?.find((x) => x.id === d)?.title ?? d).join(", ")}</p>
                  )}
                  {t.result && <p className="mt-1 text-sm text-ok">Resultado: {t.result}</p>}
                  {t.error && <p className="mt-1 text-sm text-danger">Error: {t.error}</p>}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {t.status === "awaiting_approval" && (
                      <>
                        <button className="btn btn-primary" onClick={() => act(() => post(`/tasks/${t.id}/approval`, { approve: true }))}>Autorizar</button>
                        <button className="btn btn-danger" onClick={() => act(() => post(`/tasks/${t.id}/approval`, { approve: false }))}>Rechazar</button>
                      </>
                    )}
                    {t.status === "awaiting_approval" && t.approvals.at(-1)?.decision === "approved" && (
                      <button className="btn" onClick={() => act(() => post(`/tasks/${t.id}/transition`, { status: "running" }))}>Iniciar</button>
                    )}
                    {NEXT[t.status].map((s) => (
                      <button key={s} className="btn" onClick={() => act(async () => {
                        const extra = s === "completed" ? { result: prompt("Resultado (opcional)") ?? undefined }
                          : s === "failed" ? { error: prompt("¿Qué falló?") ?? undefined } : {};
                        if (s === "cancelled" && !confirm("¿Cancelar la tarea?")) return;
                        await post(`/tasks/${t.id}/transition`, { status: s, ...extra });
                      })}>→ {LABEL[s]}</button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No hay tareas registradas.</p>}
        </Card>

        <Card title="Nueva tarea">
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              await post("/tasks", form);
              setForm({ title: "", description: "", priority: 2, requires_approval: false });
            });
          }}>
            <input className="field" placeholder="Título" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label="Título" />
            <textarea className="field min-h-24" placeholder="Descripción" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} aria-label="Descripción" />
            <select className="field" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} aria-label="Prioridad">
              <option value={1}>Prioridad alta</option><option value={2}>Prioridad media</option><option value={3}>Prioridad baja</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.requires_approval} onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })} />
              Requiere autorización antes de ejecutarse
            </label>
            <button className="btn btn-primary w-full justify-center" disabled={!form.title.trim()}>Registrar tarea</button>
          </form>
        </Card>
      </div>
    </div>
  );
}
