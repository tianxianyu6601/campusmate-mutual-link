from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from services.database import transaction
from services.migrations import LATEST_SCHEMA_VERSION, current_schema_version, run_migrations


EXPECTED_TABLES = {
    "users",
    "profiles",
    "profile_interests",
    "profile_privacy",
    "activities",
    "activity_applications",
    "activity_members",
    "match_rounds",
    "match_enrollments",
    "match_profile_snapshots",
    "match_results",
    "match_result_members",
    "email_tasks",
    "user_notifications",
    "audit_log",
    "schema_migrations",
}


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_migrations_are_idempotent_and_create_full_schema(self) -> None:
        database = self.root / "schema.db"

        self.assertEqual([1, 2, 3, 4, 5, 6, 7], run_migrations(database))
        self.assertEqual([], run_migrations(database))
        self.assertEqual(LATEST_SCHEMA_VERSION, current_schema_version(database))

        with closing(sqlite3.connect(database)) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])

        self.assertLessEqual(EXPECTED_TABLES, tables)
        self.assertEqual(LATEST_SCHEMA_VERSION, user_version)

        with transaction(database) as connection:
            profile_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(profiles)").fetchall()
            }
        self.assertIn("avatar_data_url", profile_columns)
        self.assertIn("contact_qq", profile_columns)
        with transaction(database) as connection:
            application_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(activity_applications)"
                ).fetchall()
            }
        self.assertIn("attempt_count", application_columns)
        self.assertIn("applicant_contact", application_columns)
        with transaction(database) as connection:
            enrollment_columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(match_enrollments)"
                ).fetchall()
            }
        self.assertIn("unmatched_reason", enrollment_columns)
        with transaction(database) as connection:
            activity_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(activities)").fetchall()
            }
        self.assertIn("organizer_contact", activity_columns)

    def test_share_interest_category_is_supported(self) -> None:
        database = self.root / "share-interest.db"
        run_migrations(database)
        with transaction(database) as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("share@example.com", "U0051", "hash", "salt", 1, 1),
            )
            connection.execute(
                "INSERT INTO profile_interests(email, category, tag, created_at) VALUES (?, 'share', ?, ?)",
                ("share@example.com", "拼车", 1),
            )
            row = connection.execute(
                "SELECT category, tag FROM profile_interests WHERE email = ?",
                ("share@example.com",),
            ).fetchone()
        self.assertEqual("share", row["category"])
        self.assertEqual("拼车", row["tag"])

    def test_partially_applied_column_migration_recovers(self) -> None:
        database = self.root / "partial-column.db"
        run_migrations(database)
        with transaction(database) as connection:
            connection.execute("DELETE FROM schema_migrations WHERE version = 6")

        self.assertEqual([6], run_migrations(database))
        self.assertEqual([], run_migrations(database))
        self.assertEqual(7, current_schema_version(database))

    def test_migration_preserves_legacy_users(self) -> None:
        database = self.root / "legacy.db"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                """
                CREATE TABLE users (
                    email TEXT PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("legacy@example.com", "U0051", "hash", "salt", 1, 1),
            )
            connection.commit()

        run_migrations(database)

        with closing(sqlite3.connect(database)) as connection:
            row = connection.execute(
                "SELECT email, user_id FROM users WHERE email = ?",
                ("legacy@example.com",),
            ).fetchone()
        self.assertEqual(("legacy@example.com", "U0051"), row)

    def test_transaction_rolls_back_all_writes_on_error(self) -> None:
        database = self.root / "rollback.db"
        run_migrations(database)

        with self.assertRaises(RuntimeError):
            with transaction(database, immediate=True) as connection:
                connection.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                    ("rollback@example.com", "U0051", "hash", "salt", 1, 1),
                )
                raise RuntimeError("stop")

        with closing(sqlite3.connect(database)) as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        self.assertEqual(0, count)

    def test_database_constraints_reject_invalid_activity_capacity(self) -> None:
        database = self.root / "constraints.db"
        run_migrations(database)
        with transaction(database) as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("owner@example.com", "U0051", "hash", "salt", 1, 1),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(database) as connection:
                connection.execute(
                    """
                    INSERT INTO activities(
                        activity_id, organizer_email, category, title, starts_at,
                        location_text, capacity, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "act_invalid", "owner@example.com", "sport", "羽毛球",
                        10, "体育馆", 1, 1, 1,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
