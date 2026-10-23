"""Answer generators. Each one is `(system, user) -> iterator of text chunks`."""

import os
from collections.abc import Callable, Iterator

from hci.device import backend, torch_device

Generate = Callable[[str, str], Iterator[str]]

MAX_TOKENS = 1024
DEFAULTS = {
    "mlx": "mlx-community/Qwen3-4B-4bit",
    "cuda": "Qwen/Qwen3-4B",
    "cpu": "Qwen/Qwen3-0.6B",
    "anthropic": "claude-sonnet-5-5",
}


def messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def mlx(name: str) -> Generate:
    from mlx_lm import load, stream_generate

    model, tok = load(name)

    def gen(system: str, user: str) -> Iterator[str]:
        # enable_thinking only matters for Qwen3 templates, other templates ignore it
        prompt = tok.apply_chat_template(messages(system, user), add_generation_prompt=True, enable_thinking=False)
        for r in stream_generate(model, tok, prompt, max_tokens=MAX_TOKENS):
            yield r.text

    return gen


def hf(name: str) -> Generate:
    from threading import Thread

    from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

    device = torch_device()
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, dtype="auto").to(device)

    def gen(system: str, user: str) -> Iterator[str]:
        ids = tok.apply_chat_template(
            messages(system, user), add_generation_prompt=True, enable_thinking=False, return_tensors="pt"
        ).to(device)
        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
        Thread(
            target=model.generate, kwargs={"input_ids": ids, "max_new_tokens": MAX_TOKENS, "streamer": streamer}
        ).start()
        yield from streamer

    return gen


def anthropic(name: str) -> Generate:
    import anthropic

    client = anthropic.Anthropic()

    def gen(system: str, user: str) -> Iterator[str]:
        with client.beta.messages.stream(
            model=name,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # a declined request is retried server-side on a fallback model
        ) as stream:
            yield from stream.text_stream
            if stream.get_final_message().stop_reason == "refusal":
                yield "\n[The model declined to answer.]"

    return gen


def load(provider: str | None = None, model: str | None = None) -> Generate:
    """provider: mlx | cuda | cpu | anthropic. Defaults to the fastest local backend."""
    provider = provider or os.environ.get("HCI_PROVIDER") or backend()
    name = model or os.environ.get("HCI_MODEL") or DEFAULTS[provider]
    if provider == "anthropic":
        return anthropic(name)
    return mlx(name) if provider == "mlx" else hf(name)
