"""Evaluation scenarios as hand-checkable rules.

Every rule states what must hold and *why*, so a reviewer can verify the
expectation from the mock data and the rule text alone. Rules never pin an
exact LLM decision ("expect BUY"); they only forbid decisions the data rules
out.

Two suites:
- DETERMINISTIC_SCENARIOS: run the deterministic steps (and the guardrail /
  cash-flow safety net) only. No GROQ_API_KEY needed — see run_deterministic.py.
- LLM_SCENARIOS: full graph including the Recommendation Agent (Groq), human
  review auto-approved — see run_llm.py.

All addresses refer to the synthetic demo data in src/property_advisor/data/.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from property_advisor.config import MAX_DATA_RETRIES


@dataclass(frozen=True)
class Rule:
    description: str
    reason: str
    check: Callable[[dict], bool]


@dataclass(frozen=True)
class Scenario:
    name: str
    input: dict
    rules: list[Rule] = field(default_factory=list)
    # Deterministic suite only: run past the Recommendation Agent. Safe only
    # when the agent skips its LLM call (no property data).
    run_to_end: bool = False
    skip_reason: str | None = None


def check_rules(rules: list[Rule], result: dict) -> list[str]:
    """Return a failure message (with its reason) for every rule that doesn't hold."""
    failures = []
    for rule in rules:
        try:
            ok = rule.check(result)
        except (KeyError, TypeError) as exc:
            ok = False
            rule_error = f" (could not evaluate: {exc!r})"
        else:
            rule_error = ""
        if not ok:
            failures.append(f"{rule.description}{rule_error} — reason: {rule.reason}")
    return failures


def _decision(result: dict) -> str | None:
    return result.get("recommendation", {}).get("decision")


def _risk(result: dict) -> float:
    return result.get("risk_assessment", {}).get("risk_score", 0)


def _inp(address: str, budget: float, strategy: str = "rental") -> dict:
    return {
        "property_address": address,
        "budget": budget,
        "investment_horizon_years": 5,
        "investment_strategy": strategy,
    }


WHITEFIELD = _inp("Flat 4B, Whitefield, Bangalore, 560066", 9_500_000.0)
WORLI = _inp("Sea view flat, Worli, Mumbai", 45_000_000.0)
DADAR = _inp("Flat near Dadar station, Dadar, Mumbai", 18_000_000.0)
MUZAFFARPUR = _inp("Plot near Saraiyaganj, Muzaffarpur, Bihar", 3_500_000.0, "long_term_appreciation")
INVALID = _inp("Nowhere Town, Atlantis", 5_000_000.0)

HIGH_FLOOD_RISK = Rule(
    "risk_score >= 80 and human review required",
    "Dadar's mock risk data has flood_risk='high'; flood is the heaviest-weighted factor, "
    "so the score must clear the 75 human-review threshold (it computes to 80.0).",
    lambda r: _risk(r) >= 80 and r.get("requires_human_review") is True,
)

# No mock property has significantly negative *operating* cash flow, so this
# rule is checked by forcing a BUY through the cash-flow safety net on
# synthetic metrics (see run_deterministic.py) rather than via a scenario.
@dataclass(frozen=True)
class SafetyNetCase:
    """A fixed (forced) LLM output pushed through the deterministic safety net
    and guardrail for a real mock property — checks rules the LLM can't bypass."""

    name: str
    slug: str
    forced: dict
    rules: list[Rule]
    metric_overrides: dict = field(default_factory=dict)


def _confidence(result: dict) -> float:
    return result.get("recommendation", {}).get("confidence_score", 1.0)


def _has_warning(result: dict) -> bool:
    return "[Warning: cash flow after EMI is negative" in result.get("recommendation", {}).get("justification", "")


def _forced_buy(justification: str = "Strong appreciation supports a BUY.") -> dict:
    return {"decision": "BUY", "justification": justification, "confidence_score": 0.92, "supporting_evidence": []}


