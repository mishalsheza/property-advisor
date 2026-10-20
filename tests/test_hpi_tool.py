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
