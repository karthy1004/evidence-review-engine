"""Domain models. Everything crossing a boundary (files, CLI, LLM) is validated here."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceType = Literal[
    "mining_licence",
    "export_permit",
    "chain_of_custody",
    "audit_report",
    "environmental_permit",
    "sanctions_screening",
]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- rulebook


class Category(Frozen):
    id: str
    name: str
    weight: int = Field(gt=0)


class Question(Frozen):
    id: str
    category: str
    text: str
    points: int = Field(gt=0)
    evidence: tuple[EvidenceType, ...] = ()


class Condition(Frozen):
    """Exactly one of (fact, equals) or (question, answer)."""

    fact: str | None = None
    equals: bool | None = None
    question: str | None = None
    answer: bool | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Condition:
        fact_form = self.fact is not None and self.equals is not None
        question_form = self.question is not None and self.answer is not None
        if fact_form == question_form:
            raise ValueError("condition needs either fact+equals or question+answer")
        return self


class RedFlag(Frozen):
    id: str
    when: Condition
    effect: Literal["hard_stop", "cap"]
    reason: str


class Bands(Frozen):
    go_min: int
    review_min: int

    @model_validator(mode="after")
    def _ordered(self) -> Bands:
        if not 0 <= self.review_min < self.go_min <= 100:
            raise ValueError("bands must satisfy 0 <= review_min < go_min <= 100")
        return self


class Rulebook(Frozen):
    id: str
    version: str
    title: str
    evidence_max_age_days: int = Field(gt=0)
    bands: Bands
    categories: tuple[Category, ...]
    questions: tuple[Question, ...]
    red_flags: tuple[RedFlag, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Rulebook:
        cat_ids = [c.id for c in self.categories]
        q_ids = [q.id for q in self.questions]
        if len(set(cat_ids)) != len(cat_ids):
            raise ValueError("duplicate category id")
        if len(set(q_ids)) != len(q_ids):
            raise ValueError("duplicate question id")
        if sum(c.weight for c in self.categories) != 100:
            raise ValueError("category weights must sum to 100")
        for cat in self.categories:
            pts = sum(q.points for q in self.questions if q.category == cat.id)
            if pts != cat.weight:
                raise ValueError(
                    f"category {cat.id}: question points sum to {pts}, weight is {cat.weight}"
                )
        unknown = {q.category for q in self.questions} - set(cat_ids)
        if unknown:
            raise ValueError(f"questions reference unknown categories: {sorted(unknown)}")
        for flag in self.red_flags:
            if flag.when.question is not None and flag.when.question not in q_ids:
                raise ValueError(f"red flag {flag.id} references unknown question")
        return self


# --------------------------------------------------------------------------- case input


class EvidenceDocument(Frozen):
    id: str
    type: EvidenceType
    holder_name: str
    issued_on: date
    expires_on: date | None = None
    issuer: str
    text: str = ""


class Supplier(Frozen):
    id: str
    legal_name: str
    country: str
    role: Literal["mine", "trader", "refiner", "recycler"]


class Assessment(Frozen):
    """A supplier's submitted questionnaire plus evidence, as of a given date."""

    supplier: Supplier
    as_of: date
    answers: dict[str, bool]
    facts: dict[str, bool] = Field(default_factory=dict)
    documents: tuple[EvidenceDocument, ...] = ()


# --------------------------------------------------------------------------- output


class Decision(StrEnum):
    GO = "GO"
    REVIEW = "REVIEW"
    NO_GO = "NO_GO"


class EvidenceStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    VALID = "valid"
    MISSING = "missing"
    EXPIRED = "expired"
    STALE = "stale"
    NAME_MISMATCH = "name_mismatch"


class QuestionTrace(Frozen):
    question_id: str
    category: str
    answer: bool | None
    points_available: int
    points_awarded: int
    evidence_status: dict[str, EvidenceStatus]
    reason: str


class CategoryScore(Frozen):
    category: str
    name: str
    awarded: int
    available: int


class TriggeredFlag(Frozen):
    id: str
    effect: Literal["hard_stop", "cap"]
    reason: str


class Result(Frozen):
    supplier_id: str
    rulebook_id: str
    rulebook_version: str
    as_of: date
    input_fingerprint: str
    score: int
    decision: Decision
    decision_reasons: tuple[str, ...]
    categories: tuple[CategoryScore, ...]
    trace: tuple[QuestionTrace, ...]
    unanswered: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    red_flags: tuple[TriggeredFlag, ...]
