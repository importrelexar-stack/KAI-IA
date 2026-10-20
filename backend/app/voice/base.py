"""Abstracciones del sistema de voz (implementación en la Fase 2).

Pipeline previsto: micrófono → captura → SpeechToText → KAI Core → Claude →
TextToSpeech → altavoces. Estas interfaces existen para que los motores (locales
o en la nube) se puedan enchufar sin cambiar KAI Core. Todavía no hay ningún
motor implementado ni endpoint de voz expuesto, y nunca se grabará audio de
forma permanente sin consentimiento explícito.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int = 16_000
    channels: int = 1
    sample_width: int = 2  # bytes (PCM16)


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    is_final: bool
    confidence: float | None = None


class SpeechToText(ABC):
    @abstractmethod
    def transcribe_stream(self, audio: AsyncIterator[bytes], fmt: AudioFormat,
                          language: str = "es-AR") -> AsyncIterator[Transcript]: ...


class TextToSpeech(ABC):
    @abstractmethod
    def synthesize_stream(self, text: str, language: str = "es-AR", voice: str | None = None) -> AsyncIterator[bytes]: ...


class WakeWordDetector(ABC):
    """Detección local de «Hey KAI». Sólo se activa con consentimiento explícito."""

    @abstractmethod
    async def wait_for_wake_word(self, audio: AsyncIterator[bytes], fmt: AudioFormat) -> bool: ...
