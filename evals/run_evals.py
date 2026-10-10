"""Run the extraction eval set and write a results report.

    python evals/run_evals.py                      # regex baseline (free, deterministic)
    python evals/run_evals.py --extractor claude   # needs ANTHROPIC_API_KEY; costs money

The headline metric is SILENT ERRORS: documents the pipeline accepted with at least
one wrong field. Those flow into scoring unseen. Routing to a human costs time;
a silent error costs trust. Target: zero.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evidence_review.extraction import ExtractedFields, Outcome, RegexBaselineExtractor, run
from evidence_review.extraction.base import Extractor

HERE = Path(__file__).parent
FIELDS = tuple(ExtractedFields.model_fields)


def _norm(v: Any) -> Any:
    return v.strip().casefold() if isinstance(v, str) else v


def _diff(got: ExtractedFields | None, expected: dict[str, Any]) -> list[str]:
    want = ExtractedFields.model_validate(expected)
    if got is None:
        return list(FIELDS)
    return [f for f in FIELDS if _norm(getattr(got, f)) != _norm(getattr(want, f))]


def classify(expected_outcome: str, outcome: Outcome, wrong: list[str]) -> str:
    if outcome is Outcome.ACCEPTED:
        if expected_outcome == "needs_human" or wrong:
            return "silent_error"
        return "correct_accept"
    return "correct_route" if expected_outcome == "needs_human" else "unnecessary_route"


def evaluate(extractor: Extractor, cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        res = run(extractor, case["text"])
        wrong = _diff(res.fields, case["expected"])
        rows.append(
            {
                "id": case["id"],
                "style": case["style"],
                "expected_outcome": case["expected_outcome"],
                "outcome": res.outcome.value,
                "verdict": classify(case["expected_outcome"], res.outcome, wrong),
                "wrong_fields": wrong,
                "problems": list(res.problems),
                "attempts": len(res.attempts),
                "cost_usd": res.cost_usd,
                "latency_ms": res.latency_ms,
            }
        )
    verdicts = Counter(r["verdict"] for r in rows)
    field_total = len(cases) * len(FIELDS)
    field_wrong = sum(len(r["wrong_fields"]) for r in rows)
    return {
        "extractor": extractor.name,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n": len(cases),
        "verdicts": dict(verdicts),
        "silent_errors": verdicts["silent_error"],
        "automation_rate": verdicts["correct_accept"] / len(cases),
        "field_accuracy": 1 - field_wrong / field_total,
        "retries": sum(r["attempts"] - 1 for r in rows),
        "total_cost_usd": sum(r["cost_usd"] for r in rows),
        "p50_latency_ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2],
        "rows": rows,
    }


def to_markdown(s: dict[str, Any]) -> str:
    v = s["verdicts"]
    lines = [
        f"# Extraction eval — `{s['extractor']}`",
        "",
        f"Run {s['run_at']} on {s['n']} synthetic documents (`evals/dataset.yaml`).",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| **Silent errors** (accepted with a wrong field, or accepted a trap) "
        f"| **{s['silent_errors']}** |",
        f"| Correctly accepted | {v.get('correct_accept', 0)} |",
        f"| Correctly routed to a human | {v.get('correct_route', 0)} |",
        f"| Unnecessarily routed to a human | {v.get('unnecessary_route', 0)} |",
        f"| Automation rate (correct accepts / all) | {s['automation_rate']:.0%} |",
        f"| Field accuracy (all fields, all docs) | {s['field_accuracy']:.1%} |",
        f"| Retries used | {s['retries']} |",
        f"| Total cost | ${s['total_cost_usd']:.4f} |",
        f"| Median latency per document | {s['p50_latency_ms']:.1f} ms |",
        "",
        "| Doc | Style | Expected | Got | Verdict | Wrong fields |",
        "|---|---|---|---|---|---|",
    ]
    for r in s["rows"]:
        lines.append(
            f"| {r['id']} | {r['style']} | {r['expected_outcome']} | {r['outcome']} "
            f"| {r['verdict']} | {', '.join(r['wrong_fields']) or '—'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--extractor", choices=["baseline", "claude"], default="baseline")
    args = p.parse_args()

    extractor: Extractor
    if args.extractor == "claude":
        from evidence_review.extraction.claude import ClaudeExtractor

        extractor = ClaudeExtractor()
    else:
        extractor = RegexBaselineExtractor()

    cases = yaml.safe_load((HERE / "dataset.yaml").read_text(encoding="utf-8"))["cases"]
    summary = evaluate(extractor, cases)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stem = args.extractor
    (out / f"{stem}.json").write_text(json.dumps(summary, indent=2, default=str), "utf-8")
    (out / f"{stem}.md").write_text(to_markdown(summary), "utf-8")
    print(to_markdown(summary))


if __name__ == "__main__":
    main()
