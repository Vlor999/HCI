import unittest
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
        d = {
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

    def test_select_or_edit_question_cancel(self) -> None:
        import questionary

        original_select = questionary.select
        questionary.select = lambda *args, **kwargs: type("FakeSelect", (), {"ask": staticmethod(lambda: None)})()
        try:
            self.assertIsNone(select_or_edit_question(["Q1", "Q2"]))
        finally:
            questionary.select = original_select

    def test_print_path_and_answer_types(self) -> None:
        print_path(Path())
        print_answer("")


if __name__ == "__main__":
    unittest.main()
