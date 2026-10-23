# HCI: Robot, explain yourself

A forest robot picks one path among several. This project lets it explain why, in plain language, from its own
records: past paths, the operating manual, reports, past corrections and operator updates. It is a small RAG system,
local-first: everything runs on your machine with no key. Claude is an optional backend.

![Three robots race on paths A, B and C; A hits an obstacle, C arrives first. Asked why it took C, the robot answers with cited travel times, then says it does not know about a flood forecast](doc/demo.gif)

```mermaid
flowchart LR
    subgraph sources["Robot records (data/)"]
        paths["paths.json<br/>path steps + travel time"]
        docs["documents/<br/>md, txt, pdf, docx, pages"]
        corr["corrections/ + explanations/"]
        facts["facts.json<br/>operator updates"]
    end

    sources -->|"segment and chunk<br/>(headings, pages, overlap)"| index[("Hybrid index<br/>bge embeddings + BM25")]

    user(["Operator<br/>CLI or phone"]) -->|"question (local)"| retrieve["Retrieve<br/>pinned scenario steps and facts<br/>+ top-k search, RRF fusion"]
    index --> retrieve
    retrieve --> jev{"Jev judge<br/>(optional)"}
    jev -->|"not answerable"| refuse["I don't know<br/>from the records"]
    jev -->|"relevant passages"| prompt["Grounded prompt<br/>numbered passages"]

    prompt --> local["Local LLM<br/>MLX / CUDA / CPU"]
    user -->|"question (-p anthropic)"| claude["Claude agent<br/>tool loop"]
    claude <-->|"query_context tool"| retrieve
    claude -->|"add_context<br/>proposes a fact"| approve{"Operator<br/>approves?"}
    approve -->|yes| facts

    local --> stream["Streamed answer<br/>steps + Markdown + [n] citations"]
    claude --> stream
    refuse --> stream
    stream --> user
    user -.->|"upload document"| docs
```

If the records do not contain the answer, the app says it does not know.

## Features

- Hybrid retrieval with `BAAI/bge-small-en-v1.5` embeddings and BM25, fused with reciprocal rank fusion. The current
  scenario's steps and facts are always in context, and other scenarios are never searched.
- Ingestion of Markdown, text, PDF, Word and Apple Pages files, split along headings and pages with overlap. A file
  is indexed again when it changes.
