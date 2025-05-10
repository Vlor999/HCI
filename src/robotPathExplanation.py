import os
from questionary import select, text
import json
from typing import Any

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
from src.llm.modelSelector import choose_model
from src.core.pathCreator import create_custom_path
from src.llm.promptTemplates import build_explanation_prompt
from src.llm.llmModel import LLMModel
from src.llm.modelSelector import choose_model


def load_saved_facts() -> Any:
    try:
        with open(FACTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_facts(facts: list[str]) -> None:
    os.makedirs(os.path.dirname(FACTS_FILE), exist_ok=True)
    with open(FACTS_FILE, "w") as f:
        json.dump(facts, f, indent=2)


def choose_path_scenario() -> int:
    try:
        with open(PATHS_FILE, "r") as f:
            data = f.read()
        scenarios = eval(data) if isinstance(data, str) else data
        choices = [
            f"{idx}: {scenario.get('description', f'Scenario {idx+1}')}"
            for idx, scenario in enumerate(scenarios)
        ]
        answer: str = select(
            "Select a path scenario to use:", choices=choices, default=choices[0]
        ).ask()
        if answer:
            idx = int(answer.split(":")[0])
            return idx
        return 0
    except Exception as e:
        print("Error loading path scenarios, using default (0).", e)
        return 0


def robotPath() -> None:
    model_name = os.environ.get("LLM_MODEL", MODEL_NAME_ENV)
    timeout = int(os.environ.get("LLM_TIMEOUT", TIMEOUT))
    scenario_index_env = os.environ.get("SCENARIO_INDEX")
    use_custom_path = os.environ.get("USE_CUSTOM_PATH") == "1"
    cli_fact = os.environ.get("CLI_FACT")

    if not os.environ.get("LLM_MODEL"):
        model_name = choose_model(default_model=MODEL_NAME_ENV, timeout=timeout)
    llm = LLMModel(model_name, timeout=timeout)

    if not use_custom_path and scenario_index_env is None:
        print("Do you want to use an existing path scenario or create a new one?")
        use_existing = (
            input(
                "Type 'existing' to use a scenario from data, or 'new' to create your own (default: existing): "
            )
            .strip()
            .lower()
        )
        if use_existing == "new":
            use_custom_path = True

    if use_custom_path:
        path = create_custom_path()
    else:
        if scenario_index_env is not None:
            scenario_index = int(scenario_index_env)
        else:
            scenario_index = choose_path_scenario()
        path = Path.from_json_file(PATHS_FILE, index=scenario_index)

    print_path(path)
    conversation: list[tuple[str, str]] = []
    context_log: list[str] = []

    if cli_fact:
        context_log.append(cli_fact)

    while True:
        if conversation:
            action = select(
                "\nChoose an action:",
                choices=[
                    "Ask a new question",
                    "Edit a previous question (history)",
                    "Add a new fact (addfact)",
                    "Quit",
                ],
            ).ask()

            match action:
                case "Edit a previous question (history)":
                    prev_questions = [q for q, _ in conversation]
                    edited = select_or_edit_question(prev_questions)
                    if edited:
                        question = edited
                    else:
                        continue
                case "Add a new fact (addfact)":
                    new_fact = text(
                        "Enter the new fact or update to save for future sessions:"
                    ).ask()
                    if new_fact:
                        context_log.append(new_fact)
                        save_facts(context_log)
                        print("Fact saved and will be used in future sessions.")
                    continue
                case "Quit":
                    print("Exiting.")
                    break
                case "Ask a new question":
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

        def print_stream(chunk: str) -> None:
            print(chunk, end="", flush=True)
            explanation_chunks.append(chunk)

        llm.ask(prompt, stream=True, print_stream_func=print_stream)

        explanation = "".join(explanation_chunks)
        conversation.append((question, explanation))

    if conversation:
        save_conversation(path, conversation, context_log, logDir=LOG_CONVERSATIONS_DIR)
