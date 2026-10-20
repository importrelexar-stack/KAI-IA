import { useState } from "react";
import { Loader2, Plug, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Badge, Card, Notice, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { integrationsApi, parseEnvLines, type IntegrationsOverview, type McpServer, type ToolLevel } from "../lib/api";

const STATUS: Record<McpServer["status"], { label: string; tone: "ok" | "warn" | "danger" | "muted" }> = {
  connected: { label: "Conectado", tone: "ok" },
  connecting: { label: "Conectando…", tone: "warn" },
  error: { label: "Error", tone: "danger" },
  stopped: { label: "Desactivado", tone: "muted" },
};

const LEVELS: { value: ToolLevel; label: string }[] = [
  { value: "allow", label: "Permitir" },
  { value: "ask", label: "Preguntar" },
  { value: "deny", label: "Bloquear" },
];

/** Fase 6: búsqueda/lectura web y servidores MCP (calendario, correo, notas, etc.). */
export function IntegrationsPage() {
  const data = useApi<IntegrationsOverview>("/integrations");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await data.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const d = data.data;
  return (
    <div className="space-y-4">
      <PageHeader title="Integraciones" subtitle="Conectá KAI con la web y con otras aplicaciones mediante MCP."
        actions={<button className="btn" onClick={() => void data.reload()}><RefreshCw className="h-4 w-4" />Actualizar</button>} />
      {(error || data.error) && <Notice tone="danger">{error ?? data.error}</Notice>}

      <Card title="Web">
        {d ? (
          <div className="space-y-3 text-sm">
            {([
              ["web_search_enabled", "Búsqueda web", "Claude busca información actual (máx. 5 búsquedas por respuesta, con costo por búsqueda)."],
              ["web_fetch_enabled", "Lectura de páginas", "Claude abre las páginas que le pasás o que encontró la búsqueda (máx. 5 por respuesta). Sólo puede abrir direcciones que ya aparecen en la conversación."],
            ] as const).map(([key, label, help]) => (
              <label key={key} className="flex items-start gap-2">
                <input type="checkbox" className="mt-1" checked={d.web[key]} disabled={busy === key}
                  onChange={(e) => void run(key, () => integrationsApi.setWeb({ [key]: e.target.checked }))} />
                <span><span className="text-ink">{label}</span><br /><span className="text-muted">{help}</span></span>
              </label>
            ))}
            <p className="text-xs text-muted">El contenido de las páginas se trata como dato: KAI no sigue instrucciones que aparezcan en ellas.</p>
          </div>
        ) : <Loader2 className="h-4 w-4 animate-spin" />}
      </Card>

      <Card title="Servidores MCP">
        <div className="space-y-3 text-sm">
          <p className="text-muted">
            MCP (Model Context Protocol) es el estándar abierto para conectar asistentes con aplicaciones. Cada servidor
            suma herramientas (por ejemplo, calendario, correo o notas). Las de solo lectura se permiten por defecto; las
            que modifican algo te piden autorización. Podés cambiarlo por herramienta.
          </p>
          <Notice tone="warn">
            Un servidor «local» es un programa que corre en tu PC con tus permisos. Agregá sólo servidores de fuentes
            confiables.
          </Notice>
          {d && !d.secure_storage && (
            <Notice tone="warn">No hay almacén de credenciales seguro: las claves de las integraciones se pierden al reiniciar KAI.</Notice>
          )}
          {d?.mcp.length === 0 && <p className="text-muted">Todavía no agregaste servidores.</p>}
          {d?.mcp.map((s) => <ServerCard key={s.id} s={s} busy={busy} run={run} />)}
        </div>
      </Card>

      <AddServer onAdded={() => void data.reload()} />
    </div>
  );
}

function ServerCard({ s, busy, run }: { s: McpServer; busy: string | null; run: (k: string, fn: () => Promise<unknown>) => Promise<void> }) {
  const st = STATUS[s.status];
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Plug className="h-4 w-4 text-muted" aria-hidden />
        <span className="font-medium">{s.name}</span>
        <Badge tone={st.tone}>{st.label}</Badge>
        {s.server_info && <span className="text-xs text-muted">{s.server_info}</span>}
        <span className="ml-auto flex gap-2">
          <label className="flex items-center gap-1 text-xs">
            <input type="checkbox" checked={s.enabled} disabled={busy !== null}
              onChange={(e) => void run(`en-${s.id}`, () => integrationsApi.update(s.id, { enabled: e.target.checked }))} />
            Activo
          </label>
          <button className="btn" disabled={busy !== null || !s.enabled} onClick={() => void run(`re-${s.id}`, () => integrationsApi.reconnect(s.id))}>
            {busy === `re-${s.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}Reconectar
          </button>
          <button className="btn btn-danger" disabled={busy !== null} aria-label={`Quitar ${s.name}`}
            onClick={() => { if (confirm(`¿Quitar la integración «${s.name}»? Se borran también sus claves guardadas.`)) void run(`rm-${s.id}`, () => integrationsApi.remove(s.id)); }}>
            <Trash2 className="h-4 w-4" />
          </button>
        </span>
      </div>
      <p className="mt-1 break-all font-mono text-xs text-muted">
        {s.transport === "stdio" ? [s.command, ...s.args].join(" ") : s.url}
        {s.secret_env.length > 0 && ` · claves: ${s.secret_env.join(", ")}`}
        {s.has_token && " · con token"}
      </p>
      {s.error && <p className="mt-1 text-xs text-danger">{s.error}</p>}
      {(s.secret_env.length > 0 || s.has_token) && <SecretsForm s={s} busy={busy} run={run} />}
      {s.tools.length > 0 && (
        <table className="mt-2 w-full text-xs">
          <thead><tr className="text-left text-muted"><th className="py-1">Herramienta</th><th>Tipo</th><th className="w-36">Nivel</th></tr></thead>
          <tbody>
            {s.tools.map((t) => (
              <tr key={t.name} className="border-t border-line align-top">
                <td className="py-1.5 pr-2"><span className="font-mono">{t.name}</span><br /><span className="text-muted">{t.description}</span></td>
                <td className="py-1.5 pr-2">{t.read_only ? <Badge tone="ok">Lectura</Badge> : t.destructive ? <Badge tone="danger">Destructiva</Badge> : <Badge tone="warn">Modifica</Badge>}</td>
                <td className="py-1.5">
                  <select className="field py-1" aria-label={`Nivel de ${t.name}`} value={t.level} disabled={busy !== null}
                    onChange={(e) => void run(`lv-${s.id}-${t.name}`, () => integrationsApi.setLevel(s.id, t.name, e.target.value as ToolLevel))}>
                    {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                  </select>
                  {t.custom && (
                    <button className="mt-0.5 block text-[11px] text-muted underline" disabled={busy !== null}
                      onClick={() => void run(`lv-${s.id}-${t.name}`, () => integrationsApi.setLevel(s.id, t.name, "default"))}>
                      volver al predeterminado
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AddServer({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [transport, setTransport] = useState<"stdio" | "http">("stdio");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [env, setEnv] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<McpServer | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = transport === "stdio"
        ? { name, transport, command, args: args.split(/\r?\n/).map((a) => a.trim()).filter(Boolean), env: parseEnvLines(env), secret_env: parseEnvLines(secretEnv) }
        : { name, transport, url, token: token || undefined };
      const s = await integrationsApi.add(body);
      setResult(s);
      setName(""); setCommand(""); setArgs(""); setEnv(""); setSecretEnv(""); setUrl(""); setToken("");
      onAdded();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return <button className="btn btn-primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Agregar servidor MCP</button>;
  }
  return (
    <Card title="Agregar servidor MCP">
      <form className="grid gap-3 text-sm md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <label className="space-y-1">Nombre<input className="field" value={name} onChange={(e) => setName(e.target.value)} required maxLength={40} placeholder="Calendario" /></label>
        <label className="space-y-1">Tipo
          <select className="field" value={transport} onChange={(e) => setTransport(e.target.value as "stdio" | "http")}>
            <option value="stdio">Local (programa en esta PC, stdio)</option>
            <option value="http">Remoto (HTTP)</option>
          </select>
        </label>
        {transport === "stdio" ? (
          <>
            <label className="space-y-1">Comando<input className="field font-mono" value={command} onChange={(e) => setCommand(e.target.value)} required placeholder="npx, uvx o ruta del .exe" /></label>
            <label className="space-y-1">Argumentos (uno por línea)<textarea className="field font-mono" rows={3} value={args} onChange={(e) => setArgs(e.target.value)} /></label>
            <label className="space-y-1">Variables (CLAVE=valor por línea)<textarea className="field font-mono" rows={2} value={env} onChange={(e) => setEnv(e.target.value)} /></label>
            <label className="space-y-1">Variables secretas (claves de API; se guardan cifradas)<textarea className="field font-mono" rows={2} value={secretEnv} onChange={(e) => setSecretEnv(e.target.value)} autoComplete="off" spellCheck={false} /></label>
          </>
        ) : (
          <>
            <label className="space-y-1">URL<input className="field font-mono" value={url} onChange={(e) => setUrl(e.target.value)} required placeholder="https://…/mcp" /></label>
            <label className="space-y-1">Token (opcional, Bearer)<input className="field font-mono" type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" /></label>
            <p className="text-xs text-muted md:col-span-2">Los servidores que requieren iniciar sesión con OAuth todavía no están soportados: usá uno con token.</p>
          </>
        )}
        <div className="flex gap-2 md:col-span-2">
          <button className="btn btn-primary" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}Conectar</button>
          <button type="button" className="btn" onClick={() => setOpen(false)}>Cerrar</button>
        </div>
        {error && <div className="md:col-span-2"><Notice tone="danger">{error}</Notice></div>}
        {result && (
          <div className="md:col-span-2">
            <Notice tone={result.status === "connected" ? "info" : "warn"}>
              {result.status === "connected" ? `«${result.name}» conectado: ${result.tools.length} herramientas.` : `«${result.name}» quedó guardado pero no conectó: ${result.error ?? "sin detalle"}`}
            </Notice>
          </div>
        )}
      </form>
    </Card>
  );
}

function SecretsForm({ s, busy, run }: { s: McpServer; busy: string | null; run: (k: string, fn: () => Promise<unknown>) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  if (!open) {
    return <button className="mt-1 text-xs text-muted underline" onClick={() => setOpen(true)}>Volver a cargar claves</button>;
  }
  const keys = s.transport === "http" ? ["token"] : s.secret_env;
  return (
    <form className="mt-2 flex flex-wrap items-end gap-2 text-xs" onSubmit={(e) => {
      e.preventDefault();
      const body = s.transport === "http" ? { token: values.token } : { secret_env: values };
      void run(`sec-${s.id}`, () => integrationsApi.setSecrets(s.id, body)).then(() => { setOpen(false); setValues({}); });
    }}>
      {keys.map((k) => (
        <label key={k} className="space-y-1">{k}
          <input className="field py-1 font-mono" type="password" autoComplete="off" required value={values[k] ?? ""}
            onChange={(e) => setValues({ ...values, [k]: e.target.value })} />
        </label>
      ))}
      <button className="btn btn-primary" disabled={busy !== null}>Guardar y reconectar</button>
      <button type="button" className="btn" onClick={() => setOpen(false)}>Cancelar</button>
    </form>
  );
}
