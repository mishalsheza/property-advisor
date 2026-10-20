"""End-to-end graph and API tests with a stubbed LLM and stubbed retrieval.

Cover the routing that must keep working: data retry gate, guardrail
re-analysis loop, human-review interrupt with approve/reject, and refusal.
"""

import pytest
from langgraph.types import Command

from property_advisor.graph import build_graph
from property_advisor.tools.risk_data_tool import compute_risk_score, get_risk_data

WHITEFIELD = {
    "property_address": "Whitefield, Bangalore, 560066",
    "budget": 9_500_000.0,
    "investment_horizon_years": 5,
    "investment_strategy": "rental",
}
WHITEFIELD_RISK = compute_risk_score(get_risk_data("whitefield_bangalore"))["risk_score"]


def _rec(evidence):
    return {
        "decision": "BUY",
        "justification": "Strong appreciation with acceptable risk.",
        "supporting_evidence": evidence,
        "confidence_score": 0.8,
    }


GOOD = _rec([{"metric": "risk_score", "cited_value": WHITEFIELD_RISK, "statement": "Low risk."}])
BAD = _rec([{"metric": "roi_pct", "cited_value": 999.0, "statement": "Huge ROI."}])


def _run(graph, state, thread_id):
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(state, config), config


def test_supported_claims_reach_human_review_and_approval_completes(stub_llm, stub_rag):
    stub = stub_llm(GOOD)
    graph = build_graph()
    result, config = _run(graph, WHITEFIELD, "t-good")

    payload = result["__interrupt__"][0].value
    assert payload["guardrail_result"]["status"] == "human_review_required"
    assert payload["unverified_claims"] == []

    final = graph.invoke(Command(resume={"approved": True, "feedback": ""}), config)
    assert final["final_report"]["status"] == "approved"
    assert final["final_report"]["unverified_claims"] == []
    assert len(stub.calls) == 1


def test_unsupported_claims_retry_twice_then_human_review_with_unverified(stub_llm, stub_rag):
    stub = stub_llm(BAD)
    graph = build_graph()
    result, config = _run(graph, WHITEFIELD, "t-bad")

    assert len(stub.calls) == 3  # first attempt + 2 re-analyses
    payload = result["__interrupt__"][0].value
    assert payload["unverified_claims"][0]["metric"] == "roi_pct"

    final = graph.invoke(Command(resume={"approved": True, "feedback": ""}), config)
    assert final["final_report"]["status"] == "approved"
    assert final["final_report"]["unverified_claims"][0]["cited_value"] == 999.0


def test_reanalysis_that_fixes_claims_clears_them(stub_llm, stub_rag):
    stub = stub_llm(BAD, GOOD)
    result, _ = _run(build_graph(), WHITEFIELD, "t-fix")
    assert len(stub.calls) == 2
    assert result["__interrupt__"][0].value["unverified_claims"] == []


def test_rejection_reruns_recommendation_with_feedback(stub_llm, stub_rag):
    stub = stub_llm(GOOD)
    graph = build_graph()
    _, config = _run(graph, WHITEFIELD, "t-reject")

    again = graph.invoke(Command(resume={"approved": False, "feedback": "consider flood risk"}), config)
    assert "__interrupt__" in again
    assert "consider flood risk" in stub.calls[-1][1][1]

    final = graph.invoke(Command(resume={"approved": True, "feedback": ""}), config)
    assert final["final_report"]["status"] == "approved"


def test_invalid_address_retries_then_refuses_without_llm(stub_rag):
    # The autouse fixture makes any real LLM call raise, so this also proves
    # the recommendation agent is skipped when there is no property data.
    result, _ = _run(build_graph(), {**WHITEFIELD, "property_address": "Nowhere Town, Atlantis"}, "t-bad-addr")
    assert result["data_retry_count"] == 2
    assert result["final_report"]["status"] == "refused"
    assert "__interrupt__" not in result


def test_api_analyze_approve_and_reject(stub_llm, stub_rag, monkeypatch, tmp_path):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import app as app_module

    monkeypatch.setattr(app_module, "REPORTS_DIR", tmp_path)
    stub_llm(GOOD)
    client = TestClient(app_module.app)

    pending = client.post("/analyze", json={"address": WHITEFIELD["property_address"], "budget": 9_500_000}).json()
    assert pending["approval_required"] is True
    assert pending["unverified_claims"] == []
    thread_id = pending["thread_id"]

    rejected = client.post("/reject", json={"thread_id": thread_id, "feedback": "more detail"}).json()
    assert rejected["approval_required"] is True

    approved = client.post("/approve", json={"thread_id": thread_id}).json()
    assert approved["final_report"]["status"] == "approved"
    assert approved["final_report"]["recommendation"]["supporting_evidence"][0]["metric"] == "risk_score"
    assert "report_paths" in approved, approved.get("report_error")


def test_api_rejects_invalid_loan_inputs():
    from fastapi.testclient import TestClient

    import app as app_module

    client = TestClient(app_module.app)
    response = client.post("/analyze", json={"address": "Whitefield, Bangalore", "budget": 9_500_000, "ltv": 95})
    assert response.status_code == 422
