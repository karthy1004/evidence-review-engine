"""Explainable due-diligence scoring with evidence checks and an audited review workflow."""

from evidence_review.engine import evaluate
from evidence_review.models import Assessment, Decision, Result, Rulebook
from evidence_review.rulebook import load_rulebook

__all__ = ["Assessment", "Decision", "Result", "Rulebook", "evaluate", "load_rulebook"]
__version__ = "0.1.0"
