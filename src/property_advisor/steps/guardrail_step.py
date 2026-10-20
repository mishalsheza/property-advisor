"""Step 6: Guardrail.

Deterministic step (no LLM): validates the Recommendation Agent's output
before it can reach a human reviewer. Runs the rule checks (missing data,
risk score, negative operating cash flow, large shortfall after EMI,
confidence threshold; the conflicting-evidence check is currently disabled —
see CONFLICT_CHECK_ENABLED) and a claim check that compares every cited
evidence value against the value the deterministic steps computed, plus
directional wording in the justification and evidence statements
(see text_claims.py).

Routing outcomes (see graph.py):
- "request_reanalysis": loop back to the Recommendation Agent (capped by
  MAX_REANALYSIS_RETRIES) — used only for fixable issues (unsupported claims).
- "refuse": the recommendation is fundamentally unusable (no property data,
  or no decision/justification); end the graph without human approval.
- "human_review_required": forward to Human Approval. `reasons` lists every
  concern a human reviewer should weigh, even if it's empty (human approval
  is still mandatory with no flagged concerns). Claims still unsupported once
  re-analysis retries run out are forwarded as `unverified_claims`.
"""

from __future__ import annotations

from typing import Any

from langsmith import traceable

from property_advisor.config import (
    GUARDRAIL_CONFIDENCE_THRESHOLD,
    LEVERED_SHORTFALL_PCT_OF_EMI,
    MAX_REANALYSIS_RETRIES,
    RISK_HUMAN_REVIEW_THRESHOLD,
)
from property_advisor.logging_utils import logger, timed_node
from property_advisor.schemas import EVIDENCE_METRIC_FIELDS, RAG_SOURCE_METRIC
from property_advisor.state import PropertyState
from property_advisor.steps.text_claims import check_text_claims

# Conflicting-evidence check: DISABLED.
# It matched a hard-coded pair of AI-written Hinjewadi analyst notes that
# intentionally contradicted each other. Those notes moved to
# data/rag_corpus_legacy/ when the corpus was rebuilt from official documents,
# so the pair can never be retrieved and the check would silently always pass.
# It stays off (with a logged warning) until it is redesigned for the real
# corpus, e.g. by comparing claims across retrieved chunks.
CONFLICT_CHECK_ENABLED = False
CONFLICT_PAIRS = [
    ("hinjewadi_bullish_analyst_note.txt", "hinjewadi_bearish_analyst_note.txt"),
]

# A cited number is supported if it is within 2% of the computed value or
# within 0.5 absolute (whichever is looser) — enough for the model rounding
# 28.74 to 28.7 or 3.15 to 3.2, not enough for a different figure.
CLAIM_REL_TOLERANCE = 0.02
CLAIM_ABS_TOLERANCE = 0.5


