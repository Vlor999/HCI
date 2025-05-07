import os
import questionary
import json
from typing import Any
from typeguard import typechecked

from src.config.constants import (
    MODEL_NAME_ENV,
    TIMEOUT,
    PATHS_FILE,
    FACTS_FILE,
    KEYWORDS,
    LOG_CONVERSATIONS_DIR,
)
from src.core.path import Path
from src.interface.ioConsole import ask_question, print_path, select_or_edit_question
from src.logging.conversationLogger import save_conversation
from src.modelSelector import choose_model
from src.core.pathCreator import create_custom_path
from src.promptTemplates import build_explanation_prompt
from src.llm.llm_model import LLMModel


@typechecked
def load_saved_facts() -> Any:
    try:
        with open(FACTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


@typechecked
def save_facts(facts: list[str]) -> None:
    os.makedirs(os.path.dirname(FACTS_FILE), exist_ok=True)
    with open(FACTS_FILE, "w") as f:
        json.dump(facts, f, indent=2)


@typechecked
def choose_path_scenario() -> int:
    try:
        with open(PATHS_FILE, "r") as f:
            data = f.read()
        scenarios = eval(data) if isinstance(data, str) else data
        choices = [
            f"{idx}: {scenario.get('description', f'Scenario {idx+1}')}"
            for idx, scenario in enumerate(scenarios)
        ]
        answer = questionary.select(
            "Select a path scenario to use:", choices=choices, default=choices[0]
        ).ask()
        if answer:
            idx = int(answer.split(":")[0])
            return idx
        return 0
    except Exception as e:
        print("Error loading path scenarios, using default (0).", e)
        return 0


@typechecked
def robotPath() -> None:
    model_name = choose_model(default_model=MODEL_NAME_ENV, timeout=TIMEOUT)
    llm = LLMModel(model_name, timeout=TIMEOUT)

    print("Do you want to use an existing path scenario or create a new one?")
    use_existing = (
        input(
            "Type 'existing' to use a scenario from data, or 'new' to create your own (default: existing): "
        )
        .strip()
        .lower()
    )
    if use_existing == "new":
        path = create_custom_path()
    else:
        scenario_index = choose_path_scenario()
        path = Path.from_json_file(PATHS_FILE, index=scenario_index)

    print_path(path)
    conversation: list[tuple[str, str]] = []
    context_log: list[str] = []

    while True:
        if conversation:
            action = (
                input(
                    "Press Enter to ask a new question, type 'history' to edit a previous question, or type 'addfact' to add a new fact: "
                )
                .strip()
                .lower()
            )
            if action == "history":
                prev_questions = [q for q, _ in conversation]
                edited = select_or_edit_question(prev_questions)
                if edited:
                    question = edited
                else:
                    continue
            elif action == "addfact":
                new_fact = input(
                    "Enter the new fact or update to save for future sessions: "
                ).strip()
                if new_fact:
                    context_log.append(new_fact)
                    save_facts(context_log)
                    print("Fact saved and will be used in future sessions.")
                continue
            else:
                question = ask_question()
        else:
            question = ask_question()

        if not question.strip() or question.strip().lower() in {"exit", "quit"}:
            print("Exiting.")
            break

        for word in KEYWORDS:
            if word in question.lower():
                context_log.append(question)
                save_facts(context_log)
                break

        prompt = llm.build_full_prompt(
            path, context_log, question, conversation, build_explanation_prompt
        )

        print(
            f"Processing your question with the LLM model '{model_name}' (streaming output):\n"
        )
        explanation_chunks = []

        def print_stream(chunk):
            print(chunk, end="", flush=True)
            explanation_chunks.append(chunk)

        llm.ask(prompt, stream=True, print_stream_func=print_stream)

        explanation = "".join(explanation_chunks)
        conversation.append((question, explanation))

    if conversation:
        save_conversation(path, conversation, context_log, logDir=LOG_CONVERSATIONS_DIR)
