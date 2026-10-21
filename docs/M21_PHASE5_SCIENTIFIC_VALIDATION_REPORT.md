# M21 Phase 5 — scientific validation report

**Scope:** deterministic offline synthetic fixtures only.
**Overall state:** `BLOCKED_FOR_BENCHMARK_EXECUTION`
**Required disclosure:** `SYNTHETIC SOFTWARE VALIDATION — NOT BIOLOGICAL PERFORMANCE EVIDENCE`

## Implemented

- Local FASTA exclusion validation with exact, reverse-complement and bounded local-alignment matching; explicit coverage/identity thresholds; policy and byte-digest binding; per-reference decisions; and fail-closed incomplete states.
- A separate scoring-eligibility record. Pending and unevaluable controls are excluded, controls require independent review, and technical replicates aggregate by biological group.
- A separate deterministic scoring module for sample confusion counts, candidate precision/recall, false candidate burden, read/read-pair denominators, and reasoned `NOT_ESTIMABLE` values.
- A blinded analysis/truth handoff bound by digests and dual-reviewer synthetic unblinding authorization.
- JSON schemas, operational documentation, and adversarial numeric regression tests.

## Interpretation and limitations

These tests validate software behavior, not biological relatedness or discovery performance. Synthetic sequence fixtures are not evidence about real targets. Smith–Waterman scoring uses a documented simple scoring scheme; thresholds require independent scientific approval before any real panel use. Authorization fields in this synthetic interface do not provide cryptographic signatures or custody enforcement. Small fixture sizes do not support inferential confidence intervals. No real sample classification is changed, and no biological execution is authorized.

## Phase 6 recommendation

Before any biological benchmark is considered, independently review the exclusion policy and alignment assumptions, validate blinded custody and cryptographic unblinding controls, define replicate and candidate adjudication with domain reviewers, and approve access and permissions. Keep those actions separate from synthetic software validation.
