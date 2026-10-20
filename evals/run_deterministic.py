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

from scenarios import CASH_FLOW_SAFETY_NET, DETERMINISTIC_SCENARIOS, check_rules  # noqa: E402


def _blocked_llm(*_args, **_kwargs):
    raise RuntimeError("The deterministic eval suite must not call the LLM.")


def run_scenario(graph, scenario) -> dict:
    config = {"configurable": {"thread_id": f"det-eval-{scenario.name}"}}
    interrupt_before = None if scenario.run_to_end else ["recommendation_agent"]
    return graph.invoke(scenario.input, config, interrupt_before=interrupt_before)


def run_safety_net_check() -> dict:
    state = PropertyState(
        property_address="synthetic",
        budget=10_000_000,
        investment_strategy="rental",
        investment_metrics={
            "negative_cash_flow": True,
            "cash_flow_severity": "significantly_negative",
            "strong_appreciation_evidence": False,
            "levered_cash_flow_negative": True,
        },
    )
    forced_buy = RecommendationOutput(decision="BUY", justification="Forced BUY.", confidence_score=0.9)
    return {"recommendation": rec_module._enforce_cashflow_safety_net(forced_buy, state).model_dump()}


def run_all() -> list[tuple[str, list[str]]]:
    """Return [(scenario_name, failures)] for every deterministic check."""
    rec_module.get_llm = _blocked_llm
    graph = build_graph()
    outcomes = [(s.name, check_rules(s.rules, run_scenario(graph, s))) for s in DETERMINISTIC_SCENARIOS]
    outcomes.append(("cash_flow_safety_net", check_rules([CASH_FLOW_SAFETY_NET], run_safety_net_check())))
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
