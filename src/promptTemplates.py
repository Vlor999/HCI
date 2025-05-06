from typing import List
from typeguard import typechecked

from src.path import Path


@typechecked
def build_explanation_prompt(path: Path, context_log: List[str], question: str) -> str:
    context_str = ""
    if context_log:
        context_str = (
            "\n\n# Additional facts and updates provided during the conversation:\n"
            + "\n".join(f"- {fact}" for fact in context_log)
            + "\n"
        )
    return (
        "The robot has recorded the following path with environmental context:\n"
        + path.to_prompt()
        + context_str
        + f"\n\nQuestion: {question}\n"
        "Please answer based on the path, context, and all additional facts above.\n"
        "Provide the answer in markdown format, and conclude with a final solution in the format: Solution: XXX."
    )
