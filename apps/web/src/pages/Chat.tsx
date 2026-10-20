import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Loader2, Mic, Plus, Send, Square } from "lucide-react";
import { Notice } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { get, reportVoiceState, streamChat, transcribe, type ConversationDetail, type ConversationSummary, type Message, type SystemStatus, type VoiceStatus } from "../lib/api";
import { micErrorMessage } from "../lib/audio";
import { MicCapture } from "../lib/mic";
import { browserVoice } from "../lib/speech";
import { navigate } from "../lib/nav";

interface UiMessage extends Message {
  pending?: boolean;
}

export function ChatPage({ conversationId }: { conversationId: string | null }) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const skipLoadRef = useRef<string | null>(null);
  const convs = useApi<ConversationSummary[]>("/conversations?limit=100");
  const status = useApi<SystemStatus>("/system/status");
  const voice = useApi<VoiceStatus>("/voice/status");
  const [dictating, setDictating] = useState<"off" | "listening" | "transcribing">("off");
  const dictateRef = useRef<{ ctrl: AbortController; mic?: MicCapture } | null>(null);

  async function dictate() {
    if (dictateRef.current) { dictateRef.current.ctrl.abort(); return; }
    const v = voice.data;
    const local = v?.preferences.voice_stt_engine !== "browser";
    if (local && !v?.stt.model_ready) { setError("Para dictar, descargá el modelo de reconocimiento en la pantalla Voz."); return; }
    const ctrl = new AbortController();
    const session: { ctrl: AbortController; mic?: MicCapture } = { ctrl };
    dictateRef.current = session;
    setError(null);
    setDictating("listening");
    reportVoiceState("listening");
    try {
      let text = "";
      if (local) {
        const mic = new MicCapture();
        session.mic = mic;
        try { await mic.open(); } catch (e) { throw new Error(micErrorMessage(e)); }
        const blob = await mic.listenUtterance(ctrl.signal);
        mic.close();
        reportVoiceState("idle");
        if (blob) {
          setDictating("transcribing");
          text = (await transcribe(blob, v?.preferences.language, ctrl.signal)).text;
        }
      } else {
        text = await browserVoice.recognizeOnce(v?.preferences.language ?? "es-AR", ctrl.signal);
      }
      if (text.trim()) setInput((cur) => (cur.trim() ? `${cur.trimEnd()} ${text.trim()}` : text.trim()));
      else if (!ctrl.signal.aborted) setError("No te escuché. Probá de nuevo.");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      session.mic?.close();
      reportVoiceState("idle");
      dictateRef.current = null;
      setDictating("off");
    }
  }

  useEffect(() => () => dictateRef.current?.ctrl.abort(), []);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    if (skipLoadRef.current === conversationId) return; // recién creada en este componente
    get<ConversationDetail>(`/conversations/${conversationId}`)
      .then((c) => setMessages(c.messages))
      .catch((e) => setError((e as Error).message));
  }, [conversationId]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const tempId = `tmp-${Date.now()}`;
    setMessages((m) => [
      ...m,
      { id: `${tempId}-u`, role: "user", content: text, created_at: new Date().toISOString(), pending: true },
      { id: `${tempId}-a`, role: "assistant", content: "", created_at: new Date().toISOString(), pending: true },
    ]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await streamChat(text, conversationId, (ev) => {
        if (ev.type === "meta") {
          setMessages((m) => m.map((x) => (x.id === `${tempId}-u` ? ev.user_message : x)));
          if (!conversationId) {
            skipLoadRef.current = ev.conversation_id;
            navigate("chat", ev.conversation_id);
          }
        } else if (ev.type === "delta") {
          setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? { ...x, content: x.content + ev.text } : x)));
        } else if (ev.type === "done") {
          setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? ev.assistant_message : x)));
          void convs.reload();
        } else if (ev.type === "error") {
          setError(ev.message);
          setMessages((m) => m.filter((x) => x.id !== `${tempId}-a`));
        }
      }, ctrl.signal);
      if (ctrl.signal.aborted) {
        setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? { ...x, pending: false, stop_reason: "cancelled" } : x)));
      }
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => m.filter((x) => !x.id.startsWith(tempId)));
      setInput(text);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  const unavailable = status.data && !status.data.provider.configured;

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line p-3 lg:flex" aria-label="Conversaciones">
        <button className="btn btn-primary mb-3 justify-center" onClick={() => navigate("chat")}><Plus className="h-4 w-4" />Nueva</button>
        <ul className="flex-1 space-y-0.5 overflow-y-auto">
          {convs.data?.map((c) => (
            <li key={c.id}>
              <a href={`#/chat/${c.id}`} className={`block truncate rounded-lg px-3 py-2 text-sm ${c.id === conversationId ? "bg-electric/15" : "text-muted hover:bg-white/5 hover:text-ink"}`}>
                {c.title}
              </a>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div ref={listRef} className="flex-1 overflow-y-auto px-6 py-6" aria-live="polite">
          <div className="mx-auto max-w-3xl space-y-5">
            {unavailable && (
              <Notice tone="warn">El chat real no está disponible porque no hay clave de API configurada. <button className="underline" onClick={() => navigate("settings")}>Ir a Configuración</button>.</Notice>
            )}
            {status.data?.provider.demo_mode && <Notice tone="warn">Modo demostración: las respuestas no provienen de una IA.</Notice>}
            {!messages.length && !unavailable && (
              <div className="pt-20 text-center text-muted">
                <p className="text-lg text-ink">¿En qué te ayudo?</p>
                <p className="mt-1 text-sm">Tu conversación queda guardada en el historial.</p>
              </div>
            )}
            {messages.map((m) => <Bubble key={m.id} m={m} streaming={busy && m.pending === true && m.role === "assistant"} />)}
            {error && <Notice tone="danger">{error}</Notice>}
          </div>
        </div>

        <form className="border-t border-line p-4" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <label htmlFor="chat-input" className="sr-only">Mensaje</label>
            <textarea
              id="chat-input"
              className="field max-h-48 min-h-[46px] resize-y"
              rows={1}
              placeholder={unavailable ? "Configurá la clave de API para conversar" : "Escribile a KAI… (Enter envía, Shift+Enter salto de línea)"}
              value={input}
              disabled={!!unavailable}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button type="button" className={`btn h-[46px] ${dictating !== "off" ? "btn-danger" : ""}`} onClick={() => void dictate()}
              disabled={busy || !!unavailable || dictating === "transcribing"} aria-label={dictating === "off" ? "Dictar por voz" : "Detener dictado"}
              title={dictating === "listening" ? "Escuchando… (tocá para cancelar)" : "Dictar por voz"}>
              {dictating === "transcribing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
            </button>
            {busy ? (
              <button type="button" className="btn btn-danger h-[46px]" onClick={() => abortRef.current?.abort()} aria-label="Detener respuesta"><Square className="h-4 w-4" /></button>
            ) : (
              <button type="submit" className="btn btn-primary h-[46px]" disabled={!input.trim() || !!unavailable} aria-label="Enviar"><Send className="h-4 w-4" /></button>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}

function Bubble({ m, streaming }: { m: UiMessage; streaming: boolean }) {
  const isUser = m.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`group max-w-[85%] rounded-2xl px-4 py-3 text-[0.95rem] ${isUser ? "bg-electric/20 border border-electric/30" : "panel"}`}>
        {isUser ? (
          <p className="whitespace-pre-wrap">{m.content}</p>
        ) : m.content ? (
          <div className="prose-kai"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
        ) : (
          <span className="inline-flex gap-1 text-muted" aria-label="KAI está escribiendo">
            <span className="animate-pulse">●</span><span className="animate-pulse [animation-delay:150ms]">●</span><span className="animate-pulse [animation-delay:300ms]">●</span>
          </span>
        )}
        {!isUser && !streaming && m.content && (
          <div className="mt-2 flex items-center gap-3 text-[11px] text-muted opacity-0 transition group-hover:opacity-100">
            <button onClick={() => navigator.clipboard?.writeText(m.content)} className="inline-flex items-center gap-1 hover:text-ink"><Copy className="h-3 w-3" />Copiar</button>
            {m.model && <span>{m.model}</span>}
            {m.stop_reason === "cancelled" && <span className="text-warn">Interrumpida</span>}
            {m.stop_reason === "max_tokens" && <span className="text-warn">Cortada por límite de tokens</span>}
          </div>
        )}
      </div>
    </div>
  );
}
