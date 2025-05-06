import re

def evaluate_explanation(explanation, expected_keywords, expected_answer=None):
    """
    Evaluate an explanation with several metrics.
    Returns a dict with scores.
    """
    # Keyword coverage score
    keyword_score = sum(1 for kw in expected_keywords if kw.lower() in explanation.lower())
    keyword_score = keyword_score / len(expected_keywords) if expected_keywords else 0

    # Length score (longer explanations may be more informative, but penalize too short/long)
    length = len(explanation.split())
    if length < 10:
        length_score = 0
    elif length < 30:
        length_score = 0.5
    else:
        length_score = 1

    # Optional: Exact answer match (if expected_answer is provided)
    exact_match = 0
    if expected_answer:
        # Normalize whitespace and case for comparison
        norm_exp = re.sub(r"\s+", " ", explanation.strip().lower())
        norm_ans = re.sub(r"\s+", " ", expected_answer.strip().lower())
        exact_match = int(norm_exp == norm_ans)

    return {
        "keyword_score": keyword_score,
        "length_score": length_score,
        "exact_match": exact_match,
        "final_score": (keyword_score + length_score + exact_match) / (3 if expected_answer else 2)
    }


if __name__ == "__main__":
    explanation = "I avoided path A because it is marked as not usable due to snow in winter."
    expected = ["avoided", "not usable", "snow", "winter"]
    expected_answer = "I avoided path A because it is marked as not usable due to snow in winter."
    result = evaluate_explanation(explanation, expected, expected_answer)
    print("Evaluation result:", result)
