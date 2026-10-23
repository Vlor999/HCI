"""Tests for hci.pricing: Claude cost per component, model matching, unknown prices and Jev settings."""

import pytest

from hci import pricing
from hci.config import get_settings
from hci.types import CostBreakdown

MTOK = 1_000_000


class TestClaudeCost:
    def test_each_component_uses_its_price(self):
        """Sonnet 5.5: input 2, output 10, cache write 1.25 x input, cache read 0.20 USD per million tokens."""
        # Act
        cost = pricing.claude_cost("claude-sonnet-5-5", MTOK, MTOK, MTOK, MTOK)
        # Assert
        assert cost == CostBreakdown(input_usd=2.0, output_usd=10.0, cache_write_usd=2.5, cache_read_usd=0.2)
        assert cost.total == 14.7

    def test_small_turn(self):
        """A real-sized turn: 1434 in, 76 out on Sonnet 5.5."""
        # Act
        cost = pricing.claude_cost("claude-sonnet-5-5", 1434, 76, 0, 0)
        # Assert
        assert cost is not None and cost.total == pytest.approx(0.003628)

    def test_dated_model_id_matches_its_alias(self):
        """A dated id returned by the API is priced like its alias."""
        # Act / Assert
        assert pricing.model_price("claude-opus-5-5-20261001") == pricing.model_price("claude-opus-5-5")

    @pytest.mark.parametrize(
        ("model", "cache_read"), [("claude-mystery-9", 0), (None, 0), ("claude-haiku-5-5", 10)], ids=str
    )
    def test_unknown_price_gives_none(self, model, cache_read):
        """An unlisted model, or a component its listing lacks (Haiku cache read), is never guessed."""
        # Act / Assert
        assert pricing.claude_cost(model, 10, 10, 0, cache_read) is None

    def test_listed_model_without_cache_read_still_prices_other_tokens(self):
        """Haiku 5.5 without cache reads is priced from its input and output prices."""
        # Act
        cost = pricing.claude_cost("claude-haiku-5-5", MTOK, MTOK, 0, 0)
        # Assert
        assert cost is not None and cost.total == 0.6


class TestJevCost:
    def test_unset_prices_give_none(self):
        """Without the Jev price settings, the Jev cost is unknown."""
        # Act / Assert
        assert pricing.jev_cost(1000, 100) is None

    def test_set_prices_price_the_usage(self, monkeypatch):
        """With both Jev prices set, input and output are priced into `jev_usd`."""
        # Arrange
        monkeypatch.setenv("HCI_JEV_PRICE_INPUT_PER_MTOK", "1.0")
        monkeypatch.setenv("HCI_JEV_PRICE_OUTPUT_PER_MTOK", "4.0")
        get_settings.cache_clear()
        # Act
        cost = pricing.jev_cost(MTOK, MTOK // 2)
        # Assert
        assert cost == CostBreakdown(jev_usd=3.0)
