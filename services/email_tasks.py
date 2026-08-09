"""Durable delivery worker for business notification emails.

Activity state changes are committed before this worker runs. A temporary mail
provider failure therefore never rolls back an application or membership.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from services.auth import send_email
from services.database import DEFAULT_SQLITE_PATH, transaction
from services.migrations import run_migrations


EmailSender = Callable[[str, str, str], None]


def _render_email(template_key: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    title = str(payload.get("activity_title") or "校园活动")
    applicant = str(payload.get("applicant_name") or "一位校园用户")
    reason = str(payload.get("reason") or "未填写申请说明")
    applicant_contact = str(payload.get("applicant_contact") or "未填写")
    round_name = str(payload.get("round_name") or "本轮周期匹配")
    partner_name = str(payload.get("partner_name") or "一位新搭子")
    match_score = float(payload.get("score") or 0)
    templates = {
        "activity_application_created": (
            "CampusMate：收到新的活动申请",
            f"{applicant} 申请加入“{title}”。\n\n"
            f"申请联系方式：{applicant_contact}\n申请说明：{reason}\n\n"
            "请登录 CampusMate 处理申请。",
        ),
        "activity_application_approved": (
            "CampusMate：活动申请已通过",
            f"你对“{title}”的申请已通过，现在已经是活动成员。请登录 CampusMate 查看活动详情。",
        ),
        "activity_application_rejected": (
            "CampusMate：活动申请结果",
            f"你对“{title}”的申请未通过。你仍可以在组局广场发现其他活动。",
        ),
        "activity_member_removed": (
            "CampusMate：活动成员变更",
            f"发起人已将你移出“{title}”。请登录 CampusMate 查看最新状态。",
        ),
        "activity_cancelled": (
            "CampusMate：活动已取消",
            f"“{title}”已由发起人取消。请登录 CampusMate 查看其他活动。",
        ),
        "cycle_match_published": (
            "CampusMate：本轮搭子匹配结果已公布",
            f"{round_name} 已经完成匹配。\n\n"
            f"你的搭子：{partner_name}\n"
            f"综合匹配度：{match_score:.1f}/100\n\n"
            "请登录 CampusMate 查看共同时间、地点、联系方式和破冰建议。",
        ),
    }
    return templates.get(
        template_key,
        ("CampusMate：你有一条新消息", f"与“{title}”有关的状态已经更新，请登录 CampusMate 查看。"),
    )


def _claim_tasks(path: Path, limit: int, now: int) -> list[dict[str, Any]]:
    stale_before = now - 10 * 60
    with transaction(path, immediate=True) as connection:
        rows = connection.execute(
            connection.select_for_update(
                """
                SELECT * FROM email_tasks
                WHERE attempts < max_attempts
                  AND (
                    (status IN ('queued', 'failed') AND next_attempt_at <= ?)
                    OR (status = 'sending' AND updated_at <= ?)
                  )
                ORDER BY created_at, task_id
                LIMIT ?
                """
            ),
            (now, stale_before, limit),
        ).fetchall()
        tasks = [dict(row) for row in rows]
        for task in tasks:
            connection.execute(
                """
                UPDATE email_tasks
                SET status = 'sending', attempts = attempts + 1,
                    last_error = '', updated_at = ?
                WHERE task_id = ?
                """,
                (now, str(task["task_id"])),
            )
            task["attempts"] = int(task["attempts"]) + 1
    return tasks


def process_email_tasks(
    *,
    limit: int = 10,
    sender: EmailSender = send_email,
    sqlite_path: Path | None = None,
) -> dict[str, int]:
    """Deliver ready outbox tasks and return delivery counters."""

    path = Path(sqlite_path or DEFAULT_SQLITE_PATH)
    run_migrations(path)
    clean_limit = max(1, min(int(limit), 100))
    tasks = _claim_tasks(path, clean_limit, int(time.time()))
    sent = 0
    failed = 0
    dead = 0
    for task in tasks:
        task_id = str(task["task_id"])
        try:
            raw_payload = json.loads(str(task["payload_json"]))
            payload = raw_payload if isinstance(raw_payload, dict) else {}
            subject, body = _render_email(str(task["template_key"]), payload)
            sender(str(task["recipient_email"]), subject, body)
        except Exception as error:
            attempts = int(task["attempts"])
            max_attempts = int(task["max_attempts"])
            status = "dead" if attempts >= max_attempts else "failed"
            retry_at = int(time.time()) + min(3600, 30 * (2 ** max(0, attempts - 1)))
            message = f"{type(error).__name__}: {error}"[:1000]
            with transaction(path, immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE email_tasks
                    SET status = ?, last_error = ?, next_attempt_at = ?, updated_at = ?
                    WHERE task_id = ? AND status = 'sending'
                    """,
                    (status, message, retry_at, int(time.time()), task_id),
                )
            if status == "dead":
                dead += 1
            else:
                failed += 1
            continue

        with transaction(path, immediate=True) as connection:
            now = int(time.time())
            connection.execute(
                """
                UPDATE email_tasks
                SET status = 'sent', last_error = '', sent_at = ?, updated_at = ?
                WHERE task_id = ? AND status = 'sending'
                """,
                (now, now, task_id),
            )
        sent += 1
    return {"claimed": len(tasks), "sent": sent, "failed": failed, "dead": dead}
