import json
import unittest
from pathlib import Path

from data.data_loader import load_users, validate_dataset


GENERATED_DIR = Path(__file__).resolve().parents[1] / "data" / "generated"


class GeneratedDatasetQualityTests(unittest.TestCase):
    def test_committed_datasets_exist_and_validate(self):
        for size in (50, 100, 200):
            path = GENERATED_DIR / f"users_{size:03d}.csv"
            self.assertTrue(path.exists(), path)
            users = load_users(path)
            self.assertEqual(size, len(users))
            self.assertTrue(validate_dataset(users)["is_valid"])

    def test_baseline_alias_matches_fifty_user_dataset(self):
        baseline = load_users(GENERATED_DIR.parent / "users.csv")
        fifty = load_users(GENERATED_DIR / "users_050.csv")
        self.assertEqual(fifty, baseline)

    def test_datasets_are_nested_for_scale_comparison(self):
        fifty = load_users(GENERATED_DIR / "users_050.csv")
        hundred = load_users(GENERATED_DIR / "users_100.csv")
        two_hundred = load_users(GENERATED_DIR / "users_200.csv")
        self.assertEqual(fifty, hundred[:50])
        self.assertEqual(hundred, two_hundred[:100])

    def test_quality_report_records_reproducibility_metadata(self):
        report = json.loads(
            (GENERATED_DIR / "quality_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual("1.0.0", report["metadata"]["schema_version"])
        self.assertEqual(20260802, report["metadata"]["seed"])
        self.assertEqual([50, 100, 200], report["metadata"]["sizes"])


if __name__ == "__main__":
    unittest.main()
