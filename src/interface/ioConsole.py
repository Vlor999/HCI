from questionary import text, select
from src.core.path import Path
from typing import Any, List, Optional
import os


def ask_question() -> str:
    return (
        text(
            "Ask a question about the path (e.g., 'Is this road a good one to take?')",
            qmark="🤖",
        ).ask()
        or ""
    )


def print_path(path: Path) -> None:
    print("\n📍 Current robot path with context:\n")
    print(path.to_prompt())
    print()


def print_answer(answer: str) -> None:
    print("\n🤖 Robot answer:\n")
    print(answer)


def select_or_edit_question(questions: List[str]) -> Optional[str]:
    if not os.isatty(0):
        print("Non-interactive environment detected. Returning None.")
        return None

    if not questions:
        return None
    choice = select(
        "Select a previous question to edit (ESC to cancel):",
        choices=questions,
        use_shortcuts=True,
        use_indicator=True,
        qmark="📝",
    ).ask()
    if choice is None:
        print("No question selected. Returning to main menu.")
        return None
    new_question: str = text(
        f"Edit your question (was: {choice}):", default=choice, qmark="✏️"
    ).ask()
    return new_question
