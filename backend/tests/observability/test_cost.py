"""Cost estimation degrades to null instead of inventing prices (Spec 14)."""

from decimal import Decimal

import pytest

from app.core.config import Settings
from app.services.observability.traces import estimate_cost_usd


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_cost_uses_configured_per_million_prices() -> None:
    settings = _settings(openai_input_cost_per_1m="2.50", openai_output_cost_per_1m="10")
    # 1000 * 2.5/1M + 200 * 10/1M = 0.0025 + 0.002
    assert estimate_cost_usd(settings, 1000, 200) == Decimal("0.004500")
    assert settings.cost_estimation_configured is True


@pytest.mark.parametrize(
    "prices",
    [
        {},
        {"openai_input_cost_per_1m": "2.5"},
        {"openai_output_cost_per_1m": "10"},
    ],
)
def test_cost_is_null_when_a_price_is_not_configured(prices: dict[str, str]) -> None:
    settings = _settings(**prices)
    assert settings.cost_estimation_configured is False
    assert estimate_cost_usd(settings, 1000, 200) is None


@pytest.mark.parametrize("tokens", [(None, 200), (1000, None), (None, None)])
def test_cost_is_null_when_usage_was_not_reported(tokens: tuple[int | None, int | None]) -> None:
    settings = _settings(openai_input_cost_per_1m="2.5", openai_output_cost_per_1m="10")
    assert estimate_cost_usd(settings, *tokens) is None


def test_zero_prices_are_a_real_zero_cost() -> None:
    settings = _settings(openai_input_cost_per_1m="0", openai_output_cost_per_1m="0")
    assert estimate_cost_usd(settings, 1000, 200) == Decimal("0")


def test_negative_prices_are_rejected() -> None:
    with pytest.raises(ValueError):
        _settings(openai_input_cost_per_1m="-1")


def test_no_pricing_is_hard_coded_by_default() -> None:
    settings = _settings()
    assert settings.openai_input_cost_per_1m is None
    assert settings.openai_output_cost_per_1m is None
