from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.import_legacy_sqlite import _import, _read_rows
from services.database import transaction
from services.migrations import run_migrations


class LegacyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.db"
        self.target = self.root / "target.db"
        run_migrations(self.source)
        with transaction(self.source) as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("owner@example.com", "U0051", "hash", "salt", 1, 1),
            )
            connection.execute(
                """
                INSERT INTO profiles(
                    email, display_name, school, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("owner@example.com", "测试用户", "北京大学", 1, 1),
            )
            connection.execute(
                """
                INSERT INTO profile_interests(email, category, tag, created_at)
                VALUES (?, 'sport', '羽毛球', ?)
                """,
                ("owner@example.com", 1),
            )
            connection.execute(
                """
                INSERT INTO profile_privacy(email, field_name, visibility, updated_at)
                VALUES (?, 'bio', 'public', ?)
                """,
                ("owner@example.com", 1),
            )
            connection.execute(
                """
                INSERT INTO activities(
                    activity_id, organizer_email, category, title, starts_at,
                    location_text, capacity, created_at, updated_at
                ) VALUES ('act_test', ?, 'sport', '不应迁移', 10, '燕园', 2, 1, 1)
                """,
                ("owner@example.com",),
            )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_import_keeps_accounts_and_profiles_but_excludes_activities(self) -> None:
        rows = _read_rows(self.source)
        self.assertEqual(
            {
                "users": 1,
                "user_profiles": 0,
                "profiles": 1,
                "profile_interests": 1,
                "profile_privacy": 1,
            },
            {table: len(items) for table, items in rows.items()},
        )

        _import(rows, sqlite_path=self.target)
        _import(rows, sqlite_path=self.target)

        with transaction(self.target) as connection:
            counts = {
                table: int(
                    connection.execute(
                        f"SELECT COUNT(*) AS count FROM {table}"
                    ).fetchone()["count"]
                )
                for table in (
                    "users",
                    "profiles",
                    "profile_interests",
                    "profile_privacy",
                    "activities",
                )
            }
        self.assertEqual(
            {
                "users": 1,
                "profiles": 1,
                "profile_interests": 1,
                "profile_privacy": 1,
                "activities": 0,
            },
            counts,
        )


if __name__ == "__main__":
    unittest.main()
