# M20 design: synthetic end-to-end evidence integration

**Status: design only.** This document proposes a bounded integration test across
existing registered workflow capabilities. It does not add a stage, change a
contract, activate a dataset, or assert biological interpretation. The test
must be assembled only from stage kinds, validators, and artifact types already
registered at implementation time.

## Objective and boundary

Exercise a synthetic read-to-evidence chain that joins M4/M6 with M7 recurrence,
M8 nucleotide homology, M9 ORF/optional protein search, M10 exact sequence
architecture, M12 same-workflow artifact review, and M15 evidence-dossier
provenance. The goal is to test typed handoffs, status propagation, artifact
identity, cache/resume behavior, and report completeness—not to identify a
satellite, infer function, or test helper dependence.

Use three small synthetic samples: two independently generated read sets for
the same fixed artificial candidate, enabling exact recurrence, and a negative
control with no candidate reads. Include an unrelated synthetic reference
decoy. A separately seeded truth sidecar records intended sample membership,
candidate sequence, expected recurrence, and planted synthetic ORF coordinates.
Use opaque sample/stage IDs and neutral FASTQ/reference identifiers: case,
factor, positive/negative, and truth-derived labels must not appear in paths,
headers, stage names, workflow inputs, or cache keys. No truth file, truth-derived
label, or expected result enters any analysis stage. Score only after all
permitted stages finish.

## Typed handoffs

The implementation must validate every edge against the live registry and
contract validators; this outline does not authorize weakening or extending
contracts.

1. **M4 → M6:** the registered `fastq_qc` stage consumes declared `raw_read`
   fixtures and emits `qc_fastq` plus `qc_manifest`. `residual_evidence`
   consumes the registered QC outputs, a synthetic technical reference
   (`raw_fasta`), and `reference_roles`. Require complete QC and M6 states
   before scoring. Preserve the M6 candidate sequence set, reconstruction
   evidence, residual-read manifest, and `supported_contigs.fasta` typed as
   `canonical_contig_fasta`.
2. **M6 → M7:** `independent_recurrence` receives its exact declared roles:
   `reconstruction_evidence`, `residual_read_manifest`, and
   `canonical_contig_fasta`. Require the M7 observation, exact-recurrence,
   independence-summary, validation-report, and provenance outputs with their
   existing types. Never pool reads across samples.
3. **M6/M7 → M8:** `m8_homology` requires the typed M6
   `m8_candidate_sequence_set`, a synthetic `m8_reference_snapshot_manifest`,
   and every declared `m8_reference_payload`. Supply all five optional M7
   companions only when their typed outputs validate. A completed no-hit means
   only no match within this synthetic snapshot.
4. **M6/M7/M8 → M9:** `m9_orf_translation` consumes the M6 candidate set and
   only validated optional M7/M8 context. Its ORF results, protein FASTA, and
   ORF bundle remain prediction artifacts. Exercise `m9_blastp` only against
   an explicit synthetic protein snapshot when its dependency is available;
   distinguish unavailable execution from completed no-hit.
5. **M6/M7/M8/M9 → M10:** `m10_exact_first` receives the M6 candidate set and
   supported typed optional contexts. Assert exact architecture/interval
   serialization and provenance only; an ORF or sequence motif is not a
   functional annotation.
6. **M6 → M12 → M15, plus direct typed producers → M15:** M12 accepts only its
   existing `m12_input_manifest` and the M5/M6 artifact types in
   `m12_contracts.PRODUCER_TYPES`. This design has no M5 producer, so M12 reviews
   only supported M6 artifacts from this workflow; it does not rerun producers.
   The current M12 contract does **not** accept M4 QC artifacts or M7–M10
   artifacts. M15 may consume only producer-bound types and producer stage kinds
   in `m15_contracts`; the current allowlist supports the selected M6, M7, M8,
   M9, M10, and M12 outputs. Pass M7–M10 outputs directly to M15 when their
   registered producer bindings validate, rather than routing them through M12.
   M4 QC artifacts are represented through the M6 input lineage and are not
   direct M12/M15 inputs.