@traceable(name="guardrail_detect_conflicting_evidence", run_type="tool")
def _detect_conflicting_evidence(rag_context: list[dict]) -> list[str]:
    if not CONFLICT_CHECK_ENABLED:
        logger.warning("guardrail: conflicting-evidence check is disabled (pending redesign for the new corpus)")
        return []
    sources = {r["source"] for r in rag_context}
    conflicts = []
    for a, b in CONFLICT_PAIRS:
        if a in sources and b in sources:
            conflicts.append(f"{a} vs {b}")
    return conflicts


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("%", "").replace("INR", "").replace("₹", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _value_matches(cited: Any, actual: Any) -> bool:
    if actual is None:
        # e.g. break_even_years is None when cash flow never breaks even
        return isinstance(cited, str) and cited.strip().lower() in ("none", "null", "never", "n/a")
    if isinstance(actual, str):
        return isinstance(cited, str) and cited.strip().lower() == actual.strip().lower()
    cited_num, actual_num = _to_number(cited), _to_number(actual)
    if cited_num is None or actual_num is None:
        return False
    tolerance = max(CLAIM_ABS_TOLERANCE, CLAIM_REL_TOLERANCE * abs(actual_num))
    return abs(cited_num - actual_num) <= tolerance


@traceable(name="guardrail_check_claims", run_type="tool")
def check_claims(state: PropertyState) -> list[dict[str, Any]]:
    """Return one entry per evidence item whose cited value isn't backed by
    the computed state: {metric, cited_value, computed_value, statement, reason}."""
    rag_sources = {r["source"] for r in state.rag_context}
    unsupported = []
    for item in state.recommendation.get("supporting_evidence", []):
        metric = item.get("metric", "")
        cited = item.get("cited_value")
        computed: Any = None
        if metric == RAG_SOURCE_METRIC:
            ok = cited in rag_sources
            reason = None if ok else "not a retrieved RAG source"
        elif metric in EVIDENCE_METRIC_FIELDS:
            field, key = EVIDENCE_METRIC_FIELDS[metric]
            container = getattr(state, field)
            if key not in container:
                ok, reason = False, f"no computed value for {metric}"
            else:
                computed = container[key]
                ok = _value_matches(cited, computed)
                reason = None if ok else f"cited {cited!r} but computed {computed!r}"
        else:
            ok, reason = False, f"unknown metric {metric!r}"
        if not ok:
            unsupported.append(
                {
                    "metric": metric,
                    "cited_value": cited,
                    "computed_value": computed,
                    "statement": item.get("statement", ""),
                    "reason": reason,
                }
            )
        # directional wording in the statement itself ("yield below the local average")
        unsupported += check_text_claims(item.get("statement", ""), state)
    unsupported += check_text_claims(state.recommendation.get("justification", ""), state)
    return unsupported


@timed_node("guardrail_step")
def guardrail_step(state: PropertyState) -> dict:
    reasons: list[str] = []

    missing_property_data = not state.property_data
    missing_market_data = not state.market_data
    if missing_property_data:
        reasons.append("Property data is missing for this address (data retries exhausted).")
    if missing_market_data:
        reasons.append("Market trend data is missing for this locality (data-quality risk).")

    risk_score = state.risk_assessment.get("risk_score", 0)
    high_risk = risk_score > RISK_HUMAN_REVIEW_THRESHOLD
    if high_risk:
        reasons.append(f"Risk score {risk_score} exceeds the human-review threshold of {RISK_HUMAN_REVIEW_THRESHOLD}.")

    metrics = state.investment_metrics
    negative_cash_flow = bool(metrics.get("negative_cash_flow"))
    if negative_cash_flow:
        reasons.append(
            f"Negative operating cash flow before the loan (INR {metrics.get('operating_cash_flow_inr')} per year)."
        )

    shortfall_pct = float(metrics.get("shortfall_pct_of_emi") or 0)
    levered_shortfall = bool(metrics.get("levered_cash_flow_negative")) and shortfall_pct > LEVERED_SHORTFALL_PCT_OF_EMI
    if levered_shortfall:
        reasons.append(
            f"Cash flow after EMI is negative (INR {metrics.get('cash_flow_after_emi_inr'):,.0f} per year; "
            f"monthly shortfall INR {metrics.get('monthly_shortfall_after_emi_inr'):,.0f} = {shortfall_pct:g}% of the EMI, "
            f"above the {LEVERED_SHORTFALL_PCT_OF_EMI:g}% limit): confidence capped, BUY needs strong appreciation evidence."
        )

    confidence = state.recommendation.get("confidence_score", 0.0)
    confidence_below_threshold = confidence < GUARDRAIL_CONFIDENCE_THRESHOLD
    if confidence_below_threshold:
        reasons.append(f"Recommendation confidence {confidence:.2f} is below threshold {GUARDRAIL_CONFIDENCE_THRESHOLD}.")

    conflicts = _detect_conflicting_evidence(state.rag_context)
    conflicting_evidence = bool(conflicts)
    if conflicting_evidence:
        reasons.append(f"Conflicting evidence detected in retrieved context: {', '.join(conflicts)}.")

    unsupported_claims = check_claims(state)
    has_unsupported_claims = bool(unsupported_claims)
    if has_unsupported_claims:
        reasons.append(
            "Unsupported claims found: "
            + "; ".join(f"{c['metric']}: {c['reason']}" for c in unsupported_claims)
        )

    decision_present = bool(state.recommendation.get("decision"))
    is_refusable = (
        missing_property_data or not decision_present or not state.recommendation.get("justification")
    )

    if is_refusable:
        status = "refuse"
    elif has_unsupported_claims and state.reanalysis_retry_count < MAX_REANALYSIS_RETRIES:
        # Only re-run the Recommendation Agent for fixable issues (claims it
        # can correct by re-prompting). Risk/cash-flow/confidence concerns
        # are facts about the deal, not reasoning errors — re-analysis won't
        # change them, so those go straight to a human reviewer instead.
        status = "request_reanalysis"
    else:
        status = "human_review_required"

    requires_human_review = (
        state.requires_human_review
        or high_risk
        or negative_cash_flow
        or levered_shortfall
        or confidence_below_threshold
        or missing_market_data
        or conflicting_evidence
        or has_unsupported_claims
    )

    guardrail_result = {
        "status": status,
        "reasons": reasons,
        "missing_property_data": missing_property_data,
        "missing_market_data": missing_market_data,
        "high_risk": high_risk,
        "negative_cash_flow": negative_cash_flow,
        "levered_shortfall": levered_shortfall,
        "confidence_below_threshold": confidence_below_threshold,
        "conflicting_evidence": conflicting_evidence,
        "conflict_check": "enabled" if CONFLICT_CHECK_ENABLED else "disabled",
        "conflicts": conflicts,
        "has_unsupported_claims": has_unsupported_claims,
        "unsupported_claims": unsupported_claims,
    }

    update = {
        "guardrail_result": guardrail_result,
        "requires_human_review": requires_human_review,
        # Claims that survived every re-analysis attempt go to the reviewer
        # (and the report) as unverified rather than blocking the run.
        "unverified_claims": unsupported_claims if status == "human_review_required" else [],
    }
    if status == "request_reanalysis":
        update["reanalysis_retry_count"] = state.reanalysis_retry_count + 1

    return update
