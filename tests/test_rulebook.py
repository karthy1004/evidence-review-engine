from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from evidence_review.models import Rulebook
from evidence_review.rulebook import RulebookError, load_rulebook
from tests.conftest import RULEBOOK


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(RULEBOOK.read_text(encoding="utf-8"))
    return data


def test_illustrative_rulebook_is_consistent(rulebook: Rulebook) -> None:
    assert sum(c.weight for c in rulebook.categories) == 100
    assert sum(q.points for q in rulebook.questions) == 100
    assert rulebook.version == "1.0.0"


def test_weights_must_sum_to_100() -> None:
    raw = _raw()
    raw["categories"][0]["weight"] = 31
    with pytest.raises(ValueError, match="sum to 100"):
        Rulebook.model_validate(raw)


def test_question_points_must_match_category_weight() -> None:
    raw = _raw()
    raw["questions"][0]["points"] = 13  # origin now sums to 31, weight is 30
    with pytest.raises(ValueError, match="question points sum"):
        Rulebook.model_validate(raw)


def test_duplicate_question_ids_rejected() -> None:
    raw = _raw()
    raw["questions"][1]["id"] = raw["questions"][0]["id"]
    with pytest.raises(ValueError, match="duplicate question"):
        Rulebook.model_validate(raw)


def test_unknown_category_rejected() -> None:
    raw = _raw()
    raw["questions"][0]["category"] = "nonexistent"
    with pytest.raises(ValueError):
        Rulebook.model_validate(raw)


def test_bands_must_be_ordered() -> None:
    raw = _raw()
    raw["bands"] = {"go_min": 40, "review_min": 60}
    with pytest.raises(ValueError, match="bands"):
        Rulebook.model_validate(raw)


def test_condition_must_be_one_kind() -> None:
    raw = _raw()
    raw["red_flags"][0]["when"] = {
        "fact": "x",
        "equals": True,
        "question": "ORG-1",
        "answer": False,
    }
    with pytest.raises(ValueError, match="condition"):
        Rulebook.model_validate(raw)


def test_red_flag_must_reference_known_question() -> None:
    raw = _raw()
    raw["red_flags"][1]["when"] = {"question": "NOPE-1", "answer": False}
    with pytest.raises(ValueError, match="unknown question"):
        Rulebook.model_validate(raw)


def test_unknown_evidence_type_rejected() -> None:
    raw = _raw()
    raw["questions"][0]["evidence"] = ["a_photo_of_the_mine"]
    with pytest.raises(ValueError):
        Rulebook.model_validate(raw)


def test_load_errors_are_wrapped(tmp_path: Path) -> None:
    with pytest.raises(RulebookError, match="cannot read"):
        load_rulebook(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nversion: 1\n", encoding="utf-8")
    with pytest.raises(RulebookError, match="invalid rulebook"):
        load_rulebook(bad)
