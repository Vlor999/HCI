from typing import Final, List

MODEL_NAME_ENV: Final[str] = "llama3.2"
TIMEOUT: Final[int] = 120
PATHS_FILE: Final[str] = "data/paths.json"
FACTS_FILE: Final[str] = "data/facts.json"
LOG_CONVERSATIONS_DIR: Final[str] = "log/conversations"
LOG_TESTS_DIR: Final[str] = "log/tests"
KEYWORDS: Final[List[str]] = [
    "now",
    "update",
    "change",
    "fact",
    "actually",
    "in fact",
    "new info",
    "correction",
]

EXPLANATIONS_FILE = "data/explanations/sample_explanations.json"
MANUAL_FILE = "data/documents/sample_manual.txt"
CORRECTIONS_DIR = "data/corrections"
