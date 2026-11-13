# M36 Phase 2A pre-execution readiness and post-execution validation

Phase 2A implements preparation gates only. It does not execute the 520
registered assembly attempts, enable an Actions workflow, run downstream
screening, or authorize Phase 2B. The preregistered matrix and scientific
endpoints remain unchanged.

## Implemented checks

- Expands the JSON registry and verifies the full 520-assignment denominator.
- Runs a bounded M25 synthetic fixture to compare same-seed bytes, validate the
  placement ledger against read bytes, measure realized error counts and target
  coverage, inspect sequence complexity, and prove the target-absent fixture
  has no target-derived reads.
- Tests the exact 1:9 target/background read-count ratio. The arm remains
  blocked unless this independent check passes.
- Creates opaque evaluator case tokens and an owner-only sidecar; scans analyst
  paths, FASTQ headers, manifests, stage IDs, and logs for truth/factor leakage.
- Stores raw evidence bytes separately and unchanged in an owner-only tree.
- Inspects registered SPAdes and Tadpole provenance without invoking assembly.
- Validates the truth → generated-read → contig → support chain as separate
  outcomes. Downstream handoff is not inferred from support.
- Recomputes SHA-256 for manifest-listed evidence files and binds the design
  digest and source commit to the current checkout. Tool provenance must match
  the installed tool report exactly.
- Emits all 520 registered assignments as `PLANNED` or `BLOCKED` with reasons.
  Pre-execution readiness never requires terminal results or raw execution
  evidence and never fabricates completed attempts.
- Keeps terminal status/evidence-digest validation in a separate
  post-execution validator.
- Verifies read-placement CIGAR operations against the actual synthetic read
  and contig sequences before reporting read support. Assembly, read support,
  and downstream handoff remain separate outcomes.

## Known gate states

The generator, blinded-sidecar, leakage, registry, and synthetic crosswalk
checks can be exercised with synthetic fixtures. Exact SPAdes identity remains
environment-dependent; Tadpole must also pass its pinned archive/runtime
verification. Current adapters pass thread and memory arguments but do not
provide hard OS CPU quotas, so the 26 CPU-hour estimate remains conditional
until an enforcement mechanism is evidenced or a revised bounded budget is
reviewed. Pre-execution readiness requires the full planned/blocked assignment
roster; terminal outcomes and raw-output hashes belong only to the separate
post-execution validator. The checker fails closed when installed tool
identities, actual evidence-file digests, source/design binding, compatibility
smoke evidence, or resource-limit evidence are absent. The current draft does
not authorize Phase 2B.

## Command

`python scripts/m36_phase2a_readiness.py` prints the current pre-execution
readiness and blockers. `--evidence PATH` supplies the evaluator's evidence
manifest; `--audit-one-to-nine` additionally checks the exact ratio with a
small synthetic fixture. `--output PATH` writes the canonical JSON report,
including the complete assignment roster and current environment provenance.
Exit status 2 means one or more readiness gates remain blocked. The separate
post-execution validator accepts only a complete terminal roster with
evidence digests. Neither command executes the registered matrix.
