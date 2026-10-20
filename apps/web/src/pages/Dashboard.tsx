import { KeyRound, MessageSquarePlus, Share2 } from "lucide-react";
import { KaiCore, STATE_LABEL } from "../components/KaiCore";
import { Badge, Card, Notice, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { AssistantState, ConversationSummary, SystemStatus, Task } from "../lib/api";
import { navigate } from "../lib/nav";

export function Dashboard({ state, detail, connected }: { state: AssistantState; detail: string | null; connected: boolean }) {
  const status = useApi<SystemStatus>("/system/status", [state]);
  const convs = useApi<ConversationSummary[]>("/conversations?limit=5", [state]);
  const tasks = useApi<Task[]>("/tasks?limit=50", [state]);
  const s = status.data;
  const openTasks = (tasks.data ?? []).filter((t) => !["completed", "cancelled", "failed"].includes(t.status));

  return (
    <div className="space-y-6">
      {!connected && <Notice tone="danger">No hay conexión en tiempo real con KAI Core. Verificá que el servidor esté iniciado (scripts\start.ps1).</Notice>}
      {s && !s.provider.configured && (
        <Notice tone="warn">
          El chat real no está disponible: falta la clave de API de Anthropic.{" "}
          <button className="underline" onClick={() => navigate("settings")}>Configurala acá</button>.
        </Notice>
      )}
      {s?.provider.demo_mode && <Notice tone="warn">Modo demostración activo: las respuestas NO provienen de una IA.</Notice>}

      <section className="panel flex flex-col items-center gap-6 p-10 md:flex-row md:gap-12">
        <KaiCore state={state} size={240} />
        <div className="flex-1 text-center md:text-left">
          <p className="text-sm uppercase tracking-[0.3em] text-muted">KAI AI</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">{STATE_LABEL[state]}</h1>
          <p className="mt-2 text-muted">{detail ?? "Listo para ayudarte. Escribime en el chat."}</p>
          <div className="mt-6 flex flex-wrap justify-center gap-2 md:justify-start">
            <button className="btn btn-primary" onClick={() => navigate("chat")}><MessageSquarePlus className="h-4 w-4" />Nueva conversación</button>
            <button className="btn" onClick={() => navigate("cowork")}><Share2 className="h-4 w-4" />Preparar tarea para Cowork</button>
            {s && !s.provider.configured && (
              <button className="btn" onClick={() => navigate("settings")}><KeyRound className="h-4 w-4" />Configurar clave</button>
            )}
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Proveedor" value={s ? (s.provider.demo_mode ? "Demostración" : s.provider.configured ? "Claude listo" : "Sin clave") : "—"}
          tone={s?.provider.configured && !s.provider.demo_mode ? "ok" : "warn"} hint={s?.provider.model} />
        <Stat label="Tokens hoy" value={s ? s.usage_today.total_tokens.toLocaleString("es-AR") : "—"}
          hint={s ? `${s.usage_today.requests} solicitudes` : undefined} />
        <Stat label="Presupuesto restante" value={s ? (s.budget.remaining === null ? "Sin límite" : s.budget.remaining.toLocaleString("es-AR")) : "—"}
          tone={s && s.budget.remaining !== null && s.budget.remaining < s.budget.daily_tokens * 0.1 ? "warn" : undefined} />
        <Stat label="Tareas abiertas" value={tasks.data ? String(openTasks.length) : "—"}
          hint={openTasks.some((t) => t.status === "awaiting_approval") ? "Hay tareas esperando autorización" : undefined} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Conversaciones recientes">
          {convs.data?.length ? (
            <ul className="divide-y divide-line">
              {convs.data.map((c) => (
                <li key={c.id}>
                  <button className="flex w-full items-center justify-between py-2.5 text-left text-sm hover:text-cyan" onClick={() => navigate("chat", c.id)}>
                    <span className="truncate">{c.title}</span>
                    <span className="ml-3 shrink-0 text-xs text-muted">{formatDate(c.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">Todavía no hay conversaciones.</p>}
        </Card>
        <Card title="Tareas por prioridad">
          {openTasks.length ? (
            <ul className="divide-y divide-line">
              {openTasks.slice(0, 6).map((t) => (
                <li key={t.id} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="truncate">{t.title}</span>
                  <Badge tone={t.status === "awaiting_approval" ? "warn" : t.status === "running" ? "info" : "muted"}>{t.status}</Badge>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No hay tareas pendientes.</p>}
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "ok" | "warn" }) {
  const color = tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-ink";
  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
      {hint && <div className="mt-1 truncate text-xs text-muted">{hint}</div>}
    </div>
  );
}
