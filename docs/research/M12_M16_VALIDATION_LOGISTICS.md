# M12–M16 validation logistics and platform matrix

**Status: future validation protocol only; reviewed 27 September 2026.** No
candidate data, biological sequence payload, DVG tool installation, or
benchmark holdout assignment is part of this report. See the
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md) for source-data limits,
license notes, and tool provenance.

The current [roadmap](../ROADMAP.md) is authoritative: M1–M11 are implemented
as scoped software milestones; M12–M16 remain planned and not implemented.
This historical validation plan does not change the roadmap or existing
research; any M11-specific status is superseded by the current M11 contract and
implementation documentation.

## 1. M12 offline and source-data validation plan

### Offline artifact path

An M12 baseline can operate on retained M5/M6 artifacts without reacquiring
FASTQ, if it calls itself an artifact review and preserves the original stage
scope. Its tests should use generated fixtures and cover:

- Valid and invalid artifact hashes; M5/M6 manifest and source-input identity;
  correct SAM read accounting and declared reference dictionary.
- M6 single-end and paired-end layouts, primary/unmapped/secondary records,
  mate identity, residual partition, read-back records, and same-read reuse.
- M5 native event parsing, completion/read-count accounting, completed zero,
  missing caller, malformed output, and incomplete/interrupted output.
- Missing FASTQ, SAM/BAM/CRAM, controls, sample metadata, and references as
  distinct missing or unavailable conditions rather than negative findings.
- Partial reference/metadata scope, conflicting signals, control inadequacy,
  failed dependencies, interruption, output truncation, and deterministic
  serialization.

The current M6 persistent SAMs and FASTQ partitions can be summarized only
within the M6 reference, mapper, and configuration recorded in their verified
manifest. Existing M6 read-back uses reads eligible for assembly. A full
read-origin workflow, new mapping, control comparison, pre-QC review, or
source-attribution statement waits for separately authorized source files and
metadata. Unsupported BAM/CRAM readers are optional design work, not a reason
to reject a candidate or block the offline artifact path.

### Source-data readiness checklist

Before any real-data M12 execution, record:

1. Data owner, purpose, access approval, source terms, privacy/consent scope,
   permitted fields, retention/deletion policy, and whether controlled data may
   be used in local analysis or CI.
2. Exact original/clean FASTQ or SAM/BAM/CRAM provenance, checksum, sample/run
   identity, read layout, QC history, reference identity, aligner/version,
   settings, and completion/accounting evidence.
3. Matched control role and processing relationship: negative/positive/mock
   status, extraction/library batch, lane, index/barcode, protocol/kit/lot,
   instrument, run, and any relevant UMI/read-group metadata.
4. Scope-specific reference/decoy/control manifests, record-level rights,
   version, accession, sequence hashes, exclusions, and any unavailable role.
5. Analysis plan and claim boundary before results are interpreted. Missing or
   non-matched controls are `UNKNOWN`/unavailable, not a clean result.

## 2. M13 comparator-manifest and provenance logistics

Comparator construction and classification-rule design must be kept separate.
The manifest records what an item is believed to represent and why; it does
not itself decide how M13 should classify a future candidate.

### Required manifest fields

Each item should carry stable IDs and, where available:

- Source type and immutable reference: accession.version, SRA run/BioProject,
  article/supplement identifier, repository commit, or controlled local
  artifact ID. Preserve provider release, retrieval date, query/filter, and
  exact source/sequence/read hashes. This is a metadata specification only;
  no accession payload was retrieved here.
- Candidate/comparator role as a curator statement, not an inferred taxonomy:
  deletion DVG; copy-back DVG; snap-back DVG where applicable; recombination-
  derived DVG; ordinary full-length or fragmented virus; host, microbial,
  mobile-element, vector, reagent, or other candidate-like technical
  alternative; unresolved/ambiguous.
- Label tier and rationale: directly demonstrated, supported by independent
  orthogonal evidence, publication-curated, computationally inferred, or
  unresolved. Keep event structure labels separate from interference,
  helper-dependence, replication, and function claims.
- Evidence source and method: experimental assay and controls, read support,
  source publication, reference scope, caller/version, coordinates and
  orientation, known limitations, and whether the comparator was used to
  develop/evaluate any reviewed tool.
- Sequence/read scope: molecule, parent/helper reference, coordinates,
  orientation, termini/boundaries, completeness, read layout, available
  denominators, and source linkage, with sensitive fields excluded or access
  controlled.
- Rights and provenance: source terms, redistribution/access status,
  attribution, privacy/consent constraints, curator, review date, source
  hashes, transformation policy, and normalized-record hashes.
- Relationship and split metadata: exact/near-duplicate and family/clade
  relationships, source study/lab/sample relationships, inclusion/exclusion
  rationale, and a separate development/tuning/holdout assignment maintained
  by the benchmark custodian.

