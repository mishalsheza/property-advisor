"""Shared fixtures. The Recommendation Agent's LLM is always stubbed so the
test suite never needs a GROQ_API_KEY or network access."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from property_advisor.agents import recommendation_agent as rec_module  # noqa: E402
from property_advisor.schemas import RecommendationOutput  # noqa: E402
from property_advisor.steps import rag_step  # noqa: E402


class StubLLM:
    """Mimics `get_llm().with_structured_output(...).invoke(...)`, returning
    queued RecommendationOutput values (the last one repeats) and recording
    every prompt it receives."""

    def __init__(self, outputs: list[dict]):
        self.outputs = [RecommendationOutput(**o) for o in outputs]
        self.calls: list[list] = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.outputs[min(len(self.calls), len(self.outputs)) - 1]


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise RuntimeError("Tests must not call the real LLM; use the stub_llm fixture.")

    monkeypatch.setattr(rec_module, "get_llm", _blocked)


@pytest.fixture
def stub_llm(monkeypatch):
    def install(*outputs: dict) -> StubLLM:
        stub = StubLLM(list(outputs))
        monkeypatch.setattr(rec_module, "get_llm", lambda *a, **k: stub)
        return stub

    return install


@pytest.fixture
def stub_rag(monkeypatch):
    """Replace vector retrieval in the graph with fixed chunks (no Chroma)."""
    chunks = [{"text": "stub chunk", "source": "rbi_ltv_riskweights_circular_2015.txt"}]
    monkeypatch.setattr(rag_step, "query_rag", lambda query, k=4: chunks)
    return chunks
