"""Environment-driven configuration. Groq is the only supported LLM provider."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# LangSmith tracing. Supports both the modern LANGSMITH_* env vars and the
# legacy LANGCHAIN_* aliases (LANGSMITH_* wins if both are set). Tracing is
# enabled only if explicitly turned on AND an API key is present — otherwise
# it's a no-op, never a crash.
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT", "property-investment-advisor")
_tracing_requested = (
    os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2") or "false"
).lower() == "true"
LANGSMITH_TRACING_ENABLED = bool(_tracing_requested and LANGSMITH_API_KEY)

# kept for any code/tools that still read the legacy names directly
LANGCHAIN_TRACING_V2 = "true" if LANGSMITH_TRACING_ENABLED else "false"
LANGCHAIN_API_KEY = LANGSMITH_API_KEY
LANGCHAIN_PROJECT = LANGSMITH_PROJECT

RISK_HUMAN_REVIEW_THRESHOLD = float(os.getenv("RISK_HUMAN_REVIEW_THRESHOLD", "75"))
GUARDRAIL_CONFIDENCE_THRESHOLD = float(os.getenv("GUARDRAIL_CONFIDENCE_THRESHOLD", "0.70"))

# RAG retrieval: character-based chunking and number of chunks returned per query.
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))

MAX_DATA_RETRIES = int(os.getenv("MAX_DATA_RETRIES", "2"))
MAX_REANALYSIS_RETRIES = int(os.getenv("MAX_REANALYSIS_RETRIES", "2"))

AUTO_APPROVE_HUMAN_REVIEW = os.getenv("AUTO_APPROVE_HUMAN_REVIEW", "false").lower() == "true"

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))

# Propagate the resolved tracing config back into the environment so both
# LangGraph/LangChain's internal tracer and the langsmith SDK's @traceable
# decorator (used directly on each agent — see logging_utils.py) pick it up
# consistently, regardless of which env var naming convention was used.
if LANGSMITH_TRACING_ENABLED:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
else:
    # Explicitly disable rather than leaving stale/partial env vars from a
    # previous run that could otherwise half-enable tracing.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "300"))


def get_llm(temperature: float = 0.2, max_tokens: int = DEFAULT_MAX_TOKENS):
    """Return a Groq chat model. Raises clearly if no API key is configured.

    Defaults are deliberately tight (low temperature, capped output tokens):
    every call here produces short structured JSON, not prose, so there's no
    reason to pay for long completions.
    """
    from langchain_groq import ChatGroq

    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your Groq key."
        )
    return ChatGroq(
        model=GROQ_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=GROQ_API_KEY,
    )