SAFETY_NET_CASES = [
    SafetyNetCase(
        "shortfall_warning_tier",
        "whitefield_bangalore",
        # the reported case: BUY at 92% claiming positive cash flow while cash flow after EMI is -5.06 lakh/yr
        _forced_buy("Positive cash flow and strong appreciation support a BUY."),
        [
            Rule(
                "warning added, decision and confidence untouched",
                "Whitefield's shortfall after EMI is 61.6% of the EMI: above the 25% warning level, below the "
                "70% cap level, so only the mandatory warning applies.",
                lambda r: _decision(r) == "BUY" and _confidence(r) == 0.92 and _has_warning(r),
            ),
            Rule(
                "'Positive cash flow' is an unsupported claim -> re-analysis",
                "Cash flow after EMI is negative, so an unqualified 'positive cash flow' contradicts the data.",
                lambda r: any(c["metric"] == "text:cash_flow_after_emi" for c in r["guardrail_result"]["unsupported_claims"])
                and r["guardrail_result"]["status"] == "request_reanalysis",
            ),
            Rule(
                "guardrail reports the shortfall (warning tier, not capped)",
                "The shortfall warning must reach the human reviewer, not only the justification.",
                lambda r: r["guardrail_result"]["levered_shortfall"] is True
                and r["guardrail_result"]["levered_shortfall_capped"] is False,
            ),
        ],
    ),
    SafetyNetCase(
        "shortfall_cap_tier_without_strong_appreciation",
        "worli_mumbai",
        _forced_buy(),
        [
            Rule(
                "forced BUY downgraded to HOLD, confidence <= 0.75, warning added",
                "Worli's shortfall after EMI is 86.5% of the EMI (> 70%) and strong_appreciation_evidence is "
                "false, so BUY is not justified.",
                lambda r: _decision(r) == "HOLD" and _confidence(r) <= 0.75 and _has_warning(r)
                and r["guardrail_result"]["levered_shortfall_capped"] is True,
            )
        ],
    ),
    SafetyNetCase(
        "shortfall_cap_tier_with_strong_appreciation",
        "worli_mumbai",
        _forced_buy(),
        [
            Rule(
                "BUY kept, confidence <= 0.75, warning added",
                "Above 70% BUY needs strong appreciation evidence; with it, BUY stands but confidence is "
                "capped. (Overridden metric: no mock property above 70% has strong appreciation evidence.)",
                lambda r: _decision(r) == "BUY" and _confidence(r) <= 0.75 and _has_warning(r),
            )
        ],
        metric_overrides={"strong_appreciation_evidence": True},
    ),
    SafetyNetCase(
        "operating_loss_forced_buy",
        "worli_mumbai",
        _forced_buy(),
        [
            Rule(
                "significantly negative operating cash flow -> forced BUY is downgraded (not BUY)",
                "A rental that loses money before financing, without strong appreciation evidence, must never "
                "be BUY. (Overridden metric: the calculator's fixed 25% expense ratio can't produce an "
                "operating loss on real mock data.)",
                lambda r: _decision(r) != "BUY",
            )
        ],
        metric_overrides={"cash_flow_severity": "significantly_negative", "negative_cash_flow": True},
    ),
]

