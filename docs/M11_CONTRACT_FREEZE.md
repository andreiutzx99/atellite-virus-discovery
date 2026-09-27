# M11 implementation contract freeze

**Contract status: APPROVED FOR SYNTHETIC/OFFLINE BASELINE IMPLEMENTATION.**
**Milestone status: PLANNED / NOT IMPLEMENTED.** M11 remains planned until its
implementation is merged and the current [roadmap](ROADMAP.md) is updated by
the project’s normal process. This contract authorizes implementation only of
the software baseline below; it does not claim biological performance or
authorize biological data access.

Normative **MUST**, **MUST NOT**, **SHOULD**, and **MAY** specify the baseline
software behavior. The
[M11 blocker-resolution report](research/M11_BLOCKER_RESOLUTION.md) is
authoritative for the decisions it resolves. This freeze carries those
decisions into an implementation-grade contract. If a future change conflicts
with that report, revise and review the contract explicitly rather than
silently changing behavior.

## 1. Scope, ownership, and boundaries

M11 is an optional evidence stage. Its required synthetic/offline baseline
creates a deterministic RNA analytical view from an eligible candidate and
reports one single-sequence ViennaRNA minimum-free-energy (MFE) fold for each
selected whole-candidate or explicitly declared region.

### Required core

- Validate the M6-produced candidate handoff and preserve immutable candidate
  identity and provenance.
- Apply the approved RNA/DNA, IUPAC, case-normalization, and explicit DNA
  `T`-to-RNA `U` view policy.
- Fold the exact supplied orientation and requested whole sequence or explicit
  contiguous region.
- Run ViennaRNA 2.7.2 MFE under the frozen profile in §5.
- Emit typed structure evidence, complete input/run accounting, integrity
  hashes, and deterministic artifacts.
- Keep all M11 execution, failure, and cache identity stage-scoped.
- Validate the software with the synthetic/offline acceptance suite in §10.

### Optional or deferred

| Classification | Scope |
| --- | --- |
| Optional; not required for core completion | ViennaRNA partition-function/ensemble evidence or any additional ViennaRNA output. It MUST use a separately named method/profile and MUST NOT affect core MFE completion when unselected. |
| Deferred; separate approval and contract required | Infernal/Rfam searches, dedicated ribozyme detectors, comparative/covariation analyses, alternative folding engines, biological significance thresholds, biological candidate searches, and experimental validation. |

M11 MUST NOT retrieve a biological database, search candidate data, infer
unknown molecule type, or make an upstream M1–M10 result a folding eligibility
gate. An unavailable or unselected optional branch is not negative evidence.
M11 MUST NOT modify or invalidate M6–M10 artifacts or semantics. An M11-only
change MUST NOT invalidate an otherwise-valid M6–M10 result.

## 2. Canonical input and upstream handoff

### 2.1 Accepted candidate artifact

The canonical input is the validated M6-produced
`m8_candidate_sequence_set` (`m8-candidate-sequence-set-v1`) and its paired
FASTA when sequence bytes are available, as defined by the
[candidate handoff contract](../satellite_discovery/m8_candidate_handoff.py)
and carried forward by the [M10 contract](M10_CONTRACT_FREEZE.md).

Before folding, M11 MUST validate:

- the handoff manifest and schema/version;
- producer-declared `candidate_id`, `sequence_id`, and FASTA record identity;
- exact sequence bytes, source SHA-256 digest, and length;
- source-artifact IDs/hashes and their binding to the handoff;
- the assembly manifest and M6 reconstruction evidence required by the
  handoff; and
- declared molecule type and supplied completeness/boundary metadata.

Sequence identity covers the exact source letters, not FASTA line wrapping.
M11 MUST retain every distinct producer-declared candidate identity, including
byte-identical sequences. Identical analytical views MAY share an internal
fold computation only if every candidate still receives its own source-linked
accounting and evidence record.

M7–M10 artifacts MAY be linked as separately typed context if a future approved
workflow needs them, but the core MFE branch MUST NOT consume or be gated by
them. Their presence or absence MUST NOT change the baseline fold view or MFE
result.

### 2.2 Input accounting

Each run manifest MUST list every requested candidate/region fold key exactly
once and retain its final branch status. It MUST record expected and accounted
fold counts. No candidate or request may disappear because it is invalid,
unavailable, over a cap, or not started.

