"""RBI House Price Index lookup used for appreciation rates."""

from property_advisor.tools.hpi_tool import get_hpi_appreciation, hpi_city_for


def test_city_mapping():
    assert hpi_city_for("Bangalore") == "Bangalore"
    assert hpi_city_for("Noida") == "Gautam Buddha Nagar"
    assert hpi_city_for("Mumbai", "thane_west_mumbai") == "Thane"
    assert hpi_city_for("Chandigarh", "zirakpur_chandigarh") is None  # Mohali district, Punjab
    assert hpi_city_for("Gurgaon") is None


def test_bangalore_growth_hand_checked():
    # base 2022-23 series: Q1.2023-24 = 102.24, Q1.2026-27 (provisional) = 127.08
    # (127.08 / 102.24) ** (1/3) - 1 = 7.52% per year
    hpi = get_hpi_appreciation("Bangalore", window_quarters=12)
    assert hpi["hpi_window"] == "Q1.2023-24 to Q1.2026-27"
    assert (hpi["hpi_start_index"], hpi["hpi_end_index"]) == (102.24, 127.08)
    assert hpi["hpi_annualised_growth_pct"] == 7.52
    assert hpi["hpi_provisional"] is True


def test_shorter_window_and_city_without_series():
    hpi = get_hpi_appreciation("Bangalore", window_quarters=4)
    assert hpi["hpi_window"] == "Q1.2025-26 to Q1.2026-27"
    assert get_hpi_appreciation("Gurgaon") == {}


def test_volatile_when_window_and_longest_rates_diverge():
    # Lucknow: 11.99%/yr over 12 quarters vs 5.23%/yr over Q1.2022-23 to Q1.2026-27
    lucknow = get_hpi_appreciation("Lucknow")
    assert lucknow["hpi_longest_window"] == "Q1.2022-23 to Q1.2026-27"
    assert (lucknow["hpi_annualised_growth_pct"], lucknow["hpi_longest_annualised_growth_pct"]) == (11.99, 5.23)
    assert lucknow["hpi_volatile"] is True
    assert get_hpi_appreciation("Bangalore")["hpi_volatile"] is False  # 7.52 vs 6.65


def test_volatile_rate_is_never_strong_appreciation_evidence():
    from property_advisor.tools.financial_calculator import compute_investment_metrics

    prop = {"price_inr": 10_000_000, "area_sqft": 1000}
    market = {"avg_monthly_rent_per_sqft_inr": 30, "appreciation_rate_5yr_pct": 12.0}
    assert compute_investment_metrics(prop, market, 10_000_000, 5)["strong_appreciation_evidence"] is True
    volatile = {**market, "hpi_volatile": True}
    assert compute_investment_metrics(prop, volatile, 10_000_000, 5)["strong_appreciation_evidence"] is False
