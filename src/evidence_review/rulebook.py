"""Load and validate a rulebook file."""

from __future__ import annotations

from pathlib import Path

import yaml

from evidence_review.models import Rulebook


class RulebookError(ValueError):
    """The rulebook file is unreadable or internally inconsistent."""


def load_rulebook(path: str | Path) -> Rulebook:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RulebookError(f"cannot read rulebook {path}: {exc}") from exc
    try:
        return Rulebook.model_validate(raw)
    except ValueError as exc:
        raise RulebookError(f"invalid rulebook {path}: {exc}") from exc
