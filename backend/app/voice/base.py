"""Abstracciones del sistema de voz.

Pipeline: micrófono (interfaz) → captura → SpeechToText → KAI Core → Claude →
TextToSpeech → altavoces (interfaz). Los motores son intercambiables: hoy hay
motores locales (faster-whisper y Piper) y la interfaz puede usar los del navegador.

Privacidad: el audio se procesa en memoria y nunca se guarda en disco ni en la base.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    duration_seconds: float
    engine: str


@dataclass(frozen=True)
class SynthesizedAudio:
    data: bytes
    mime_type: str
    sample_rate: int
    engine: str


@dataclass(frozen=True)
class EngineStatus:
    id: str
    kind: str  # stt | tts
    name: str
    installed: bool  # paquete de Python disponible
    model: str
    model_ready: bool  # modelo descargado
    model_size_mb: int
    detail: str


class VoiceEngineError(Exception):
    def __init__(self, message: str, code: str = "voice_error", status_code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class SpeechToText(ABC):
    @abstractmethod
    def status(self) -> EngineStatus: ...

    @abstractmethod
    def download(self) -> None:
        """Descarga el modelo (bloqueante; se ejecuta en un hilo)."""

    @abstractmethod
    def transcribe(self, audio: bytes, language: str) -> Transcript:
        """Transcribe audio (webm/ogg/wav/mp3…). Bloqueante; se ejecuta en un hilo."""


class TextToSpeech(ABC):
    @abstractmethod
    def status(self) -> EngineStatus: ...

    @abstractmethod
    def download(self) -> None: ...

    @abstractmethod
    def synthesize(self, text: str, language: str) -> SynthesizedAudio: ...


def language_code(language: str) -> str:
    """'es-AR' → 'es' (Whisper usa códigos ISO 639-1)."""
    return (language or "es").split("-")[0].split("_")[0].lower() or "es"


_CODE_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_MARKS = re.compile(r"[*#>|~]+|(?<!\w)_+|_+(?!\w)")
_BULLET = re.compile(r"^[ \t]*(?:[-+•]|\d+[.)])[ \t]+", re.M)


def clean_for_speech(text: str, max_chars: int = 4000) -> str:
    """Quita Markdown, bloques de código y URLs para que la lectura en voz alta sea natural."""
    text = _CODE_BLOCK.sub(" (te dejé el código en pantalla) ", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("el enlace en pantalla", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _BULLET.sub("", text)
    text = _MARKS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", ". ", text).replace("\n", ", ")
    text = re.sub(r"\s*([.,;:!?])(\s*[.,])+", r"\1", text).strip(" ,")
    if len(text) > max_chars:
        cut = text[:max_chars]
        text = cut[: cut.rfind(".") + 1] if "." in cut else cut
    return text.strip()
