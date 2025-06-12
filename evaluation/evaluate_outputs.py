import re
from typing import List, Dict, Any, Optional


def evaluate_explanation(
    explanation: str,
    expected_keywords: List[str],
    expected_answer: Optional[str] = None,
) -> Dict[str, Any]:
    keyword_score: float = sum(1 for kw in expected_keywords if kw.lower() in explanation.lower())
    keyword_score = keyword_score / len(expected_keywords) if expected_keywords else 0.0

    length: int = len(explanation.split())
    if length < 10:
        length_score: float = 0.0
    elif length < 30:
        length_score = 0.5
    else:
        length_score = 1.0

    exact_match: int = 0
    if expected_answer:
        norm_exp = re.sub(r"\s+", " ", explanation.strip().lower())
        norm_ans = re.sub(r"\s+", " ", expected_answer.strip().lower())
        exact_match = int(norm_exp == norm_ans)

    denom = 3 if expected_answer else 2
    final_score: float = (keyword_score + length_score + exact_match) / denom

    return {
        "keyword_score": keyword_score,
        "length_score": length_score,
        "exact_match": exact_match,
        "final_score": final_score,
    }
