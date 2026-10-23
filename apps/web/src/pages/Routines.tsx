import { useEffect, useState } from "react";
import { CalendarClock, Loader2, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Badge, Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { routinesApi, type Routine, type RoutineSchedule } from "../lib/api";

const DAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const EXAMPLES = [
  { name: "Resumen de la mañana", prompt: "Resumime las tareas pendientes, lo que espera mi autorización y los próximos pasos de mis proyectos.", schedule: { type: "weekly", days: [0, 1, 2, 3, 4], time: "08:30" } },
  { name: "Cierre del día", prompt: "Hacé un resumen de lo que avancé hoy en mis proyectos y proponé las prioridades de mañana.", schedule: { type: "weekly", days: [0, 1, 2, 3, 4], time: "18:00" } },
] as const;

/** Fase 6: pedidos que KAI ejecuta solo según un horario (hora local de esta PC). */
export function RoutinesPage({ refreshKey }: { refreshKey: number }) {
  const list = useApi<Routine[]>("/routines");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void list.reload(); }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await list.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Rutinas" subtitle="Pedidos que KAI hace solo, en el horario que elijas (con la PC encendida y KAI abierto)."
        actions={<button className="btn" onClick={() => void list.reload()}><RefreshCw className="h-4 w-4" />Actualizar</button>} />
      {(error || list.error) && <Notice tone="danger">{error ?? list.error}</Notice>}
      <Notice tone="info">
        Cada rutina usa las mismas reglas que el chat: las acciones que modifican algo quedan esperando tu autorización
        (nunca se aprueban solas) y cuenta para el presupuesto diario de tokens. Si la PC estuvo apagada, una rutina vencida
        corre una sola vez al volver.
      </Notice>

      {list.data?.length === 0 && <p className="text-sm text-muted">Todavía no hay rutinas.</p>}
      <div className="space-y-3">
        {list.data?.map((r) => (
          <Card key={r.id}>
            <div className="flex flex-wrap items-start gap-3 text-sm">
              <CalendarClock className="mt-0.5 h-5 w-5 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{r.name}</span>
                  <Badge tone={r.enabled ? "info" : "muted"}>{r.schedule_text}</Badge>
                  {r.last_status === "running" && <Badge tone="warn">Ejecutando…</Badge>}
                  {r.last_status === "ok" && <Badge tone="ok">Última: OK</Badge>}
                  {r.last_status === "error" && <Badge tone="danger">Última: error</Badge>}
                </div>
                <p className="mt-1 whitespace-pre-wrap text-muted">{r.prompt}</p>
                <p className="mt-1 text-xs text-muted">
                  {r.enabled && r.next_run_at ? `Próxima: ${formatDate(r.next_run_at)}` : "Pausada"}
                  {r.last_run_at && ` · última: ${formatDate(r.last_run_at)}`} · {r.run_count} ejecuciones
                  {r.conversation_id && <> · <a className="underline" href={`#/chat/${r.conversation_id}`}>ver resultados</a></>}
                </p>
                {r.last_status === "error" && r.last_error && <p className="mt-1 text-xs text-danger">{r.last_error}</p>}
              </div>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={r.enabled} disabled={busy !== null}
                    onChange={(e) => void run(`en-${r.id}`, () => routinesApi.update(r.id, { enabled: e.target.checked }))} />
                  Activa
                </label>
                <button className="btn" disabled={busy !== null || r.last_status === "running"} onClick={() => void run(`run-${r.id}`, () => routinesApi.run(r.id))}>
                  {busy === `run-${r.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Ejecutar ahora
                </button>
                <button className="btn btn-danger" aria-label={`Eliminar ${r.name}`} disabled={busy !== null}
                  onClick={() => { if (confirm(`¿Eliminar la rutina «${r.name}»? Sus resultados quedan en el historial.`)) void run(`rm-${r.id}`, () => routinesApi.remove(r.id)); }}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <NewRoutine onCreated={() => void list.reload()} />
    </div>
  );
}

function NewRoutine({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [kind, setKind] = useState<RoutineSchedule["type"]>("weekly");
  const [time, setTime] = useState("08:30");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [minutes, setMinutes] = useState(120);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function schedule(): RoutineSchedule {
    if (kind === "daily") return { type: "daily", time };
    if (kind === "weekly") return { type: "weekly", days, time };
    return { type: "interval", minutes };
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await routinesApi.create({ name, prompt, schedule: schedule() });
      setName("");
      setPrompt("");
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Nueva rutina">
      <form className="grid gap-3 text-sm md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <div className="flex flex-wrap gap-2 md:col-span-2">
          <span className="text-muted">Ejemplos:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex.name} type="button" className="rounded-full border border-line px-2 py-0.5 text-xs hover:bg-white/5"
              onClick={() => { setName(ex.name); setPrompt(ex.prompt); setKind("weekly"); setDays([...ex.schedule.days]); setTime(ex.schedule.time); }}>
              {ex.name}
            </button>
          ))}
        </div>
        <label className="space-y-1">Nombre<input className="field" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} /></label>
        <label className="space-y-1">Frecuencia
          <select className="field" value={kind} onChange={(e) => setKind(e.target.value as RoutineSchedule["type"])}>
            <option value="daily">Todos los días</option>
            <option value="weekly">Algunos días de la semana</option>
            <option value="interval">Cada cierto tiempo</option>
          </select>
        </label>
        <label className="space-y-1 md:col-span-2">Qué tiene que hacer KAI
          <textarea className="field" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} required minLength={3} maxLength={4000}
            placeholder="Ej.: Revisá mis tareas y avisame qué vence esta semana." />
        </label>
        {kind === "interval" ? (
          <label className="space-y-1">Cada (minutos, mínimo 15)
            <input className="field" type="number" min={15} max={10080} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
          </label>
        ) : (
          <label className="space-y-1">Hora (de esta PC)<input className="field" type="time" value={time} onChange={(e) => setTime(e.target.value)} required /></label>
        )}
        {kind === "weekly" && (
          <fieldset className="space-y-1">
            <legend>Días</legend>
            <div className="flex flex-wrap gap-1">
              {DAYS.map((d, i) => (
                <label key={d} className={`cursor-pointer rounded-md border px-2 py-1 text-xs ${days.includes(i) ? "border-electric bg-electric/20" : "border-line"}`}>
                  <input type="checkbox" className="sr-only" checked={days.includes(i)}
                    onChange={(e) => setDays(e.target.checked ? [...days, i].sort() : days.filter((x) => x !== i))} />
                  {d}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="md:col-span-2">
          <button className="btn btn-primary" disabled={busy || (kind === "weekly" && days.length === 0)}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}Crear rutina
          </button>
        </div>
        {error && <div className="md:col-span-2"><Notice tone="danger">{error}</Notice></div>}
      </form>
    </Card>
  );
}
