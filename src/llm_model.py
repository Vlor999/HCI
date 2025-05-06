import json
from src.llmInterface import query_llm

class LLMModel:
    def __init__(self, model_name, timeout=120, manual_path="data/documents/sample_manual.txt", explanations_path="data/explanations/sample_explanations.json"):
        self.model_name = model_name
        self.timeout = timeout
        self.manual = self._load_manual(manual_path)
        self.explanations = self._load_explanations(explanations_path)

    def _load_manual(self, path):
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return ""

    def _load_explanations(self, path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def summarize_perception_info(self, path):
        perception_summary = []
        for step in path.steps:
            perception = {
                "location": getattr(step, "location", None),
                "timestamp": getattr(step, "timestamp", None),
                "context": getattr(step, "context", None),
                "average_speed": getattr(step, "average_speed", None),
                "length": getattr(step, "length", None),
                "seasonal_info": getattr(step, "seasonal_info", None)
            }
            perception_summary.append(perception)
        return json.dumps(perception_summary, indent=2)

    def retrieve_contextual_memory(self, conversation, n=3):
        if not conversation:
            return ""
        memory = conversation[-n:]
        return "\n".join(f"Q: {q}\nA: {a}" for q, a in memory)

    def build_full_prompt(self, path, context_log, question, conversation=None, build_explanation_prompt=None):
        perception_json = self.summarize_perception_info(path)
        memory = self.retrieve_contextual_memory(conversation or [], n=3)
        prompt = (
            (build_explanation_prompt(path, context_log, question) if build_explanation_prompt else "")
            + "\n\n"
            + "### Structured Perception Info:\n"
            + perception_json
            + "\n\n"
            + "### Recent Conversation Memory:\n"
            + memory
        )
        return prompt

    def ask(self, prompt, stream=False, print_stream_func=None):
        if not stream:
            return query_llm(prompt, self.model_name, timeout=self.timeout)
        import requests
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model_name, "prompt": prompt},
                stream=True,
                timeout=self.timeout
            )
            response.raise_for_status()
            explanation = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    explanation += chunk
                    if print_stream_func:
                        print_stream_func(chunk)
            return explanation
        except Exception as e:
            if print_stream_func:
                print_stream_func(f"\nError querying LLM: {e}")
            return f"Error querying LLM: {e}"
