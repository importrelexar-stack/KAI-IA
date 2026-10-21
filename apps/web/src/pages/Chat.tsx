import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, FileText, Image as ImageIcon, Loader2, Mic, Paperclip, Plus, Send, Square, Wrench, X } from "lucide-react";
import { Notice } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { get, reportVoiceState, streamChat, transcribe, uploadAttachment, type AttachmentOut, type ConversationDetail, type ConversationSummary, type Message, type SystemStatus, type VoiceStatus } from "../lib/api";
import { micErrorMessage } from "../lib/audio";
import { MicCapture } from "../lib/mic";
import { PendingAction } from "../components/PendingAction";
import { browserVoice, effectiveSttEngine } from "../lib/speech";
import { SttSetup } from "../components/SttSetup";
import { navigate } from "../lib/nav";

const MAX_ATTACHMENTS = 5;
const ACCEPT = "image/png,image/jpeg,image/webp,image/gif,.pdf,.docx,.txt,.md,.csv,.json,.log,.xml,.html,.py,.js,.ts";

function AttachmentIcon({ kind }: { kind: string }) {
  return kind === "image" ? <ImageIcon className="h-3 w-3" aria-hidden /> : <FileText className="h-3 w-3" aria-hidden />;
}

interface UiMessage extends Message {
  pending?: boolean;
}

export function ChatPage({ conversationId }: { conversationId: string | null }) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<AttachmentOut[]>([]);
  const [uploading, setUploading] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
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
  const [needModel, setNeedModel] = useState(false);

  async function dictate() {
    if (dictateRef.current) { dictateRef.current.ctrl.abort(); return; }
    const v = voice.data;
    const local = effectiveSttEngine(v?.preferences.voice_stt_engine) === "local";
    if (local && !v?.stt.model_ready) { setNeedModel(true); return; }
    setNeedModel(false);
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
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
        // el reconocimiento del navegador falló en este equipo: el próximo intento usa el local
        if (!local && !browserVoice.sttAvailable() && !v?.stt.model_ready) setNeedModel(true);
      }
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

  async function attach(files: FileList | null) {
    if (!files) return;
    const list = Array.from(files).slice(0, Math.max(0, MAX_ATTACHMENTS - attachments.length));
    if (files.length > list.length) setError(`Podés adjuntar hasta ${MAX_ATTACHMENTS} archivos por mensaje.`);
    for (const f of list) {
      setUploading((n) => n + 1);
      try {
        const att = await uploadAttachment(f);
        setAttachments((a) => [...a, att]);
      } catch (e) {
        setError(`${f.name}: ${(e as Error).message}`);
      } finally {
        setUploading((n) => n - 1);
      }
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  async function send() {
    const text = input.trim();
    const sent = attachments;
    if ((!text && !sent.length) || busy || uploading) return;
    setInput("");
    setAttachments([]);
    setError(null);
    setBusy(true);
    const tempId = `tmp-${Date.now()}`;
    setMessages((m) => [
      ...m,
      { id: `${tempId}-u`, role: "user", content: text, attachments: sent, created_at: new Date().toISOString(), pending: true },
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
        } else if (ev.type === "tool") {
          const item = { name: ev.name, summary: ev.summary, ok: ev.ok, task_id: ev.task_id };
          setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? { ...x, tool_events: [...(x.tool_events ?? []), item] } : x)));
        } else if (ev.type === "done") {
          setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? ev.assistant_message : x)));
          void convs.reload();
        } else if (ev.type === "error") {
          setError(ev.message);
          setMessages((m) => m.filter((x) => x.id !== `${tempId}-a`));
        }
      }, ctrl.signal, "text", sent.map((a) => a.id));
      if (ctrl.signal.aborted) {
        setMessages((m) => m.map((x) => (x.id === `${tempId}-a` ? { ...x, pending: false, stop_reason: "cancelled" } : x)));
      }
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => m.filter((x) => !x.id.startsWith(tempId)));
      setInput(text);
      setAttachments(sent);
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
            {needModel && !voice.data?.stt.model_ready && <SttSetup status={voice.data} onReload={voice.reload} />}
          </div>
        </div>

        <form className="border-t border-line p-4" onSubmit={(e) => { e.preventDefault(); void send(); }}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void attach(e.dataTransfer.files); }}>
          {(attachments.length > 0 || uploading > 0) && (
            <ul className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2" aria-label="Archivos adjuntos">
              {attachments.map((a) => (
                <li key={a.id} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-xs">
                  <AttachmentIcon kind={a.kind} />{a.name}
                  <button type="button" onClick={() => setAttachments((x) => x.filter((y) => y.id !== a.id))} aria-label={`Quitar ${a.name}`} className="text-muted hover:text-ink"><X className="h-3 w-3" /></button>
                </li>
              ))}
              {uploading > 0 && <li className="inline-flex items-center gap-1.5 px-2 py-1 text-xs text-muted"><Loader2 className="h-3 w-3 animate-spin" />Subiendo…</li>}
            </ul>
          )}
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <input ref={fileRef} type="file" multiple className="hidden" accept={ACCEPT} onChange={(e) => void attach(e.target.files)} />
            <button type="button" className="btn h-[46px]" onClick={() => fileRef.current?.click()} disabled={busy || !!unavailable || attachments.length >= MAX_ATTACHMENTS}
              aria-label="Adjuntar archivo" title="Adjuntar documento o imagen (también podés arrastrarlo)"><Paperclip className="h-4 w-4" /></button>
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
              <button type="submit" className="btn btn-primary h-[46px]" disabled={(!input.trim() && !attachments.length) || uploading > 0 || !!unavailable} aria-label="Enviar"><Send className="h-4 w-4" /></button>
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
        {!isUser && m.tool_events && m.tool_events.length > 0 && (
          <ul className="mb-2 flex flex-wrap gap-1.5" aria-label="Acciones de KAI">
            {m.tool_events.map((t, i) => (
              <li key={i} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${t.ok ? "border-line text-muted" : "border-danger/40 text-danger"}`}>
                <Wrench className="h-3 w-3" aria-hidden />{t.summary}
              </li>
            ))}
          </ul>
        )}
        {!isUser && m.tool_events?.filter((t) => t.task_id).map((t) => <PendingAction key={t.task_id} taskId={t.task_id!} />)}
        {isUser && m.attachments && m.attachments.length > 0 && (
          <ul className="mb-1.5 flex flex-wrap gap-1.5" aria-label="Adjuntos">
            {m.attachments.map((a) => (
              <li key={a.id} className="inline-flex items-center gap-1 rounded-md bg-black/20 px-2 py-0.5 text-xs"><AttachmentIcon kind={a.kind} />{a.name}</li>
            ))}
          </ul>
        )}
        {isUser ? (
          m.content && <p className="whitespace-pre-wrap">{m.content}</p>
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
