"""Email-based account, verification, and notification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from services.database import DatabaseConnection, transaction
from services.migrations import ensure_migrations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "campusmate_app.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
SESSION_COOKIE_NAME = "cm_session"
SESSION_STATE_REFRESH_SECONDS = 60 * 60
SESSION_CLEANUP_INTERVAL_SECONDS = 15 * 60
_VALIDATED_SESSION_TOKEN_KEY = "_validated_session_token"
_PERSISTED_SESSION_DIGEST_KEY = "_persisted_session_digest"
_PERSISTED_SESSION_AT_KEY = "_persisted_session_at"
_SESSION_CLEANUP_LOCK = threading.Lock()
_LAST_SESSION_CLEANUP: dict[str, float] = {}
PERSISTED_SESSION_KEYS = (
    "selected_match_type",
    "questionnaire_answers",
    "current_profile",
    "matching_run",
    "current_match",
    "feedback_records",
)
MAIL_SYSTEM_VERSION = "mail-auto-fallback-2026-08-08-2"
MAIL_USER_AGENT = "CampusMate/1.0 (Streamlit Cloud; mail verification)"
SMTP_CLOUD_FAILURE_ADVICE = (
    "如果你在 Streamlit Cloud 上使用 QQ 邮箱并看到 Connection unexpectedly closed，"
    "通常是云服务器到 QQ SMTP 的连接被服务端断开。代码无法绕过这个外部限制；"
    "建议改用 SendGrid 这类 HTTPS 邮件通道，或换一个明确允许云服务器 SMTP 登录的发件邮箱服务。"
)


class AuthError(RuntimeError):
    """Raised for expected account-flow failures."""


class MailNotConfigured(RuntimeError):
    """Raised when SMTP settings are missing."""


@contextmanager
def _db() -> DatabaseConnection:
    with transaction(DB_PATH) as connection:
        yield connection


def init_db() -> None:
    ensure_migrations(DB_PATH)
    cleanup_key = str(Path(DB_PATH).resolve())
    now = time.monotonic()
    if now - _LAST_SESSION_CLEANUP.get(cleanup_key, 0.0) < SESSION_CLEANUP_INTERVAL_SECONDS:
        return
    with _SESSION_CLEANUP_LOCK:
        if now - _LAST_SESSION_CLEANUP.get(cleanup_key, 0.0) < SESSION_CLEANUP_INTERVAL_SECONDS:
            return
        with _db() as connection:
            connection.execute(
                "DELETE FROM login_sessions WHERE expires_at < ?", (int(time.time()),)
            )
        _LAST_SESSION_CLEANUP[cleanup_key] = now


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_RE.fullmatch(normalized):
        raise AuthError("请输入有效的邮箱地址")
    return normalized


def account_exists(email: str) -> bool:
    init_db()
    with _db() as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE email = ?", (normalize_email(email),)
        ).fetchone()
    return row is not None


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _serializable_session_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in PERSISTED_SESSION_KEYS:
        if key not in state:
            continue
        value = state[key]
        try:
            json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            continue
        payload[key] = value
    return payload


def _session_payload_digest(state: Mapping[str, Any]) -> str:
    payload_json = json.dumps(
        _serializable_session_payload(state),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _mark_session_persisted(token: str, state: Mapping[str, Any]) -> None:
    st.session_state[_VALIDATED_SESSION_TOKEN_KEY] = str(token)
    st.session_state[_PERSISTED_SESSION_DIGEST_KEY] = _session_payload_digest(state)
    st.session_state[_PERSISTED_SESSION_AT_KEY] = time.monotonic()


def _current_session_token() -> str | None:
    token = st.session_state.get("session_token")
    if token:
        return str(token)
    try:
        cookie_value = st.context.cookies.get(SESSION_COOKIE_NAME)
    except Exception:
        cookie_value = None
    return str(cookie_value) if cookie_value else None


def write_session_cookie(token: str) -> None:
    """Write the opaque browser token without triggering iframe navigation."""

    token_json = json.dumps(str(token))
    name_json = json.dumps(SESSION_COOKIE_NAME)
    st.html(
        f"""
        <span style="display:none" aria-hidden="true"></span>
        <script>
          (() => {{
            const campusMateCookieName = {name_json};
            const campusMateToken = {token_json};
            const campusMateSecure = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie = `${{campusMateCookieName}}=${{encodeURIComponent(campusMateToken)}}; Max-Age={SESSION_TTL_SECONDS}; Path=/; SameSite=Strict${{campusMateSecure}}`;
          }})();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def clear_session_cookie() -> None:
    """Remove the browser token without triggering iframe navigation."""

    name_json = json.dumps(SESSION_COOKIE_NAME)
    st.html(
        f"""
        <span style="display:none" aria-hidden="true"></span>
        <script>
          (() => {{
            const campusMateCookieName = {name_json};
            const campusMateSecure = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie = `${{campusMateCookieName}}=; Max-Age=0; Path=/; SameSite=Strict${{campusMateSecure}}`;
          }})();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def create_login_session(
    user: Mapping[str, str],
    state: Mapping[str, Any] | None = None,
) -> str:
    """Create a refresh-safe server session and return its opaque browser token."""

    init_db()
    email = normalize_email(str(user["email"]))
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    state_json = json.dumps(
        _serializable_session_payload(state or {}),
        ensure_ascii=False,
    )
    with _db() as connection:
        row = connection.execute(
            "SELECT email FROM users WHERE email = ? AND verified = 1",
            (email,),
        ).fetchone()
        if row is None:
            raise AuthError("登录用户不存在或尚未完成验证")
        connection.execute(
            """
            INSERT INTO login_sessions(
                session_token_hash, email, state_json, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _hash_session_token(token),
                email,
                state_json,
                now,
                now,
                now + SESSION_TTL_SECONDS,
            ),
        )
    return token


