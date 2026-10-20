"""Recommendation Agent (the only LLM agent in the graph).

The one place in the graph where an LLM (Groq) exercises judgment: weighing
deterministic investment metrics, risk assessment, and RAG-retrieved
evidence into a BUY/HOLD/AVOID call with justification, supporting evidence,
and a confidence score. The prompt explicitly grounds the model in the
already-computed numbers so it cannot invent its own financial figures.

Cash-flow safety net: negative cash flow must never be silently waved
through into a BUY. Operating losses (rental strategy) and large shortfalls
after EMI (any strategy) force a downgrade unless appreciation evidence is
strong, the latter also caps confidence and always adds a warning. The prompt tells
the model the rules, and a deterministic post-processing step enforces them
regardless of what the model actually outputs — financial decision rules are
not left to LLM discretion alone, consistent with this project's preference
for deterministic guardrails over agent autonomy.

Token budget: this call is intentionally terse on both sides. The prompt
sends only the fields the model needs to decide (not full nested
property/market dicts), and the schema asks for short JSON, not prose — see
config.get_llm's max_tokens/temperature defaults and schemas.py.
"""

from __future__ import annotations

import json

from property_advisor.config import (
    LEVERED_SHORTFALL_CONFIDENCE_CAP,
    LEVERED_SHORTFALL_PCT_OF_EMI,
    get_llm,
)
from property_advisor.logging_utils import timed_node
from property_advisor.schemas import EVIDENCE_METRICS, RecommendationOutput
from property_advisor.state import PropertyState

# The older ambiguous cash-flow names are still accepted by the guardrail but
# not offered to the model.
PROMPT_EVIDENCE_METRICS = [
    m for m in EVIDENCE_METRICS if m not in ("annual_cash_flow_inr", "unlevered_annual_cash_flow_inr")
]

SYSTEM_PROMPT = """Indian real-estate Recommendation Agent. Output BUY, HOLD, or AVOID.

Decide from the WHOLE picture, never a single metric. Use ONLY the numbers \
given below; never invent figures. Weigh together:
- Total return: roi_pct is the TOTAL ROI over roi_horizon_years (appreciation \
plus cash flow after EMI, divided by price) and the market appreciation rate.
- Income: rental_yield_pct; operating_cash_flow_inr (rent minus expenses, BEFORE \
the loan; cash_flow_severity describes this figure); cash_flow_after_emi_inr \
(what the buyer actually nets AFTER paying the EMI).
- Risk: risk_score (0-100, higher = worse), the per-factor indicators, and \
data_quality_confidence.
- RAG evidence: let supporting or contradicting context move the call.

Wording rules (checked automatically; violations are rejected):
- Never say "positive cash flow" or "negative cash flow" without saying which: \
"operating cash flow (before loan)" or "cash flow after EMI". If \
cash_flow_after_emi_inr < 0, do not describe the property as cash-flow positive.
- Describe risk and yield only in ways the numbers support (e.g. "low risk" only \
for a low risk_score).
- Do not compare to benchmarks that are not in the data. The only benchmark \
given is the market's rental_yield_avg_pct; never mention local/city averages \
for ROI, price or anything else.

Guidance (lean, not rigid thresholds):
- Strong total return + solid yield + acceptable risk -> lean BUY.
- Mixed or borderline signals -> HOLD.
- Reserve AVOID for genuinely poor deals: negative/very weak roi_pct, very low \
yield, or high risk -- NOT merely because a leveraged buyer sees negative \
monthly cash flow.

Financing caveat: cash_flow_after_emi_inr < 0 means the EMI (at the Loan \
terms given below) exceeds net rent and the buyer must fund the shortfall. \
This is common for Indian rentals (appreciation, not monthly cash flow, drives \
most returns): mention it -- it does NOT by itself justify AVOID. When \
shortfall_pct_of_emi > """ + f"{LEVERED_SHORTFALL_PCT_OF_EMI:g}" + """, BUY additionally \
requires strong_appreciation_evidence=true and confidence is capped at \
""" + f"{LEVERED_SHORTFALL_CONFIDENCE_CAP:g}" + """.

Operating cash-flow rule (mandatory): cash_flow_severity="significantly_negative" \
(the asset loses money even before financing) -> decision must be HOLD or AVOID \
UNLESS strong_appreciation_evidence=true.

Evidence: up to 3 supporting_evidence items, each {metric, cited_value, statement}. \
metric must be one of: """ + ", ".join(PROMPT_EVIDENCE_METRICS) + """. cited_value must be \
copied exactly from the Metrics/Risk/Market/Property data below (for rag_source: \
the bracketed RAG filename). Every cited value is checked against the computed \
data; anything else is rejected.

Be concise. Max 2 sentences in justification."""


