// Captura de micrófono en PCM con detección de voz. El audio nunca se guarda:
// sólo se arma un WAV en memoria con la frase detectada.

import { SilenceDetector, concat, downsample, encodeWav, rms, type SilenceDetectorOptions } from "./audio";

const TARGET_RATE = 16_000;
const PREROLL_MS = 450;

const WORKLET = `
class KaiCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice(0)); this.n = 0; }
      }
    }
    return true;
  }
}
registerProcessor("kai-capture", KaiCapture);
`;

type Mode =
  | { kind: "idle" }
  | { kind: "utterance"; resolve: (b: Blob | null) => void; startedAt: number; maxMs: number; noSpeechMs: number }
  | { kind: "continuous"; onSegment: (b: Blob) => void; maxMs: number }
  | { kind: "monitor"; onSpeech: () => void };

export interface MicOptions {
  deviceId?: string;
  onLevel?: (level: number, threshold: number, speaking: boolean) => void;
  detector?: SilenceDetectorOptions;
}

export class MicCapture {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private node: AudioNode | null = null;
  private detector: SilenceDetector;
  private preroll: Float32Array[] = [];
  private prerollSamples = 0;
  private segment: Float32Array[] | null = null;
  private segmentSamples = 0;
  private mode: Mode = { kind: "idle" };
  private rate = 48_000;

  constructor(private opts: MicOptions = {}) {
    this.detector = new SilenceDetector(opts.detector);
  }

  get isOpen() {
    return this.stream !== null;
  }

  async open(): Promise<void> {
    if (this.stream) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw Object.assign(new Error("Este navegador no permite usar el micrófono."), { name: "NotSupportedError" });
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: this.opts.deviceId ? { exact: this.opts.deviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    const ctx = new AudioContext();
    this.ctx = ctx;
    this.rate = ctx.sampleRate;
    const source = ctx.createMediaStreamSource(this.stream);
    if (ctx.audioWorklet) {
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      try {
        await ctx.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      const node = new AudioWorkletNode(ctx, "kai-capture");
      node.port.onmessage = (e: MessageEvent<Float32Array>) => this.onFrame(e.data);
      source.connect(node);
      this.node = node;
    } else {
      // Navegadores sin AudioWorklet
      const proc = ctx.createScriptProcessor(2048, 1, 1);
      proc.onaudioprocess = (e) => this.onFrame(new Float32Array(e.inputBuffer.getChannelData(0)));
      source.connect(proc);
      proc.connect(ctx.destination);
      this.node = proc;
    }
    if (ctx.state === "suspended") await ctx.resume();
  }

  close() {
    this.finish(null);
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close().catch(() => undefined);
    this.stream = null;
    this.ctx = null;
    this.node = null;
  }

  /** Graba una frase: empieza al detectar voz y termina tras un silencio. Devuelve WAV 16 kHz o null. */
  listenUtterance(signal: AbortSignal, maxMs = 30_000, noSpeechMs = 8_000): Promise<Blob | null> {
    this.finish(null);
    this.detector.reset();
    return new Promise((resolve) => {
      this.mode = { kind: "utterance", resolve, startedAt: performance.now(), maxMs, noSpeechMs };
      signal.addEventListener("abort", () => this.finish(null), { once: true });
    });
  }

  /** Modo manos libres: entrega cada frase detectada (máx. maxMs). */
  startContinuous(onSegment: (b: Blob) => void, maxMs = 10_000) {
    this.finish(null);
    this.detector.reset();
    this.mode = { kind: "continuous", onSegment, maxMs };
  }

  /** Avisa cuando el usuario empieza a hablar (para interrumpir la respuesta). */
  monitor(onSpeech: () => void) {
    this.finish(null);
    this.detector.reset();
    this.mode = { kind: "monitor", onSpeech };
  }

  stopMode() {
    this.finish(null);
  }

  private finish(result: Blob | null) {
    const m = this.mode;
    this.mode = { kind: "idle" };
    this.segment = null;
    this.segmentSamples = 0;
    if (m.kind === "utterance") m.resolve(result);
  }

  private toWav(chunks: Float32Array[]): Blob {
    const pcm = downsample(concat(chunks), this.rate, TARGET_RATE);
    return new Blob([encodeWav(pcm, TARGET_RATE)], { type: "audio/wav" });
  }

  private onFrame(frame: Float32Array) {
    const ms = (frame.length / this.rate) * 1000;
    const level = rms(frame);
    const ev = this.detector.feed(level, ms);
    this.opts.onLevel?.(level, this.detector.threshold, this.detector.speaking);

    // Pre-roll: los últimos ~450 ms, para no cortar el comienzo de la frase.
    this.preroll.push(frame);
    this.prerollSamples += frame.length;
    while (this.prerollSamples - this.preroll[0].length > (PREROLL_MS / 1000) * this.rate) {
      this.prerollSamples -= this.preroll.shift()!.length;
    }

    const m = this.mode;
    if (m.kind === "idle") return;
    if (m.kind === "monitor") {
      if (ev === "speech_start") {
        this.mode = { kind: "idle" };
        m.onSpeech();
      }
      return;
    }

    if (ev === "speech_start" && !this.segment) {
      this.segment = [...this.preroll];
      this.segmentSamples = this.prerollSamples;
      return;
    }
    if (this.segment) {
      this.segment.push(frame);
      this.segmentSamples += frame.length;
      const segMs = (this.segmentSamples / this.rate) * 1000;
      if (ev === "speech_end" || segMs >= m.maxMs) {
        const blob = this.toWav(this.segment);
        this.segment = null;
        this.segmentSamples = 0;
        if (m.kind === "utterance") this.finish(blob);
        else {
          this.detector.reset();
          m.onSegment(blob);
        }
      }
      return;
    }
    if (m.kind === "utterance" && performance.now() - m.startedAt > m.noSpeechMs) this.finish(null);
  }
}

export async function listDevices(): Promise<{ inputs: MediaDeviceInfo[]; outputs: MediaDeviceInfo[] }> {
  if (!navigator.mediaDevices?.enumerateDevices) return { inputs: [], outputs: [] };
  const all = await navigator.mediaDevices.enumerateDevices();
  return { inputs: all.filter((d) => d.kind === "audioinput"), outputs: all.filter((d) => d.kind === "audiooutput") };
}

export const canSelectOutput = () => typeof HTMLMediaElement !== "undefined" && "setSinkId" in HTMLMediaElement.prototype;