Use the upstream input-status meanings:

| `input_status` | Meaning |
| --- | --- |
| `INPUT_VALID` | Candidate identity, provenance, source bytes, digest, and accepted input alphabet validate. |
| `INPUT_INVALID` | Identity, manifest, digest, alphabet, empty sequence, or region request is invalid. |
| `SEQUENCE_UNAVAILABLE` | A valid candidate identity exists, but the source sequence bytes are unavailable. |
| `COMPLETE_EMPTY_INPUT_SET` | The validated handoff contains no candidates; there are no candidate branches and no candidate-level no-result. |

An empty validated candidate set is a completed accounting state, not a fold
result. If M11 was selected, the run may have `aggregate_status=COMPLETE` with
`input_status=COMPLETE_EMPTY_INPUT_SET` and zero expected/accounted candidate
folds. If M11 was not selected, its stage and aggregate status are
`NOT_SELECTED`; do not represent non-selection as an empty completed run.

## 3. Immutable source and RNA analytical view

### 3.1 Validation, alphabet, and status precedence

M11 accepts the same case-insensitive IUPAC nucleotide symbols as M10 for
source validation only:

`A C G T U R Y S W K M B D H V N`

All other symbols—including gaps, embedded whitespace, punctuation, and
non-ASCII lookalikes—are `INPUT_INVALID`. M11 MUST NOT strip or repair them.
Apply validation in this order:

1. Validate candidate identity and provenance; failure is `INPUT_INVALID`.
2. If identity is valid but sequence bytes are missing, use
   `SEQUENCE_UNAVAILABLE`.
3. Validate source symbols, nonempty sequence, and region coordinates; failure
   is `INPUT_INVALID`.
4. Resolve the declared molecule type and observed `T`/`U` consistency; an
   unknown or conflicting type is `INSUFFICIENT_INFORMATION`.
5. Apply the folding alphabet; valid ambiguity symbols are `NOT_APPLICABLE`.

Thus invalid source data are not masked by unknown molecule type, and a valid
ambiguous sequence with unknown molecule type is `INSUFFICIENT_INFORMATION`,
not `NOT_APPLICABLE`.

### 3.2 Fold eligibility and transformations

| Declared molecule type and source symbols | Fold applicability and analytical view |
| --- | --- |
| RNA; only `A C G U` (ASCII case-insensitive) | Applicable. Map ASCII lowercase to uppercase in a derived view and fold it. |
| DNA; only `A C G T` (ASCII case-insensitive) | Applicable. Map ASCII lowercase to uppercase and explicitly convert each `T` to `U` in a derived RNA view. |
| Valid IUPAC ambiguity symbol present | `NOT_APPLICABLE` for MFE. Preserve the candidate; do not expand ambiguity codes or treat this state as negative evidence. |
| Molecule type unknown or undeclared | `INSUFFICIENT_INFORMATION`; never infer type from composition. |
| Declared DNA containing `U`, or declared RNA containing `T` | `INSUFFICIENT_INFORMATION`; preserve the declaration and source symbols without conversion. |

The source sequence, source digest, candidate identifiers, and source artifacts
are immutable. Uppercasing ASCII lowercase and the explicit DNA `T`-to-`U`
conversion occur only in a separately identified analytical view. For a view
with bytes `view_bytes`, compute:

`SHA-256("M11-RNA-VIEW-v1" + NUL + view_bytes)`

The label is ASCII and `NUL` is one zero byte. The view bytes are the uppercase
ASCII RNA letters. Each view record MUST include source candidate/sequence
identities and digest, source length, transformation and policy version, view
digest and length, molecule-type declaration, and a one-to-one coordinate map.
The source digest MUST remain the upstream digest and MUST NOT be replaced by
the view digest.

A foldable input MUST be nonempty. A one-nucleotide candidate or region is
eligible; no biological minimum length applies. An empty sequence is
`INPUT_INVALID`, not a completed no-result. A valid ambiguous candidate remains
valid upstream even though this MFE method is `NOT_APPLICABLE`.

## 4. Orientation, regions, and coordinates

The default request is the complete supplied source sequence in its
producer-declared orientation. The fold record MUST use orientation
`AS_SUPPLIED`. M11 MUST NOT reverse-complement, rotate, circularize, join,
trim, or create automatic windows. Sequence-topology signals from M10 do not
establish physical circularity and MUST NOT alter the M11 view.

