from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from services.database import transaction
from services.email_tasks import process_email_tasks
from services.migrations import run_migrations
from services.platform_service import apply_to_activity, create_activity, upsert_profile


class EmailTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "mail.db"
        run_migrations(self.database)
        with transaction(self.database) as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("owner@example.com", "U0051", "hash", "salt", 1, 1),
            )
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                ("member@example.com", "U0052", "hash", "salt", 1, 1),
            )
        for email in ("owner@example.com", "member@example.com"):
            upsert_profile(
                email,
                {"display_name": email.split("@", 1)[0], "contact_email": email},
                sqlite_path=self.database,
            )
        self.activity_id = create_activity(
            "owner@example.com",
            category="sport",
            title="周末羽毛球",
            description="",
            starts_at=int(time.time()) + 3600,
            location_text="邱德拔体育馆",
            capacity=3,
            sqlite_path=self.database,
        )
        self.application_id = apply_to_activity(
            self.activity_id,
            "member@example.com",
            reason="想一起运动",
            sqlite_path=self.database,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_worker_sends_and_marks_the_task_sent(self) -> None:
        deliveries: list[tuple[str, str, str]] = []

        def fake_sender(recipient: str, subject: str, body: str) -> None:
            deliveries.append((recipient, subject, body))

        result = process_email_tasks(
            sender=fake_sender, sqlite_path=self.database
        )

        self.assertEqual({"claimed": 1, "sent": 1, "failed": 0, "dead": 0}, result)
        self.assertEqual("owner@example.com", deliveries[0][0])
        self.assertIn("周末羽毛球", deliveries[0][2])
        self.assertIn("申请联系方式", deliveries[0][2])
        self.assertIn("member@example.com", deliveries[0][2])
        with transaction(self.database) as connection:
            status = connection.execute(
                "SELECT status FROM email_tasks"
            ).fetchone()["status"]
        self.assertEqual("sent", status)

    def test_mail_failure_is_retryable_and_does_not_rollback_application(self) -> None:
        def failing_sender(_recipient: str, _subject: str, _body: str) -> None:
            raise RuntimeError("temporary failure")

        first = process_email_tasks(
            sender=failing_sender, sqlite_path=self.database
        )
        self.assertEqual(1, first["failed"])
        with transaction(self.database, immediate=True) as connection:
            task = connection.execute(
                "SELECT status, attempts, last_error FROM email_tasks"
            ).fetchone()
            application = connection.execute(
                "SELECT status FROM activity_applications WHERE application_id = ?",
                (self.application_id,),
            ).fetchone()
            connection.execute(
                "UPDATE email_tasks SET next_attempt_at = ?", (int(time.time()) - 1,)
            )
        self.assertEqual("failed", task["status"])
        self.assertEqual(1, task["attempts"])
        self.assertIn("temporary failure", task["last_error"])
        self.assertEqual("pending", application["status"])

        second = process_email_tasks(
            sender=lambda *_args: None, sqlite_path=self.database
        )
        self.assertEqual(1, second["sent"])
        with transaction(self.database) as connection:
            task = connection.execute(
                "SELECT status, attempts FROM email_tasks"
            ).fetchone()
        self.assertEqual("sent", task["status"])
        self.assertEqual(2, task["attempts"])


if __name__ == "__main__":
    unittest.main()
