# HCI: Robot, explain yourself

A RAG that explains why a forest robot picked a path. It answers from the robot's own records: past paths,
documents (the operating manual, reports, uploads), past corrections and operator updates.

```
question ─► hybrid retrieval ─► Jev judge (optional) ─► grounded prompt ─► LLM ─► answer with [n] citations
            (bge embeddings       drops irrelevant        current scenario        MLX / CUDA / CPU
             + BM25, RRF)         passages, refuses       always in context       or Anthropic
                                  unanswerable questions
```

- **Retrieval**: dense embeddings (`BAAI/bge-small-en-v1.5`) and BM25, fused with reciprocal rank fusion. Exact
  terms like path names come from BM25, paraphrases from embeddings. The current scenario's steps and facts, plus
  facts that apply everywhere, are always in context. Other scenarios are never searched. A follow-up question is
  searched together with the previous one.
- **Jev** ([TypeSafe AI](https://docs.typesafe.ai)): when `TYPESAFE_API_KEY` is set, one call scores every retrieved
  passage and checks whether the question can be answered at all. Below the threshold, the LLM is skipped and the
  app says it doesn't know.
- **Generation**: picks the fastest backend it finds. That's MLX on Apple Silicon, then CUDA, then CPU (`transformers`).
- **Agent mode** (`-p anthropic`, `claude-sonnet-5-5`, effort `medium`): Claude drives the memory itself through
  three tools. `query_context` searches the records, as many times as needed. `add_context` proposes a new fact.
  `list_scenarios` lists the scenarios. Facts are never saved without the operator: the CLI asks `[y/N]`, and the
  phone shows Approve / Reject buttons. Local models keep the fixed pipeline, because they are too small to use
  tools reliably.
- **Streaming with steps**: answers stream token by token. The current step is shown as it happens: thinking,
  `Searching: "..."`, `Found 9 passages`, `Proposing fact: "..."`. The CLI prints steps in grey, the phone above the
  answer. On the wire, a step is a line that starts with `\x1f`; facts the agent proposes come last, after `\x1e`, as
  a JSON list. Both markers are defined once, in `hci/constants.py`.
- **Errors**: a Claude failure (bad key, rate limit, network) ends the stream with a `Claude request failed` step and
  a message saying what to fix. A Jev outage keeps every passage. A corrupt `facts.json` is renamed
  `facts.json.corrupt-<timestamp>` and logged, so the next fact cannot overwrite it.
- **Travel times** (`t = d / v`) are computed when the data is indexed. Small models got this wrong before
  (`data/corrections/`).

## Run

```sh
uv sync
# API keys go in .env (git-ignored), e.g. ANTHROPIC_API_KEY=... ; load it with: uv run --env-file .env hci ...
uv run hci -s 0 ask "In which order should I take the paths to finish first?"
uv run hci -s 0 chat          # follow-up questions and slash commands
uv run hci fact -s 2 "Path Q is closed for maintenance"
```

Chat commands (type `/` for a fuzzy menu):

| Command | Does |
| --- | --- |
| `/fact <text>` | save an operator update for the current scenario (prints the usage without text) |
| `/scenario [n]` | show the current scenario, or switch to `n` (checked against `data/paths.json`; clears the conversation) |
| `/clear` | forget the conversation |
| `/help` | list commands |
| `/exit` | quit (Ctrl-D works too) |

To add a command, add it to `COMMANDS` in `hci/constants.py` and write `ChatSession.cmd_<name>` in `hci/cli.py`.
A command without its method fails at import.

Options: `-s` sets the scenario index in `data/paths.json`. `-p` picks the provider (`mlx | cuda | cpu | anthropic`).
`-m` picks the model.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HCI_PROVIDER` | fastest local | `mlx`, `cuda`, `cpu`, `anthropic` (agent mode) |
| `HCI_MODEL` | `mlx-community/Qwen3-4B-4bit` (MLX), `Qwen/Qwen3-4B` (CUDA), `Qwen/Qwen3-0.6B` (CPU) | local generator. `-m` also picks the Claude model (default `claude-sonnet-5-5`). |
| `HCI_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | embedder |
| `ANTHROPIC_API_KEY` | | for `-p anthropic` |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | the SDK honours it. A proxy that sets it (e.g. a CLI wrapper) makes direct keys fail with 401. `--env-file` does not override it, so prefix the command with `ANTHROPIC_BASE_URL=https://api.anthropic.com`. |
| `TYPESAFE_API_KEY` | | turns on the Jev judge |
| `HCI_JEV_KEEP`, `HCI_JEV_ANSWERABLE` | `0.5`, `0.3` | Jev thresholds. Tune them on questions the docs can't answer. |

Every tunable (retrieval `k`, Jev timeout, agent limits, server host and port, facts file...) is a field of
`Settings` in `hci/config.py`, read from `HCI_<FIELD>` (e.g. `HCI_K=8`, `HCI_PORT=9000`). Nothing else reads the
environment.


## Phone

```sh
uv run hci serve              # prints http://<lan-ip>:8000/#<token>
```

Open the printed link on a phone on the same Wi-Fi, then use Share → Add to Home Screen. The page streams answers,
keeps the last turns as history, and saves facts. Answers render as Markdown with Notion-like extras: tables,
checklists, `> [!NOTE|TIP|IMPORTANT|WARNING|CAUTION]` callouts and `[1.2]` citation badges. The model output is
sanitized with DOMPurify; marked and DOMPurify are pinned copies in `web/vendor/`, served by `hci serve`, so the page
works offline. For each question you pick where generation runs:

- **on-prem**: the model runs on the machine running `hci serve` (MLX on a Mac, CUDA on a GPU box). Nothing leaves
  your network.
- **anthropic**: generation goes to Claude. The API key stays on the server and never reaches the phone. Listed
  only when `ANTHROPIC_API_KEY` is set; asking for it otherwise gives 400.

One local generation runs at a time (local models are not thread-safe). Claude answers and fact approvals never wait
for it.

All API calls need the token. Set `HCI_TOKEN` to keep it the same across restarts. The server speaks plain HTTP: on
the LAN, the token and answers travel unencrypted. Use a trusted network, or put a TLS reverse proxy (Caddy, nginx) in
front.

## Data

| File | Indexed as |
| --- | --- |
| `data/paths.json` | one chunk per path step, with travel time |
| `data/documents/**` | documents (`.md`, `.txt`, `.pdf`, `.docx`, `.pages`), cut as below; the manual is one of them |
| `data/corrections/*.md` | past mistakes with the expected answer |
| `data/explanations/sample_explanations.json` | example explanations |
| `data/facts.json` | operator updates (git-ignored) |

Chunk ids are explicit file references, so a test or a citation points at a real file: `data/paths.json#0/A`
(scenario 0, path A), `data/documents/sample_manual.md#3` (third chunk of the manual, counted from 1),
`data/corrections/correction_1.md`, `data/explanations/sample_explanations.json#4` (array index). Operator facts
keep `fact-<n>`: the facts file is runtime state outside git. Document ids are positional: editing a document
renumbers the chunks after the edit, so a case that names one can silently point at another passage. pytest only
checks that the id still exists, so re-check the cases that cite a document after editing it.

The index is rebuilt in memory at startup, and again when a file under `data/`, the documents folder or the facts
file changes, so a running server picks up new documents without a restart. Each file is parsed once per version
(mtime and size), so a reload only re-reads what changed. There are only a few dozen chunks, so a vector database isn't needed yet.

## Documents

Drop files into `data/documents/` (subfolders included), or upload them from the phone with **Add document**.
Supported: Markdown, plain text, PDF (`pypdf`), Word `.docx` (`python-docx`) and Apple Pages. Hidden files and other
types are ignored; a file that fails to parse is skipped with a warning and never breaks the index. Text files are
read as UTF-8 (a BOM is dropped); other encodings are flagged in the log.

Segmentation goes structure first, then size:

| Format | Sections | Paragraphs |
| --- | --- | --- |
| `.md` | `#` headings; the heading path (`Robot manual > 1. Energy Management`) is the section title | blank lines |
| `.docx` | `Title` and `Heading <n>` paragraph styles, same heading path (Title above Heading 1) | one per DOCX paragraph, one per table row, in body order |
| `.pdf` | one per page (`page 3`); ligatures normalised (NFKC) | blank lines in the extracted text |
| `.txt` | none | blank lines |
| `.pages` | exported to PDF, then as PDF | as PDF |

Inside a section, sentences are packed into chunks of at most `HCI_CHUNK_WORDS` words (default 220, about 300
tokens, under the 512-token limit of `bge-small`), and the next chunk repeats up to `HCI_CHUNK_OVERLAP_WORDS` words
(default 40) of whole trailing sentences. A chunk never spans two sections, and a sentence is only cut when it is
longer than a chunk by itself. Every chunk starts with its file name and section or page
(`report.pdf, page 3: ...`), so the model can say where an answer comes from.

`.pages` files are a zip of Apple's private protobuf format. On macOS with Pages installed, they are exported to a
temporary PDF through the Pages app (`osascript`; the first run may ask to allow automation of Pages). Elsewhere the
file is skipped with a warning: export it from Pages as PDF or DOCX and add that instead.

Phone uploads (`POST /api/documents`, multipart, token required) land in `data/documents/uploads/` (git-ignored).
The token holder is the operator: an upload is an operator action, and its text enters the grounding corpus with no
further review, like a file dropped into `data/documents/`.
The token and the declared size (`Content-Length`) are checked from the headers before the body is read: 401 without
the token, 411 without a length, 413 above `HCI_MAX_UPLOAD_MB` (default 20). The file name is reduced to its base name
(no folders, no leading dot, at most 120 bytes), and a name already taken gets `-1`, `-2`... An unsupported type gives
415. A file that cannot be indexed (no readable text, as in a scanned PDF, or over a size bound below) gives 422 with
the reason and is not kept. `GET /api/documents` lists the documents with their chunk
counts.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HCI_DOCUMENTS_DIR` | `data/documents` | folder indexed recursively; uploads go to its `uploads/` subfolder |
| `HCI_CHUNK_WORDS` | `220` | max words per document chunk |
| `HCI_CHUNK_OVERLAP_WORDS` | `40` | overlap between chunks of a section (must be below `HCI_CHUNK_WORDS`) |
| `HCI_MAX_UPLOAD_MB` | `20` | largest upload |
| `HCI_MAX_DOCX_EXPANDED_MB` | `100` | largest uncompressed DOCX, checked before opening it (zip bomb guard) |
| `HCI_MAX_PDF_PAGES` | `500` | larger PDFs are skipped |
| `HCI_MAX_DOCUMENT_CHARS` | `2000000` | documents with more extracted text are skipped |
| `HCI_PAGES_EXPORT_TIMEOUT` | `60` | seconds for the Pages export |

## Test and evaluate

```sh
make check-all                # format, lint, ty, then pytest: unit tests + every case in tests/cases/*.json
uv run hci eval               # same cases end to end with the LLM: JSON report of quality and latency
uv run hci -p anthropic eval  # same, on Claude
```

Unit tests mirror the modules (`tests/test_<module>.py`) and mock Anthropic, Jev and model loading. Only the case
runner uses the real embedder (downloaded once). CI runs `uv sync --locked` then `make check-all`.

Each file in `tests/cases/` is a JSON list of cases. The format is defined in `tests/cases/schema.json`, and pytest
validates every file against it. A case gives a question, an optional scenario, history and facts, and what to expect:
chunk ids that must or must not be in the context (pytest checks that each one names an existing file and a real
chunk), chunks that must come first, and words the answer must all contain, at least one of
(`answer_contains_any`), or must not contain. `unanswerable` marks a question the records do not answer: the answer
must refuse (it contains one of the refusal markers of `hci/constants.py`), and with `--jev` retrieval passes when Jev
refuses rather than on the pinned chunks. `xfail` marks a known weakness, and the case still runs.

`hci eval` on an M4 Pro (MLX, 45 cases):

| Metric | Qwen3-4B (default) | Gemma 4 E4B (tested, not kept) |
| --- | --- | --- |
| Retrieval pass rate | 84 % (7 paraphrase misses marked `xfail`) | same |
| Recall of expected chunks | 74 % | same |
| Answer pass rate | 95 % | 81 % (before the Markdown prompt) |
| Retrieval latency (p50) | 7 ms | 6 ms |
| First token (p50) | 1.25 s | 0.8 s |
| Generation | 85 tokens/s | 67 tokens/s |

The report and slides are in `doc/robot-explain-yourself/`. The first version (Ollama, no retrieval) is in the git
history.

## License

[MIT](LICENSE)
