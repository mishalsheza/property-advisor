"""Step 3: RAG retrieval.

Deterministic vector retrieval (no LLM) over the Indian real-estate corpus
(RBI circulars, tenancy/tax/RERA explainers, NDMA flood guidance). Synthesis
against this context happens downstream in the Recommendation Agent.
"""

from __future__ import annotations

from property_advisor.config import RAG_TOP_K
from property_advisor.logging_utils import timed_node
from property_advisor.state import PropertyState
from property_advisor.tools.rag_tool import query_rag


@timed_node("rag_retrieval_step")
def rag_retrieval_step(state: PropertyState) -> dict:
    city = state.property_data.get("city", "")
    locality = state.property_data.get("locality", "")

    query = (
        f"{locality} {city} real estate appreciation trends, zoning and RERA "
        f"regulations, infrastructure/metro development, flood and regulatory risk, "
        f"relevant to a {state.investment_strategy} investment strategy"
    ).strip()

    results = query_rag(query, k=RAG_TOP_K)

    # de-duplicate by source while preserving order
    seen = set()
    deduped = []
    for r in results:
        if r["source"] not in seen:
            seen.add(r["source"])
            deduped.append(r)

    return {"rag_context": deduped}
