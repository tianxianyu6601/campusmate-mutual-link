"""Safely import durable legacy SQLite data into configured PostgreSQL.

The command is dry-run by default and never prints email addresses or the
database URL. Use ``python -m scripts.import_legacy_sqlite --apply`` to write.
"""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from services.database import DEFAULT_SQLITE_PATH, backend_name, transaction
from services.migrations import run_migrations


TABLES = (
    "users",
    "user_profiles",
    "profiles",
    "profile_interests",
    "profile_privacy",
)
PROFILE_COLUMNS = (
    "email",
    "display_name",
    "school",
    "department",
    "grade",
    "identity_label",
    "bio",
    "mbti",
    "introversion",
    "planning_style",
    "warm_up_level",
    "group_size_preference",
    "self_description",
    "partner_expectation",
    "contact_email",
    "contact_wechat",
    "available_times_json",
    "preferred_locations_json",
    "max_distance_km",
    "allow_cross_school",
    "completion_percent",
    "created_at",
    "updated_at",
    "avatar_data_url",
)


def _read_rows(source_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"source SQLite database not found: {source_path}")
    result: dict[str, list[dict[str, Any]]] = {}
    with closing(sqlite3.connect(source_path)) as connection:
        connection.row_factory = sqlite3.Row
        existing_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in TABLES:
            result[table] = (
                [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
                if table in existing_tables
                else []
            )
    return result


def _import(
    rows: dict[str, list[dict[str, Any]]],
    *,
    sqlite_path: Path | None = None,
) -> None:
    run_migrations(sqlite_path)
    with transaction(sqlite_path, immediate=True) as connection:
        for row in rows["users"]:
            connection.execute(
                """
                INSERT INTO users(email, user_id, password_hash, salt, verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    user_id = excluded.user_id,
                    password_hash = excluded.password_hash,
                    salt = excluded.salt,
                    verified = excluded.verified
                """,
                (
                    row["email"], row["user_id"], row["password_hash"], row["salt"],
                    row["verified"], row["created_at"],
                ),
            )
        for row in rows["user_profiles"]:
            connection.execute(
                """
                INSERT INTO user_profiles(email, profile_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (row["email"], row["profile_json"], row["updated_at"]),
            )
        profile_updates = ", ".join(
            f"{column} = excluded.{column}"
            for column in PROFILE_COLUMNS
            if column not in {"email", "created_at"}
        )
        profile_placeholders = ", ".join("?" for _ in PROFILE_COLUMNS)
        for row in rows["profiles"]:
            connection.execute(
                f"""
                INSERT INTO profiles({', '.join(PROFILE_COLUMNS)})
                VALUES ({profile_placeholders})
                ON CONFLICT(email) DO UPDATE SET {profile_updates}
                """,
                tuple(row[column] for column in PROFILE_COLUMNS),
            )
        for row in rows["profile_interests"]:
            connection.execute(
                """
                INSERT INTO profile_interests(email, category, tag, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email, category, tag) DO UPDATE SET
                    created_at = excluded.created_at
                """,
                (row["email"], row["category"], row["tag"], row["created_at"]),
            )
        for row in rows["profile_privacy"]:
            connection.execute(
                """
                INSERT INTO profile_privacy(email, field_name, visibility, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email, field_name) DO UPDATE SET
                    visibility = excluded.visibility,
                    updated_at = excluded.updated_at
                """,
                (
                    row["email"],
                    row["field_name"],
                    row["visibility"],
                    row["updated_at"],
                ),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--apply", action="store_true", help="write to configured PostgreSQL")
    args = parser.parse_args()

    rows = _read_rows(args.source.resolve())
    counts = " ".join(f"{table}={len(rows[table])}" for table in TABLES)
    if not args.apply:
        print(f"dry_run=true {counts}")
        return
    if backend_name() != "postgresql":
        raise RuntimeError("--apply requires a configured PostgreSQL database_url")
    _import(rows)
    print(f"dry_run=false imported {counts}")


if __name__ == "__main__":
    main()
