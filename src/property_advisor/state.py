"""Shared LangGraph state schema for the Property Investment Advisor.

Every graph node (deterministic step or LLM agent) reads/writes only the fields relevant to its responsibility.
Routing/control fields are kept separate from the domain data fields so nodes never need to touch them directly.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from property_advisor.tools.financial_calculator import (
    DEFAULT_INTEREST_RATE_PCT,
    DEFAULT_LOAN_TENURE_YEARS,
    DEFAULT_LOAN_TO_VALUE_RATIO,
)


class PropertyState(BaseModel):
    # --- Inputs ---
    property_address: str
    budget: float  # INR
    investment_horizon_years: int = 5
    investment_strategy: Literal["rental", "flip", "long_term_appreciation"] = "rental"
    # Loan assumptions. RBI caps LTV at 90% for the smallest loans, so higher is rejected.
    loan_to_value_pct: float = Field(default=DEFAULT_LOAN_TO_VALUE_RATIO * 100, gt=0, le=90)
    interest_rate_pct: float = Field(default=DEFAULT_INTEREST_RATE_PCT, gt=0, le=25)
    loan_tenure_years: int = Field(default=DEFAULT_LOAN_TENURE_YEARS, ge=1, le=30)

    # --- Step / agent outputs ---
    property_data: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    rag_context: list[dict[str, Any]] = Field(default_factory=list)
    investment_metrics: dict[str, Any] = Field(default_factory=dict)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    guardrail_result: dict[str, Any] = Field(default_factory=dict)
    # Evidence claims still unsupported after the re-analysis retries ran out;
    # surfaced to the human reviewer and the final report.
    unverified_claims: list[dict[str, Any]] = Field(default_factory=list)

    # --- Human-in-the-loop ---
    requires_human_review: bool = False
    human_decision: dict[str, Any] = Field(default_factory=dict)
    final_report: dict[str, Any] = Field(default_factory=dict)

    # --- Routing / control ---
    data_retry_count: int = 0
    reanalysis_retry_count: int = 0
    workflow_status: str = "in_progress"
    errors: list[str] = Field(default_factory=list)
