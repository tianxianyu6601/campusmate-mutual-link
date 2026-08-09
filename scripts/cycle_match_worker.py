"""Finalize overdue weekly match rounds and deliver queued result emails."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.email_tasks import process_email_tasks
from services.platform_service import ensure_cycle_match_round


def main() -> None:
    cycle = ensure_cycle_match_round()
    email_report = process_email_tasks(limit=100)
    print(
        json.dumps(
            {"cycle": cycle, "email": email_report},
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
