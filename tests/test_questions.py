import unittest

from data import vocabulary as vocab
from questionnaire.questions import get_questions


class QuestionDefinitionTests(unittest.TestCase):
    def test_each_scenario_exposes_twenty_unique_questions(self):
        for match_type in vocab.MATCH_TYPES:
            questions = get_questions(match_type)
            ids = [question["id"] for question in questions]
            self.assertEqual(20, len(questions))
            self.assertEqual(len(ids), len(set(ids)))

    def test_activity_and_goal_options_are_scenario_specific(self):
        questions = {item["id"]: item for item in get_questions("sport")}
        activity_values = {item["value"] for item in questions["activity"]["options"]}
        goal_values = {item["value"] for item in questions["goal"]["options"]}
        self.assertEqual(set(vocab.ACTIVITIES["sport"]), activity_values)
        self.assertEqual(set(vocab.GOALS["sport"]), goal_values)
        self.assertNotIn("python", activity_values)

    def test_unknown_match_type_is_rejected(self):
        with self.assertRaises(ValueError):
            get_questions("dating")

    def test_open_world_questions_accept_user_defined_values(self):
        questions = {item["id"]: item for item in get_questions("study")}
        for question_id in ("activity", "acceptable_locations", "interests"):
            self.assertTrue(questions[question_id]["accept_new_options"])
        group_values = {
            item["value"] for item in questions["group_size_preference"]["options"]
        }
        self.assertEqual({"one_to_one", "either"}, group_values)


if __name__ == "__main__":
    unittest.main()
