"""Command-line entry point: `evidence-review assess | demo | extract`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidence_review.engine import evaluate
from evidence_review.extraction import RegexBaselineExtractor, run
from evidence_review.extraction.base import Extractor
from evidence_review.models import Assessment
from evidence_review.report import to_json, to_markdown
from evidence_review.rulebook import load_rulebook
from evidence_review.workflow import ReviewCase

DEFAULT_RULEBOOK = Path("rulebooks/illustrative-responsible-sourcing-v1.yaml")
DEFAULT_CASES = Path("data/cases")


def _load_case(path: Path) -> Assessment:
    return Assessment.model_validate_json(path.read_text(encoding="utf-8"))


def cmd_assess(args: argparse.Namespace) -> int:
    rulebook = load_rulebook(args.rulebook)
    assessment = _load_case(Path(args.case))
    result = evaluate(assessment, rulebook)
    out = (
        to_json(result)
        if args.format == "json"
        else to_markdown(result, assessment.supplier.legal_name)
    )
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    rulebook = load_rulebook(args.rulebook)
    cases = sorted(Path(args.cases).glob("*.json"))
    print(f"Rulebook {rulebook.id}@{rulebook.version} (illustrative)\n")
    print(f"{'case':<40}{'score':>6}  {'decision':<8} first reason")
    for path in cases:
        a = _load_case(path)
        r = evaluate(a, rulebook)
        print(f"{path.stem:<40}{r.score:>6}  {r.decision.value:<8} {r.decision_reasons[0]}")

    print("\nWorkflow walk-through on the first case:")
    case = ReviewCase("CASE-001", _load_case(cases[0]), rulebook)
    case.submit("supplier-portal")
    rec = case.score()
    case.assign("reviewer.a")
    case.decide("reviewer.a", rec.decision)
    for e in case.log.entries:
        print(f"  #{e.seq} {e.actor:<16} {e.action:<28} {e.hash[:12]}")
    problems = case.log.verify()
    print(f"  audit chain: {problems if problems else 'intact'}")
    return 0


def _extractor(name: str) -> Extractor:
    if name == "claude":
        from evidence_review.extraction.claude import ClaudeExtractor  # optional dependency

        return ClaudeExtractor()
    return RegexBaselineExtractor()


def cmd_extract(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    res = run(_extractor(args.extractor), text)
    print(
        json.dumps(
            {
                "outcome": res.outcome.value,
                "fields": res.fields.model_dump(mode="json") if res.fields else None,
                "problems": list(res.problems),
                "attempts": len(res.attempts),
                "cost_usd": round(res.cost_usd, 6),
                "latency_ms": round(res.latency_ms, 1),
            },
            indent=2,
        )
    )
    return 0 if res.outcome.value == "accepted" else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="evidence-review")
    p.add_argument("--rulebook", default=str(DEFAULT_RULEBOOK))
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("assess", help="score one case file")
    a.add_argument("case")
    a.add_argument("--format", choices=["md", "json"], default="md")
    a.add_argument("--out")
    a.set_defaults(func=cmd_assess)

    d = sub.add_parser("demo", help="score every sample case and walk one through review")
    d.add_argument("--cases", default=str(DEFAULT_CASES))
    d.set_defaults(func=cmd_demo)

    x = sub.add_parser("extract", help="extract fields from a text document")
    x.add_argument("file")
    x.add_argument("--extractor", choices=["baseline", "claude"], default="baseline")
    x.set_defaults(func=cmd_extract)

    args = p.parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
