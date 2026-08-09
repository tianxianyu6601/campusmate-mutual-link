"""Idempotent database migrations shared by SQLite and PostgreSQL."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from services.database import (
    DEFAULT_SQLITE_PATH,
    DatabaseConnection,
    configured_database_url,
    transaction,
)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


BASE_SCHEMA = Migration(
    version=1,
    name="base_auth_schema",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
            created_at INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS verification_codes (
            email TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            email TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY,
            recipient_email TEXT NOT NULL,
            match_id TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS login_sessions (
            session_token_hash TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_login_sessions_email ON login_sessions(email)",
        "CREATE INDEX IF NOT EXISTS idx_login_sessions_expires ON login_sessions(expires_at)",
    ),
)


UNIFIED_PLATFORM_SCHEMA = Migration(
    version=2,
    name="unified_platform_schema",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            email TEXT PRIMARY KEY REFERENCES users(email) ON DELETE CASCADE,
            display_name TEXT NOT NULL CHECK (LENGTH(display_name) BETWEEN 1 AND 30),
            school TEXT NOT NULL DEFAULT '北京大学',
            department TEXT NOT NULL DEFAULT '',
            grade TEXT NOT NULL DEFAULT '',
            identity_label TEXT NOT NULL DEFAULT '',
            bio TEXT NOT NULL DEFAULT '',
            mbti TEXT NOT NULL DEFAULT '',
            introversion INTEGER NOT NULL DEFAULT 3 CHECK (introversion BETWEEN 1 AND 5),
            planning_style TEXT NOT NULL DEFAULT 'flexible',
            warm_up_level INTEGER NOT NULL DEFAULT 3 CHECK (warm_up_level BETWEEN 1 AND 5),
            group_size_preference TEXT NOT NULL DEFAULT 'any'
                CHECK (group_size_preference IN ('one_to_one', 'small_group', 'large_group', 'any')),
            self_description TEXT NOT NULL DEFAULT '',
            partner_expectation TEXT NOT NULL DEFAULT '',
            contact_email TEXT NOT NULL DEFAULT '',
            contact_wechat TEXT NOT NULL DEFAULT '',
            available_times_json TEXT NOT NULL DEFAULT '[]',
            preferred_locations_json TEXT NOT NULL DEFAULT '[]',
            max_distance_km INTEGER NOT NULL DEFAULT 5 CHECK (max_distance_km BETWEEN 0 AND 100),
            allow_cross_school INTEGER NOT NULL DEFAULT 0 CHECK (allow_cross_school IN (0, 1)),
            completion_percent INTEGER NOT NULL DEFAULT 0 CHECK (completion_percent BETWEEN 0 AND 100),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS profile_interests (
            email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
            category TEXT NOT NULL CHECK (category IN ('study', 'sport', 'social', 'entertainment', 'travel', 'custom')),
            tag TEXT NOT NULL CHECK (LENGTH(tag) BETWEEN 1 AND 40),
            created_at INTEGER NOT NULL,
            PRIMARY KEY (email, category, tag)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS profile_privacy (
            email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            visibility TEXT NOT NULL CHECK (visibility IN ('private', 'matched', 'activity_members', 'public')),
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (email, field_name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY,
            organizer_email TEXT NOT NULL REFERENCES users(email),
            category TEXT NOT NULL CHECK (category IN ('study', 'sport', 'social', 'entertainment', 'travel', 'share', 'custom')),
            custom_category TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL CHECK (LENGTH(title) BETWEEN 1 AND 60),
            description TEXT NOT NULL DEFAULT '' CHECK (LENGTH(description) <= 3000),
            image_url TEXT NOT NULL DEFAULT '',
            starts_at INTEGER NOT NULL,
            ends_at INTEGER,
            location_text TEXT NOT NULL CHECK (LENGTH(location_text) BETWEEN 1 AND 200),
            capacity INTEGER NOT NULL CHECK (capacity BETWEEN 2 AND 100),
            visibility TEXT NOT NULL DEFAULT 'campus' CHECK (visibility IN ('campus', 'public', 'invite')),
            approval_required INTEGER NOT NULL DEFAULT 1 CHECK (approval_required IN (0, 1)),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'full', 'ended', 'cancelled')),
            version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            CHECK (ends_at IS NULL OR ends_at > starts_at)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_activities_status_start ON activities(status, starts_at)",
        "CREATE INDEX IF NOT EXISTS idx_activities_organizer ON activities(organizer_email)",
        """
        CREATE TABLE IF NOT EXISTS activity_applications (
            application_id TEXT PRIMARY KEY,
            activity_id TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
            applicant_email TEXT NOT NULL REFERENCES users(email),
            reason TEXT NOT NULL DEFAULT '' CHECK (LENGTH(reason) <= 500),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
            reviewed_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE (activity_id, applicant_email)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_activity_applications_pending ON activity_applications(activity_id, status)",
        """
        CREATE TABLE IF NOT EXISTS activity_members (
            activity_id TEXT NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
            member_email TEXT NOT NULL REFERENCES users(email),
            role TEXT NOT NULL CHECK (role IN ('organizer', 'member')),
            joined_at INTEGER NOT NULL,
            PRIMARY KEY (activity_id, member_email)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_rounds (
            round_id TEXT PRIMARY KEY,
            name TEXT NOT NULL CHECK (LENGTH(name) BETWEEN 1 AND 80),
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned', 'open', 'closed', 'matching', 'published', 'cancelled')),
            registration_opens_at INTEGER NOT NULL,
            registration_closes_at INTEGER NOT NULL,
            results_at INTEGER NOT NULL,
            created_by_email TEXT NOT NULL REFERENCES users(email),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            CHECK (registration_closes_at > registration_opens_at),
            CHECK (results_at >= registration_closes_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_enrollments (
            round_id TEXT NOT NULL REFERENCES match_rounds(round_id) ON DELETE CASCADE,
            email TEXT NOT NULL REFERENCES users(email),
            status TEXT NOT NULL DEFAULT 'enrolled'
                CHECK (status IN ('enrolled', 'withdrawn', 'matched', 'unmatched')),
            enrolled_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (round_id, email)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_profile_snapshots (
            round_id TEXT NOT NULL REFERENCES match_rounds(round_id) ON DELETE CASCADE,
            email TEXT NOT NULL REFERENCES users(email),
            profile_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (round_id, email)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_results (
            result_id TEXT PRIMARY KEY,
            round_id TEXT NOT NULL REFERENCES match_rounds(round_id) ON DELETE CASCADE,
            score REAL NOT NULL CHECK (score BETWEEN 0 AND 100),
            explanation_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_result_members (
            result_id TEXT NOT NULL REFERENCES match_results(result_id) ON DELETE CASCADE,
            round_id TEXT NOT NULL REFERENCES match_rounds(round_id) ON DELETE CASCADE,
            email TEXT NOT NULL REFERENCES users(email),
            seat INTEGER NOT NULL CHECK (seat IN (1, 2)),
            PRIMARY KEY (result_id, email),
            UNIQUE (result_id, seat),
            UNIQUE (round_id, email)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_tasks (
            task_id TEXT PRIMARY KEY,
            recipient_email TEXT NOT NULL,
            template_key TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'sending', 'sent', 'failed', 'dead')),
            idempotency_key TEXT NOT NULL UNIQUE,
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
            last_error TEXT NOT NULL DEFAULT '',
            next_attempt_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            sent_at INTEGER
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_email_tasks_ready ON email_tasks(status, next_attempt_at)",
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id TEXT PRIMARY KEY,
            actor_email TEXT REFERENCES users(email),
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id, created_at)",
    ),
)


PROFILE_EXPERIENCE_SCHEMA = Migration(
    version=3,
    name="profile_experience_schema",
    statements=(
        "ALTER TABLE profiles ADD COLUMN avatar_data_url TEXT NOT NULL DEFAULT ''",
        """
        CREATE TABLE profile_interests_v3 (
            email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
            category TEXT NOT NULL CHECK (
                category IN (
                    'study', 'sport', 'social', 'entertainment',
                    'travel', 'share', 'custom'
                )
            ),
            tag TEXT NOT NULL CHECK (LENGTH(tag) BETWEEN 1 AND 40),
            created_at INTEGER NOT NULL,
            PRIMARY KEY (email, category, tag)
        )
        """,
        """
        INSERT INTO profile_interests_v3(email, category, tag, created_at)
        SELECT email, category, tag, created_at FROM profile_interests
        """,
        "DROP TABLE profile_interests",
        "ALTER TABLE profile_interests_v3 RENAME TO profile_interests",
    ),
)


ACTIVITY_WORKFLOW_SCHEMA = Migration(
    version=4,
    name="activity_workflow_schema",
    statements=(
        "ALTER TABLE activity_applications ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1)",
        """
        CREATE TABLE IF NOT EXISTS user_notifications (
            notification_id TEXT PRIMARY KEY,
            recipient_email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL CHECK (LENGTH(title) BETWEEN 1 AND 120),
            message TEXT NOT NULL DEFAULT '' CHECK (LENGTH(message) <= 1000),
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL,
            read_at INTEGER
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_user_notifications_inbox ON user_notifications(recipient_email, is_read, created_at)",
    ),
)


