from typing import List
from src.core.path import Path


def build_explanation_prompt(path: Path, context_log: List[str], question: str) -> str:
    context_str = ""
    if context_log:
        context_str = (
            "# Context Updates:\n"
            "These are factual updates or observations, not questions:\n"
            + "\n".join(f"- {fact}" for fact in context_log)
            + "\n"
        )

    return (
        "SYSTEM ROLE:\n"
        "You are an intelligent mobile robot navigating a forest environment. "
        "You are equipped with sensors including LIDAR, camera, IMU, and have access to previous weather data and satellite imagery. "
        "The terrain may include slopes, obstacles, unstable soil, and ecologically sensitive areas.\n\n"
        "AVAILABLE PATHS:\n" + path.to_prompt() + "\n\n" + context_str + "\n"
        "OBJECTIVE:\n"
        "Evaluate the paths and answer the question below using all available data. "
        "Base your reasoning on safety, terrain feasibility, energy efficiency, and ecological impact. "
        "Always prefer up-to-date and sensor-driven information over outdated or uncertain data.\n\n"
        f"QUESTION:\n{question}\n\n"
        "RESPONSE FORMAT:\n"
        "- State the best path or decision clearly.\n"
        "- Justify based on terrain, context, and robot constraints.\n"
        "- If applicable, explain trade-offs or why other paths were less suitable.\n"
    )
