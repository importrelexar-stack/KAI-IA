"""Servicio de voz: elige motores según las preferencias, descarga modelos y ejecuta
STT/TTS fuera del bucle de eventos."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from app.core.state import EventBus
from app.voice.base import SpeechToText, SynthesizedAudio, TextToSpeech, Transcript, VoiceEngineError
from app.voice.piper_tts import PiperTTS
from app.voice.whisper_stt import WhisperSTT

log = logging.getLogger(__name__)

Kind = Literal["stt", "tts"]


class VoiceService:
    def __init__(self, models_dir: Path, bus: EventBus) -> None:
        self.models_dir = models_dir
        self._bus = bus
        self._stt: SpeechToText | None = None
        self._stt_key: str | None = None
        self._tts: TextToSpeech | None = None
        self._tts_key: str | None = None
        self.downloads: dict[str, dict[str, Any]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # Fábricas reemplazables en pruebas
    def make_stt(self, model_size: str) -> SpeechToText:
        return WhisperSTT(self.models_dir, model_size)

    def make_tts(self, voice: str) -> TextToSpeech:
        return PiperTTS(self.models_dir, voice)

    def stt(self, model_size: str) -> SpeechToText:
        if self._stt is None or self._stt_key != model_size:
            self._stt, self._stt_key = self.make_stt(model_size), model_size
        return self._stt

    def tts(self, voice: str) -> TextToSpeech:
        if self._tts is None or self._tts_key != voice:
            self._tts, self._tts_key = self.make_tts(voice), voice
        return self._tts

    def engine(self, kind: Kind, model_size: str, voice: str) -> SpeechToText | TextToSpeech:
        return self.stt(model_size) if kind == "stt" else self.tts(voice)

    async def transcribe(self, model_size: str, audio: bytes, language: str) -> Transcript:
        return await asyncio.to_thread(self.stt(model_size).transcribe, audio, language)

    async def synthesize(self, voice: str, text: str, language: str) -> SynthesizedAudio:
        return await asyncio.to_thread(self.tts(voice).synthesize, text, language)

    def start_download(self, kind: Kind, model_size: str, voice: str) -> dict[str, Any]:
        engine = self.engine(kind, model_size, voice)
        st = engine.status()
        if not st.installed:
            raise VoiceEngineError("Primero hay que instalar los paquetes de voz (scripts\\install.ps1).",
                                   code="voice_not_installed")
        current = self.downloads.get(kind)
        if current and current["state"] == "downloading":
            return current
        if st.model_ready:
            self.downloads[kind] = {"state": "done", "model": st.model}
            return self.downloads[kind]

        self.downloads[kind] = {"state": "downloading", "model": st.model, "size_mb": st.model_size_mb}
        self._bus.publish({"type": "voice_download", "kind": kind, **self.downloads[kind]})

        async def _run() -> None:
            try:
                await asyncio.to_thread(engine.download)
                self.downloads[kind] = {"state": "done", "model": st.model}
            except Exception as e:  # noqa: BLE001
                log.exception("Falló la descarga del modelo de voz %s", st.model)
                msg = e.message if isinstance(e, VoiceEngineError) else f"{type(e).__name__}: {e}"
                self.downloads[kind] = {"state": "error", "model": st.model,
                                        "error": f"No se pudo descargar el modelo ({msg}). Revisá tu conexión."}
            self._bus.publish({"type": "voice_download", "kind": kind, **self.downloads[kind]})

        task = asyncio.get_running_loop().create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return self.downloads[kind]
