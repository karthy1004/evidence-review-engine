"""The deterministic scoring core.

Design rule: a "yes" only earns points if the evidence behind it is present, current
and issued to the supplier being assessed. Claims without evidence score zero and are
listed as gaps. Same input + same rulebook -> same result and same fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from evidence_review.models import (
    Assessment,
    CategoryScore,
    Condition,
    Decision,
    EvidenceDocument,
    EvidenceStatus,
    EvidenceType,
    Question,
    QuestionTrace,
    Result,
    Rulebook,
    TriggeredFlag,
)

_LEGAL_SUFFIXES = {"ltd", "limited", "llc", "inc", "sa", "sas", "gmbh", "plc", "co", "corp"}

# Lower rank = better. Used to report the most useful status when several documents
# of the same type exist (e.g. one expired and one valid -> valid).
_STATUS_RANK = {
    EvidenceStatus.VALID: 0,
    EvidenceStatus.STALE: 1,
    EvidenceStatus.EXPIRED: 2,
    EvidenceStatus.NAME_MISMATCH: 3,
    EvidenceStatus.MISSING: 4,
}


def normalise_name(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.casefold())
    return " ".join(t for t in tokens if t not in _LEGAL_SUFFIXES)


def document_status(
    doc: EvidenceDocument, assessment: Assessment, max_age_days: int
) -> EvidenceStatus:
    if normalise_name(doc.holder_name) != normalise_name(assessment.supplier.legal_name):
        return EvidenceStatus.NAME_MISMATCH
    if doc.expires_on is not None and doc.expires_on < assessment.as_of:
        return EvidenceStatus.EXPIRED
    if (assessment.as_of - doc.issued_on).days > max_age_days:
        return EvidenceStatus.STALE
    return EvidenceStatus.VALID


def evidence_status(
    kind: EvidenceType, assessment: Assessment, max_age_days: int
) -> EvidenceStatus:
    statuses = [
        document_status(d, assessment, max_age_days) for d in assessment.documents if d.type == kind
    ]
    if not statuses:
        return EvidenceStatus.MISSING
    return min(statuses, key=_STATUS_RANK.__getitem__)


def _score_question(q: Question, assessment: Assessment, max_age_days: int) -> QuestionTrace:
    answer = assessment.answers.get(q.id)
    statuses = {kind: evidence_status(kind, assessment, max_age_days) for kind in q.evidence}
    shown: dict[str, EvidenceStatus] = {str(k): v for k, v in statuses.items()} or {
        "-": EvidenceStatus.NOT_REQUIRED
    }

    if answer is None:
        awarded, reason = 0, "unanswered"
    elif answer is False:
        awarded, reason = 0, "answered no"
    else:
        problems = {k: v for k, v in statuses.items() if v is not EvidenceStatus.VALID}
        if problems:
            detail = ", ".join(f"{k} {v.value}" for k, v in sorted(problems.items()))
            awarded, reason = 0, f"claimed yes but evidence not acceptable ({detail})"
        else:
            awarded = q.points
            reason = "yes, evidence valid" if q.evidence else "yes, no evidence required"

    return QuestionTrace(
        question_id=q.id,
        category=q.category,
        answer=answer,
        points_available=q.points,
        points_awarded=awarded,
        evidence_status=shown,
        reason=reason,
    )


def _condition_holds(cond: Condition, assessment: Assessment) -> bool | None:
    """True/False when decidable, None when the input needed to decide is missing."""
    if cond.fact is not None:
        value = assessment.facts.get(cond.fact)
        return None if value is None else value == cond.equals
    value = assessment.answers.get(cond.question or "")
    return None if value is None else value == cond.answer


def fingerprint(assessment: Assessment, rulebook: Rulebook) -> str:
    payload = {
        "rulebook": [rulebook.id, rulebook.version],
        "assessment": assessment.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def evaluate(assessment: Assessment, rulebook: Rulebook) -> Result:
    trace = tuple(
        _score_question(q, assessment, rulebook.evidence_max_age_days) for q in rulebook.questions
    )
    score = sum(t.points_awarded for t in trace)

    categories = tuple(
        CategoryScore(
            category=c.id,
            name=c.name,
            awarded=sum(t.points_awarded for t in trace if t.category == c.id),
            available=c.weight,
        )
        for c in rulebook.categories
    )

    unanswered = [t.question_id for t in trace if t.answer is None]
    evidence_gaps = [
        f"{t.question_id}: {kind} {status.value}"
        for t in trace
        if t.answer is True
        for kind, status in t.evidence_status.items()
        if status not in (EvidenceStatus.VALID, EvidenceStatus.NOT_REQUIRED)
    ]

    flags: list[TriggeredFlag] = []
    for flag in rulebook.red_flags:
        holds = _condition_holds(flag.when, assessment)
        if holds is None and flag.when.fact is not None:
            unanswered.append(f"fact:{flag.when.fact}")
        if holds:
            flags.append(TriggeredFlag(id=flag.id, effect=flag.effect, reason=flag.reason))

    hard_stops = [f for f in flags if f.effect == "hard_stop"]
    caps = [f for f in flags if f.effect == "cap"]
    reasons: list[str] = []

    if hard_stops:
        decision = Decision.NO_GO
        reasons += [f"hard stop {f.id}: {f.reason}" for f in hard_stops]
    elif score < rulebook.bands.review_min:
        decision = Decision.NO_GO
        reasons.append(f"score {score} below review threshold {rulebook.bands.review_min}")
    elif score >= rulebook.bands.go_min and not caps and not unanswered:
        decision = Decision.GO
        reasons.append(f"score {score} meets GO threshold {rulebook.bands.go_min}")
    else:
        decision = Decision.REVIEW
        if score < rulebook.bands.go_min:
            reasons.append(f"score {score} below GO threshold {rulebook.bands.go_min}")
        reasons += [f"capped by {f.id}: {f.reason}" for f in caps]
        if unanswered:
            reasons.append(f"incomplete: {len(_dedupe(unanswered))} item(s) unanswered")

    return Result(
        supplier_id=assessment.supplier.id,
        rulebook_id=rulebook.id,
        rulebook_version=rulebook.version,
        as_of=assessment.as_of,
        input_fingerprint=fingerprint(assessment, rulebook),
        score=score,
        decision=decision,
        decision_reasons=tuple(reasons),
        categories=categories,
        trace=trace,
        unanswered=_dedupe(unanswered),
        evidence_gaps=_dedupe(evidence_gaps),
        red_flags=tuple(flags),
    )
