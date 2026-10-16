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

Use three small synthetic samples: a positive with a fixed artificial candidate,
a second independently generated positive for exact recurrence, and a negative
control with no candidate reads. Include an unrelated synthetic reference
decoy. A separately seeded truth sidecar records intended sample membership,
candidate sequence, expected recurrence, and planted synthetic ORF coordinates.
No truth file, truth-derived label, or expected result enters any analysis
stage. Score only after all permitted stages finish.

## Typed handoffs

The implementation must validate every edge against the live registry and
contract validators; this outline does not authorize weakening or extending
contracts.

1. **M4 → M6:** `fastq_qc` consumes declared `raw_read` fixtures and emits its
   existing QC artifacts. `residual_evidence` consumes the typed QC handoff,
   synthetic technical reference (`raw_fasta`), and `reference_roles`. Require
   complete QC and M6 states before scoring. Preserve the M6 candidate sequence
   set, reconstruction evidence, residual-read manifest, and canonical contigs.
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
6. **M4–M10 → M12 → M15:** M12 is built from its existing
   `m12_input_manifest` and supported milestone-typed artifacts from the same
   workflow; it reviews handoffs and does not rerun producers. M15 consumes only
   the input types and producer bundles accepted by the live `m15_contracts`
   allowlist, then validates its input manifest, edge list, result bundle, and
   output digests. Where a direct M12→M15 or producer→M15 edge is not accepted
   by those contracts, omit it and record the unsupported edge as out of scope.

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

## Scientific limitations

Every sequence and reference is artificial. The test evaluates software
contracts and deterministic accounting only—not biological sensitivity,
specificity, abundance, contamination, taxonomy, circularity, function,
novelty, or independent validation. Repeated synthetic co-occurrence is not
helper dependence. M8 no-hit is limited to the supplied snapshot; M9 ORFs and
protein matches are hypotheses. Passing M20 must not be described as satellite
classification or biological validation.
