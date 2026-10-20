import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Ear, Mic, MicOff, Square, Volume2 } from "lucide-react";
import { KaiCore } from "../components/KaiCore";
import { Badge, Card, Notice, PageHeader } from "../components/ui";
import { useApi } from "../hooks/useApi";
import {
  post, put, reportVoiceState, streamChat, synthesize, transcribe,
  type AssistantState, type Preferences, type SettingsOut, type VoiceEngine, type VoiceStatus,
} from "../lib/api";
import { micErrorMessage } from "../lib/audio";
import { MicCapture, canSelectOutput, listDevices } from "../lib/mic";
import { browserVoice, cleanForSpeech, matchWakeWord } from "../lib/speech";

type Phase = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Tocá el micrófono para hablar",
  listening: "Te escucho…",
  transcribing: "Transcribiendo…",
  thinking: "Pensando…",
  speaking: "Hablando… (Esc o tocá para interrumpir)",
};
const PHASE_CORE: Record<Phase, AssistantState> = {
  idle: "idle", listening: "listening", transcribing: "processing", thinking: "processing", speaking: "speaking",
};

const store = {
  get: (k: string) => { try { return localStorage.getItem(k) ?? ""; } catch { return ""; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
};

interface Turn { role: "user" | "assistant"; text: string }

function chime() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.26);
    osc.onended = () => void ctx.close();
  } catch { /* sin audio */ }
}

