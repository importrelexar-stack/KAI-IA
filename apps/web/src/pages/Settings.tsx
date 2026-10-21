import { useEffect, useState } from "react";
import { KeyRound, Save, ShieldCheck, Trash2 } from "lucide-react";
import { Badge, Card, Notice, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { del, post, put, type ApiKeyStatus, type Preferences, type SettingsOut } from "../lib/api";

const SOURCE: Record<ApiKeyStatus["source"], string> = {
  env: "variable de entorno / .env",
  keyring: "Administrador de credenciales del sistema",
  memory: "memoria (se pierde al reiniciar)",
  none: "sin configurar",
};

const EFFORT_HELP: Record<string, string> = {
  low: "Rápido y económico (recomendado para chat)",
  medium: "Equilibrado",
  high: "Más razonamiento",
  xhigh: "Tareas complejas",
  max: "Máxima calidad, mayor costo",
};

export function SettingsPage() {
  const settings = useApi<SettingsOut>("/settings");
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState<{ tone: "info" | "warn" | "danger"; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => { if (settings.data) setPrefs(settings.data.preferences); }, [settings.data]);

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setMsg(null);
    try { await fn(); await settings.reload(); if (ok) setMsg({ tone: "info", text: ok }); }
    catch (e) { setMsg({ tone: "danger", text: (e as Error).message }); }
  }

  const s = settings.data;
  if (!s || !prefs) return <p className="text-muted">{settings.error ?? "Cargando…"}</p>;

  return (
    <div className="space-y-4">
      <PageHeader title="Configuración" subtitle="Credenciales, modelo, costos y preferencias." />
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <Card title={<span className="inline-flex items-center gap-2"><KeyRound className="h-4 w-4" />Clave de API de Anthropic</span>}>
        <Notice tone="warn">
          Una suscripción Claude Pro o Max <strong>no</strong> incluye acceso a la API. Necesitás una clave de
          {" "}<a className="underline" href="https://console.anthropic.com/" target="_blank" rel="noreferrer">console.anthropic.com</a>{" "}
          con facturación propia (se cobra por uso).
        </Notice>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          Estado: {s.api_key.configured ? <Badge tone="ok">Configurada {s.api_key.masked}</Badge> : <Badge tone="warn">Sin clave</Badge>}
          <span className="text-muted">Origen: {SOURCE[s.api_key.source]}</span>
          {!s.api_key.keyring_available && <Badge tone="warn">Sin almacén seguro del sistema</Badge>}
        </div>
        {s.api_key.source === "env" ? (
          <p className="mt-3 text-sm text-muted">La clave viene de ANTHROPIC_API_KEY. Para cambiarla, editá el archivo .env y reiniciá KAI.</p>
        ) : (
          <form className="mt-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); void run(async () => { await put("/settings/api-key", { api_key: key }); setKey(""); }, "Clave guardada de forma segura."); }}>
            <input className="field max-w-md flex-1" type="password" autoComplete="off" placeholder="sk-ant-…" value={key} onChange={(e) => setKey(e.target.value)} aria-label="Clave de API" />
            <button className="btn btn-primary" disabled={key.trim().length < 20}><Save className="h-4 w-4" />Guardar</button>
            {s.api_key.configured && (
              <button type="button" className="btn btn-danger" onClick={() => confirm("¿Borrar la clave guardada?") && run(() => del("/settings/api-key"), "Clave eliminada.")}><Trash2 className="h-4 w-4" />Borrar</button>
            )}
          </form>
        )}
        <button className="btn mt-3" disabled={testing || !s.api_key.configured} onClick={async () => {
          setTesting(true);
          try {
            const r = await post<{ ok: boolean; message: string }>("/settings/api-key/test");
            setMsg({ tone: r.ok ? "info" : "danger", text: r.message });
          } catch (e) { setMsg({ tone: "danger", text: (e as Error).message }); }
          setTesting(false);
        }}><ShieldCheck className="h-4 w-4" />{testing ? "Probando…" : "Probar clave (no consume tokens)"}</button>
      </Card>

      <Card title="Modelo y costos">
        <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void run(() => put("/settings", prefs), "Preferencias guardadas."); }}>
          <label className="text-sm">Modelo
            <select className="field mt-1" value={prefs.model} onChange={(e) => setPrefs({ ...prefs, model: e.target.value })}>
              {Object.entries(s.models).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <label className="text-sm">Esfuerzo de razonamiento
            <select className="field mt-1" value={prefs.effort} onChange={(e) => setPrefs({ ...prefs, effort: e.target.value as Preferences["effort"] })}>
              {s.effort_levels.map((l) => <option key={l} value={l}>{l} — {EFFORT_HELP[l]}</option>)}
            </select>
          </label>
          <label className="text-sm">Máximo de tokens por respuesta
            <input type="number" min={256} max={64000} className="field mt-1" value={prefs.max_tokens} onChange={(e) => setPrefs({ ...prefs, max_tokens: Number(e.target.value) })} />
          </label>
          <label className="text-sm">Mensajes previos enviados como contexto
            <input type="number" min={2} max={200} className="field mt-1" value={prefs.history_window} onChange={(e) => setPrefs({ ...prefs, history_window: Number(e.target.value) })} />
          </label>
          <label className="text-sm">Presupuesto diario de tokens (0 = sin límite)
            <input type="number" min={0} className="field mt-1" value={prefs.daily_token_budget} onChange={(e) => setPrefs({ ...prefs, daily_token_budget: Number(e.target.value) })} />
          </label>
          <label className="flex items-start gap-2 text-sm md:col-span-2">
            <input type="checkbox" className="mt-1" checked={prefs.fast_mode} onChange={(e) => setPrefs({ ...prefs, fast_mode: e.target.checked })} />
            <span>
              Modo rápido (Claude Opus 5.5): escribe hasta 2,5 veces más rápido
              <span className="block text-xs text-muted">
                Cuesta el doble por token (US$ 8 / 40 por millón en lugar de 4 / 20). Sólo con Opus 5.5 u Opus 5.
                Si se agota su límite, KAI responde a velocidad normal.
              </span>
            </span>
          </label>
          <label className="mt-6 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={prefs.use_fallbacks} onChange={(e) => setPrefs({ ...prefs, use_fallbacks: e.target.checked })} />
            Reintento automático con otro modelo si Claude rechaza por seguridad
          </label>
          <label className="text-sm">Tu nombre (opcional)
            <input className="field mt-1" maxLength={80} value={prefs.user_name} onChange={(e) => setPrefs({ ...prefs, user_name: e.target.value })} />
          </label>
          <label className="text-sm">Idioma
            <input className="field mt-1" maxLength={16} value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value })} />
          </label>
          <label className="text-sm md:col-span-2">Instrucciones personalizadas para KAI
            <textarea className="field mt-1 min-h-24" maxLength={4000} value={prefs.custom_instructions} onChange={(e) => setPrefs({ ...prefs, custom_instructions: e.target.value })} placeholder="Ej.: respondé con conclusiones accionables al final." />
          </label>
          <div className="md:col-span-2"><button className="btn btn-primary"><Save className="h-4 w-4" />Guardar preferencias</button></div>
        </form>
      </Card>

      <Card title="Memoria y agentes">
        <div className="space-y-3 text-sm">
          {([
            ["memory_enabled", "Usar la memoria en las conversaciones", "KAI tiene en cuenta tus preferencias y recupera datos relevantes."],
            ["memory_auto_approve", "Aprobar automáticamente lo que KAI propone recordar", "Si está apagado, cada propuesta espera tu aprobación en la pantalla Memoria."],
            ["agents_enabled", "Permitir que KAI use herramientas (memoria, tareas, planes, proyectos)", "Sin herramientas, KAI sólo conversa."],
            ["web_search_enabled", "Búsqueda web (KAI Research)", "Usa la búsqueda web de Anthropic: tiene costo adicional por búsqueda (máx. 5 por respuesta)."],
            ["web_fetch_enabled", "Lectura de páginas web", "Claude puede abrir las páginas que le pases o que encuentre la búsqueda (máx. 5 por respuesta, con costo por tokens)."],
          ] as const).map(([key, label, help]) => (
            <label key={key} className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={prefs[key]} onChange={(e) => {
                const next = { ...prefs, [key]: e.target.checked };
                setPrefs(next);
                void run(() => put("/settings", { [key]: e.target.checked }), "Preferencias guardadas.");
              }} />
              <span>{label}<span className="block text-xs text-muted">{help}</span></span>
            </label>
          ))}
          <label className="block max-w-xs">Máximo de pasos de herramientas por respuesta
            <input type="number" min={1} max={15} className="field mt-1" value={prefs.max_tool_iterations}
              onChange={(e) => setPrefs({ ...prefs, max_tool_iterations: Number(e.target.value) })}
              onBlur={() => void run(() => put("/settings", { max_tool_iterations: prefs.max_tool_iterations }), "Preferencias guardadas.")} />
          </label>
        </div>
      </Card>

      <Card title="Privacidad">
        <p className="text-sm text-muted">Todo el historial se guarda localmente en <code>data/kai.db</code>. Podés eliminar conversaciones individuales desde Historial o borrar todo acá.</p>
        <button className="btn btn-danger mt-3" onClick={() => {
          if (!confirm("¿Eliminar TODO el historial de conversaciones? No se puede deshacer.")) return;
          void run(() => del("/conversations?confirm=true"), "Historial eliminado.");
        }}><Trash2 className="h-4 w-4" />Eliminar todo el historial</button>
      </Card>
    </div>
  );
}