A request MAY select exactly one explicitly declared contiguous region
`[start,end)` of a candidate, where coordinates are zero-based and half-open on
the original source sequence. It MUST satisfy:

`0 <= start < end <= source_length`

An invalid, empty, or out-of-range region is `INPUT_INVALID`. The view is
derived from exactly that slice. The source coordinate map is the identity
offset for the selected interval; derived positions `[0,end-start)` map to
source positions `[start,end)`. No implicit padding, flank extension, or
wraparound is allowed. A region is not a new candidate. The source
completeness/boundary declaration MUST be retained; folding a partial supplied
fragment does not assert that missing flanks are absent.

## 5. ViennaRNA MFE execution contract

### 5.1 Exact implementation and profile

The required distribution is the official ViennaRNA Python interface
(`RNAlib`, imported as `RNA`), release **2.7.2**. The baseline MUST use the
single-sequence Python API call sequence:

1. Create `RNA.md()` model details.
2. Set `temperature = 37.0` and `dangles = 2` explicitly.
3. Create `RNA.fold_compound(view_sequence, model_details)`.
4. Call `fold_compound.mfe()` once for that fold request.

The profile is `M11-VIENNARNA-MFE-TURNER2004-T37-DANGLES2-v1`. It uses the
built-in Turner 2004 parameter set, 37.0 °C, dangling-end setting 2, an
unconstrained linear RNA input, and MFE only. Partition-function mode, custom
constraints, custom parameter files, circular-RNA mode, DNA mode, alternate
temperatures, and engine substitution are not part of this profile.

All other model options MUST remain at the exact 2.7.2 `RNA.md()` defaults.
Their resolved effective values MUST be serialized in the evidence record; a
record that says only “defaults” is insufficient. The method/profile ID,
parameter object, and contract/profile versions are part of cache identity.

### 5.2 Engine result validation and output values

The `mfe()` return is the source result: dot-bracket structure and energy. The
adapter MUST validate that:

- the structure length equals the RNA view length;
- the structure contains only `.`, `(`, and `)` and has balanced parentheses;
- the energy is finite; and
- the API call and normalized record complete without an execution or integrity
  error.

The normalized record MUST store `mfe_structure_dot_bracket` and
`mfe_energy_kcal_mol` as a locale-independent decimal string with exactly two
fractional digits. Normalize negative zero to `0.00`. Preserve the raw API
return in a deterministic provenance envelope containing the returned
dot-bracket string and the energy's IEEE-754 hexadecimal representation. Hash
that envelope as `raw_engine_result_sha256`. This Python API produces no raw
stdout file; M11 MUST NOT invent one. If a future adapter actually emits raw
output, preserve and hash that actual artifact separately.

A completed evidence record MUST contain at least:

- candidate, sequence, handoff, source-artifact, and source-sequence digest
  identities;
- source length, molecule type, supplied completeness/boundary state, selected
  source region, `AS_SUPPLIED` orientation, and coordinate map;
- view transformation/policy, digest, length, and sequence identity;
- method/profile ID, ViennaRNA interface/release, exact package/wheel digest,
  native-library/build identity, Python implementation/version/ABI, operating
  system, and architecture;
- complete effective model details and finite resource configuration;
- validated dot-bracket structure and MFE energy with units;
- raw API result-envelope hash, normalized evidence hash, and artifact links;
- branch status, evidence status, reason/limitations, and schema/contract
  identities.

The structure is a model-dependent predicted secondary structure. The energy
is an optimum under the named model; it is not a probability, confidence score,
or significance statistic.

### 5.3 Resource limits, timeouts, and caps

Every run MUST declare finite positive limits for all of the following:

| Configuration | Meaning |
| --- | --- |
| `max_fold_symbols` | Maximum symbols in one complete candidate or declared region. |
| `max_folds_per_run` | Maximum candidate/region fold requests in one run. |
| `timeout_seconds_per_fold` | Maximum wall time for one MFE call. |
| `memory_bytes_per_fold` | Maximum memory available to one MFE call. |

These are engineering protections, not biological cutoffs. Deployment profiles
MAY select different values, but a run MUST provide effective values and
enforcement policy; missing, non-finite, non-positive, or unenforceable limits
MUST fail preflight rather than silently falling back to an unbounded run.
Record the normalized effective values and configuration version in every run
and bind them in cache identity.

