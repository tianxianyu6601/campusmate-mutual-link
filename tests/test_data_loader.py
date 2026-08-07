import tempfile
import unittest
from pathlib import Path

from data.data_loader import DataLoadError, load_users, save_users, summarize_dataset
from data.mock_data import generate_users


class DataLoaderTests(unittest.TestCase):
    def test_csv_round_trip_preserves_profiles(self):
        users = generate_users(10, seed=21)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            save_users(users, path)
            restored = load_users(path)
        self.assertEqual(users, restored)

    def test_summary_reports_expected_count(self):
        users = generate_users(20, seed=22)
        summary = summarize_dataset(users)
        self.assertEqual(20, summary["user_count"])
        self.assertTrue(summary["validation"]["is_valid"])
        self.assertEqual(20, sum(summary["match_type_counts"].values()))

    def test_extra_csv_column_is_rejected(self):
        users = generate_users(1, seed=23)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.csv"
            save_users(users, path)
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            lines[0] += ",unexpected"
            lines[1] += ",value"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(DataLoadError):
                load_users(path)

    def test_duplicate_user_ids_are_rejected_on_save(self):
        users = generate_users(2, seed=24)
        users[1]["user_id"] = users[0]["user_id"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DataLoadError):
                save_users(users, Path(directory) / "users.csv")


if __name__ == "__main__":
    unittest.main()
