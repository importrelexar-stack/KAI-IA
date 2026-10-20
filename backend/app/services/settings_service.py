"""Lectura y escritura de preferencias del usuario."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import SettingEntry
from app.schemas.settings import Preferences, PreferencesUpdate

_KEY = "preferences"


def get_preferences(db: Session) -> Preferences:
    row = db.get(SettingEntry, _KEY)
    if row is None or not isinstance(row.value, dict):
        return Preferences()
    try:
        return Preferences.model_validate({**Preferences().model_dump(), **row.value})
    except ValueError:
        # Si quedó un valor inválido (p. ej. un modelo retirado), se vuelve a los valores por defecto.
        return Preferences()


def update_preferences(db: Session, update: PreferencesUpdate) -> tuple[Preferences, list[str]]:
    current = get_preferences(db)
    changes = update.model_dump(exclude_none=True)
    merged = Preferences.model_validate({**current.model_dump(), **changes})
    row = db.get(SettingEntry, _KEY)
    if row is None:
        db.add(SettingEntry(key=_KEY, value=merged.model_dump()))
    else:
        row.value = merged.model_dump()
    db.commit()
    return merged, sorted(changes)
