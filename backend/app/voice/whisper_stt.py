"""Reconocimiento de voz local con faster-whisper (CTranslate2, CPU).

Requiere `pip install -r requirements-voice.txt`. El modelo se descarga una sola vez,
sólo cuando el usuario lo pide desde la interfaz.
"""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

from app.voice.base import EngineStatus, SpeechToText, Transcript, VoiceEngineError, language_code

log = logging.getLogger(__name__)

WHISPER_MODELS_MB = {"tiny": 75, "base": 145, "small": 465}


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
                segments, info = model.transcribe(io.BytesIO(audio), language=language_code(language),
                                                  beam_size=1, vad_filter=True, condition_on_previous_text=False)
                text = " ".join(s.text.strip() for s in segments).strip()
            except VoiceEngineError:
                raise
            except Exception as e:  # noqa: BLE001 - audio corrupto o formato no soportado
                log.warning("No se pudo transcribir el audio: %s", e)
                raise VoiceEngineError("No se pudo procesar el audio (formato no soportado o archivo dañado).",
                                       code="invalid_audio", status_code=422) from e
        return Transcript(text=text, language=info.language, duration_seconds=round(float(info.duration), 2),
                          engine="whisper")
