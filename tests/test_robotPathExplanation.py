import unittest
from datetime import datetime
import tempfile, json as pyjson
import importlib
import sys
from typing import Any
from src.core.path import Path, PathStep
from evaluation.evaluate_outputs import evaluate_explanation
from src.logging.conversationLogger import save_conversation


def simulate_llm_response(prompt: str) -> str:
    return f"\nPrompt sent to LLM:\n{prompt}\n---\n(Simulated LLM response would appear here)\n"


class TestRobotPathExplanation(unittest.TestCase):
    def test_scenario_1(self) -> None:
        steps = [
            PathStep("A", datetime(2023, 5, 1, 8, 0), "Blocked by a fallen tree.", 0.5, 100),
            PathStep("B", datetime(2023, 5, 1, 8, 10), "Clear, but steep slope.", 1.2, 200),
            PathStep("C", datetime(2023, 5, 1, 8, 20), "Muddy, but passable.", 0.8, 150),
        ]
        path = Path(steps)
        user_question = "Which path should I take if I want the easiest route?"
        prompt = (
            "The robot has recorded the following path with environmental context:\n"
            + path.to_prompt()
            + f"\n\nQuestion: {user_question}\n"
            "Please answer based on the path and context above."
        )
        result = simulate_llm_response(prompt)
        self.assertIn("Prompt sent to LLM", result)

    def test_scenario_2(self) -> None:
        steps = [
            PathStep(
                "X",
                datetime(2023, 6, 10, 9, 0),
                "Flooded area, not recommended.",
                0.3,
                80,
            ),
            PathStep(
                "Y",
                datetime(2023, 6, 10, 9, 15),
                "Dry and wide, easy to cross.",
                2.0,
                250,
            ),
            PathStep("Z", datetime(2023, 6, 10, 9, 30), "Rocky, but no water.", 1.0, 200),
        ]
        path = Path(steps)
        user_question = "I have a heavy load. Which path is safest for my equipment?"
        prompt = (
            "The robot has recorded the following path with environmental context:\n"
            + path.to_prompt()
            + f"\n\nQuestion: {user_question}\n"
            "Please answer based on the path and context above."
        )
        result = simulate_llm_response(prompt)
        self.assertIn("Prompt sent to LLM", result)

    def test_scenario_3(self) -> None:
        steps = [
            PathStep("North", datetime(2023, 7, 15, 14, 0), "Icy, very slippery.", 0.6, 90),
            PathStep(
                "East",
                datetime(2023, 7, 15, 14, 5),
                "Dry, but longer distance.",
                1.5,
                300,
            ),
            PathStep(
                "West",
                datetime(2023, 7, 15, 14, 10),
                "Blocked by construction.",
                0.0,
                0,
            ),
        ]
        path = Path(steps)
        user_question = "I am in a hurry but want to avoid danger. Which direction should I go?"
        prompt = (
            "The robot has recorded the following path with environmental context:\n"
            + path.to_prompt()
            + f"\n\nQuestion: {user_question}\n"
            "Please answer based on the path and context above."
        )
        result = simulate_llm_response(prompt)
        self.assertIn("Prompt sent to LLM", result)

    def test_evaluation(self) -> None:
        explanation = "I avoided path A because it is marked as not usable due to snow in winter."
        expected_keywords = ["avoided", "not usable", "snow", "winter"]
        expected_answer = "I avoided path A because it is marked as not usable due to snow in winter."
        result = evaluate_explanation(explanation, expected_keywords, expected_answer)
        self.assertGreaterEqual(result["keyword_score"], 0.75)
        self.assertEqual(result["exact_match"], 1)
        self.assertGreater(result["final_score"], 0.7)

    def test_evaluation_no_key(self) -> None:
        explanation: str = "foo"
        expected_keywords: list[str] = []
        expected_answer: str = ""
        result = evaluate_explanation(explanation, expected_keywords, expected_answer)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["keyword_score"], 0.0)
        self.assertEqual(result["exact_match"], 0)
        self.assertGreaterEqual(result["final_score"], 0.0)

    def test_evaluation_short_explanation(self) -> None:
        explanation: str = "short"
        expected_keywords: list[str] = ["short"]
        expected_answer: str = ""
        result = evaluate_explanation(explanation, expected_keywords, expected_answer)
        self.assertIsInstance(result, dict)
        self.assertGreaterEqual(result["keyword_score"], 0.75)
        self.assertGreaterEqual(result["exact_match"], 0.0)
        self.assertGreaterEqual(result["final_score"], 0.5)

    def test_evaluation_no_expected_answer(self) -> None:
        explanation: str = "something"
        expected_keywords: list[str] = ["some"]
        expected_answer: str = ""
        result = evaluate_explanation(explanation, expected_keywords, expected_answer)
        self.assertIsInstance(result, dict)
        self.assertGreaterEqual(result["keyword_score"], 0.75)
        self.assertEqual(result["exact_match"], 0)
        self.assertGreaterEqual(result["final_score"], 0.5)

    def test_evaluation_exact_match_fail(self) -> None:
        explanation: str = "foo"
        expected_keywords: list[str] = ["foo"]
        expected_answer: str = "bar"
        result = evaluate_explanation(explanation, expected_keywords, expected_answer)
        self.assertGreaterEqual(result["keyword_score"], 0.75)
        self.assertEqual(result["exact_match"], 0)
        self.assertGreater(result["final_score"], 0.2)

    def test_pathstep_to_dict_and_prompt(self) -> None:
        step = PathStep(
            location="D",
            timestamp="2024-01-01T12:00:00",
            context="Dry and sunny",
            average_speed=2.5,
            length=300,
            terrain_features=None,
            energy_consumption=None,
            ecological_impact=None,
            seasonal_info={"summer": "perfect"},
        )
        d = step.to_dict()
        self.assertEqual(d["location"], "D")
        self.assertIn("summer", d["seasonal_info"])
        prompt = step.to_prompt()
        self.assertIn("Dry and sunny", prompt)
        self.assertIn("average speed", prompt)

    def test_path_add_step_and_to_dict(self) -> None:
        path = Path()
        step = PathStep("E", "2024-01-01T13:00:00", "Rainy", 1.0, 120)
        path.add_step(step)
        self.assertEqual(len(path.steps), 1)
        d = path.to_dict()
        self.assertIn("description", d)
        self.assertEqual(len(d["steps"]), 1)

    def test_path_from_json_file(self) -> None:
        steps: list[dict[str, Any]] = [
            {
                "location": "F",
                "timestamp": "2024-01-01T14:00:00",
                "context": "Windy",
                "average_speed": 1.8,
                "length": 180,
                "seasonal_info": {"winter": "difficult"},
            }
        ]
        scenario: dict[str, Any] = {"description": "Test scenario", "steps": steps}
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            pyjson.dump([scenario], tf)
            tf.flush()
            path = Path.from_json_file(tf.name, index=0)
            self.assertEqual(path.description, "Test scenario")
            self.assertEqual(len(path.steps), 1)
            self.assertEqual(path.steps[0].location, "F")

    def test_save_conversation_to_test_log(self) -> None:
        path = Path()
        step = PathStep("G", "2024-01-01T15:00:00", "Test log", 1.5, 140)
        path.add_step(step)
        conversation = [("What is the best path?", "The best path is G.")]
        context_log = ["fact for test log"]
        save_conversation(
            path,
            conversation,
            context_log,
            logDir="log/tests",
            filename="test_conversation_log.md",
        )

    def test_main_block(self) -> None:
        module_name = "tests.test_robotPathExplanation"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


if __name__ == "__main__":
    unittest.main()
