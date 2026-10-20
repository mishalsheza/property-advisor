"""House Price Index Tool.

Annualised house-price growth for a city from the RBI House Price Index
(data/rbi_hpi.csv, parsed from the RBI publication — see scripts/corpus/).
Only the base 2022-23 series is used; the older 2008-09 and 2010-11 series
are on different bases and must not be mixed with it.

The HPI is city-level, built from registration data: it says nothing about a
specific locality, which is why callers lower data quality confidence when
they use it.
"""

from __future__ import annotations

import csv
import os
from typing import Any

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rbi_hpi.csv")
BASE_YEAR = "2022-23"

# Mock-data city -> HPI city where the names differ. Localities are mapped
# explicitly when the mock city is wrong for them.
CITY_ALIASES = {"Noida": "Gautam Buddha Nagar"}
LOCALITY_OVERRIDES: dict[str, str | None] = {
    "thane_west_mumbai": "Thane",  # Thane has its own series
    "zirakpur_chandigarh": None,  # Zirakpur is in Mohali district (Punjab), not Chandigarh
}


def _load() -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {}
    with open(_DATA_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["base_year"] != BASE_YEAR:
                continue
            series.setdefault(row["city"], []).append(
                {
                    "quarter": row["quarter"],
                    "index": float(row["index_value"]),
                    "provisional": row["provisional"] == "true",
                }
            )
    # chronological order: "Q1.2022-23" -> (2022, 1)
    for rows in series.values():
        rows.sort(key=lambda r: (int(r["quarter"][3:7]), int(r["quarter"][1])))
    return series


_SERIES = _load()


def hpi_city_for(city: str, slug: str | None = None) -> str | None:
    """The HPI series to use for a mock-data locality, or None if there is none."""
    if slug in LOCALITY_OVERRIDES:
        return LOCALITY_OVERRIDES[slug]
    name = CITY_ALIASES.get(city, city)
    return name if name in _SERIES else None


def _annualised(start: dict, end: dict, quarters: int) -> float:
    return ((end["index"] / start["index"]) ** (4 / quarters) - 1) * 100


def get_hpi_appreciation(
    city: str, slug: str | None = None, window_quarters: int = 12, volatility_threshold_pts: float = 4.0
) -> dict[str, Any]:
    """Annualised growth over the last `window_quarters` quarters of the city's
    base 2022-23 HPI series, cross-checked against the longest available
    window: if the two rates differ by more than `volatility_threshold_pts`
    percentage points, the rate is flagged volatile. Returns {} when there is
    no series for the city."""
    hpi_city = hpi_city_for(city, slug)
    rows = _SERIES.get(hpi_city or "", [])
    if len(rows) <= window_quarters:
        return {}
    start, end, first = rows[-1 - window_quarters], rows[-1], rows[0]
    rate = _annualised(start, end, window_quarters)
    longest_quarters = len(rows) - 1
    longest_rate = _annualised(first, end, longest_quarters)
    return {
        "hpi_city": hpi_city,
        "hpi_base_year": BASE_YEAR,
        "hpi_window": f"{start['quarter']} to {end['quarter']}",
        "hpi_start_index": start["index"],
        "hpi_end_index": end["index"],
        "hpi_annualised_growth_pct": round(rate, 2),
        "hpi_longest_window": f"{first['quarter']} to {end['quarter']}",
        "hpi_longest_annualised_growth_pct": round(longest_rate, 2),
        "hpi_volatile": abs(rate - longest_rate) > volatility_threshold_pts,
        "hpi_provisional": start["provisional"] or end["provisional"],
    }
