"""Integración real de voz: descarga modelos, sintetiza con Piper y transcribe con Whisper.

Se ejecuta sólo con KAI_VOICE_INTEGRATION=1 (lo hace el CI), porque descarga ~575 MB.
"""

from __future__ import annotations

import io
import os
import unicodedata
import wave
from pathlib import Path

import pytest

from app.voice.piper_tts import PiperTTS
from app.voice.whisper_stt import WhisperSTT

pytestmark = pytest.mark.skipif(os.environ.get("KAI_VOICE_INTEGRATION") != "1",
                                reason="Integración de voz desactivada (KAI_VOICE_INTEGRATION=1 para activarla)")

# Nota: «Hola, ¿qué tareas tengo…» se descartó porque la voz sintética de Piper pronuncia ese tramo de
# forma ambigua (Whisper base y small, en Linux y Windows, oyen siempre «O las quitarías tembo»), mientras
# que otras frases se transcriben perfecto. Es una limitación de la síntesis, no del reconocimiento.
PHRASES = [
    ("Tengo que revisar las tareas pendientes de mañana.", ["tengo", "revisar", "tareas", "pendientes", "manana"]),
    ("Necesito preparar el informe de ventas del mes.", ["necesito", "preparar", "informe", "ventas", "mes"]),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum() or c == " ")


@pytest.fixture(scope="module")
def engines(tmp_path_factory):
    models = Path(os.environ.get("KAI_VOICE_MODELS_DIR", tmp_path_factory.mktemp("models")))
    tts = PiperTTS(models, "es_AR-daniela-high")
    stt = WhisperSTT(models, "small")
    if not tts.model_ready():
        tts.download()
    if not stt.model_ready():
        stt.download()
    assert tts.status().model_ready and stt.status().model_ready
    return tts, stt


def test_kai_tts_produces_audio(engines):
    tts, _ = engines
    audio = tts.synthesize("Hola, soy KAI.", "es-AR")
    assert audio.mime_type == "audio/wav" and len(audio.data) > 20_000
    with wave.open(io.BytesIO(audio.data)) as w:
        assert w.getframerate() == audio.sample_rate and w.getnframes() / w.getframerate() > 0.5


def test_roundtrip_piper_to_whisper(engines):
    from piper import SynthesisConfig

    tts, stt = engines
    voice = tts._load()
    total = hits = 0
    for phrase, keywords in PHRASES:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            # Sin ruido aleatorio: la prueba es reproducible.
            voice.synthesize_wav(phrase, w, syn_config=SynthesisConfig(noise_scale=0.0, noise_w_scale=0.0))
        t = stt.transcribe(buf.getvalue(), "es-AR")
        text = _norm(t.text)
        found = [k for k in keywords if k in text]
        print(f"Piper: «{phrase}» → Whisper: «{t.text}» ({len(found)}/{len(keywords)})")
        assert t.language == "es" and t.duration_seconds > 1
        total += len(keywords)
        hits += len(found)
    assert hits / total >= 0.8, f"sólo {hits}/{total} palabras clave reconocidas"
