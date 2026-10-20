"""Integración real de voz: descarga modelos, sintetiza con Piper y transcribe con Whisper.

Se ejecuta sólo con KAI_VOICE_INTEGRATION=1 (lo hace el CI), porque descarga ~185 MB.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

import pytest

from app.voice.piper_tts import PiperTTS
from app.voice.whisper_stt import WhisperSTT

pytestmark = pytest.mark.skipif(os.environ.get("KAI_VOICE_INTEGRATION") != "1",
                                reason="Integración de voz desactivada (KAI_VOICE_INTEGRATION=1 para activarla)")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum() or c == " ")


def test_roundtrip_piper_to_whisper(tmp_path: Path):
    models = Path(os.environ.get("KAI_VOICE_MODELS_DIR", tmp_path))
    tts = PiperTTS(models, "es_AR-daniela-high")
    stt = WhisperSTT(models, "small")
    if not tts.model_ready():
        tts.download()
    if not stt.model_ready():
        stt.download()
    assert tts.status().model_ready and stt.status().model_ready

    audio = tts.synthesize("Hola, ¿qué tareas tengo pendientes para mañana?", "es-AR")
    assert audio.mime_type == "audio/wav" and len(audio.data) > 20_000

    t = stt.transcribe(audio.data, "es-AR")
    text = _norm(t.text)
    print("Transcripción:", t.text)
    assert t.language == "es" and t.duration_seconds > 1
    assert "tareas" in text and "manana" in text
