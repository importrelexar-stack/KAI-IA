import { afterEach, describe, expect, it } from "vitest";
import { SilenceDetector, concat, downsample, encodeWav, micErrorMessage, rms } from "../lib/audio";
import { cleanForSpeech, matchWakeWord } from "../lib/speech";

function feedMany(d: SilenceDetector, level: number, ms: number, step = 20) {
  const events = [];
  for (let t = 0; t < ms; t += step) {
    const e = d.feed(level, step);
    if (e) events.push(e);
  }
  return events;
}

describe("SilenceDetector", () => {
  it("detecta inicio y fin de una frase", () => {
    const d = new SilenceDetector({ startMs: 100, endSilenceMs: 600, calibrationMs: 200 });
    expect(feedMany(d, 0.002, 1000)).toEqual([]);
    expect(feedMany(d, 0.1, 500)).toEqual(["speech_start"]);
    expect(feedMany(d, 0.002, 400)).toEqual([]); // pausa corta: sigue hablando
    expect(d.speaking).toBe(true);
    expect(feedMany(d, 0.002, 700)).toEqual(["speech_end"]);
  });

  it("ignora ruidos breves", () => {
    const d = new SilenceDetector({ startMs: 150, calibrationMs: 0 });
    expect(feedMany(d, 0.2, 60)).toEqual([]);
    expect(feedMany(d, 0.002, 200)).toEqual([]);
    expect(d.speaking).toBe(false);
  });

  it("se adapta al ruido de fondo", () => {
    const d = new SilenceDetector();
    feedMany(d, 0.02, 5000); // ambiente ruidoso pero estable
    expect(d.threshold).toBeGreaterThan(0.02);
    expect(d.speaking).toBe(false);
  });
});

describe("audio", () => {
  it("rms", () => {
    expect(rms(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5);
    expect(rms(new Float32Array())).toBe(0);
  });

  it("downsample y concat", () => {
    const x = new Float32Array(48000).fill(0.25);
    const y = downsample(x, 48000, 16000);
    expect(y.length).toBe(16000);
    expect(y[100]).toBeCloseTo(0.25);
    expect(concat([new Float32Array([1]), new Float32Array([2, 3])])).toEqual(new Float32Array([1, 2, 3]));
  });

  it("encodeWav genera un WAV PCM válido", () => {
    const wav = encodeWav(new Float32Array([0, 1, -1]), 16000);
    const view = new DataView(wav.buffer);
    expect(String.fromCharCode(...wav.slice(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...wav.slice(8, 12))).toBe("WAVE");
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint32(40, true)).toBe(6);
    expect(view.getInt16(46, true)).toBe(32767);
    expect(view.getInt16(48, true)).toBe(-32768);
  });

  it("mensajes de error del micrófono", () => {
    expect(micErrorMessage({ name: "NotAllowedError" })).toContain("permiso");
    expect(micErrorMessage({ name: "NotFoundError" })).toContain("No se encontró");
    expect(micErrorMessage({ name: "NotReadableError" })).toContain("ocupado");
  });
});

describe("matchWakeWord", () => {
  it.each([
    ["Hey KAI, ¿qué tareas tengo?", "¿qué tareas tengo?"],
    ["Ey, Kai. Abrí el chat", "Abrí el chat"],
    ["Oye Kay", ""],
    ["¡Hey, Caí! decime la hora", "decime la hora"],
    ["Kai, ¿cómo estás?", "¿cómo estás?"],
  ])("reconoce %s", (text, command) => {
    expect(matchWakeWord(text)).toEqual({ matched: true, command });
  });

  it.each(["Hay que comprar pan", "El kaiser", "hola cómo estás", "Mañana con Kai hablamos"])("no reconoce %s", (t) => {
    expect(matchWakeWord(t).matched).toBe(false);
  });
});

describe("cleanForSpeech", () => {
  it("conserva guiones bajos dentro de palabras", () => {
    expect(cleanForSpeech("usá _énfasis_ y KAI_DEMO_MODE")).toBe("usá énfasis y KAI_DEMO_MODE");
  });

  it("quita Markdown igual que el backend", () => {
    expect(cleanForSpeech("**Hola** ver [docs](https://x.y)\n\n- uno\n- dos")).toBe("Hola ver docs. uno, dos");
    expect(cleanForSpeech("# Título\n\nTexto con `code` y ```py\nx=1\n```")).toBe(
      "Título. Texto con code y (te dejé el código en pantalla)",
    );
  });
});

describe("reconocimiento en la app de escritorio", () => {
  const w = window as unknown as Record<string, unknown>;
  afterEach(() => { delete w.webkitSpeechRecognition; delete w.chrome; });

  it("en WebView2 no ofrece el reconocimiento del navegador y usa el local", async () => {
    const { browserVoice, effectiveSttEngine, isDesktopApp } = await import("../lib/speech");
    w.webkitSpeechRecognition = function () {};
    expect(browserVoice.sttAvailable()).toBe(true);
    expect(effectiveSttEngine("browser")).toBe("browser");
    w.chrome = { webview: {} };
    expect(isDesktopApp()).toBe(true);
    expect(browserVoice.sttAvailable()).toBe(false);
    expect(effectiveSttEngine("browser")).toBe("local");
    expect(effectiveSttEngine("local")).toBe("local");
  });

  it("si el navegador falla con «network», pasa al reconocimiento local", async () => {
    const { browserVoice, effectiveSttEngine } = await import("../lib/speech");
    class FakeRec {
      lang = ""; interimResults = false; maxAlternatives = 1; continuous = false;
      onresult: unknown; onend: (() => void) | null = null; onerror: ((e: { error: string }) => void) | null = null;
      start() { setTimeout(() => { this.onerror?.({ error: "network" }); this.onend?.(); }, 0); }
      abort() {}
    }
    w.webkitSpeechRecognition = FakeRec;
    await expect(browserVoice.recognizeOnce("es-AR", new AbortController().signal)).rejects.toThrow(/reconocimiento local/);
    expect(browserVoice.sttAvailable()).toBe(false);
    expect(effectiveSttEngine("browser")).toBe("local");
  });
});
