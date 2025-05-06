import requests
import json
import os
import sys
import time
import threading
import questionary
from src.path import Path
from src.ioConsole import ask_question, print_path, print_answer, select_or_edit_question
from src.conversationLogger import save_conversation
from src.modelSelector import choose_model
from src.pathCreator import create_custom_path
from src.promptTemplates import build_explanation_prompt
from src.llmInterface import query_llm
from src.llm_model import LLMModel

MODEL_NAME_ENV = os.environ.get("LLM_MODEL", "llama3.2")
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
        choices = [
            f"{idx}: {scenario.get('description', f'Scenario {idx+1}')}"
            for idx, scenario in enumerate(data)
        ]
        answer = questionary.select(
            "Select a path scenario to use:",
            choices=choices,
            default=choices[0]
        ).ask()
        if answer:
            idx = int(answer.split(":")[0])
            return idx
        return 0
    except Exception as e:
        print("Error loading path scenarios, using default (0).", e)
        return 0

def load_background_knowledge():
    # Load robot manual
    manual = ""
    try:
        with open("data/documents/sample_manual.txt", "r") as f:
            manual = f.read()
    except Exception:
        pass

    # Load explanations dataset (optional)
    explanations = []
    try:
        with open("data/explanations/sample_explanations.json", "r") as f:
            explanations = json.load(f)
    except Exception:
        pass

    return manual, explanations

def summarize_perception_info(path):
    """
    Summarize perception info from the path into a prompt-friendly JSON-like string.
    """
    perception_summary = []
    for step in path.steps:
        perception = {
            "location": step.location if hasattr(step, "location") else step.get("location"),
            "timestamp": step.timestamp if hasattr(step, "timestamp") else step.get("timestamp"),
            "context": step.context if hasattr(step, "context") else step.get("context"),
            "average_speed": getattr(step, "average_speed", None) or step.get("average_speed", None),
            "length": getattr(step, "length", None) or step.get("length", None),
            "seasonal_info": getattr(step, "seasonal_info", None) or step.get("seasonal_info", None)
        }
        perception_summary.append(perception)
    return json.dumps(perception_summary, indent=2)

def retrieve_contextual_memory(conversation, n=3):
    """
    Retrieve the last n questions/answers as contextual memory.
    """
    if not conversation:
        return ""
    memory = conversation[-n:]
    return "\n".join(
        f"Q: {q}\nA: {a}" for q, a in memory
    )

def send_context_to_llm(model, timeout, path, manual, explanations, conversation=None):
    perception_json = summarize_perception_info(path)
    memory = retrieve_contextual_memory(conversation or [], n=3)
    context = (
        "### Robot Manual:\n"
        f"{manual}\n\n"
        "### Example Explanations:\n"
        + "\n".join(f"Q: {ex['input']}\nA: {ex['output']}" for ex in explanations)
        + "\n\n"
        "### Current Path (structured perception info):\n"
        f"{perception_json}\n\n"
        "### Recent Conversation Memory:\n"
        f"{memory}\n\n"
        "You are a robot assistant. Use this information to answer user questions about the robot's path, context, and reasoning."
    )
    _ = query_llm(context, model, timeout=timeout)

def spinner(stop_event):
    spinner_chars = "|/-\\"
    idx = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r🤖 Model is thinking... {spinner_chars[idx % len(spinner_chars)]}")
        sys.stdout.flush()
        idx += 1
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 40 + "\r")

def robotPath():
    MODEL_NAME = choose_model(default_model=MODEL_NAME_ENV, timeout=TIMEOUT)
    llm = LLMModel(MODEL_NAME, timeout=TIMEOUT)

    print("Do you want to use an existing path scenario or create a new one?")
    use_existing = input("Type 'existing' to use a scenario from data, or 'new' to create your own (default: existing): ").strip().lower()
    if use_existing == "new":
        path = create_custom_path()
    else:
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

        prompt = llm.build_full_prompt(path, context_log, question, conversation, build_explanation_prompt)

        print(f"Processing your question with the LLM model '{MODEL_NAME}' (streaming output):\n")

        explanation_chunks = []
        def print_stream(chunk):
            print(chunk, end="", flush=True)
            explanation_chunks.append(chunk)
        start_time = time.time()
        llm.ask(prompt, stream=True, print_stream_func=print_stream)
        elapsed = time.time() - start_time
        print(f"\n⏱️ Model response time: {elapsed:.2f} seconds")

        explanation = "".join(explanation_chunks)
        conversation.append((question, explanation))

    if conversation:
        save_conversation(path, conversation, context_log)
