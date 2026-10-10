from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.cli import main
from tests.conftest import CASES, RULEBOOK

RB = ["--rulebook", str(RULEBOOK)]


def test_assess_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*RB, "assess", str(CASES / "02-sierra-traders-review.json")]) == 0
    out = capsys.readouterr().out
    assert "**Recommendation: REVIEW** · score 73/100" in out
    assert "RF-CONFLICT-AREA" in out
    assert "Evidence: ORG-3: export_permit expired" in out


def test_assess_json_to_file(tmp_path: Path) -> None:
    target = tmp_path / "r.json"
    main(
        [
            *RB,
            "assess",
            str(CASES / "01-aurum-recyclers-go.json"),
            "--format",
            "json",
            "--out",
            str(target),
        ]
    )
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["decision"] == "GO"
    assert len(data["trace"]) == 12


def test_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*RB, "demo", "--cases", str(CASES)]) == 0
    out = capsys.readouterr().out
    assert "audit chain: intact" in out
    assert out.count("NO_GO") == 2


def test_extract_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.txt"
    good.write_text(
        "Export permit\nHolder: Acme Gold\nIssued: 2026-01-01\nIssuer: Customs XZ\n",
        encoding="utf-8",
    )
    assert main(["extract", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "accepted"

    vague = tmp_path / "vague.txt"
    vague.write_text("We have all our permits, honestly.", encoding="utf-8")
    assert main(["extract", str(vague)]) == 2
