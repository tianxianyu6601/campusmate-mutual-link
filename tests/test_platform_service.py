from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from services.database import transaction
from services.migrations import run_migrations
from services.platform_service import (
    CapacityError,
    ConflictError,
    PermissionDenied,
    ValidationError,
    apply_to_activity,
    calculate_profile_completion,
    cancel_activity,
    create_activity,
    create_match_round,
    end_activity,
    enroll_in_match_round,
    get_activity,
    get_profile,
    get_visible_profile,
    leave_activity,
    list_activities,
    list_activity_applications,
    list_activity_members,
    list_user_notifications,
    mark_notification_read,
    publish_activity,
    remove_activity_member,
    review_activity_application,
    update_activity,
    upsert_profile,
    validate_profile_for_matching,
    withdraw_activity_application,
)


USERS = (
    ("owner@example.com", "U0051"),
    ("member1@example.com", "U0052"),
    ("member2@example.com", "U0053"),
)


class PlatformServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "platform.db"
        run_migrations(self.database)
        with transaction(self.database) as connection:
            for email, user_id in USERS:
                connection.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                    (email, user_id, "hash", "salt", 1, 1),
                )
        for email, _ in USERS:
            upsert_profile(
                email,
                {"display_name": email.split("@", 1)[0], "contact_email": email},
                privacy={"contact_email": "activity_members"},
                sqlite_path=self.database,
            )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def create_activity(self, *, capacity: int = 3) -> str:
        return create_activity(
            "owner@example.com",
            category="sport",
            title="周末羽毛球",
            description="测试活动",
            starts_at=int(time.time()) + 3600,
            location_text="邱德拔体育馆",
            capacity=capacity,
            sqlite_path=self.database,
        )

    def save_profile(self, email: str, name: str) -> None:
        upsert_profile(
            email,
            {
                "display_name": name,
                "available_times": ["周六下午"],
                "preferred_locations": ["校内"],
                "self_description": "慢热但熟悉后很健谈",
                "partner_expectation": "希望对方守时、沟通直接",
                "contact_email": email,
                "contact_qq": "123456",
                "completion_percent": 80,
            },
            interests=[("sport", "羽毛球"), ("study", "Python")],
            privacy={"contact_email": "activity_members", "contact_qq": "matched"},
            sqlite_path=self.database,
        )

    def test_profile_round_trip_keeps_interests_and_privacy(self) -> None:
        self.save_profile("member1@example.com", "小北")

        profile = get_profile("member1@example.com", sqlite_path=self.database)

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual("小北", profile["display_name"])
        self.assertEqual(["周六下午"], profile["available_times"])
        self.assertEqual(
            [
                {"category": "sport", "tag": "羽毛球"},
                {"category": "study", "tag": "Python"},
            ],
            profile["interests"],
        )
        self.assertEqual("123456", profile["contact_qq"])
        self.assertEqual(
            {"contact_email": "activity_members", "contact_qq": "matched"},
            profile["privacy"],
        )
        self.assertEqual(70, profile["completion_percent"])
        self.assertEqual([], validate_profile_for_matching("member1@example.com", sqlite_path=self.database))

    def test_completion_is_calculated_server_side(self) -> None:
        score = calculate_profile_completion(
            {
                "display_name": "小北",
                "school": "北京大学",
                "department": "",
                "identity_label": "",
                "bio": "",
                "available_times": ["周六下午"],
                "preferred_locations": ["校内"],
                "self_description": "慢热",
                "partner_expectation": "守时",
                "completion_percent": 100,
            },
            [("sport", "羽毛球")],
        )
        self.assertEqual(70, score)

    def test_profile_validation_rejects_unknown_interest_and_privacy(self) -> None:
        payload = {"display_name": "小北"}
        with self.assertRaisesRegex(ValidationError, "兴趣分类"):
            upsert_profile(
                "member1@example.com",
                payload,
                interests=[("unknown", "测试")],
                sqlite_path=self.database,
            )

        with self.assertRaisesRegex(ValidationError, "QQ号"):
            upsert_profile(
                "member1@example.com",
                {"display_name": "小北", "contact_qq": "QQ-123"},
                sqlite_path=self.database,
            )
        with self.assertRaisesRegex(ValidationError, "隐私"):
            upsert_profile(
                "member1@example.com",
                payload,
                privacy={"password": "public"},
                sqlite_path=self.database,
            )

    def test_activity_publish_and_apply_require_a_contact_method(self) -> None:
        upsert_profile(
            "owner@example.com",
            {"display_name": "发起人"},
            sqlite_path=self.database,
        )
        activity_values = {
            "category": "sport",
            "title": "联系方式校验",
            "description": "测试",
            "starts_at": int(time.time()) + 3600,
            "location_text": "自定义地点",
            "capacity": 3,
            "sqlite_path": self.database,
        }
        with self.assertRaisesRegex(ValidationError, "本次活动公开联系方式"):
            create_activity("owner@example.com", organizer_contact="", **activity_values)

        draft_id = create_activity(
            "owner@example.com", status="draft", organizer_contact="", **activity_values
        )
        with self.assertRaisesRegex(ValidationError, "本次活动公开联系方式"):
            publish_activity(draft_id, "owner@example.com", sqlite_path=self.database)

        published_id = create_activity(
            "owner@example.com",
            organizer_contact="微信：campusmate_owner",
            **activity_values,
        )
        detail = get_activity(
            published_id, "member1@example.com", sqlite_path=self.database
        )
        self.assertEqual("微信：campusmate_owner", detail["organizer_contact"])

        with self.assertRaisesRegex(ValidationError, "本次申请联系方式"):
            apply_to_activity(
                published_id,
                "member1@example.com",
                applicant_contact="",
                sqlite_path=self.database,
            )
        apply_to_activity(
            published_id,
            "member1@example.com",
            applicant_contact="QQ：123456",
            sqlite_path=self.database,
        )
        applications = list_activity_applications(
            published_id, "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual("QQ：123456", applications[0]["applicant_contact"])

    def test_avatar_validation_accepts_small_image_and_rejects_invalid_data(self) -> None:
        avatar_bytes = b"\x89PNG\r\n\x1a\n" + b"small-image"
        avatar = "data:image/png;base64," + base64.b64encode(avatar_bytes).decode("ascii")
        upsert_profile(
            "member1@example.com",
            {"display_name": "小北", "avatar_data_url": avatar},
            sqlite_path=self.database,
        )
        profile = get_profile("member1@example.com", sqlite_path=self.database)
        assert profile is not None
        self.assertEqual(avatar, profile["avatar_data_url"])

        with self.assertRaisesRegex(ValidationError, "头像"):
            upsert_profile(
                "member1@example.com",
                {"display_name": "小北", "avatar_data_url": "javascript:alert(1)"},
                sqlite_path=self.database,
            )

    def test_incomplete_profile_cannot_enroll_in_match_round(self) -> None:
        upsert_profile(
            "member1@example.com",
            {"display_name": "小北"},
            sqlite_path=self.database,
        )
        now = int(time.time())
        round_id = create_match_round(
            "owner@example.com",
            name="资料校验轮次",
            registration_opens_at=now - 60,
            registration_closes_at=now + 600,
            results_at=now + 1200,
            status="open",
            sqlite_path=self.database,
        )
        with self.assertRaisesRegex(ValidationError, "参加周期匹配前"):
            enroll_in_match_round(
                round_id, "member1@example.com", sqlite_path=self.database
            )

    def test_visible_profile_obeys_public_activity_and_match_rules(self) -> None:
        upsert_profile(
            "member1@example.com",
            {
                "display_name": "小北",
                "school": "北京大学",
                "bio": "只给自己看",
                "contact_email": "member1@example.com",
                "contact_qq": "123456",
            },
            interests=[("sport", "羽毛球")],
            privacy={
                "school": "public",
                "bio": "private",
                "interests": "activity_members",
                "contact_email": "matched",
                "contact_qq": "activity_members",
            },
            sqlite_path=self.database,
        )

        public_view = get_visible_profile(
            "member2@example.com", "member1@example.com", sqlite_path=self.database
        )
        assert public_view is not None
        self.assertEqual("北京大学", public_view["school"])
        self.assertNotIn("bio", public_view)
        self.assertNotIn("interests", public_view)
        self.assertNotIn("contact_email", public_view)

        activity_id = self.create_activity()
        with transaction(self.database) as connection:
            now = int(time.time())
            connection.execute(
                "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'member', ?)",
                (activity_id, "member1@example.com", now),
            )
            connection.execute(
                "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'member', ?)",
                (activity_id, "member2@example.com", now),
            )
        activity_view = get_visible_profile(
            "member2@example.com", "member1@example.com", sqlite_path=self.database
        )
        assert activity_view is not None
        self.assertEqual(
            [{"category": "sport", "tag": "羽毛球"}], activity_view["interests"]
        )
        self.assertNotIn("contact_email", activity_view)
        self.assertEqual("123456", activity_view["contact_qq"])

        now = int(time.time())
        with transaction(self.database) as connection:
            connection.execute(
                """
                INSERT INTO match_rounds(
                    round_id, name, status, registration_opens_at,
                    registration_closes_at, results_at, created_by_email,
                    created_at, updated_at
                ) VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?)
                """,
                (
                    "round_privacy", "隐私测试", now - 300, now - 200,
                    now - 100, "owner@example.com", now - 400, now - 400,
                ),
            )
            connection.execute(
                "INSERT INTO match_results(result_id, round_id, score, created_at) VALUES (?, ?, ?, ?)",
                ("result_privacy", "round_privacy", 88.0, now),
            )
            connection.execute(
                "INSERT INTO match_result_members(result_id, round_id, email, seat) VALUES (?, ?, ?, ?)",
                ("result_privacy", "round_privacy", "member1@example.com", 1),
            )
            connection.execute(
                "INSERT INTO match_result_members(result_id, round_id, email, seat) VALUES (?, ?, ?, ?)",
                ("result_privacy", "round_privacy", "member2@example.com", 2),
            )
        matched_view = get_visible_profile(
            "member2@example.com", "member1@example.com", sqlite_path=self.database
        )
        assert matched_view is not None
        self.assertEqual("member1@example.com", matched_view["contact_email"])

    def test_duplicate_application_is_blocked_and_email_is_idempotent(self) -> None:
        activity_id = self.create_activity()

        apply_to_activity(activity_id, "member1@example.com", sqlite_path=self.database)
        with self.assertRaisesRegex(ConflictError, "已经申请"):
            apply_to_activity(activity_id, "member1@example.com", sqlite_path=self.database)

        with closing(sqlite3.connect(self.database)) as connection:
            applications = int(
                connection.execute("SELECT COUNT(*) FROM activity_applications").fetchone()[0]
            )
            email_tasks = int(
                connection.execute("SELECT COUNT(*) FROM email_tasks").fetchone()[0]
            )
        self.assertEqual(1, applications)
        self.assertEqual(1, email_tasks)

    def test_activity_draft_publish_discovery_and_detail(self) -> None:
        start = int(time.time()) + 3600
        activity_id = create_activity(
            "owner@example.com",
            category="study",
            title="Python 复习局",
            description="一起复习期末重点",
            starts_at=start,
            location_text="理科一号楼",
            capacity=4,
            status="draft",
            organizer_contact="邮箱：owner@example.com",
            sqlite_path=self.database,
        )
        self.assertEqual(
            [], list_activities("member1@example.com", sqlite_path=self.database)
        )
        mine = list_activities(
            "owner@example.com", scope="mine", sqlite_path=self.database
        )
        self.assertEqual([activity_id], [item["activity_id"] for item in mine])
        self.assertEqual("draft", mine[0]["status"])

        publish_activity(activity_id, "owner@example.com", sqlite_path=self.database)
        discovered = list_activities(
            "member1@example.com",
            keyword="Python",
            categories=["study"],
            location="理科",
            statuses=["published"],
            sqlite_path=self.database,
        )
        self.assertEqual([activity_id], [item["activity_id"] for item in discovered])
        detail = get_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        self.assertEqual("Python 复习局", detail["title"])
        self.assertEqual(1, detail["member_count"])
        self.assertFalse(detail["is_organizer"])

    def test_invite_activity_is_only_visible_to_owner_or_member(self) -> None:
        activity_id = create_activity(
            "owner@example.com",
            category="social",
            title="小范围交流",
            description="仅邀请成员可见",
            starts_at=int(time.time()) + 3600,
            location_text="燕园",
            capacity=4,
            visibility="invite",
            sqlite_path=self.database,
        )
        self.assertEqual(
            [], list_activities("member1@example.com", sqlite_path=self.database)
        )
        with self.assertRaises(PermissionDenied):
            get_activity(activity_id, "member1@example.com", sqlite_path=self.database)
        with transaction(self.database) as connection:
            connection.execute(
                "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'member', ?)",
                (activity_id, "member1@example.com", int(time.time())),
            )
        self.assertEqual(
            [activity_id],
            [
                item["activity_id"]
                for item in list_activities(
                    "member1@example.com", sqlite_path=self.database
                )
            ],
        )

    def test_activity_update_version_permissions_and_end(self) -> None:
        activity_id = self.create_activity(capacity=4)
        original = get_activity(
            activity_id, "owner@example.com", sqlite_path=self.database
        )
        with self.assertRaises(PermissionDenied):
            update_activity(
                activity_id,
                "member1@example.com",
                category="sport",
                title="越权修改",
                description="",
                starts_at=int(time.time()) + 3600,
                location_text="燕园",
                capacity=4,
                expected_version=original["version"],
                sqlite_path=self.database,
            )
        update_activity(
            activity_id,
            "owner@example.com",
            category="sport",
            title="周末羽毛球（更新）",
            description="记得带球拍",
            starts_at=int(time.time()) + 7200,
            location_text="邱德拔体育馆",
            capacity=5,
            expected_version=original["version"],
            sqlite_path=self.database,
        )
        with self.assertRaisesRegex(ConflictError, "刷新"):
            update_activity(
                activity_id,
                "owner@example.com",
                category="sport",
                title="旧版本覆盖",
                description="",
                starts_at=int(time.time()) + 7200,
                location_text="燕园",
                capacity=4,
                expected_version=original["version"],
                sqlite_path=self.database,
            )
        end_activity(activity_id, "owner@example.com", sqlite_path=self.database)
        ended = get_activity(
            activity_id, "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual("ended", ended["status"])

    def test_activity_image_and_field_validation(self) -> None:
        valid_image = "data:image/png;base64," + base64.b64encode(
            b"\x89PNG\r\n\x1a\nactivity"
        ).decode("ascii")
        activity_id = create_activity(
            "owner@example.com",
            category="custom",
            custom_category="校园观鸟",
            title="未名湖观鸟",
            description="",
            image_url=valid_image,
            starts_at=int(time.time()) + 3600,
            location_text="未名湖",
            capacity=6,
            sqlite_path=self.database,
        )
        self.assertEqual(
            valid_image,
            get_activity(activity_id, "owner@example.com", sqlite_path=self.database)[
                "image_url"
            ],
        )
        with self.assertRaisesRegex(ValidationError, "活动图片"):
            create_activity(
                "owner@example.com",
                category="sport",
                title="坏图片",
                description="",
                image_url="data:image/png;base64,bm90LWEtcG5n",
                starts_at=int(time.time()) + 3600,
                location_text="燕园",
                capacity=3,
                sqlite_path=self.database,
            )

    def test_unauthorized_review_and_cancel_leave_state_unchanged(self) -> None:
        activity_id = self.create_activity()
        application_id = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )

        with self.assertRaises(PermissionDenied):
            review_activity_application(
                activity_id,
                application_id,
                "member2@example.com",
                approve=True,
                sqlite_path=self.database,
            )
        with self.assertRaises(PermissionDenied):
            cancel_activity(
                activity_id, "member2@example.com", sqlite_path=self.database
            )

        with closing(sqlite3.connect(self.database)) as connection:
            activity_status = connection.execute(
                "SELECT status FROM activities WHERE activity_id = ?", (activity_id,)
            ).fetchone()[0]
            application_status = connection.execute(
                "SELECT status FROM activity_applications WHERE application_id = ?",
                (application_id,),
            ).fetchone()[0]
        self.assertEqual("published", activity_status)
        self.assertEqual("pending", application_status)

    def test_capacity_check_prevents_over_approval(self) -> None:
        activity_id = self.create_activity(capacity=2)
        first = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        second = apply_to_activity(
            activity_id, "member2@example.com", sqlite_path=self.database
        )

        status = review_activity_application(
            activity_id,
            first,
            "owner@example.com",
            approve=True,
            sqlite_path=self.database,
        )
        self.assertEqual("approved", status)
        with self.assertRaises(CapacityError):
            review_activity_application(
                activity_id,
                second,
                "owner@example.com",
                approve=True,
                sqlite_path=self.database,
            )

        with closing(sqlite3.connect(self.database)) as connection:
            member_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM activity_members WHERE activity_id = ?",
                    (activity_id,),
                ).fetchone()[0]
            )
            second_status = connection.execute(
                "SELECT status FROM activity_applications WHERE application_id = ?",
                (second,),
            ).fetchone()[0]
        self.assertEqual(2, member_count)
        self.assertEqual("pending", second_status)

    def test_concurrent_approvals_never_overfill_activity(self) -> None:
        activity_id = self.create_activity(capacity=2)
        applications = [
            apply_to_activity(activity_id, email, sqlite_path=self.database)
            for email in ("member1@example.com", "member2@example.com")
        ]

        def approve(application_id: str) -> str:
            try:
                return review_activity_application(
                    activity_id,
                    application_id,
                    "owner@example.com",
                    approve=True,
                    sqlite_path=self.database,
                )
            except CapacityError:
                return "capacity_error"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(approve, applications))

        self.assertCountEqual(["approved", "capacity_error"], results)
        with transaction(self.database) as connection:
            member_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM activity_members WHERE activity_id = ?",
                    (activity_id,),
                ).fetchone()["count"]
            )
        self.assertEqual(2, member_count)

    def test_application_creates_owner_notice_and_durable_mail_task(self) -> None:
        self.save_profile("member1@example.com", "小北")
        activity_id = self.create_activity()

        application_id = apply_to_activity(
            activity_id,
            "member1@example.com",
            reason="想认识一起打球的同学",
            sqlite_path=self.database,
        )

        notices = list_user_notifications(
            "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual(1, len(notices))
        self.assertIn("小北", notices[0]["message"])
        with transaction(self.database) as connection:
            task = connection.execute(
                "SELECT status, payload_json FROM email_tasks WHERE recipient_email = ?",
                ("owner@example.com",),
            ).fetchone()
        self.assertEqual("queued", task["status"])
        self.assertIn(application_id, task["payload_json"])

    def test_pending_application_can_be_withdrawn_and_resubmitted(self) -> None:
        activity_id = self.create_activity()
        first_id = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        withdraw_activity_application(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        second_id = apply_to_activity(
            activity_id,
            "member1@example.com",
            reason="重新考虑后仍想参加",
            sqlite_path=self.database,
        )

        self.assertEqual(first_id, second_id)
        with transaction(self.database) as connection:
            row = connection.execute(
                "SELECT status, attempt_count, reason FROM activity_applications WHERE application_id = ?",
                (first_id,),
            ).fetchone()
            owner_task_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM email_tasks WHERE recipient_email = ?",
                    ("owner@example.com",),
                ).fetchone()["count"]
            )
        self.assertEqual("pending", row["status"])
        self.assertEqual(2, row["attempt_count"])
        self.assertEqual("重新考虑后仍想参加", row["reason"])
        self.assertEqual(2, owner_task_count)

    def test_no_approval_activity_joins_immediately_and_becomes_full(self) -> None:
        activity_id = create_activity(
            "owner@example.com",
            category="social",
            title="无需审核的咖啡聊天",
            description="",
            starts_at=int(time.time()) + 3600,
            location_text="新太阳学生中心",
            capacity=2,
            approval_required=False,
            sqlite_path=self.database,
        )

        application_id = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )

        with transaction(self.database) as connection:
            application = connection.execute(
                "SELECT status FROM activity_applications WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            activity = connection.execute(
                "SELECT status FROM activities WHERE activity_id = ?", (activity_id,)
            ).fetchone()
        self.assertEqual("approved", application["status"])
        self.assertEqual("full", activity["status"])
        self.assertTrue(
            get_activity(
                activity_id, "member1@example.com", sqlite_path=self.database
            )["is_member"]
        )

    def test_leave_and_remove_member_reopen_a_full_activity(self) -> None:
        activity_id = self.create_activity(capacity=2)
        application_id = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        review_activity_application(
            activity_id,
            application_id,
            "owner@example.com",
            approve=True,
            sqlite_path=self.database,
        )
        leave_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        self.assertEqual(
            "published",
            get_activity(
                activity_id, "owner@example.com", sqlite_path=self.database
            )["status"],
        )

        reapplied = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        review_activity_application(
            activity_id,
            reapplied,
            "owner@example.com",
            approve=True,
            sqlite_path=self.database,
        )
        with self.assertRaises(PermissionDenied):
            remove_activity_member(
                activity_id,
                "member1@example.com",
                "member2@example.com",
                sqlite_path=self.database,
            )
        remove_activity_member(
            activity_id,
            "member1@example.com",
            "owner@example.com",
            sqlite_path=self.database,
        )
        current = get_activity(
            activity_id, "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual("published", current["status"])
        self.assertEqual(1, current["member_count"])

    def test_application_and_roster_views_enforce_permissions(self) -> None:
        activity_id = self.create_activity()
        apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        applications = list_activity_applications(
            activity_id, "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual(1, len(applications))
        with self.assertRaises(PermissionDenied):
            list_activity_applications(
                activity_id, "member2@example.com", sqlite_path=self.database
            )
        with self.assertRaises(PermissionDenied):
            list_activity_members(
                activity_id, "member2@example.com", sqlite_path=self.database
            )
        self.assertEqual(
            1,
            len(
                list_activity_members(
                    activity_id, "owner@example.com", sqlite_path=self.database
                )
            ),
        )

    def test_cancel_rejects_pending_and_notifies_every_affected_user(self) -> None:
        activity_id = self.create_activity(capacity=3)
        pending = apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        approved = apply_to_activity(
            activity_id, "member2@example.com", sqlite_path=self.database
        )
        review_activity_application(
            activity_id,
            approved,
            "owner@example.com",
            approve=True,
            sqlite_path=self.database,
        )

        cancel_activity(activity_id, "owner@example.com", sqlite_path=self.database)

        with transaction(self.database) as connection:
            pending_status = connection.execute(
                "SELECT status FROM activity_applications WHERE application_id = ?",
                (pending,),
            ).fetchone()["status"]
        self.assertEqual("rejected", pending_status)
        self.assertTrue(
            any(
                item["notification_type"] == "activity_cancelled"
                for item in list_user_notifications(
                    "member1@example.com", sqlite_path=self.database
                )
            )
        )
        self.assertTrue(
            any(
                item["notification_type"] == "activity_cancelled"
                for item in list_user_notifications(
                    "member2@example.com", sqlite_path=self.database
                )
            )
        )

    def test_notifications_can_be_marked_read_individually_or_all_at_once(self) -> None:
        activity_id = self.create_activity()
        apply_to_activity(
            activity_id, "member1@example.com", sqlite_path=self.database
        )
        notices = list_user_notifications(
            "owner@example.com", sqlite_path=self.database
        )
        self.assertEqual(
            1,
            mark_notification_read(
                "owner@example.com",
                str(notices[0]["notification_id"]),
                sqlite_path=self.database,
            ),
        )
        self.assertTrue(
            list_user_notifications(
                "owner@example.com", sqlite_path=self.database
            )[0]["is_read"]
        )
        self.assertEqual(
            0,
            mark_notification_read(
                "owner@example.com", sqlite_path=self.database
            ),
        )

    def test_database_primary_key_rejects_duplicate_member(self) -> None:
        activity_id = self.create_activity()

        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.database) as connection:
                connection.execute(
                    "INSERT INTO activity_members(activity_id, member_email, role, joined_at) VALUES (?, ?, 'organizer', ?)",
                    (activity_id, "owner@example.com", int(time.time())),
                )

    def test_match_enrollment_is_unique_and_saves_snapshot(self) -> None:
        self.save_profile("member1@example.com", "小北")
        now = int(time.time())
        round_id = create_match_round(
            "owner@example.com",
            name="本周搭子匹配",
            registration_opens_at=now - 60,
            registration_closes_at=now + 600,
            results_at=now + 1200,
            status="open",
            sqlite_path=self.database,
        )

        enroll_in_match_round(
            round_id, "member1@example.com", sqlite_path=self.database
        )
        with self.assertRaisesRegex(ConflictError, "已经报名"):
            enroll_in_match_round(
                round_id, "member1@example.com", sqlite_path=self.database
            )

        with closing(sqlite3.connect(self.database)) as connection:
            enrollment_count = int(
                connection.execute("SELECT COUNT(*) FROM match_enrollments").fetchone()[0]
            )
            snapshot_count = int(
                connection.execute("SELECT COUNT(*) FROM match_profile_snapshots").fetchone()[0]
            )
        self.assertEqual(1, enrollment_count)
        self.assertEqual(1, snapshot_count)


if __name__ == "__main__":
    unittest.main()
