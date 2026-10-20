"""Runs the deterministic eval suite (evals/run_deterministic.py) under pytest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))

from run_deterministic import run_all  # noqa: E402


def test_deterministic_eval_rules_hold(stub_rag):
    failures = {name: f for name, f in run_all() if f}
    assert not failures, failures
