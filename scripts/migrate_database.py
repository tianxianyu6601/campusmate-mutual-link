"""Apply CampusMate database migrations without printing credentials."""

from __future__ import annotations

from services.database import backend_name
from services.migrations import current_schema_version, run_migrations


def main() -> None:
    applied = run_migrations()
    version = current_schema_version()
    applied_label = ", ".join(str(item) for item in applied) if applied else "none"
    print(f"backend={backend_name()} schema_version={version} applied={applied_label}")


if __name__ == "__main__":
    main()
