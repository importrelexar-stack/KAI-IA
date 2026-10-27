import { useEffect, useState } from "react";
import { Check, FolderKanban, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { Badge, Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api, del, get, patch, post, type MemoryItem, type MemoryKind, type Project, type ProjectDetail } from "../lib/api";

const KIND_LABEL: Record<MemoryKind, string> = { preference: "Preferencia", fact: "Dato", project: "Proyecto" };
const KIND_TONE: Record<MemoryKind, "info" | "muted" | "ok"> = { preference: "info", fact: "muted", project: "ok" };
const LOG_LABEL = { decision: "Decisión", progress: "Avance", note: "Nota" } as const;
const STATUS_LABEL = { active: "Activo", paused: "En pausa", done: "Terminado" } as const;
const TASK_LABEL: Record<string, string> = {
  pending: "Pendiente", awaiting_approval: "Esperando autorización", running: "En ejecución",
  completed: "Completada", failed: "Fallida", cancelled: "Cancelada",
};

export function MemoryPage({ refreshKey }: { refreshKey: number }) {
  const [tab, setTab] = useState<"memories" | "projects">("memories");
  return (
    <div className="space-y-4">
      <PageHeader title="Memoria" subtitle="Lo que KAI recuerda de vos y de tus proyectos. Todo queda en tu equipo y lo podés editar o borrar." />
      <div className="flex gap-2" role="tablist">
        <button role="tab" aria-selected={tab === "memories"} className={`btn ${tab === "memories" ? "btn-primary" : ""}`} onClick={() => setTab("memories")}>Memorias</button>
        <button role="tab" aria-selected={tab === "projects"} className={`btn ${tab === "projects" ? "btn-primary" : ""}`} onClick={() => setTab("projects")}><FolderKanban className="h-4 w-4" />Proyectos</button>
      </div>
      {tab === "memories" ? <Memories refreshKey={refreshKey} /> : <Projects refreshKey={refreshKey} />}
    </div>
  );
}

function Memories({ refreshKey }: { refreshKey: number }) {
  const [kind, setKind] = useState<MemoryKind | "">("");
  const [q, setQ] = useState("");
  const list = useApi<MemoryItem[]>(`/memory${kind ? `?kind=${kind}` : ""}`, [refreshKey]);
  const projects = useApi<Project[]>("/projects", [refreshKey]);
  const [results, setResults] = useState<MemoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ kind: MemoryKind; content: string; project_id: string }>({ kind: "fact", content: "", project_id: "" });

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); await list.reload(); setResults(null); } catch (e) { setError((e as Error).message); }
  }

  async function search() {
    if (!q.trim()) { setResults(null); return; }
    try { setResults(await get<MemoryItem[]>(`/memory/search?q=${encodeURIComponent(q)}`)); } catch (e) { setError((e as Error).message); }
  }

  const all = list.data ?? [];
  const proposed = all.filter((m) => m.status === "proposed");
  const active = results ?? all.filter((m) => m.status === "active");
  const projectName = (id: string | null) => projects.data?.find((p) => p.id === id)?.name;

  return (
    <div className="space-y-4">
      {error && <Notice tone="danger">{error}</Notice>}
      {proposed.length > 0 && (
        <Card title={`Propuestas de KAI (${proposed.length}) — no se usan hasta que las apruebes`}>
          <ul className="divide-y divide-line">
            {proposed.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                <Badge tone={KIND_TONE[m.kind]}>{KIND_LABEL[m.kind]}</Badge>
                <span className="min-w-0 flex-1">{m.content}</span>
                <button className="btn btn-primary" onClick={() => act(() => post(`/memory/${m.id}/approve`))}><Check className="h-4 w-4" />Aprobar</button>
                <button className="btn btn-danger" onClick={() => act(() => del(`/memory/${m.id}`))}><X className="h-4 w-4" />Descartar</button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <Card title="Memorias activas">
          <div className="mb-3 flex flex-wrap gap-2">
            <form className="relative min-w-56 flex-1" onSubmit={(e) => { e.preventDefault(); void search(); }}>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
              <input className="field pl-9" placeholder="Buscar en la memoria…" value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) setResults(null); }} aria-label="Buscar en la memoria" />
            </form>
            <select className="field w-44" value={kind} onChange={(e) => { setKind(e.target.value as MemoryKind | ""); setResults(null); }} aria-label="Filtrar por tipo">
              <option value="">Todos los tipos</option>
              <option value="preference">Preferencias</option>
              <option value="fact">Datos</option>
              <option value="project">Proyectos</option>
            </select>
          </div>
          {active.length ? (
            <ul className="divide-y divide-line">
              {active.map((m) => (
                <li key={m.id} className="py-2.5 text-sm">
                  <div className="flex items-start gap-2">
                    <Badge tone={KIND_TONE[m.kind]}>{KIND_LABEL[m.kind]}</Badge>
                    <span className="min-w-0 flex-1">{m.content}</span>
                    <button className="p-1 text-muted hover:text-ink" aria-label="Editar" onClick={() => {
                      const content = prompt("Editar memoria", m.content)?.trim();
                      if (content && content !== m.content) void act(() => patch(`/memory/${m.id}`, { content }));
                    }}><Pencil className="h-4 w-4" /></button>
                    <button className="p-1 text-muted hover:text-danger" aria-label="Eliminar" onClick={() => confirm("¿Eliminar esta memoria?") && act(() => del(`/memory/${m.id}`))}><Trash2 className="h-4 w-4" /></button>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 pl-1 text-xs text-muted">
                    <span>{m.source === "kai" ? "Propuesta por KAI" : "Agregada por vos"}</span>
                    {projectName(m.project_id) && <span>Proyecto: {projectName(m.project_id)}</span>}
                    <span>Usada {m.use_count} {m.use_count === 1 ? "vez" : "veces"}</span>
                    <span>{formatDate(m.updated_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">{results ? "Sin resultados." : "Todavía no hay memorias. Agregá una o pedile a KAI que recuerde algo."}</p>}
          {all.length > 0 && (
            <button className="btn btn-danger mt-4" onClick={() => confirm("¿Eliminar TODA la memoria? No se puede deshacer.") && act(() => del("/memory?confirm=true"))}>
              <Trash2 className="h-4 w-4" />Borrar toda la memoria
            </button>
          )}
        </Card>

        <Card title="Agregar memoria">
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              await post("/memory", { kind: form.kind, content: form.content, project_id: form.project_id || null });
              setForm({ ...form, content: "" });
            });
          }}>
            <select className="field" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as MemoryKind })} aria-label="Tipo">
              <option value="preference">Preferencia (siempre la tiene en cuenta)</option>
              <option value="fact">Dato (lo usa cuando viene al caso)</option>
              <option value="project">Nota de proyecto</option>
            </select>
            <textarea className="field min-h-24" required maxLength={2000} placeholder="Ej.: Prefiero los informes en una sola página." value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} aria-label="Contenido" />
            <select className="field" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })} aria-label="Proyecto">
              <option value="">Sin proyecto</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button className="btn btn-primary w-full justify-center" disabled={!form.content.trim()}><Plus className="h-4 w-4" />Guardar</button>
            <p className="text-xs text-muted">No guardes contraseñas ni claves: KAI las rechaza.</p>
          </form>
        </Card>
      </div>
    </div>
  );
}

