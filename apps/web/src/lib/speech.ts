// Texto para voz, palabra de activación y motores de voz del navegador (Web Speech API).

function stripAccents(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Variantes con las que Whisper suele transcribir «Hey KAI» en español.
const WAKE_RE = /^\s*(?:(?:hey|hei|ey|eh|ei|oye|oi|hola|ok|okey|okay|che)[\s,.!¡]*)?(?:kai|kay|kaí|cai|caí|kaj|kye|kail?)\b[\s,.!?:;]*/i;

/** Detecta «Hey KAI» al inicio de una transcripción y devuelve el resto como orden. */
export function matchWakeWord(text: string): { matched: boolean; command: string } {
  const original = text.trim().replace(/^[¡¿"'«\s]+/, "");
  const normalized = stripAccents(original);
  const m = WAKE_RE.exec(normalized);
  if (!m) return { matched: false, command: "" };
  const command = original.slice(m[0].length).trim().replace(/^[,.;:]+\s*/, "");
  return { matched: true, command };
}

/** Quita Markdown, código y URLs para leer en voz alta (equivalente al backend). */
export function cleanForSpeech(text: string, maxChars = 4000): string {
  let t = text
    .replace(/```[\s\S]*?```/g, " (te dejé el código en pantalla) ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "el enlace en pantalla")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^[ \t]*(?:[-+•]|\d+[.)])[ \t]+/gm, "")
    .replace(/[*#>|~]+|(?<!\w)_+|_+(?!\w)/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, ", ")
    .replace(/\s*([.,;:!?])(\s*[.,])+/g, "$1")
    .trim()
    .replace(/^[ ,]+|[ ,]+$/g, "");
  if (t.length > maxChars) {
    const cut = t.slice(0, maxChars);
    t = cut.includes(".") ? cut.slice(0, cut.lastIndexOf(".") + 1) : cut;
  }
  return t.trim();
}

// ---- Web Speech API (alternativa del navegador) ----

interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
}

function recognitionCtor(): (new () => RecognitionLike) | null {
  const w = window as unknown as { SpeechRecognition?: new () => RecognitionLike; webkitSpeechRecognition?: new () => RecognitionLike };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** App de escritorio (WebView2 de Windows): trae el reconocimiento «webkitSpeechRecognition», pero sin el servicio
 * de Google detrás, así que siempre falla con «network». Ahí sólo sirve el reconocimiento local (Whisper). */
export function isDesktopApp(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as { chrome?: { webview?: unknown }; __TAURI_INTERNALS__?: unknown };
  return !!w.chrome?.webview || !!w.__TAURI_INTERNALS__;
}

let browserSttFailed = false;

/** Motor de reconocimiento a usar de verdad: si el del navegador no anda en este equipo, se usa el local. */
export function effectiveSttEngine(pref: string | undefined): "local" | "browser" {
  return pref === "browser" && browserVoice.sttAvailable() ? "browser" : "local";
}

export const browserVoice = {
  sttAvailable: () => typeof window !== "undefined" && !browserSttFailed && !isDesktopApp() && recognitionCtor() !== null,
  ttsAvailable: () => typeof window !== "undefined" && "speechSynthesis" in window,

  /** Reconoce una frase con el servicio del navegador (el audio sale del equipo). */
  recognizeOnce(lang: string, signal: AbortSignal): Promise<string> {
    const Ctor = recognitionCtor();
    if (!Ctor) return Promise.reject(new Error("Este navegador no ofrece reconocimiento de voz."));
    return new Promise((resolve, reject) => {
      const rec = new Ctor();
      rec.lang = lang;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.continuous = false;
      let text = "";
      rec.onresult = (e) => {
        text = Array.from(e.results).map((r) => r[0].transcript).join(" ");
      };
      rec.onerror = (e) => {
        const msg: Record<string, string> = {
          "not-allowed": "No hay permiso para usar el micrófono.",
          "no-speech": "No te escuché. Probá de nuevo.",
          network: "El reconocimiento del navegador no está disponible en este equipo. A partir de ahora KAI usa el reconocimiento local (Whisper).",
          "audio-capture": "No se encontró el micrófono.",
        };
        if (e.error === "network") browserSttFailed = true; // desde ahora se usa el reconocimiento local
        if (e.error !== "aborted") reject(new Error(msg[e.error] ?? `Error de reconocimiento: ${e.error}`));
      };
      rec.onend = () => resolve(text.trim());
      signal.addEventListener("abort", () => rec.abort());
      rec.start();
    });
  },

  voices(lang: string): SpeechSynthesisVoice[] {
    if (!("speechSynthesis" in window)) return [];
    const all = window.speechSynthesis.getVoices();
    const base = lang.split("-")[0];
    const exact = all.filter((v) => v.lang.replace("_", "-").toLowerCase() === lang.toLowerCase());
    const same = all.filter((v) => v.lang.toLowerCase().startsWith(base));
    return [...exact, ...same.filter((v) => !exact.includes(v))];
  },

  speak(text: string, lang: string, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!("speechSynthesis" in window)) return reject(new Error("Este navegador no puede leer en voz alta."));
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang;
      const v = browserVoice.voices(lang)[0];
      if (v) u.voice = v;
      u.onend = () => resolve();
      u.onerror = (e) => (e.error === "canceled" || e.error === "interrupted" ? resolve() : reject(new Error(e.error)));
      signal.addEventListener("abort", () => window.speechSynthesis.cancel());
      window.speechSynthesis.speak(u);
    });
  },
};
