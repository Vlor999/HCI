"""Local answer generators. Each one is `(system, user) -> iterator of text chunks`."""

from collections.abc import Iterator
from threading import Thread

from loguru import logger
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BatchEncoding,
    PreTrainedTokenizerBase,
    TextIteratorStreamer,
)

from hci.config import get_settings
from hci.constants import LOCAL_MODELS
from hci.device import backend, torch_device
from hci.types import Generate


def messages(system: str, user: str) -> list[dict]:
    """Chat messages for a chat template.

    Args:
        system: The system prompt.
        user: The user turn.

    Returns:
        The system and user messages.
    """
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class MlxGenerator:
    """Streams answers from an MLX model (Apple Silicon)."""

    def __init__(self, name: str) -> None:
        """Load the model.

        Args:
            name: Hugging Face repo or local path of an MLX model.
        """
        # lazy: mlx_lm only installs on Apple Silicon
        from mlx_lm import load, stream_generate

        loaded = load(name)  # (model, tokenizer), plus a config only when return_config=True
        self.model, self.tokenizer = loaded[0], loaded[1]
        self.stream_generate = stream_generate

    def __call__(self, system: str, user: str) -> Iterator[str]:
        """Generate an answer.

        Args:
            system: The system prompt.
            user: The user turn.

        Yields:
            Text pieces as they are generated.
        """
        # enable_thinking only matters for Qwen3 templates, other templates ignore it
        prompt = self.tokenizer.apply_chat_template(
            messages(system, user), add_generation_prompt=True, enable_thinking=False
        )
        max_tokens = get_settings().local_max_tokens
        for r in self.stream_generate(self.model, self.tokenizer, prompt, max_tokens=max_tokens):
            yield r.text


class HfGenerator:
    """Streams answers from a transformers model (CUDA or CPU)."""

    def __init__(self, name: str) -> None:
        """Load the tokenizer and model on the torch device.

        Args:
            name: Hugging Face repo or local path of a causal LM.

        Raises:
            ValueError: The repo has no tokenizer.
        """
        tokenizer = AutoTokenizer.from_pretrained(name)
        if not isinstance(tokenizer, PreTrainedTokenizerBase):
            raise ValueError(f"No tokenizer found for {name}")
        self.tokenizer = tokenizer
        self.device = torch_device()
        model = AutoModelForCausalLM.from_pretrained(name, dtype="auto")
        # transformers wraps `PreTrainedModel.to` with functools.wraps, so ty binds the device to `self`
        self.model = model.to(self.device)  # ty: ignore[invalid-argument-type]

    def _encode(self, system: str, user: str) -> BatchEncoding:
        encoding = self.tokenizer.apply_chat_template(
            messages(system, user), add_generation_prompt=True, enable_thinking=False, return_tensors="pt"
        )
        if not isinstance(encoding, BatchEncoding):  # return_dict=True (default) always gives one
            raise TypeError(f"Unexpected chat template output: {type(encoding)}")
        return encoding.to(self.device)

    def _generate(self, encoding: BatchEncoding, streamer: TextIteratorStreamer, errors: list[Exception]) -> None:
        try:
            self.model.generate(**encoding, max_new_tokens=get_settings().local_max_tokens, streamer=streamer)
        except Exception as e:  # re-raised by __call__ in the consumer thread
            errors.append(e)
            streamer.end()  # unblock the consumer instead of leaving it waiting forever

    def __call__(self, system: str, user: str) -> Iterator[str]:
        """Generate an answer in a background thread.

        Args:
            system: The system prompt.
            user: The user turn.

        Yields:
            Text pieces as they are generated.

        Raises:
            Exception: Whatever `generate` raised in the background thread.
        """
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        errors: list[Exception] = []
        Thread(target=self._generate, args=(self._encode(system, user), streamer, errors)).start()
        yield from streamer
        if errors:
            raise errors[0]


def load(provider: str | None = None, model: str | None = None) -> Generate:
    """Load a local generator. Claude goes through `hci.agent`.

    Args:
        provider: `mlx`, `cuda` or `cpu`; None uses the setting, then the fastest local backend.
        model: Model name or path; None uses the setting, then the backend default.

    Returns:
        A `(system, user) -> iterator of text pieces` callable.
    """
    settings = get_settings()
    provider = provider or settings.provider or backend()
    name = model or settings.model or LOCAL_MODELS[provider]
    logger.info("Model: {} (local, {})", name, provider)
    return MlxGenerator(name) if provider == "mlx" else HfGenerator(name)
