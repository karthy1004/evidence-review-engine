from __future__ import annotations

from datetime import date

import pytest

from evidence_review.engine import evaluate, normalise_name
from evidence_review.models import Decision, EvidenceStatus, Rulebook
from tests.conftest import ALL_EVIDENCE, doc, load_case, make_assessment


@pytest.mark.parametrize(
    ("case", "score", "decision"),
    [
        ("01-aurum-recyclers-go.json", 100, Decision.GO),
        ("02-sierra-traders-review.json", 73, Decision.REVIEW),
        ("03-northfield-mining-nogo.json", 88, Decision.NO_GO),
        ("04-delta-refining-unsupported-claims.json", 16, Decision.NO_GO),
        ("05-harbour-bullion-incomplete.json", 90, Decision.REVIEW),
    ],
)
def test_sample_cases(rulebook: Rulebook, case: str, score: int, decision: Decision) -> None:
    result = evaluate(load_case(case), rulebook)
    assert (result.score, result.decision) == (score, decision)


def test_high_score_does_not_beat_a_hard_stop(rulebook: Rulebook) -> None:
    result = evaluate(load_case("03-northfield-mining-nogo.json"), rulebook)
    assert result.score >= rulebook.bands.go_min
    assert [f.id for f in result.red_flags] == ["RF-SANCTIONS"]


def test_claims_without_evidence_earn_nothing(rulebook: Rulebook) -> None:
    result = evaluate(load_case("04-delta-refining-unsupported-claims.json"), rulebook)
    by_q = {t.question_id: t for t in result.trace}
    assert by_q["ORG-1"].evidence_status["chain_of_custody"] is EvidenceStatus.NAME_MISMATCH
    assert by_q["LEG-1"].evidence_status["mining_licence"] is EvidenceStatus.EXPIRED
    assert by_q["PPL-1"].evidence_status["audit_report"] is EvidenceStatus.STALE
    assert by_q["ENV-2"].evidence_status["environmental_permit"] is EvidenceStatus.MISSING
    assert all(by_q[q].points_awarded == 0 for q in ("ORG-1", "LEG-1", "PPL-1", "ENV-2"))
    assert "ORG-1: chain_of_custody name_mismatch" in result.evidence_gaps


def test_unknown_sanctions_status_blocks_go(rulebook: Rulebook) -> None:
    result = evaluate(load_case("05-harbour-bullion-incomplete.json"), rulebook)
    assert "fact:sanctions_match" in result.unanswered
    assert result.decision is Decision.REVIEW


def test_conflict_area_caps_at_review(rulebook: Rulebook) -> None:
    result = evaluate(make_assessment(facts={"conflict_affected_area": True}), rulebook)
    assert result.score == 100
    assert result.decision is Decision.REVIEW
    assert any("RF-CONFLICT-AREA" in r for r in result.decision_reasons)


def test_answering_no_to_child_labour_question_is_a_hard_stop(rulebook: Rulebook) -> None:
    result = evaluate(make_assessment(answers={"PPL-3": False}), rulebook)
    assert result.decision is Decision.NO_GO
    assert "RF-CHILD-LABOUR" in {f.id for f in result.red_flags}


def test_legal_suffixes_and_case_do_not_cause_name_mismatch() -> None:
    assert normalise_name("AURUM RECYCLERS LIMITED") == normalise_name("Aurum Recyclers Ltd.")
    assert normalise_name("Delta Refining Group") != normalise_name("Delta Precious Metals")


def test_best_document_wins_when_several_exist(rulebook: Rulebook) -> None:
    docs = [doc(k) for k in ALL_EVIDENCE if k != "mining_licence"]
    docs += [
        doc("mining_licence", expires=date(2025, 1, 1), doc_id="old"),
        doc("mining_licence", expires=date(2030, 1, 1), doc_id="new"),
    ]
    result = evaluate(make_assessment(documents=docs), rulebook)
    leg1 = next(t for t in result.trace if t.question_id == "LEG-1")
    assert leg1.evidence_status["mining_licence"] is EvidenceStatus.VALID


def test_evidence_on_expiry_day_is_still_valid(rulebook: Rulebook) -> None:
    docs = [doc(k) for k in ALL_EVIDENCE if k != "export_permit"]
    docs.append(doc("export_permit", expires=date(2026, 10, 1)))
    result = evaluate(make_assessment(documents=docs), rulebook)
    assert result.score == 100


def test_stale_boundary(rulebook: Rulebook) -> None:
    max_age = rulebook.evidence_max_age_days
    on_limit = date.fromordinal(date(2026, 10, 1).toordinal() - max_age)
    past_limit = date.fromordinal(on_limit.toordinal() - 1)
    # audit_report backs PPL-1 (12) + PPL-3 (7) + ENV-1 (8) = 27 points
    for issued, expected in ((on_limit, 100), (past_limit, 73)):
        docs = [doc(k) for k in ALL_EVIDENCE if k != "audit_report"]
        docs.append(doc("audit_report", issued=issued))
        assert evaluate(make_assessment(documents=docs), rulebook).score == expected


def test_low_score_is_no_go(rulebook: Rulebook) -> None:
    result = evaluate(make_assessment(documents=[]), rulebook)
    assert result.score == 10  # only the two no-evidence-required questions
    assert result.decision is Decision.NO_GO


def test_unanswered_questions_are_listed_and_score_zero(rulebook: Rulebook) -> None:
    result = evaluate(make_assessment(all_yes=False, answers={"ORG-1": True}), rulebook)
    assert len(result.unanswered) == 11
    assert result.score == 12


def test_category_scores_add_up(rulebook: Rulebook) -> None:
    result = evaluate(load_case("02-sierra-traders-review.json"), rulebook)
    assert sum(c.awarded for c in result.categories) == result.score


def test_deterministic_and_fingerprinted(rulebook: Rulebook) -> None:
    a = make_assessment()
    first, second = evaluate(a, rulebook), evaluate(a, rulebook)
    assert first == second
    changed = evaluate(make_assessment(answers={"GOV-2": False}), rulebook)
    assert changed.input_fingerprint != first.input_fingerprint
