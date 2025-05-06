import requests
import json

def query_llm(prompt, model, timeout=120):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt},
            stream=True,
            timeout=timeout
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
