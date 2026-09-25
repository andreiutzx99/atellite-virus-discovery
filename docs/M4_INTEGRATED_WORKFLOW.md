# M4 — Integrated artifact workflow

**Status: IMPLEMENTED.** M4 connects selected typed artifact stages. It is not
an autonomous biological discovery chain. See the [README](../README.md) and
[roadmap](ROADMAP.md).

## 1. Purpose

Connect compatible, explicitly declared software stages through typed
artifacts, recorded provenance, preflight checks, and human-/machine-readable
reports.

## 2. Why this milestone exists

Independent tools need compatible handoffs and consistent run identity.
Workflow wiring should not make absent, incomplete, or incompatible evidence
look like a successful negative result.

## 3. Implemented functionality

M4 provides typed stage handoffs, supplied-reference BLAST comparison,
occurrence/context summaries, preflight, verified reuse, workflow provenance,
and consolidated reporting for supported artifact workflows.

## 4. Inputs

The workflow accepts a declared allowlisted stage graph, validated stage
configuration, and supplied artifacts such as reads, reference files, and
context/observation tables. It does not accept arbitrary shell commands.

## 5. Outputs

Outputs are stage-specific typed artifacts, reports, and run manifests that
record the selected workflow and its declared inputs.

## 6. External tools and dependencies

BLAST+ and other optional tools are external dependencies. Stages requiring an
unavailable tool report that dependency state rather than claiming a
comparison was performed.

## 7. Evidence produced

Tests support compatibility checks, stage execution/handoff, report
generation, preflight, failure handling, and reuse. Results are scoped to the
provided artifacts and configured comparison.

## 8. Provenance and reuse

The workflow records configuration, declared input/output identities, stage
status, and relevant tool information. Reuse validates the recorded identity
and artifacts before accepting previous outputs.

## 9. Failure and dependency semantics

Invalid handoffs, missing inputs/tools, failed stages, and integrity
discrepancies remain visible. A workflow does not replace missing data with
zero evidence or silently certify stale outputs.

## 10. Interpretation

A successful M4 report summarizes operations on supplied artifacts. BLAST
hits and no-hits apply only to the supplied reference set and recorded
settings. Descriptive context and occurrence tables are not causal analyses.

## 11. Limitations

M4 connects modular analysis but does not automatically curate references,
generate all scientific evidence, or enforce a complete end-to-end discovery
protocol. User-supplied labels and context are not independently verified.

## 12. What M4 does not establish

It does not establish reference completeness, novelty, sample identity,
taxonomy, host/helper relationships, causal association, biological
significance, or discovery performance.

## 13. Relevant tests and records

See [conditional-tool contracts](CONDITIONAL_TOOLS.md),
[artifact validation report](ARTIFACT_VALIDATION_REPORT.md), the
[test suite](../tests/), and the [M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md).

## 14. Relevant literature

The supplied-reference sequence comparison uses BLAST; see
[Altschul et al. (1990)](https://doi.org/10.1016/S0022-2836(05)80360-2).
That method citation does not establish that any user-supplied reference set
is complete or biologically appropriate.

## 15. Relationship to other milestones

M4 orchestrates compatible implemented artifacts; M5 can supply optional
caller-specific DVG evidence, and M6 can consume declared reads/references for
residual triage. These components remain bounded technical stages. M7–M16 are
planned in the [roadmap](ROADMAP.md).