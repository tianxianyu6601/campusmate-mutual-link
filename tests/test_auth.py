"""Tests for email account registration helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import auth


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db_path = auth.DB_PATH
        self.tempdir = tempfile.TemporaryDirectory()
        auth.DB_PATH = Path(self.tempdir.name) / "auth_test.db"

    def tearDown(self) -> None:
        auth.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_register_and_login_without_smtp_returns_demo_code(self) -> None:
        code = auth.send_verification_code("USER@example.com")
        self.assertIsNotNone(code)
        user = auth.register_user("USER@example.com", "password123", str(code))
        self.assertEqual("user@example.com", user["email"])
        self.assertEqual(user, auth.authenticate("user@example.com", "password123"))

    def test_wrong_password_is_rejected(self) -> None:
        code = auth.send_verification_code("person@example.com")
        auth.register_user("person@example.com", "password123", str(code))
        with self.assertRaises(auth.AuthError):
            auth.authenticate("person@example.com", "wrong-password")

    def test_smtp_placeholder_is_rejected_before_login(self) -> None:
        with patch(
            "services.auth.st.secrets",
            {
                "smtp": {
                    "host": "smtp.qq.com",
                    "port": 465,
                    "username": "你的发件邮箱@qq.com",
                    "password": "你的SMTP授权码",
                    "from_email": "CampusMate <sender@qq.com>",
                    "use_ssl": True,
                    "use_tls": False,
                }
            },
        ):
            with self.assertRaisesRegex(auth.AuthError, "SMTP"):
                auth.send_verification_code("receiver@example.com")


if __name__ == "__main__":
    unittest.main()
