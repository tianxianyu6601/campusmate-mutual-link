"""Tests for Part 2 directional and reciprocal scoring."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from algorithm.reciprocal_score import harmonic_mean, reciprocal_match_score
from algorithm.scoring import directional_dimension_scores, directional_score
from data import vocabulary as vocab
from data.data_loader import load_users


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _weights(active_dimension: str) -> dict[str, float]:
    return {
        dimension: 1.0 if dimension == active_dimension else 0.0
        for dimension in vocab.PREFERENCE_DIMENSIONS
    }


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        users = load_users(PROJECT_ROOT / "data" / "users.csv")
        cls.left = users[0]
        cls.right = users[1]

    def test_directional_score_uses_owner_weights(self) -> None:
        left = copy.deepcopy(self.left)
        right = copy.deepcopy(self.right)
        left["preference_weights"] = _weights("time")
        right["preference_weights"] = _weights("interest")

        left_dimensions = directional_dimension_scores(left, right, text_score=0)
        right_dimensions = directional_dimension_scores(right, left, text_score=0)

        self.assertEqual(
            directional_score(left, right, text_score=0),
            left_dimensions["time"],
        )
        self.assertEqual(
            directional_score(right, left, text_score=0),
            right_dimensions["interest"],
        )
        self.assertNotEqual(
            directional_score(left, right, text_score=0),
            directional_score(right, left, text_score=0),
        )

    def test_reciprocal_scores_stay_in_range(self) -> None:
        result = reciprocal_match_score(self.left, self.right)
        self.assertTrue(0 <= result["score"] <= 100)
        self.assertEqual(
            set(result["dimension_scores"]),
            set(vocab.PREFERENCE_DIMENSIONS),
        )
        self.assertTrue(
            all(0 <= score <= 100 for score in result["dimension_scores"].values())
        )

    def test_harmonic_mean_penalizes_one_sided_match(self) -> None:
        self.assertEqual(harmonic_mean(100, 0), 0.0)
        self.assertLess(harmonic_mean(95, 30), 60)


if __name__ == "__main__":
    unittest.main()