An input exceeding `max_fold_symbols` or a request not started because
`max_folds_per_run` was reached is `TRUNCATED`. Preserve the full source and
requested interval; never fold a prefix, truncate the view, or silently split a
region. A timeout, process termination, or memory-limit kill is `INTERRUPTED`.
Preserve completed sibling fold records and account for every request. Neither
state is a completed prediction or a negative result. A run may not use
wall-clock completion order as a deterministic enumeration or output-order
rule.

## 6. Typed status axes and aggregate semantics

Each candidate/region result MUST retain separate fields for `input_status`,
`applicability_status`, `execution_status`, `evidence_status`, and
`branch_status`. A value on one axis MUST NOT overwrite another. Use the exact
branch vocabulary below, in addition to the separate axes.

### 6.1 MFE branch status

| `branch_status` | Meaning |
| --- | --- |
| `PREDICTION_REPORTED` | A valid, applicable, complete MFE call and parsed structure/energy are preserved. |
| `INPUT_INVALID` | Candidate identity/provenance, source alphabet, empty input, or region request failed validation. |
| `SEQUENCE_UNAVAILABLE` | Candidate identity is valid, but source sequence bytes are unavailable. |
| `INSUFFICIENT_INFORMATION` | Molecule type is unknown, undeclared, or inconsistent with observed `T`/`U`. |
| `NOT_APPLICABLE` | Input is valid but MFE policy does not apply, including valid ambiguity codes. |
| `NOT_SELECTED` | M11 or a separately optional branch was not selected. |
| `DEPENDENCY_UNAVAILABLE` | The selected ViennaRNA 2.7.2 runtime/build is unavailable. |
| `EXECUTION_FAILED` | The selected engine failed without a complete result. |
| `OUTPUT_INVALID` | Engine return, parser result, or saved artifact is malformed or fails integrity validation. |
| `INTERRUPTED` | Execution stopped before the fold completed, including timeout or resource kill. |
| `TRUNCATED` | A configured input-size or per-run fold-count cap prevented the requested fold. |
| `NOT_STARTED` | Selected work has not begun; not a result. |
| `RUNNING` | Selected work is in progress; not a result. |

`input_status` uses `INPUT_VALID`, `INPUT_INVALID`, `SEQUENCE_UNAVAILABLE`, or
run-level `COMPLETE_EMPTY_INPUT_SET` as appropriate. `applicability_status` is
one of `APPLICABLE`, `INSUFFICIENT_INFORMATION`, `NOT_APPLICABLE`, or
`NOT_EVALUATED`. `execution_status` records `NOT_STARTED`, `RUNNING`,
`COMPLETED`, `DEPENDENCY_UNAVAILABLE`, `EXECUTION_FAILED`, `OUTPUT_INVALID`,
`INTERRUPTED`, or `TRUNCATED`. `evidence_status` is `EVIDENCE_FOUND` only when
a valid prediction record exists; otherwise use `NO_EVIDENCE_REPORTED`.
`NO_EVIDENCE_REPORTED` is not a negative result.

Examples of the axis mapping:

| Condition | Input | Applicability | Execution | Evidence | Branch |
| --- | --- | --- | --- | --- | --- |
| Successful eligible fold | `INPUT_VALID` | `APPLICABLE` | `COMPLETED` | `EVIDENCE_FOUND` | `PREDICTION_REPORTED` |
| Valid ambiguous RNA | `INPUT_VALID` | `NOT_APPLICABLE` | `NOT_STARTED` | `NO_EVIDENCE_REPORTED` | `NOT_APPLICABLE` |
| Unknown/conflicting type | `INPUT_VALID` | `INSUFFICIENT_INFORMATION` | `NOT_STARTED` | `NO_EVIDENCE_REPORTED` | `INSUFFICIENT_INFORMATION` |
| Invalid source or region | `INPUT_INVALID` | `NOT_EVALUATED` | `NOT_STARTED` | `NO_EVIDENCE_REPORTED` | `INPUT_INVALID` |
| Missing source bytes | `SEQUENCE_UNAVAILABLE` | `NOT_EVALUATED` | `NOT_STARTED` | `NO_EVIDENCE_REPORTED` | `SEQUENCE_UNAVAILABLE` |
| Tool missing | `INPUT_VALID` | `APPLICABLE` | `DEPENDENCY_UNAVAILABLE` | `NO_EVIDENCE_REPORTED` | `DEPENDENCY_UNAVAILABLE` |
| Interrupted or over cap | `INPUT_VALID` | `APPLICABLE` | `INTERRUPTED` or `TRUNCATED` | `NO_EVIDENCE_REPORTED` | matching branch status |

