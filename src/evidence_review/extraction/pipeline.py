"""Extraction pipeline: extract -> schema-validate -> ground -> (retry once) -> accept or
route to a human. Every attempt is recorded with latency, tokens and cost."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import ValidationError

from evidence_review.engine import normalise_name
from evidence_review.extraction.base import ExtractedFields, Extractor

REQUIRED = ("document_type", "holder_name", "issued_on", "issuer")


class Outcome(StrEnum):
    ACCEPTED = "accepted"
    NEEDS_HUMAN = "needs_human"


@dataclass(frozen=True)
class Attempt:
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    problems: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionResult:
    outcome: Outcome
    fields: ExtractedFields | None
    problems: tuple[str, ...]
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)

    @property
    def cost_usd(self) -> float:
        return sum(a.cost_usd for a in self.attempts)

    @property
    def latency_ms(self) -> float:
        return sum(a.latency_ms for a in self.attempts)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.casefold())


def check(fields: ExtractedFields, source: str) -> list[str]:
    """Business and grounding checks the JSON schema cannot express.

    Grounding is the anti-hallucination guard: free-text identifiers the extractor
    returns must literally appear in the source document."""
    problems = [f"{name} missing" for name in REQUIRED if getattr(fields, name) is None]
    if fields.issued_on and fields.expires_on and fields.expires_on < fields.issued_on:
        problems.append("expires_on is before issued_on")

    squashed = _squash(source)
    if fields.holder_name and _squash(normalise_name(fields.holder_name)) not in squashed:
        problems.append("holder_name not found in document")
    if fields.reference_number and _squash(fields.reference_number) not in squashed:
        problems.append("reference_number not found in document")
    if fields.issuer and _squash(fields.issuer) not in squashed:
        problems.append("issuer not found in document")
    return problems


def run(extractor: Extractor, text: str, max_attempts: int = 2) -> ExtractionResult:
    attempts: list[Attempt] = []
    feedback: str | None = None
    problems: list[str] = []
    fields: ExtractedFields | None = None

    for _ in range(max_attempts):
        started = time.perf_counter()
        raw = extractor.extract(text, feedback)
        latency = (time.perf_counter() - started) * 1000
        cost = (
            raw.input_tokens * extractor.cost_per_mtok_in
            + raw.output_tokens * extractor.cost_per_mtok_out
        ) / 1_000_000

        fields = None
        if raw.refused:
            problems = ["model declined the request"]
        elif raw.data is None:
            problems = ["no output", *raw.notes]
        else:
            try:
                fields = ExtractedFields.model_validate(raw.data)
                problems = check(fields, text)
            except ValidationError as exc:
                problems = [
                    f"schema: {e['loc'][0] if e['loc'] else '?'} {e['msg']}" for e in exc.errors()
                ]

        attempts.append(
            Attempt(latency, raw.input_tokens, raw.output_tokens, cost, tuple(problems))
        )
        if not problems:
            return ExtractionResult(Outcome.ACCEPTED, fields, (), tuple(attempts))
        if raw.refused or not extractor.supports_feedback:
            break
        feedback = "\n".join(f"- {p}" for p in problems)

    return ExtractionResult(Outcome.NEEDS_HUMAN, fields, tuple(problems), tuple(attempts))
