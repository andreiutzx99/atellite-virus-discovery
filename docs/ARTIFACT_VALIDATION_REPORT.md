# Development report after PR #6

Historical report: its component-availability statements describe the project at that report's baseline and are superseded for assembly by the current [registered assembly stage guide](ASSEMBLY.md). Its earlier test and runtime evidence remains a record of that milestone.

Baseline: `99e997c`, 182 tests. This change adds general software validation and supplied-artifact accounting. It preserves prior QC and does not run any requested virus screen. Artificial assembly is a standalone diagnostic and is not connected to discovery processing.

| Component | Implementation status | Tested? | Scientific validation? | Remaining limitation |
|---|---|---|---|---|
| Acquisition fallback | Trusted-provider contract now supports 0–2 retries per provider, deterministic order, prior attempt history, UTC times, elapsed time and verification | Transient retries, alternative success, permanent integrity stop, interruption, invalid config | No | No production remote alternative registered. Providers must enforce time/byte limits; synchronous callbacks cannot be forcibly stopped by this contract. History is caller-persisted; reused artifacts require verification again. |
| Tadpole | Pinned standalone artificial single/paired diagnostic; bounded process/log output; command, runtime hash, heap/thread limits, report and verified reuse | Actual Windows Java17 / BBTools40.01 execution for both layouts; failure tests; optional Linux CI | Artificial reconstruction only | Fixed generated fixtures only; no arbitrary-read assembler or discovery adapter. Failed/interrupted diagnostic requires a fresh folder. Output polling is not a hard filesystem quota; direct child termination only. |
| SPAdes | Existing version/dependency probe | Missing locally; no runtime success claimed | No | Needs compatible external runtime and separate artificial-only diagnostic. No automatic substitution or equivalence claim. |
| Reference management | Immutable supplied snapshots now include snapshot ID, reference ID, display name, category, accession/version, source, retrieval time, digest, bytes, database version, provenance and supplied update status | Metadata preservation, duplicate ID rejection, status validation, change comparison; prior integrity tests retained | No curation/completeness claim | Category/provenance/update status are assertions. Older manifests receive explicit defaults. One record describes a supplied file; no per-sequence record extraction or curated biological panels. |
| Generic benchmark | New evaluator over supplied file SHA256 observation tables, menu23, CLI and workflow stage | Positive digest, absent digest, explicit zero-output dataset, malformed/duplicate/missing inputs, failed processing, corruption and resume | No | File-digest equality only. Does not verify underlying files or prove upstream withholding; no sequence similarity, rank or discovery sensitivity. |
| Negative controls | Produced/classified/unclassified counts; exact-digest recurrence and negative-dataset counts | Artificial text-digest positives/negatives, duplicate occurrences counted once per dataset | No | Supplied labels only. No biological false-positive denominator. Existing coverage/contamination reports remain separate supplied-evidence stages. |
| Automatic handoff | New benchmark participates in existing allowlisted artifact workflow with manifests/reproducibility and verified reuse | Workflow execution/reuse tested | No | Does not add reads → subtract known material → residual assembly → candidate classification. |
| Scientific discovery | Existing unsupported boundary retained | Not run | Not validated | No viral/helper-dependent reconstruction, DVG discrimination, functional characterization, autonomous follow-up or candidate prioritization. |

## Answers to the nine readiness questions

