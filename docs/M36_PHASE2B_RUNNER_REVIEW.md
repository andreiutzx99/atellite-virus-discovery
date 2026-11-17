# M36 Phase 2B runner implementation review

## Decision

**The runner is not execution-ready, and Phase 2B remains unauthorized.** The
coordinator has stricter manifest, authorization, storage, timeout, and accounting
controls. Those controls have synthetic tests. The 520-row registered matrix was
not executed. Keep it disabled until the remaining blockers are supplied,
integrated, and independently reviewed.

## Implemented controls

- Requires evaluator-manifest schema v2, the exact frozen design digest, a digest
  of condition parameters derived from the scientific preregistration, and a
  frozen seed-role policy.
- Checks all 520 assignment identities, 4/4/4 family splits, the alternative
  assembler block's four development/four held-out families, stable family
  seeds, distinct read seeds across repeats, and identical seeds for paired
  assemblers. It compares actual generated-input byte digests across paired
  assembler runs and checks that repeats do not reuse identical input bytes.
- Requires a canonical Ed25519 approval envelope bound to the exact source
  commit, design, tool identities, evaluator-manifest bytes, synthetic-only
  scope, and frozen resource budget. Production verification loads only the
  root-controlled host trust anchor at
  `/etc/m36-phase2b/approval_signer_ed25519.pem`; no callback or boolean can
  assert authorization.
- Reads the manifest from a provisioned owner-only directory outside the source
  checkout and public outputs. Restricted writes are immutable, owner-only,
  byte-verified, and fsynced; terminal records retain restricted evidence hashes.
- Runs each adapter in a killable process group. The assembler launcher requests
  systemd cgroup-v2 CPU and memory limits, a runtime ceiling, and control-group
  termination. Timeout and cancellation paths stop the unit and verify it is
  inactive before returning.
- Rehashes actual generated input bytes and analyst-facing output bytes. The
  runner checks paired-input identity and records exactly one terminal status
  per registered assignment, including unstarted, interrupted, and failed work.
- The existing M36 contract-smoke workflow still uses only small, unregistered
  synthetic fixtures for SPAdes/Tadpole compatibility and read-support checks.
  Its restricted sidecar and raw-log audit files now live in a temporary
  directory outside the uploaded artifact.

## Fixture-tested controls

| Control | Test evidence | Limitation |
|---|---|---|
| 520-row manifest coverage, split rules, seed roles, condition mapping, and paired reads | Unit tests over synthetic manifest fixtures | No authentic frozen evaluator sidecar is present |
| Ed25519 signature and exact resource scope | Unit test with an ephemeral key | The host-controlled production trust anchor is not provisioned |
| Restricted storage permissions, immutability, traversal rejection, and digests | Unit test with a temporary POSIX directory | No durable host storage mount is configured |
| Non-cooperative worker termination and systemd timeout cleanup | Process-group test plus mocked systemd cleanup test | Does not prove behavior on the production execution host |
| SPAdes/Tadpole and read-support contracts | Existing CI smoke using four unregistered synthetic fixtures | Does not test all registered conditions or execute the matrix |
| Registered 520-attempt matrix | Not run | Explicitly prohibited pending independent review and authorization |

## Remaining blockers

- The authenticated evaluator manifest is not provisioned. The checkout has no
  frozen per-family sequence seeds, read seeds, or family-to-split assignment.
  The private manifest must be created and held outside this repository; its
  values must not be invented or copied into analyst-facing files.
- Some condition details remain unresolved in the preregistration: the exact
  target/background 1:9 generator behavior, the low-complexity sequence recipe,
  and the alternate error-position distribution. The manifest validator marks
  these condition rows blocked instead of guessing.
- No durable owner-only restricted storage volume is provisioned. The file
  store enforces ownership, permissions, atomic immutable writes, and fsync, but
  cannot establish that an arbitrary host path survives host loss.
- No root-controlled Ed25519 trust anchor or approved signer identity is
  installed. The production approval path therefore fails closed.
- The repository still lacks a concrete registered condition-to-M25/SPAdes/
  Tadpole/downstream adapter that consumes the restricted manifest, verifies
  generator placement evidence, preserves frozen M6/M8/M31 behavior, and
  writes raw partial artifacts into the restricted store. The small CI smoke
  adapter is not a substitute for this production contract.
- No M36 execution workflow is added or enabled. The final CI link and exact
  commit are recorded in the PR description after the final-head run.

## Workflow plan (not enabled)

1. Provision the independently frozen evaluator manifest and durable restricted
   store outside the checkout and public artifacts.
2. Install and independently review the root-controlled Ed25519 trust anchor.
3. Complete the exact condition catalog and the condition-specific generator,
   assembly, read-support, and downstream adapters. Validate their source and
   tool identities.
4. Add a separately reviewed, manually dispatched protected workflow that
   checks the exact signed commit, design, tools, manifest, and resource budget.
5. Publish only validated analyst-facing output. Keep mappings, truth, raw logs,
   and partial restricted evidence in the protected store.
6. Stop at pre-execution review. Separate explicit approval is required before
   any registered synthetic execution or held-out unblinding.

## Safety state

- Registered matrix: `NOT_RUN`.
- Phase 2B authorization: `false`.
- Held-out comparison/unblinding: `LOCKED`.
- Biological sequencing data: not used.
- Frozen M6/M8/M31 behavior and M34/M35 results: unchanged.
- Pipeline promotion, PR merge, and M37: not performed.
