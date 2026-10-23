# HCI: Robot, explain yourself

A RAG that explains why a forest robot picked a path. It answers from the robot's own records: past paths, the
operating manual, past corrections and operator updates.

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

On Linux, `uv sync` installs CPU-only torch (`[tool.uv.sources]` in `pyproject.toml`, for CI). On a CUDA box, remove
that `torch` source.

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
keeps the last turns as history, and saves facts. For each question you pick where generation runs:

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
| `data/documents/sample_manual.md` | one chunk per manual section |
| `data/corrections/*.md` | past mistakes with the expected answer |
| `data/explanations/sample_explanations.json` | example explanations |
| `data/facts.json` | operator updates (git-ignored) |

The index is rebuilt in memory at startup. There are only a few dozen chunks, so a vector database isn't needed yet.

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
chunk ids that must or must not be in the context, chunks that must come first, and words the answer must contain
or must not contain. `xfail` marks a known weakness, and the case still runs.

`hci eval` on an M4 Pro (MLX, 45 cases):

| Metric | Qwen3-4B (default) | Gemma 4 E4B (tested, not kept) |
| --- | --- | --- |
| Retrieval pass rate | 84 % (7 paraphrase misses marked `xfail`) | same |
| Recall of expected chunks | 74 % | same |
| Answer pass rate | 90 % | 81 % |
| Retrieval latency (p50) | 7 ms | 6 ms |
| First token (p50) | 1.25 s | 0.8 s |
| Generation | 85 tokens/s | 67 tokens/s |

The report and slides are in `doc/robot-explain-yourself/`. The first version (Ollama, no retrieval) is in the git
history.

## License

[MIT](LICENSE)
