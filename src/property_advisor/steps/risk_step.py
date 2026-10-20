"""Step 5: Risk scoring.

Deterministic step (no LLM): aggregates vacancy/crime/flood/regulatory/
market-volatility risk into a single 0-100 risk_score. Sets
requires_human_review when risk_score exceeds the configured threshold,
implementing Risk-Based Routing.
"""

from __future__ import annotations

from property_advisor.config import RISK_HUMAN_REVIEW_THRESHOLD
from property_advisor.logging_utils import timed_node
from property_advisor.state import PropertyState
from property_advisor.tools.risk_data_tool import compute_risk_score, get_risk_data


@timed_node("risk_scoring_step")
def risk_scoring_step(state: PropertyState) -> dict:
    slug = state.property_data.get("locality_slug")
    risk_data = get_risk_data(slug)
    risk_assessment = compute_risk_score(risk_data)
    risk_assessment["raw_indicators"] = risk_data

    requires_human_review = state.requires_human_review or (
        risk_assessment["risk_score"] > RISK_HUMAN_REVIEW_THRESHOLD
    )

    return {
        "risk_assessment": risk_assessment,
        "requires_human_review": requires_human_review,
    }
