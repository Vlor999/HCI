import unittest
from src.path import Path
from src.io_console import ask_question, print_path, print_answer
from src.conversation_logger import save_conversation

class TestCoverage(unittest.TestCase):
    def test_path_class(self):
        path = Path()
        path.add_step("Test", "2024-01-01T00:00:00", "test context", 1.0, 10)
        self.assertEqual(len(path), 1)
        self.assertIn("Test", path.to_prompt())

    def test_save_conversation(self):
        path = Path()
        path.add_step("Test", "2024-01-01T00:00:00", "test context", 1.0, 10)
        conversation = [("What is the best path?", "The best path is Test.")]
        context_log = ["now the path is dry"]
        save_conversation(path, conversation, context_log, logDir="log", filename="test_conversation_log.md")

    def test_io_console(self):
        print_path(Path())
        print_answer("Sample answer")

if __name__ == "__main__":
    unittest.main()