Represent ordinary viral fragments and candidate-like false positives as
distinct comparator classes; a fragment is not a DVG-negative simply because
it lacks a known junction. Keep synthetic fixtures separate from empirical
truth. Do not infer that a read, event, publication label, or tool output is
ground truth without recording its supporting evidence and label strength.

### Public provenance leads, not approved truth set

These examples are useful leads for a later curated manifest. They are not
selected as holdouts, downloaded, or approved for redistribution:

| Lead | What the source reports | Limit and leakage/rights note |
| --- | --- | --- |
| Mumps-virus copy-back reads, SRA runs `SRR8719995`–`SRR8719998` | The DVGfinder paper reports a set of 28 5′ copy-back genomes supported by DVG-specific RT-PCR in the described public sample group; see the [paper and table](https://doi.org/10.3390/v14051114). | The same paper evaluates DVGfinder on these examples, so they are not an independent DVGfinder holdout. Recheck each run/sample mapping, truth record, terms, and study relationships before any future use. No SRA payload was retrieved. |
| RSV reference `KC731482.1` and VODKA2 artificial copy-back reads | The VODKA2 README identifies an RSV reference file and explicitly labels its associated FASTQ test reads as simulated/artificial copy-back data; see [repository](https://github.com/lopezlab-washu/VODKA2). | Useful for software-fixture provenance only, not an empirical positive or biological performance estimate. Repository has no declared license; do not bundle its files. |
| Flock House virus project `SRP013296` | The current ViReMa README identifies a small FHV read example as originating from this SRA project; see [ViReMa repository](https://github.com/andrewrouth/ViReMa). | A tool demonstration is not a DVG truth label or independent comparator. Check the exact sample/run, source terms, and prior tool exposure before use. No read payload was retrieved. |
| Measles-virus copy-back/snap-back examples in the DI-tector paper | The publication reports computational detection and follow-up validation examples, including 5′/3′ copy-back or snap-back structures; see [DI-tector paper](https://doi.org/10.1261/rna.066910.118). | A paper citation is not yet an accession-level read manifest. Resolve exact source records, rights, and label evidence before curating an item. The currently visible author repository does not provide the program source. |

The published set’s prior exposure should be retained in the manifest even when
it is useful for method development. Never use it as a blinded confirmatory
holdout for a tool or rule already evaluated against it.

## 3. M14 observational units and claim boundaries

| Unit | Appropriate role | Denominator and dependence rule |
| --- | --- | --- |
| Read or read pair | Technical support within one library/run. | Count fragments, not mates, as the unit for paired evidence; reads from one library are not independent biological replicates. |
| Sequencing run/library | Technical observation and run-level detection. | Record total eligible/evaluable reads or fragments and detection method/limit. Re-sequencing or lane splits from one library do not create new samples. |
| Sample/specimen | Primary observational unit when sample identity and ascertainment are defined. | Keep candidate/helper present, not detected within scope, or unknown, with tested denominator and matched detection methods. Separate technical replicates and biological replicates. |
| Experiment / independent extraction | Unit for a controlled preparation or intervention when its design supports it. | Document source specimen, extraction, library preparation, treatment, batch, and replicate relationship. Independent libraries from one specimen are not automatically independent specimens. |
| Study / laboratory / publication | Cluster or stratum for repeated samples and study-level generalization. | Preserve all member sample IDs and study/lab links. Do not count multiple samples from one study as independent evidence of cross-study replication. |

For co-occurrence, report explicit `candidate × helper × evaluable unit`
records, detection methods and limits, matched controls, missingness, and
denominators. “Not detected” is a scoped observation only when that unit was
tested by a defined method; an absent database row is not a negative.

For sparse public data, begin with stratified counts and the four-cell
denominator where available. Show raw cell counts and uncertainty. A Fisher
exact or conditional association summary is meaningful only when its sampling
frame and all cells are defined. Use study-stratified/hierarchical or
cluster-robust approaches only when independent clusters, covariates, and
sample size justify them; otherwise state that evidence is insufficient.
Account for repeated measures, study selection, multiple testing, uneven depth,
and ascertainment. Candidate/helper read counts are not biological abundance
without an assay and normalization model that addresses library depth and
compositionality.

| Claim | Public observational evidence can support | Additional requirement |
| --- | --- | --- |
| Co-occurrence | Named candidate/helper detections in evaluated samples/runs, with denominators, method sensitivity, controls, and missingness. | Does not establish same-cell presence, interaction, or causal helper role. |
| Association | A specified statistical association across matched, adequately sampled units and a declared model. | Confounding, sampling bias, repeated studies, and uncertainty must be addressed. |
| Recurrence with a helper | Repeated co-observation across declared units/studies, with independence evidence and source provenance. | Repeated runs/samples from one source are not independent replication by default. |
| Abundance correlation | Covariation under a declared measurement, normalization, detection limit, and study-level model. | Relative read counts alone do not establish absolute abundance, interaction, or dependence. |
| Possible dependence | A hypothesis motivated by observations or sequence/context evidence. | Must remain explicitly hypothetical without claim-appropriate intervention evidence. |
| Demonstrated dependence | Not established by public co-occurrence, recurrence, homology, or computational prediction alone. | A controlled helper omission/perturbation and appropriate rescue/complementation or equivalent biological evidence, with measured replication/encapsidation/movement phenotype as relevant. |

M7’s declared sample/run/study identifiers can be linked but are not external
verification of independence. M14’s experimental result, if supplied, should
remain a separate typed record from any observational association.

## 4. M15 integration contract logistics

M15 should first be a provenance-linked descriptive dossier and evidence matrix.
Preserve each upstream record, its original schema/version and artifact digest,
method, scope, limitations, and dependencies. Do not rerun an upstream analysis
or create multiple “votes” from the same underlying read, event, or reference.

At minimum, preserve separate axes for:

- positive evidence reported;
- completed scoped no-match/no-signal;
- missing/not supplied;
- not applicable or not selected;
- dependency unavailable;
- failed;
- interrupted;
- incomplete or truncated;
- invalid/corrupt input or artifact;
- conflicting observations and unresolved interpretation.

These are semantic categories, not a mandate to rename existing milestone
enums. Keep method completion/accounting, applicability, evidence observation,
and interpretation as separate typed fields. Preserve partial positive rows
when another branch fails. Missing, unavailable, or not-applicable is never
rewritten as a completed negative.

The cross-stage interface should carry immutable candidate/observation IDs,
artifact IDs and hashes, producer stage/schema, original status axes, method
and parameters, consumed input/reference snapshot identity, source terms/access
class where relevant, and dependency links. Use explicit absence for an
optional stage not supplied. M15 may group/filter/display and show support,
conflict, gaps, or unresolved alternatives; it should not assign a biological
winner or a default numerical score.

Any later prioritization must name a non-biological decision objective, declare
correlated evidence and missingness handling, expose uncertainty/sensitivity,
and be validated against independent data before use. It is an optional branch,
not a prerequisite for a descriptive dossier.

## 5. M16 benchmark, leakage, custody, and blinding

### Truth and comparator tiers

Version labels independently by claim: sequence/family identity, DVG event
structure, satellite/subviral role, helper relationship, source/artifact, and
functional/interference/dependence evidence. Distinguish direct experimental
support, orthogonal corroboration, publication-curated annotation,
computational-only evidence, disputed labels, and unknown. A known family
member is not automatically experimentally functional; a DVG is not
automatically interfering; unknown or disputed cases are not forced into the
negative denominator.

Maintain distinct benchmark subsets for:

- known positives for each claim, with supporting evidence;
- biological comparators, including ordinary viral fragments/full genomes,
  host/organelle/microbial and mobile-element alternatives;
- DVG structure groups (deletion, copy-back, snap-back where applicable,
  recombination-derived) and their parent/reference context;
- hard negatives and technical alternatives, including adapter/vector/reagent
  sequence, host carryover, chimeras, assembly artifacts, and candidate-like
  fragments;
- ambiguous/unresolved cases for abstention and coverage analysis;
- generated synthetic fixtures for parser, status, and controlled mechanism
  tests only.

### Split and evaluation controls

Before tuning or performance evaluation, curate and hash a versioned manifest
with source/accession, sequence/read hashes where permitted, label evidence and
confidence, relationships/derivation, terms, curation history, inclusion and
exclusion reasons, and prior use by tools/papers. Deduplicate exact sequences
and identify relatedness before splitting. Keep dependent items together at the
highest relevant level: family/clade or close homolog, parent genome, source
study, sample/donor, laboratory, extraction/library, run, and accession as
appropriate to the question.

Keep development, tuning/validation, and final holdout sets separate. A
custodian who did not choose thresholds or curate borderline cases should
control final labels and holdout access where practical. Blind candidate IDs
and truth labels during execution/review when feasible. Freeze software,
parameters, reference/model snapshots, interpretation rules, required branches,
metrics, strata, confidence intervals, and stop criteria before unblinding.
Any post-unblinding method or threshold change requires a new independent
holdout for confirmatory claims. Do not split reads from one specimen/library
across partitions.

Report confusion counts and class denominators only for adjudicated labels.
Report per-class metrics, coverage, and missing/not-applicable/failed/
interrupted/incomplete/truncated rates separately. Uncertainty must reflect the
independent unit (for example, family or study), not millions of correlated
reads. If no suitable truth set exists, report software/fixture validation and
protocol readiness, not sensitivity, specificity, calibration, or accuracy.
Do not assign actual holdouts in this audit.

Experimental validation remains a separate output with claim-specific assays
and controls: source confirmation may require independent extraction/library or
targeted assays; helper dependence needs perturbation and rescue; DVG
interference needs a measured phenotype; topology/function claims require
appropriate orthogonal assays. Benchmark performance is not confirmation of
any individual candidate.

## 6. Platform and CI matrix

The current project requires Python 3.11 or later. Its
[GitHub Actions workflow](../../.github/workflows/tests.yml) runs the base
suite on Ubuntu and Windows with Python 3.11 and 3.12, plus a separate Ubuntu
optional-tools job. This is the project’s existing baseline, not evidence that
each external DVG caller works on every matrix entry.

| Tool/branch | Linux x86-64 | Windows native | Python 3.11 | Python 3.12 | GitHub Actions recommendation | Offline synthetic fixture feasibility |
| --- | --- | --- | --- | --- | --- | --- |
| Existing M5 ViReMa adapter | Explicitly supported only for the project’s pinned Linux x86-64 path; source and Bowtie hashes checked. | Not supported by the current adapter. | Project runtime supports 3.11; full pinned caller compatibility must be verified rather than inferred. | Project runtime supports 3.12; full pinned caller compatibility must be verified rather than inferred. | Keep optional/Linux-only; base CI can test parser/status with fixtures. Do not upgrade or bundle as part of this audit. | High for parser/accounting and missing-tool behavior; caller-specific runtime fixture only in a separately authorized pinned environment. |
| DI-tector | Publication describes a Python script, but current source/runtime/platform recipe is unavailable; unverified. | Unverified. | Unverified. | Unverified. | Defer provisioning; no required or optional job until code, version, and terms are resolved. | High for future adapter mechanics using generated reads; cannot validate the unavailable caller itself. |
| VODKA2 | Bash/Perl, Bowtie2, BLAST, and R make Linux/container the plausible target; not tested here. | No Windows-native path documented; WSL/container would be a separate external setup. | Not a Python runtime dependency. | Not a Python runtime dependency. | Optional, isolated Linux job only after rights and exact container/tool pins are resolved; never required baseline CI. | High for independent wrapper/parser fixtures; repo demo payload must not be reused until terms are cleared. |
| DVGfinder | Linux/Conda is plausible from the Unix setup and pinned environment; not tested here. | No Windows-native support documented. | Its environment pins Python 3.9.12 and older dependencies; 3.11 compatibility unestablished. | 3.12 compatibility unestablished. | Defer CI provisioning pending license review, version pin, and compatibility work; do not treat its combined output as independent votes. | High for manifest, parser, and wrapper state tests; caller/model behavior requires licensed pinned resources. |
| M12/M14/M15/M16 baseline harness | Supported through standard project workflow and generated fixtures. | Supported by current base test matrix where the code is platform-neutral. | Supported by current project matrix. | Supported by current project matrix. | Required CI should remain offline, deterministic, and free of private/biological payloads. Keep optional native tools in separate jobs. | High for accounting, missingness, sparse observations, state preservation, leakage checks, and deterministic reports. |

### Provisioning recommendation

- **Required CI:** synthetic artifact/contract tests only; no external DVG tool,
  biological reference database, private read, sample metadata, or benchmark
  truth payload is a required dependency.
- **Optional-tools CI:** after exact source/license approval, provision a
  selected tool in an isolated Linux job from immutable release/commit and
  dependency pins. Run synthetic data only; surface unavailable/failed states.
- **Linux-only validation:** use for the current ViReMa adapter and any
  approved Linux-oriented caller until native Windows support is independently
  tested.
- **Externally provisioned:** keep large native dependency stacks or controlled
  data in an explicitly maintained environment/container. Record image digest,
  source/binary hashes, OS and architecture, runtime, and licenses.
- **Deferred:** DI-tector until current executable/terms exist; VODKA2 and
  DVGfinder until their code/data/dependency terms and exact compatible pins
  are resolved. No tool installation or CI modification is authorized here.

## 7. Sources and local records checked

- [Current roadmap](../ROADMAP.md), [M5](../M5_DVG_EVIDENCE.md),
  [M6](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md), [M7](../M7_INDEPENDENT_RECURRENCE.md),
  [M8](../M8_REFERENCE_AND_HOMOLOGY_SPEC.md), [M9](../M9_CONTRACT_FREEZE.md),
  and [M10](../M10_CONTRACT_FREEZE.md).
- [M12 contract](../M12_CONTRACT_FREEZE.md),
  [M12 implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md),
  [M12 semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md),
  [M13 research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md),
  [M14 research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md),
  [M15 research](M15_EVIDENCE_INTEGRATION_DESIGN_RESEARCH.md),
  [M16 research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md), and
  [resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md).
- Current tool repositories, paper records, and public example references are
  linked at their points of use above. No sequence file or holdout was
  retrieved.
