# ADR-0002: LLM extraction is a proposal, validated and grounded before use

- Status: accepted
- Date: 2026-10-09

## Context

Typing fields out of licences, permits and audit summaries is the slowest part of a review, and LLMs are good at it. The failure that matters is not malformed JSON, which structured outputs largely prevent. It is a **well-formed, plausible, wrong value**: a licence number that isn't on the page, or a holder name "corrected" to the parent company. That error flows into scoring silently.

## Decision

1. The extraction schema makes every field nullable, and the prompt instructs the model to return null rather than infer.
2. The pipeline, not the model, decides what is required.
3. After schema validation, deterministic checks run: required fields present, `expires_on ≥ issued_on`, and `holder_name`, `reference_number` and `issuer` must literally appear in the source text (normalised for case and punctuation). This is the anti-hallucination guard.
4. On failure, retry **once**, sending the specific problems back as feedback. Then route to a human.
5. A refusal (`stop_reason == "refusal"`) routes straight to a human without retry. Rate limits, connection errors and 5xx (after the SDK's own retries) also route to a human. 4xx errors raise, because they indicate misconfiguration.
6. Measure every change with the eval set. The headline metric is *silent errors* (accepted but wrong), not accuracy.
7. A regex baseline stays in the codebase as the bar the LLM must beat.

Server-side model fallbacks were deliberately not enabled. A refusal on a supplier document should reach a person, not be re-tried on another model.

## Consequences

- Silent errors are bounded by the grounding check rather than by model quality.
- Grounding is lexical. It can't tell that the right string was put in the wrong field (e.g. the issuer's name as the holder). The eval set should grow to cover that.
- Each document costs up to two model calls, recorded per attempt.
