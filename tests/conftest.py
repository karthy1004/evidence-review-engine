from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from evidence_review.models import Assessment, EvidenceDocument, Rulebook, Supplier
from evidence_review.rulebook import load_rulebook

ROOT = Path(__file__).resolve().parents[1]
RULEBOOK = ROOT / "rulebooks" / "illustrative-responsible-sourcing-v1.yaml"
CASES = ROOT / "data" / "cases"
AS_OF = date(2026, 10, 1)


@pytest.fixture(scope="session")
def rulebook() -> Rulebook:
    return load_rulebook(RULEBOOK)


def load_case(name: str) -> Assessment:
    return Assessment.model_validate_json((CASES / name).read_text(encoding="utf-8"))


def doc(
    kind: str,
    holder: str = "Acme Gold Ltd",
    issued: date = date(2026, 1, 1),
    expires: date | None = None,
    doc_id: str | None = None,
) -> EvidenceDocument:
    return EvidenceDocument.model_validate(
        {
            "id": doc_id or f"D-{kind}",
            "type": kind,
            "holder_name": holder,
            "issued_on": issued,
            "expires_on": expires,
            "issuer": "Test Issuer",
        }
    )


ALL_EVIDENCE = (
    "chain_of_custody",
    "export_permit",
    "mining_licence",
    "audit_report",
    "environmental_permit",
    "sanctions_screening",
)


def make_assessment(
    answers: dict[str, bool] | None = None,
    facts: dict[str, bool] | None = None,
    documents: list[EvidenceDocument] | None = None,
    all_yes: bool = True,
) -> Assessment:
    base = (
        {
            q: True
            for q in (
                "ORG-1",
                "ORG-2",
                "ORG-3",
                "LEG-1",
                "LEG-2",
                "PPL-1",
                "PPL-2",
                "PPL-3",
                "ENV-1",
                "ENV-2",
                "GOV-1",
                "GOV-2",
            )
        }
        if all_yes
        else {}
    )
    base.update(answers or {})
    return Assessment(
        supplier=Supplier(id="S-T", legal_name="Acme Gold Ltd", country="XZ", role="trader"),
        as_of=AS_OF,
        answers=base,
        facts={"sanctions_match": False, "conflict_affected_area": False, **(facts or {})},
        documents=tuple(documents if documents is not None else [doc(k) for k in ALL_EVIDENCE]),
    )
