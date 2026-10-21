from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import client_id, get_ctx, get_db
from app.core.context import AppContext
from app.core.errors import KaiError
from app.core.state import AssistantState
from app.security.access import RateLimiter
from app.security.audit import audit
from app.services.settings_service import get_preferences
from app.voice.base import EngineStatus, clean_for_speech
from app.voice.service import VoiceService

router = APIRouter(prefix="/voice", tags=["voice"])
Ctx = Annotated[AppContext, Depends(get_ctx)]
Db = Annotated[Session, Depends(get_db)]

MAX_AUDIO_BYTES = 15 * 1024 * 1024
_limiter = RateLimiter(limit=120)


def get_voice(request: Request) -> VoiceService:
    return request.app.state.voice


Voice = Annotated[VoiceService, Depends(get_voice)]


class EngineOut(BaseModel):
    id: str
    kind: str
    name: str
    installed: bool
    model: str
    model_ready: bool
    model_size_mb: int
    detail: str


def _engine_out(s: EngineStatus) -> EngineOut:
    return EngineOut(**s.__dict__)


class VoiceStatus(BaseModel):
    stt: EngineOut
    tts: EngineOut
    downloads: dict[str, dict]
    preferences: dict
    privacy: str


class SynthesizeIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    language: str | None = Field(default=None, max_length=16)


class TranscriptOut(BaseModel):
    text: str
    language: str
    duration_seconds: float
    engine: str


class ClientStateIn(BaseModel):
    state: Literal["listening", "speaking", "idle"]


def _check_rate(request: Request) -> None:
    if not _limiter.check(client_id(request)):
        raise KaiError("Demasiadas solicitudes de voz por minuto.", code="rate_limited", status_code=429)


@router.get("/status", response_model=VoiceStatus, summary="Motores de voz, modelos y preferencias")
def voice_status(voice: Voice, db: Db) -> VoiceStatus:
    p = get_preferences(db)
    voice.warm(p.whisper_model, p.piper_voice)
    return VoiceStatus(
        stt=_engine_out(voice.stt(p.whisper_model).status()),
        tts=_engine_out(voice.tts(p.piper_voice).status()),
        downloads=voice.downloads,
        preferences={k: v for k, v in p.model_dump().items() if k.startswith(("voice_", "whisper_", "piper_"))}
        | {"language": p.language},
        privacy="El audio se procesa en memoria en este equipo y nunca se guarda.",
    )


@router.post("/models/{kind}/download", status_code=202, summary="Descargar el modelo de voz (stt o tts)")
async def download_model(kind: Literal["stt", "tts"], request: Request, voice: Voice, db: Db) -> dict:
    p = get_preferences(db)
    result = voice.start_download(kind, p.whisper_model, p.piper_voice)
    audit(db, "voice.model.download", target=kind, details={"model": result.get("model")}, client=client_id(request))
    return result


@router.post("/transcribe", response_model=TranscriptOut, summary="Voz a texto (motor local)")
async def transcribe(request: Request, ctx: Ctx, voice: Voice, db: Db, audio: UploadFile = File(...),
                     language: str | None = Form(default=None)) -> TranscriptOut:
    ctx.touch()
    _check_rate(request)
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise KaiError("El audio está vacío.", code="empty_audio", status_code=422)
    if len(data) > MAX_AUDIO_BYTES:
        raise KaiError("El audio supera los 15 MB.", code="audio_too_large", status_code=413)
    p = get_preferences(db)
    ctx.state.begin(AssistantState.PROCESSING, "Transcribiendo")
    try:
        t = await voice.transcribe(p.whisper_model, data, language or p.language)
    finally:
        ctx.state.end()
    return TranscriptOut(text=t.text, language=t.language, duration_seconds=t.duration_seconds, engine=t.engine)


@router.post("/synthesize", summary="Texto a voz (WAV, motor local)",
             responses={200: {"content": {"audio/wav": {}}}})
async def synthesize(body: SynthesizeIn, request: Request, ctx: Ctx, voice: Voice, db: Db) -> Response:
    ctx.touch()
    _check_rate(request)
    text = clean_for_speech(body.text)
    if not text:
        raise KaiError("No hay texto para leer.", code="empty_text", status_code=422)
    p = get_preferences(db)
    ctx.state.begin(AssistantState.PROCESSING, "Generando voz")
    try:
        audio = await voice.synthesize(p.piper_voice, text, body.language or p.language)
    finally:
        ctx.state.end()
    return Response(content=audio.data, media_type=audio.mime_type, headers={"Cache-Control": "no-store"})


@router.post("/state", summary="La interfaz informa que está escuchando o hablando")
def client_state(body: ClientStateIn, ctx: Ctx) -> dict:
    ctx.state.set_client_state(None if body.state == "idle" else AssistantState(body.state))
    return ctx.state.snapshot()
