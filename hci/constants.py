"""Immutable values shared across the package: prompts, markers, model ids, URLs, paths, labels."""

import re
from enum import StrEnum
from pathlib import Path

# --- Prompts -----------------------------------------------------------------

SYSTEM = """You are the explanation module of a mobile robot that navigates a forest with LIDAR, camera and IMU.
Explain its path choices to a human using only the numbered context passages.
- Operator updates are the newest information: when they contradict a record, follow the update.
- Reason about safety, terrain, energy and ecological impact; give the decision first, then the justification.
- Travel times are precomputed in the passages; use them instead of recomputing.
- Cite the passages you rely on like [2]. If the context does not answer the question, say so.
- Write in Markdown (the phone renders it like Notion): bold, lists, `- [ ]` checklists, tables, `code`, and
  callouts, a quote whose first line is [!NOTE], [!TIP], [!IMPORTANT], [!WARNING] or [!CAUTION] on its own.
  Start with the decision as one bold sentence. Use a table only to compare paths. Example shape:

  **Take path C first.**

  | Path | Time | Terrain | Risk |
  |---|---|---|---|
  | C | 5.4 min | paved, flat | low [3] |

  - C is the fastest and the most stable [3].

  > [!WARNING]
  > Slow down on path B if it is icy [2].

  Keep short answers short: no table for a one-line answer."""

AGENT_SYSTEM = (
    SYSTEM
    + """

You have tools over the robot's memory:
- query_context: search the records. Call it before answering, as often as needed (paths, documents, past corrections).
- add_context: when the user reports a new observation or change (a closed path, new weather, a repair), propose it
  as a fact. The operator approves it; do not claim it is saved unless the tool says so.
Passage numbers restart at each search; cite them as [search.passage], e.g. [1.2].
Never answer from general knowledge, even when you know the answer: if the records do not cover the question,
say you don't know from the robot's records and offer what the records can answer. Do not state the answer."""
)

NOT_FOUND = "I can't answer that from the robot's records."

# --- Stream protocol ---------------------------------------------------------

STEP_MARKER = "\x1f"  # stream lines starting with this are progress steps, not answer text
PROPOSALS_MARKER = "\x1e"  # followed by a JSON list of facts the agent proposes, at the end of the stream

# --- Models ------------------------------------------------------------------

LOCAL_MODELS = {
    "mlx": "mlx-community/Qwen3-4B-4bit",
    "cuda": "Qwen/Qwen3-4B",
    "cpu": "Qwen/Qwen3-0.6B",
}
CLAUDE_MODEL = "claude-sonnet-5-5"
AGENT_BETAS = ("server-side-fallback-2026-07-01",)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge query instruction

# --- Jev (TypeSafe AI) -------------------------------------------------------

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_PASSAGE_QUESTION = "Does `passages.{key}` help answer `query`?"
JEV_ANSWERABLE_QUESTION = "Taken together, do `passages` contain enough information to answer `query`?"

# --- Retrieval ---------------------------------------------------------------

BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60  # reciprocal rank fusion constant

# --- Documents ---------------------------------------------------------------

DOCUMENT_EXTENSIONS = (".md", ".txt", ".pdf", ".docx", ".pages")  # one parser each in hci/documents.py
MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")  # ATX heading: level, title
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
PATH_SEPARATORS = re.compile(r"[\\/]")  # POSIX and Windows, for client file names
UNSAFE_NAME_CHARS = re.compile(r"[^\w.-]+")
UPLOADS_DIRNAME = "uploads"  # subfolder of the documents dir that phone uploads go to
UPLOADS_ROUTE = "/api/documents"
UPLOAD_OVERHEAD_BYTES = 64 * 1024  # multipart boundaries and headers around the file, allowed on top of max_upload_mb
MAX_NAME_BYTES = 120  # saved file name stem, in UTF-8 bytes (file systems cap names at 255)
PAGES_HINT = "export it from Pages as PDF or DOCX and add that file instead"
# Exports a .pages file to PDF through the Pages app; paths come as arguments, never spliced into the script.
PAGES_EXPORT_SCRIPT = """on run argv
  tell application id "com.apple.Pages"
    set d to open (POSIX file (item 1 of argv))
    export d to (POSIX file (item 2 of argv)) as PDF
    close d saving no
  end tell
end run"""

# --- Paths -------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PATHS_FILE = DATA_DIR / "paths.json"
DOCUMENTS_DIR = DATA_DIR / "documents"
CORRECTIONS_DIR = DATA_DIR / "corrections"
EXPLANATIONS_FILE = DATA_DIR / "explanations" / "sample_explanations.json"
FACTS_FILE = DATA_DIR / "facts.json"
WEB_PAGE = ROOT_DIR / "web" / "index.html"
VENDOR_DIR = ROOT_DIR / "web" / "vendor"  # pinned marked + DOMPurify, served locally (works offline)
METRICS_FILE = ROOT_DIR / "logs" / "metrics.jsonl"
CASES_DIR = ROOT_DIR / "tests" / "cases"


class Source(StrEnum):
    """Where a record chunk comes from."""

    PATH = "path"
    DOCUMENT = "document"
    CORRECTION = "correction"
    EXAMPLE = "example"
    FACT = "fact"


# --- Chat --------------------------------------------------------------------

COMMANDS = {
    "/fact": "record an operator update: /fact <text>",
    "/scenario": "show or switch the current scenario: /scenario <n>",
    "/clear": "forget this conversation",
    "/help": "list commands",
    "/exit": "quit",
}

# --- Metrics -----------------------------------------------------------------


class MetricSource(StrEnum):
    """What produced an answer's metric events."""

    CLI = "cli"
    SERVER = "server"
    EVAL = "eval"


# --- agent/server ------------------------------------------------------------

AGENT_SCENARIO_NOTE = "The current scenario is {}."
AGENT_NO_SCENARIO_NOTE = "No current scenario."
AGENT_NO_OPERATOR = "Not saved: no operator available to approve facts here."
AGENT_PROPOSED_ON_PHONE = "Proposed: the operator will approve or reject it on the phone."
AGENT_NOTHING_FOUND = "Nothing relevant in the records."
AGENT_REFUSAL = "\n[The model declined to answer.]"
AGENT_NO_KEY = "Claude is not configured: set ANTHROPIC_API_KEY on the server."
AGENT_STEP_THINKING = "Thinking"
AGENT_STEP_REASONING = "Reasoning"
AGENT_STEP_FOUND = "Found {} passages"
AGENT_STEP_ERROR = "Claude request failed"
AGENT_TOOL_STEPS = {  # step label per tool; {query} and {text} come from the tool input
    "query_context": 'Searching: "{query}"',
    "add_context": 'Proposing fact: "{text}"',
    "list_scenarios": "Listing scenarios",
}
AGENT_TOOL_STEP_DEFAULT = "Running tool {tool}"
AGENT_TOOL_STEP_SCENARIO = " (scenario {})"
AGENT_ERRORS = {  # Anthropic exception class name -> user message; the nearest class in the MRO wins
    "AuthenticationError": "Claude rejected the server's API key. Check ANTHROPIC_API_KEY.",
    "RateLimitError": "Claude is rate limited right now. Try again in a minute.",
    "APIConnectionError": "Cannot reach Claude. Check the server's internet connection.",
    "APIStatusError": "Claude returned an error. Try again, or use a local model.",
}
