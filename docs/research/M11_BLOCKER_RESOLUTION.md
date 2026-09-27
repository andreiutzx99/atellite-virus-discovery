# M11 blocker resolution: conservative offline MFE baseline

**Decision:** the software and contract decisions needed to freeze a small
synthetic/offline M11 baseline are resolved below. The baseline is deterministic
RNA-view construction plus one ViennaRNA minimum-free-energy (MFE) prediction.
This document does not implement M11, authorize biological-data access, or
establish biological performance.

The current [roadmap](../ROADMAP.md) governs milestone status: M1–M10 are
implemented as scoped software milestones and M11 remains planned. This report
resolves the contract blockers identified by the
[M11 readiness review](M11_PRECONTRACT_READINESS.md), using the
[M11 design research](M11_RNA_STRUCTURE_DESIGN_RESEARCH.md), current
[M10 contract](../M10_CONTRACT_FREEZE.md), and the project’s
[stage-identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).
Historical status wording in older documents does not supersede the roadmap.

## 1. Core contract decisions

### 1.1 Source, alphabet, normalization, and applicability

The validated upstream candidate is immutable. M11 records its candidate and
sequence identities, source-artifact identity, source digest, declared molecule
type, and completeness metadata. M11 does not repair, trim, join, rotate,
circularize, or replace the source sequence. It does not change M1–M10
validation, outputs, cache identity, or eligibility.

M11 applies the case-insensitive IUPAC alphabet already accepted by M10,
`A C G T U R Y S W K M B D H V N`, for input validation only. The folding
engine's accepted analytical view is deliberately narrower:

| Declared molecule type and symbols | M11 fold view and branch outcome |
| --- | --- |
| RNA containing only `A C G U` | Uppercase ASCII lowercase in a derived view; fold that view. |
| DNA containing only `A C G T` | Uppercase ASCII lowercase and explicitly convert each `T` to `U` in a derived RNA view; fold that view. |
| Valid IUPAC ambiguity symbol present | Preserve the valid source; mark the MFE branch `NOT_APPLICABLE`. Do not expand ambiguity codes or treat them as negative evidence. |
| Unknown molecule type, DNA containing `U`, or RNA containing `T` | `INSUFFICIENT_INFORMATION`; do not infer molecule type or silently resolve a conflict. |
| Invalid symbol, failed source identity/provenance validation, or empty sequence | `INPUT_INVALID`; do not strip or repair input. |
| Candidate identity is valid but source sequence bytes are unavailable | `SEQUENCE_UNAVAILABLE`. |

Apply these checks in order: failed candidate identity/provenance validation;
valid candidate identity with unavailable source bytes; invalid symbols,
empty-sequence, or region validation; unknown/conflicting molecule type; then
folding-alphabet applicability. Thus an invalid symbol is never masked by an
unknown molecule type, and a valid ambiguous sequence with unknown molecule
type is `INSUFFICIENT_INFORMATION` rather than `NOT_APPLICABLE`.

ASCII lowercasing-to-uppercase and DNA `T`-to-RNA `U` conversion are the only
normalizations. They occur only in the derived analytical view. The view record
contains the source digest and length, view digest and length, transformation
policy/version, molecule-type declaration, and a one-to-one source-coordinate
map. The source letters and upstream digest remain unchanged. No conversion is
inferred from sequence composition.

A foldable sequence must be nonempty. One nucleotide is eligible; there is no
biological minimum length. An empty sequence is invalid input, not a completed
no-result or a negative observation. A valid ambiguous sequence is likewise not
rejected as a candidate; only this MFE method is inapplicable to it.

### 1.2 Orientation, regions, and coordinates

The default request folds the complete supplied sequence in its producer-
declared orientation. The branch records orientation as `AS_SUPPLIED`. It must
not search the reverse complement, rotate a sequence, infer circularity, or
generate automatic windows.

A caller may instead select exactly one explicitly declared contiguous region
`[start,end)` on the original candidate, using zero-based, half-open coordinates.
The region must satisfy `0 <= start < end <= source_length`; malformed or
out-of-range coordinates are `INPUT_INVALID`. The derived RNA view is formed
from that region only, and every output interval maps directly back to the same
source interval. A region is not a new candidate. No implicit flank padding,
joining, or circular wraparound is permitted. A one-symbol region is eligible.

An M11-only region or orientation choice does not change any upstream result.
M11 does not consume optional M7–M10 findings as a gate for this fold.

