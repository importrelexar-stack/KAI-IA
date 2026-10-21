import { cleanForSpeech } from "./speech";

/** Dónde cortar la próxima frase completa del texto que va llegando (-1 si todavía no hay una). */
export function nextCut(buf: string, minChars = 25): number {
  // No se corta dentro de un bloque de código (``` abierto)
  const fences = (buf.match(/```/g) ?? []).length;
  if (fences % 2 === 1) return -1;
  const re = /([.!?…]+["»)]?)(\s+)|(\n+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(buf))) {
    const end = m.index + m[0].length;
    if (buf.slice(0, end).trim().length >= minChars) return end;
  }
  return -1;
}

/**
 * Habla la respuesta frase por frase mientras llega: la primera frase suena enseguida y la
 * siguiente se va preparando (síntesis) mientras se reproduce la anterior.
 */
export class SentenceSpeaker<T> {
  private buf = "";
  private prep: Promise<unknown> = Promise.resolve();
  private play: Promise<void> = Promise.resolve();
  private failure: unknown = null;
  spoke = false;

  constructor(
    private prepare: (text: string, signal: AbortSignal) => Promise<T>,
    private playItem: (item: T, signal: AbortSignal) => Promise<void>,
    private signal: AbortSignal,
    private onStart?: () => void,
  ) {}

  push(text: string) {
    this.buf += text;
    let cut: number;
    while ((cut = nextCut(this.buf)) > 0) {
      this.enqueue(this.buf.slice(0, cut));
      this.buf = this.buf.slice(cut);
    }
  }

  /** Termina con lo que quedó y espera a que se haya dicho todo. */
  async finish(): Promise<void> {
    if (this.buf.trim()) this.enqueue(this.buf);
    this.buf = "";
    await this.play;
    if (this.failure) throw this.failure;
  }

  private enqueue(raw: string) {
    const text = cleanForSpeech(raw);
    if (!text || this.signal.aborted) return;
    // Una síntesis a la vez (en orden), adelantada respecto de la reproducción
    const ready = this.prep.then(() => (this.signal.aborted ? null : this.prepare(text, this.signal)));
    this.prep = ready.catch(() => undefined);
    this.play = this.play.then(async () => {
      if (this.failure || this.signal.aborted) return;
      try {
        const item = await ready;
        if (item === null || this.signal.aborted) return;
        if (!this.spoke) { this.spoke = true; this.onStart?.(); }
        await this.playItem(item as T, this.signal);
      } catch (e) {
        if ((e as Error).name !== "AbortError") this.failure = e;
      }
    });
  }
}
