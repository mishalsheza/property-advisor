"""Deterministic check of directional claims in free text (justification and
evidence statements) against the computed state.

Covers three kinds of claim, clause by clause:
- cash flow sign ("positive cash flow", "cash flow after EMI is negative");
  a claim that doesn't say "operating"/"before loan" is checked against cash
  flow AFTER the EMI, which is what the buyer actually experiences;
- risk level ("low risk", "high flood risk") against risk_score or the
  per-factor indicator;
- yield level / comparison ("strong yield", "yield below the market average").
Any comparison to a benchmark that isn't in state (e.g. "above the local
average ROI") is unverified. Text the pipeline itself appends in [brackets]
is ignored.

This is keyword matching, not language understanding: it catches the common
wrong-direction phrasings, not every possible one.
"""

from __future__ import annotations

import re
from typing import Any

from property_advisor.state import PropertyState

POSITIVE = r"positive|surplus|self-sustaining|self-funding"
NEGATIVE = r"negative|deficit|shortfall"
NEGATION = re.compile(r"\b(not|no|never|isn't|isnt|aren't|without)\b")
OPERATING_SCOPE = re.compile(r"operating|before (the )?(loan|emi|financing|debt)|pre-financing|unlevered|\bnoi\b")
LEVERED_SCOPE = re.compile(r"after (the )?(emi|loan|financing|debt)|levered|leveraged|post-emi|net of (the )?(emi|debt)")
BENCHMARK = re.compile(
    r"\b(local|market|city|area|regional|national|neighbou?rhood|peer|sector)\b[\w\s-]{0,12}?\b(average|avg|benchmark|median|norm|mean)\b"
    r"|\bcomparable (properties|projects|flats)\b"
)

RISK_LOW = r"low|minimal|limited|modest|manageable|acceptable"
RISK_HIGH = r"high|elevated|significant|substantial|severe|considerable"
RISK_MODERATE = r"moderate|medium"
RISK_FACTORS = {
    "flood": "flood_risk",
    "vacancy": "vacancy_risk",
    "regulatory": "regulatory_risk",
    "volatility": "market_volatility",
    "crime": "crime_score",
}
# Bands deliberately overlap so borderline scores accept either word.
RISK_SCORE_BANDS = {"low": (0, 40), "moderate": (25, 75), "high": (60, 101)}

YIELD_HIGH = r"high|strong|healthy|solid|attractive|robust|good"
YIELD_LOW = r"low|weak|poor|thin|modest|meagre|meager"
# Overlapping like the risk bands: 3.5-4% may be called either.
YIELD_HIGH_MIN_PCT = 3.5
YIELD_LOW_MAX_PCT = 4.0
ABOVE = r"above|higher than|exceeds?|beats?|outperforms?"
BELOW = r"below|lower than|trails?|under|lags?|underperforms?"


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\[[^\]]*\]", " ", text)  # pipeline-added notes
    return [s.strip().lower() for s in re.split(r"(?<=[.;!?])\s+", text) if s.strip()]


def _clauses(sentence: str) -> list[str]:
    parts = re.split(r",\s|\s(?:but|while|whereas|although|though|however|despite|yet)\s", sentence)
    return [p.strip() for p in parts if p and p.strip()]


def _claim(kind: str, phrase: str, computed: Any, statement: str, reason: str) -> dict[str, Any]:
    return {"metric": f"text:{kind}", "cited_value": phrase, "computed_value": computed, "statement": statement, "reason": reason}


def _polarity(clause: str, positive: str, negative: str) -> str | None:
    pos = re.search(rf"\b({positive})\b", clause)
    neg = re.search(rf"\b({negative})\b", clause)
    if bool(pos) == bool(neg):
        return None  # none, or both (ambiguous)
    match = pos or neg
    preceding = clause[: match.start()].split()[-3:]
    negated = any(NEGATION.fullmatch(w) for w in preceding)
    is_pos = bool(pos) != negated
    return "positive" if is_pos else "negative"


def _check_cash_flow(clause: str, metrics: dict, statement: str) -> list[dict]:
    if not re.search(r"cash[- ]?flow", clause):
        return []
    polarity = _polarity(clause, POSITIVE, NEGATIVE)
    if polarity is None:
        return []
    if OPERATING_SCOPE.search(clause) and not LEVERED_SCOPE.search(clause):
        kind, key = "operating_cash_flow", "operating_cash_flow_inr"
    else:
        kind, key = "cash_flow_after_emi", "cash_flow_after_emi_inr"
    value = metrics.get(key)
    if value is None:
        return [_claim(kind, f"{polarity} cash flow", None, statement, f"no computed {key}")]
    if (polarity == "positive") != (value > 0):
        scope = "before the loan" if kind == "operating_cash_flow" else "after EMI (unqualified cash-flow claims are read as after EMI)"
        return [_claim(kind, f"{polarity} cash flow", value, statement, f"says {polarity} but cash flow {scope} is INR {value:,.0f}")]
    return []


