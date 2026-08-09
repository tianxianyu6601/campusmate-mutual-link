"""Tests for Part 2 hard-constraint filtering."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from algorithm.hard_filter import pass_hard_constraints
from data.data_loader import load_users


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HardFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        users = load_users(PROJECT_ROOT / "data" / "users.csv")
        cls.left = users[0]
        cls.right = users[1]

    def _pair(self):
        return copy.deepcopy(self.left), copy.deepcopy(self.right)

    def test_compatible_seed_pair_passes(self) -> None:
        result = pass_hard_constraints(self.left, self.right)
        self.assertTrue(result.passed)
        self.assertGreaterEqual(len(result.common_times), 2)
        self.assertTrue(result.common_locations)

    def test_single_common_slot_is_not_enough_for_sixty_minutes(self) -> None:
        left, right = self._pair()
        left["available_times"] = ["mon_19_00"]
        right["available_times"] = ["mon_19_00"]
        left["min_session_minutes"] = 60
        right["min_session_minutes"] = 60
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)
        self.assertIn("没有满足最短时长的连续共同时间", result.reasons)

    def test_no_common_continuous_time_is_rejected(self) -> None:
        left, right = self._pair()
        left["available_times"] = ["mon_19_00", "mon_20_00"]
        right["available_times"] = ["mon_19_00", "mon_20_00"]
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)

    def test_no_common_location_is_rejected(self) -> None:
        left, right = self._pair()
        left["acceptable_locations"] = ["pku_library"]
        right["acceptable_locations"] = ["teaching_building"]
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)
        self.assertIn("没有双方都能接受的地点", result.reasons)

    def test_level_outside_acceptance_is_rejected(self) -> None:
        left, right = self._pair()
        left["acceptable_partner_levels"] = ["advanced"]
        right["self_level"] = "novice"
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)
        self.assertIn("活动水平不在双方可接受范围内", result.reasons)

    def test_high_intensity_restriction_is_rejected(self) -> None:
        left, right = self._pair()
        left["hard_restrictions"] = ["no_high_intensity"]
        right["intensity"] = 5
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)
        self.assertIn("不接受高强度活动", result.reasons)

    def test_same_custom_activity_and_location_can_match(self) -> None:
        left, right = self._pair()
        left["activity"] = right["activity"] = "custom:量子物理讨论"
        left["acceptable_locations"] = ["custom:圆明园东门"]
        right["acceptable_locations"] = ["custom:圆明园东门"]
        left["hard_restrictions"] = []
        right["hard_restrictions"] = []
        result = pass_hard_constraints(left, right)
        self.assertTrue(result.passed)
        self.assertEqual(("custom:圆明园东门",), result.common_locations)

    def test_custom_location_is_conservatively_blocked_by_no_off_campus(self) -> None:
        left, right = self._pair()
        left["activity"] = right["activity"] = "custom:量子物理讨论"
        left["acceptable_locations"] = ["custom:圆明园东门"]
        right["acceptable_locations"] = ["custom:圆明园东门"]
        left["hard_restrictions"] = ["no_off_campus"]
        right["hard_restrictions"] = []
        result = pass_hard_constraints(left, right)
        self.assertFalse(result.passed)
        self.assertIn("没有双方都能接受的地点", result.reasons)


if __name__ == "__main__":
    unittest.main()
