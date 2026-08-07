"""Tests for Member 4's feedback and experiment-evaluation helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.experiment import compare_algorithms, save_experiment_report
from evaluation.feedback import build_feedback, summarize_feedback
from evaluation.metrics import evaluate_matches, validate_pairing_integrity


MATCHES = [
    {"user_a": "U0001", "user_b": "U0002", "score": 88.0},
    {"user_a": "U0003", "user_b": "U0004", "score": 76.0},
]


class FeedbackTests(unittest.TestCase):
    def test_feedback_summary(self) -> None:
        records = [
            build_feedback(
                match_id="U0001-U0002",
                match_score=4,
                explanation_helpfulness=5,
                would_meet_again=True,
            ),
            build_feedback(
                match_id="U0003-U0004",
                match_score=2,
                explanation_helpfulness=3,
                would_meet_again=False,
            ),
        ]
        summary = summarize_feedback(records)
        self.assertEqual(summary["response_count"], 2)
        self.assertEqual(summary["meet_again_rate"], 50.0)

    def test_invalid_feedback_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_feedback(
                match_id="U0001-U0002",
                match_score=6,
                explanation_helpfulness=3,
                would_meet_again=True,
            )


class MetricTests(unittest.TestCase):
    def test_evaluate_matches(self) -> None:
        report = evaluate_matches(MATCHES, participant_count=5)
        self.assertEqual(report["pair_count"], 2)
        self.assertEqual(report["match_rate"], 80.0)
        self.assertEqual(report["integrity_violation_count"], 0)

    def test_repeated_user_is_detected(self) -> None:
        repeated = [*MATCHES, {"user_a": "U0002", "user_b": "U0005", "score": 81.0}]
        self.assertEqual(len(validate_pairing_integrity(repeated)), 1)


class ExperimentTests(unittest.TestCase):
    def test_compare_and_save_report(self) -> None:
        users = [{"user_id": f"U{index:04d}"} for index in range(1, 5)]
        report = compare_algorithms(users, {"fixture": lambda _: MATCHES})
        self.assertEqual(report[0]["algorithm"], "fixture")
        with tempfile.TemporaryDirectory() as directory:
            path = save_experiment_report(report, Path(directory) / "report.json")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
