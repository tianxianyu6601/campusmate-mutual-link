"""Database backend adapter for local SQLite and hosted PostgreSQL."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "campusmate_app.db"
DATABASE_URL_ENV = "CAMPUSMATE_DATABASE_URL"
FORCE_SQLITE_ENV = "CAMPUSMATE_FORCE_SQLITE"


def configured_database_url() -> str | None:
    if os.environ.get(FORCE_SQLITE_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return None
    env_value = os.environ.get(DATABASE_URL_ENV, "").strip()
    if env_value:
        return env_value
    try:
        secret_value = st.secrets.get("database_url", None)
    except Exception:
        return None
    value = str(secret_value).strip() if secret_value else ""
    return value or None


class DatabaseConnection:
    """Small DB-API compatibility layer with named-row results."""

    def __init__(self, raw_connection: Any, backend: str) -> None:
        self.raw = raw_connection
        self.backend = backend

    def _adapt_sql(self, sql: str) -> str:
        if self.backend == "postgresql":
            return sql.replace("?", "%s")
        return sql

    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] | None = None,
    ) -> Any:
        return self.raw.execute(self._adapt_sql(sql), tuple(parameters or ()))

    def executemany(self, sql: str, parameters: Sequence[Sequence[Any]]) -> Any:
        return self.raw.executemany(self._adapt_sql(sql), parameters)

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.raw.executescript(script)
            return
        for statement in _split_sql_script(script):
            self.raw.execute(statement)

    def select_for_update(self, sql: str) -> str:
        if self.backend == "postgresql":
            return f"{sql.rstrip()} FOR UPDATE"
        return sql

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def _split_sql_script(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def connect(sqlite_path: Path | None = None) -> DatabaseConnection:
    database_url = configured_database_url()
    if database_url:
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("database_url 必须是 PostgreSQL 连接串")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "已配置 database_url，但尚未安装 psycopg[binary]"
            ) from error
        raw_connection = psycopg.connect(database_url, row_factory=dict_row)
        return DatabaseConnection(raw_connection, "postgresql")

    path = Path(sqlite_path or DEFAULT_SQLITE_PATH)
    raw_connection = sqlite3.connect(path, timeout=10)
    raw_connection.row_factory = sqlite3.Row
    raw_connection.execute("PRAGMA foreign_keys = ON")
    raw_connection.execute("PRAGMA busy_timeout = 5000")
    return DatabaseConnection(raw_connection, "sqlite")


@contextmanager
def transaction(
    sqlite_path: Path | None = None,
    *,
    immediate: bool = False,
) -> Iterator[DatabaseConnection]:
    connection = connect(sqlite_path)
    try:
        if immediate and connection.backend == "sqlite":
            connection.execute("BEGIN IMMEDIATE")
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def backend_name() -> str:
    return "postgresql" if configured_database_url() else "sqlite"


def is_integrity_error(error: BaseException) -> bool:
    """Return whether a driver error represents a constraint violation."""

    if isinstance(error, sqlite3.IntegrityError):
        return True
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate is None:
        diagnostic = getattr(error, "diag", None)
        sqlstate = getattr(diagnostic, "sqlstate", None)
    return bool(sqlstate and str(sqlstate).startswith("23"))
