"""Tests for hci.llm: the transformers generator's background thread."""

from functools import partial
from unittest.mock import MagicMock, patch

import pytest
import torch
from transformers import BatchEncoding, PreTrainedTokenizerBase, TextIteratorStreamer

from hci.llm import HfGenerator


def _make_generator(generate_error: Exception) -> HfGenerator:
    tokenizer = MagicMock(spec=PreTrainedTokenizerBase)
    tokenizer.apply_chat_template.return_value = BatchEncoding({"input_ids": torch.tensor([[1, 2]])})
    with (
        patch("hci.llm.AutoTokenizer.from_pretrained", return_value=tokenizer),
        patch("hci.llm.AutoModelForCausalLM.from_pretrained") as load_model,
        patch("hci.llm.torch_device", return_value="cpu"),
    ):
        load_model.return_value.to.return_value.generate.side_effect = generate_error
        return HfGenerator("fake/model", "cpu")


def test_generate_error_is_reraised_not_hung():
    """An error in the generation thread reaches the consumer instead of leaving it waiting."""
    # Arrange
    generator = _make_generator(RuntimeError("CUDA out of memory"))
    # a hang would surface as queue.Empty after 5 s, failing the test instead of blocking it
    streamer = partial(TextIteratorStreamer, timeout=5)
    # Act / Assert
    with patch("hci.llm.TextIteratorStreamer", streamer), pytest.raises(RuntimeError, match="out of memory"):
        list(generator("system", "user"))
