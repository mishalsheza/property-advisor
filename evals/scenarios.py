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
CASH_FLOW_SAFETY_NET = Rule(
    "significantly negative operating cash flow -> forced BUY is downgraded (not BUY)",
    "A rental that loses money before financing, without strong appreciation evidence, "
    "must never be recommended as BUY regardless of what the LLM outputs.",
    lambda r: _decision(r) != "BUY",
)

DETERMINISTIC_SCENARIOS = [
    Scenario(
        "high_growth_corridor_metrics",
        WHITEFIELD,
        [
            Rule(
                "roi_pct > 15 and strong_appreciation_evidence",
                "Whitefield's mock appreciation rate is >= 8%/yr, which compounds to >15% "
                "over 5 years even after the levered cash-flow drag.",
                lambda r: r["investment_metrics"]["roi_pct"] > 15
                and r["investment_metrics"]["strong_appreciation_evidence"] is True,
            ),
            Rule(
                "risk_score < 75",
                "All Whitefield risk indicators are low/medium; no factor pushes it to review.",
                lambda r: _risk(r) < 75,
            ),
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
            )
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
