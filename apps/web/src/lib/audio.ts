// Utilidades de audio puras (sin APIs del navegador) para poder probarlas.

/** Nivel RMS de un bloque de muestras [-1, 1]. */
export function rms(samples: Float32Array): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

export interface SilenceDetectorOptions {
  /** Umbral mínimo absoluto de voz. */
  minThreshold?: number;
  /** Cuántas veces por encima del ruido de fondo se considera voz. */
  noiseFactor?: number;
  /** Tiempo de voz continua para declarar inicio (ms). */
  startMs?: number;
  /** Silencio continuo para declarar fin (ms). */
  endSilenceMs?: number;
  /** Tiempo inicial en el que sólo se mide el ruido de fondo (ms). */
  calibrationMs?: number;
}

export type DetectorEvent = "speech_start" | "speech_end" | null;

/**
 * Detector de actividad de voz por energía con ruido de fondo adaptativo.
 * `feed(level, durationMs)` devuelve un evento cuando cambia el estado.
 */
export class SilenceDetector {
  private floor = 0.004;
  private voiceMs = 0;
  private silenceMs = 0;
  private calibratedMs = 0;
  speaking = false;
  readonly opts: Required<SilenceDetectorOptions>;

  constructor(opts: SilenceDetectorOptions = {}) {
    this.opts = { minThreshold: 0.012, noiseFactor: 3, startMs: 120, endSilenceMs: 900, calibrationMs: 400, ...opts };
  }

  get threshold() {
    return Math.max(this.opts.minThreshold, this.floor * this.opts.noiseFactor);
  }

  feed(level: number, durationMs: number): DetectorEvent {
    if (this.calibratedMs < this.opts.calibrationMs) {
      // Calibración: el nivel más bajo observado (las pausas entre palabras revelan el ambiente
      // aunque el usuario empiece a hablar enseguida).
      this.floor = this.calibratedMs === 0 ? level : Math.min(this.floor, level);
      this.calibratedMs += durationMs;
      return null;
    }
    const isVoice = level > this.threshold;
    if (!this.speaking) {
      if (isVoice) {
        this.voiceMs += durationMs;
        if (this.voiceMs >= this.opts.startMs) {
          this.speaking = true;
          this.silenceMs = 0;
          return "speech_start";
        }
      } else {
        this.voiceMs = 0;
        // El ruido de fondo sólo se aprende fuera de la voz.
        this.floor = this.floor * 0.97 + level * 0.03;
      }
      return null;
    }
    // Un ruido estable se termina absorbiendo aunque haya empezado como "voz".
    this.floor = this.floor * 0.999 + level * 0.001;
    if (isVoice) {
      this.silenceMs = 0;
    } else {
      this.silenceMs += durationMs;
      if (this.silenceMs >= this.opts.endSilenceMs) {
        this.speaking = false;
        this.voiceMs = 0;
        return "speech_end";
      }
    }
    return null;
  }

  reset() {
    this.speaking = false;
    this.voiceMs = 0;
    this.silenceMs = 0;
  }
}

/** Reduce la frecuencia de muestreo promediando (suficiente para voz). */
export function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (toRate >= fromRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

export function concat(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/** Codifica PCM mono como WAV de 16 bits. */
export function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array<ArrayBuffer> {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buffer);
}

/** Mensaje comprensible para errores de getUserMedia. */
export function micErrorMessage(err: unknown): string {
  const name = (err as { name?: string })?.name ?? "";
  switch (name) {
    case "NotAllowedError":
    case "SecurityError":
      return "No hay permiso para usar el micrófono. Habilitalo en la configuración del navegador (ícono del candado) y en Windows: Configuración → Privacidad → Micrófono.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No se encontró el micrófono seleccionado. Conectalo o elegí otro dispositivo.";
    case "NotReadableError":
    case "AbortError":
      return "El micrófono está ocupado por otra aplicación o falló el dispositivo. Cerrá otras apps que lo usen y reintentá.";
    default:
      return `No se pudo acceder al micrófono${(err as Error)?.message ? `: ${(err as Error).message}` : "."}`;
  }
}