PROFILE_CONTACT_SCHEMA = Migration(
    version=5,
    name="profile_contact_schema",
    statements=(
        "ALTER TABLE profiles ADD COLUMN contact_qq TEXT NOT NULL DEFAULT ''",
    ),
)


ACTIVITY_CONTACT_SCHEMA = Migration(
    version=6,
    name="activity_contact_schema",
    statements=(
        "ALTER TABLE activities ADD COLUMN organizer_contact TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE activity_applications ADD COLUMN applicant_contact TEXT NOT NULL DEFAULT ''",
    ),
)


MIGRATIONS = (
    BASE_SCHEMA,
    UNIFIED_PLATFORM_SCHEMA,
    PROFILE_EXPERIENCE_SCHEMA,
    ACTIVITY_WORKFLOW_SCHEMA,
    PROFILE_CONTACT_SCHEMA,
    ACTIVITY_CONTACT_SCHEMA,
)
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version
_MIGRATION_CACHE: set[tuple[str, str]] = set()
_MIGRATION_LOCK = threading.RLock()


def _migration_identity(sqlite_path: Path | None) -> tuple[str, str]:
    database_url = configured_database_url()
    if database_url:
        digest = hashlib.sha256(database_url.encode("utf-8")).hexdigest()
        return ("postgresql", digest)
    path = Path(sqlite_path or DEFAULT_SQLITE_PATH).resolve()
    return ("sqlite", str(path))


def _ensure_migration_table(connection: DatabaseConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at INTEGER NOT NULL
        )
        """
    )


def run_migrations(sqlite_path: Path | None = None) -> list[int]:
    applied_now: list[int] = []
    with transaction(sqlite_path, immediate=True) as connection:
        _ensure_migration_table(connection)
        rows = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        applied = {int(row["version"]) for row in rows}

        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, int(time.time())),
            )
            applied_now.append(migration.version)

        if connection.backend == "sqlite":
            connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")
    with _MIGRATION_LOCK:
        _MIGRATION_CACHE.add(_migration_identity(sqlite_path))
    return applied_now


def ensure_migrations(sqlite_path: Path | None = None) -> None:
    """Run the idempotent migration check once per database and process."""

    identity = _migration_identity(sqlite_path)
    if identity in _MIGRATION_CACHE:
        return
    with _MIGRATION_LOCK:
        if identity not in _MIGRATION_CACHE:
            run_migrations(sqlite_path)


def current_schema_version(sqlite_path: Path | None = None) -> int:
    run_migrations(sqlite_path)
    with transaction(sqlite_path) as connection:
        row = connection.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()
    return int(row["version"] or 0) if row else 0
