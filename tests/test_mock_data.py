import unittest

from data.data_loader import validate_dataset
from data.mock_data import generate_users


class MockDataTests(unittest.TestCase):
    def test_generation_is_reproducible(self):
        self.assertEqual(generate_users(12, seed=7), generate_users(12, seed=7))

    def test_generation_has_expected_coverage(self):
        users = generate_users(50, seed=11)
        self.assertEqual(50, len(users))
        self.assertEqual(50, len({user["user_id"] for user in users}))
        self.assertEqual({"study", "sport", "interest"}, {user["match_type"] for user in users})
        self.assertGreaterEqual(len({user["activity"] for user in users}), 15)
        self.assertTrue(validate_dataset(users)["is_valid"])

    def test_generated_pairs_have_a_compatible_candidate(self):
        users = generate_users(50, seed=13)
        compatible_users = 0
        for user in users:
            for other in users:
                if user["user_id"] == other["user_id"]:
                    continue
                if user["match_type"] != other["match_type"]:
                    continue
                if user["activity"] != other["activity"]:
                    continue
                if not set(user["available_times"]) & set(other["available_times"]):
                    continue
                if not set(user["acceptable_locations"]) & set(other["acceptable_locations"]):
                    continue
                if other["self_level"] not in user["acceptable_partner_levels"]:
                    continue
                compatible_users += 1
                break
        self.assertGreaterEqual(compatible_users, 40)

    def test_invalid_count_is_rejected(self):
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                generate_users(value)


if __name__ == "__main__":
    unittest.main()
