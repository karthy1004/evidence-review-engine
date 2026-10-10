"""Human-readable (Markdown) and machine-readable (JSON) reports."""

from __future__ import annotations

from evidence_review.models import Result

_MARK = {True: "yes", False: "no", None: "—"}


def to_json(result: Result) -> str:
    return result.model_dump_json(indent=2)


def to_markdown(result: Result, supplier_name: str) -> str:
    lines = [
        f"# Due-diligence pre-assessment — {supplier_name}",
        "",
        f"**Recommendation: {result.decision.value}** · score {result.score}/100 · "
        f"as of {result.as_of.isoformat()} · "
        f"rulebook `{result.rulebook_id}@{result.rulebook_version}`",
        "",
        "> Illustrative rulebook. A recommendation for a human reviewer, not a certification.",
        "",
        "## Why",
        *[f"- {r}" for r in result.decision_reasons],
        "",
        "## Category scores",
        "",
        "| Category | Score |",
        "|---|---:|",
        *[f"| {c.name} | {c.awarded}/{c.available} |" for c in result.categories],
        "",
    ]
    if result.red_flags:
        lines += [
            "## Red flags",
            "",
            *[f"- **{f.id}** ({f.effect}): {f.reason}" for f in result.red_flags],
            "",
        ]
    if result.evidence_gaps or result.unanswered:
        lines += ["## Gaps to close", ""]
        lines += [f"- Evidence: {g}" for g in result.evidence_gaps]
        lines += [f"- Unanswered: {u}" for u in result.unanswered]
        lines.append("")
    lines += [
        "## Question trace",
        "",
        "| Question | Answer | Points | Reason |",
        "|---|---|---:|---|",
        *[
            f"| {t.question_id} | {_MARK[t.answer]} | {t.points_awarded}/{t.points_available} "
            f"| {t.reason} |"
            for t in result.trace
        ],
        "",
        f"<sub>Input fingerprint `{result.input_fingerprint[:16]}…` — re-running the same "
        "input and rulebook reproduces this report exactly.</sub>",
        "",
    ]
    return "\n".join(lines)
