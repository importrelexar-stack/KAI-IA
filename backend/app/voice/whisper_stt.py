"""Reconocimiento de voz local con faster-whisper (CTranslate2, CPU).

Requiere `pip install -r requirements-voice.txt`. El modelo se descarga una sola vez,
sólo cuando el usuario lo pide desde la interfaz.
"""

from __future__ import annotations

import io
import logging
import threading
import wave
from pathlib import Path

from app.voice.base import EngineStatus, SpeechToText, Transcript, VoiceEngineError, language_code

log = logging.getLogger(__name__)

WHISPER_MODELS_MB = {"tiny": 75, "base": 145, "small": 465}
SAMPLE_RATE = 16_000
# Contexto inicial: mejora la puntuación y el reconocimiento del nombre «KAI».
INITIAL_PROMPTS = {"es": "Conversación en español rioplatense con KAI, un asistente personal."}


def decode_audio(data: bytes):  # type: ignore[no-untyped-def]
    """Devuelve PCM float32 mono a 16 kHz.

    WAV (lo que envía la interfaz) se decodifica con la biblioteca estándar; otros formatos
    (webm/ogg/mp3) con PyAV. No se usa el decodificador de faster-whisper porque depende de
    una API de PyAV que cambió entre versiones.
    """
    import numpy as np

    is_wav = data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if is_wav:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(w.getnframes())
    if is_wav and rate != SAMPLE_RATE:
        # Remuestreo con filtro antialiasing (libswresample); la interpolación lineal distorsiona
        # las consonantes y empeora el reconocimiento.
        try:
            return _decode_with_av(data)
        except Exception:  # noqa: BLE001 - sin PyAV: se usa el remuestreo simple
            pass
    if is_wav:
        if width == 2:
            pcm = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 4:
            pcm = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif width == 1:
            pcm = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raise ValueError(f"WAV de {width * 8} bits no soportado")
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)
        if rate != SAMPLE_RATE and len(pcm):
            n = int(round(len(pcm) * SAMPLE_RATE / rate))
            pcm = np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.float32)
        return pcm

    return _decode_with_av(data)


def _decode_with_av(data: bytes):  # type: ignore[no-untyped-def]
    import av
    import numpy as np

    chunks = []
    with av.open(io.BytesIO(data)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


class WhisperSTT(SpeechToText):
    def __init__(self, models_dir: Path, model_size: str = "base") -> None:
        if model_size not in WHISPER_MODELS_MB:
            raise ValueError(f"Modelo de Whisper no soportado: {model_size}")
        self.model_size = model_size
        self.model_dir = models_dir / f"whisper-{model_size}"
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return True

    def model_ready(self) -> bool:
        return (self.model_dir / "model.bin").is_file()

    def status(self) -> EngineStatus:
        installed = self.installed()
        ready = self.model_ready()
        if not installed:
            detail = "Falta instalar el paquete de voz (scripts\\install.ps1)."
        elif not ready:
            detail = "Modelo no descargado."
        else:
            detail = "Listo (local, sin conexión)."
        return EngineStatus(id="whisper", kind="stt", name=f"Whisper {self.model_size} (local)", installed=installed,
                            model=self.model_size, model_ready=ready, model_size_mb=WHISPER_MODELS_MB[self.model_size],
                            detail=detail)

    def download(self) -> None:
        if not self.installed():
            raise VoiceEngineError("El paquete faster-whisper no está instalado.", code="voice_not_installed")
        from faster_whisper.utils import download_model

        self.model_dir.mkdir(parents=True, exist_ok=True)
        download_model(self.model_size, output_dir=str(self.model_dir))

    def _load(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            if not self.installed():
                raise VoiceEngineError("El reconocimiento de voz local no está instalado.", code="voice_not_installed")
            if not self.model_ready():
                raise VoiceEngineError("El modelo de reconocimiento de voz no está descargado.",
                                       code="voice_model_missing")
            from faster_whisper import WhisperModel

            log.info("Cargando Whisper %s", self.model_size)
            self._model = WhisperModel(str(self.model_dir), device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: bytes, language: str) -> Transcript:
        with self._lock:
            model = self._load()
            try:
                pcm = decode_audio(audio)
                if len(pcm) < SAMPLE_RATE // 10:
                    raise VoiceEngineError("El audio es demasiado corto.", code="invalid_audio", status_code=422)
                code = language_code(language)
                # La interfaz ya entrega sólo la frase hablada: el VAD de Whisper puede recortar el
                # comienzo, así que se usa sólo en audios largos (archivos importados).
                segments, info = model.transcribe(
                    pcm, language=code, beam_size=5, condition_on_previous_text=False,
                    vad_filter=len(pcm) > 30 * SAMPLE_RATE,
                    initial_prompt=INITIAL_PROMPTS.get(code),
                )
                text = " ".join(s.text.strip() for s in segments).strip()
            except VoiceEngineError:
                raise
            except Exception as e:  # noqa: BLE001 - audio corrupto o formato no soportado
                log.warning("No se pudo transcribir el audio: %s", e)
                raise VoiceEngineError("No se pudo procesar el audio (formato no soportado o archivo dañado).",
                                       code="invalid_audio", status_code=422) from e
        return Transcript(text=text, language=info.language, duration_seconds=round(float(info.duration), 2),
                          engine="whisper")