function Projects({ refreshKey }: { refreshKey: number }) {
  const list = useApi<Project[]>("/projects", [refreshKey]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", goal: "" });
  const [logForm, setLogForm] = useState<{ kind: "decision" | "progress" | "note"; text: string }>({ kind: "progress", text: "" });

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    api<ProjectDetail>(`/projects/${selected}`).then(setDetail).catch((e) => setError((e as Error).message));
  }, [selected, refreshKey]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await list.reload();
      if (selected) setDetail(await api<ProjectDetail>(`/projects/${selected}`));
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <div className="space-y-4">
      {error && <Notice tone="danger">{error}</Notice>}
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="space-y-4">
          <Card title="Proyectos">
            {list.data?.length ? (
              <ul className="space-y-1">
                {list.data.map((p) => (
                  <li key={p.id}>
                    <button className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${p.id === selected ? "bg-electric/15" : "hover:bg-white/5"}`} onClick={() => setSelected(p.id)}>
                      <span className="truncate">{p.name}</span>
                      <Badge tone={p.status === "active" ? "ok" : "muted"}>{STATUS_LABEL[p.status]}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">Sin proyectos. Creá uno o pedile a KAI que lo haga.</p>}
          </Card>
          <Card title="Nuevo proyecto">
            <form className="space-y-2" onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                const p = await post<Project>("/projects", { name: form.name, goal: form.goal });
                setForm({ name: "", goal: "" });
                setSelected(p.id);
              });
            }}>
              <input className="field" required maxLength={200} placeholder="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Nombre del proyecto" />
              <textarea className="field min-h-16" placeholder="Objetivo" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} aria-label="Objetivo" />
              <button className="btn btn-primary w-full justify-center" disabled={!form.name.trim()}><Plus className="h-4 w-4" />Crear</button>
            </form>
          </Card>
        </div>

        {detail ? (
          <Card title={detail.name}>
            <div className="space-y-4 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <select className="field w-40" value={detail.status} onChange={(e) => act(() => patch(`/projects/${detail.id}`, { status: e.target.value }))} aria-label="Estado del proyecto">
                  <option value="active">Activo</option><option value="paused">En pausa</option><option value="done">Terminado</option>
                </select>
                <button className="btn btn-danger ml-auto" onClick={() => confirm(`¿Eliminar el proyecto «${detail.name}»? Sus tareas y memorias se conservan.`) && act(async () => { await del(`/projects/${detail.id}`); setSelected(null); })}><Trash2 className="h-4 w-4" />Eliminar</button>
              </div>
              <EditableText label="Objetivo" value={detail.goal} onSave={(goal) => act(() => patch(`/projects/${detail.id}`, { goal }))} />
              <EditableText label="Próximos pasos" value={detail.next_steps} onSave={(next_steps) => act(() => patch(`/projects/${detail.id}`, { next_steps }))} />

              <div>
                <div className="mb-1 text-xs uppercase tracking-wider text-muted">Tareas</div>
                {detail.tasks.length ? (
                  <ul className="space-y-1">{detail.tasks.map((t) => <li key={t.id} className="flex justify-between"><span>{t.title}</span><Badge tone={t.status === "completed" ? "ok" : t.status === "awaiting_approval" ? "warn" : "muted"}>{TASK_LABEL[t.status] ?? t.status}</Badge></li>)}</ul>
                ) : <p className="text-muted">Sin tareas.</p>}
              </div>

              {detail.memories.length > 0 && (
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wider text-muted">Notas en memoria</div>
                  <ul className="list-disc space-y-1 pl-5">{detail.memories.map((m, i) => <li key={i}>{m}</li>)}</ul>
                </div>
              )}

              <div>
                <div className="mb-1 text-xs uppercase tracking-wider text-muted">Decisiones y avances</div>
                <form className="mb-3 flex gap-2" onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => { await post(`/projects/${detail.id}/log`, logForm); setLogForm({ ...logForm, text: "" }); });
                }}>
                  <select className="field w-32" value={logForm.kind} onChange={(e) => setLogForm({ ...logForm, kind: e.target.value as typeof logForm.kind })} aria-label="Tipo de registro">
                    <option value="progress">Avance</option><option value="decision">Decisión</option><option value="note">Nota</option>
                  </select>
                  <input className="field flex-1" placeholder="Registrar…" value={logForm.text} onChange={(e) => setLogForm({ ...logForm, text: e.target.value })} aria-label="Texto del registro" />
                  <button className="btn" disabled={!logForm.text.trim()}><Plus className="h-4 w-4" /></button>
                </form>
                {detail.log.length ? (
                  <ul className="space-y-2">
                    {[...detail.log].reverse().map((l, i) => (
                      <li key={i} className="flex gap-2">
                        <Badge tone={l.kind === "decision" ? "info" : l.kind === "progress" ? "ok" : "muted"}>{LOG_LABEL[l.kind]}</Badge>
                        <span className="flex-1">{l.text}</span>
                        <span className="shrink-0 text-xs text-muted">{l.by === "kai" ? "KAI · " : ""}{formatDate(l.at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-muted">Sin registros todavía.</p>}
              </div>
            </div>
          </Card>
        ) : <Card><p className="text-sm text-muted">Elegí un proyecto para ver su objetivo, decisiones, tareas y próximos pasos.</p></Card>}
      </div>
    </div>
  );
}

function EditableText({ label, value, onSave }: { label: string; value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wider text-muted">
        {label}
        {!editing && <button className="text-muted hover:text-ink" onClick={() => setEditing(true)} aria-label={`Editar ${label}`}><Pencil className="h-3.5 w-3.5" /></button>}
      </div>
      {editing ? (
        <div className="space-y-2">
          <textarea className="field min-h-20" value={draft} onChange={(e) => setDraft(e.target.value)} aria-label={label} />
          <div className="flex gap-2">
            <button className="btn btn-primary" onClick={() => { onSave(draft); setEditing(false); }}>Guardar</button>
            <button className="btn" onClick={() => { setDraft(value); setEditing(false); }}>Cancelar</button>
          </div>
        </div>
      ) : <p className="whitespace-pre-wrap">{value || <span className="text-muted">—</span>}</p>}
    </div>
  );
}
