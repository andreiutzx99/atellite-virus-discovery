# M36 Phase 2A preparation and validation

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
- Checks required SHA-256 evidence, exact tools, all assignment statuses,
  one-vCPU enforcement evidence, and design-only governance.

## Known gate states

The generator, blinded-sidecar, leakage, registry, and synthetic crosswalk
checks can be exercised with synthetic fixtures. Exact SPAdes identity remains
environment-dependent; Tadpole must also pass its pinned archive/runtime
verification. Current adapters pass thread and memory arguments but do not
provide hard OS CPU quotas, so the 26 CPU-hour estimate remains conditional
until an enforcement mechanism is evidenced or the budget is recalculated.
The readiness checker fails closed when tool digests, all 520 attempt-status
records, hashes, or resource-limit evidence are missing.

## Command

`python scripts/m36_phase2a_readiness.py` prints the current preparation
readiness and blockers. `--evidence PATH` supplies the evaluator's complete
readiness evidence; `--audit-one-to-nine` additionally checks the exact ratio
with a small synthetic fixture. Exit status 2 means one or more readiness gates
remain blocked. Neither option executes the registered matrix.
