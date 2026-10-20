"""Retrieval tests against the real RAG corpus and Chroma index.

Uses ChromaDB's local embedding model (downloaded once on first use); no LLM.
"""

import os

import pytest

from property_advisor.config import RAG_TOP_K
from property_advisor.state import PropertyState
from property_advisor.steps.rag_step import rag_retrieval_step
from property_advisor.tools.rag_tool import _CORPUS_DIR, query_rag

LTV_SOURCES = {
    "rbi_housing_finance_master_circular_2014.txt",
    "rbi_ltv_circular_2012.txt",
    "rbi_ltv_riskweights_circular_2015.txt",
}

# query -> sources of which at least one must appear in the top RAG_TOP_K chunks
EXPECTED_SOURCES = {
    "maximum home loan for a 60 lakh flat": LTV_SOURCES,
    "flood risk in a low-lying area": {"ndma_urban_flooding_excerpt.txt"},
    "security deposit limit for a rented flat": {"model_tenancy_act_2021_prs.txt"},
    "tax deduction on home loan interest for a let-out property": {"income_tax_house_property.txt"},
    "is RERA registration mandatory for a new project": {"rera_act_2016_explainer.txt"},
}


@pytest.mark.parametrize("query,expected", EXPECTED_SOURCES.items())
def test_query_retrieves_expected_source(query, expected):
    sources = [r["source"] for r in query_rag(query)]
    assert len(sources) == RAG_TOP_K
    assert expected & set(sources), f"{query!r} retrieved {sources}"


def test_corpus_contains_only_cleaned_sources():
    txt_files = {f for f in os.listdir(_CORPUS_DIR) if f.endswith(".txt")}
    assert "hinjewadi_bullish_analyst_note.txt" not in txt_files
    assert set().union(*EXPECTED_SOURCES.values()) <= txt_files


def test_rag_step_returns_deduplicated_context():
    state = PropertyState(
        property_address="Whitefield, Bangalore, 560066",
        budget=9_500_000,
        property_data={"city": "Bangalore", "locality": "Whitefield"},
    )
    rag_context = rag_retrieval_step(state)["rag_context"]
    sources = [r["source"] for r in rag_context]
    assert sources
    assert len(sources) == len(set(sources))