1. **Routine acquisition:** primary acquisition and explicit local archive conversion remain available; automatic production remote fallback is **not ready**. The tested callback contract is not a deployed provider registry.
2. **Executable assembly:** **yes for the fixed Tadpole artificial diagnostic**, both read layouts. SPAdes is not validated. This is not an arbitrary-input assembly pipeline.
3. **References:** supplied-file snapshot management is operational. Comprehensive or scientifically appropriate reference collections are not supplied or certified.
4. **Known positives:** artificial positive/negative digest cases are represented and executed, alongside exact artificial assembly reconstruction. No blinded biological known-positive recovery experiment was performed. The evaluator explicitly reports withholding as `not_verified`.
5. **Negative controls:** supplied-artifact accounting is executable, including explicit completed datasets with zero artifacts. A failed dataset cannot be interpreted as negative.
6. **Automatic reads-to-unclassified processing:** remains incomplete. Existing acquisition/QC and supplied-artifact review exist; this change connects only the evaluator to the artifact workflow. There is no new mapping/filtering/assembly discovery chain.
7. **Before scientific detection evaluation:** independently justified truth sets, curation, controls, external runtimes, biological evaluation design and authorized scientific review are still necessary. Software fixture success cannot establish biological performance.
8. **Unsupported:** targeted novel viral/helper-dependent element recovery, reference panels tailored to that discovery, residual-read reconstruction, DVG discrimination, compatibility/function inference, novel-candidate ranking and cross-dataset exploratory screens remain outside this implementation.
9. **Feasible work still missing:** **yes**. Production neutral acquisition-provider integration, SPAdes artificial diagnostics, stronger process-tree quotas, per-record reference import, and an independently verifiable upstream blinding harness are not delivered. These must not be represented as completed by the narrower changes here. Some require external runtimes or a separate domain-neutral scope; no additional step in the implemented subset requires user action.

## Remaining-chain audit

Codes: A = implemented and software-tested; B = implementation exists but scientific validation is absent; C = external dependency/evidence; D = permitted software work not delivered; E = outside supported discovery scope.

| Step | Code | Actual extent |
|---|---|---|
| Read acquisition/QC | A/B/C | Existing path; prior QC preserved; optional converter runtime |
| Production remote fallback | D | Contract tested, production registration absent |
| Remove known material for novel-element discovery | E | Not implemented |
| Assemble residual biological reads | E | Artificial Tadpole diagnostic is separate A; SPAdes diagnostic is C/D |
| Compare supplied artifacts/references | A/B/C | Existing comparison/import; curated truth and optional tools external |
| Distinguish artifacts/DVGs | E | Supplied descriptive evidence is not a discriminator |
| Cross-dataset supplied recurrence | A/B | Digest/control counts and existing observation reports; no causal inference |
| Characterize and prioritize novel candidates | E | Not implemented |
| Reference per-record import / verifiable blinding | D | File-level metadata and evaluator do not implement these |

## Use the evaluator

`python -m satellite_discovery.artifact_benchmark --datasets datasets.csv --expectations expectations.csv --artifacts artifacts.csv --output new-report`

CSV contracts (headers required even for zero observations):

- `datasets.csv`: `dataset_id,role,processing_status,reference_version`; unique IDs, role positive/negative/unspecified, status complete.
- `expectations.csv`: `benchmark_id,artifact_sha256`; unique benchmark IDs and lowercase 64-character digests. At least one expectation.
- `artifacts.csv`: `dataset_id,artifact_id,artifact_sha256,classification`; unique artifact ID within each known dataset, classification classified/unclassified. Zero rows allowed.

Workflow kind `artifact_benchmark` takes inputs `datasets`, `expectations`, `artifacts`. It supports the existing earlier-stage-artifact syntax only when those stages actually produce the required schema. It does not infer conversions between unrelated table formats.

Reports include comparisons, counts, recurrence, runtime, caveats and lifecycle provenance. Missing optional reference metadata is recorded as unknown; default reference ID/name is the filename and default category is the supplied role. Snapshot IDs default to the specification digest; all updates require new output folders.

## Evidence

Real Windows results are recorded in `validation/tadpole-artificial.json`. The pinned runtime was downloaded afresh and its 3,528 runtime files verified. Single: 724 reads; paired: 1,288 reads; each produced one exact 1,000-base contig (allowing reverse complement), and saved output reuse passed. Artificial failure injection covers timeout, interruption, byte-budget exception and empty assembler output. Existing bounded-process tests exercise actual timeout termination and byte limits.

The optional Linux CI job runs `python scripts/check_tadpole_ci.py`, which downloads the pinned 33 MB archive, checks SHA256/path/size bounds, and executes both layouts plus reuse. This is opt-in diagnostic tooling, not a general runtime installer. Offline Windows/Linux CI continues to run without downloading an assembler.

Local verification: 196 tests passed (three optional-tool skips), installed-distribution smoke checks and the example workflow/reuse completed. CI results are attached to the pull request; real Linux Tadpole execution is checked by the optional job.