## Live contract review

The design was checked against the registered workflow at the base revision.
The following edges are supported only with the listed existing types and
validators:

- M4 QC outputs to M6; M6 reconstruction evidence, residual manifest, and
  canonical contigs to M7.
- M6 candidate set plus all required M8 snapshot/payload inputs to M8; M7's
  five typed context artifacts are optional M8 inputs.
- M6 candidate set plus optional typed M7/M8 context to M9 ORF translation.
  M9 BLASTP is a separate stage requiring M9 ORF/protein outputs and an explicit
  typed synthetic protein reference snapshot/payload.
- M6 candidate set plus the M7–M9 context artifact types declared by M10.
- M6's supported M5/M6 producer types to M12; M6–M10 and M12's declared output
  types to M15, each bound to the registered producing stage kind.

Unsupported connections excluded from this design are M4→M12, M4→M15,
M7–M10→M12, and any M12 claim to validate those unsupported inputs. M12 is not
a general-purpose aggregator. No edge may be added by changing registry
contracts, bypassing validators, or passing untyped filesystem paths.

## Truth, provenance, and expected evidence

- Recompute each fixture's exact deterministic bytes before execution; compare
  source-manifest digests and byte counts. A self-rehashed altered fixture must
  fail. Truth uses a separate seed stream and remains outside the workflow
  input directory and all cache keys.
- Require input descriptors to bind artifact type, producer stage/run identity,
  digest, and path containment. Re-validate typed artifacts at each consumer;
  reject symlinks, path escapes, changed producer manifests, stale outputs, and
  mismatched digests. M7 provenance and M15 envelopes/edges/bundles must bind
  the same producing run, not merely agree on filenames.
- Expected positive evidence is conditional: M6 support for each planted
  candidate, exact M7 recurrence across independent synthetic samples, M8
  searched-snapshot status, M9 ORF hypothesis and optional search status, M10
  deterministic exact-architecture output, then M12/M15 traceability of the
  validated handoffs. Assertions compare these records with held-out truth
  after execution; no stage receives truth for gating or selection.
- Negative controls include a no-candidate sample, an unrelated reference
  decoy, and a truth-label permutation test. The negative must not become a
  positive merely because M8/M9 dependencies are missing or because a stage
  completed with zero rows.

## Missingness and failures

Keep `complete`, `blocked`, `dependency_missing`/`unavailable`, `skipped`,
`interrupted`, `failed`, `invalid_output`, and `not_evaluated` distinctions
where the producer contracts expose them. Never convert an absent artifact,
missing reference snapshot, failed tool, partial manifest, or invalid digest
into a zero-hit or negative biological result. A downstream stage may run only
when its required typed inputs validate; optional context is either entirely
validated or explicitly absent according to that stage's contract. Reports
must identify the failed edge and preserve unaffected upstream evidence.

## Acceptance criteria and resource bounds

- The workflow validates with the unchanged registry and all declared
  artifact types; no permissive dynamic edge or private file-path bypass.
- Same seed and software contracts reproduce fixture digests, semantic
  summaries, and M10 ordering. A changed fixture or producer output invalidates
  the relevant handoff/cache and cannot reuse stale success.
- Positive, negative, unavailable, interrupted, and tampered-artifact fixtures
  produce their expected distinct states. M7 recurrence counts only the
  independently generated positive samples; the negative remains a zero-
  candidate control, not an absence/function claim.
- M12/M15 only attest to provenance and completeness defined by their current
  contracts. Reports include per-stage status, typed lineage, missingness, and
  limitations; truth is never serialized into analysis outputs.
- Limit to three samples, one small candidate/reference per sample, single-end
  reads of at most 100 bases, at most 10x nominal target coverage, one worker,
  2 GiB memory per assembly, and 10 minutes wall time per optional external-tool
  stage. Skip optional-tool assertions explicitly when dependencies are absent.

## Phased implementation plan