DETERMINISTIC_SCENARIOS = [
    Scenario(
        "high_growth_corridor_metrics",
        WHITEFIELD,
        [
            Rule(
                "appreciation from RBI HPI Bangalore (7.52%/yr), provisional, confidence 0.85",
                "Bangalore HPI went 102.24 -> 127.08 from Q1 2023-24 to Q1 2026-27 (provisional): "
                "(127.08/102.24)^(1/3) - 1 = 7.52%/yr. City-level data caps confidence at 0.85.",
                lambda r: r["market_data"]["appreciation_source"] == "rbi_hpi"
                and r["market_data"]["hpi_city"] == "Bangalore"
                and abs(r["market_data"]["appreciation_rate_5yr_pct"] - 7.52) < 0.01
                and r["market_data"]["hpi_provisional"] is True
                and r["investment_metrics"]["data_quality_confidence"] == 0.85,
            ),
            Rule(
                "roi_pct > 15, roe_pct > 0, but no strong appreciation evidence",
                "7.52%/yr still compounds to 17.1% on price over 5 years, but it is below the 8%/yr "
                "needed for strong_appreciation_evidence.",
                lambda r: r["investment_metrics"]["roi_pct"] > 15
                and r["investment_metrics"]["roe_pct"] > 0
                and r["investment_metrics"]["strong_appreciation_evidence"] is False,
            ),
            Rule(
                "risk_score < 75",
                "All Whitefield risk indicators are low/medium; no factor pushes it to review.",
                lambda r: _risk(r) < 75,
            ),
        ],
    ),
    Scenario(
        "no_hpi_series_uses_labelled_mock_fallback",
        _inp("Cyber City, Gurgaon", 12_000_000.0),
        [
            Rule(
                "appreciation_source says mock fallback; mock rate kept; confidence not capped",
                "RBI publishes no HPI series for Gurgaon, so the synthetic mock rate (7.4%) is used and "
                "must be labelled as such.",
                lambda r: r["market_data"]["appreciation_source"].startswith("mock (fallback")
                and r["market_data"]["appreciation_rate_5yr_pct"] == 7.4
                and "hpi_city" not in r["market_data"],
            )
        ],
    ),
    Scenario(
        "negative_total_return",
        WORLI,
        [
            Rule(
                "roi_pct < 0",
                "Worli's price is very high relative to rent and appreciation, so 5-year "
                "appreciation does not cover the levered cash-flow shortfall.",
                lambda r: r["investment_metrics"]["roi_pct"] < 0,
            )
        ],
    ),
    Scenario("high_flood_risk", DADAR, [HIGH_FLOOD_RISK]),
    Scenario(
        "missing_market_data_retry",
        MUZAFFARPUR,
        [
            Rule(
                f"data_retry_count == {MAX_DATA_RETRIES} and market_data empty",
                "Muzaffarpur has property data but no market-trend entry, so the retry gate "
                "must exhaust its retries before continuing.",
                lambda r: r.get("data_retry_count") == MAX_DATA_RETRIES and not r.get("market_data"),
            )
        ],
    ),
    Scenario(
        "invalid_address_refused",
        INVALID,
        [
            Rule(
                "final_report.status == 'refused'",
                "No property matches the address, so there is nothing to judge; the guardrail "
                "must refuse rather than send an empty recommendation to a reviewer.",
                lambda r: r.get("final_report", {}).get("status") == "refused",
            )
        ],
        run_to_end=True,
    ),
]

LLM_SCENARIOS = [
    Scenario(
        "high_growth_not_avoid",
        WHITEFIELD,
        [
            Rule(
                "decision != 'AVOID'",
                "ROI > 15%, strong appreciation evidence and low risk: the prompt reserves AVOID "
                "for poor deals, so AVOID here would contradict the data.",
                lambda r: _decision(r) in ("BUY", "HOLD"),
            ),
            Rule(
                "after-EMI warning present",
                "Cash flow after EMI is -5.06 lakh/yr (61.6% of the EMI, above the 25% warning level): "
                "the warning is mandatory whatever the model says.",
                lambda r: _has_warning(r),
            ),
        ],
    ),
    Scenario(
        "negative_return_not_buy",
        WORLI,
        [
            Rule(
                "decision != 'BUY'",
                "roi_pct is negative over the horizon; buying a property that loses money in "
                "total return is never supported by the data.",
                lambda r: _decision(r) in ("HOLD", "AVOID"),
            )
        ],
    ),
    Scenario(
        "high_flood_risk_not_buy",
        DADAR,
        [
            HIGH_FLOOD_RISK,
            Rule(
                "decision != 'BUY'",
                "High flood risk with only ~6% 5-year ROI and no strong appreciation evidence.",
                lambda r: _decision(r) in ("HOLD", "AVOID"),
            ),
        ],
    ),
    Scenario(
        "missing_market_data_flagged",
        MUZAFFARPUR,
        [
            Rule(
                "guardrail flags missing market data",
                "Without market data the metrics are low-confidence; the reviewer must be told.",
                lambda r: r.get("guardrail_result", {}).get("missing_market_data") is True,
            ),
            Rule(
                "decision != 'BUY'",
                "ROI is strongly negative (no rent/appreciation data), so BUY is unsupported.",
                lambda r: _decision(r) in ("HOLD", "AVOID"),
            ),
        ],
    ),
    Scenario(
        "conflicting_reports_guardrail",
        _inp("Hinjewadi Phase 2, Pune", 7_200_000.0),
        skip_reason=(
            "The conflicting-evidence check relied on two AI-written Hinjewadi analyst notes "
            "that were moved to rag_corpus_legacy/; the check is disabled until it is "
            "redesigned for the real corpus (5 of 6 guardrail rule checks are active)."
        ),
    ),
]
