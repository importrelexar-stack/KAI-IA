"""Proveedor Anthropic Claude (SDK oficial `anthropic`).

Importante: una suscripción Claude Pro/Max NO da acceso a la API. Esta
integración necesita una clave de API de https://console.anthropic.com con
facturación propia.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import anthropic

from app.core.errors import ProviderError, ProviderNotConfiguredError
from app.providers.base import (
    AIProvider,
    ChatTurn,
    Completed,
    GenerationOptions,
    ProviderEvent,
    TextDelta,
    Usage,
    ValidationResult,
)

log = logging.getLogger(__name__)

# Modelos ofrecidos en la interfaz. Todos aceptan `output_config.effort`.
SUPPORTED_MODELS: dict[str, str] = {
    "claude-opus-5-5": "Claude Opus 5.5 (recomendado)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (más económico)",
    "claude-haiku-5-5": "Claude Haiku 5.5 (el más rápido y barato)",
    "claude-fable-5-1": "Claude Fable 5.1 (máxima capacidad, más caro)",
}
DEFAULT_MODEL = "claude-opus-5-5"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# Modelos que aceptan el reintento automático en servidor (`fallbacks: "default"`)
# cuando un clasificador de seguridad rechaza la solicitud.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, *, timeout: float = 120.0, max_retries: int = 2) -> None:
        self._api_key = api_key
        self._client = (
            anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)
            if api_key
            else None
        )
        self._minimal_requests = False

    @property
    def configured(self) -> bool:
        return self._client is not None

    def _require_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            raise ProviderNotConfiguredError(
                "No hay una clave de API de Anthropic configurada. El chat real no está disponible: "
                "cargá la clave en Configuración o definí ANTHROPIC_API_KEY."
            )
        return self._client

    async def stream_chat(
        self, *, system: str, turns: list[ChatTurn], options: GenerationOptions
    ) -> AsyncIterator[ProviderEvent]:
        client = self._require_client()
        kwargs: dict = {
            "model": options.model,
            "max_tokens": options.max_tokens,
            "system": system,
            "messages": [{"role": t.role, "content": t.content} for t in turns],
            # Caché automático del prefijo (system + historial) para bajar costos.
            "cache_control": {"type": "ephemeral"},
        }
        if options.effort:
            kwargs["output_config"] = {"effort": options.effort}
        if options.use_fallbacks and options.model in _FALLBACK_MODELS and not self._minimal_requests:
            kwargs["betas"] = [_FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        if self._minimal_requests:
            kwargs.pop("cache_control", None)

        final = None
        emitted = False
        for attempt in (1, 2):
            try:
                async with client.beta.messages.stream(**kwargs) as stream:
                    async for text in stream.text_stream:
                        if text:
                            emitted = True
                            yield TextDelta(text=text)
                    final = await stream.get_final_message()
                break
            except anthropic.BadRequestError as e:
                # Si la API rechaza una función opcional (reintento en servidor o caché),
                # se reintenta una vez sin ellas y se recuerda para las próximas solicitudes.
                optional = [k for k in ("fallbacks", "betas", "cache_control") if k in kwargs]
                if attempt == 1 and optional and not emitted:
                    log.warning("Anthropic rechazó funciones opcionales (%s); se reintenta sin ellas: %s",
                                ", ".join(optional), _api_message(e))
                    for k in optional:
                        kwargs.pop(k)
                    self._minimal_requests = True
                    continue
                raise ProviderError(f"Solicitud rechazada por Anthropic: {_api_message(e)}",
                                    code="bad_request", status_code=400) from e
            except anthropic.AuthenticationError as e:
                raise ProviderError("La clave de API fue rechazada por Anthropic (401). Revisala en Configuración.",
                                    code="auth_failed", status_code=401) from e
            except anthropic.PermissionDeniedError as e:
                raise ProviderError("La clave no tiene permiso para este modelo o recurso (403).",
                                    code="permission_denied", status_code=403) from e
            except anthropic.NotFoundError as e:
                raise ProviderError(f"El modelo '{options.model}' no existe o no está disponible para tu cuenta.",
                                    code="model_not_found", status_code=404) from e
            except anthropic.RateLimitError as e:
                raise ProviderError("Anthropic limitó las solicitudes (429). Esperá unos segundos y reintentá.",
                                    code="rate_limited", status_code=429) from e
            except anthropic.APIStatusError as e:
                raise ProviderError(f"Error del servicio de Anthropic ({e.status_code}). Reintentá más tarde.",
                                    code="upstream_error", status_code=502) from e
            except anthropic.APITimeoutError as e:
                raise ProviderError("Se agotó el tiempo de espera con Anthropic.", code="timeout",
                                    status_code=504) from e
            except anthropic.APIConnectionError as e:
                raise ProviderError("No se pudo conectar con Anthropic. Revisá tu conexión a Internet o proxy.",
                                    code="connection_error", status_code=503) from e
        assert final is not None

        usage = Usage(
            input_tokens=getattr(final.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(final.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(final.usage, "cache_read_input_tokens", 0) or 0,
        )
        iterations = getattr(final.usage, "iterations", None) or []
        served_by_fallback = any(getattr(it, "type", None) == "fallback_message" for it in iterations)
        if final.stop_reason == "refusal":
            log.info("Claude rechazó la solicitud por política de seguridad")
        yield Completed(model=final.model, stop_reason=final.stop_reason, usage=usage,
                        served_by_fallback=served_by_fallback)

    async def validate(self) -> ValidationResult:
        """Verifica la clave listando modelos (no consume tokens)."""
        try:
            client = self._require_client()
            page = await client.models.list(limit=5)
            ids = [m.id for m in page.data]
            return ValidationResult(ok=True, message=f"Clave válida. Modelos visibles: {', '.join(ids) or 'ninguno'}")
        except ProviderNotConfiguredError as e:
            return ValidationResult(ok=False, message=e.message)
        except anthropic.AuthenticationError:
            return ValidationResult(ok=False, message="Clave inválida (401).")
        except anthropic.APIConnectionError:
            return ValidationResult(ok=False, message="No se pudo conectar con Anthropic.")
        except anthropic.APIStatusError as e:
            return ValidationResult(ok=False, message=f"Anthropic respondió {e.status_code}.")


def _api_message(e: anthropic.APIStatusError) -> str:
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
    return str(e)