There is no completed MFE “no match” state. A valid, applicable, nonempty
sequence that completes an MFE call reports a structure. Never emit
`COMPLETED_NO_MATCH`, a no-fold result, or negative evidence for missing
structure, unavailable dependencies, failure, interruption, truncation, or
malformed output.

### 6.2 Aggregate and lifecycle status

`aggregate_status` is:

- `COMPLETE` when the selected M11 run has valid input accounting and every
  required fold request is accounted; for a nonempty set every required MFE
  branch MUST be `PREDICTION_REPORTED`;
- `PARTIAL` when any required candidate/request is invalid, unavailable,
  inapplicable, insufficient, failed, output-invalid, interrupted, or
  truncated, while retaining any independent completed prediction; or
- `NOT_SELECTED` when M11 itself was not selected.

An empty validated candidate set may be `COMPLETE` only with
`input_status=COMPLETE_EMPTY_INPUT_SET` and an explicit zero-fold accounting
record; it is not a candidate-level fold or no-result. An unselected optional
branch does not make core M11 partial. `NOT_STARTED` and `RUNNING` are lifecycle
states, not completed aggregate outcomes.

## 7. Evidence artifacts and integrity

The M11 result bundle MUST contain a verified run manifest, one input/
accounting record per candidate, one branch record per requested candidate/
region, and one typed `RNA_STRUCTURE_EVIDENCE` record for each reported fold.
The manifest MUST provide schema and contract versions, stage/method/profile
identity, implementation identity, normalized configuration, expected and
accounted request counts, effective limits, aggregate status, artifact
references, and hashes.

The typed structure evidence MUST preserve the fields in §5.2 and link to the
exact source candidate, validated handoff, analytic view, selected region,
raw API result envelope, and normalized result. Invalid, inapplicable, missing,
failed, and incomplete requests still receive their accounting record and
reason; they do not receive fabricated structure evidence.

Hash each persisted artifact with SHA-256 and bind its path/role/hash/size in
the manifest. On load or cache reuse, verify the manifest identity, schema
compatibility, all required files, and all hashes. A missing or corrupt output
is `OUTPUT_INVALID`; the workflow MUST safely recompute or report a visible
failure. It MUST NOT convert corruption to `NOT_APPLICABLE`, no-result, or
negative evidence.

Completed fold outputs may be reused only when their full stage identity and
all output hashes verify. Failed, interrupted, unavailable, truncated, or
output-invalid attempts are not reusable predictions. A later retry is a new
execution attempt; it does not rewrite or erase the prior attempt's provenance.

## 8. Deterministic serialization, ordering, and cache identity

### 8.1 Serialization and ordering

Serialize normalized records as UTF-8 JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- non-ASCII text encoded as UTF-8;
- explicit `null` for non-applicable optional fields;
- no NaN or infinity; and
- exactly one final LF.

Represent energy as the fixed decimal string in §5.2 and preserve its raw API
value separately in hexadecimal form. Stable record IDs MUST derive from the
stage identity and record key; timestamps, random values, filesystem traversal
order, process identifiers, and thread completion order MUST NOT affect
normalized artifacts.

Sort candidate records by `candidate_id`, then `sequence_id`; within each
candidate sort by source-region start, source-region end, and method/profile ID.
For identical sort keys, use the deterministic input-manifest ordinal as the
final tie-breaker. Preserve distinct producer candidate IDs even when source
sequence bytes are identical.

For fixed source identity, region, ViennaRNA 2.7.2 build, platform, and
normalized configuration, successful reruns MUST produce byte-identical
normalized records and hashes. The acceptance test compares both a fresh
rerun and a verified cache hit.

### 8.2 Stage-scoped cache identity

The M11 cache identity MUST bind, at minimum:

