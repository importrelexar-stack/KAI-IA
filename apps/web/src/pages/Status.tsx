import { RefreshCw } from "lucide-react";
import { Badge, Card, PageHeader, formatDate } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { SystemStatus } from "../lib/api";

const FEATURE: Record<string, string> = {
  chat: "Chat con Claude", history: "Historial persistente", tasks: "Motor de tareas", cowork_bridge: "CoworkBridge",
  voice: "Voz", agents: "Agentes especializados", automation: "Automatización Windows", files: "Archivos", attachments: "Adjuntos en el chat", android: "Android",
};
const FEATURE_STATE: Record<string, { label: string; tone: "ok" | "warn" | "muted" | "info" }> = {
  available: { label: "Disponible", tone: "ok" },
  needs_api_key: { label: "Falta clave de API", tone: "warn" },
  manual: { label: "Manual", tone: "info" },
  planned: { label: "Planificado", tone: "muted" },
  beta: { label: "Beta", tone: "info" },
  disabled: { label: "Desactivado", tone: "muted" },
};

interface AuditEntry { id: number; action: string; target: string | null; client: string | null; created_at: string }

export function StatusPage() {
  const status = useApi<SystemStatus>("/system/status");
  const audit = useApi<AuditEntry[]>("/audit?limit=30");
  const s = status.data;
  return (
    <div className="space-y-4">
      <PageHeader title="Estado del sistema" actions={<button className="btn" onClick={() => { void status.reload(); void audit.reload(); }}><RefreshCw className="h-4 w-4" />Actualizar</button>} />
      {status.error && <p className="text-danger">{status.error}</p>}
      {s && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card title="KAI Core">
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-muted">Versión</dt><dd>{s.version}</dd>
              <dt className="text-muted">Activo hace</dt><dd>{Math.floor(s.uptime_seconds / 60)} min</dd>
              <dt className="text-muted">Plataforma</dt><dd>{s.platform}</dd>
              <dt className="text-muted">Python</dt><dd>{s.python}</dd>
              <dt className="text-muted">Base de datos</dt><dd>{s.database.ok ? <Badge tone="ok">OK</Badge> : <Badge tone="danger">Error</Badge>}</dd>
              <dt className="text-muted">Estado</dt><dd>{s.assistant.state}</dd>
              <dt className="text-muted">Clientes en tiempo real</dt><dd>{s.realtime_clients}</dd>
            </dl>
          </Card>
          <Card title="IA y consumo de hoy (UTC)">
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-muted">Proveedor</dt><dd>{s.provider.name}{s.provider.demo_mode && " (demo)"}</dd>
              <dt className="text-muted">Modelo</dt><dd>{s.provider.model}</dd>
              <dt className="text-muted">Esfuerzo</dt><dd>{s.provider.effort}</dd>
              <dt className="text-muted">Solicitudes</dt><dd>{s.usage_today.requests}</dd>
              <dt className="text-muted">Tokens entrada / salida</dt><dd>{s.usage_today.input_tokens.toLocaleString("es-AR")} / {s.usage_today.output_tokens.toLocaleString("es-AR")}</dd>
              <dt className="text-muted">Tokens leídos de caché</dt><dd>{s.usage_today.cache_read_tokens.toLocaleString("es-AR")}</dd>
              <dt className="text-muted">Presupuesto diario</dt><dd>{s.budget.daily_tokens ? s.budget.daily_tokens.toLocaleString("es-AR") : "Sin límite"}</dd>
            </dl>
          </Card>
          <Card title="Funciones" className="md:col-span-2">
            <ul className="grid gap-2 sm:grid-cols-3">
              {Object.entries(s.features).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm">
                  {FEATURE[k] ?? k}<Badge tone={FEATURE_STATE[v]?.tone ?? "muted"}>{FEATURE_STATE[v]?.label ?? v}</Badge>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
      <Card title="Registro de auditoría (últimos 30)">
        {audit.data?.length ? (
          <ul className="divide-y divide-line font-mono text-xs">
            {audit.data.map((a) => (
              <li key={a.id} className="flex gap-3 py-1.5"><span className="text-muted">{formatDate(a.created_at)}</span><span className="text-cyan">{a.action}</span><span className="truncate text-muted">{a.target}</span></li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">Sin eventos.</p>}
      </Card>
    </div>
  );
}