### 1.3 Resource limits and incomplete execution

Each run must declare finite, positive limits for:

- `max_fold_symbols`: maximum symbols in one complete candidate or explicitly
  selected region;
- `max_folds_per_run`: maximum requested candidate/region folds in the run;
- `timeout_seconds_per_fold`: maximum wall time for one fold; and
- `memory_bytes_per_fold`: maximum memory available to one fold.

These are software-safety limits, not biological cutoffs. Their effective
values, enforcement policy, and configuration version are recorded and included
in M11 cache identity. Deployment profiles may choose different finite values.
There is no silent truncation, prefix fold, automatic subdivision, or fallback
to a different engine. A request exceeding a configured symbol or run-count cap
is `TRUNCATED`; the full input and cap are reported, and no partial sequence is
folded. A timeout or externally enforced resource kill is `INTERRUPTED`, with
the reason and any completed sibling records retained. Neither state is a
completed prediction or a no-result.

The run manifest records every requested candidate/region key, the expected and
accounted fold counts, and one terminal branch status per request. A run-count
cap marks every request not started because of that cap `TRUNCATED`; no request
is silently omitted from accounting.

An MFE call is atomic at the branch level: only a structurally valid, fully
parsed return is a reported prediction. A failed call is `EXECUTION_FAILED`;
malformed structure/energy output or failed artifact-integrity checks are
`OUTPUT_INVALID`. Do not convert a crash, interruption, resource limit, or
parse failure into a no-fold/no-signal result.

### 1.4 Engine, model, and required output

The required engine is the ViennaRNA Python interface (`RNAlib`/`RNA`), exactly
release **2.7.2**. Use its single-sequence MFE operation only. There is no
automatic engine substitution. At runtime, record the exact wheel/artifact
SHA-256, native-library/build identity, Python implementation/version and ABI,
operating system, and architecture.

Freeze the following energy profile:

- Turner 2004 parameter set;
- temperature `37.0 °C`;
- dangling-end setting `2`;
- unconstrained, linear RNA input;
- MFE-only calculation, with no partition function or ensemble calculation.

All other model options must use the pinned 2.7.2 profile and their resolved
effective values must be recorded, not merely described as “defaults.” The
profile identifier/version, parameter object, and any constraints are part of
the result and cache identity. No custom parameter file or constraint is
permitted in the baseline.

Each completed fold record includes, at minimum:

- candidate, sequence, source-artifact, and source-sequence digest identities;
- declared molecule type, source completeness, selected source region,
  `AS_SUPPLIED` orientation, and source/view coordinate mapping;
- view transformation/policy, view digest, and view length;
- engine, interface, exact build and runtime identities;
- method/profile ID, effective model parameters, and finite resource limits;
- dot-bracket MFE structure and its length;
- MFE energy in kcal/mol, serialized as a locale-independent decimal string
  with two fractional digits;
- limitations, branch status, normalized-record hash, and artifact references.

The structure must have exactly the view length and use the engine's supported
dot-bracket representation. Do not add a probability, confidence score,
significance threshold, or family/function label. If an external raw-output
artifact exists, hash and link it; an API-based run must not invent a raw
stdout artifact.

## 2. Status vocabulary and result meaning

Keep input validity, applicability, execution/completeness, and evidence as
separate fields. The MFE branch uses these exact status values:

| Branch status | Meaning |
| --- | --- |
| `PREDICTION_REPORTED` | A valid, applicable, complete MFE call and parsed structure/energy are preserved. |
| `INPUT_INVALID` | Candidate identity/provenance, sequence symbols, empty input, or region selection failed validation. |
| `SEQUENCE_UNAVAILABLE` | Candidate identity is valid, but sequence bytes are unavailable. |
| `INSUFFICIENT_INFORMATION` | Molecule type is missing, unknown, or inconsistent with the observed `T`/`U` symbols. |
| `NOT_APPLICABLE` | Input is valid but the MFE input policy does not apply, including valid ambiguous IUPAC symbols. |
| `NOT_SELECTED` | The optional M11 stage or a separately optional branch was not selected. |
| `DEPENDENCY_UNAVAILABLE` | Selected ViennaRNA 2.7.2 runtime/build is unavailable. |
| `EXECUTION_FAILED` | The selected engine failed without a complete result. |
| `OUTPUT_INVALID` | Engine output, parsed record, or saved artifact is malformed or fails integrity validation. |
| `INTERRUPTED` | Execution stopped before the fold completed, including timeout or resource kill. |
| `TRUNCATED` | A configured input-size or per-run fold-count cap prevented the requested fold. |
| `NOT_STARTED` / `RUNNING` | Lifecycle states only; neither is a result. |

