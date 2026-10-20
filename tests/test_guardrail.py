"""Unit tests for the deterministic guardrail claim check (no LLM)."""

from property_advisor.state import PropertyState
from property_advisor.steps.guardrail_step import check_claims, guardrail_step


def _state(evidence, **overrides) -> PropertyState:
    fields = dict(
        property_address="Whitefield, Bangalore",
        budget=9_500_000,
        property_data={"price_inr": 9_500_000, "city": "Bangalore"},
        market_data={"appreciation_rate_5yr_pct": 9.5},
        investment_metrics={
            "roi_pct": 28.74,
            "rental_yield_pct": 3.2,
            "annual_cash_flow_inr": -412_000.0,
            "cash_flow_severity": "positive",
            "break_even_years": None,
        },
        risk_assessment={"risk_score": 20.1},
        rag_context=[{"source": "model_tenancy_act_2021_prs.txt", "text": "..."}],
        recommendation={
            "decision": "BUY",
            "justification": "Strong appreciation.",
            "confidence_score": 0.8,
            "supporting_evidence": evidence,
        },
    )
    fields.update(overrides)
    return PropertyState(**fields)


def _ev(metric, value):
    return {"metric": metric, "cited_value": value, "statement": f"{metric} is {value}"}


def test_values_within_tolerance_are_supported():
    evidence = [
        _ev("roi_pct", 28.7),
        _ev("annual_cash_flow_inr", "-4,10,000"),  # Indian digit grouping, within 2%
        _ev("risk_score", "20"),
        _ev("price_inr", 9_500_000),
        _ev("appreciation_rate_5yr_pct", "9.5%"),
    ]
    assert check_claims(_state(evidence)) == []


def test_value_outside_tolerance_is_unsupported():
    unsupported = check_claims(_state([_ev("roi_pct", 35.0)]))
    assert len(unsupported) == 1
    assert unsupported[0]["computed_value"] == 28.74


def test_unknown_metric_is_unsupported():
    unsupported = check_claims(_state([_ev("vacancy_rate_pct", 4.0)]))
    assert unsupported[0]["reason"].startswith("unknown metric")


def test_string_metrics_must_match_exactly():
    assert check_claims(_state([_ev("cash_flow_severity", "Positive")])) == []
    assert len(check_claims(_state([_ev("cash_flow_severity", "mildly_negative")]))) == 1


def test_none_valued_metric_accepts_never():
    assert check_claims(_state([_ev("break_even_years", "never")])) == []
    assert len(check_claims(_state([_ev("break_even_years", 12)]))) == 1


def test_rag_source_must_be_retrieved():
    assert check_claims(_state([_ev("rag_source", "model_tenancy_act_2021_prs.txt")])) == []
    assert len(check_claims(_state([_ev("rag_source", "made_up_report.txt")]))) == 1


def test_unsupported_claims_request_reanalysis_then_human_review_with_unverified_list():
    evidence = [_ev("roi_pct", 99.0)]
    first = guardrail_step(_state(evidence))
    assert first["guardrail_result"]["status"] == "request_reanalysis"
    assert first["unverified_claims"] == []

    exhausted = guardrail_step(_state(evidence, reanalysis_retry_count=2))
    assert exhausted["guardrail_result"]["status"] == "human_review_required"
    assert exhausted["unverified_claims"][0]["metric"] == "roi_pct"


def test_missing_property_data_is_refused():
    result = guardrail_step(_state([], property_data={}))
    assert result["guardrail_result"]["status"] == "refuse"


def test_missing_decision_is_refused():
    result = guardrail_step(_state([], recommendation={}))
    assert result["guardrail_result"]["status"] == "refuse"


def test_conflict_check_is_disabled_and_reported():
    rag = [
        {"source": "hinjewadi_bullish_analyst_note.txt", "text": "..."},
        {"source": "hinjewadi_bearish_analyst_note.txt", "text": "..."},
    ]
    result = guardrail_step(_state([], rag_context=rag))["guardrail_result"]
    assert result["conflict_check"] == "disabled"
    assert result["conflicting_evidence"] is False