- An optional Jev judge. With `TYPESAFE_API_KEY` set, [Jev](https://docs.typesafe.ai) scores each retrieved passage
  and refuses questions the records cannot answer.
- Local generation on MLX (Apple Silicon), CUDA or CPU (`transformers`), picked in that order.
- A Claude agent mode (`-p anthropic`). Claude searches the records and proposes facts through tools, and a fact is
  saved only after the operator approves it.
- Streamed answers that show the current step, for example `Searching: "..."`.
- A phone web app with Markdown answers (tables, callouts, citation badges) and document upload. The page loads no
  CDN script (`marked` and DOMPurify are in `web/vendor/`) but needs `hci serve` running.
- Test cases written as JSON data and checked by pytest (retrieval) and `hci eval` (answers).

## Quick start

Requires [uv](https://github.com/astral-sh/uv) and Python 3.12.

```sh
uv sync
uv run hci -s 0 ask "In which order should I take the paths to finish first?"
uv run hci -s 0 chat                                   # follow-ups and slash commands
uv run hci -s 2 fact "Path Q is closed for maintenance"
uv run hci serve                                       # phone app, see below
```

The first run downloads the models. API keys go in `.env` (git-ignored); load it with `uv run --env-file .env hci ...`.

`-s` is the scenario index in `data/paths.json`, `-p` the provider (`mlx | cuda | cpu | anthropic`), `-m` the model.
These come before the sub-command.

The Anthropic SDK reads `ANTHROPIC_BASE_URL`. If a wrapper sets it, a direct key fails with 401, and `--env-file`
does not override it. Prefix the command with `ANTHROPIC_BASE_URL=https://api.anthropic.com`.

In `chat`, type `/` for a menu: `/fact <text>`, `/scenario [n]`, `/clear`, `/help`, `/exit`.

## Configuration

Every tunable is a field of `Settings` in `hci/config.py`, read from `HCI_<FIELD>`. That file has the full list.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HCI_PROVIDER` | fastest local | `mlx`, `cuda`, `cpu`, `anthropic` |
| `HCI_MODEL` | `mlx-community/Qwen3-4B-4bit` (MLX), `Qwen/Qwen3-4B` (CUDA), `Qwen/Qwen3-0.6B` (CPU) | local generator |
| `HCI_CLAUDE_MODEL` | `claude-sonnet-5-5` | model in agent mode |
| `HCI_AGENT_EFFORT` | `medium` | Claude effort level |
| `HCI_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | embedder |
| `HCI_K` | `6` | passages retrieved per question |
| `HCI_JEV_KEEP`, `HCI_JEV_ANSWERABLE` | `0.5`, `0.3` | Jev thresholds |
| `HCI_TOKEN` | random per run | phone API token |
| `HCI_HOST`, `HCI_PORT` | `0.0.0.0`, `8000` | server bind |
| `HCI_DOCUMENTS_DIR` | `data/documents` | documents folder, read recursively |
| `HCI_CHUNK_WORDS`, `HCI_CHUNK_OVERLAP_WORDS` | `220`, `40` | document chunk size and overlap |
| `HCI_MAX_UPLOAD_MB` | `20` | largest phone upload |
| `ANTHROPIC_API_KEY` | none | enables `-p anthropic` |
| `TYPESAFE_API_KEY` | none | enables the Jev judge |

## Phone app

```sh
uv run hci serve    # prints http://<lan-ip>:8000/#<token>
```

Open the link on a phone on the same Wi-Fi, then Share, Add to Home Screen. For each question you choose where
generation runs: on the machine running `hci serve` (nothing leaves your network), or on Claude (`anthropic`, listed
only when `ANTHROPIC_API_KEY` is set; the key stays on the server). Answers render as Markdown, sanitized with DOMPurify;
`marked` and DOMPurify are pinned in `web/vendor/`. Facts proposed by Claude appear with Approve / Reject buttons.
One local generation runs at a time.

## Documents

Drop files into `data/documents/` (subfolders included), or upload them from the phone with the Add document button.
A file that fails to parse is skipped with a warning and never breaks the index.

| Format | Sections | Paragraphs |
| --- | --- | --- |
| `.md` | `#` headings; the heading path is the section title | blank lines |
| `.docx` | `Title` and `Heading <n>` styles | one per paragraph and table row |
| `.pdf` | one per page | blank lines in the extracted text |
| `.txt` | none | blank lines |
| `.pages` | exported to PDF, then as PDF | as PDF |

Within a section, sentences are packed into chunks of at most `HCI_CHUNK_WORDS` words with `HCI_CHUNK_OVERLAP_WORDS`
of overlap. A chunk never spans two sections, and starts with its file name and section or page so answers can cite it.
`.pages` export needs macOS with Pages installed (`osascript`); elsewhere export to PDF or DOCX first.

Uploads (`POST /api/documents`) go to `data/documents/uploads/`. Limits: 401 without the token, 411 without
`Content-Length`, 413 above `HCI_MAX_UPLOAD_MB`, 415 for unsupported types, 422 for files with no extractable text.
`GET /api/documents` lists documents with chunk counts. Size guards: `HCI_MAX_DOCX_EXPANDED_MB`,
`HCI_MAX_PDF_PAGES`, `HCI_MAX_DOCUMENT_CHARS`, `HCI_PAGES_EXPORT_TIMEOUT`.

Other records: `data/paths.json` (one chunk per path step, with travel time `t = d / v`), `data/corrections/*.md`
(past mistakes with the expected answer), `data/explanations/`, and `data/facts.json` (operator facts, git-ignored).
The index is rebuilt in memory at startup and whenever these files change.

## Agent mode

With `-p anthropic`, Claude works on the records through three tools: `query_context` (search the records),
`add_context` (propose a new fact) and `list_scenarios`. A proposed fact is saved only if the operator approves it:
the CLI asks `[y/N]` and the phone shows Approve / Reject. Local models use the fixed pipeline, because they are too small to
use tools reliably. A Claude failure (bad key, rate limit, network) ends the stream with a `Claude request failed` step and a
message saying what to fix.

## Evaluation

```sh
make check-all                # format, lint, ty, pytest (unit tests + every JSON case)
uv run hci eval               # cases end to end with the LLM: JSON report of quality and latency
uv run hci eval --no-answers  # retrieval only, no LLM
uv run hci eval --jev         # filter retrieval with the Jev judge (paid, needs TYPESAFE_API_KEY)
uv run hci -p anthropic eval  # same, on Claude
```

Without `--jev`, eval never calls Jev, even when the key is set; `ask`, `chat` and `serve` do use it.

Cases live in `tests/cases/*.json` and follow `tests/cases/schema.json`: a question, optional scenario, history and
facts, and what to expect (chunk ids that must or must not be retrieved, which chunk comes first, words the answer
must or must not contain). `xfail` marks a known weakness.

Author run of `hci eval` on an M4 Pro (MLX, 45 cases), recorded on 2026-10-23 (commit b2d7654). Gemma is
`mlx-community/gemma-4-e4b-it-4bit`, set with `-m`. Retrieval does not depend on the generator, so those two rows
are the same for both:

| Metric | Qwen3-4B (default) | Gemma 4 E4B (tested, not kept) |
| --- | --- | --- |
| Retrieval pass rate | 84 % (7 paraphrase misses marked `xfail`) | 84 % |
| Recall of expected chunks | 74 % | 74 % |
| Answer pass rate | 95 % | 81 % (before the Markdown prompt) |
| Retrieval latency (p50) | 7 ms | 6 ms |
| First token (p50) | 1.25 s | 0.8 s |
| Generation | 85 tokens/s | 67 tokens/s |

## Development

| Command | Purpose |
| --- | --- |
| `make install` | `uv sync` |
| `make format-fix`, `make lint-fix` | apply ruff formatting and fixes |
| `make check-all` | `ruff format --check`, `ruff check`, `ty check`, `pytest` |
| `make eval` | `hci eval` (needs an LLM, not in `check-all`) |

All execution goes through `uv`. Unit tests mirror the modules (`tests/test_<module>.py`) and mock Anthropic, Jev and
model loading; only the case runner uses the real embedder. CI runs `uv sync --locked` then `make check-all`.
Conventions for contributors and agents are in `CLAUDE.md` and `.agents/rules/`.

## Security notes

- The `HCI_TOKEN` holder is the operator: they can upload documents, which enter the grounding corpus without review,
  and approve facts.
- `hci serve` binds `0.0.0.0` by default, so the whole LAN can reach it. Use `--host 127.0.0.1` for local only.
- The token is random per process unless `HCI_TOKEN` is set, so a Home Screen link stops working after a restart.
  Set `HCI_TOKEN` to keep it stable. The page stores the token in the browser's `localStorage`.
- The server speaks plain HTTP. On a LAN the token and answers travel unencrypted: use a trusted network or a TLS
  reverse proxy.
- API keys stay on the server and never reach the web page.

## License

[MIT](LICENSE)