# Structured evidence items need more room than the global default cap, and on
# reasoning models (e.g. openai/gpt-oss-120b) hidden reasoning tokens count
# against this limit too — 500 truncated the JSON mid-string.
RECOMMENDATION_MAX_TOKENS = 2000


def _format_rag_context(rag_context: list[dict], limit: int = 3, snippet_len: int = 220) -> str:
    if not rag_context:
        return "none"
    lines = []
    for r in rag_context[:limit]:
        lines.append(f"[{r['source']}] {r['text'][:snippet_len]}")
    return "\n".join(lines)


def _compact_metrics(metrics: dict) -> dict:
    keys = (
        "roi_pct",
        "rental_yield_pct",
        "cap_rate_pct",
        "operating_cash_flow_inr",
        "cash_flow_severity",
        "cash_flow_after_emi_inr",
        "shortfall_pct_of_emi",
        "strong_appreciation_evidence",
        "break_even_years",
        "data_quality_confidence",
    )
    compact = {k: metrics[k] for k in keys if k in metrics}
    if "horizon_years" in metrics:
        compact["roi_horizon_years"] = metrics["horizon_years"]
    if "loan_assumptions" in metrics:
        compact["monthly_emi_inr"] = metrics["loan_assumptions"].get("monthly_emi_inr")
    return compact


def _compact_risk(risk: dict) -> dict:
    keys = ("risk_score", "data_quality_confidence")
    compact = {k: risk[k] for k in keys if k in risk}
    if risk.get("raw_indicators"):
        compact["indicators"] = risk["raw_indicators"]
    return compact


def cash_flow_warning(state: PropertyState) -> str:
    """The mandatory after-EMI cash-flow warning (also used by the guardrail)."""
    m = state.investment_metrics
    return (
        f"[Warning: cash flow after EMI is negative: INR {m.get('cash_flow_after_emi_inr'):,.0f} per year "
        f"(monthly shortfall INR {m.get('monthly_shortfall_after_emi_inr'):,.0f}, "
        f"{m.get('shortfall_pct_of_emi'):g}% of the EMI at {state.loan_to_value_pct:g}% LTV). "
        f"Operating cash flow before the loan is INR {m.get('operating_cash_flow_inr'):,.0f} per year. "
        f"The buyer must fund the shortfall from other income.]"
    )


