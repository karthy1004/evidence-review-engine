# ADR-0001: Deterministic scoring core; no LLM in the decision path

- Status: accepted
- Date: 2026-10-09

## Context

Due-diligence decisions get challenged by suppliers, auditors and internal reviewers, sometimes years later. Each decision must be reproducible from its inputs and explainable line by line. An LLM asked to "assess this supplier" can produce fluent reasoning, but the same input can yield different answers, and there is no ground truth for *why* a score moved.

## Decision

Scoring is a pure function of (assessment, rulebook version). No network, no clock (`as_of` is an input), no model calls. Rules live in versioned YAML, and the result carries a hash of its inputs.

LLMs are allowed only *before* the engine, to turn unstructured documents into structured candidates. Those candidates go through deterministic checks ([ADR-0002](0002-llm-extraction-behind-validation.md)).

## Consequences

- Any decision can be re-derived exactly, and a changed rulebook shows up as a changed fingerprint.
- The rules are less flexible than an LLM's judgement. Edge cases go to REVIEW and a human, which is the intended outcome, not a failure.
- Rule changes need a reviewer to edit YAML. That is cheaper and safer than prompt changes, which can't be diffed for behaviour.
