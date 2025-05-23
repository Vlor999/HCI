from requests import post
from json import loads
from typing import Any


def query_llm(prompt: str, model: str, timeout: int = 120, temperature: float = 0.0, prev_message: int = 0) -> str:
    try:
        response = post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "temperature": temperature,
                "num_ctx": prev_message,
                "repeat_penalty": 1.1,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        explanation = ""
        for line in response.iter_lines():
            if line:
                data: Any = loads(line)
                explanation += data.get("response", "")
        return explanation
    except Exception as e:
        return f"Error querying LLM: {e}"
