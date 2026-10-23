import { useEffect, useState } from "react";
import { ArrowUp, FileText, Folder, FolderPlus, Lock, Plus, Trash2 } from "lucide-react";
import { Badge, Card, Notice, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { get, put, type AutomationPermissions, type BrowseResult, type Level } from "../lib/api";

const TOOL_LABEL: Record<string, string> = {
  listar_carpeta: "Listar carpetas",
  buscar_archivos: "Buscar archivos",
  leer_archivo: "Leer archivos (texto, PDF, Word)",
  crear_carpeta: "Crear carpetas",
  escribir_archivo: "Crear o reemplazar archivos de texto",
  mover_archivo: "Mover o renombrar",
  organizar_carpeta: "Ordenar carpetas",
  enviar_a_papelera: "Enviar a la papelera",
  abrir: "Abrir archivos y aplicaciones registradas",
  abrir_aplicacion: "Abrir aplicaciones del menú Inicio",
  ejecutar_script: "Ejecutar scripts registrados",
};
const LEVEL_LABEL: Record<Level, string> = { allow: "Permitir", ask: "Preguntar", deny: "Bloquear" };

export function FilesPage() {
  const perms = useApi<AutomationPermissions>("/automation/permissions");
  const installed = useApi<{ available: boolean; total: number }>("/automation/installed-apps");
  const [draft, setDraft] = useState<AutomationPermissions | null>(null);
  const [msg, setMsg] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const [newFolder, setNewFolder] = useState({ path: "", mode: "read" as "read" | "read_write" });
  const [newApp, setNewApp] = useState({ name: "", command: "" });
  const [newScript, setNewScript] = useState({ name: "", path: "", timeout_seconds: 60 });

  useEffect(() => { if (perms.data) setDraft(perms.data); }, [perms.data]);

  async function save(next: AutomationPermissions) {
    setMsg(null);
    try {
      const saved = await put<AutomationPermissions>("/automation/permissions", {
        folders: next.folders, apps: next.apps.map(({ name, command }) => ({ name, command })),
        scripts: next.scripts, levels: next.levels, start_menu_apps: next.start_menu_apps,
      });
      perms.setData(saved);
      setDraft(saved);
      setMsg({ tone: "info", text: "Permisos guardados." });
      return true;
    } catch (e) {
      setMsg({ tone: "danger", text: (e as Error).message });
      return false;
    }
  }

  if (!draft) return <p className="text-muted">{perms.error ?? "Cargando…"}</p>;

  return (
    <div className="space-y-4">
      <PageHeader title="Archivos y automatización" subtitle="KAI sólo accede a lo que autorizás acá. Las acciones que modifican algo pueden pedir tu confirmación." />
      <Notice>
        Las carpetas del sistema, los datos de KAI y los archivos de credenciales (.env, claves, .ssh) quedan bloqueados siempre.
        Nada se borra definitivamente: lo eliminado va a la Papelera de reciclaje. KAI no puede ejecutar comandos libres: sólo
        abre aplicaciones (del menú Inicio o las que registres) y los scripts que registres.
      </Notice>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <Card title="Carpetas autorizadas">
        {draft.folders.length ? (
          <ul className="mb-3 divide-y divide-line">
            {draft.folders.map((f, i) => (
              <li key={f.path} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Folder className="h-4 w-4 text-cyan" aria-hidden />
                <code className="min-w-0 flex-1 truncate">{f.path}</code>
                <select className="field w-44" value={f.mode} aria-label={`Permiso de ${f.path}`}
                  onChange={(e) => void save({ ...draft, folders: draft.folders.map((x, j) => (j === i ? { ...x, mode: e.target.value as typeof f.mode } : x)) })}>
                  <option value="read">Sólo lectura</option>
                  <option value="read_write">Lectura y escritura</option>
                </select>
                <button className="p-1.5 text-muted hover:text-danger" aria-label="Quitar carpeta"
                  onClick={() => void save({ ...draft, folders: draft.folders.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        ) : <p className="mb-3 text-sm text-muted">Todavía no autorizaste ninguna carpeta: KAI no puede ver tus archivos.</p>}
        <form className="flex flex-wrap gap-2" onSubmit={async (e) => {
          e.preventDefault();
          if (await save({ ...draft, folders: [...draft.folders, newFolder] })) setNewFolder({ path: "", mode: "read" });
        }}>
          <input className="field min-w-64 flex-1" placeholder="C:\Users\vos\Documents\Proyectos" value={newFolder.path}
            onChange={(e) => setNewFolder({ ...newFolder, path: e.target.value })} aria-label="Ruta de la carpeta" />
          <select className="field w-44" value={newFolder.mode} onChange={(e) => setNewFolder({ ...newFolder, mode: e.target.value as "read" | "read_write" })} aria-label="Permiso">
            <option value="read">Sólo lectura</option>
            <option value="read_write">Lectura y escritura</option>
          </select>
          <button className="btn btn-primary" disabled={!newFolder.path.trim()}><FolderPlus className="h-4 w-4" />Autorizar</button>
        </form>
        <p className="mt-2 text-xs text-muted">Copiá la ruta desde el Explorador de Windows (barra de direcciones). No se permiten unidades completas ni tu carpeta de usuario entera.</p>
      </Card>

      {draft.folders.length > 0 && <Explorer roots={draft.folders.map((f) => f.path)} />}

      <Card title="Permisos por acción">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-line">
            {Object.keys(draft.default_levels).map((tool) => {
              const locked = draft.always_ask.includes(tool);
              return (
                <tr key={tool}>
                  <td className="py-2">{TOOL_LABEL[tool] ?? tool}</td>
                  <td className="py-2 text-right">
                    <select className="field w-40" value={draft.levels[tool]} aria-label={`Nivel de ${TOOL_LABEL[tool] ?? tool}`}
                      onChange={(e) => void save({ ...draft, levels: { ...draft.levels, [tool]: e.target.value as Level } })}>
                      {(["allow", "ask", "deny"] as Level[]).filter((l) => !(locked && l === "allow")).map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
                    </select>
                    {locked && <span className="ml-2 inline-flex items-center gap-1 text-xs text-muted"><Lock className="h-3 w-3" />siempre pregunta</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Aplicaciones que KAI puede abrir">
          <label className="mb-1 flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={draft.start_menu_apps}
              onChange={(e) => void save({ ...draft, start_menu_apps: e.target.checked })} />
            <span>
              Permitir que KAI abra cualquier aplicación del menú Inicio cuando se lo pidas («abrí Excel»)
              <span className="block text-xs text-muted">
                Se abre igual que con un clic en el menú Inicio, sin parámetros. KAI no puede ejecutar comandos.
                {installed.data?.available && ` ${installed.data.total} aplicaciones encontradas.`}
              </span>
            </span>
          </label>
          <p className="mb-3 text-xs text-muted">También podés registrar programas que no estén en el menú Inicio:</p>
          {draft.apps.length ? (
            <ul className="mb-3 divide-y divide-line text-sm">
              {draft.apps.map((a, i) => (
                <li key={a.name} className="flex items-center gap-2 py-2">
                  <span className="font-medium">{a.name}</span>
                  <code className="min-w-0 flex-1 truncate text-xs text-muted">{a.resolved ?? a.command}</code>
                  {a.available === false && <Badge tone="danger">No encontrada</Badge>}
                  <button className="p-1 text-muted hover:text-danger" aria-label="Quitar" onClick={() => void save({ ...draft, apps: draft.apps.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          ) : <p className="mb-3 text-sm text-muted">Sin aplicaciones registradas.</p>}
          <form className="flex flex-wrap gap-2" onSubmit={async (e) => {
            e.preventDefault();
            if (await save({ ...draft, apps: [...draft.apps, newApp] })) setNewApp({ name: "", command: "" });
          }}>
            <input className="field w-36" placeholder="Nombre (excel)" value={newApp.name} onChange={(e) => setNewApp({ ...newApp, name: e.target.value })} aria-label="Nombre de la aplicación" />
            <input className="field min-w-48 flex-1" placeholder="notepad.exe o ruta completa al .exe" value={newApp.command} onChange={(e) => setNewApp({ ...newApp, command: e.target.value })} aria-label="Programa" />
            <button className="btn" disabled={!newApp.name.trim() || !newApp.command.trim()}><Plus className="h-4 w-4" />Agregar</button>
          </form>
        </Card>

        <Card title="Scripts registrados">
          {draft.scripts.length ? (
            <ul className="mb-3 divide-y divide-line text-sm">
              {draft.scripts.map((s, i) => (
                <li key={s.name} className="flex items-center gap-2 py-2">
                  <span className="font-medium">{s.name}</span>
                  <code className="min-w-0 flex-1 truncate text-xs text-muted">{s.path}</code>
                  <span className="text-xs text-muted">{s.timeout_seconds}s</span>
                  <button className="p-1 text-muted hover:text-danger" aria-label="Quitar" onClick={() => void save({ ...draft, scripts: draft.scripts.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          ) : <p className="mb-3 text-sm text-muted">Sin scripts. Registrá sólo scripts tuyos y de confianza (.ps1, .bat, .cmd, .py).</p>}
          <form className="flex flex-wrap gap-2" onSubmit={async (e) => {
            e.preventDefault();
            if (await save({ ...draft, scripts: [...draft.scripts, newScript] })) setNewScript({ name: "", path: "", timeout_seconds: 60 });
          }}>
            <input className="field w-36" placeholder="Nombre" value={newScript.name} onChange={(e) => setNewScript({ ...newScript, name: e.target.value })} aria-label="Nombre del script" />
            <input className="field min-w-48 flex-1" placeholder="C:\scripts\backup.ps1" value={newScript.path} onChange={(e) => setNewScript({ ...newScript, path: e.target.value })} aria-label="Ruta del script" />
            <input type="number" min={5} max={600} className="field w-24" value={newScript.timeout_seconds} onChange={(e) => setNewScript({ ...newScript, timeout_seconds: Number(e.target.value) })} aria-label="Tiempo máximo en segundos" />
            <button className="btn" disabled={!newScript.name.trim() || !newScript.path.trim()}><Plus className="h-4 w-4" />Agregar</button>
          </form>
        </Card>
      </div>
    </div>
  );
}

function Explorer({ roots }: { roots: string[] }) {
  const [path, setPath] = useState(roots[0]);
  const [data, setData] = useState<BrowseResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (!roots.includes(path) && !roots.some((r) => path.startsWith(r))) setPath(roots[0]); }, [roots, path]);
  useEffect(() => {
    get<BrowseResult>(`/automation/browse?path=${encodeURIComponent(path)}`).then((d) => { setData(d); setError(null); }).catch((e) => setError((e as Error).message));
  }, [path]);

  const sep = path.includes("\\") ? "\\" : "/";
  const canGoUp = data && data.path !== data.root;
  return (
    <Card title="Explorador (lo que KAI puede ver)">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select className="field w-auto max-w-sm" value={roots.find((r) => path.startsWith(r)) ?? roots[0]} onChange={(e) => setPath(e.target.value)} aria-label="Carpeta autorizada">
          {roots.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        {canGoUp && <button className="btn" onClick={() => setPath(data.path.slice(0, data.path.lastIndexOf(sep)) || data.root)}><ArrowUp className="h-4 w-4" />Subir</button>}
        <code className="truncate text-xs text-muted">{data?.path}</code>
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      <ul className="max-h-80 divide-y divide-line overflow-y-auto text-sm">
        {data?.items.map((i) => (
          <li key={i.nombre} className="flex items-center gap-2 py-1.5">
            {i.tipo === "carpeta" ? <Folder className="h-4 w-4 text-cyan" aria-hidden /> : <FileText className="h-4 w-4 text-muted" aria-hidden />}
            {i.tipo === "carpeta"
              ? <button className="flex-1 truncate text-left hover:text-cyan" onClick={() => setPath(`${data.path}${sep}${i.nombre}`)}>{i.nombre}</button>
              : <span className="flex-1 truncate">{i.nombre}</span>}
            <span className="w-20 text-right text-xs text-muted">{i.tamano ?? ""}</span>
            <span className="w-32 text-right text-xs text-muted">{i.modificado}</span>
          </li>
        ))}
        {data && !data.items.length && <li className="py-2 text-muted">Carpeta vacía.</li>}
      </ul>
    </Card>
  );
}
