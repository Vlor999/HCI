import requests  # type: ignore
import json
from typing import List, Optional, Callable, Any, Tuple, Dict
import os

from src.llm.llmInterface import query_llm


class LLMModel:
    def __init__(
        self,
        model_name: str,
        timeout: int = 120,
        manual_path: str = "data/documents/sample_manual.txt",
        explanations_path: str = "data/explanations/sample_explanations.json",
        corrections_dir: str = "data/corrections",
    ):
        self.model_name: str = model_name
        self.timeout: int = timeout
        self.manual: str = self.load_manual(manual_path)
        self.explanations: List[Dict[str, Any]] = self.load_explanations(
            explanations_path
        )
        self.corrections: List[Tuple[str, str, str]] = self.load_corrections(
            corrections_dir
        )

    def getTime(self, path: str) -> float:
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0

    def _get_dir_mtime(self, dir_path: str) -> float:
        latest = 0.0
        if not os.path.isdir(dir_path):
            return latest
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if os.path.isfile(fpath):
                latest = max(latest, self.getTime(fpath))
        return latest

    def dataTime(self) -> float:
        mtimes = [
            self.getTime("data/explanations/sample_explanations.json"),
            self._get_dir_mtime("data/corrections"),
            self.getTime("data/documents/sample_manual.txt"),
        ]
        return max(mtimes)

    def load_manual(self, path: str) -> str:
        try:
            with open(path, "r") as f:
                return f.read()
        except Exception:
            return ""

    def load_explanations(self, path: str) -> List[Dict[str, Any]]:
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception:
            return []

    def load_corrections(self, corrections_dir: str) -> List[Tuple[str, str, str]]:
        """
        Returns a list of (question, llm_answer, correct_solution)
        """
        corrections: List[Tuple[str, str, str]] = []
        if not os.path.isdir(corrections_dir):
            return corrections
        for fname in os.listdir(corrections_dir):
            if fname.endswith(".md"):
                fpath = os.path.join(corrections_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        lines = f.readlines()
                    question, llm_answer, correct_solution = None, None, None
                    for idx, line in enumerate(lines):
                        if line.strip().startswith("### Q"):
                            question = line.strip().split(":", 1)[-1].strip()
                        if line.strip().startswith("**Answer:**"):
                            llm_answer_lines = []
                            for l in lines[idx + 1 :]:
                                if l.strip().startswith("###"):
                                    break
                                llm_answer_lines.append(l)
                            llm_answer = "".join(llm_answer_lines).strip()
                        if line.strip().lower().startswith("### correct solution"):
                            correct_solution = "".join(lines[idx + 2 :]).strip()
                        if question and llm_answer and correct_solution:
                            corrections.append((question, llm_answer, correct_solution))
                            question, llm_answer, correct_solution = None, None, None
                except Exception:
                    continue
        return corrections

    def summarize_perception_info(self, path: Any) -> str:
        perception_summary: List[Dict[str, Any]] = []
        for step in path.steps:
            perception = {
                "location": getattr(step, "location", None),
                "timestamp": getattr(step, "timestamp", None),
                "context": getattr(step, "context", None),
                "average_speed": getattr(step, "average_speed", None),
                "length": getattr(step, "length", None),
                "seasonal_info": getattr(step, "seasonal_info", None),
            }
            perception_summary.append(perception)
        return json.dumps(perception_summary, indent=2)

    def retrieve_contextual_memory(
        self, conversation: List[Tuple[str, str]], n: int = 3
    ) -> str:
        if not conversation:
            return ""
        memory = conversation[-n:]
        return "\n".join(f"Q: {q}\nA: {a}" for q, a in memory)

    def build_full_prompt(
        self,
        path: Any,
        context_log: List[str],
        question: str,
        conversation: Optional[List[Tuple[str, str]]] = None,
        build_explanation_prompt: Optional[Callable[..., str]] = None,
    ) -> str:
        perception_json: str = self.summarize_perception_info(path)
        memory: str = self.retrieve_contextual_memory(conversation or [], n=3)
        corrections_str = ""
        if self.corrections:
            corrections_str = (
                "\n\n# Previous Questions, LLM Answers, and Corrections:\n"
                + "\n".join(
                    f"Q: {q}\nLLM Answer: {llm_ans}\nCorrect Solution: {corr}"
                    for q, llm_ans, corr in self.corrections
                )
            )
        similar_str = ""
        prompt: str = (
            (
                build_explanation_prompt(path, context_log, question)
                if build_explanation_prompt
                else ""
            )
            + "\n\n"
            + "### Structured Perception Info:\n"
            + perception_json
            + "\n\n"
            + "### Recent Conversation Memory:\n"
            + memory
            + corrections_str
            + similar_str
        )
        return prompt

    def ask(
        self,
        prompt: str,
        stream: bool = False,
        print_stream_func: Optional[Callable[[str], None]] = None,
    ) -> str:
        if not stream:
            return query_llm(prompt, self.model_name, timeout=self.timeout)

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self.model_name, "prompt": prompt},
                stream=True,
                timeout=self.timeout,
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
