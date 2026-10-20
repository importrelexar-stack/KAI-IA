import { useState } from "react";
import { Check, ClipboardCopy, Download, Upload } from "lucide-react";
import { Badge, Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { API, api, post, type ConversationSummary, type CoworkHandoff, type CoworkStatus } from "../lib/api";

const STATUS: Record<CoworkHandoff["status"], { label: string; tone: "muted" | "info" | "ok" | "danger" }> = {
  draft: { label: "Borrador", tone: "muted" },
  sent: { label: "Enviada (manual)", tone: "info" },
  completed: { label: "Resultado importado", tone: "ok" },
  cancelled: { label: "Cancelada", tone: "danger" },
};

const lines = (s: string) => s.split("\n").map((l) => l.trim()).filter(Boolean);

export function CoworkPage() {
  const status = useApi<CoworkStatus>("/cowork/status");
  const handoffs = useApi<CoworkHandoff[]>("/cowork/handoffs");
  const convs = useApi<ConversationSummary[]>("/conversations?limit=30");
  const [selected, setSelected] = useState<CoworkHandoff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [result, setResult] = useState("");
  const [form, setForm] = useState({ title: "", objective: "", context: "", deliverables: "", constraints: "", folders: "", conversation_id: "", include_messages: 6 });

  async function act<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setError(null);
    try { return await fn(); } catch (e) { setError((e as Error).message); return undefined; }
  }

  async function prepare() {
    const h = await act(() => post<CoworkHandoff>("/cowork/prepare", {
      title: form.title, objective: form.objective, context: form.context,
      deliverables: lines(form.deliverables), constraints: lines(form.constraints), folders: lines(form.folders),
      conversation_id: form.conversation_id || null, include_messages: form.conversation_id ? form.include_messages : 0,
    }));
    if (h) { setSelected(h); await handoffs.reload(); }
  }

  async function refreshSelected(id: string) {
    const h = await act(() => api<CoworkHandoff>(`/cowork/handoffs/${id}`));
    if (h) setSelected(h);
    await handoffs.reload();
  }

  async function copy(h: CoworkHandoff) {
    await navigator.clipboard.writeText(h.instructions_md);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function upload(h: CoworkHandoff, files: FileList | null) {
    if (!files?.length) return;
    for (const f of Array.from(files)) {
      const fd = new FormData();
      fd.append("file", f);
      await act(() => api(`/cowork/handoffs/${h.id}/files`, { method: "POST", body: fd }));
    }
    await refreshSelected(h.id);
  }

  return (
    <div>
      <PageHeader title="CoworkBridge" subtitle="Preparar tareas estructuradas para Claude Cowork e importar sus resultados." />
      {status.data && (
        <div className="mb-4 space-y-2">
          <Notice tone="warn">
            <strong>Integración manual.</strong> {status.data.description} No existe una API pública oficial para controlar
            sesiones de Cowork, por eso KAI no la simula.
          </Notice>
          <Notice>{status.data.untrusted_notice}</Notice>
        </div>
      )}
      {error && <div className="mb-4"><Notice tone="danger">{error}</Notice></div>}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="1 · Preparar instrucciones">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void prepare(); }}>
            <input className="field" placeholder="Título de la tarea" required maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label="Título" />
            <textarea className="field min-h-20" placeholder="Objetivo: qué tiene que lograr Cowork" required value={form.objective} onChange={(e) => setForm({ ...form, objective: e.target.value })} aria-label="Objetivo" />
            <textarea className="field min-h-16" placeholder="Contexto (opcional)" value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} aria-label="Contexto" />
            <textarea className="field min-h-16" placeholder="Entregables (uno por línea)" value={form.deliverables} onChange={(e) => setForm({ ...form, deliverables: e.target.value })} aria-label="Entregables" />
            <textarea className="field min-h-16" placeholder="Carpetas de trabajo (una por línea)" value={form.folders} onChange={(e) => setForm({ ...form, folders: e.target.value })} aria-label="Carpetas" />
            <textarea className="field min-h-16" placeholder="Restricciones adicionales (una por línea)" value={form.constraints} onChange={(e) => setForm({ ...form, constraints: e.target.value })} aria-label="Restricciones" />
            <div className="flex gap-2">
              <select className="field" value={form.conversation_id} onChange={(e) => setForm({ ...form, conversation_id: e.target.value })} aria-label="Adjuntar conversación">
                <option value="">Sin extracto de conversación</option>
                {convs.data?.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
              {form.conversation_id && (
                <input type="number" min={1} max={50} className="field w-24" value={form.include_messages} onChange={(e) => setForm({ ...form, include_messages: Number(e.target.value) })} aria-label="Cantidad de mensajes" />
              )}
            </div>
            <button className="btn btn-primary w-full justify-center" disabled={!form.title.trim() || !form.objective.trim()}>Generar instrucciones</button>
          </form>
        </Card>

        <Card title="2 · Copiar a Cowork · 3 · Importar resultado">
          {!selected ? <p className="text-sm text-muted">Generá o elegí una transferencia de la lista.</p> : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{selected.title}</span>
                <Badge tone={STATUS[selected.status].tone}>{STATUS[selected.status].label}</Badge>
              </div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-void p-3 text-xs">{selected.instructions_md}</pre>
              <div className="flex flex-wrap gap-2">
                <button className="btn" onClick={() => copy(selected)}>{copied ? <Check className="h-4 w-4 text-ok" /> : <ClipboardCopy className="h-4 w-4" />}Copiar</button>
                <a className="btn" href={`${API}/cowork/handoffs/${selected.id}/export`}><Download className="h-4 w-4" />Exportar .md</a>
                {selected.status === "draft" && (
                  <button className="btn" onClick={() => act(() => post(`/cowork/handoffs/${selected.id}/sent`)).then(() => refreshSelected(selected.id))}>Marcar como enviada</button>
                )}
                {selected.status !== "completed" && selected.status !== "cancelled" && (
                  <button className="btn btn-danger" onClick={() => confirm("¿Cancelar esta transferencia?") && act(() => post(`/cowork/handoffs/${selected.id}/cancel`)).then(() => refreshSelected(selected.id))}>Cancelar</button>
                )}
              </div>

              {selected.status !== "cancelled" && (
                <div className="space-y-2 border-t border-line pt-3">
                  <textarea className="field min-h-24" placeholder="Pegá acá el resultado que devolvió Cowork" value={result} onChange={(e) => setResult(e.target.value)} aria-label="Resultado de Cowork" />
                  <div className="flex flex-wrap gap-2">
                    <button className="btn btn-primary" disabled={!result.trim()} onClick={() => act(() => post(`/cowork/handoffs/${selected.id}/result`, { text: result })).then(() => { setResult(""); return refreshSelected(selected.id); })}>Importar resultado</button>
                    <label className="btn cursor-pointer"><Upload className="h-4 w-4" />Importar archivos<input type="file" multiple className="hidden" onChange={(e) => upload(selected, e.target.files)} /></label>
                  </div>
                </div>
              )}
              {selected.result_text && (
                <div><div className="mb-1 text-xs uppercase text-muted">Resultado importado (datos no confiables)</div>
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-void p-3 text-xs">{selected.result_text}</pre></div>
              )}
              {selected.result_files.length > 0 && (
                <ul className="text-sm">
                  {selected.result_files.map((f) => (
                    <li key={f.name}><a className="text-cyan underline" href={`${API}/cowork/handoffs/${selected.id}/files/${encodeURIComponent(f.name)}`}>{f.name}</a> <span className="text-muted">({Math.ceil(f.size / 1024)} KB)</span></li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      </div>

      <Card title="Transferencias" className="mt-4">
        {handoffs.data?.length ? (
          <ul className="divide-y divide-line">
            {handoffs.data.map((h) => (
              <li key={h.id}>
                <button className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:text-cyan" onClick={() => setSelected(h)}>
                  <span className="flex-1 truncate">{h.title}</span>
                  <Badge tone={STATUS[h.status].tone}>{STATUS[h.status].label}</Badge>
                  <span className="text-xs text-muted">{formatDate(h.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">Todavía no preparaste tareas para Cowork.</p>}
      </Card>
    </div>
  );
}
