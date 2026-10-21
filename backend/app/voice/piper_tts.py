"""Síntesis de voz local con Piper (ONNX, CPU).

Voz por defecto: `es_AR-daniela-high` (español de Argentina). Requiere
`pip install -r requirements-voice.txt`; la voz se descarga sólo cuando el usuario lo pide.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import wave
from pathlib import Path

from app.voice.base import EngineStatus, SynthesizedAudio, TextToSpeech, VoiceEngineError

log = logging.getLogger(__name__)

PIPER_VOICES = {
    "es_AR-daniela-high": ("Daniela (Argentina)", 110),
    "es_MX-claude-high": ("Claude (México)", 110),
    "es_ES-davefx-medium": ("Davefx (España)", 60),
}
_VOICE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(x_low|low|medium|high)$")


class PiperTTS(TextToSpeech):
    def __init__(self, models_dir: Path, voice: str = "es_AR-daniela-high") -> None:
        if not _VOICE_RE.match(voice):
            raise ValueError(f"Nombre de voz inválido: {voice}")
        self.voice = voice
        self.models_dir = models_dir / "piper"
        self._voice = None
        self._lock = threading.Lock()

    @property
    def model_path(self) -> Path:
        return self.models_dir / f"{self.voice}.onnx"

    @staticmethod
    def installed() -> bool:
        try:
            import piper  # noqa: F401
        except Exception:  # noqa: BLE001
            return False
        return True

    def model_ready(self) -> bool:
        return self.model_path.is_file() and Path(f"{self.model_path}.json").is_file()

    def status(self) -> EngineStatus:
        installed = self.installed()
        ready = self.model_ready()
        label, size = PIPER_VOICES.get(self.voice, (self.voice, 100))
        if not installed:
            detail = "Falta instalar el paquete de voz (scripts\\install.ps1)."
        elif not ready:
            detail = "Voz no descargada."
        else:
            detail = "Lista (local, sin conexión)."
        return EngineStatus(id="piper", kind="tts", name=f"Piper · {label}", installed=installed, model=self.voice,
                            model_ready=ready, model_size_mb=size, detail=detail)

    def download(self) -> None:
        if not self.installed():
            raise VoiceEngineError("El paquete piper-tts no está instalado.", code="voice_not_installed")
        from piper.download_voices import download_voice

        self.models_dir.mkdir(parents=True, exist_ok=True)
        download_voice(self.voice, self.models_dir)

    def warm(self) -> None:
        with self._lock:
            self._load()

    def _load(self):  # type: ignore[no-untyped-def]
        if self._voice is None:
            if not self.installed():
                raise VoiceEngineError("La síntesis de voz local no está instalada.", code="voice_not_installed")
            if not self.model_ready():
                raise VoiceEngineError("La voz no está descargada.", code="voice_model_missing")
            from piper import PiperVoice

            log.info("Cargando voz Piper %s", self.voice)
            self._voice = PiperVoice.load(str(self.model_path))
        return self._voice

    def synthesize(self, text: str, language: str) -> SynthesizedAudio:
        with self._lock:
            voice = self._load()
            buf = io.BytesIO()
            try:
                with wave.open(buf, "wb") as wav:
                    voice.synthesize_wav(text, wav)
            except Exception as e:  # noqa: BLE001
                log.exception("Error de síntesis")
                raise VoiceEngineError("No se pudo generar el audio.", code="tts_failed", status_code=500) from e
            rate = int(voice.config.sample_rate)
        return SynthesizedAudio(data=buf.getvalue(), mime_type="audio/wav", sample_rate=rate, engine="piper")