- candidate ID, sequence ID, handoff/manifest identity, source-artifact
  identities/hashes, exact source digest/length, declared molecule type, and
  source completeness/boundary metadata;
- exact selected region coordinates and bytes, `AS_SUPPLIED` orientation,
  derived-view bytes/digest, normalization policy, and transformation version;
- selected method and profile IDs, every effective model parameter, and all
  effective resource limits;
- ViennaRNA release, exact installed wheel/artifact hash, native build,
  Python/runtime/platform identity;
- M11 implementation/stage identity, parser/adapter identity, schema version,
  contract semantics, and normalized configuration; and
- any optional input actually validated, consumed, or passed through by a
  separately approved branch.

Basic MFE does not consume M7–M10 artifacts; their contents MUST NOT enter the
M11 cache identity. An M11-only implementation, input, configuration,
parser, schema, or semantic change invalidates M11 only. Shared validator or
workflow-cache semantic changes follow the existing
[stage-identity policy](PRE_M9_STAGE_IDENTITY_AUDIT.md). Never use a
package-wide source hash as a substitute for M11's stage-scoped identity.

## 9. Provisioning and CI

Initial supported provisioning targets are official ViennaRNA 2.7.2 Python
wheels for CPython 3.11 and 3.12 on Linux x86-64 and Windows x86-64. The
implementation dependency lock MUST pin exact per-platform wheel filenames
and SHA-256 digests. The run record MUST retain the installed artifact and
native build identity. A missing or unverified compatible dependency is
`DEPENDENCY_UNAVAILABLE`; there is no engine fallback.

Do not vendor the wheel or bundle/redistribute ViennaRNA binaries in the
application. Provision the pinned official package as an environment
dependency, retain applicable license and attribution notices, and review the
exact artifact terms before distribution. Contact the ViennaRNA authors before
commercial-product release as requested by the published license information.
If the intended distribution cannot meet those terms, do not ship the folding
dependency or silently replace it with another engine. This is a project
posture, not a legal opinion. These terms and implementation/release gates do
not block freezing the software semantics.

CI MUST, after implementation, test dependency installation/import and a
synthetic MFE smoke fold on every supported Python/OS/architecture
combination. It MUST also test the typed `DEPENDENCY_UNAVAILABLE` path without
the package present. Exact wheel hashes, runtime build identities, and actual
CI results belong in the dependency lock and build/test records; none are
invented by this contract.

## 10. Synthetic/offline acceptance matrix

All sequence inputs below are artificial fixture strings. These tests establish
software behavior only, not biological accuracy, predictive performance,
structure in vivo, or function. The successful-fold golden structure and
energy MUST be generated and checked in against the pinned 2.7.2 build during
implementation.

| Fixture | Required result |
| --- | --- |
| Ordinary canonical RNA, e.g. `GCGAAACGC` | `PREDICTION_REPORTED`; structure length equals view length; energy, model profile, source/view provenance, and hashes are present. |
| Declared DNA `ACGT` | Source remains `ACGT`; view is exactly `ACGU`; explicit T→U policy, digest, and one-to-one coordinate map are recorded. |
| Lowercase RNA `acgu` | Source letters remain unchanged; the derived view is `ACGU`. |
| Valid ambiguity `ACGNR`, declared RNA | `NOT_APPLICABLE`; no engine call and no negative evidence. |
| Valid ambiguity with unknown molecule type | `INSUFFICIENT_INFORMATION`, confirming type validation precedes applicability. |
| DNA with `U` or RNA with `T` | `INSUFFICIENT_INFORMATION`; no inferred type or silent conversion. |
| Invalid symbol `ACG-X` | `INPUT_INVALID`; do not strip, repair, or invoke the engine. |
| Empty sequence | `INPUT_INVALID`; no engine call and no completed no-result. |
| Length boundaries | Under test cap `L`, a 1-symbol and exactly `L`-symbol request are eligible; `L+1` is `TRUNCATED` without prefix folding. |
| Run-count cap | Each request beyond `max_folds_per_run` is explicitly accounted as `TRUNCATED`; no request disappears. |
| Declared region | Fold only a valid artificial `[a,b)` slice and map it to original zero-based half-open source coordinates. Invalid/empty/out-of-range regions are `INPUT_INVALID`. |
| Orientation | `AS_SUPPLIED`; assert no reverse complement, rotation, circular wraparound, or automatic window is made. |
| Successful MFE | Match the pinned synthetic golden structure/energy; validate effective parameters, raw API return envelope, normalized output, and hashes. |
| Tool unavailable | `DEPENDENCY_UNAVAILABLE`; no fallback and no no-result. |
| Tool failure | Inject an engine exception/failure; return `EXECUTION_FAILED`, not a negative result. |
| Interruption/resource kill | Inject timeout/termination; return `INTERRUPTED`, retain completed siblings, and do not reuse the incomplete attempt. |
| Malformed output | Inject non-finite/missing energy, malformed/unbalanced/wrong-length dot-bracket, or corrupt artifact; return `OUTPUT_INVALID`. |
| Deterministic rerun/cache | Same input/build/profile/config yields byte-identical canonical records and the same identity. Verified cache hits are unchanged; changing region, profile, resource policy, or build changes identity. Corrupt cache is rejected. |
| Empty validated handoff | `COMPLETE_EMPTY_INPUT_SET`, zero expected/accounted folds, no candidate branch, and no candidate no-result. |
| Optional branch omitted | Branch is `NOT_SELECTED`; core MFE completion is unaffected. |

