"""API request models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Provider(StrEnum):
    """Where generation runs."""

    MLX = "mlx"
    CUDA = "cuda"
    CPU = "cpu"
    ANTHROPIC = "anthropic"


class AskRequest(BaseModel):
    """A question from the phone."""

    question: str = Field(..., min_length=1, max_length=2000, description="The question to answer.")
    scenario: int | None = Field(default=None, ge=0, description="Current scenario index; None for no scenario.")
    provider: Provider | None = Field(default=None, description="Where generation runs; None picks the local backend.")
    history: list[tuple[str, str]] = Field(
        default_factory=list, max_length=10, description="Previous (question, answer) turns, oldest first."
    )


class FactRequest(BaseModel):
    """An operator-approved fact to save."""

    text: str = Field(..., min_length=1, max_length=500, description="The fact, one self-contained sentence.")
    scenario: int | None = Field(default=None, ge=0, description="Scenario it applies to; None for everywhere.")
