# ADR-0003: Hash-chained append-only audit log

- Status: accepted
- Date: 2026-10-09

## Context

Reviewers can override the engine. When an approval is questioned later, the record must show who decided what, when, and why, and that the record wasn't edited afterwards.

## Decision

Each entry stores `prev_hash` and its own SHA-256 over (seq, timestamp, actor, action, detail, prev_hash), serialised canonically. `verify()` recomputes the chain and reports each broken link. Logs serialise to JSONL.

## Consequences

- An edit, deletion or reordering of a past entry is detected (tested).
- It does not stop an attacker who can rewrite the *whole* file and rebuild the chain. Mitigation: publish or store the head hash elsewhere at decision time.
- No database or external service is needed, so the demo runs anywhere.
