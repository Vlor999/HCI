import unittest
from unittest.mock import patch, MagicMock
from typing import Any
from src.core.path import Path, PathStep
from src.config.constants import LOG_TESTS_DIR
from src.interface.ioConsole import (
    ask_question,
    print_path,
    print_answer,
    select_or_edit_question,
)
from src.logging.conversationLogger import save_conversation


class TestCoverage(unittest.TestCase):
    def test_path_class(self) -> None:
        path = Path()
        step = PathStep("Test", "2024-01-01T00:00:00", "test context", 1.0, 10)
        path.add_step(step)
        self.assertEqual(len(path.steps), 1)
        self.assertIn("Test", path.to_prompt())
        self.assertIsInstance(step.to_dict(), dict)
        self.assertIsInstance(step.to_prompt(), str)
        self.assertIsInstance(path.to_dict(), dict)

    def test_pathstep_seasonal_info(self) -> None:
        step: PathStep = PathStep(
            "Test", "2024-01-01T00:00:00", "test seasonal information", 1.0, 10, seasonal_info="winter"
        )
        self.assertIsInstance(step.seasonal_info, dict)

    def test_pathstep_toprompt_if_branch(self) -> None:
        step: PathStep = PathStep(
            "Test",
            "2024-01-01T00:00:00",
            "test seasonal information",
            1.0,
            10,
            terrain_features={"terrain": "rocks", "rise": "15%"},
            energy_consumption="13",
            ecological_impact="76kg",
            seasonal_info="winter",
            hash_value=23818,
        )
        output = step.to_prompt()
        self.assertIsInstance(output, str)
        self.assertTrue("terrain:" in output)
        self.assertTrue("energy" in output)
        self.assertTrue("eco-impact:" in output)
        self.assertTrue("season:" in output)
        self.assertTrue("Hash:" in output)

    def test_save_conversation(self) -> None:
        path = Path()
        step = PathStep("Test", "2024-01-01T00:00:00", "test context", 1.0, 10)
        path.add_step(step)
        conversation = [("What is the best path?", "The best path is Test.")]
        context_log = ["now the path is dry"]
        save_conversation(
            path,
            conversation,
            context_log,
            logDir=LOG_TESTS_DIR,
            filename="test_conversation_log.md",
        )

    def test_io_console(self) -> None:
        path = Path()
        print_path(path)
        print_answer("Sample answer")

    def test_pathstep_from_dict(self) -> None:
        d: dict[str, Any] = {
            "location": "A",
            "timestamp": "2024-01-01T00:00:00",
            "context": "ctx",
            "average_speed": 1.0,
            "length": 10,
            "seasonal_info": {"summer": "ok"},
        }
        step = PathStep.from_dict(d)
        self.assertEqual(step.location, "A")
        self.assertEqual(step.context, "ctx")
        self.assertEqual(step.average_speed, 1.0)
        self.assertEqual(step.length, 10)
        self.assertIn("summer", step.seasonal_info)

    def test_path_to_dict_and_prompt(self) -> None:
        path = Path()
        step = PathStep("B", "2024-01-01T01:00:00", "ctx2", 2.0, 20)
        path.add_step(step)
        d = path.to_dict()
        self.assertIn("description", d)
        self.assertIn("steps", d)
        prompt = path.to_prompt()
        self.assertIn("B", prompt)

    def test_select_or_edit_question_empty(self) -> None:
        self.assertIsNone(select_or_edit_question([]))

    @patch("src.interface.ioConsole.text")
    def test_ioconsole_ask_question(self, mock_text: MagicMock) -> None:
        mock_text.return_value.ask.return_value = "What's the current season ?"
        output: str = ask_question()
        self.assertIsInstance(output, str)
        self.assertEqual(output, "What's the current season ?")

    @patch("src.interface.ioConsole.text")
    @patch("src.interface.ioConsole.select")
    def test_select_or_edit_question_cancel(self, mock_select: MagicMock, mock_text: MagicMock) -> None:
        mock_select.return_value.ask.return_value = None
        mock_text.return_value.ask.return_value = None

        result = select_or_edit_question(["Q1", "Q2"])
        self.assertIsNone(result)

    @patch("src.interface.ioConsole.os.isatty", return_value=False)
    def test_select_or_edit_question_non_interactive(self, mock_isatty: MagicMock) -> None:
        result = select_or_edit_question(["Q1", "Q2"])
        self.assertIsNone(result)

    @patch("src.interface.ioConsole.os.isatty", return_value=True)
    @patch("src.interface.ioConsole.text")
    @patch("src.interface.ioConsole.select")
    def test_select_or_edit_question(
        self, mock_select: MagicMock, mock_text: MagicMock, mock_isatty: MagicMock
    ) -> None:
        mock_select.return_value.ask.return_value = "Q1"
        mock_text.return_value.ask.return_value = "Q1"

        result = select_or_edit_question(["Q1", "Q2"])
        self.assertEqual(result, "Q1")

    def test_print_path_and_answer_types(self) -> None:
        print_path(Path())
        print_answer("")


if __name__ == "__main__":
    unittest.main()
