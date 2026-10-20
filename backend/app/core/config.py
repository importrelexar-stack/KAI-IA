"""Configuración de KAI Core.

Toda la configuración sale de variables de entorno (o de un archivo `.env`).
Las preferencias que el usuario cambia desde la interfaz (modelo, esfuerzo,
presupuesto, etc.) viven en la base de datos: ver `services/settings_service.py`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import os
import sys

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

# Empaquetado con PyInstaller (app de escritorio): los datos van a la carpeta del usuario
# y la interfaz viaja dentro del ejecutable.
FROZEN = bool(getattr(sys, "frozen", False))


def _user_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "KAI"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KAI"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "kai"


DEFAULT_DATA_DIR = _user_data_dir() if FROZEN else REPO_ROOT / "data"
DEFAULT_WEB_DIST = (Path(getattr(sys, "_MEIPASS", BACKEND_DIR)) / "web") if FROZEN else REPO_ROOT / "apps" / "web" / "dist"
ENV_FILES = (str(DEFAULT_DATA_DIR / ".env"),) if FROZEN else (str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Servidor
    host: str = Field(default="127.0.0.1", alias="KAI_HOST")
    port: int = Field(default=8765, alias="KAI_PORT")
    log_level: str = Field(default="INFO", alias="KAI_LOG_LEVEL")
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "tauri://localhost",
            "http://tauri.localhost",
        ],
        alias="KAI_ALLOWED_ORIGINS",
    )

    # Datos
    data_dir: Path = Field(default=DEFAULT_DATA_DIR, alias="KAI_DATA_DIR")
    web_dist: Path = Field(default=DEFAULT_WEB_DIST, alias="KAI_WEB_DIST")

    # IA
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    demo_mode: bool = Field(default=False, alias="KAI_DEMO_MODE")

    # Seguridad
    chat_rate_limit_per_minute: int = Field(default=20, alias="KAI_CHAT_RATE_LIMIT")
    max_upload_mb: int = Field(default=25, alias="KAI_MAX_UPLOAD_MB")
    use_keyring: bool = Field(default=True, alias="KAI_USE_KEYRING")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def effective_origins(self) -> list[str]:
        """Orígenes permitidos + la propia interfaz servida por KAI Core en el puerto configurado."""
        own = [f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"]
        return list(dict.fromkeys([*self.allowed_origins, *own]))

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'kai.db').as_posix()}"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def cowork_dir(self) -> Path:
        return self.data_dir / "cowork"

    @property
    def voice_models_dir(self) -> Path:
        return self.data_dir / "voice-models"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.logs_dir, self.cowork_dir, self.voice_models_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
