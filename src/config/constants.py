from typing import Final, List

MODEL_NAME_ENV: Final[str] = "llama3.2"
TIMEOUT: Final[int] = 120
PATHS_FILE: Final[str] = "data/paths.json"
FACTS_DIR: Final[str] = "data/facts"
FACTS_FILE: Final[str] = "facts"
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
MANUAL_FILE = "data/documents/sample_manual.md"
CORRECTIONS_DIR = "data/corrections"
