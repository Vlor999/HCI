import re
from typing import List, Tuple, Any
from dataclasses import dataclass
from src.evaluation.conversationReader import ConversationEntry, ConversationLog


@dataclass
class ExplanationMetrics:
    accuracy_score: float
    completeness_score: float
    relevance_score: float
    clarity_score: float
    overall_score: float


@dataclass
class EvaluationResult:
    conversation_log: ConversationLog
    question_evaluations: List[Tuple[ConversationEntry, ExplanationMetrics]]
    average_metrics: ExplanationMetrics


class ExplanationEvaluator:
    def __init__(self) -> None:
        self.path_keywords = ["path", "route", "road", "terrain", "slope", "obstacle", "energy", "ecological"]
        self.decision_keywords = ["best", "choose", "recommend", "prefer", "suitable", "optimal"]
        self.reasoning_keywords = ["because", "due to", "since", "therefore", "as a result", "consequently"]

    def evaluate_conversation(self, conversation_log: ConversationLog) -> EvaluationResult:
        """Evaluate all Q&A pairs in a conversation log."""
        question_evaluations: list[tuple[ConversationEntry, ExplanationMetrics]] = []

        for conversation_entry in conversation_log.conversations:
            metrics = self.evaluate_explanation(
                conversation_entry.question,
                conversation_entry.answer,
                conversation_log.path_description,
                conversation_log.additional_facts,
            )
            question_evaluations.append((conversation_entry, metrics))

        if question_evaluations:
            avg_accuracy = sum(m[1].accuracy_score for m in question_evaluations) / len(question_evaluations)
            avg_completeness = sum(m[1].completeness_score for m in question_evaluations) / len(question_evaluations)
            avg_relevance = sum(m[1].relevance_score for m in question_evaluations) / len(question_evaluations)
            avg_clarity = sum(m[1].clarity_score for m in question_evaluations) / len(question_evaluations)
            avg_overall = sum(m[1].overall_score for m in question_evaluations) / len(question_evaluations)
        else:
            avg_accuracy = avg_completeness = avg_relevance = avg_clarity = avg_overall = 0.0

        average_metrics = ExplanationMetrics(
            accuracy_score=avg_accuracy,
            completeness_score=avg_completeness,
            relevance_score=avg_relevance,
            clarity_score=avg_clarity,
            overall_score=avg_overall,
        )

        return EvaluationResult(conversation_log, question_evaluations, average_metrics)

    def evaluate_explanation(
        self, question: str, answer: str, path_context: str, facts: List[str]
    ) -> ExplanationMetrics:
        accuracy_score = self.evaluate_accuracy(question, answer, path_context, facts)
        completeness_score = self.evaluate_completeness(question, answer)
        relevance_score = self.evaluate_relevance(question, answer)
        clarity_score = self.evaluate_clarity(answer)

        overall_score = accuracy_score * 0.3 + completeness_score * 0.25 + relevance_score * 0.25 + clarity_score * 0.2

        return ExplanationMetrics(
            accuracy_score=accuracy_score,
            completeness_score=completeness_score,
            relevance_score=relevance_score,
            clarity_score=clarity_score,
            overall_score=overall_score,
        )

    def evaluate_accuracy(self, question: str, answer: str, path_context: str, facts: List[str]) -> float:
        score = 0.0

        path_elements = self.extract_path_elements(path_context)
        referenced_elements = 0

        for element in path_elements:
            if element.lower() in answer.lower():
                referenced_elements += 1

        if path_elements:
            score += (referenced_elements / len(path_elements)) * 0.5

        if facts:
            fact_usage = sum(1 for fact in facts if any(word in answer.lower() for word in fact.lower().split()))
            score += min(fact_usage / len(facts), 1.0) * 0.3

        if self.contains_contradictions(answer):
            score -= 0.2

        return max(0.0, min(1.0, score + 0.2))

    def evaluate_completeness(self, question: str, answer: str) -> float:
        score = 0.0

        if any(keyword in answer.lower() for keyword in self.reasoning_keywords):
            score += 0.4

        if any(keyword in question.lower() for keyword in self.decision_keywords):
            if any(keyword in answer.lower() for keyword in self.decision_keywords):
                score += 0.3

        word_count = len(answer.split())
        if word_count >= 50:
            score += 0.3
        elif word_count >= 20:
            score += 0.2
        elif word_count >= 10:
            score += 0.1

        return min(1.0, score)

    def evaluate_relevance(self, question: str, answer: str) -> float:
        score = 0.0

        question_terms = set(re.findall(r"\b\w+\b", question.lower()))
        answer_terms = set(re.findall(r"\b\w+\b", answer.lower()))

        if question_terms:
            overlap = len(question_terms.intersection(answer_terms))
            score += (overlap / len(question_terms)) * 0.5

        if any(keyword in question.lower() for keyword in self.path_keywords):
            if any(keyword in answer.lower() for keyword in self.path_keywords):
                score += 0.3

        if not self.goes_off_topic(question, answer):
            score += 0.2
        return min(1.0, score)

    def evaluate_clarity(self, answer: str) -> float:
        score = 0.0
        sentences = answer.split(".")
        if len(sentences) >= 2:
            score += 0.3

        if any(phrase in answer.lower() for phrase in ["the best", "i recommend", "should take", "prefer"]):
            score += 0.3

        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        if 10 <= avg_sentence_length <= 25:
            score += 0.2

        if any(connector in answer.lower() for connector in ["therefore", "however", "additionally", "furthermore"]):
            score += 0.2

        return min(1.0, score)

    def extract_path_elements(self, path_context: str) -> List[str]:
        elements: list[Any] = []
        lines = path_context.split("\n")
        for line in lines:
            if ":" in line:
                elements.extend(re.findall(r"\b\w+\b", line))
        return list(set(elements))

    def contains_contradictions(self, answer: str) -> bool:
        contradictory_pairs = [
            ("safe", "dangerous"),
            ("good", "bad"),
            ("recommend", "avoid"),
            ("efficient", "inefficient"),
            ("best", "worst"),
        ]

        answer_lower = answer.lower()
        for pair in contradictory_pairs:
            if pair[0] in answer_lower and pair[1] in answer_lower:
                return True
        return False

    def goes_off_topic(self, question: str, answer: str) -> bool:
        question_lower = question.lower()
        answer_lower = answer.lower()
        if any(keyword in question_lower for keyword in self.path_keywords):
            if not any(keyword in answer_lower for keyword in self.path_keywords):
                return True
        return False
