# M36 Phase 2B runner implementation review

## Decision

**Runner implementation is not yet execution-ready.** The coordinator is
implemented as a gated interface and has synthetic dry-run tests. No registered
assignment was executed. Do not enable or invoke matrix execution until every
blocker below is resolved and independently reviewed.

## Implemented controls

- Expands and validates the frozen 520-row registry and rejects altered family
  seeds, split assignments, paired-read seed mismatches, or reused technical
  repeat seeds.
- Requires a verifier for a scoped approval bound to the source commit, design,
  tool inventory, and evaluator-manifest digests.
- Caps concurrency at four; fixes the per-attempt timeout at 180 seconds, the
  execution window at 6.5 hours, the aggregate slot budget at 26 hours, and the
  total workflow budget at eight hours. Queued work is not retried.
- Provides a systemd transient-service launcher with a one-vCPU quota, 4 GiB
  memory ceiling, runtime cap, and in-cgroup resource proof before the assembler
  starts. Child processes inherit the service cgroup.
- Separates analyst-facing files from owner-only evaluator/raw evidence,
  checks analyst-visible files for label leakage, and records opaque-ID
  accounting plus content digests.
- Exposes a dry-run scheduler that accepts at most four injected fixtures and
  cannot run the registered 520-row matrix.

## Workflow plan (not enabled)

1. Provision the authenticated evaluator manifest and a durable owner-only
   evidence location outside the repository and CI artifact directory.
2. Add a separately reviewed signature-verification implementation and a
   condition-specific generator/assembler/downstream adapter.
3. Add a manually dispatched, protected workflow that checks the exact approved
   commit and design/tool/manifest digests before calling the runner.
4. Upload only the validated analyst-facing package; keep evaluator mappings
   and raw restricted evidence in the separate protected location.
5. Stop at pre-execution review. A separate explicit approval is required
   before any scientific execution or held-out unblinding.

## Remaining blockers

- The checkout contains no evaluator sidecar or frozen per-assignment seeds,
  split mapping, and decoded condition parameters. The design refers to these
  values but does not include them. The runner will not invent replacements.
- No owner-only durable restricted-evidence location is configured. The current
  coordinator refuses a restricted path inside the source checkout or public
  artifact directory.
- No trusted authorization key/verifier is configured. A caller-provided
  boolean is intentionally insufficient.
- The condition-specific M25 generation, SPAdes/Tadpole adapters, downstream
  handoff, and stage-by-stage truth/support validation are not yet wired into
  the coordinator. The adapter contract requires bounded tool calls and
  separate public/restricted outputs.
- No M36 execution workflow is added or enabled. Existing CI remains
  preparation/dry-run validation only.

## Safety state

- Registered matrix: `NOT_RUN`.
- Phase 2B authorization: `false`.
- Held-out comparison/unblinding: `LOCKED`.
- Biological data, M6/M8 settings, M31 thresholds, and M34/M35 results:
  unchanged.
