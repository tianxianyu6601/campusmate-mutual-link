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

    def test_require_login_redirects_when_session_is_missing(self) -> None:
        with (
            patch("services.auth.st.session_state", {}),
            patch("services.auth.st.switch_page") as switch_page,
            patch("services.auth.st.stop", side_effect=RuntimeError("stopped")),
        ):
            with self.assertRaisesRegex(RuntimeError, "stopped"):
                auth.require_login()

        switch_page.assert_called_once_with("pages/login.py")

    def test_password_reset_updates_login_password(self) -> None:
        register_code = auth.send_verification_code("person@example.com")
        auth.register_user("person@example.com", "password123", str(register_code))

        reset_code = auth.send_password_reset_code("person@example.com")
        auth.reset_password("person@example.com", str(reset_code), "newpass123")

        with self.assertRaises(auth.AuthError):
            auth.authenticate("person@example.com", "password123")
        user = auth.authenticate("person@example.com", "newpass123")
        self.assertEqual("person@example.com", user["email"])

    def test_password_reset_code_requires_registered_email(self) -> None:
        with self.assertRaisesRegex(auth.AuthError, "尚未注册"):
            auth.send_password_reset_code("missing@example.com")

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

    def test_qq_smtp_cloud_disconnect_points_to_https_provider(self) -> None:
        def fake_send_once(config, attempt, message) -> None:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

        with (
            patch(
                "services.auth.st.secrets",
                {
                    "mail_provider": "smtp",
                    "smtp": {
                        "host": "smtp.qq.com",
                        "port": 465,
                        "username": "123456789@qq.com",
                        "password": "abcdefghijklmnop",
                        "from_email": "123456789@qq.com",
                        "use_ssl": True,
                        "use_tls": False,
                    },
                },
            ),
            patch("services.auth._send_email_once", side_effect=fake_send_once),
        ):
            with self.assertRaisesRegex(auth.AuthError, "SendGrid"):
                auth.send_email("receiver@example.com", "Subject", "Body")

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
        self.assertEqual(auth.MAIL_USER_AGENT, captured["headers"]["User-agent"])
        self.assertEqual("CampusMate <notify@example.org>", captured["payload"]["from"])
        self.assertEqual(["receiver@example.com"], captured["payload"]["to"])
        self.assertEqual("Subject", captured["payload"]["subject"])
        self.assertEqual("Body", captured["payload"]["text"])

    def test_sendgrid_provider_posts_mail_send_request(self) -> None:
        class FakeResponse:
            status = 202

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
                    "mail_provider": "sendgrid",
                    "sendgrid": {
                        "api_key": "SG.123456789",
                        "from_email": "sender@example.org",
                        "from_name": "CampusMate",
                    },
                },
            ),
            patch("services.auth.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            auth.send_email("receiver@example.com", "Subject", "Body")

        self.assertEqual("https://api.sendgrid.com/v3/mail/send", captured["url"])
        self.assertEqual(30, captured["timeout"])
        self.assertEqual("Bearer SG.123456789", captured["headers"]["Authorization"])
        self.assertEqual(auth.MAIL_USER_AGENT, captured["headers"]["User-agent"])
        self.assertEqual(
            [{"to": [{"email": "receiver@example.com"}]}],
            captured["payload"]["personalizations"],
        )
        self.assertEqual(
            {"email": "sender@example.org", "name": "CampusMate"},
            captured["payload"]["from"],
        )
        self.assertEqual("Subject", captured["payload"]["subject"])
        self.assertEqual(
            [{"type": "text/plain", "value": "Body"}],
            captured["payload"]["content"],
        )

    def test_auto_provider_falls_back_to_smtp(self) -> None:
        calls: list[str] = []

        def fake_sendgrid(to_email, subject, body) -> None:
            calls.append("sendgrid")
            raise auth.AuthError("SendGrid unavailable")

        def fake_send_once(config, attempt, message) -> None:
            calls.append(f"smtp:{attempt['port']}")

        with (
            patch(
                "services.auth.st.secrets",
                {
                    "mail_provider": "auto",
                    "sendgrid": {
                        "api_key": "SG.123456789",
                        "from_email": "sender@example.org",
                        "from_name": "CampusMate",
                    },
                    "smtp": {
                        "host": "smtp.qq.com",
                        "port": 465,
                        "username": "123456789@qq.com",
                        "password": "abcdefghijklmnop",
                        "from_email": "123456789@qq.com",
                        "use_ssl": True,
                        "use_tls": False,
                    },
                },
            ),
            patch("services.auth._send_email_sendgrid", side_effect=fake_sendgrid),
            patch("services.auth._send_email_once", side_effect=fake_send_once),
        ):
            auth.send_email("receiver@example.com", "Subject", "Body")

        self.assertEqual(["sendgrid", "smtp:465"], calls)

    def test_mail_diagnostic_includes_version_and_provider_order(self) -> None:
        with (
            patch(
                "services.auth.st.secrets",
                {
                    "mail_provider": "auto",
                    "sendgrid": {
                        "api_key": "SG.123456789",
                        "from_email": "sender@example.org",
                        "from_name": "CampusMate",
                    },
                },
            ),
            patch("services.auth._send_email_sendgrid"),
        ):
            report = auth.diagnose_mail_service("receiver@example.com")

        self.assertIn(f"邮件系统版本：{auth.MAIL_SYSTEM_VERSION}", report)
        self.assertIn("当前邮件通道：sendgrid -> smtp", report)


if __name__ == "__main__":
    unittest.main()
