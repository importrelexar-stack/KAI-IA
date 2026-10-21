import { useEffect, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { get, post } from "../lib/api";

interface UpdateInfo {
  current: { version: string; build: number; sha: string };
  latest: { version: string; build?: number; notes?: string };
  available: boolean;
  can_install: boolean;
  state: UpdateState;
}
interface UpdateState { phase: "idle" | "downloading" | "launching" | "launched" | "error"; progress?: number; error?: string }

const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;

/** Pie del menú: versión, «Buscar actualizaciones» y, si hay una nueva, «Actualizar» (descarga, verifica e instala). */
export function UpdateButton({ version }: { version: string }) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [state, setState] = useState<UpdateState>({ phase: "idle" });
  const [checking, setChecking] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function check(force = false, manual = false) {
    setChecking(true);
    if (manual) setMsg(null);
    try {
      const r = await get<UpdateInfo>(`/system/update${force ? "?force=true" : ""}`);
      setInfo(r);
      setState(r.state);
      if (manual && !r.available) setMsg("Ya tenés la última versión.");
    } catch (e) {
      if (manual) setMsg((e as Error).message);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    void check();
    const t = setInterval(() => void check(), CHECK_EVERY_MS);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (state.phase !== "downloading" && state.phase !== "launching") return;
    const t = setInterval(async () => {
      try { setState(await get<UpdateState>("/system/update/state")); } catch { /* KAI se está cerrando para actualizar */ }
    }, 1000);
    return () => clearInterval(t);
  }, [state.phase]);

  async function install() {
    if (!info) return;
    if (!info.can_install) {
      setMsg("Instalaste KAI desde el código: cerrá KAI y ejecutá «actualizar.bat» en la carpeta de KAI.");
      return;
    }
    if (!confirm(`¿Actualizar KAI a la versión ${info.latest.version}?\n\nSe descarga el instalador oficial, se verifica y se abre. `
      + "KAI se cierra unos segundos y vuelve a abrirse. Tus conversaciones y ajustes se conservan.")) return;
    setMsg(null);
    try { setState(await post<UpdateState>("/system/update/install")); } catch (e) { setMsg((e as Error).message); }
  }

  const phase = state.phase;
  return (
    <div className="mt-auto space-y-1 px-2 pb-1 text-[11px] text-muted">
      {info?.available && phase !== "launched" && (
        <button className="btn btn-primary w-full justify-center text-xs" onClick={() => void install()}
          disabled={phase === "downloading" || phase === "launching"} title={info.latest.notes}>
          {phase === "downloading" || phase === "launching" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {phase === "downloading" ? `Descargando ${Math.round((state.progress ?? 0) * 100)}%`
            : phase === "launching" ? "Abriendo instalador…" : `Actualizar a v${info.latest.version}`}
        </button>
      )}
      {phase === "launched" && <p className="text-cyan">Se abrió el instalador. KAI se va a reiniciar solo.</p>}
      {phase === "error" && <p className="text-danger">{state.error}</p>}
      {msg && <p>{msg}</p>}
      <div className="flex items-center justify-between gap-2">
        <span>KAI AI · v{info?.current.version ?? version}{info?.current.build ? ` (build ${info.current.build})` : ""}</span>
        <button className="inline-flex items-center gap-1 hover:text-white" onClick={() => void check(true, true)} disabled={checking}
          aria-label="Buscar actualizaciones" title="Buscar actualizaciones">
          <RefreshCw className={`h-3 w-3 ${checking ? "animate-spin" : ""}`} />
        </button>
      </div>
    </div>
  );
}
