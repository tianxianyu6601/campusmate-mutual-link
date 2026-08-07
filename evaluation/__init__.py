"""Feedback and experiment helpers for the CampusMate project."""

from .experiment import compare_algorithms, save_experiment_report
from .feedback import build_feedback, summarize_feedback
from .metrics import evaluate_matches, validate_pairing_integrity

__all__ = [
    "build_feedback",
    "compare_algorithms",
    "evaluate_matches",
    "save_experiment_report",
    "summarize_feedback",
    "validate_pairing_integrity",
]
