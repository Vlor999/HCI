import requests
import json
import os
from src.path import Path
from src.io_console import ask_question, print_path, print_answer, select_or_edit_question
from src.conversation_logger import save_conversation

MODEL_NAME = os.environ.get("LLM_MODEL", "llama3.2")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))
PATHS_FILE = "data/paths.json"

KEYWORDS = ["now", "update", "change", "fact", "actually", "in fact", "new info", "correction"]

def build_prompt(path, context_log, question):
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

def choose_path_scenario():
    try:
        with open(PATHS_FILE, "r") as f:
            data = json.load(f)
        print("Available path scenarios:")
        for idx, scenario in enumerate(data):
            desc = scenario.get("description", f"Scenario {idx+1}")
            print(f"{idx}: {desc}")
        while True:
            choice = input(f"Select scenario index (0-{len(data)-1}, default 0): ").strip()
            if not choice:
                return 0
            if choice.isdigit() and 0 <= int(choice) < len(data):
                return int(choice)
            print("Invalid input. Please enter a valid index.")
    except Exception as e:
        print("Error loading path scenarios, using default (0).", e)
        return 0

def robotPath():
    scenario_index = choose_path_scenario()
    path = Path.from_json_file(PATHS_FILE, index=scenario_index)
    print_path(path)

    conversation = []
    context_log = []

    while True:
        if conversation:
            action = input("Press Enter to ask a new question, or type 'history' to edit a previous question: ").strip().lower()
            if action == "history":
                prev_questions = [q for q, _ in conversation]
                edited = select_or_edit_question(prev_questions)
                if edited:
                    question = edited
                else:
                    continue
            else:
                question = ask_question()
        else:
            question = ask_question()

        if not question.strip() or question.strip().lower() in {"exit", "quit"}:
            print("Exiting.")
            break

        if any(word in question.lower() for word in KEYWORDS):
            context_log.append(question)

        prompt = build_prompt(path, context_log, question)

        print(f"Processing your question with the LLM model '{MODEL_NAME}'. This may take a while for large models...")
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": MODEL_NAME, "prompt": prompt},
                stream=True,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            explanation = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    explanation += data.get("response", "")
            print_answer(explanation)
            conversation.append((question, explanation))
        except requests.exceptions.RequestException as e:
            print(f"Error: Unable to connect to Ollama or model '{MODEL_NAME}'. Is it running on http://localhost:11434?")
            print(e)
            break
        except json.JSONDecodeError as e:
            print("Error: Failed to parse Ollama response.")
            print(e)
            break

    if conversation:
        save_conversation(path, conversation, context_log)
