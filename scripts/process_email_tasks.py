"""Send queued CampusMate business notification emails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.email_tasks import process_email_tasks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sqlite-path", type=Path, default=None)
    arguments = parser.parse_args()
    print(
        json.dumps(
            process_email_tasks(limit=arguments.limit, sqlite_path=arguments.sqlite_path),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
