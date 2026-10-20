"""Structured-output schema for the Recommendation Agent, plus the fixed set of
metric names its evidence may cite.

Field descriptions explicitly ask for brevity — these are JSON outputs, not
prose, and every word here is an output token the model will spend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Metric names the Recommendation Agent may cite, mapped to the PropertyState
# field (and key) holding the computed value. The guardrail compares each cited
# value against this; any metric not listed here counts as unsupported.
EVIDENCE_METRIC_FIELDS: dict[str, tuple[str, str]] = {
    "roi_pct": ("investment_metrics", "roi_pct"),
    "rental_yield_pct": ("investment_metrics", "rental_yield_pct"),
    "cap_rate_pct": ("investment_metrics", "cap_rate_pct"),
    "annual_cash_flow_inr": ("investment_metrics", "annual_cash_flow_inr"),
    "unlevered_annual_cash_flow_inr": ("investment_metrics", "unlevered_annual_cash_flow_inr"),
    "break_even_years": ("investment_metrics", "break_even_years"),
    "cash_flow_severity": ("investment_metrics", "cash_flow_severity"),
    "risk_score": ("risk_assessment", "risk_score"),
    "appreciation_rate_5yr_pct": ("market_data", "appreciation_rate_5yr_pct"),
    "price_inr": ("property_data", "price_inr"),
}
# Special metric: cited_value must be the filename of a retrieved RAG chunk.
RAG_SOURCE_METRIC = "rag_source"
EVIDENCE_METRICS = (*EVIDENCE_METRIC_FIELDS, RAG_SOURCE_METRIC)


class EvidenceItem(BaseModel):
    metric: str = Field(description=f"One of: {', '.join(EVIDENCE_METRICS)}.")
    cited_value: float | str = Field(
        description="The value exactly as given in the input data (number, string, or RAG filename)."
    )
    statement: str = Field(description="One short clause using this value.")


class RecommendationOutput(BaseModel):
    decision: Literal["BUY", "HOLD", "AVOID"]
    justification: str = Field(description="Max 2 short sentences. No filler.")
    supporting_evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Up to 3 items citing values from the input data.",
    )
    confidence_score: float = Field(ge=0.0, le=1.0)
