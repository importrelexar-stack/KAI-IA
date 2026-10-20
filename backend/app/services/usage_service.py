"""Control de consumo de tokens (presupuesto diario)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BudgetExceededError
from app.models.entities import UsageRecord
from app.providers.base import Usage


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def record_usage(db: Session, model: str, usage: Usage) -> None:
    db.add(UsageRecord(day=today(), model=model, input_tokens=usage.input_tokens,
                       output_tokens=usage.output_tokens, cache_read_tokens=usage.cache_read_tokens))
    db.commit()


def usage_for_day(db: Session, day: str | None = None) -> dict[str, int]:
    day = day or today()
    row = db.execute(
        select(
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cache_read_tokens), 0),
            func.count(UsageRecord.id),
        ).where(UsageRecord.day == day)
    ).one()
    return {"input_tokens": int(row[0]), "output_tokens": int(row[1]), "cache_read_tokens": int(row[2]),
            "requests": int(row[3]), "total_tokens": int(row[0]) + int(row[1])}


def ensure_within_budget(db: Session, daily_budget: int) -> None:
    if daily_budget <= 0:
        return
    used = usage_for_day(db)["total_tokens"]
    if used >= daily_budget:
        raise BudgetExceededError(
            f"Se alcanzó el presupuesto diario de tokens ({used:,} / {daily_budget:,}). "
            "Podés ampliarlo en Configuración o esperar al próximo día (UTC)."
        )
