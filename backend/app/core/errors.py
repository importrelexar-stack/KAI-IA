"""Errores de dominio con mensajes comprensibles para el usuario."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class KaiError(Exception):
    status_code = 400
    code = "kai_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(KaiError):
    status_code = 404
    code = "not_found"


class ProviderNotConfiguredError(KaiError):
    status_code = 503
    code = "provider_not_configured"


class ProviderError(KaiError):
    status_code = 502
    code = "provider_error"


class BudgetExceededError(KaiError):
    status_code = 429
    code = "budget_exceeded"


class InvalidTransitionError(KaiError):
    status_code = 409
    code = "invalid_transition"


async def kai_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, KaiError)
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})
