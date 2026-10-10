"""Regression gate on the eval harness itself and on the baseline's safety property."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from evals.run_evals import classify, evaluate
from evidence_review.extraction import Outcome, RegexBaselineExtractor

DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset.yaml"


def _cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = yaml.safe_load(DATASET.read_text(encoding="utf-8"))["cases"]
    return cases


def test_dataset_shape() -> None:
    cases = _cases()
    assert len(cases) == 20
    assert len({c["id"] for c in cases}) == 20
    assert sum(c["expected_outcome"] == "needs_human" for c in cases) == 6


def test_classify() -> None:
    assert classify("accepted", Outcome.ACCEPTED, []) == "correct_accept"
    assert classify("accepted", Outcome.ACCEPTED, ["issuer"]) == "silent_error"
    assert classify("needs_human", Outcome.ACCEPTED, []) == "silent_error"
    assert classify("needs_human", Outcome.NEEDS_HUMAN, ["issuer"]) == "correct_route"
    assert classify("accepted", Outcome.NEEDS_HUMAN, []) == "unnecessary_route"


def test_baseline_never_silently_accepts_a_wrong_document() -> None:
    summary = evaluate(RegexBaselineExtractor(), _cases())
    assert summary["silent_errors"] == 0
    assert summary["verdicts"] == {
        "correct_accept": 8,
        "unnecessary_route": 6,
        "correct_route": 6,
    }
