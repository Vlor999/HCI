import os

def save_conversation(path, conversation, contextLog, logDir="log", filename="conversation_log.md"):
    os.makedirs(logDir, exist_ok=True)
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
        for idx, (q, a) in enumerate(conversation, 1):
            f.write(f"### Q{idx}: {q}\n\n")
            f.write(f"**Answer:**\n\n{a}\n\n")
    print(f"Conversation saved to {filepath}")
