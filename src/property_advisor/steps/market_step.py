"""Step 2: Market lookup.

Deterministic step (no LLM): retrieves city/locality rent and demand/supply
trends from the Market Data Tool. The appreciation rate comes from the RBI
House Price Index (city-level, base 2022-23) when the city has a series; the
synthetic mock rate is used only as a labelled fallback.
"""

from __future__ import annotations

from property_advisor.config import HPI_CITY_LEVEL_CONFIDENCE, HPI_WINDOW_QUARTERS
from property_advisor.logging_utils import timed_node
from property_advisor.state import PropertyState
from property_advisor.tools.hpi_tool import get_hpi_appreciation
from property_advisor.tools.market_data_tool import get_market_data


def _with_appreciation_source(market_data: dict, city: str, slug: str | None) -> dict:
    hpi = get_hpi_appreciation(city, slug, window_quarters=HPI_WINDOW_QUARTERS)
    market_data = {**market_data, "mock_appreciation_rate_5yr_pct": market_data.get("appreciation_rate_5yr_pct")}
    if hpi:
        return {
            **market_data,
            **hpi,
            "appreciation_rate_5yr_pct": hpi["hpi_annualised_growth_pct"],
            "appreciation_source": "rbi_hpi",
            # city-level index applied to a locality: less certain than the other inputs
            "data_quality_confidence": HPI_CITY_LEVEL_CONFIDENCE,
        }
    return {**market_data, "appreciation_source": f"mock (fallback: no RBI HPI series for {city})"}


@timed_node("market_lookup_step")
def market_lookup_step(state: PropertyState) -> dict:
    city = state.property_data.get("city", "")
    locality = state.property_data.get("locality", "")
    slug = state.property_data.get("locality_slug")

    market_data = get_market_data(city, locality, slug=slug)

    errors = list(state.errors)
    if not market_data:
        errors.append(f"No market trend data found for {locality}, {city}".strip(", "))
    else:
        market_data = _with_appreciation_source(market_data, city, slug)

    return {"market_data": market_data, "errors": errors}
