# M21 Phase 7 — readiness report (draft)

**Overall:** `INCOMPLETE` — the canonical synthetic transition adapters and
27-case adversarial suite are implemented, but this draft does not contain a
verified independently retained checkpoint set or signed matrix-attestation
evidence for a complete readiness report. The new CI job attests its matrix
results with the run identity as predicate; a signed reviewer matrix must still
bind the completed run and attestation bundle. No biological benchmark is
authorized.

| Area | Status | Evidence / limitation |
|---|---|---|
| Multi-artifact inventory and exclusion | PASS for covered synthetic cases | Validates signed inventory, actual bytes, all files, cross-file IDs, shared resource limits, and per-artifact results. |
| Aggregate scientific approval | PASS for covered synthetic case | Approval binding includes snapshot, inventory, policy, aggregate evidence, exact review, and approval-set digests. |
| Independent custody interface | PASS for covered synthetic cases | Compares retained checkpoints with local event prefixes, authenticates checkpoint rotation, permits a valid uncheckpointed suffix, and rejects missing history, rollback, and reordered checkpoints. External source independence remains a caller responsibility. |
| Canonical transition adapters | PASS for the complete synthetic fixture | All five adapters use existing Phase 4–6 validators, bind common snapshot/upstream digests, recompute scoring, and ignore caller callbacks. |
| Multiple qualified controls | PASS for synthetic regression | Separately signed positive, negative, and excluded controls cover blinded inputs, replicate grouping, eligibility, and negative-read denominators. |
| Adversarial suite | PASS locally for 27 named cases | Every named test independently asserts fail-closed behavior. CI emits an exact run statement and verifies its GitHub artifact attestation; reviewers must sign the run-bound matrix before readiness can consume it. |
| Reports and schemas | PASS for covered schema checks | Draft 2020-12 schemas include typed stage evidence, CI-run identity, and the adversarial matrix contract; local valid/invalid-instance tests are included. |
| Biological execution authorization | BLOCKED | Fixed state remains `BLOCKED_FOR_BENCHMARK_EXECUTION`. |

No real sequences, FASTQ/FASTA datasets, credentials, or truth keys were used.
Phase 5 scoring definitions and M1–M20 interfaces are unchanged. Biological
execution remains blocked even if the synthetic readiness report later reaches
`PASS`.

GitHub's attestation proves the run statement was produced by the named
repository workflow for its recorded source context. It does not prove
third-party retention, correctness of GitHub-hosted infrastructure, or
biological validity. The Python readiness verifier checks the reviewer-signed
attestation digest but does not fetch GitHub data or verify Sigstore bundles.

## Recommended Phase 8 scope

After Phase 7 reaches `PASS`, evaluate a reproducible synthetic-only rerun
against independently retained checkpoints and pinned artifact inventories.
Keep biological execution blocked until a separate, authenticated governance
decision addresses scientific validity and data access.
