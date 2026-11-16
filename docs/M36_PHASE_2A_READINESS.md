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
- Uses an isolated GitHub Actions synthetic-smoke job to request a Linux
  cgroup-v2 `CPUQuota=100%`, `MemoryMax=4 GiB`, and `TasksMax=512` for each
  SPAdes/Tadpole single- or paired-read compatibility attempt. The smoke checks
  the kernel-reported limits and verifies a child process remains in the same
  cgroup. Its retained report binds the evidence to the exact Actions run and
  source commit.
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
checks can be exercised with synthetic fixtures. The new Actions job must
actually pass before its tool and cgroup evidence can count; local availability
or thread settings alone do not prove a hard CPU cap. With 520 attempts capped
at 180 seconds and four concurrent attempts, the preregistered execution
window is 6.5 hours, plus 0.75 hours each for setup/teardown and validation,
fitting the 8-hour budget exactly. This is a capacity calculation, not a
measured runtime guarantee.

If the intended runner cannot provide verifiable cgroup enforcement, a
separate review proposal is to run one attempt at a time on a verified
two-vCPU runner, preserve the 180-second attempt timeout, 4 GiB memory and
400 MB output ceilings, disable automatic retries, and increase the total
window to 28 hours (26 attempt-hours plus the 1.5-hour reserve, rounded up).
This changes concurrency and the wall-time budget and must not replace the
frozen design without independent approval.

Pre-execution readiness requires the full planned/blocked assignment roster;
terminal outcomes and raw-output hashes belong only to the separate
post-execution validator. The checker fails closed when installed tool
identities, actual evidence-file digests, source/design binding, compatibility
smoke evidence, or resource-limit evidence are absent. The CI report marks the
registered matrix `NOT_RUN`; it does not authorize Phase 2B.

## Command

`python scripts/m36_phase2a_readiness.py` prints the current pre-execution
readiness and blockers. `--evidence PATH` supplies the evaluator's evidence
manifest; `--audit-one-to-nine` additionally checks the exact ratio with a
small synthetic fixture. `--output PATH` writes the canonical JSON report,
including the complete assignment roster and current environment provenance.
The `m36-phase2a-contract-smoke` Actions job retains the four bounded synthetic
assembler smokes and the full readiness report as the
`m36-phase2a-contract-smoke` artifact.
Exit status 2 means one or more readiness gates remain blocked. The separate
post-execution validator accepts only a complete terminal roster with
evidence digests. Neither command executes the registered matrix.
