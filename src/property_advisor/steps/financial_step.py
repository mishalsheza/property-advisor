"""Step 4: Financial calculation.

Deterministic step (no LLM): ROI/cap-rate/rental-yield/cash-flow/break-even
calculations in INR. Financial calculations must be deterministic.
"""

from __future__ import annotations

from property_advisor.config import HURDLE_RATE_PCT, STAMP_DUTY_REGISTRATION_PCT
from property_advisor.logging_utils import timed_node
from property_advisor.state import PropertyState
from property_advisor.tools.financial_calculator import compute_investment_metrics


@timed_node("financial_calc_step")
def financial_calc_step(state: PropertyState) -> dict:
    metrics = compute_investment_metrics(
        property_data=state.property_data,
        market_data=state.market_data,
        budget=state.budget,
        horizon_years=state.investment_horizon_years,
        loan_to_value_ratio=state.loan_to_value_pct / 100,
        interest_rate_pct=state.interest_rate_pct,
        loan_tenure_years=state.loan_tenure_years,
        stamp_duty_registration_pct=STAMP_DUTY_REGISTRATION_PCT,
        hurdle_rate_pct=HURDLE_RATE_PCT,
    )
    return {"investment_metrics": metrics}