MFE has no legitimate completed “no match” state: for a valid, applicable,
nonempty sequence a successful engine call reports a predicted structure.
There is no `COMPLETED_NO_MATCH` and no completed negative fold result. A
successful fold is a model-dependent prediction, not an experimentally observed
structure.

The aggregate is `COMPLETE` only when the required MFE branch for every selected
candidate/region is `PREDICTION_REPORTED`. It is `PARTIAL` when any selected
required fold is invalid, unavailable, inapplicable, failed, interrupted,
truncated, or output-invalid; retain any independently completed records.
Optional unselected branches do not make the baseline aggregate partial. If
M11 itself is not selected, report `NOT_SELECTED`, not an empty completed
aggregate.

## 3. Deterministic records, ordering, and cache identity

Serialize normalized records as UTF-8 canonical JSON with a final LF, stable
key ordering, explicit nulls for non-applicable fields, no non-finite numbers,
and the fixed decimal representation above. Sort records by candidate ID,
sequence ID, source-region start, source-region end, then method/profile ID.
Stable record identifiers derive from the normalized stage identity and record
key; do not use timestamps, random IDs, filesystem traversal order, or thread
completion order in result records. For a fixed candidate, exact 2.7.2 build,
normalized configuration, and platform, a completed rerun must produce the
same normalized records and hashes.

M11 cache identity includes the validated candidate/source-artifact identity
and digest; exact source and selected-region bytes; molecule type and
completeness; orientation and region boundaries; derived-view bytes/digest and
transformation-policy version; method and full effective parameter profile;
finite resource limits; ViennaRNA release and exact build/runtime; implementation,
parser, schema, and contract-semantic identities. Include optional input
identity only if a future selected method actually consumes it. Basic MFE does
not consume M7–M10 outputs.

Reuse only a completed, integrity-verified fold record whose identity and
artifact hashes match. Recompute or visibly fail on corrupt/missing output;
never reinterpret it as no-result. Interrupted, failed, unavailable, or
otherwise incomplete attempts are not reusable predictions. An M11-only
implementation, input, or contract change invalidates M11 only, consistent
with the [stage-identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).

## 4. Provisioning, licensing, and CI posture

Use official ViennaRNA 2.7.2 Python wheels for CPython 3.11 and 3.12 on Linux
and Windows x86-64 as the initial supported provisioning targets. Pin the exact
per-platform wheel filenames and SHA-256 digests in the implementation's
dependency lock; record the installed artifact and native build identity in
each result. A target without a verified compatible build reports
`DEPENDENCY_UNAVAILABLE`. Do not install tools or alter dependencies as part
of this contract-resolution task.

Do not vendor the wheel or bundle/redistribute ViennaRNA binaries in the
application. Provision the pinned official package as an environment dependency,
retain the applicable license and attribution notice, and review the exact
artifact terms before distribution. Before commercial-product release, contact
the ViennaRNA authors as requested by the published license information; if the
intended distribution cannot meet the terms, do not ship the folding dependency
or silently substitute another engine. Later CI must smoke-test import and a
synthetic MFE fold on each supported Python/OS/architecture combination.

These requirements settle the project posture; they are not a legal opinion.
The release/build hashes and actual CI smoke results belong to implementation
and release records and do not block freezing the software contract.

## 5. Optional branches and future biological execution

| Area | Decision for this baseline | What requires a separate future decision |
| --- | --- | --- |
| ViennaRNA ensemble / partition function | `NOT_SELECTED`; MFE-only is the required baseline. Its absence does not reduce a completed baseline result. | Whether ensemble free energy, diversity, base-pair probabilities, or other fields answer a defined question; their representation, parameter alignment, thresholds, and cache/output contract. |
| Infernal/Rfam | `NOT_SELECTED`; no database is retrieved and no profile-search no-hit is emitted. | Exact Infernal build, Rfam release/model-set hash, selected models/clans, thresholds, accounting, platform, and licensing/provisioning. A no-hit would require complete valid accounting of the frozen model set. |
| Comparative analysis, R-scape, custom ribozyme detection, alternative folding engines | Deferred and outside the core contract. | A defined evidence question, valid inputs, named method/model, validation, licensing, and separate typed result semantics. |
| Real biological execution | Not required for synthetic/offline software acceptance; no candidate sequences or biological database are selected or searched here. | Authorization and terms for any data, resource provenance, suitable controls/comparators, and independently designed empirical validation. |
| Biological interpretation | MFE is a prediction under the named model and parameters only. It is not native structure, catalytic activity, expression, replication role, satellite identity, helper dependence, novelty, or function. MFE energy is not a calibrated probability or candidate significance score. | Any biological claim requires claim-appropriate independent evidence; catalytic activity/function requires experimental evidence and cannot be inferred by this contract. |

