import unittest

from data.data_loader import load_users
from services.matching_adapter import (
    MatchingContractError,
    backend_status,
    normalize_match,
    run_matching,
)


class MatchingAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.users = load_users("data/users.csv")
        cls.current = cls.users[0]

    def test_reports_part2_backend_without_crashing(self):
        status = backend_status()
        self.assertTrue(status["available"])
        self.assertEqual("algorithm.pipeline.run_matching", status["entry_point"])

    def test_runs_real_part2_without_demo_mode(self):
        result = run_matching(self.current, self.users, top_k=2)
        self.assertEqual("part2", result["mode"])
        self.assertEqual("algorithm.pipeline.run_matching", result["algorithm"])
        self.assertLessEqual(len(result["matches"]), 2)

    def test_demo_flag_does_not_override_real_backend(self):
        result = run_matching(
            self.current,
            self.users,
            top_k=2,
            allow_demo=True,
        )
        self.assertEqual("part2", result["mode"])
        self.assertEqual(self.current["user_id"], result["query_user_id"])
        self.assertEqual([], result["warnings"])
        self.assertLessEqual(len(result["matches"]), 2)
        for match in result["matches"]:
            self.assertIn(self.current["user_id"], {match["user_a"], match["user_b"]})
            self.assertGreaterEqual(match["score"], 0)
            self.assertLessEqual(match["score"], 100)

    def test_injected_backend_is_normalized_and_sorted(self):
        other_ids = [user["user_id"] for user in self.users[1:3]]

        def backend(current_profile, candidates, *, top_k):
            del candidates, top_k
            return {
                "matches": [
                    {
                        "user_a": current_profile["user_id"],
                        "user_b": other_ids[0],
                        "score": 70,
                        "dimension_scores": {"time": 80},
                        "reasons": ["测试结果一"],
                    },
                    {
                        "user_a": current_profile["user_id"],
                        "user_b": other_ids[1],
                        "score": 90,
                        "dimension_scores": {"time": 95},
                        "reasons": ["测试结果二"],
                    },
                ]
            }

        result = run_matching(
            self.current,
            self.users,
            top_k=2,
            backend=backend,
        )
        self.assertEqual("part2", result["mode"])
        self.assertEqual([90.0, 70.0], [item["score"] for item in result["matches"]])

    def test_rejects_out_of_range_score(self):
        with self.assertRaises(MatchingContractError):
            normalize_match(
                {
                    "user_a": self.current["user_id"],
                    "user_b": self.users[1]["user_id"],
                    "score": 101,
                    "dimension_scores": {"time": 80},
                    "reasons": ["无效分数测试"],
                },
                query_user_id=self.current["user_id"],
            )


if __name__ == "__main__":
    unittest.main()
