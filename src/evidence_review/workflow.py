"""Reviewer workflow: explicit states, legal transitions only, every step audited.

The engine *recommends*; a named human *decides*. Disagreeing with the engine is
allowed but costs a written reason, and a hard-stop red flag can never be approved.
"""

from __future__ import annotations

from enum import StrEnum

from evidence_review.audit import AuditLog
from evidence_review.engine import evaluate
from evidence_review.models import Assessment, Decision, Result, Rulebook

MIN_OVERRIDE_REASON = 20


class CaseState(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    SCORED = "scored"
    IN_REVIEW = "in_review"
    DECIDED = "decided"


_ALLOWED: dict[CaseState, set[CaseState]] = {
    CaseState.DRAFT: {CaseState.SUBMITTED},
    CaseState.SUBMITTED: {CaseState.SCORED},
    CaseState.SCORED: {CaseState.IN_REVIEW},
    CaseState.IN_REVIEW: {CaseState.DECIDED, CaseState.DRAFT},  # DRAFT = sent back for info
    CaseState.DECIDED: set(),
}


class WorkflowError(RuntimeError):
    """An illegal transition or a decision that breaks a governance rule."""


class ReviewCase:
    def __init__(self, case_id: str, assessment: Assessment, rulebook: Rulebook) -> None:
        self.case_id = case_id
        self.assessment = assessment
        self.rulebook = rulebook
        self.state = CaseState.DRAFT
        self.result: Result | None = None
        self.final_decision: Decision | None = None
        self.reviewer: str | None = None
        self.log = AuditLog()
        self.log.append(
            "system", "case_opened", {"case": case_id, "supplier": assessment.supplier.id}
        )

    def _move(self, to: CaseState, actor: str, detail: dict[str, object] | None = None) -> None:
        if to not in _ALLOWED[self.state]:
            raise WorkflowError(f"cannot move from {self.state} to {to}")
        self.log.append(actor, f"state:{self.state}->{to}", dict(detail or {}))
        self.state = to

    def submit(self, actor: str) -> None:
        self._move(CaseState.SUBMITTED, actor)

    def score(self) -> Result:
        if self.state is not CaseState.SUBMITTED:
            raise WorkflowError(f"cannot score a case in state {self.state}")
        self.result = evaluate(self.assessment, self.rulebook)
        self._move(
            CaseState.SCORED,
            "engine",
            {
                "score": self.result.score,
                "recommendation": self.result.decision.value,
                "rulebook": f"{self.rulebook.id}@{self.rulebook.version}",
                "fingerprint": self.result.input_fingerprint,
            },
        )
        return self.result

    def assign(self, reviewer: str) -> None:
        self._move(CaseState.IN_REVIEW, "system", {"reviewer": reviewer})
        self.reviewer = reviewer

    def request_information(self, reviewer: str, note: str) -> None:
        self._require_reviewer(reviewer)
        self._move(CaseState.DRAFT, reviewer, {"note": note})
        self.result = None

    def decide(self, reviewer: str, decision: Decision, reason: str = "") -> None:
        self._require_reviewer(reviewer)
        if self.result is None:  # unreachable via the state machine; guard anyway
            raise WorkflowError("case has no engine result")
        recommended = self.result.decision
        hard_stops = [f.id for f in self.result.red_flags if f.effect == "hard_stop"]

        if decision is Decision.GO and hard_stops:
            raise WorkflowError(f"cannot approve: hard-stop red flags {hard_stops}")
        overriding = decision is not recommended
        if overriding and len(reason.strip()) < MIN_OVERRIDE_REASON:
            raise WorkflowError(
                f"overriding the engine ({recommended} -> {decision}) needs a reason "
                f"of at least {MIN_OVERRIDE_REASON} characters"
            )
        self._move(
            CaseState.DECIDED,
            reviewer,
            {
                "decision": decision.value,
                "recommended": recommended.value,
                "override": overriding,
                "reason": reason,
            },
        )
        self.final_decision = decision

    def _require_reviewer(self, actor: str) -> None:
        if self.state is not CaseState.IN_REVIEW:
            raise WorkflowError(f"case is {self.state}, not in review")
        if actor != self.reviewer:
            raise WorkflowError(f"{actor} is not the assigned reviewer")
