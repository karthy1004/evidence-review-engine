"""Deterministic regex baseline. It is the bar an LLM has to beat to earn its cost.

It reads 'Label: value' lines in the formats our synthetic documents use and leaves
anything else as null. It never guesses, so its failures route to a human."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from evidence_review.extraction.base import RawExtraction

_LABELS: dict[str, tuple[str, ...]] = {
    "document_type": ("document type", "type"),
    "holder_name": ("holder", "licence holder", "license holder", "issued to", "company"),
    "reference_number": (
        "reference",
        "reference number",
        "licence no",
        "license no",
        "permit no",
        "certificate no",
        "number",
    ),
    "issued_on": ("issued", "issue date", "date of issue", "issued on"),
    "expires_on": ("expires", "expiry", "expiry date", "valid until", "expires on"),
    "issuer": ("issuer", "issuing authority", "issued by", "authority"),
}

_TYPE_WORDS: tuple[tuple[str, str], ...] = (
    ("mining licen", "mining_licence"),
    ("export permit", "export_permit"),
    ("chain of custody", "chain_of_custody"),
    ("audit", "audit_report"),
    ("environmental permit", "environmental_permit"),
    ("sanctions", "sanctions_screening"),
)

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y")


def parse_date(value: str) -> date | None:
    cleaned = value.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _doc_type(value: str) -> str | None:
    low = value.casefold()
    return next((kind for word, kind in _TYPE_WORDS if word in low), None)


class RegexBaselineExtractor:
    name = "regex-baseline"
    supports_feedback = False
    cost_per_mtok_in = 0.0
    cost_per_mtok_out = 0.0

    def extract(self, text: str, feedback: str | None = None) -> RawExtraction:
        lines: dict[str, str] = {}
        for line in text.splitlines():
            label, sep, rest = line.partition(":")
            if sep and rest.strip():
                lines.setdefault(label.strip().casefold(), rest.strip())

        out: dict[str, Any] = {}
        for field_name, labels in _LABELS.items():
            value = next((lines[lbl] for lbl in labels if lbl in lines), None)
            if value is None:
                continue
            if field_name == "document_type":
                out[field_name] = _doc_type(value)
            elif field_name in ("issued_on", "expires_on"):
                out[field_name] = parse_date(value)
            else:
                out[field_name] = value
        if "document_type" not in out or out["document_type"] is None:
            first = text.strip().splitlines()[0] if text.strip() else ""
            out["document_type"] = _doc_type(first)
        return RawExtraction(data=out, model=self.name)
