"""Tests for Part 2 public matching entry points."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from algorithm.baseline import interest_greedy_matching, random_matching
from algorithm.pipeline import run_global_matching, run_matching
from algorithm.graph_matching import max_weight_matching
from data.data_loader import load_users
from evaluation.metrics import validate_pairing_integrity


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MatchingPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.users = load_users(PROJECT_ROOT / "data" / "users.csv")

    def test_run_matching_skips_current_user_and_limits_results(self) -> None:
        result = run_matching(self.users[0], self.users, top_k=3)
        self.assertLessEqual(len(result), 3)
        for match in result:
            self.assertEqual(self.users[0]["user_id"], match["user_a"])
            self.assertNotEqual(match["user_a"], match["user_b"])
            self.assertTrue(0 <= match["score"] <= 100)
            self.assertTrue(match["reasons"])

    def test_no_compatible_candidates_returns_empty_list(self) -> None:
        candidates = []
        for user in self.users[1:5]:
            candidate = copy.deepcopy(user)
            candidate["match_type"] = "sport"
            candidate["activity"] = "running"
            candidate["goal"] = "fitness"
            candidates.append(candidate)
        self.assertEqual(run_matching(self.users[0], candidates), [])

    def test_global_matching_does_not_repeat_users(self) -> None:
        matches = run_global_matching(self.users)
        self.assertFalse(validate_pairing_integrity(matches))

    def test_odd_user_count_is_safe(self) -> None:
        matches = run_global_matching(self.users[:7])
        self.assertFalse(validate_pairing_integrity(matches))
        self.assertLessEqual(len(matches), 3)

    def test_baselines_return_valid_pairings(self) -> None:
        for matcher in (random_matching, interest_greedy_matching):
            matches = matcher(self.users)
            self.assertFalse(validate_pairing_integrity(matches))

    def test_generated_dataset_sizes_can_run(self) -> None:
        for filename in ("users_050.csv", "users_100.csv", "users_200.csv"):
            users = load_users(PROJECT_ROOT / "data" / "generated" / filename)
            matches = run_matching(users[0], users, top_k=3)
            self.assertLessEqual(len(matches), 3)
            self.assertTrue(all(0 <= match["score"] <= 100 for match in matches))

    def test_global_matching_is_deterministic_and_uses_selection_score(self) -> None:
        edges = [
            {"user_a": "A", "user_b": "B", "score": 90, "selection_score": 50},
            {"user_a": "C", "user_b": "D", "score": 90, "selection_score": 50},
            {"user_a": "A", "user_b": "C", "score": 80, "selection_score": 100},
            {"user_a": "B", "user_b": "D", "score": 80, "selection_score": 100},
        ]
        expected = {frozenset(("A", "C")), frozenset(("B", "D"))}
        for candidate_edges in (edges, list(reversed(edges))):
            selected = max_weight_matching(candidate_edges)
            pairs = {
                frozenset((str(item["user_a"]), str(item["user_b"])))
                for item in selected
            }
            self.assertEqual(expected, pairs)


if __name__ == "__main__":
    unittest.main()
