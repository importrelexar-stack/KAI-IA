import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { post, type VoiceStatus } from "../lib/api";
import { Notice } from "./ui";

/** Aviso con descarga en un clic del modelo de reconocimiento local (Whisper), con seguimiento del progreso. */
export function SttSetup({ status, onReload }: { status?: VoiceStatus | null; onReload: () => void | Promise<unknown> }) {
  const [error, setError] = useState<string | null>(null);
  const dl = status?.downloads.stt;
  const downloading = dl?.state === "downloading";

  useEffect(() => {
    if (!downloading) return;
    const t = setInterval(() => void onReload(), 3000);
    return () => clearInterval(t);
  }, [downloading]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!status || status.stt.model_ready) return null;
  if (!status.stt.installed) {
    return <Notice tone="warn">El reconocimiento de voz local no está instalado en este equipo. {status.stt.detail}</Notice>;
  }

  async function start() {
    setError(null);
    try { await post("/voice/models/stt/download"); await onReload(); } catch (e) { setError((e as Error).message); }
  }

  return (
    <Notice tone="warn">
      <span className="block">
        Para hablarle a KAI hace falta el modelo de reconocimiento de voz <strong>{status.stt.model}</strong> (~{status.stt.model_size_mb} MB).
        Se descarga una sola vez y después funciona sin Internet; el audio nunca sale de tu equipo.
      </span>
      <button className="btn mt-2" onClick={() => void start()} disabled={downloading}>
        {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        {downloading ? "Descargando… (puede tardar unos minutos)" : "Descargar ahora"}
      </button>
      {(error || dl?.state === "error") && <span className="mt-1 block text-xs text-danger">{error ?? dl?.error}</span>}
    </Notice>
  );
}
