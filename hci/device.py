"""Picks the fastest backend available: MLX on Apple Silicon, then CUDA, then CPU."""

import importlib.util
import platform
from functools import cache

import torch


@cache
def backend() -> str:
    """Fastest local generation backend.

    Returns:
        `mlx` on Apple Silicon with `mlx_lm` installed, else `cuda` when available, else `cpu`.
    """
    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_lm"):
        return "mlx"
    return "cuda" if torch.cuda.is_available() else "cpu"


def torch_device() -> str:
    """Device for torch models (embeddings, HF generation).

    Returns:
        `cuda`, `mps` or `cpu`, the first available.
    """
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"
