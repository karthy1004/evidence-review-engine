from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from evidence_review.extraction import (
    ExtractedFields,
    Outcome,
    RawExtraction,
    RegexBaselineExtractor,
    check,
    run,
)
from evidence_review.extraction.baseline import parse_date

STRUCTURED = """MINING LICENCE
Holder: Aurum Recyclers Ltd
Licence No: ML-2025-0042
Issued: 2025-01-10
Expires: 09/01/2028
Issuing authority: Precious Metals Board XA
"""

PROSE = """This is to certify that Aurum Recyclers Ltd has been granted mining
licence ML-2025-0042 by the Precious Metals Board XA on 10 January 2025."""


class Scripted:
    """Fake extractor that replays canned outputs and records the feedback it got."""

    name = "scripted"
    supports_feedback = True
    cost_per_mtok_in = 4.0
    cost_per_mtok_out = 20.0

    def __init__(self, outputs: list[RawExtraction]) -> None:
        self.outputs = outputs
        self.feedback: list[str | None] = []

    def extract(self, text: str, feedback: str | None = None) -> RawExtraction:
        self.feedback.append(feedback)
        return self.outputs[len(self.feedback) - 1]


GOOD: dict[str, Any] = {
    "document_type": "mining_licence",
    "holder_name": "Aurum Recyclers Ltd",
    "reference_number": "ML-2025-0042",
    "issued_on": "2025-01-10",
    "expires_on": "2028-01-09",
    "issuer": "Precious Metals Board XA",
}


def test_baseline_reads_structured_document() -> None:
    res = run(RegexBaselineExtractor(), STRUCTURED)
    assert res.outcome is Outcome.ACCEPTED
    assert res.fields == ExtractedFields.model_validate(GOOD)
    assert res.cost_usd == 0
    assert len(res.attempts) == 1


def test_baseline_routes_prose_to_human_instead_of_guessing() -> None:
    res = run(RegexBaselineExtractor(), PROSE)
    assert res.outcome is Outcome.NEEDS_HUMAN
    assert "holder_name missing" in res.problems
    assert len(res.attempts) == 1  # deterministic extractor: no pointless retry


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2025-01-10", date(2025, 1, 10)),
        ("10/01/2025", date(2025, 1, 10)),
        ("10 January 2025", date(2025, 1, 10)),
        ("10 Jan 2025.", date(2025, 1, 10)),
        ("January 10, 2025", date(2025, 1, 10)),
        ("next Tuesday", None),
    ],
)
def test_date_formats(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_grounding_catches_invented_values() -> None:
    fields = ExtractedFields.model_validate(
        {**GOOD, "holder_name": "Aurum Holdings plc", "reference_number": "ML-9999"}
    )
    problems = check(fields, STRUCTURED)
    assert "holder_name not found in document" in problems
    assert "reference_number not found in document" in problems


def test_dates_must_be_in_order() -> None:
    fields = ExtractedFields.model_validate({**GOOD, "expires_on": "2020-01-01"})
    assert "expires_on is before issued_on" in check(fields, STRUCTURED)


def test_retry_with_feedback_then_accept() -> None:
    bad = {**GOOD, "holder_name": "Aurum Group"}
    fake = Scripted(
        [
            RawExtraction(data=bad, input_tokens=1000, output_tokens=100),
            RawExtraction(data=GOOD, input_tokens=1200, output_tokens=100),
        ]
    )
    res = run(fake, STRUCTURED)
    assert res.outcome is Outcome.ACCEPTED
    assert fake.feedback[0] is None
    assert fake.feedback[1] is not None and "holder_name not found" in fake.feedback[1]
    assert res.cost_usd == pytest.approx((2200 * 4 + 200 * 20) / 1_000_000)


def test_gives_up_after_max_attempts() -> None:
    bad = {**GOOD, "issuer": None}
    fake = Scripted([RawExtraction(data=bad)] * 2)
    res = run(fake, STRUCTURED)
    assert res.outcome is Outcome.NEEDS_HUMAN
    assert res.problems == ("issuer missing",)
    assert len(res.attempts) == 2


def test_refusal_goes_straight_to_human() -> None:
    fake = Scripted([RawExtraction(data=None, refused=True)])
    res = run(fake, STRUCTURED)
    assert res.outcome is Outcome.NEEDS_HUMAN
    assert res.problems == ("model declined the request",)
    assert len(res.attempts) == 1


def test_schema_violation_is_reported_not_raised() -> None:
    fake = Scripted([RawExtraction(data={**GOOD, "issued_on": "soon", "colour": "gold"})] * 2)
    res = run(fake, STRUCTURED)
    assert res.outcome is Outcome.NEEDS_HUMAN
    assert any(p.startswith("schema: issued_on") for p in res.problems)
    assert any(p.startswith("schema: colour") for p in res.problems)


def test_transport_failure_is_reported() -> None:
    fake = Scripted([RawExtraction(data=None, notes=["connection error"])] * 2)
    res = run(fake, STRUCTURED)
    assert res.outcome is Outcome.NEEDS_HUMAN
    assert res.problems == ("no output", "connection error")
