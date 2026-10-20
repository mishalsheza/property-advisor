#!/usr/bin/env python
"""Validation harness: run the deterministic chain + Recommendation Agent over
the entire mock dataset and report the BUY/HOLD/AVOID distribution.

Isolates the decision step (the one LLM agent): real property,
market, metrics and risk are computed per property; rag_context is left empty
so the comparison is apples-to-apples and not subject to vector-store state.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from property_advisor.agents.recommendation_agent import recommendation_agent  # noqa: E402
from property_advisor.state import PropertyState  # noqa: E402
from property_advisor.steps.financial_step import financial_calc_step  # noqa: E402
from property_advisor.steps.risk_step import risk_scoring_step  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "src" / "property_advisor" / "data"
PROPS = json.loads((DATA / "mock_properties.json").read_text())
MARKET = json.loads((DATA / "mock_market_trends.json").read_text())


def build_state(slug: str, strategy: str = "rental") -> PropertyState:
    record = {k: v for k, v in PROPS[slug].items() if k != "match_keywords"}
    record["locality_slug"] = slug
    return PropertyState(
        property_address=f"{record['locality']}, {record['city']}",
        budget=float(record["price_inr"]),
        investment_horizon_years=5,
        investment_strategy=strategy,
        property_data=record,
        market_data=MARKET.get(slug, {}),
    )


def run(slug: str, strategy: str) -> dict:
    state = build_state(slug, strategy)
    state = state.model_copy(update=financial_calc_step(state))
    state = state.model_copy(update=risk_scoring_step(state))
    rec = recommendation_agent(state)["recommendation"]
    return {
        "slug": slug,
        "decision": rec["decision"],
        "confidence": rec["confidence_score"],
        "roi_pct": state.investment_metrics["roi_pct"],
        "yield_pct": state.investment_metrics["rental_yield_pct"],
        "severity": state.investment_metrics["cash_flow_severity"],
        "risk_score": state.risk_assessment["risk_score"],
    }


def main() -> None:
    strategy = sys.argv[1] if len(sys.argv) > 1 else "rental"
    rows = []
    for slug in PROPS:
        if not MARKET.get(slug):
            continue
        try:
            rows.append(run(slug, strategy))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {slug}: {exc}")
    dist = Counter(r["decision"] for r in rows)
    print(f"\n{'slug':28} {'decision':>8} {'conf':>5} {'roi%':>7} {'yield%':>6} {'risk':>5}")
    for r in sorted(rows, key=lambda x: x["decision"]):
        print(f"{r['slug']:28} {r['decision']:>8} {r['confidence']:>5} {r['roi_pct']:>7} {r['yield_pct']:>6} {r['risk_score']:>5}")
    print(f"\nStrategy={strategy}  N={len(rows)}  distribution={dict(dist)}")


if __name__ == "__main__":
    main()
