"""Email-based account, verification, and notification helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Mapping

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "campusmate_app.db"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_TTL_SECONDS = 10 * 60


class AuthError(RuntimeError):
    """Raised for expected account-flow failures."""


class MailNotConfigured(RuntimeError):
    """Raised when SMTP settings are missing."""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _db() -> sqlite3.Connection:
    connection = _connect()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with _db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verification_codes (
                email TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                email TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_email TEXT NOT NULL,
                match_id TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )


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


def _next_user_id(connection: sqlite3.Connection) -> str:
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
    config = _smtp_config()
    message = EmailMessage()
    message["From"] = str(config["from_email"])
    message["To"] = normalize_email(to_email)
    message["Subject"] = subject
    message.set_content(body)

    failures: list[str] = []
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
            failures.append(f"{_describe_attempt(attempt)} -> {error}")
    attempted = "；".join(failures)
    raise AuthError(
        "验证码邮件发送失败：SMTP 服务器断开或连接失败。"
        f"已尝试：{attempted}"
    )


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


def register_user(email: str, password: str, code: str) -> dict[str, str]:
    normalized = normalize_email(email)
    if len(password) < 6:
        raise AuthError("密码至少需要 6 位")
    init_db()
    with _db() as connection:
        row = connection.execute(
            "SELECT code_hash, expires_at, attempts FROM verification_codes WHERE email = ?",
            (normalized,),
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
                (normalized,),
            )
            raise AuthError("验证码不正确")
        if account_exists(normalized):
            raise AuthError("该邮箱已经注册，请直接登录")
        salt = secrets.token_hex(16)
        user_id = _next_user_id(connection)
        connection.execute(
            """
            INSERT INTO users(email, user_id, password_hash, salt, verified, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (normalized, user_id, _hash_password(password, salt), salt, int(time.time())),
        )
        connection.execute("DELETE FROM verification_codes WHERE email = ?", (normalized,))
    return {"email": normalized, "user_id": user_id}


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
    except (OSError, smtplib.SMTPException) as error:
        status = "failed"
        message = f"匹配通知邮件发送失败：{error}"
    init_db()
    with _db() as connection:
        connection.execute(
            """
            INSERT INTO notifications(recipient_email, match_id, status, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (normalize_email(recipient_email), match_id, status, message, int(time.time())),
        )
    return status


def require_login() -> dict[str, str]:
    user = st.session_state.get("auth_user")
    if not user:
        st.warning("请先使用邮箱登录或注册。")
        if st.button("去登录", type="primary"):
            st.switch_page("pages/login.py")
        st.stop()
    return dict(user)
