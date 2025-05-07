import requests
import questionary
from typeguard import typechecked


@typechecked
def choose_model(default_model: str = "llama3.2", timeout: int = 120) -> str:
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", [])]
        if not models:
            print(
                "No models available. Please ensure Ollama is running and models are installed."
            )
            return default_model

        answer = questionary.select(
            "Select an Ollama model to use:",
            choices=models,
            default=default_model if default_model in models else models[0],
            style=questionary.Style(
                [
                    ("selected", "fg:#ffffff"),
                    ("pointer", "fg:#007acc bold"),
                    ("question", "bold"),
                ]
            ),
        ).ask()

        if answer:
            questionary.print(
                f"\nSelected model: {answer}\n", style="bold italic fg:green"
            )
            return answer
        return default_model

    except requests.exceptions.RequestException as e:
        print("Error retrieving models from Ollama API. Using default model.", e)
        return default_model
    except Exception as e:
        print("Unexpected error occurred. Using default model.", e)
        return default_model
