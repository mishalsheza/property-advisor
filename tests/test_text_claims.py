"""Directional claims in free text are checked against computed values."""

import pytest

from property_advisor.agents.recommendation_agent import _enforce_cashflow_safety_net
from property_advisor.schemas import RecommendationOutput
from property_advisor.state import PropertyState
from property_advisor.steps.guardrail_step import check_claims
from property_advisor.steps.text_claims import check_text_claims
from property_advisor.tools.financial_calculator import compute_investment_metrics
from property_advisor.tools.market_data_tool import get_market_data
from property_advisor.tools.property_data_tool import get_property_data
from property_advisor.tools.risk_data_tool import compute_risk_score, get_risk_data


def _state(address, city, locality, slug, **overrides) -> PropertyState:
    property_data = get_property_data(address)
    market_data = get_market_data(city, locality, slug=slug)
    raw = get_risk_data(slug)
    fields = dict(
        property_address=address,
        budget=property_data["price_inr"],
        property_data=property_data,
        market_data=market_data,
        investment_metrics=compute_investment_metrics(property_data, market_data, property_data["price_inr"], 5),
        risk_assessment={**compute_risk_score(raw), "raw_indicators": raw},
    )
    fields.update(overrides)
    return PropertyState(**fields)


@pytest.fixture(scope="module")
def whitefield():
    # operating cash flow +3.15 lakh/yr, after EMI -5.06 lakh/yr, risk 13.2, yield 4.42%
    return _state("Whitefield, Bangalore", "Bangalore", "Whitefield", "whitefield_bangalore")


@pytest.fixture(scope="module")
def dadar():
    # risk 80 (high flood risk), yield 2.75% vs market average 3.1%
    return _state("Dadar, Mumbai", "Mumbai", "Dadar-Kurla Belt", "dadar_kurla_mumbai")


def _reasons(text, state):
    return [c["metric"] for c in check_text_claims(text, state)]


@pytest.mark.parametrize(
    "text",
    [
        "Positive cash flow and strong appreciation support a BUY.",  # the reported case
        "The property is cash-flow positive.",
        "Cash flow after EMI is positive.",
    ],
)
def test_positive_cash_flow_claims_contradicting_after_emi_value_are_flagged(whitefield, text):
    assert _reasons(text, whitefield) == ["text:cash_flow_after_emi"]


@pytest.mark.parametrize(
    "text",
    [
        "Operating cash flow before the loan is positive, but cash flow after EMI is negative.",
        "Cash flow after EMI is not positive.",
        "Low risk and a solid yield.",
        "Appreciation is strong. [Note: pipeline-added text such as 'positive cash flow' is ignored.]",
    ],
)
def test_consistent_statements_pass(whitefield, text):
    assert _reasons(text, whitefield) == []


def test_operating_scope_is_checked_against_operating_value(whitefield):
    assert _reasons("Operating cash flow is negative.", whitefield) == ["text:operating_cash_flow"]


def test_risk_level_must_match_score_and_factor(dadar):
    assert _reasons("High flood risk weighs on the case.", dadar) == []
    assert _reasons("This is a low risk property.", dadar) == ["text:risk"]
    assert _reasons("Low flood risk.", dadar) == ["text:flood_risk"]


def test_yield_level_and_market_comparison(dadar):
    assert _reasons("Rental yield of 2.75% is below the local average of 3.1%.", dadar) == []
    assert _reasons("Rental yield is above the market average.", dadar) == ["text:yield_vs_market"]
    assert _reasons("Rental yield is below the local average of 4.5%.", dadar) == ["text:yield_benchmark"]
    assert _reasons("A strong rental yield.", dadar) == ["text:yield"]


def test_benchmark_not_in_state_is_unverified(whitefield):
    assert _reasons("ROI is well above the local average.", whitefield) == ["text:benchmark"]


def test_guardrail_checks_justification_and_statements(whitefield):
    rec = {
        "decision": "BUY",
        "justification": "Positive cash flow.",
        "confidence_score": 0.7,
        "supporting_evidence": [{"metric": "risk_score", "cited_value": 13.2, "statement": "Risk is above the city average."}],
    }
    metrics = [c["metric"] for c in check_claims(whitefield.model_copy(update={"recommendation": rec}))]
    assert metrics == ["text:benchmark", "text:cash_flow_after_emi"]


def test_leverage_warning_tier_always_warns_without_capping(whitefield):
    # 61.6% of EMI: warning tier only. The justification already says "cash flow":
    # an earlier safety net skipped its note in exactly this case.
    result = _enforce_cashflow_safety_net(
        RecommendationOutput(decision="BUY", justification="Positive cash flow.", confidence_score=0.92), whitefield
    )
    assert result.decision == "BUY"
    assert result.confidence_score == 0.92
    assert "[Warning: cash flow after EMI is negative: INR -505,550 per year" in result.justification


def test_no_warning_below_warning_tier(whitefield):
    metrics = {**whitefield.investment_metrics, "shortfall_pct_of_emi": 20.0}
    result = _enforce_cashflow_safety_net(
        RecommendationOutput(decision="BUY", justification="Strong appreciation.", confidence_score=0.92),
        whitefield.model_copy(update={"investment_metrics": metrics}),
    )
    assert "[Warning" not in result.justification


def test_leverage_cap_tier_downgrades_buy_without_strong_appreciation():
    worli = _state("Worli, Mumbai", "Mumbai", "Worli", "worli_mumbai")
    result = _enforce_cashflow_safety_net(
        RecommendationOutput(decision="BUY", justification="Prime location.", confidence_score=0.92), worli
    )
    assert result.decision == "HOLD"
    assert result.confidence_score <= 0.75
