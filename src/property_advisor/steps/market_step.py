"""Step 2: Market lookup.

Deterministic step (no LLM): retrieves city/locality appreciation and
demand/supply trends from the Market Data Tool.
"""

from __future__ import annotations

from property_advisor.logging_utils import timed_node
from property_advisor.state import PropertyState
from property_advisor.tools.market_data_tool import get_market_data


@timed_node("market_lookup_step")
def market_lookup_step(state: PropertyState) -> dict:
    city = state.property_data.get("city", "")
    locality = state.property_data.get("locality", "")
    slug = state.property_data.get("locality_slug")

    market_data = get_market_data(city, locality, slug=slug)

    errors = list(state.errors)
    if not market_data:
        errors.append(f"No market trend data found for {locality}, {city}".strip(", "))

    return {"market_data": market_data, "errors": errors}
