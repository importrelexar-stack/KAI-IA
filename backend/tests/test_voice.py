"""Pruebas del sistema de voz con motores simulados (sin modelos ni micrófono)."""

from __future__ import annotations

import io
import time
import wave

import pytest

from app.voice.base import (
    EngineStatus,
    SpeechToText,
    SynthesizedAudio,
    TextToSpeech,
    Transcript,
    VoiceEngineError,
    clean_for_speech,
    language_code,
)
from app.voice.piper_tts import PiperTTS
from app.voice.service import VoiceService
from app.voice.whisper_stt import WhisperSTT
from tests.conftest import parse_sse


def _wav(seconds: float = 0.2, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeSTT(SpeechToText):
    def __init__(self, ready: bool = True, text: str = "hola kai") -> None:
        self.ready, self.text, self.calls, self.downloaded = ready, text, [], False

    def status(self) -> EngineStatus:
        return EngineStatus("whisper", "stt", "Fake STT", True, "base", self.ready, 145, "ok")

    def download(self) -> None:
        time.sleep(0.05)
        self.ready = self.downloaded = True

    def transcribe(self, audio: bytes, language: str) -> Transcript:
        if not self.ready:
            raise VoiceEngineError("El modelo de reconocimiento de voz no está descargado.", code="voice_model_missing")
        self.calls.append((len(audio), language))
        return Transcript(self.text, "es", 1.5, "fake")


class FakeTTS(TextToSpeech):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def status(self) -> EngineStatus:
        return EngineStatus("piper", "tts", "Fake TTS", True, "es_AR-daniela-high", True, 110, "ok")

    def download(self) -> None:
        pass

    def synthesize(self, text: str, language: str) -> SynthesizedAudio:
        self.texts.append(text)
        return SynthesizedAudio(_wav(), "audio/wav", 16000, "fake")


@pytest.fixture
def voice_client(client):
    svc: VoiceService = client.app.state.voice
    stt, tts = FakeSTT(), FakeTTS()
    svc.make_stt = lambda size: stt  # type: ignore[method-assign]
    svc.make_tts = lambda voice: tts  # type: ignore[method-assign]
    return client, stt, tts


def test_status_reports_engines_and_privacy(voice_client):
    client, _, _ = voice_client
    s = client.get("/api/v1/voice/status").json()
    assert s["stt"]["model_ready"] is True and s["tts"]["model"] == "es_AR-daniela-high"
    assert s["preferences"]["voice_handsfree_consent"] is False
    assert s["preferences"]["language"] == "es-AR"
    assert "nunca se guarda" in s["privacy"]


def test_transcribe(voice_client):
    client, stt, _ = voice_client
    r = client.post("/api/v1/voice/transcribe", files={"audio": ("a.webm", b"\x1aE\xdf\xa3fake", "audio/webm")})
    assert r.status_code == 200, r.text
    assert r.json() == {"text": "hola kai", "language": "es", "duration_seconds": 1.5, "engine": "fake"}
    assert stt.calls == [(8, "es-AR")]
    assert client.get("/api/v1/health").json()["assistant"]["state"] == "idle"


def test_transcribe_validations(voice_client):
    client, stt, _ = voice_client
    assert client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", b"", "audio/wav")}).status_code == 422
    big = b"0" * (15 * 1024 * 1024 + 1)
    assert client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", big, "audio/wav")}).status_code == 413
    stt.ready = False
    r = client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", _wav(), "audio/wav")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "voice_model_missing"


def test_synthesize_cleans_markdown(voice_client):
    client, _, tts = voice_client
    r = client.post("/api/v1/voice/synthesize", json={"text": "**Hola** ver [docs](https://x.y)\n\n- uno\n- dos"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getframerate() == 16000
    assert tts.texts == ["Hola ver docs. uno, dos"]
    assert client.post("/api/v1/voice/synthesize", json={"text": "***"}).status_code == 422


def test_download_runs_in_background(voice_client):
    client, _, _ = voice_client
    svc: VoiceService = client.app.state.voice
    stt = FakeSTT(ready=False)
    svc.make_stt = lambda size: stt  # type: ignore[method-assign]
    svc._stt = None
    with client.websocket_connect("/api/v1/ws/events") as ws:
        ws.receive_json()
        r = client.post("/api/v1/voice/models/stt/download")
        assert r.status_code == 202 and r.json()["state"] == "downloading"
        events = [ws.receive_json(), ws.receive_json()]
    downloads = [e for e in events if e["type"] == "voice_download"]
    assert downloads[-1]["state"] == "done" and stt.downloaded
    assert client.get("/api/v1/voice/status").json()["stt"]["model_ready"] is True
    assert "voice.model.download" in [a["action"] for a in client.get("/api/v1/audit").json()]


def test_client_state_listening_and_speaking(voice_client):
    client, _, _ = voice_client
    assert client.post("/api/v1/voice/state", json={"state": "listening"}).json()["state"] == "listening"
    # Mientras transcribe, el estado real es "processing" y luego vuelve a "listening"
    client.post("/api/v1/voice/transcribe", files={"audio": ("a.wav", _wav(), "audio/wav")})
    assert client.get("/api/v1/health").json()["assistant"]["state"] == "listening"
    assert client.post("/api/v1/voice/state", json={"state": "speaking"}).json()["state"] == "speaking"
    assert client.post("/api/v1/voice/state", json={"state": "idle"}).json()["state"] == "idle"
    assert client.post("/api/v1/voice/state", json={"state": "error"}).status_code == 422


def test_voice_preferences(client):
    r = client.put("/api/v1/settings", json={"whisper_model": "small", "piper_voice": "es_MX-claude-high",
                                              "voice_handsfree_consent": True})
    assert r.status_code == 200
    s = client.get("/api/v1/voice/status").json()
    assert s["stt"]["model"] == "small" and s["tts"]["model"] == "es_MX-claude-high"
    assert client.put("/api/v1/settings", json={"whisper_model": "huge"}).status_code == 422
    assert client.put("/api/v1/settings", json={"piper_voice": "../../evil"}).status_code == 422


def test_voice_channel_changes_system_prompt(client, providers):
    client.post("/api/v1/chat", json={"message": "hola", "stream": False, "channel": "voice"})
    assert "se va a leer en voz alta" in providers[-1].calls[-1]["system"]
    events = parse_sse(client.post("/api/v1/chat", json={"message": "hola"}).text)
    assert events[-1]["type"] == "done"
    assert "se va a leer en voz alta" not in providers[-1].calls[-1]["system"]


def test_clean_for_speech():
    assert clean_for_speech("# Título\n\nTexto con `code` y ```py\nx=1\n```") == \
        "Título. Texto con code y (te dejé el código en pantalla)"
    assert "https" not in clean_for_speech("mirá https://example.com/a?b=1")
    assert len(clean_for_speech("Hola. " * 2000, max_chars=100)) <= 100
    assert clean_for_speech("usá _énfasis_ y KAI_DEMO_MODE") == "usá énfasis y KAI_DEMO_MODE"
    assert language_code("es-AR") == "es" and language_code("pt_BR") == "pt" and language_code("") == "es"


def test_real_engines_report_missing_models(tmp_path):
    stt = WhisperSTT(tmp_path, "tiny")
    st = stt.status()
    assert st.model_ready is False and st.model_size_mb == 75
    if st.installed:
        with pytest.raises(VoiceEngineError) as e:
            stt.transcribe(_wav(), "es-AR")
        assert e.value.code == "voice_model_missing"
    tts = PiperTTS(tmp_path)
    assert tts.status().model_ready is False and tts.model_path.name == "es_AR-daniela-high.onnx"
    with pytest.raises(ValueError):
        PiperTTS(tmp_path, "../../x")
    with pytest.raises(ValueError):
        WhisperSTT(tmp_path, "gigante")


def test_decode_audio_wav_and_compressed():
    np = pytest.importorskip("numpy")
    av = pytest.importorskip("av")
    from app.voice.whisper_stt import decode_audio

    rate = 48000
    sig = (0.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.stack([sig, sig], 1).reshape(-1).tobytes())
    pcm = decode_audio(buf.getvalue())
    assert pcm.dtype == np.float32 and len(pcm) == 16000 and 0.45 < abs(pcm).max() < 0.55

    out = io.BytesIO()
    with av.open(out, "w", format="ogg") as c:
        stream = c.add_stream("libopus", rate=48000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(sig.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        for p in stream.encode(frame):
            c.mux(p)
        for p in stream.encode(None):
            c.mux(p)
    pcm = decode_audio(out.getvalue())
    assert 15000 <= len(pcm) <= 17000
