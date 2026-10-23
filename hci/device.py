"""Picks the fastest backend available: MLX on Apple Silicon, then CUDA, then CPU."""

import importlib.util
import platform
from functools import cache


@cache
def backend() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64" and importlib.util.find_spec("mlx_lm"):
        return "mlx"
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def torch_device() -> str:
    """Device for torch models (embeddings, HF generation)."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"
