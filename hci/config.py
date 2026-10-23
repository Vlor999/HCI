"""Tunable settings, read from the environment (`HCI_*`, plus `TYPESAFE_API_KEY`)."""

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from hci.constants import CLAUDE_MODEL, FACTS_FILE
from hci.schemas import Provider


class Settings(BaseSettings):
    """Every tunable of the app. Env name: `HCI_<FIELD>` unless an alias says otherwise."""

    model_config = SettingsConfigDict(env_prefix="HCI_")

    provider: Provider | None = Field(default=None, description="Generation provider; None picks the fastest local.")
    model: str | None = Field(default=None, description="Local model name or path; None uses the backend default.")
    claude_model: str = Field(default=CLAUDE_MODEL, description="Claude model used in agent mode.")
    embed_model: str = Field(default="BAAI/bge-small-en-v1.5", description="Sentence-transformers embedder.")
    jev_model: str = Field(default="jev-latest", description="Jev judge model.")
    jev_keep: float = Field(default=0.5, description="Min P(relevant) for Jev to keep a passage.")
    jev_answerable: float = Field(
        default=0.3, description="Min P(answerable) below which the question is refused. Tune on out-of-docs questions."
    )
    jev_timeout: float = Field(default=10, description="Jev HTTP timeout in seconds.")
    typesafe_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TYPESAFE_API_KEY"),
        description="TypeSafe API key; enables the Jev judge when set.",
    )
    token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(16),
        description="Bearer token for the HTTP API; random per process when unset.",
    )
    k: int = Field(default=6, description="Passages retrieved by search, on top of the pinned ones.")
    history_turns: int = Field(default=3, description="Previous turns included in the local prompt.")
    agent_max_iterations: int = Field(default=8, description="Max model turns in the agent tool loop.")
    agent_max_tokens: int = Field(default=16000, description="Max output tokens per agent turn.")
    agent_effort: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="medium", description="Claude effort level in agent mode."
    )
    local_max_tokens: int = Field(default=1024, description="Max new tokens for local generation.")
    host: str = Field(default="0.0.0.0", description="Server bind address (0.0.0.0 for phone access on the LAN).")
    port: int = Field(default=8000, description="Server port.")
    facts_file: Path = Field(default=FACTS_FILE, description="JSON file of operator-approved facts.")


@lru_cache
def get_settings() -> Settings:
    """Settings, read once per process.

    Returns:
        The cached `Settings`.
    """
    return Settings()
