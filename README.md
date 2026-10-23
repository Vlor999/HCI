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
  terms like path names come from BM25, paraphrases from embeddings. The current scenario's steps and facts are
  always in context.
- **Jev** ([TypeSafe AI](https://docs.typesafe.ai)): when `TYPESAFE_API_KEY` is set, one call scores every retrieved
  passage and checks whether the question can be answered at all. Below the threshold, the LLM is skipped and the
  app says it doesn't know.
- **Generation**: picks the fastest backend it finds. That's MLX on Apple Silicon, then CUDA, then CPU (`transformers`).
  Anthropic (`claude-opus-5-5`) is also available.
- **Travel times** (`t = d / v`) are computed when the data is indexed. Small models got this wrong before
  (`data/corrections/`).

## Run

```sh
uv sync
uv run hci -s 0 ask "In which order should I take the paths to finish first?"
uv run hci -s 0 chat          # follow-up questions, '/fact <text>' records an update
uv run hci fact -s 2 "Path Q is closed for maintenance"
```

Options: `-s` sets the scenario index in `data/paths.json`. `-p` picks the provider (`mlx | cuda | cpu | anthropic`).
`-m` picks the model.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HCI_PROVIDER` | fastest local | `mlx`, `cuda`, `cpu`, `anthropic` |
| `HCI_MODEL` | `mlx-community/Qwen3-4B-4bit` (MLX), `Qwen/Qwen3-4B` (CUDA), `Qwen/Qwen3-0.6B` (CPU), `claude-opus-5-5` | generator |
| `HCI_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | embedder |
| `ANTHROPIC_API_KEY` | | for `-p anthropic` |
| `TYPESAFE_API_KEY` | | turns on the Jev judge |
| `HCI_JEV_KEEP`, `HCI_JEV_ANSWERABLE` | `0.5`, `0.3` | Jev thresholds. Tune them on questions the docs can't answer. |

On an M4 Pro, a question takes about 7 s end to end with MLX, model load included.

## Phone

```sh
uv run hci serve              # prints http://<lan-ip>:8000/#<token>
```

Open the printed link on a phone on the same Wi-Fi, then use Share → Add to Home Screen. The page streams answers,
keeps the last turns as history, and saves facts. For each question you pick where generation runs:

- **on-prem**: the model runs on the machine running `hci serve` (MLX on a Mac, CUDA on a GPU box). Nothing leaves
  your network.
- **anthropic**: generation goes to Claude. The API key stays on the server and never reaches the phone.

All API calls need the token. Set `HCI_TOKEN` to keep it the same across restarts.

## Data

| File | Indexed as |
| --- | --- |
| `data/paths.json` | one chunk per path step, with travel time |
| `data/documents/sample_manual.md` | one chunk per manual section |
| `data/corrections/*.md` | past mistakes with the expected answer |
| `data/explanations/sample_explanations.json` | example explanations |
| `data/facts.json` | operator updates (git-ignored) |

The index is rebuilt in memory at startup. There are only a few dozen chunks, so a vector database isn't needed yet.

## Test

```sh
uv run pytest
```

The report and slides are in `doc/robot-explain-yourself/`. The first version (Ollama, no retrieval) is in the git
history.

## License

[MIT](LICENSE)