def load_login_session(token: str) -> dict[str, Any] | None:
    init_db()
    token = str(token).strip()
    if not token:
        return None
    token_hash = _hash_session_token(token)
    now = int(time.time())
    with _db() as connection:
        row = connection.execute(
            """
            SELECT s.state_json, s.expires_at, u.email, u.user_id
            FROM login_sessions AS s
            JOIN users AS u ON u.email = s.email
            WHERE s.session_token_hash = ? AND u.verified = 1
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        if int(row["expires_at"]) < now:
            connection.execute(
                "DELETE FROM login_sessions WHERE session_token_hash = ?",
                (token_hash,),
            )
            return None
        connection.execute(
            """
            UPDATE login_sessions
            SET updated_at = ?, expires_at = ?
            WHERE session_token_hash = ?
            """,
            (now, now + SESSION_TTL_SECONDS, token_hash),
        )

    try:
        state = json.loads(str(row["state_json"]))
    except json.JSONDecodeError:
        state = {}
    if not isinstance(state, dict):
        state = {}
    return {
        "auth_user": {"email": str(row["email"]), "user_id": str(row["user_id"])},
        "state": _serializable_session_payload(state),
    }


def save_login_session_state(token: str, state: Mapping[str, Any]) -> None:
    init_db()
    token = str(token).strip()
    if not token:
        return
    now = int(time.time())
    with _db() as connection:
        connection.execute(
            """
            UPDATE login_sessions
            SET state_json = ?, updated_at = ?, expires_at = ?
            WHERE session_token_hash = ? AND expires_at >= ?
            """,
            (
                json.dumps(_serializable_session_payload(state), ensure_ascii=False),
                now,
                now + SESSION_TTL_SECONDS,
                _hash_session_token(token),
                now,
            ),
        )


def delete_login_session(token: str) -> None:
    init_db()
    token = str(token).strip()
    if not token:
        return
    with _db() as connection:
        connection.execute(
            "DELETE FROM login_sessions WHERE session_token_hash = ?",
            (_hash_session_token(token),),
        )


def start_persistent_session(user: Mapping[str, str]) -> str:
    token = create_login_session(user, dict(st.session_state))
    st.session_state["session_token"] = token
    _mark_session_persisted(token, dict(st.session_state))
    return token


def restore_persistent_session() -> bool:
    token = _current_session_token()
    if not token:
        return bool(st.session_state.get("auth_user"))
    if (
        st.session_state.get("auth_user")
        and st.session_state.get(_VALIDATED_SESSION_TOKEN_KEY) == token
    ):
        return True

    restored = load_login_session(token)
    if restored is None:
        st.session_state.pop("session_token", None)
        st.session_state.pop("auth_user", None)
        st.session_state.pop(_VALIDATED_SESSION_TOKEN_KEY, None)
        st.session_state.pop(_PERSISTED_SESSION_DIGEST_KEY, None)
        st.session_state.pop(_PERSISTED_SESSION_AT_KEY, None)
        return False

    st.session_state["session_token"] = token
    st.session_state["auth_user"] = restored["auth_user"]
    for key, value in restored["state"].items():
        st.session_state[key] = value
    _mark_session_persisted(token, restored["state"])
    return True


def persist_current_session_state() -> None:
    user = st.session_state.get("auth_user")
    if not user:
        return
    token = _current_session_token()
    if not token:
        token = start_persistent_session(dict(user))
    st.session_state["session_token"] = token
    current_state = dict(st.session_state)
    current_digest = _session_payload_digest(current_state)
    last_digest = st.session_state.get(_PERSISTED_SESSION_DIGEST_KEY)
    last_saved_at = float(st.session_state.get(_PERSISTED_SESSION_AT_KEY, 0.0))
    if (
        current_digest == last_digest
        and time.monotonic() - last_saved_at < SESSION_STATE_REFRESH_SECONDS
    ):
        return
    save_login_session_state(token, current_state)
    _mark_session_persisted(token, current_state)


def clear_persistent_session() -> None:
    token = _current_session_token()
    if token:
        delete_login_session(token)
    st.session_state.pop("session_token", None)
    st.session_state.pop(_VALIDATED_SESSION_TOKEN_KEY, None)
    st.session_state.pop(_PERSISTED_SESSION_DIGEST_KEY, None)
    st.session_state.pop(_PERSISTED_SESSION_AT_KEY, None)


def _next_user_id(connection: DatabaseConnection) -> str:
    rows = connection.execute("SELECT user_id FROM users").fetchall()
    numbers = [
        int(row["user_id"][1:])
        for row in rows
        if isinstance(row["user_id"], str) and row["user_id"].startswith("U")
    ]
    return f"U{max(numbers, default=50) + 1:04d}"


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _smtp_config() -> dict[str, Any]:
    try:
        config = st.secrets.get("smtp", None)
    except Exception as error:
        raise MailNotConfigured("尚未配置 SMTP 邮件服务") from error
    if not config:
        raise MailNotConfigured("尚未配置 SMTP 邮件服务")
    required = ("host", "port", "username", "password", "from_email")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise MailNotConfigured(f"SMTP 配置缺少：{', '.join(missing)}")
    normalized_config = dict(config)
    try:
        normalized_config["port"] = int(normalized_config["port"])
    except (TypeError, ValueError) as error:
        raise AuthError("SMTP port 必须是数字，例如 465 或 587。") from error

    normalized_config["host"] = str(normalized_config["host"]).strip()
    normalized_config["username"] = str(normalized_config["username"]).strip()
    # App passwords are commonly copied with visual spaces; SMTP auth expects
    # the raw token. This keeps QQ/Gmail-style authorization codes usable.
    normalized_config["password"] = re.sub(
        r"\s+", "", str(normalized_config["password"])
    )
    normalized_config["from_email"] = str(normalized_config["from_email"]).strip()

    placeholder_markers = ("your_", "example.com", "你的", "授权码")
    for key in ("host", "username", "password"):
        value = str(normalized_config[key])
        if any(marker in value for marker in placeholder_markers):
            raise AuthError(
                "SMTP Secrets 仍然是示例占位内容，请填写真实发件邮箱和 SMTP 授权码。"
            )
    for key in ("username", "password"):
        value = str(normalized_config[key])
        try:
            value.encode("ascii")
        except UnicodeEncodeError as error:
            raise AuthError(
                "SMTP 用户名和授权码只能使用真实邮箱服务提供的英文/数字内容，"
                "不能包含中文占位符或中文标点。"
            ) from error
    host = str(normalized_config["host"]).lower()
    if host == "smtp.qq.com" and not re.fullmatch(
        r"[A-Za-z0-9]{16}", str(normalized_config["password"])
    ):
        raise AuthError(
            "QQ 邮箱的 SMTP password 必须填写 16 位授权码，不是 QQ 登录密码。"
        )
    port = int(normalized_config["port"])
    if port == 465:
        normalized_config["use_ssl"] = True
        normalized_config["use_tls"] = False
    elif port == 587:
        normalized_config["use_ssl"] = False
        normalized_config["use_tls"] = True
    else:
        normalized_config["use_ssl"] = _as_bool(normalized_config.get("use_ssl"))
        normalized_config["use_tls"] = _as_bool(normalized_config.get("use_tls"))
    return normalized_config


def _resend_config() -> dict[str, str] | None:
    try:
        config = st.secrets.get("resend", None)
    except Exception:
        return None
    if not config:
        return None
    required = ("api_key", "from_email")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise AuthError(f"Resend 配置缺少：{', '.join(missing)}")
    api_key = str(config["api_key"]).strip()
    from_email = str(config["from_email"]).strip()
    if not api_key.startswith("re_"):
        raise AuthError("Resend api_key 应以 re_ 开头，请检查 Secrets。")
    if "your_" in from_email or "example.com" in from_email or "你的" in from_email:
        raise AuthError("Resend from_email 仍然是示例占位内容。")
    return {"api_key": api_key, "from_email": from_email}


def _sendgrid_config() -> dict[str, str] | None:
    try:
        config = st.secrets.get("sendgrid", None)
    except Exception:
        return None
    if not config:
        return None
    required = ("api_key", "from_email")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise AuthError(f"SendGrid 配置缺少：{', '.join(missing)}")
    api_key = str(config["api_key"]).strip()
    from_email = str(config["from_email"]).strip()
    from_name = str(config.get("from_name", "CampusMate")).strip() or "CampusMate"
    if not api_key.startswith("SG."):
        raise AuthError("SendGrid api_key 应以 SG. 开头，请检查 Secrets。")
    if "your_" in from_email or "example.com" in from_email or "你的" in from_email:
        raise AuthError("SendGrid from_email 仍然是示例占位内容。")
    normalize_email(from_email)
    return {"api_key": api_key, "from_email": from_email, "from_name": from_name}


def _send_email_resend(to_email: str, subject: str, body: str) -> None:
    config = _resend_config()
    if not config:
        raise AuthError("mail_provider = resend，但缺少 [resend] api_key/from_email 配置。")
    payload = json.dumps(
        {
            "from": config["from_email"],
            "to": [normalize_email(to_email)],
            "subject": subject,
            "text": body,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": MAIL_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise AuthError(f"Resend 发信失败：HTTP {response.status}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AuthError(f"Resend 发信失败：HTTP {error.code} {detail}") from error
    except urllib.error.URLError as error:
        raise AuthError(f"Resend 发信失败：{error.reason}") from error


def _send_email_sendgrid(to_email: str, subject: str, body: str) -> None:
    config = _sendgrid_config()
    if not config:
        raise AuthError(
            "mail_provider = sendgrid，但缺少 [sendgrid] api_key/from_email 配置。"
        )
    payload = json.dumps(
        {
            "personalizations": [
                {"to": [{"email": normalize_email(to_email)}]},
            ],
            "from": {"email": config["from_email"], "name": config["from_name"]},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": MAIL_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status < 200 or response.status >= 300:
                raise AuthError(f"SendGrid 发信失败：HTTP {response.status}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise AuthError(f"SendGrid 发信失败：HTTP {error.code} {detail}") from error
    except urllib.error.URLError as error:
        raise AuthError(f"SendGrid 发信失败：{error.reason}") from error


def _configured_mail_provider() -> str | None:
    try:
        configured = st.secrets.get("mail_provider", None)
    except Exception:
        return None
    if not configured:
        return None
    provider = str(configured).strip().lower()
    if provider not in {"auto", "smtp", "resend", "sendgrid"}:
        raise AuthError("mail_provider 只能填写 auto、smtp、resend 或 sendgrid。")
    return provider


def _mail_provider_order() -> list[str]:
    provider = _configured_mail_provider()
    if provider and provider != "auto":
        return [provider]

    providers: list[str] = []
    if _sendgrid_config():
        providers.append("sendgrid")
    if _resend_config():
        providers.append("resend")
    providers.append("smtp")
    return providers


def _smtp_attempts(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    attempts = [
        {
            "host": str(config["host"]),
            "port": int(config["port"]),
            "use_ssl": bool(config.get("use_ssl")),
            "use_tls": bool(config.get("use_tls")),
        }
    ]
    if str(config["host"]).lower() == "smtp.qq.com":
        fallback = {"host": "smtp.qq.com", "port": 587, "use_ssl": False, "use_tls": True}
        if int(config["port"]) == 587:
            fallback = {"host": "smtp.qq.com", "port": 465, "use_ssl": True, "use_tls": False}
        if fallback not in attempts:
            attempts.append(fallback)
    return attempts


def _describe_attempt(attempt: Mapping[str, Any]) -> str:
    mode = "SSL" if attempt.get("use_ssl") else "STARTTLS" if attempt.get("use_tls") else "plain"
    return f"{attempt['host']}:{attempt['port']} {mode}"


def _smtp_failure_message(
    config: Mapping[str, Any], smtp_failures: list[str]
) -> str:
    message = "SMTP 服务器断开或连接失败。"
    if smtp_failures:
        message += f"已尝试：{'；'.join(smtp_failures)}"
    host = str(config.get("host", "")).lower()
    combined = " ".join(smtp_failures).lower()
    if host == "smtp.qq.com" or "connection unexpectedly closed" in combined:
        message += f" {SMTP_CLOUD_FAILURE_ADVICE}"
    return message


def _send_email_once(
    config: Mapping[str, Any],
    attempt: Mapping[str, Any],
    message: EmailMessage,
) -> None:
    context = ssl.create_default_context()
    if bool(attempt.get("use_ssl")):
        with smtplib.SMTP_SSL(
            str(attempt["host"]),
            int(attempt["port"]),
            timeout=30,
            context=context,
        ) as server:
            server.ehlo()
            server.login(str(config["username"]), str(config["password"]))
            server.send_message(message)
        return

    with smtplib.SMTP(str(attempt["host"]), int(attempt["port"]), timeout=30) as server:
        server.ehlo()
        if bool(attempt.get("use_tls")):
            server.starttls(context=context)
            server.ehlo()
        server.login(str(config["username"]), str(config["password"]))
        server.send_message(message)


def send_email(to_email: str, subject: str, body: str) -> None:
    configured_provider = _configured_mail_provider()
    failures: list[str] = []
    missing_provider_count = 0

    for provider in _mail_provider_order():
        try:
            if provider == "sendgrid":
                _send_email_sendgrid(to_email, subject, body)
                return
            if provider == "resend":
                _send_email_resend(to_email, subject, body)
                return

            config = _smtp_config()
            message = EmailMessage()
            message["From"] = str(config["from_email"])
            message["To"] = normalize_email(to_email)
            message["Subject"] = subject
            message.set_content(body)

            smtp_failures: list[str] = []
            for attempt in _smtp_attempts(config):
                try:
                    _send_email_once(config, attempt, message)
                    return
                except smtplib.SMTPAuthenticationError as error:
                    raise AuthError(
                        "SMTP 登录失败：请确认邮箱已开启 SMTP 服务，password 填的是授权码，"
                        "不是邮箱登录密码。"
                    ) from error
                except (OSError, smtplib.SMTPException, TimeoutError) as error:
                    smtp_failures.append(f"{_describe_attempt(attempt)} -> {error}")
            raise AuthError(_smtp_failure_message(config, smtp_failures))
        except MailNotConfigured as error:
            missing_provider_count += 1
            failures.append(f"{provider}: {error}")
            if configured_provider and configured_provider != "auto":
                raise
        except AuthError as error:
            failures.append(f"{provider}: {error}")
            if configured_provider and configured_provider != "auto":
                raise

    if failures and missing_provider_count == len(failures):
        raise MailNotConfigured("尚未配置真实邮件服务")
    if len(failures) == 1:
        raise AuthError(f"验证码邮件发送失败：{failures[0]}")
    raise AuthError(
        "验证码邮件发送失败：所有已配置邮件通道均失败。"
        f"详情：{'；'.join(failures)}"
    )


def diagnose_mail_service(to_email: str) -> list[str]:
    """Return a safe, secret-free mail diagnostic report."""

    normalized = normalize_email(to_email)
    report: list[str] = []
    providers = _mail_provider_order()
    report.append(f"邮件系统版本：{MAIL_SYSTEM_VERSION}")
    report.append(f"当前邮件通道：{' -> '.join(providers)}")
    for provider in providers:
        if provider == "sendgrid":
            _diagnose_sendgrid(normalized, report)
        elif provider == "resend":
            _diagnose_resend(normalized, report)
        else:
            _diagnose_smtp(normalized, report)
    return report


def _diagnose_sendgrid(normalized_email: str, report: list[str]) -> None:
    config = _sendgrid_config()
    report.append(
        f"SendGrid from_email：{config['from_email'] if config else '未配置'}"
    )
    try:
        _send_email_sendgrid(
            normalized_email,
            "CampusMate 邮件服务自检",
            "这是一封 CampusMate 邮件服务自检邮件。",
        )
        report.append("SendGrid 自检成功：测试邮件已发送。")
    except (AuthError, MailNotConfigured) as error:
        report.append(f"SendGrid 自检失败：{error}")


def _diagnose_resend(normalized_email: str, report: list[str]) -> None:
    config = _resend_config()
    report.append(f"Resend from_email：{config['from_email'] if config else '未配置'}")
    try:
        _send_email_resend(
            normalized_email,
            "CampusMate 邮件服务自检",
            "这是一封 CampusMate 邮件服务自检邮件。",
        )
        report.append("Resend 自检成功：测试邮件已发送。")
    except (AuthError, MailNotConfigured) as error:
        report.append(f"Resend 自检失败：{error}")


def _diagnose_smtp(normalized_email: str, report: list[str]) -> None:
    try:
        config = _smtp_config()
    except (AuthError, MailNotConfigured) as error:
        report.append(f"SMTP 自检跳过：{error}")
        return
    report.append(f"SMTP host：{config['host']}")
    report.append(f"SMTP username：{config['username']}")
    for attempt in _smtp_attempts(config):
        label = _describe_attempt(attempt)
        try:
            message = EmailMessage()
            message["From"] = str(config["from_email"])
            message["To"] = normalized_email
            message["Subject"] = "CampusMate 邮件服务自检"
            message.set_content("这是一封 CampusMate 邮件服务自检邮件。")
            _send_email_once(config, attempt, message)
        except smtplib.SMTPAuthenticationError:
            report.append(f"{label}：登录失败，请检查 SMTP 服务是否开启、授权码是否正确。")
        except (OSError, smtplib.SMTPException, TimeoutError) as error:
            report.append(f"{label}：失败：{error}")
        else:
            report.append(f"{label}：成功，测试邮件已发送。")
            break


def create_verification_code(email: str) -> str:
    init_db()
    normalized = normalize_email(email)
    code = f"{secrets.randbelow(1_000_000):06d}"
    with _db() as connection:
        connection.execute(
            """
            INSERT INTO verification_codes(email, code_hash, expires_at, attempts)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(email) DO UPDATE SET
              code_hash = excluded.code_hash,
              expires_at = excluded.expires_at,
              attempts = 0
            """,
            (normalized, _hash_code(code), int(time.time()) + CODE_TTL_SECONDS),
        )
    return code


def send_verification_code(email: str) -> str | None:
    code = create_verification_code(email)
    body = (
        "欢迎使用 CampusMate。\n\n"
        f"你的注册验证码是：{code}\n"
        "验证码 10 分钟内有效。如果不是你本人操作，可以忽略这封邮件。"
    )
    try:
        send_email(email, "CampusMate 注册验证码", body)
    except MailNotConfigured:
        return code
    except AuthError:
        raise
    except (OSError, smtplib.SMTPException, UnicodeEncodeError) as error:
        raise AuthError(f"验证码邮件发送失败：{error}") from error
    return None


def send_password_reset_code(email: str) -> str | None:
    normalized = normalize_email(email)
    if not account_exists(normalized):
        raise AuthError("该邮箱尚未注册")
    code = create_verification_code(normalized)
    body = (
        "你正在重置 CampusMate 登录密码。\n\n"
        f"你的密码重置验证码是：{code}\n"
        "验证码 10 分钟内有效。如果不是你本人操作，请忽略这封邮件。"
    )
    try:
        send_email(normalized, "CampusMate 密码重置验证码", body)
    except MailNotConfigured:
        return code
    except AuthError:
        raise
    except (OSError, smtplib.SMTPException, UnicodeEncodeError) as error:
        raise AuthError(f"密码重置邮件发送失败：{error}") from error
    return None


def _consume_verification_code(
    connection: DatabaseConnection, email: str, code: str
) -> None:
    row = connection.execute(
        "SELECT code_hash, expires_at, attempts FROM verification_codes WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None:
        raise AuthError("请先发送邮箱验证码")
    if int(row["expires_at"]) < int(time.time()):
        raise AuthError("验证码已过期，请重新发送")
    if int(row["attempts"]) >= 5:
        raise AuthError("验证码尝试次数过多，请重新发送")
    if not hmac.compare_digest(str(row["code_hash"]), _hash_code(code.strip())):
        connection.execute(
            "UPDATE verification_codes SET attempts = attempts + 1 WHERE email = ?",
            (email,),
        )
        raise AuthError("验证码不正确")
    connection.execute("DELETE FROM verification_codes WHERE email = ?", (email,))


def register_user(email: str, password: str, code: str) -> dict[str, str]:
    normalized = normalize_email(email)
    if len(password) < 6:
        raise AuthError("密码至少需要 6 位")
    init_db()
    with _db() as connection:
        if account_exists(normalized):
            raise AuthError("该邮箱已经注册，请直接登录")
        _consume_verification_code(connection, normalized, code)
        salt = secrets.token_hex(16)
        user_id = _next_user_id(connection)
        connection.execute(
            """
            INSERT INTO users(email, user_id, password_hash, salt, verified, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (normalized, user_id, _hash_password(password, salt), salt, int(time.time())),
        )
    return {"email": normalized, "user_id": user_id}


def reset_password(email: str, code: str, new_password: str) -> None:
    normalized = normalize_email(email)
    if len(new_password) < 6:
        raise AuthError("密码至少需要 6 位")
    init_db()
    with _db() as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE email = ?", (normalized,)
        ).fetchone()
        if row is None:
            raise AuthError("该邮箱尚未注册")
        _consume_verification_code(connection, normalized, code)
        salt = secrets.token_hex(16)
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, salt = ?, verified = 1
            WHERE email = ?
            """,
            (_hash_password(new_password, salt), salt, normalized),
        )


def authenticate(email: str, password: str) -> dict[str, str]:
    normalized = normalize_email(email)
    init_db()
    with _db() as connection:
        row = connection.execute(
            "SELECT email, user_id, password_hash, salt, verified FROM users WHERE email = ?",
            (normalized,),
        ).fetchone()
    if row is None:
        raise AuthError("该邮箱尚未注册")
    if not int(row["verified"]):
        raise AuthError("该邮箱尚未完成验证")
    expected = _hash_password(password, str(row["salt"]))
    if not hmac.compare_digest(str(row["password_hash"]), expected):
        raise AuthError("密码不正确")
    return {"email": str(row["email"]), "user_id": str(row["user_id"])}


def save_profile(email: str, profile: Mapping[str, Any]) -> None:
    init_db()
    with _db() as connection:
        connection.execute(
            """
            INSERT INTO user_profiles(email, profile_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              profile_json = excluded.profile_json,
              updated_at = excluded.updated_at
            """,
            (
                normalize_email(email),
                json.dumps(dict(profile), ensure_ascii=False),
                int(time.time()),
            ),
        )


def load_registered_profiles() -> list[dict[str, Any]]:
    init_db()
    with _db() as connection:
        rows = connection.execute("SELECT profile_json FROM user_profiles").fetchall()
    return [json.loads(str(row["profile_json"])) for row in rows]


def email_for_user_id(user_id: str) -> str | None:
    init_db()
    with _db() as connection:
        row = connection.execute(
            "SELECT email FROM users WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return str(row["email"]) if row else None


def send_match_notification(
    recipient_email: str, *, partner_id: str, score: float
) -> str:
    body = (
        "你好，CampusMate 已为你找到一个匹配结果。\n\n"
        f"候选搭子匿名编号：{partner_id}\n"
        f"综合匹配度：{score:.1f}/100\n\n"
        "请回到 CampusMate 查看详情，并只在你愿意的情况下继续沟通。"
    )
    match_id = f"{recipient_email}:{partner_id}:{int(time.time())}"
    try:
        send_email(recipient_email, "CampusMate 匹配成功通知", body)
        status = "sent"
        message = "匹配通知邮件已发送"
    except MailNotConfigured as error:
        status = "not_configured"
        message = str(error)
    except AuthError as error:
        status = "failed"
        message = str(error)
    except (OSError, smtplib.SMTPException) as error:
        status = "failed"
        message = f"匹配通知邮件发送失败：{error}"
    init_db()
    with _db() as connection:
        next_notification_id = int(
            connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM notifications"
            ).fetchone()["next_id"]
        )
        connection.execute(
            """
            INSERT INTO notifications(
                id, recipient_email, match_id, status, message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                next_notification_id,
                normalize_email(recipient_email),
                match_id,
                status,
                message,
                int(time.time()),
            ),
        )
    return status


def require_login() -> dict[str, str]:
    restore_persistent_session()
    user = st.session_state.get("auth_user")
    if not user:
        st.switch_page("pages/login.py")
        st.stop()
    return dict(user)
