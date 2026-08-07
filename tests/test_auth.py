"""Tests for email account registration helpers."""

from __future__ import annotations

import tempfile
import unittest
import smtplib
import json
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

    def test_qq_smtp_falls_back_from_ssl_to_starttls(self) -> None:
        calls: list[tuple[int, bool, bool]] = []

        def fake_send_once(config, attempt, message) -> None:
            calls.append(
                (
                    int(attempt["port"]),
                    bool(attempt["use_ssl"]),
                    bool(attempt["use_tls"]),
                )
            )
            if int(attempt["port"]) == 465:
                raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

        with (
            patch(
                "services.auth.st.secrets",
                {
                    "smtp": {
                        "host": "smtp.qq.com",
                        "port": 465,
                        "username": "123456789@qq.com",
                        "password": "abcdefghijklmnop",
                        "from_email": "CampusMate <123456789@qq.com>",
                        "use_ssl": True,
                        "use_tls": False,
                    }
                },
            ),
            patch("services.auth._send_email_once", side_effect=fake_send_once),
        ):
            auth.send_email("receiver@example.com", "Subject", "Body")

        self.assertEqual([(465, True, False), (587, False, True)], calls)

    def test_resend_provider_posts_email_api_request(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with (
            patch(
                "services.auth.st.secrets",
                {
                    "mail_provider": "resend",
                    "resend": {
                        "api_key": "re_123456789",
                        "from_email": "CampusMate <notify@example.org>",
                    },
                },
            ),
            patch("services.auth.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            auth.send_email("receiver@example.com", "Subject", "Body")

        self.assertEqual("https://api.resend.com/emails", captured["url"])
        self.assertEqual(30, captured["timeout"])
        self.assertEqual("Bearer re_123456789", captured["headers"]["Authorization"])
        self.assertEqual("CampusMate <notify@example.org>", captured["payload"]["from"])
        self.assertEqual(["receiver@example.com"], captured["payload"]["to"])
        self.assertEqual("Subject", captured["payload"]["subject"])
        self.assertEqual("Body", captured["payload"]["text"])


if __name__ == "__main__":
    unittest.main()
