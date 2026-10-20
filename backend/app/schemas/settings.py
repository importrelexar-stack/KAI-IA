from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.providers.anthropic_provider import DEFAULT_MODEL, EFFORT_LEVELS, SUPPORTED_MODELS


class Preferences(BaseModel):
    """Preferencias editables desde la interfaz (persisten en SQLite)."""

    model: str = DEFAULT_MODEL
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    max_tokens: int = Field(default=16000, ge=256, le=64000)
    history_window: int = Field(default=40, ge=2, le=200, description="Mensajes previos enviados como contexto")
    daily_token_budget: int = Field(default=500_000, ge=0, description="0 = sin límite")
    use_fallbacks: bool = True
    language: str = Field(default="es-AR", max_length=16)
    user_name: str = Field(default="", max_length=80)
    custom_instructions: str = Field(default="", max_length=4000)
    # Voz (Fase 2)
    voice_stt_engine: Literal["local", "browser"] = "local"
    voice_tts_engine: Literal["local", "browser"] = "local"
    whisper_model: Literal["tiny", "base", "small"] = "small"
    piper_voice: Literal["es_AR-daniela-high", "es_MX-claude-high", "es_ES-davefx-medium"] = "es_AR-daniela-high"
    voice_auto_speak: bool = True
    voice_handsfree_consent: bool = False
    # Memoria y agentes (Fase 3)
    memory_enabled: bool = True
    memory_auto_approve: bool = False
    agents_enabled: bool = True
    web_search_enabled: bool = False
    max_tool_iterations: int = Field(default=6, ge=1, le=15)

    @field_validator("model")
    @classmethod
    def _model_supported(cls, v: str) -> str:
        if v not in SUPPORTED_MODELS:
            raise ValueError(f"Modelo no soportado. Opciones: {', '.join(SUPPORTED_MODELS)}")
        return v


class PreferencesUpdate(BaseModel):
    model: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    max_tokens: int | None = Field(default=None, ge=256, le=64000)
    history_window: int | None = Field(default=None, ge=2, le=200)
    daily_token_budget: int | None = Field(default=None, ge=0)
    use_fallbacks: bool | None = None
    language: str | None = Field(default=None, max_length=16)
    user_name: str | None = Field(default=None, max_length=80)
    custom_instructions: str | None = Field(default=None, max_length=4000)
    voice_stt_engine: Literal["local", "browser"] | None = None
    voice_tts_engine: Literal["local", "browser"] | None = None
    whisper_model: Literal["tiny", "base", "small"] | None = None
    piper_voice: Literal["es_AR-daniela-high", "es_MX-claude-high", "es_ES-davefx-medium"] | None = None
    voice_auto_speak: bool | None = None
    voice_handsfree_consent: bool | None = None
    memory_enabled: bool | None = None
    memory_auto_approve: bool | None = None
    agents_enabled: bool | None = None
    web_search_enabled: bool | None = None
    max_tool_iterations: int | None = Field(default=None, ge=1, le=15)

    @field_validator("model")
    @classmethod
    def _model_supported(cls, v: str | None) -> str | None:
        return v if v is None else Preferences._model_supported(v)


class ApiKeyStatus(BaseModel):
    configured: bool
    source: Literal["env", "keyring", "memory", "none"]
    masked: str | None
    keyring_available: bool
    persisted: bool


class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=300)

    @field_validator("api_key")
    @classmethod
    def _looks_like_key(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("sk-ant-"):
            raise ValueError("La clave de API de Anthropic empieza con 'sk-ant-'.")
        if any(c.isspace() for c in v):
            raise ValueError("La clave no puede contener espacios.")
        return v


class SettingsOut(BaseModel):
    preferences: Preferences
    api_key: ApiKeyStatus
    demo_mode: bool
    models: dict[str, str] = SUPPORTED_MODELS
    effort_levels: tuple[str, ...] = EFFORT_LEVELS


class ValidationOut(BaseModel):
    ok: bool
    message: str
