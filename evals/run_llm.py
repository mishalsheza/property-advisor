"""Runs the LLM eval suite end-to-end through the LangGraph workflow
(auto-approving human review so it can run non-interactively).

Requires GROQ_API_KEY (the Recommendation Agent calls Groq). For checks that
need no key, use run_deterministic.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.types import Command  # noqa: E402

from property_advisor.config import GROQ_API_KEY  # noqa: E402
from property_advisor.graph import build_graph  # noqa: E402

from scenarios import LLM_SCENARIOS, check_rules  # noqa: E402


def run_scenario(graph, scenario) -> dict:
    config = {"configurable": {"thread_id": f"llm-eval-{scenario.name}"}}
    result = graph.invoke(scenario.input, config)

    while "__interrupt__" in result:
        result = graph.invoke(Command(resume={"approved": True, "feedback": ""}), config)

    return result


def main() -> None:
    if not GROQ_API_KEY:
        print("GROQ_API_KEY is not set. Copy .env.example to .env and add your Groq key, then re-run.")
        sys.exit(1)

    graph = build_graph()
    passed, failed, skipped = 0, 0, 0

    for scenario in LLM_SCENARIOS:
        print(f"\n--- {scenario.name} ---")
        if scenario.skip_reason:
            print(f"SKIP: {scenario.skip_reason}")
            skipped += 1
            continue
        try:
            result = run_scenario(graph, scenario)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR running scenario: {exc}")
            failed += 1
            continue

        rec = result.get("recommendation", {})
        print(
            f"decision={rec.get('decision')} confidence={rec.get('confidence_score')} "
            f"risk={result.get('risk_assessment', {}).get('risk_score')} "
            f"reanalyses={result.get('reanalysis_retry_count', 0)} "
            f"unverified_claims={len(result.get('unverified_claims', []))}"
        )
        for item in rec.get("supporting_evidence", []):
            print(f"  evidence: {item.get('metric')}={item.get('cited_value')!r}")
        failures = check_rules(scenario.rules, result)
        if failures:
            print("FAIL")
            for f in failures:
                print(f"  - {f}")
            failed += 1
        else:
            print("PASS")
            passed += 1

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped out of {len(LLM_SCENARIOS)} scenarios")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
