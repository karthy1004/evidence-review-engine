# Architecture

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `models.py` | Pydantic types for rulebook, case input and result. Rulebook self-consistency checks. | — |
| `rulebook.py` | Load and validate YAML. Wrap errors in `RulebookError`. | models |
| `engine.py` | Pure function `evaluate(assessment, rulebook) -> Result`. No I/O, no clock, no randomness. | models |
| `workflow.py` | `ReviewCase` state machine. Governance rules on decisions. | engine, audit |
| `audit.py` | Hash-chained append-only log, `verify()`, JSONL round-trip. | — |
| `extraction/` | `Extractor` protocol, regex baseline, Claude adapter, pipeline (validate → ground → retry → route). | models, engine.normalise_name |
| `report.py` / `cli.py` | Markdown and JSON output. `assess`, `demo`, `extract` commands. | all |

## Scoring sequence

```mermaid
sequenceDiagram
    participant C as Case file
    participant E as engine.evaluate
    participant R as Rulebook
    C->>E: answers, facts, documents, as_of
    R->>E: questions, evidence rules, red flags, bands
    loop each question
        E->>E: answer? → evidence status per required type<br/>(missing / expired / stale / name_mismatch / valid)
        E->>E: points = full only if answer is yes AND all evidence valid
    end
    loop each red flag
        E->>E: condition true → hard_stop or cap<br/>condition undecidable (fact missing) → unanswered
    end
    E->>E: decision = NO_GO if hard stop or score < review_min<br/>GO if score ≥ go_min and no caps and nothing unanswered<br/>else REVIEW
    E-->>C: Result + SHA-256 fingerprint
```

## Review state machine

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> submitted: submit
    submitted --> scored: score (engine)
    scored --> in_review: assign reviewer
    in_review --> decided: decide (assigned reviewer only)
    in_review --> draft: request information
    decided --> [*]
    note right of decided
        override needs a reason ≥ 20 chars
        hard-stop flag can never be GO
    end note
```

## Extraction pipeline

```mermaid
flowchart TD
    T[Document text] --> X[extractor.extract]
    X -->|refused| H[[needs_human]]
    X -->|no output / transport error| C{attempts left<br/>and extractor<br/>takes feedback?}
    X -->|data| S{Pydantic schema}
    S -->|invalid| C
    S -->|valid| G{required present?<br/>dates ordered?<br/>holder/ref/issuer<br/>appear in text?}
    G -->|problems| C
    G -->|ok| A[accepted]
    C -->|yes: send problems as feedback| X
    C -->|no| H
```

Every attempt records latency, input and output tokens, and USD cost. `evals/run_evals.py` aggregates these.

## Invariants (each one tested)

1. `evaluate` is deterministic. Equal inputs give equal `Result` and fingerprint.
2. Category weights sum to 100, and each category's question points equal its weight.
3. A `hard_stop` red flag always yields NO_GO, and the workflow refuses GO for it.
4. Nothing reaches `decided` without passing through `scored` and `in_review`.
5. Any modification of a past audit entry makes `verify()` non-empty.
6. An extractor result is `accepted` only when schema, consistency and grounding checks all pass.
