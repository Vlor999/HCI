#! /usr/bin/env python3

import requests  # type: ignore
import json
from time import time


def query_llm(prompt: str, model: str, timeout: int = 120) -> str:
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt},
            stream=True,
            timeout=timeout,
        )
        response.raise_for_status()
        explanation = ""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                explanation += data.get("response", "")
        return explanation
    except Exception as e:
        return f"Error querying LLM: {e}"


def main() -> None:
    question = "What's the color of the sun ?"
    answer = query_llm(question, "mistral:7b-instruct-v0.3-fp16")
    print("Question : ", question)
    print("Answer : ", answer)


if __name__ == "__main__":
    tic = time()
    main()
    tac = time()
    print(tac - tic)
