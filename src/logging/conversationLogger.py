import os
from datetime import datetime
from typing import List, Tuple, Sequence
from src.core.path import Path


def save_conversation(
    path: Path,
    conversation: Sequence[Tuple[str, str]],
    contextLog: Sequence[str],
    logDir: str = "log",
    filename: str = "conversation_log.md",
) -> None:
    os.makedirs(logDir, exist_ok=True)
    file = filename.split(".")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{file[0]}_{timestamp}.{file[1]}"
    filepath = os.path.join(logDir, filename)
    with open(filepath, "w") as f:
        f.write("# Robot Path Conversation Log\n\n")
        f.write("## Path\n\n")
        f.write("```\n")
        f.write(path.to_prompt())
        f.write("\n```\n\n")
        if contextLog:
            f.write("## Additional facts and updates\n\n")
            for fact in contextLog:
                f.write(f"- {fact}\n")
            f.write("\n")
        for idx, qa in enumerate(conversation, 1):
            q, a = qa
            f.write(f"### Q{idx}: {q}\n\n")
            f.write(f"**Answer:**\n\n{a}\n\n")
    print(f"Conversation saved to {filepath}")
