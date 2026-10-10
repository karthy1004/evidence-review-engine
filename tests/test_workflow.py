from __future__ import annotations

import pytest

from evidence_review.audit import AuditEntry, AuditLog
from evidence_review.models import Decision, Rulebook
from evidence_review.workflow import CaseState, ReviewCase, WorkflowError
from tests.conftest import load_case, make_assessment


def _in_review(rulebook: Rulebook, case_file: str | None = None) -> ReviewCase:
    assessment = load_case(case_file) if case_file else make_assessment()
    case = ReviewCase("C-1", assessment, rulebook)
    case.submit("portal")
    case.score()
    case.assign("rev")
    return case


def test_happy_path_is_fully_audited(rulebook: Rulebook) -> None:
    case = _in_review(rulebook)
    case.decide("rev", Decision.GO)
    assert case.state is CaseState.DECIDED
    assert [e.action for e in case.log.entries] == [
        "case_opened",
        "state:draft->submitted",
        "state:submitted->scored",
        "state:scored->in_review",
        "state:in_review->decided",
    ]
    assert case.log.entries[-1].detail["override"] is False
    assert case.log.verify() == []


def test_cannot_skip_states(rulebook: Rulebook) -> None:
    case = ReviewCase("C-2", make_assessment(), rulebook)
    with pytest.raises(WorkflowError):
        case.score()
    with pytest.raises(WorkflowError):
        case.assign("rev")
    with pytest.raises(WorkflowError):
        case.decide("rev", Decision.GO)


def test_decided_case_is_final(rulebook: Rulebook) -> None:
    case = _in_review(rulebook)
    case.decide("rev", Decision.GO)
    with pytest.raises(WorkflowError):
        case.decide("rev", Decision.NO_GO)


def test_override_requires_written_reason(rulebook: Rulebook) -> None:
    case = _in_review(rulebook, "02-sierra-traders-review.json")
    with pytest.raises(WorkflowError, match="needs a reason"):
        case.decide("rev", Decision.NO_GO, "no")
    case.decide("rev", Decision.NO_GO, "Site visit found undeclared intermediary in the chain.")
    assert case.log.entries[-1].detail["override"] is True


def test_hard_stop_can_never_be_approved(rulebook: Rulebook) -> None:
    case = _in_review(rulebook, "03-northfield-mining-nogo.json")
    with pytest.raises(WorkflowError, match="hard-stop"):
        case.decide("rev", Decision.GO, "The sanctions match is a false positive, trust me.")


def test_only_assigned_reviewer_decides(rulebook: Rulebook) -> None:
    case = _in_review(rulebook)
    with pytest.raises(WorkflowError, match="not the assigned reviewer"):
        case.decide("someone.else", Decision.GO)


def test_request_information_returns_case_to_draft(rulebook: Rulebook) -> None:
    case = _in_review(rulebook, "05-harbour-bullion-incomplete.json")
    case.request_information("rev", "Please upload a sanctions screening.")
    assert case.state is CaseState.DRAFT
    assert case.result is None
    case.submit("portal")
    case.score()
    assert case.log.verify() == []


def test_tampering_is_detected(rulebook: Rulebook) -> None:
    case = _in_review(rulebook, "02-sierra-traders-review.json")
    case.decide("rev", Decision.REVIEW)
    entries = list(case.log.entries)
    forged = entries[2].model_dump()
    assert forged["detail"]["recommendation"] == "REVIEW"
    forged["detail"] = {**forged["detail"], "score": 100, "recommendation": "GO"}
    entries[2] = AuditEntry.model_validate(forged)
    problems = AuditLog(entries).verify()
    assert problems == ["entry 2: content does not match its hash"]

    deleted = AuditLog([e for i, e in enumerate(case.log.entries) if i != 1]).verify()
    assert any("prev_hash" in p for p in deleted)
    assert any("sequence" in p for p in deleted)


def test_audit_log_round_trips_through_jsonl(rulebook: Rulebook) -> None:
    case = _in_review(rulebook)
    restored = AuditLog.from_jsonl(case.log.to_jsonl())
    assert restored.entries == case.log.entries
    assert restored.verify() == []
    assert restored.head == case.log.head
