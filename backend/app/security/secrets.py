"""Almacenamiento seguro de la clave de API.

Orden de resolución:
1. Variable de entorno `ANTHROPIC_API_KEY` (o `.env`).
2. Almacén de credenciales del sistema operativo vía `keyring`
   (en Windows: Administrador de credenciales de Windows).
3. Memoria del proceso (sólo si no hay un almacén seguro disponible; se pierde al reiniciar).

La clave nunca se guarda en la base de datos ni en texto plano en disco, y la API
nunca la devuelve: sólo informa si existe y de dónde proviene.
"""

from __future__ import annotations

import logging
from typing import Literal

log = logging.getLogger(__name__)

SERVICE_NAME = "kai-ai"
KEY_NAME = "anthropic_api_key"

KeySource = Literal["env", "keyring", "memory", "none"]


class SecretStore:
    def __init__(self, env_key: str | None, use_keyring: bool = True) -> None:
        self._env_key = env_key.strip() if env_key else None
        self._memory_key: str | None = None
        self._keyring = None
        if use_keyring:
            try:
                import keyring
                from keyring.backends import fail

                backend = keyring.get_keyring()
                if not isinstance(backend, fail.Keyring) and getattr(backend, "priority", 0) > 0:
                    self._keyring = keyring
                else:
                    log.warning("No hay un almacén de credenciales seguro disponible en este sistema")
            except Exception as e:  # noqa: BLE001
                log.warning("keyring no disponible: %s", e)

    @property
    def keyring_available(self) -> bool:
        return self._keyring is not None

    def get_api_key(self) -> tuple[str | None, KeySource]:
        if self._env_key:
            return self._env_key, "env"
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(SERVICE_NAME, KEY_NAME)
                if value:
                    return value, "keyring"
            except Exception as e:  # noqa: BLE001
                log.error("No se pudo leer el almacén de credenciales: %s", e)
        if self._memory_key:
            return self._memory_key, "memory"
        return None, "none"

    def set_api_key(self, value: str) -> KeySource:
        value = value.strip()
        if self._keyring is not None:
            self._keyring.set_password(SERVICE_NAME, KEY_NAME, value)
            self._memory_key = None
            return "keyring"
        self._memory_key = value
        return "memory"

    def delete_api_key(self) -> None:
        self._memory_key = None
        if self._keyring is not None:
            try:
                self._keyring.delete_password(SERVICE_NAME, KEY_NAME)
            except Exception:  # noqa: BLE001 - no existía
                pass


def mask_key(key: str | None) -> str | None:
    if not key:
        return None
    return f"{key[:7]}…{key[-4:]}" if len(key) > 14 else "***"