## 11. End-to-end workflow acceptance

An implementation conforms only if the following all hold:

1. It accepts the validated M6 handoff without changing its bytes, digests,
   provenance, or artifacts; revalidates the identity and sequence binding
   before any fold.
2. It runs only when M11 is explicitly selected and does not make M11 a
   required M1–M10 gate. A missing ViennaRNA runtime leaves upstream outputs
   intact and reports `DEPENDENCY_UNAVAILABLE` for M11.
3. It constructs only the approved canonical RNA analytical views and either
   folds every selected request completely or records its typed non-success
   state; it never silently skips or shortens requests.
4. It emits a manifest with every requested candidate/region and a terminal
   status, typed evidence only for valid completed folds, and verifiable hashes
   for every persisted artifact.
5. A fully successful eligible run is `COMPLETE`; any incomplete required
   branch is `PARTIAL` while retaining valid sibling evidence. No failed or
   incomplete run is represented as a successful no-fold/no-signal result.
6. Repeated execution and verified reuse satisfy §8; an M11-only change leaves
   M6–M10 cache identities and artifacts unchanged.
7. The offline acceptance suite passes without network access, biological
   databases, candidate sequence searches, or empirical performance claims.
8. Reports identify the output as a predicted structure under a specific
   model and parameters, not an observed or biologically confirmed structure.

## 12. Scientific limitations and downstream handoff

Every report and exported evidence record MUST make clear:

- predicted folding is not experimentally demonstrated structure;
- folding is not RNA expression, catalytic activity, or biological function;
- folding is not satellite classification, novelty, or helper dependence;
- the MFE energy is not a calibrated probability or candidate significance
  score; and
- synthetic fixtures validate software behavior, not biological performance.

Ordinary single-sequence secondary-structure prediction omits cellular context,
co-transcriptional effects, many pseudoknots, tertiary interactions, and
alternative conformations. A partial supplied candidate remains a prediction
for that supplied fragment only. A fold cannot establish circularity or repair
uncertain candidate boundaries.

M15 MAY link M11 predictions as one typed evidence dimension while retaining
their limitations, provenance, and missingness. M15 MUST NOT turn a fold into
a classification or unapproved score. M16 MAY test software behavior and,
under a separate approved protocol, assess empirical method performance.
Synthetic acceptance results MUST remain distinct from biological validation
and experimental results; no M16 result is implied by this contract.

## 13. Governing records and references

- [Current roadmap](ROADMAP.md)
- [M11 blocker-resolution report](research/M11_BLOCKER_RESOLUTION.md)
- [M11 pre-contract readiness review](research/M11_PRECONTRACT_READINESS.md)
- [M11 RNA-structure design research](research/M11_RNA_STRUCTURE_DESIGN_RESEARCH.md)
- [M10 contract freeze](M10_CONTRACT_FREEZE.md)
- [M9 contract freeze](M9_CONTRACT_FREEZE.md)
- [Stage-identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md)
- [Official ViennaRNA RNAfold manual](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/man/RNAfold.html)
- [Official ViennaRNA license information](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/license.html)

M11 baseline contract: APPROVED FOR IMPLEMENTATION