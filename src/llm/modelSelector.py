import os
from requests import get, exceptions
from typing import Any
from questionary import select


def choose_model(default_model: str = "llama3.2", timeout: int = 120) -> Any | str:
    try:
        response = get("http://localhost:11434/api/tags", timeout=timeout)
        response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", [])]
        if not models:
            print(
                "No models available. Please ensure Ollama is running and models are installed."
            )
            return default_model

        if not os.isatty(0):
            print("Non-interactive environment detected. Using default model.")
            return default_model

        choices = [f"{idx}: {model}" for idx, model in enumerate(models)]
        answer = select(
            "Select an Ollama model to use:", choices=choices, default=choices[0]
        ).ask()

        if answer:
            idx = int(answer.split(":")[0])
            selected_model = models[idx]
            print(f"Selected model: {selected_model}")
            return selected_model

        return default_model
    except exceptions.RequestException as e:
        print("Error retrieving models from Ollama API. Using default model.", e)
        return default_model
    except Exception as e:
        print("Unexpected error occurred. Using default model.", e)
        return default_model