The current implementation branch completes Phase 1 only. Phases 2–5 remain
deferred and must not be included in this change.

1. **Freeze the contract map and fixtures.** Record the live registry's input
   and output contracts for every planned edge. Build a fixed-seed fixture
   generator for two independent positive read sets, one no-candidate negative,
   and one unrelated decoy. Use opaque analysis IDs; keep exact expected
   sequences, labels, recurrence, and ORF coordinates in a separate held-out
   sidecar. Test exact generated bytes, manifest digests, label non-leakage,
   and tamper rejection before invoking any stage.
2. **Implement and test the M4→M6→M7 path.** Reuse the existing
   `fastq_qc`, `residual_evidence`, and `independent_recurrence` adapters. Feed
   only contract-declared typed outputs; run M7 across independently generated
   sample observations without pooling read data. Test completed recurrence,
   negative control, missing QC/M6 outputs, interrupted runs, stale manifests,
   changed inputs, and path/symlink escapes.
3. **Add typed M8/M9/M10 consumers.** Reuse the registered M8 homology, M9 ORF
   translation, optional M9 BLASTP, and M10 stages. Validate every artifact
   with its existing contract before constructing the next stage input. Keep
   BLASTN/BLASTP reference snapshots synthetic and digest-bound. Test completed
   no-hit separately from unavailable dependencies, invalid snapshots, and
   failed searches; do not turn any missing search into a negative biological
   result.
4. **Add the supported M12/M15 review path.** Construct M12 input only from its
   accepted M6 artifacts. Construct M15's authenticated producer bindings from
   the accepted M6–M10 and M12 outputs, preserving exact producer run identity,
   artifact digest, edge, and stage-kind checks. Test omitted, mismatched, stale,
   tampered, and cross-run artifacts without relaxing either allowlist.
5. **Complete regression and release checks.** Add focused tests for each
   supported/unsupported edge, truth isolation, negative controls, each
   missingness/failure state, deterministic output, resume/cache invalidation,
   and wall-time/resource bounds. Re-run the full offline suite. Exercise each
   external-tool path when present; when absent, assert an explicit skipped,
   unavailable, or blocked state and verify downstream evidence is not scored
   as a hit/no-hit. Deliver the synthetic fixture manifest, machine-readable
   report, human-readable limitations, and test results; do not change M1–M19
   contracts.

## Phase 1 use

Generate the fixture set in a dedicated output directory:

```sh
python -m satellite_discovery.m20_phase1 --output generated-artifacts/m20-phase1
```

Verify an existing fixture directory with
`satellite_discovery.m20_phase1.verify_fixtures(path)`. The verifier rebuilds
expected bytes from the fixed seed and rejects edited or extra inputs even if
their manifest hashes were recomputed. The sidecar `heldout_truth.json` is kept
outside `inputs/`; do not pass it to a workflow stage.

The machine-readable contract map is
`docs/M20_REGISTERED_CONTRACT_MAP.json`. Regenerate it from the live registry
with:

```sh
python -m satellite_discovery.m20_phase1 \
  --write-contract-map docs/M20_REGISTERED_CONTRACT_MAP.json
```

Focused Phase 1 tests are in `tests/test_m20_phase1.py`.

## Phase 2 use

Run the registered M4 QC → M6 residual-evidence → M7 recurrence workflow on
the frozen three-sample fixtures:

```sh
python -m satellite_discovery.m20_phase2 --output generated-artifacts/m20-phase2
```

The runner validates the fixture bytes before execution and again afterward.
M4/M6 and M7 run as two workflows so the M7 handoff is constructed only from
completed M6 outputs. Every handed-off file must match the M6 producer
inventory digest and declared artifact type. Supported contigs are optional
only when M6 does not report a read-supported assembly. The two workflow
specifications and manifests are under `stages/m4_m6/` and `stages/m7/`;
machine-readable `report.json` and readable `report.md` / `report.html` are
written in the output directory.