def _enforce_cashflow_safety_net(result: RecommendationOutput, state: PropertyState) -> RecommendationOutput:
    """Deterministic safety net: the LLM is instructed to follow the
    cash-flow tradeoff rules above, but financial decision rules are not
    left to LLM discretion alone — this guarantees the rules hold even if
    the model doesn't comply.
    """
    metrics = state.investment_metrics
    if not metrics:
        return result

    # significantly_negative describes OPERATING (unlevered) economics: an
    # asset that loses money before any financing is a genuine red flag. The
    # shortfall after EMI is a separate financing caveat, handled by the
    # leverage rule below.
    significantly_negative = metrics.get("cash_flow_severity") == "significantly_negative"
    strong_appreciation = bool(metrics.get("strong_appreciation_evidence"))
    levered_negative = bool(metrics.get("levered_cash_flow_negative"))
    shortfall_pct = float(metrics.get("shortfall_pct_of_emi") or 0)
    heavy_shortfall = levered_negative and shortfall_pct > LEVERED_SHORTFALL_PCT_OF_EMI

    decision = result.decision
    confidence = result.confidence_score
    justification = result.justification

    if state.investment_strategy == "rental" and significantly_negative and not strong_appreciation and decision == "BUY":
        # Only override when the property loses money on an OPERATING basis and
        # appreciation isn't strong enough to compensate — not for ordinary
        # leveraged-cash-flow negativity, which is normal for Indian rentals.
        decision = "HOLD"
        confidence = round(min(confidence, 0.55), 2)
        justification = (
            f"{justification} [Guardrail override: the Recommendation Agent's original BUY call "
            f"was downgraded to HOLD because the property's operating (pre-financing) cash flow is "
            f"significantly negative and strong_appreciation_evidence was not met.]"
        )

    if heavy_shortfall:
        # Leverage rule: a large monthly shortfall after EMI caps confidence,
        # always carries a warning, and BUY must rest on strong appreciation.
        if decision == "BUY" and not strong_appreciation:
            decision = "HOLD"
            justification = (
                f"{justification} [Guardrail override: BUY was downgraded to HOLD because the "
                f"monthly shortfall after EMI is {shortfall_pct:g}% of the EMI and "
                f"strong_appreciation_evidence was not met.]"
            )
        confidence = round(min(confidence, LEVERED_SHORTFALL_CONFIDENCE_CAP), 2)

    if levered_negative:
        # Mandatory, regardless of how the model worded its justification (the
        # old version skipped this whenever the text merely said "cash flow").
        justification = f"{justification} {cash_flow_warning(state)}"

    return RecommendationOutput(
        decision=decision,
        justification=justification,
        supporting_evidence=result.supporting_evidence,
        confidence_score=max(0.0, min(1.0, confidence)),
    )


@timed_node("recommendation_agent")
def recommendation_agent(state: PropertyState) -> dict:
    if not state.property_data:
        # Nothing to judge (address not found after data retries): skip the
        # LLM call; the guardrail refuses an empty recommendation.
        return {"recommendation": {}}

    llm = get_llm(max_tokens=RECOMMENDATION_MAX_TOKENS)
    structured_llm = llm.with_structured_output(RecommendationOutput)

    feedback_note = ""
    if state.human_decision.get("approved") is False:
        feedback_note = f"\nRejected by reviewer. Feedback: {state.human_decision.get('feedback', '')}"

    reanalysis_note = ""
    if state.reanalysis_retry_count > 0:
        reasons = state.guardrail_result.get("reasons", [])
        reanalysis_note = f"\nRe-analysis #{state.reanalysis_retry_count}. Guardrail reasons: {json.dumps(reasons)}"

    user_prompt = f"""Address: {state.property_address}
Budget: INR {state.budget} | Horizon: {state.investment_horizon_years}yr | Strategy: {state.investment_strategy}
Loan: {state.loan_to_value_pct:g}% LTV, {state.interest_rate_pct:g}% interest, {state.loan_tenure_years}yr tenure

Property: {json.dumps({k: state.property_data.get(k) for k in ("city", "locality", "property_type", "price_inr", "area_sqft") if k in state.property_data})}
Market: {json.dumps(state.market_data) if state.market_data else "none"}
Metrics: {json.dumps(_compact_metrics(state.investment_metrics))}
Risk: {json.dumps(_compact_risk(state.risk_assessment))}
RAG:
{_format_rag_context(state.rag_context)}
{feedback_note}{reanalysis_note}
"""

    result: RecommendationOutput = structured_llm.invoke(
        [("system", SYSTEM_PROMPT), ("user", user_prompt)]
    )
    result = _enforce_cashflow_safety_net(result, state)

    return {"recommendation": result.model_dump()}
