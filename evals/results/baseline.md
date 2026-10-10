# Extraction eval — `regex-baseline`

Run 2026-10-10T00:20:38+00:00 on 20 synthetic documents (`evals/dataset.yaml`).

| Metric | Value |
|---|---:|
| **Silent errors** (accepted with a wrong field, or accepted a trap) | **0** |
| Correctly accepted | 8 |
| Correctly routed to a human | 6 |
| Unnecessarily routed to a human | 6 |
| Automation rate (correct accepts / all) | 40% |
| Field accuracy (all fields, all docs) | 69.2% |
| Retries used | 0 |
| Total cost | $0.0000 |
| Median latency per document | 0.0 ms |

| Doc | Style | Expected | Got | Verdict | Wrong fields |
|---|---|---|---|---|---|
| S01 | structured | accepted | accepted | correct_accept | — |
| S02 | structured | accepted | accepted | correct_accept | — |
| S03 | structured | accepted | accepted | correct_accept | — |
| S04 | structured | accepted | accepted | correct_accept | — |
| S05 | structured | accepted | accepted | correct_accept | — |
| S06 | structured | accepted | accepted | correct_accept | — |
| S07 | structured | accepted | accepted | correct_accept | — |
| S08 | structured | accepted | accepted | correct_accept | — |
| P01 | prose | accepted | needs_human | unnecessary_route | holder_name, reference_number, issued_on, expires_on, issuer |
| P02 | prose | accepted | needs_human | unnecessary_route | document_type, holder_name, reference_number, issued_on, expires_on, issuer |
| P03 | prose | accepted | needs_human | unnecessary_route | holder_name, reference_number, issued_on, issuer |
| P04 | prose | accepted | needs_human | unnecessary_route | holder_name, reference_number, issued_on, issuer |
| P05 | prose | accepted | needs_human | unnecessary_route | document_type, holder_name, reference_number, issued_on, expires_on, issuer |
| P06 | prose | accepted | needs_human | unnecessary_route | document_type, holder_name, reference_number, issued_on, issuer |
| T01 | trap-missing-issuer | needs_human | needs_human | correct_route | — |
| T02 | trap-missing-date | needs_human | needs_human | correct_route | holder_name, reference_number, issuer |
| T03 | trap-not-evidence | needs_human | needs_human | correct_route | holder_name |
| T04 | trap-unreadable-date | needs_human | needs_human | correct_route | — |
| T05 | trap-inconsistent-dates | needs_human | needs_human | correct_route | — |
| T06 | trap-missing-holder | needs_human | needs_human | correct_route | reference_number, issued_on, issuer |