export function VoicePage({ refreshKey }: { refreshKey: number }) {
  const status = useApi<VoiceStatus>("/voice/status", [refreshKey]);
  const settings = useApi<SettingsOut>("/settings");
  const [phase, setPhase] = useState<Phase>("idle");
  const [handsfree, setHandsfree] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [level, setLevel] = useState(0);
  const [consentOpen, setConsentOpen] = useState(false);
  const [activateAfterConsent, setActivateAfterConsent] = useState(false);
  const [devices, setDevices] = useState<{ inputs: MediaDeviceInfo[]; outputs: MediaDeviceInfo[] }>({ inputs: [], outputs: [] });
  const [micId, setMicId] = useState(() => store.get("kai.mic"));
  const [outId, setOutId] = useState(() => store.get("kai.out"));

  const micRef = useRef<MicCapture | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const convRef = useRef<string | null>(null);
  const handsfreeRef = useRef(false);
  const busyRef = useRef(false);

  const s = status.data;
  const prefs = settings.data?.preferences;
  const lang = s?.preferences.language ?? "es-AR";
  const sttLocal = (s?.preferences.voice_stt_engine ?? "local") === "local";
  const ttsLocal = (s?.preferences.voice_tts_engine ?? "local") === "local";
  const sttReady = sttLocal ? !!s?.stt.installed && !!s?.stt.model_ready : browserVoice.sttAvailable();
  const ttsReady = ttsLocal ? !!s?.tts.installed && !!s?.tts.model_ready : browserVoice.ttsAvailable();

  const refreshDevices = useCallback(async () => {
    try { setDevices(await listDevices()); } catch { /* sin permisos todavía */ }
  }, []);

  useEffect(() => {
    void refreshDevices();
    navigator.mediaDevices?.addEventListener?.("devicechange", refreshDevices);
    return () => navigator.mediaDevices?.removeEventListener?.("devicechange", refreshDevices);
  }, [refreshDevices]);

  const releaseMic = useCallback(() => {
    micRef.current?.close();
    micRef.current = null;
    setLevel(0);
  }, []);

  const getMic = useCallback(async () => {
    if (micRef.current?.isOpen) return micRef.current;
    const mic = new MicCapture({ deviceId: micId || undefined, onLevel: (l) => setLevel(l) });
    try {
      await mic.open();
    } catch (e) {
      throw new Error(micErrorMessage(e));
    }
    micRef.current = mic;
    void refreshDevices(); // con permiso concedido aparecen los nombres de los dispositivos
    return mic;
  }, [micId, refreshDevices]);

  const stopAll = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    audioRef.current?.pause();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    micRef.current?.stopMode();
    reportVoiceState("idle");
    busyRef.current = false;
    setPhase("idle");
  }, []);

  // Al salir de la pantalla se libera el micrófono (manos libres sólo funciona con la pantalla abierta).
  useEffect(() => () => {
    handsfreeRef.current = false;
    abortRef.current?.abort();
    audioRef.current?.pause();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    micRef.current?.close();
    reportVoiceState("idle");
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") stopAll(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stopAll]);

  async function speak(text: string, signal: AbortSignal) {
    const clean = cleanForSpeech(text);
    if (!clean) return;
    setPhase("speaking");
    reportVoiceState("speaking");
    // Si el usuario habla durante la respuesta (manos libres), se interrumpe.
    if (handsfreeRef.current && micRef.current) micRef.current.monitor(() => abortRef.current?.abort());
    try {
      if (ttsLocal && s?.tts.model_ready) {
        const blob = await synthesize(clean, signal);
        const url = URL.createObjectURL(blob);
        const audio = audioRef.current ?? new Audio();
        audioRef.current = audio;
        audio.src = url;
        if (outId && canSelectOutput()) {
          try { await (audio as HTMLAudioElement & { setSinkId(id: string): Promise<void> }).setSinkId(outId); } catch { /* salida no disponible */ }
        }
        await new Promise<void>((resolve, reject) => {
          const done = () => { URL.revokeObjectURL(url); resolve(); };
          audio.onended = done;
          audio.onerror = () => { URL.revokeObjectURL(url); reject(new Error("No se pudo reproducir el audio.")); };
          signal.addEventListener("abort", () => { audio.pause(); done(); }, { once: true });
          audio.play().catch(reject);
        });
      } else if (browserVoice.ttsAvailable()) {
        await browserVoice.speak(clean, lang, signal);
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") throw e;
    } finally {
      micRef.current?.stopMode();
      reportVoiceState("idle");
    }
  }

  async function ask(text: string, ctrl: AbortController) {
    setTurns((t) => [...t, { role: "user", text }, { role: "assistant", text: "" }]);
    setPhase("thinking");
    let answer = "";
    let failure: string | null = null;
    await streamChat(text, convRef.current, (ev) => {
      if (ev.type === "meta") convRef.current = ev.conversation_id;
      else if (ev.type === "delta") {
        answer += ev.text;
        setTurns((t) => [...t.slice(0, -1), { role: "assistant", text: answer }]);
      } else if (ev.type === "error") failure = ev.message;
    }, ctrl.signal, "voice");
    if (failure) {
      setTurns((t) => t.slice(0, -1));
      throw new Error(failure);
    }
    if (!ctrl.signal.aborted && answer && (s?.preferences.voice_auto_speak ?? true)) await speak(answer, ctrl.signal);
  }

  async function recognize(ctrl: AbortController, mic?: MicCapture): Promise<string> {
    setPhase("listening");
    reportVoiceState("listening");
    try {
      if (sttLocal) {
        const m = mic ?? (await getMic());
        const blob = await m.listenUtterance(ctrl.signal);
        if (!blob) return "";
        setPhase("transcribing");
        reportVoiceState("idle");
        return (await transcribe(blob, lang, ctrl.signal)).text;
      }
      return await browserVoice.recognizeOnce(lang, ctrl.signal);
    } finally {
      reportVoiceState("idle");
    }
  }

  async function talk() {
    if (busyRef.current) { stopAll(); return; }
    if (!sttReady) { setError(sttLocal ? "Primero descargá el modelo de reconocimiento de voz (abajo)." : "Este navegador no ofrece reconocimiento de voz."); return; }
    setError(null);
    setInfo(null);
    busyRef.current = true;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const text = (await recognize(ctrl)).trim();
      if (!handsfreeRef.current) releaseMic();
      if (ctrl.signal.aborted) return;
      if (!text) { setInfo("No te escuché. Probá de nuevo, un poco más cerca del micrófono."); return; }
      await ask(text, ctrl);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      busyRef.current = false;
      setPhase("idle");
      if (handsfreeRef.current) resumeHandsfree();
      else releaseMic();
    }
  }

  function resumeHandsfree() {
    const mic = micRef.current;
    if (!handsfreeRef.current || !mic) return;
    mic.startContinuous(async (blob) => {
      if (busyRef.current || !handsfreeRef.current) return;
      busyRef.current = true;
      mic.stopMode();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        const t = await transcribe(blob, lang, ctrl.signal);
        const wake = matchWakeWord(t.text);
        if (!wake.matched) return; // lo que no empieza con «Hey KAI» se descarta y no se guarda
        let command = wake.command;
        if (!command) {
          chime();
          command = (await recognize(ctrl, mic)).trim();
        }
        if (command && !ctrl.signal.aborted) await ask(command, ctrl);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      } finally {
        busyRef.current = false;
        setPhase("idle");
        if (handsfreeRef.current) resumeHandsfree();
      }
    });
  }

  async function toggleHandsfree() {
    if (handsfree) {
      handsfreeRef.current = false;
      setHandsfree(false);
      stopAll();
      releaseMic();
      return;
    }
    if (!s?.preferences.voice_handsfree_consent) { setConsentOpen(true); return; }
    if (!(s.preferences.voice_stt_engine === "local" && s.stt.model_ready)) {
      setError("El modo manos libres necesita el reconocimiento local (Whisper) descargado, para que el audio no salga de tu equipo.");
      return;
    }
    try {
      setError(null);
      await getMic();
      handsfreeRef.current = true;
      setHandsfree(true);
      resumeHandsfree();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function savePrefs(change: Partial<Preferences>) {
    try {
      await put("/settings", change);
      await Promise.all([status.reload(), settings.reload()]);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function download(kind: "stt" | "tts") {
    try { await post(`/voice/models/${kind}/download`); await status.reload(); } catch (e) { setError((e as Error).message); }
  }

  async function testVoice() {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try { await speak("Hola, soy KAI. Así suena mi voz.", ctrl.signal); } catch (e) { setError((e as Error).message); } finally { setPhase("idle"); }
  }

  // Tras aceptar el consentimiento, se activa en cuanto el estado actualizado lo refleja.
  useEffect(() => {
    if (activateAfterConsent && s?.preferences.voice_handsfree_consent) {
      setActivateAfterConsent(false);
      void toggleHandsfree();
    }
  }); // eslint-disable-line react-hooks/exhaustive-deps

  const busy = phase !== "idle";

  return (
    <div className="space-y-4">
      <PageHeader title="Voz" subtitle="Hablá con KAI y escuchá sus respuestas. Español de Argentina por defecto." />
      {s && <Notice>{s.privacy} En «manos libres», sólo se procesa lo que empieza con «Hey KAI»; el resto se descarta.</Notice>}
      {error && <Notice tone="danger">{error}</Notice>}
      {info && <Notice tone="warn">{info}</Notice>}

      <section className="panel flex flex-col items-center gap-5 p-8">
        <button
          className="rounded-full focus-visible:outline-4 disabled:opacity-50"
          onClick={() => void talk()}
          disabled={!s}
          aria-label={busy ? "Interrumpir" : "Hablar con KAI"}
        >
          <KaiCore state={PHASE_CORE[phase]} size={200} />
        </button>
        <div className="h-1.5 w-56 overflow-hidden rounded-full bg-line" aria-hidden>
          <div className="h-full bg-cyan transition-[width] duration-75" style={{ width: `${Math.min(100, level * 900)}%` }} />
        </div>
        <p className="text-lg">{PHASE_LABEL[phase]}</p>
        <div className="flex flex-wrap justify-center gap-2">
          <button className="btn btn-primary" onClick={() => void talk()} disabled={!s}>
            {busy ? <><Square className="h-4 w-4" />Interrumpir</> : <><Mic className="h-4 w-4" />Hablar</>}
          </button>
          <button className={`btn ${handsfree ? "btn-danger" : ""}`} onClick={() => void toggleHandsfree()} disabled={!s}>
            {handsfree ? <><MicOff className="h-4 w-4" />Desactivar manos libres</> : <><Ear className="h-4 w-4" />Manos libres («Hey KAI»)</>}
          </button>
          {convRef.current && (
            <button className="btn" onClick={() => { convRef.current = null; setTurns([]); }}>Nueva conversación</button>
          )}
        </div>
        {handsfree && (
          <p className="flex items-center gap-2 text-sm text-danger" role="status">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-danger" />Micrófono activo — decí «Hey KAI» seguido de tu pedido
          </p>
        )}
      </section>

      {turns.length > 0 && (
        <Card title="Conversación por voz">
          <ul className="space-y-3 text-sm">
            {turns.map((t, i) => (
              <li key={i} className={t.role === "user" ? "text-cyan" : ""}>
                <span className="mr-2 text-xs uppercase text-muted">{t.role === "user" ? "Vos" : "KAI"}</span>
                {t.text || <span className="text-muted">…</span>}
              </li>
            ))}
          </ul>
          {convRef.current && <a className="mt-3 inline-block text-xs text-cyan underline" href={`#/chat/${convRef.current}`}>Ver en el chat</a>}
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Reconocimiento de voz">
          <EngineChooser
            local={s?.stt} useLocal={sttLocal} browserOk={browserVoice.sttAvailable()}
            browserNote="Usa el servicio del navegador (Google/Microsoft): el audio sale de tu equipo y necesita Internet."
            onChoose={(v) => void savePrefs({ voice_stt_engine: v })}
            onDownload={() => void download("stt")} download={s?.downloads.stt}
          />
          <label className="mt-3 block text-sm">Modelo Whisper
            <select className="field mt-1" value={prefs?.whisper_model ?? "small"} onChange={(e) => void savePrefs({ whisper_model: e.target.value as Preferences["whisper_model"] })}>
              <option value="tiny">tiny — más rápido, menos preciso (~75 MB)</option>
              <option value="base">base — liviano, menos preciso en español (~145 MB)</option>
              <option value="small">small — recomendado para español (~465 MB)</option>
            </select>
          </label>
        </Card>

        <Card title="Voz de KAI">
          <EngineChooser
            local={s?.tts} useLocal={ttsLocal} browserOk={browserVoice.ttsAvailable()}
            browserNote="Usa las voces instaladas en Windows/navegador. Puede no haber voz de Argentina."
            onChoose={(v) => void savePrefs({ voice_tts_engine: v })}
            onDownload={() => void download("tts")} download={s?.downloads.tts}
          />
          <label className="mt-3 block text-sm">Voz local
            <select className="field mt-1" value={prefs?.piper_voice ?? "es_AR-daniela-high"} onChange={(e) => void savePrefs({ piper_voice: e.target.value as Preferences["piper_voice"] })}>
              <option value="es_AR-daniela-high">Daniela — Argentina</option>
              <option value="es_MX-claude-high">Claude — México</option>
              <option value="es_ES-davefx-medium">Davefx — España</option>
            </select>
          </label>
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={prefs?.voice_auto_speak ?? true} onChange={(e) => void savePrefs({ voice_auto_speak: e.target.checked })} />
            Leer las respuestas en voz alta
          </label>
          <button className="btn mt-3" onClick={() => void testVoice()} disabled={!ttsReady || busy}><Volume2 className="h-4 w-4" />Probar voz</button>
        </Card>

        <Card title="Dispositivos" className="md:col-span-2">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-sm">Micrófono
              <select className="field mt-1" value={micId} onChange={(e) => { setMicId(e.target.value); store.set("kai.mic", e.target.value); releaseMic(); }}>
                <option value="">Predeterminado del sistema</option>
                {devices.inputs.filter((d) => d.deviceId && d.deviceId !== "default").map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Micrófono ${i + 1}`}</option>)}
              </select>
            </label>
            <label className="text-sm">Salida de audio
              <select className="field mt-1" value={outId} disabled={!canSelectOutput()} onChange={(e) => { setOutId(e.target.value); store.set("kai.out", e.target.value); }}>
                <option value="">Predeterminada del sistema</option>
                {devices.outputs.filter((d) => d.deviceId && d.deviceId !== "default").map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Salida ${i + 1}`}</option>)}
              </select>
            </label>
          </div>
          {!devices.inputs.some((d) => d.label) && <p className="mt-2 text-xs text-muted">Los nombres de los dispositivos aparecen después de dar permiso al micrófono por primera vez.</p>}
          {s?.preferences.voice_handsfree_consent && (
            <button className="btn mt-3" onClick={() => { if (handsfree) void toggleHandsfree(); void savePrefs({ voice_handsfree_consent: false }); }}>Revocar consentimiento de manos libres</button>
          )}
        </Card>
      </div>

      {consentOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="consent-title">
          <div className="panel max-w-lg p-6">
            <h2 id="consent-title" className="text-lg font-semibold">Activar «manos libres»</h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted">
              <li>El micrófono queda abierto mientras esta pantalla esté abierta y el modo activo (vas a ver el indicador rojo).</li>
              <li>Cada frase se transcribe <strong>en tu equipo</strong> con Whisper. Sólo lo que empieza con «Hey KAI» se envía a Claude.</li>
              <li>El audio nunca se guarda. Podés desactivarlo o revocar este permiso cuando quieras.</li>
            </ul>
            <div className="mt-5 flex justify-end gap-2">
              <button className="btn" onClick={() => setConsentOpen(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={async () => { setConsentOpen(false); await savePrefs({ voice_handsfree_consent: true }); setActivateAfterConsent(true); }}>Acepto</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EngineChooser({ local, useLocal, browserOk, browserNote, onChoose, onDownload, download }: {
  local?: VoiceEngine; useLocal: boolean; browserOk: boolean; browserNote: string;
  onChoose: (v: "local" | "browser") => void; onDownload: () => void;
  download?: { state: string; error?: string };
}) {
  const downloading = download?.state === "downloading";
  return (
    <div className="space-y-3 text-sm">
      <label className="flex items-start gap-2">
        <input type="radio" className="mt-1" checked={useLocal} onChange={() => onChoose("local")} />
        <span className="flex-1">
          <span className="flex flex-wrap items-center gap-2">
            {local?.name ?? "Motor local"}
            {local && (local.model_ready ? <Badge tone="ok">Listo</Badge> : local.installed ? <Badge tone="warn">Falta el modelo</Badge> : <Badge tone="danger">No instalado</Badge>)}
          </span>
          <span className="block text-xs text-muted">Sin conexión y sin costo por uso. {local?.detail}</span>
          {local && local.installed && !local.model_ready && (
            <button className="btn mt-2" onClick={onDownload} disabled={downloading}>
              <Download className="h-4 w-4" />{downloading ? "Descargando…" : `Descargar modelo (~${local.model_size_mb} MB)`}
            </button>
          )}
          {download?.state === "error" && <span className="mt-1 block text-xs text-danger">{download.error}</span>}
        </span>
      </label>
      <label className="flex items-start gap-2">
        <input type="radio" className="mt-1" checked={!useLocal} disabled={!browserOk} onChange={() => onChoose("browser")} />
        <span>
          Navegador {!browserOk && <Badge>No disponible en este navegador</Badge>}
          <span className="block text-xs text-muted">{browserNote}</span>
        </span>
      </label>
    </div>
  );
}
