from typing import List
from src.core.path import Path


def build_explanation_prompt(path: Path, context_log: List[str], question: str) -> str:
    context_str = ""
    if context_log:
        context_str = (
            "\n\n# Additional facts and updates provided during the conversation:\n"
            + "\n".join(f"- {fact}" for fact in context_log)
            + "\n"
            + "You must remember that if informations are too old it may not be anymore true or at least have less importance.\n"
        )
    return (
        "You are a robot into a forest that do know stuff about the roads from previous walk, hikes and other. You do have recorded environmental context, but also strategical informations :\n"
        + "The different path available are those ones : \n"
        + path.to_prompt()
        + context_str
        + f"\n\nQuestion: {question}\n"
        "Please answer based on the path, context, and all additional facts above.\n"
    )
