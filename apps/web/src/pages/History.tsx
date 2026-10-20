import { useState } from "react";
import { Pencil, Search, Trash2 } from "lucide-react";
import { Card, Notice, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { del, patch, type ConversationSummary } from "../lib/api";
import { navigate } from "../lib/nav";

export function HistoryPage() {
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const convs = useApi<ConversationSummary[]>(`/conversations?limit=200${q ? `&q=${encodeURIComponent(q)}` : ""}`);

  async function rename(c: ConversationSummary) {
    const title = prompt("Nuevo nombre de la conversación", c.title)?.trim();
    if (!title) return;
    try { await patch(`/conversations/${c.id}`, { title }); await convs.reload(); } catch (e) { setError((e as Error).message); }
  }

  async function remove(c: ConversationSummary) {
    if (!confirm(`¿Eliminar definitivamente «${c.title}»? Esta acción no se puede deshacer.`)) return;
    try { await del(`/conversations/${c.id}`); await convs.reload(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <div>
      <PageHeader title="Historial" subtitle="Conversaciones guardadas localmente en tu equipo (SQLite)." />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
        <input className="field pl-9" placeholder="Buscar por título…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar conversaciones" />
      </div>
      {error && <div className="mb-4"><Notice tone="danger">{error}</Notice></div>}
      <Card>
        {convs.data?.length ? (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted">
              <tr><th className="pb-2">Título</th><th className="pb-2">Mensajes</th><th className="pb-2">Actualizada</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {convs.data.map((c) => (
                <tr key={c.id}>
                  <td className="py-2.5"><button className="text-left hover:text-cyan" onClick={() => navigate("chat", c.id)}>{c.title}</button></td>
                  <td className="py-2.5 text-muted">{c.message_count}</td>
                  <td className="py-2.5 text-muted">{formatDate(c.updated_at)}</td>
                  <td className="py-2.5 text-right">
                    <button className="p-1.5 text-muted hover:text-ink" onClick={() => rename(c)} aria-label="Renombrar"><Pencil className="h-4 w-4" /></button>
                    <button className="p-1.5 text-muted hover:text-danger" onClick={() => remove(c)} aria-label="Eliminar"><Trash2 className="h-4 w-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-sm text-muted">{convs.loading ? "Cargando…" : "No hay conversaciones."}</p>}
      </Card>
    </div>
  );
}
