import unittest

from data.schema import ProfileValidationError, SCHEMA_VERSION, validate_profile
from questionnaire.profile_builder import build_profile


def valid_answers():
    return {
        "match_type": "study",
        "activity": "python",
        "available_times": ["wed_19_00", "wed_19_30", "wed_20_00"],
        "acceptable_locations": ["pku_library", "online"],
        "group_size_preference": "one_to_one",
        "self_level": "basic",
        "acceptable_partner_levels": ["novice", "basic", "intermediate"],
        "hard_restrictions": ["no_off_campus"],
        "goal": "exam_prep",
        "intensity": 3,
        "communication_style": "balanced",
        "planning_style": "planned",
        "supervision_preference": 4,
        "punctuality_importance": 5,
        "cancellation_tolerance": 2,
        "organization_role": "balanced",
        "interests": ["programming", "ai"],
        "self_description": "我习惯在晚间按计划完成学习任务。",
        "partner_expectation": "希望对方守时，并愿意交流学习进度。",
        "preference_priorities": ["time", "goal", "planning"],
    }


class ProfileBuilderTests(unittest.TestCase):
    def test_builds_valid_profile_with_derived_fields(self):
        profile = build_profile(valid_answers(), user_id="U0001")
        self.assertEqual(SCHEMA_VERSION, profile["schema_version"])
        self.assertEqual(60, profile["min_session_minutes"])
        self.assertFalse(profile["allow_off_campus"])
        self.assertAlmostEqual(1.0, sum(profile["preference_weights"].values()))
        self.assertTrue(validate_profile(profile).is_valid)

    def test_accepts_chinese_display_labels(self):
        answers = valid_answers()
        answers.update(
            {
                "match_type": "学习搭子",
                "activity": "Python学习",
                "acceptable_locations": ["北京大学图书馆", "线上"],
                "goal": "考试复习",
                "interests": ["编程", "人工智能", "编程"],
            }
        )
        profile = build_profile(answers, user_id="U0002")
        self.assertEqual("study", profile["match_type"])
        self.assertEqual("python", profile["activity"])
        self.assertEqual(["programming", "ai"], profile["interests"])

    def test_missing_hard_constraint_is_rejected(self):
        answers = valid_answers()
        answers.pop("available_times")
        with self.assertRaises(ProfileValidationError) as context:
            build_profile(answers, user_id="U0003")
        fields = {issue.field for issue in context.exception.result.issues}
        self.assertIn("available_times", fields)

    def test_category_mismatch_is_rejected(self):
        answers = valid_answers()
        answers["activity"] = "running"
        with self.assertRaises(ProfileValidationError):
            build_profile(answers, user_id="U0004")

    def test_unknown_priority_is_rejected(self):
        answers = valid_answers()
        answers["preference_priorities"] = ["time", "unknown_dimension"]
        with self.assertRaises(ProfileValidationError):
            build_profile(answers, user_id="U0004")

    def test_sensitive_field_is_rejected_by_strict_schema(self):
        profile = build_profile(valid_answers(), user_id="U0005")
        profile["wechat"] = "not-allowed"
        result = validate_profile(profile)
        self.assertFalse(result.is_valid)
        self.assertIn("sensitive_field", {issue.code for issue in result.issues})

    def test_custom_activity_location_and_interest_are_canonical_and_valid(self):
        answers = valid_answers()
        answers.update(
            {
                "activity": "相对论讨论",
                "acceptable_locations": ["海淀公园", "圆明园东门"],
                "hard_restrictions": [],
                "interests": ["量子计算"],
            }
        )
        profile = build_profile(answers, user_id="U0006")
        self.assertEqual("custom:相对论讨论", profile["activity"])
        self.assertEqual(
            ["haidian_park", "custom:圆明园东门"],
            profile["acceptable_locations"],
        )
        self.assertEqual(["custom:量子计算"], profile["interests"])
        self.assertTrue(profile["allow_off_campus"])
        self.assertTrue(validate_profile(profile).is_valid)

    def test_known_activity_from_wrong_match_type_is_not_recast_as_custom(self):
        answers = valid_answers()
        answers["activity"] = "running"
        with self.assertRaises(ProfileValidationError):
            build_profile(answers, user_id="U0007")


if __name__ == "__main__":
    unittest.main()
