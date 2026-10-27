"""Migraciones livianas de SQLite.

`create_all` crea tablas nuevas pero no agrega columnas a tablas existentes. Acá se
agregan las columnas incorporadas en fases posteriores, para que una base creada en
una versión anterior siga funcionando sin perder datos.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# (tabla, columna, definición SQL)
COLUMNS: list[tuple[str, str, str]] = [
    ("messages", "tool_events", "JSON DEFAULT '[]'"),
    ("tasks", "project_id", "VARCHAR(32)"),
    ("tasks", "depends_on", "JSON DEFAULT '[]'"),
    ("tasks", "created_by", "VARCHAR(16) DEFAULT 'user'"),
    ("tasks", "action", "JSON"),
    ("messages", "attachments", "JSON DEFAULT '[]'"),
]

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5("
    "memory_id UNINDEXED, content, tags, tokenize = 'unicode61 remove_diacritics 2')"
)


def run_migrations(engine: Engine) -> dict[str, bool]:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in COLUMNS:
            if table not in insp.get_table_names():
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column not in existing:
                log.info("Migración: agregando %s.%s", table, column)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    fts = True
    try:
        with engine.begin() as conn:
            conn.execute(text(FTS_DDL))
    except Exception as e:  # noqa: BLE001 - SQLite sin FTS5: se usa búsqueda simple
        log.warning("FTS5 no disponible (%s): la memoria usará búsqueda simple", e)
        fts = False
    return {"fts5": fts}