Missing or unavailable optional evidence remains `NOT_SELECTED`,
`NOT_APPLICABLE`, `INSUFFICIENT_INFORMATION`, or the applicable unavailable/
incomplete state. It never counts against a candidate and never changes the
MFE branch into a negative result.

## 6. Synthetic/offline acceptance fixtures

Fixtures use artificial sequence strings and injected engine/runtime outcomes.
They test software behavior only. The successful-fold golden structure and
energy are generated and checked in against the pinned 2.7.2 build during
implementation; this report does not assert biological performance.

| Fixture | Required acceptance behavior |
| --- | --- |
| Ordinary canonical RNA, e.g. `GCGAAACGC` | Complete MFE result; valid dot-bracket length equals view length; energy and parameters are recorded. |
| Declared DNA `ACGT` | Source remains `ACGT`; derived view is exactly `ACGU`, with explicit T→U policy, digest, and coordinate map. |
| Lowercase RNA `acgu` | Source bytes remain unchanged; uppercase analytical view is exactly `ACGU`. |
| Ambiguous IUPAC, e.g. `ACGNR` | Valid source, `NOT_APPLICABLE`, no engine invocation, no negative evidence. |
| Invalid character, e.g. `ACG-X` | `INPUT_INVALID`; no stripping, repair, fold, or no-result. |
| Empty sequence | `INPUT_INVALID`; no engine invocation and no completed no-result. |
| Length boundaries | With a test cap `L`, length 1 and `L` are eligible; `L+1` is `TRUNCATED` with no prefix fold. Test the lower and upper boundaries independently of biological meaning. |
| Declared subregion | For an artificial source and valid `[a,b)`, fold only that slice and map the output to the original zero-based half-open interval. Invalid or empty regions are `INPUT_INVALID`. |
| Orientation | Confirm `AS_SUPPLIED`; no reverse-complement, rotation, automatic window, or circular wraparound call occurs. |
| Successful MFE | Pinned synthetic golden output, finite two-decimal energy, exact effective parameter/build provenance, and valid output hashes. |
| Tool unavailable | `DEPENDENCY_UNAVAILABLE`; no fallback engine and no no-result. |
| Tool failure | Injected engine exception/nonzero failure yields `EXECUTION_FAILED`, not a negative result. |
| Interrupted/incomplete | Inject timeout/termination; yield `INTERRUPTED`, retain completed sibling folds, and do not reuse the incomplete attempt as a prediction. |
| Malformed tool output | Inject invalid dot-bracket, wrong structure length, non-finite/missing energy, or corrupt artifact; yield `OUTPUT_INVALID`. |
| Deterministic rerun/cache | Same input, build, and normalized settings produce byte-identical canonical records and the same identity; verified cache hit returns them unchanged. Changing region, model parameter, resource policy, or build changes identity; corrupt cached output is rejected. |

## 7. Resolution

The required synthetic/offline contract is fully specified without selecting an
optional branch, biological dataset, candidate sequence, or empirical
performance threshold. Those future choices are not blockers to this narrow
software contract. No upstream scientific behavior is changed, and M11 remains
an optional evidence layer rather than an M1–M10 gate.

## Sources and project records

- [M11 pre-contract readiness review](M11_PRECONTRACT_READINESS.md)
- [M11 RNA structure design research](M11_RNA_STRUCTURE_DESIGN_RESEARCH.md)
- [M10 exact-first contract](../M10_CONTRACT_FREEZE.md)
- [Current roadmap](../ROADMAP.md)
- [Stage-identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md)
- [Official ViennaRNA RNAfold manual](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/man/RNAfold.html)
- [Official ViennaRNA license information](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/license.html)

M11 CONTRACT BLOCKERS: RESOLVED