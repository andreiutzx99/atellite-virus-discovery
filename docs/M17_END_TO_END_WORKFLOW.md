# M17 end-to-end synthetic workflow

## Run locally

Install the package, then run:

```sh
satellite-m17 --output /tmp/m17-demo
```

This command generates deterministic artificial inputs and runs the registered
M9 ORF-derivation stage followed by M10 exact-first analysis. It writes
`m17-report.json` and `m17-report.html`, an M4 `stages/workflow.json` execution
manifest, and `inputs/fixture_truth.json`. Re-running against the same output
uses M4's existing validated cache/recovery behavior.

## Supported scenarios and evidence

The generator includes seven artificial RNA/DNA-labelled cases: reference-
compatible-like sequences, residual-review candidates, a junction-like pattern,
an ambiguous-contaminant control, and a short low-information control. Opaque
candidate identifiers are used in pipeline inputs; descriptive scenario labels
are isolated in `fixture_truth.json` and are not passed to M9/M10. Candidate
sequence and source digests are validated using the frozen M8 handoff validator.
An M17-local guard also checks the generated candidate, source manifest,
assembly manifest, and M6-shaped reconstruction fixture for exact synthetic-only
markers and explicit absence of genuine M6 reconstruction, read support, and
independent biological evidence. It runs before M9/M10 dispatch and rejects
hash-consistent provenance edits without changing M8 or any M1-M16 contract.

M9 ORF hypotheses and M10 exact repeat/topology observations are the only
analysis outputs connected in this version. Homology, recurrence, caller-
specific DVG evidence, technical artifact review, helper association, M15
dossier integration, M16 benchmarking, and DNA circularity/SV analysis are
reported as not run, skipped, or unavailable rather than represented by
placeholder results.

`m17-report.json` reports each candidate's M10 branch statuses. It uses
`NO_SIGNAL_WITHIN_TESTED_M10_SCOPE` only if all applicable exact-first branches
completed and reported no evidence rows; this is scoped to M10's tested policy,
not a biological negative. The M4 `stages/workflow.json` is the run manifest
for exact input/output digests, stage versions, configuration, dependencies,
and reproducibility metadata. Its timestamp-bearing execution artifacts are
separate from the deterministic M17 summary report.

## Safety and scientific limits

This is an offline synthetic demonstration. It never calls discovery,
acquisition, FASTQ download, reference retrieval, or real-data processing
paths. No biological reads or reference sequences are embedded or retrieved.
No M1-M16 contract or implementation is changed. RNA-only folding is not
dispatched for DNA. The report is deterministic for the same generated input
and stage implementation, but does not claim biological validity or calibrated
discovery performance.

## Prioritized implementation backlog

1. Add authentic, offline M5/M6 synthetic fixtures that preserve their complete
   caller/read and provenance contracts, then connect those stages to M8.
2. Add explicitly supplied pinned reference snapshots and exercise M8
   homology; keep terms, hashes, no-hit scope, and missing-tool states visible.
3. Connect M7 only with multiple independently declared synthetic source
   datasets and test its source-read independence semantics.
4. Add optional M11 RNA folding with dependency-missing behavior; reject DNA
   inputs before dispatch.
5. Supply authentic typed controls/read-origin evidence for M12 and compatible
   M5 caller evidence for M13; do not infer DVGs from sequence labels.
6. Add matched synthetic observations for M14 and authenticated producer
   references for M15; preserve association vs dependence and correlated
   evidence boundaries.
7. Extend M16 benchmark coverage only after freezing fixture truth, holdouts,
   leakage boundaries and scoring contracts.
8. Design and validate DNA circularity/structural-variant methods and
   benchmarks independently; do not repurpose RNA caller validation.

## Verified integration boundary

The current vertical slice is M8 typed candidate input→M9→M10 through M4's
workflow runner. M1-M16 public contracts remain unchanged. Other registered
stages have typed inputs/outputs but are not treated as a connected discovery
chain until their producer requirements, tools, references and evidence
semantics are satisfied.
