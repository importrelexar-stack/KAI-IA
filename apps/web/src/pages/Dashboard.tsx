import type { ComponentType } from "react";
import {
  ArrowRight, CalendarClock, Coins, Cpu, FolderOpen, Gauge, KeyRound, ListChecks, MessageSquarePlus, Mic, Plug, ShieldCheck,
} from "lucide-react";
import { KaiCore, STATE_LABEL } from "../components/KaiCore";
import { Badge, Card, Notice, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { AssistantState, ConversationSummary, Routine, SettingsOut, SystemStatus, Task } from "../lib/api";
import { navigate } from "../lib/nav";
import { TASK_LABEL, TASK_TONE } from "../lib/taskStatus";

type Icon = ComponentType<{ className?: string }>;

function greeting(): string {
  const h = new Date().getHours();
  return h < 6 ? "Buenas noches" : h < 13 ? "Buen día" : h < 20 ? "Buenas tardes" : "Buenas noches";
}

const QUICK: { route: string; icon: Icon; title: string; text: string }[] = [
  { route: "chat", icon: MessageSquarePlus, title: "Nueva conversación", text: "Escribile a KAI lo que necesites" },
  { route: "voice", icon: Mic, title: "Hablar con KAI", text: "Por voz, con respuesta hablada" },
  { route: "tasks", icon: ListChecks, title: "Automatizaciones", text: "Tareas y acciones a autorizar" },
  { route: "routines", icon: CalendarClock, title: "Rutinas", text: "Pedidos que KAI hace solo" },
  { route: "files", icon: FolderOpen, title: "Archivos y apps", text: "Carpetas y aplicaciones permitidas" },
  { route: "integrations", icon: Plug, title: "Integraciones", text: "Conectá otras herramientas" },
];

export function Dashboard({ state, detail, connected }: { state: AssistantState; detail: string | null; connected: boolean }) {
  const status = useApi<SystemStatus>("/system/status", [state]);
  const convs = useApi<ConversationSummary[]>("/conversations?limit=5", [state]);
  const tasks = useApi<Task[]>("/tasks?limit=50", [state]);
  const routines = useApi<Routine[]>("/routines", [state]);
  const settings = useApi<SettingsOut>("/settings");
  const s = status.data;
  const name = settings.data?.preferences.user_name?.trim();
  const openTasks = (tasks.data ?? []).filter((t) => !["completed", "cancelled", "failed"].includes(t.status));
  const awaiting = openTasks.filter((t) => t.status === "awaiting_approval");
  const nextRoutines = (routines.data ?? []).filter((r) => r.enabled && r.next_run_at)
    .sort((a, b) => (a.next_run_at ?? "").localeCompare(b.next_run_at ?? "")).slice(0, 4);
  const budgetUsed = s && s.budget.daily_tokens ? Math.min(1, s.usage_today.total_tokens / s.budget.daily_tokens) : null;

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

      {/* Bienvenida */}
      <section className="panel relative overflow-hidden p-8 md:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-electric/20 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -bottom-28 left-1/3 h-60 w-60 rounded-full bg-violet/15 blur-3xl" aria-hidden />
        <div className="relative flex flex-col items-center gap-8 md:flex-row md:gap-12">
          <KaiCore state={state} size={210} />
          <div className="flex-1 text-center md:text-left">
            <span className="chip"><span className="dot" aria-hidden />{STATE_LABEL[state]}</span>
            <h1 className="text-gradient mt-3 text-4xl font-semibold tracking-tight md:text-5xl">
              {greeting()}{name ? `, ${name}` : ""}
            </h1>
            <p className="mt-3 max-w-xl text-muted">{detail ?? "¿En qué te ayudo hoy? Escribime, hablame o pedime que abra una aplicación."}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2 md:justify-start">
              <button className="btn btn-primary" onClick={() => navigate("chat")}><MessageSquarePlus className="h-4 w-4" />Nueva conversación</button>
              <button className="btn" onClick={() => navigate("voice")}><Mic className="h-4 w-4" />Hablar con KAI</button>
              {s && !s.provider.configured && (
                <button className="btn" onClick={() => navigate("settings")}><KeyRound className="h-4 w-4" />Configurar clave</button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Lo que espera una decisión tuya */}
      {awaiting.length > 0 && (
        <button className="panel panel-hover flex w-full items-center gap-4 p-4 text-left" onClick={() => navigate("tasks")}>
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-warn/15 text-warn"><ShieldCheck className="h-5 w-5" aria-hidden /></span>
          <span className="flex-1">
            <span className="block font-medium">
              {awaiting.length === 1 ? "Hay 1 acción esperando tu autorización" : `Hay ${awaiting.length} acciones esperando tu autorización`}
            </span>
            <span className="block truncate text-sm text-muted">{awaiting[0].title}</span>
          </span>
          <ArrowRight className="h-4 w-4 text-muted" aria-hidden />
        </button>
      )}

      {/* Indicadores */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Cpu} label="Asistente" value={s ? (s.provider.demo_mode ? "Demostración" : s.provider.configured ? "Claude listo" : "Sin clave") : "—"}
          tone={s?.provider.configured && !s.provider.demo_mode ? "ok" : "warn"} hint={s?.provider.model} />
        <Stat icon={Coins} label="Tokens hoy" value={s ? s.usage_today.total_tokens.toLocaleString("es-AR") : "—"}
          hint={s ? `${s.usage_today.requests} solicitudes` : undefined} />
        <Stat icon={Gauge} label="Presupuesto restante" value={s ? (s.budget.remaining === null ? "Sin límite" : s.budget.remaining.toLocaleString("es-AR")) : "—"}
          tone={s && s.budget.remaining !== null && s.budget.remaining < s.budget.daily_tokens * 0.1 ? "warn" : undefined}
          meter={budgetUsed === null ? undefined : 1 - budgetUsed} />
        <Stat icon={ListChecks} label="Tareas abiertas" value={tasks.data ? String(openTasks.length) : "—"}
          hint={awaiting.length ? `${awaiting.length} esperando autorización` : "Nada pendiente de tu parte"} tone={awaiting.length ? "warn" : undefined} />
      </div>

      {/* Accesos rápidos */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {QUICK.map(({ route, icon: Ico, title, text }) => (
          <button key={route} className="panel panel-hover group flex items-center gap-4 p-4 text-left" onClick={() => navigate(route)}>
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-electric/30 bg-gradient-to-br from-electric/25 to-violet/15 text-cyan shadow-[0_0_18px_-6px_var(--color-cyan)]">
              <Ico className="h-5 w-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{title}</span>
              <span className="block truncate text-xs text-muted">{text}</span>
            </span>
            <ArrowRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5 group-hover:text-cyan" aria-hidden />
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Conversaciones recientes">
          {convs.data?.length ? (
            <ul className="space-y-1">
              {convs.data.map((c) => (
                <li key={c.id}>
                  <button className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm transition hover:bg-white/5 hover:text-cyan" onClick={() => navigate("chat", c.id)}>
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
            <ul className="space-y-1">
              {openTasks.slice(0, 6).map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm">
                  <span className="truncate">{t.title}</span>
                  <Badge tone={TASK_TONE[t.status]}>{TASK_LABEL[t.status]}</Badge>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No hay tareas pendientes.</p>}
        </Card>
        <Card title="Próximas rutinas">
          {nextRoutines.length ? (
            <ul className="space-y-1">
              {nextRoutines.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm">
                  <span className="truncate">{r.name}</span>
                  <span className="shrink-0 text-xs text-muted">{formatDate(r.next_run_at as string)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">
              No hay rutinas programadas.{" "}
              <button className="text-cyan underline" onClick={() => navigate("routines")}>Crear una</button>
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

function Stat({ icon: Ico, label, value, hint, tone, meter }: {
  icon: Icon; label: string; value: string; hint?: string; tone?: "ok" | "warn"; meter?: number;
}) {
  const color = tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-ink";
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-[0.16em] text-muted">{label}</span>
        <Ico className="h-4 w-4 text-cyan/80" />
      </div>
      <div className={`mt-2 font-[family-name:var(--font-display)] text-2xl font-semibold ${color}`}>{value}</div>
      {meter !== undefined && (
        <div className="meter mt-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(meter * 100)} aria-label={label}>
          <span style={{ width: `${Math.round(meter * 100)}%` }} />
        </div>
      )}
      {hint && <div className="mt-1.5 truncate text-xs text-muted">{hint}</div>}
    </div>
  );
}
