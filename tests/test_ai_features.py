"""Tests for Member 4's offline AI explanation features."""

from __future__ import annotations

import unittest
from pathlib import Path

from ai.explanation import generate_match_explanation
from ai.icebreaker import generate_icebreakers
from ai.text_similarity import bidirectional_text_scores, text_similarity, tokenize
from data.data_loader import load_users


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TextSimilarityTests(unittest.TestCase):
    def test_tokenize_supports_chinese_and_english(self) -> None:
        tokens = tokenize("一起学习 Python 编程")
        self.assertIn("python", tokens)
        self.assertIn("学习", tokens)

    def test_identical_text_has_maximum_similarity(self) -> None:
        self.assertEqual(text_similarity("一起复习 Python", "一起复习 Python"), 100.0)

    def test_directional_scores_stay_in_range(self) -> None:
        users = load_users(PROJECT_ROOT / "data" / "users.csv")
        scores = bidirectional_text_scores(users[0], users[1])
        self.assertEqual(set(scores), {"a_to_b", "b_to_a"})
        self.assertTrue(all(0 <= score <= 100 for score in scores.values()))


class ExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.users = load_users(PROJECT_ROOT / "data" / "users.csv")

    def test_explanation_is_non_empty_and_limited(self) -> None:
        reasons = generate_match_explanation(self.users[0], self.users[1], limit=3)
        self.assertGreaterEqual(len(reasons), 1)
        self.assertLessEqual(len(reasons), 3)

    def test_icebreakers_are_non_empty_and_privacy_safe(self) -> None:
        prompts = generate_icebreakers(self.users[0], self.users[1])
        self.assertEqual(len(prompts), 3)
        self.assertTrue(all(prompt.strip() for prompt in prompts))
        self.assertFalse(any("微信" in prompt or "手机号" in prompt for prompt in prompts))


if __name__ == "__main__":
    unittest.main()
