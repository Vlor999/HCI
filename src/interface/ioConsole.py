import questionary
from typing import List, Optional
from typeguard import typechecked

from src.core.path import Path, PathStep


@typechecked
def ask_question() -> str:
    return (
        questionary.text(
            "Ask a question about the path (e.g., 'Is this road a good one to take?')",
            qmark="🤖",
        ).ask()
        or ""
    )


@typechecked
def print_path(path: Path) -> None:
    print("\n📍 Current robot path with context:\n")
    print(path.to_prompt())
    print()


@typechecked
def print_answer(answer: str) -> None:
    print("\n🤖 Robot answer:\n")
    print(answer)


@typechecked
def select_or_edit_question(questions: List[str]) -> Optional[str]:
    if not questions:
        return None
    choice = questionary.select(
        "Select a previous question to edit (ESC to cancel):",
        choices=questions,
        use_shortcuts=True,
        use_indicator=True,
        qmark="📝",
    ).ask()
    if choice is None:
        print("No question selected. Returning to main menu.")
        return None
    new_question: str = questionary.text(
        f"Edit your question (was: {choice}):", default=choice, qmark="✏️"
    ).ask()
    return new_question
