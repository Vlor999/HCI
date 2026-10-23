"""Cost estimates from logged usage: Claude by the model that answered (`MODEL_PRICES`), Jev from the settings.

Estimates only: they apply list prices to the usage the APIs report, and know nothing of discounts or batch rates.
"""

from hci.config import get_settings
from hci.constants import CACHE_WRITE_MULTIPLIER, MODEL_PRICES, TOKENS_PER_PRICE_UNIT
from hci.types import CostBreakdown


def model_price(model: str | None) -> dict[str, float] | None:
    """The listed price of a Claude model, matching dated ids (`claude-sonnet-5-5-20261001`) to their alias.

    Args:
        model: Model id as the API returned it.

    Returns:
        USD per million tokens by component, or None when the model is not listed.
    """
    if not model:
        return None
    return next((p for name, p in MODEL_PRICES.items() if model == name or model.startswith(name + "-")), None)


def _usd(tokens: int | None, per_mtok: float) -> float:
    return round((tokens or 0) * per_mtok / TOKENS_PER_PRICE_UNIT, 8)


def claude_cost(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int | None,
    cache_read_tokens: int | None,
) -> CostBreakdown | None:
    """Cost of one Claude turn.

    Args:
        model: Model that answered.
        input_tokens: Prompt tokens, cache excluded.
        output_tokens: Generated tokens.
        cache_write_tokens: Prompt tokens written to the cache (priced at `CACHE_WRITE_MULTIPLIER` x input).
        cache_read_tokens: Prompt tokens read from the cache.

    Returns:
        The cost by component, or None when the model or a component it used has no listed price.
    """
    price = model_price(model)
    if price is None or (cache_read_tokens and "cache_read" not in price):
        return None
    return CostBreakdown(
        input_usd=_usd(input_tokens, price["input"]),
        output_usd=_usd(output_tokens, price["output"]),
        cache_write_usd=_usd(cache_write_tokens, price["input"] * CACHE_WRITE_MULTIPLIER),
        cache_read_usd=_usd(cache_read_tokens, price.get("cache_read", 0)),
    )


def jev_cost(input_tokens: int | None, output_tokens: int | None) -> CostBreakdown | None:
    """Cost of one Jev call, from the `jev_price_*_per_mtok` settings.

    Args:
        input_tokens: Jev usage, input side.
        output_tokens: Jev usage, output side.

    Returns:
        The cost (in `jev_usd`), or None when a price setting or the usage is missing.
    """
    settings = get_settings()
    input_price, output_price = settings.jev_price_input_per_mtok, settings.jev_price_output_per_mtok
    if input_price is None or output_price is None or input_tokens is None or output_tokens is None:
        return None
    return CostBreakdown(jev_usd=round(_usd(input_tokens, input_price) + _usd(output_tokens, output_price), 8))
