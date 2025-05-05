import requests
import json
from src.path import Path
from src.io_console import ask_question, print_path, print_answer

def robotPath():
    path = Path.from_json_file("data/paths.json", index=0)
    print_path(path)

    conversation = []
    context_log = []

    while True:
        user_question = ask_question()
        if not user_question.strip() or user_question.strip().lower() in {"exit", "quit"}:
            print("Exiting.")
            break

        # If the user question contains a clarification or update, add it to the context log
        # (You can improve this logic as needed)
        if any(word in user_question.lower() for word in ["now", "update", "change", "fact", "actually", "in fact", "new info", "correction"]):
            context_log.append(user_question)

        # Build the context string
        context_str = ""
        if context_log:
            context_str = (
                "\n\n# Additional facts and updates provided during the conversation:\n"
                + "\n".join(f"- {fact}" for fact in context_log)
                + "\n"
            )

        prompt = (
            "The robot has recorded the following path with environmental context:\n"
            + path.to_prompt()
            + context_str
            + f"\n\nQuestion: {user_question}\n"
            "Please answer based on the path, context, and all additional facts above."
        )

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2", "prompt": prompt},
                stream=True
            )
            response.raise_for_status()
            explanation = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    explanation += data.get("response", "")
            print_answer(explanation)
            conversation.append((user_question, explanation))
        except requests.exceptions.RequestException as e:
            print("Error: Unable to connect to Ollama. Is it running on http://localhost:11434?")
            print(e)
            break
        except json.JSONDecodeError as e:
            print("Error: Failed to parse Ollama response.")
            print(e)
            break

    if conversation:
        with open("log/conversation_log.md", "w") as f:
            f.write("# Robot Path Conversation Log\n\n")
            f.write("## Path\n\n")
            f.write("```\n")
            f.write(path.to_prompt())
            f.write("\n```\n\n")
            if context_log:
                f.write("## Additional facts and updates\n\n")
                for fact in context_log:
                    f.write(f"- {fact}\n")
                f.write("\n")
            for idx, (q, a) in enumerate(conversation, 1):
                f.write(f"### Q{idx}: {q}\n\n")
                f.write(f"**Answer:**\n\n{a}\n\n")
        print("Conversation saved to conversation_log.md")
