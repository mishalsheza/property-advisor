"""Runs the deterministic eval suite: no GROQ_API_KEY required.

Each scenario runs the real graph but stops before the Recommendation Agent
(or, for scenarios with run_to_end=True, runs to completion because the agent
skips its LLM call). The LLM is blocked outright so this can never touch the
network for generation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from property_advisor.agents import recommendation_agent as rec_module  # noqa: E402
from property_advisor.graph import build_graph  # noqa: E402
from property_advisor.schemas import RecommendationOutput  # noqa: E402
from property_advisor.state import PropertyState  # noqa: E402
from property_advisor.steps.guardrail_step import guardrail_step  # noqa: E402
from property_advisor.steps.market_step import market_lookup_step  # noqa: E402
from property_advisor.tools.financial_calculator import compute_investment_metrics  # noqa: E402
from property_advisor.tools.property_data_tool import _PROPERTIES as PROPERTIES  # noqa: E402
from property_advisor.tools.risk_data_tool import compute_risk_score, get_risk_data  # noqa: E402

from scenarios import DETERMINISTIC_SCENARIOS, SAFETY_NET_CASES, check_rules  # noqa: E402


def _blocked_llm(*_args, **_kwargs):
    raise RuntimeError("The deterministic eval suite must not call the LLM.")


def run_scenario(graph, scenario) -> dict:
    config = {"configurable": {"thread_id": f"det-eval-{scenario.name}"}}
    interrupt_before = None if scenario.run_to_end else ["recommendation_agent"]
    return graph.invoke(scenario.input, config, interrupt_before=interrupt_before)


def _state_for(slug: str, metric_overrides: dict) -> PropertyState:
    """State as the deterministic steps would compute it for a mock property."""
    property_data = {**PROPERTIES[slug], "locality_slug": slug}
    # the real market step, so HPI appreciation (or the labelled fallback) applies
    market_data = market_lookup_step(
        PropertyState(property_address=slug, budget=property_data["price_inr"], property_data=property_data)
    )["market_data"]
    raw_risk = get_risk_data(slug)
    risk = {**compute_risk_score(raw_risk), "raw_indicators": raw_risk}
    metrics = compute_investment_metrics(property_data, market_data, property_data["price_inr"], 5)
    return PropertyState(
        property_address=f"{property_data['locality']}, {property_data['city']}",
        budget=property_data["price_inr"],
        property_data=property_data,
        market_data=market_data,
        investment_metrics={**metrics, **metric_overrides},
        risk_assessment=risk,
    )


def run_safety_net_case(case) -> dict:
    state = _state_for(case.slug, case.metric_overrides)
    forced = RecommendationOutput(**case.forced)
    recommendation = rec_module._enforce_cashflow_safety_net(forced, state).model_dump()
    guardrail = guardrail_step(state.model_copy(update={"recommendation": recommendation}))
    return {"recommendation": recommendation, "guardrail_result": guardrail["guardrail_result"]}


def run_all() -> list[tuple[str, list[str]]]:
    """Return [(scenario_name, failures)] for every deterministic check."""
    rec_module.get_llm = _blocked_llm
    graph = build_graph()
    outcomes = [(s.name, check_rules(s.rules, run_scenario(graph, s))) for s in DETERMINISTIC_SCENARIOS]
    outcomes += [(c.name, check_rules(c.rules, run_safety_net_case(c))) for c in SAFETY_NET_CASES]
    return outcomes


def main() -> None:
    outcomes = run_all()
    for name, failures in outcomes:
        print(f"{'PASS' if not failures else 'FAIL'}  {name}")
        for f in failures:
            print(f"      - {f}")
    failed = sum(1 for _, f in outcomes if f)
    print(f"\n{len(outcomes) - failed} passed, {failed} failed out of {len(outcomes)} deterministic checks")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
