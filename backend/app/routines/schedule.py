"""Horarios de las rutinas, en la hora local de la PC donde corre KAI.

Formatos (validados con Pydantic):
- {"type": "daily", "time": "08:00"}
- {"type": "weekly", "days": [0, 2, 4], "time": "08:00"}   (0 = lunes … 6 = domingo)
- {"type": "interval", "minutes": 120}                       (mínimo 15 minutos)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Timed(_Base):
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM (hora local)")

    def at(self) -> time:
        h, m = self.time.split(":")
        return time(int(h), int(m))


class Daily(_Timed):
    type: Literal["daily"]


class Weekly(_Timed):
    type: Literal["weekly"]
    days: list[int] = Field(min_length=1, max_length=7)

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("Los días van de 0 (lunes) a 6 (domingo).")
        return sorted(set(v))


class Interval(_Base):
    type: Literal["interval"]
    minutes: int = Field(ge=15, le=7 * 24 * 60)


Schedule = Annotated[Daily | Weekly | Interval, Field(discriminator="type")]
_adapter: TypeAdapter[Daily | Weekly | Interval] = TypeAdapter(Schedule)


def parse(data: dict) -> Daily | Weekly | Interval:
    return _adapter.validate_python(data)


def next_run(schedule: Daily | Weekly | Interval, after: datetime, tz: tzinfo | None = None) -> datetime:
    """Próxima ejecución estrictamente posterior a `after` (aware), devuelta en UTC.

    Sin `tz` se usa la hora local del sistema (respeta el horario de verano); con `tz` (p. ej. ZoneInfo)
    se calcula en esa zona.
    """
    if isinstance(schedule, Interval):
        return (after + timedelta(minutes=schedule.minutes)).astimezone(timezone.utc)
    allowed = set(range(7)) if isinstance(schedule, Daily) else set(schedule.days)
    if tz is not None:
        local = after.astimezone(tz)
        to_utc = lambda naive: naive.replace(tzinfo=tz).astimezone(timezone.utc)  # noqa: E731
    else:
        local = datetime.fromtimestamp(after.timestamp())  # hora local ingenua del sistema
        to_utc = lambda naive: datetime.fromtimestamp(naive.timestamp(), timezone.utc)  # noqa: E731
    base = local.replace(tzinfo=None)
    for offset in range(0, 8):
        day = (base + timedelta(days=offset)).date()
        if day.weekday() not in allowed:
            continue
        candidate = to_utc(datetime.combine(day, schedule.at()))
        if candidate > after:
            return candidate
    raise ValueError("Horario sin próximas ejecuciones")  # no debería ocurrir


def describe(schedule: Daily | Weekly | Interval) -> str:
    if isinstance(schedule, Interval):
        m = schedule.minutes
        return f"cada {m // 60} h" + (f" {m % 60} min" if m % 60 else "") if m >= 60 else f"cada {m} min"
    if isinstance(schedule, Daily):
        return f"todos los días a las {schedule.time}"
    if schedule.days == [0, 1, 2, 3, 4]:
        return f"de lunes a viernes a las {schedule.time}"
    return ", ".join(DAY_NAMES[d] for d in schedule.days) + f" a las {schedule.time}"
