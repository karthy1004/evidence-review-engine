"""Contract between the pipeline and any extractor (regex baseline, LLM, scripted fake)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from evidence_review.models import EvidenceType


class ExtractedFields(BaseModel):
    """What an extractor may return. Every field is optional on purpose: an extractor
    must say "not stated" (null) rather than guess. The pipeline decides what is required."""

    model_config = ConfigDict(extra="forbid")

    document_type: EvidenceType | None = None
    holder_name: str | None = None
    reference_number: str | None = None
    issued_on: date | None = None
    expires_on: date | None = None
    issuer: str | None = None


@dataclass(frozen=True)
class RawExtraction:
    data: dict[str, Any] | None
    refused: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    notes: list[str] = field(default_factory=list)


class Extractor(Protocol):
    name: str
    supports_feedback: bool
    cost_per_mtok_in: float
    cost_per_mtok_out: float

    def extract(self, text: str, feedback: str | None = None) -> RawExtraction: ...