def _risk_word(clause: str) -> tuple[str, re.Match] | None:
    for level, words in (("low", RISK_LOW), ("high", RISK_HIGH), ("moderate", RISK_MODERATE)):
        m = re.search(rf"\b({words})\b(?:[\s-]+\w+){{0,2}}?[\s-]+risk\b|\brisk\b(?:[\s-]+\w+){{0,3}}?[\s-]+(is |are )?({words})\b", clause)
        if m:
            return level, m
    return None


def _check_risk(clause: str, risk: dict, statement: str) -> list[dict]:
    if not re.search(r"\brisk", clause):
        return []
    found = _risk_word(clause)
    if not found:
        return []
    level, match = found
    span = match.group(0)
    factor = next((k for k in RISK_FACTORS if k in span), None)
    if factor:
        indicators = risk.get("raw_indicators", {})
        key = RISK_FACTORS[factor]
        actual = indicators.get(key)
        if actual is None:
            return [_claim(f"{factor}_risk", span, None, statement, f"no {key} indicator in the data")]
        if key == "crime_score":
            actual_level = "low" if actual < 40 else "high" if actual >= 60 else "moderate"
        else:
            actual_level = {"medium": "moderate"}.get(actual, actual)
        if actual_level != level:
            return [_claim(f"{factor}_risk", span, actual, statement, f"says {level} but {key} is {actual!r}")]
        return []
    score = risk.get("risk_score")
    if score is None:
        return [_claim("risk", span, None, statement, "no computed risk_score")]
    lo, hi = RISK_SCORE_BANDS[level]
    if not lo <= score < hi:
        return [_claim("risk", span, score, statement, f"says {level} risk but risk_score is {score}")]
    return []


def _check_yield_comparison(sentence: str, metrics: dict, market: dict) -> list[dict]:
    """Yield vs the market average — the only benchmark in state."""
    bench = BENCHMARK.search(sentence)
    if not re.search(r"\byields?\b", sentence) or not bench:
        return []
    value, avg = metrics.get("rental_yield_pct"), market.get("rental_yield_avg_pct")
    if avg is None or value is None:
        return [_claim("yield_benchmark", bench.group(0), None, sentence, "benchmark is not in the data")]
    claims = []
    direction = "above" if re.search(rf"\b({ABOVE})\b", sentence) else "below" if re.search(rf"\b({BELOW})\b", sentence) else None
    if direction and (direction == "above") != (value > avg):
        claims.append(_claim("yield_vs_market", f"yield {direction} market average", value, sentence,
                             f"says {direction} but yield is {value}% vs market average {avg}%"))
    # a figure quoted for the benchmark ("average of 3.1%") must be the market average
    quoted = re.match(r"\s*(?:of|at|is|=|\()?\s*(\d+(?:\.\d+)?)\s*%", sentence[bench.end():])
    if quoted and abs(float(quoted.group(1)) - avg) > 0.05:
        claims.append(_claim("yield_benchmark", f"{quoted.group(1)}%", avg, sentence,
                             f"quotes {quoted.group(1)}% for the market average, which is {avg}%"))
    return claims


def _check_yield(clause: str, metrics: dict, statement: str) -> list[dict]:
    if not re.search(r"\byields?\b", clause) or BENCHMARK.search(clause):
        return []  # comparisons are handled per sentence
    value = metrics.get("rental_yield_pct")
    m_high = re.search(rf"\b({YIELD_HIGH})\b(?:[\s-]+\w+){{0,2}}?[\s-]+yields?\b", clause)
    m_low = re.search(rf"\b({YIELD_LOW})\b(?:[\s-]+\w+){{0,2}}?[\s-]+yields?\b", clause)
    if value is None or bool(m_high) == bool(m_low):
        return []
    if m_high and value < YIELD_HIGH_MIN_PCT:
        return [_claim("yield", m_high.group(0), value, statement, f"says {m_high.group(1)} yield but rental_yield_pct is {value}% (needs >= {YIELD_HIGH_MIN_PCT}%)")]
    if m_low and value >= YIELD_LOW_MAX_PCT:
        return [_claim("yield", m_low.group(0), value, statement, f"says {m_low.group(1)} yield but rental_yield_pct is {value}%")]
    return []


def _check_other_benchmarks(sentence: str) -> list[dict]:
    """Benchmarks for anything other than yield are never in state."""
    m = BENCHMARK.search(sentence)
    if m and not re.search(r"\byields?\b", sentence):
        return [_claim("benchmark", m.group(0), None, sentence, "compares to a benchmark that is not in the data")]
    return []


def check_text_claims(text: str, state: PropertyState) -> list[dict[str, Any]]:
    """Return unsupported directional claims found in `text`."""
    if not text:
        return []
    metrics, risk, market = state.investment_metrics, state.risk_assessment, state.market_data
    found: list[dict] = []
    for sentence in _sentences(text):
        for clause in _clauses(sentence):
            found += _check_cash_flow(clause, metrics, sentence)
            found += _check_risk(clause, risk, sentence)
            found += _check_yield(clause, metrics, sentence)
        found += _check_yield_comparison(sentence, metrics, market)
        found += _check_other_benchmarks(sentence)
    return found