Held-out roles and exact-sequence checks are loaded only after M4/M6 and M7
return; they are never included in workflow specifications, stage inputs, or
cache keys. Exact recovery is evaluated only when M6 supplies an available,
digest-verified candidate FASTA. Per-sample run/study identifiers are synthetic
independence metadata declared for M7, not claims about experimental samples.

QC, M6 candidate availability, read-back support, exact recovery, and M7
recurrence states remain separate. Missing or invalid outputs stay unavailable,
failed, or not evaluated rather than becoming zero counts. Optional minimap2
and SPAdes outcomes are reported by the registered stages; do not lower support
thresholds or alter fixtures when a stage cannot complete. A zero-prediction
negative control is not evidence of biological absence. Focused runner tests
are in `tests/test_m20_phase2.py`.

Phase 2 diagnostics are computed after registered execution. They retain the
SPAdes manifest and raw log path/digest, distinguish the assembler's logged
failure from dependency checks, and compare supported contigs to held-out
synthetic truth using strict full-length recovery separately from local
minimap2 alignment measurements. These comparisons never enter stage inputs or
cache keys. Positive samples have separate deterministic read-generation seeds
and distinct fixture digests. In the current fixture, s03 has no eligible
residual reads, so M6 does not expose a validated candidate set and the
negative-control prediction count is unevaluable—not a measured zero.

The current 40-read, 100-nt positive-sample fixture is only a contract test. If
future benchmark work needs an assembler-compatible recovery target, introduce
a separately versioned fixture with independently justified coverage and read
sampling characteristics. Do not alter the Phase 1 fixture bytes, seeds,
thresholds, or digests to force recovery.

## Phase 2B v2 assembler-recovery benchmark

Phase 2B is an opt-in follow-on benchmark. It does not replace or amend the
Phase 1 fixture or the original Phase 2 report. Run it in its own output
directory:

```sh
python -m satellite_discovery.m20_phase2b --output generated-artifacts/m20-phase2b
```

The versioned schema is `m20-phase2b-synthetic-benchmark-v2`. Its frozen
matrix crosses random-start and stratified-start read sampling with 10x and
30x nominal coverage. Each of the four strata has two independently seeded
positive read sets for the same 400-nt artificial candidate. Two additional,
independently seeded negative controls contain separate artificial background
sequences; all cases use independently generated unrelated reference decoys.
Reads are 100 nt. A case has 40 or 120 reads; the resource bound is 120 reads,
one assembly thread, and 2 GiB. The fixed generator seed, per-case seeds,
parameters, byte counts, and SHA-256 digests are recorded in
`benchmark_manifest.json`. The expected role, positive candidate, and pair
labels remain in `heldout_truth.json`, outside `inputs/`.

All ten cases are retained regardless of outcome. The runner executes the
registered M4/M6 workflow, constructs M7 inputs only from digest-verified typed
M6 artifacts, and reports failed/unavailable cases as such. The JSON, Markdown,
and HTML reports give per-case QC and residual eligibility, SPAdes status,
version, configuration, logs and errors, candidate/support state, exact
full-length recovery, alignment breadth/identity/terminal losses and
fragmentation where measurable. Negative controls are marked evaluable only
when M6 supplies a validated candidate set. Pairwise recurrence is evaluated
only when both members have read-supported M6 outputs and M7 completes.
`report.json` also records the Python/platform environment and verifies the
frozen Phase 1 manifest and truth digests against their known values.

This is a synthetic software-recovery benchmark, not an estimate of biological
sensitivity, specificity, absence, or classification. Its matrix is
prespecified; failed seeds must not be discarded, and no M6 thresholds may be
relaxed to improve recovery.

## Scientific limitations

Every sequence and reference is artificial. The test evaluates software
contracts and deterministic accounting only—not biological sensitivity,
specificity, abundance, contamination, taxonomy, circularity, function,
novelty, or independent validation. Repeated synthetic co-occurrence is not
helper dependence. M8 no-hit is limited to the supplied snapshot; M9 ORFs and
protein matches are hypotheses. Passing M20 must not be described as satellite
classification or biological validation.
