# M10 exact-first implementation contract freeze

**Status: APPROVED FOR SYNTHETIC/OFFLINE BASELINE IMPLEMENTATION.**

At the time of this freeze, M10 was **PLANNED / NOT IMPLEMENTED**. This
contract authorized only the minimal deterministic exact-first software scope
below, exercised with synthetic fixtures. The M10 stage and workflow have since
been integrated according to this contract. The implementation does not
authorize biological sequence searches, reference retrieval, biological
validation, or biological conclusions.

The current [roadmap](ROADMAP.md) is authoritative for milestone status:
M1–M10 are implemented as scoped software milestones and M11–M16 remain
planned. M9 evidence remains optional context and its status does not affect
M10 eligibility. M10 is independent of M9.

Normative terms **MUST**, **MUST NOT**, and **MAY** specify the frozen software
behavior. The [blocker-resolution policy](research/M10_BLOCKER_RESOLUTION.md)
is the detailed authority for alphabet, enumeration, canonicalization, and cap
semantics; this document carries those policies into the implementation
contract.

## 1. Purpose and evidence boundary

M10 reports sequence-architecture evidence about an immutable candidate
representation and its declared boundaries. It MUST NOT infer biological
topology, completeness, identity, replication, activity, or class from sequence
geometry. A completed result is complete only for its stated candidate,
method, policy, and fully accounted search scope.

The contract is reconciled with the
[M10 architecture design research](research/M10_ARCHITECTURE_DESIGN_RESEARCH.md),
[M10 synthetic validation plan](research/M10_EMPIRICAL_VALIDATION_PLAN.md),
[M10 pre-contract readiness review](research/M10_PRECONTRACT_READINESS.md),
[M10 blocker resolution](research/M10_BLOCKER_RESOLUTION.md),
[M8 handoff and BLASTN contract](M8_CONTRACT_AND_BLASTN_VALIDATION.md),
[M9 contract freeze](M9_CONTRACT_FREEZE.md), and
[stage-identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md). Current contracts
govern current milestone status and released handoffs; M10 research documents
govern the proposed M10 design and do not create released interfaces.

## 2. Canonical input and upstream handoff

### 2.1 Candidate input

The unit of M10 analysis is one producer-declared candidate nucleotide sequence
plus its immutable identity and provenance. The canonical source is the
validated M6-produced `m8_candidate_sequence_set`
(`m8-candidate-sequence-set-v1`) and its paired FASTA when sequence bytes are
available. Revalidate the manifest, FASTA record IDs, sequence digests and
lengths, source-artifact bindings, assembly manifest, and M6 reconstruction
evidence using the existing
[candidate handoff contract](../satellite_discovery/m8_candidate_handoff.py).
The sequence digest covers the exact sequence letters; FASTA wrapping is not
part of sequence identity.

For each candidate, M10 MUST preserve:

- Producer-declared `candidate_id`, `sequence_id`, and FASTA record ID.
- Exact source sequence letters, source sequence SHA-256, and length.
- Source artifact IDs and hashes, handoff/manifest identity, and validation
  outcome.
- Declared molecule type, supplied completeness/boundary state, M6 assembly
  state, and M6 support state.
- Every distinct producer-declared identity. Byte-identical sequences MAY share
  internal computation, but MUST remain separate candidate/result records.

Unavailable sequence bytes, invalid or contradictory identity, and a complete
empty candidate set are distinct input states. None is an evaluated
no-match. A valid one-base candidate is eligible. No repeat-length or other
biological eligibility threshold is permitted.

### 2.2 Optional context and ownership

M6/M7/M8 context and any supplied M9 context MAY be linked as separate typed
artifacts. Preserve each supplied artifact's ID, hash, original status,
provenance, and unresolved/invalid state. Record absent optional context as
absent; do not infer a negative finding. Context actually validated, consumed,
or passed through in M10 output is part of M10 input identity.

M7 recurrence, M8 nucleotide homology, and M9 protein evidence MUST NOT gate
whether a valid candidate enters M10. M10 MUST NOT overwrite, repair, reinterpret,
or replace M6–M9 evidence. M10 has no dependency on an M9 result; M9 evidence
remains optional context.

## 3. Immutable sequence and alphabet contract

### 3.1 Source and analytic views

The source candidate and its upstream digest are immutable. M10 MUST NOT repair,
trim, join, circularize, or normalize the source candidate, and MUST NOT
silently convert `T` and `U`.

M10 MAY create derived analytic views with their own provenance:

- The comparison view maps ASCII lowercase to uppercase, one symbol per source
  coordinate. Its digest is
  `SHA-256("M10-COMPARE-IUPAC-v1" + NUL + uppercase_sequence_bytes)`.
- A reverse-complement view is created only when the declared type selects a
  single alphabet. Its digest is
  `SHA-256("M10-REVERSE-COMPLEMENT-v1" + NUL + alphabet_id + NUL + view_bytes)`.
- Every view records source candidate/sequence IDs and digest, transformation
  and policy version, derived digest and length, and the coordinate map.
  Reverse-complement view interval `[a,b)` maps to source interval
  `[n-b,n-a)` and is reported as `REVERSE_COMPLEMENT`.

The source digest remains the upstream candidate digest. The digest construction
labels are ASCII bytes and `NUL` denotes one zero byte. FASTA parsing and
source-digest rules remain those of the upstream handoff.

### 3.2 Valid symbols and exact matches

Accept the case-insensitive IUPAC nucleotide symbols
`A C G T U R Y S W K M B D H V N`. All other sequence symbols are
`INPUT_INVALID`; do not strip or repair embedded gaps, punctuation, whitespace,
or unknown symbols.

Only equal canonical singleton bases are definite exact matches:
`A=A`, `C=C`, `G=G`, `T=T`, and `U=U`. `T` and `U` never match.

Ambiguity symbols are not exact matches, even when the same ambiguity code is
present on both sides. For fixed comparison accounting, two ambiguity-bearing
symbols are `AMBIGUITY_COMPATIBLE` only if their represented IUPAC base sets
intersect; otherwise they are `AMBIGUITY_INCOMPATIBLE`. Compatibility is not
identity, cannot extend an exact run, and cannot alone emit an exact repeat
record. Compatibility-only repeat enumeration is not part of this baseline.

Use these complements in a derived reverse-complement view:

| DNA | RNA | Complement |
| --- | --- | --- |
| `A` | `A` | `T` / `U` |
| `C` | `C` | `G` |
| `G` | `G` | `C` |
| `T` | `U` | `A` |
| `R` | `R` | `Y` |
| `Y` | `Y` | `R` |
| `S` | `S` | `S` |
| `W` | `W` | `W` |
| `K` | `K` | `M` |
| `M` | `M` | `K` |
| `B` | `B` | `V` |
| `V` | `V` | `B` |
| `D` | `D` | `H` |
| `H` | `H` | `D` |
| `N` | `N` | `N` |

Ambiguity still breaks definite exact runs after complementing; the map does not
make ambiguity a wildcard.

### 3.3 Molecule-type applicability

Molecule type is explicit input metadata. It MUST NOT be inferred from the
sequence composition or whichever comparison gives a longer match.

| Declared type / observed symbols | Literal same-orientation branches | Reverse-complement branches |
| --- | --- | --- |
| DNA, no `U` | Run on the literal comparison view. | Applicable under the DNA complement map. |
| RNA, no `T` | Run on the literal comparison view. | Applicable under the RNA complement map. |
| Unknown type | Run on the literal comparison view. | `INSUFFICIENT_INFORMATION`. |
| Both `T` and `U` | Run on literal symbols without equating `T` and `U`. | `INSUFFICIENT_INFORMATION`. |
| DNA with `U`, or RNA with `T` | Run on literal symbols; retain the declared inconsistency. | `INSUFFICIENT_INFORMATION`. |

Illegal symbols or invalid provenance are `INPUT_INVALID`, not an
insufficient-information no-match. Unknown/mixed/inconsistent type does not
invalidate otherwise valid source letters; it limits the reverse-complement
branches only.

## 4. Exact-first method profile

The baseline is dependency-free and consists of four required exact branches.
All four are selected for every valid candidate; a reverse-complement branch
whose alphabet is unresolved returns `INSUFFICIENT_INFORMATION` and makes the
candidate aggregate `PARTIAL`, rather than being silently omitted:

| Branch ID | Required search |
| --- | --- |
| `M10_TERMINAL_DIRECT_V1` | Every exact proper suffix-prefix/end-to-start relationship in direct orientation. A same-geometry direct terminal-repeat label links to the same alignment. |
| `M10_TERMINAL_INVERTED_V1` | Every exact proper terminal relationship in reverse-complement orientation. |
| `M10_INTERNAL_DIRECT_V1` | Maximal exact internal direct-repeat pairs. |
| `M10_INTERNAL_INVERTED_V1` | Maximal exact internal reverse-complement-repeat pairs. |

Approximate/banded terminal alignment is optional and is not required for
baseline completion. General local self-alignment, BLASTN self-search, REPuter,
TRF, EMBOSS, minimap2, CheckV/PhageTerm extensions, external repeat tools, and
read-based topology evidence are deferred. No optional method silently
substitutes for an exact branch. A future optional method requires separate
approval, named method/profile, semantics, dependencies, synthetic tests, and
cache identity.

### 4.1 Terminal enumeration

For sequence length `n`, enumerate each proper length `k=1..n-1` in ascending
order. Do not set a minimum length or terminal window.

- Direct terminal: compare source intervals `[0,k)` and `[n-k,n)` in
  `DIRECT` orientation. Emit a row only when every aligned position is a
  definite exact base match. This enumerates all exact proper borders,
  including nested borders and overlapping source intervals.
- Direct terminal-repeat and suffix-prefix labels that describe this same
  coordinate pair share one alignment ID; they are not independent evidence.
- Inverted terminal: compare the prefix interval `[0,k)` with the suffix
  interval `[n-k,n)` in `REVERSE_COMPLEMENT` orientation. Retain every
  definite exact proper relationship and map both coordinates to the original
  source sequence.
- Never emit `k=n` or the full-sequence self-match. Ambiguity stops a definite
  exact run; shorter fully exact proper lengths remain independently testable.

A one-symbol sequence has no proper-border lengths and remains eligible. An
empty candidate set is not a one-symbol sequence and produces no candidate
no-match record.

### 4.2 Internal repeat enumeration

An internal repeat has two distinct equal-span intervals strictly inside the
candidate (`start > 0`, `end < n`). Terminal-to-internal alignments are outside
these internal-repeat classes in the minimal baseline.

For each orientation, extend a pair to its maximal definite exact match in both
directions while both intervals remain strictly internal. A pair is maximal
within this internal-repeat class when neither side can extend by another
definite matching base without either interval touching a candidate boundary.
An ambiguity, mismatch, or candidate boundary stops extension. Do not emit
every shorter subinterval of the same maximal pair.

Canonicalize each pair by lexicographically ordering the two source interval
tuples `(start,end)`. Exclude an identical-interval self-comparison and emit a
given `(relationship_class, orientation, interval_A, interval_B)` at most once.
Suppress only the mirrored generation of that same record. Retain all distinct
pairs, including nested, overlapping, and tandem pairs. Retain separate
`DIRECT` and `REVERSE_COMPLEMENT` records even when their coordinates match.
Overlapping coordinates or equal coordinates across different relationship
classes are not grounds for collapsing evidence.

### 4.3 Coordinates, quantitative fields, and ordering

Every alignment uses zero-based, half-open coordinates on the immutable source.
Orientation values are `DIRECT` and `REVERSE_COMPLEMENT`. Every exact
relationship records both intervals, span, definite identical-base count and
denominator, ambiguity-compatible/incompatible counts where a fixed comparison
includes ambiguous symbols, `source_intervals_overlap`, relationship class,
branch/method ID, and policy/configuration identity. Exact rows have no
mismatches, gaps, or ambiguity columns counted as identities.

Canonical serialization order is candidate ID, sequence ID, branch order
(direct terminal, inverted terminal, internal direct, internal inverted),
terminal length ascending, then internal interval A and interval B ascending,
then descending span for any remaining tie, then relationship class
(suffix-prefix, direct-terminal, inverted-terminal, internal-direct,
internal-inverted), then method ID.

For capped branches, select evidence under the fixed deterministic traversal
defined in §6.2 of the
[blocker-resolution policy](research/M10_BLOCKER_RESOLUTION.md): terminal
length ascending; internal start pairs in first-start then second-start order,
followed by maximal extension. This is the pre-cap order. Retain capped rows in
that discovery order and record it. Uncapped complete records use the canonical
serialization order above.

## 5. Partial and low-complexity candidates

Partial candidates remain eligible. Preserve supplied boundary/completeness
metadata. Positive observed relationships remain reportable, but a missing or
unresolved biological terminus MUST NOT be treated as a tested terminal
boundary or completed terminal no-match. An exact internal scan may complete
for the observed fragment; its scope is that fragment, not an unobserved
biological sequence.

Exact low-complexity relationships MUST NOT be masked or silently discarded.
They MAY carry deterministic descriptive context: source interval,
canonical-base counts, ambiguity count, Shannon entropy over unambiguous
bases, and longest homopolymer run. These measurements do not themselves
classify low complexity or support a topology conclusion.

## 6. Canonical outcomes and accounting

Every candidate, branch, and aggregate MUST retain the status axes below.
These exact strings are normative. A value on one axis does not overwrite
another axis.

### 6.1 Candidate input status

`input_status` is exactly one of:

- `INPUT_VALID` — candidate identity, provenance, sequence bytes, digest, and
  alphabet validation passed.
- `INPUT_INVALID` — identity, manifest, digest, alphabet, or artifact
  validation failed.
- `SEQUENCE_UNAVAILABLE` — valid candidate identity exists but sequence bytes
  are unavailable.
- `COMPLETE_EMPTY_INPUT_SET` — the validated input set has no candidates;
  there is no candidate branch and no candidate no-match.

### 6.2 Branch status

Each required method branch has exactly one `branch_status`:

| Value | Meaning |
| --- | --- |
| `COMPLETED_MATCHES_REPORTED` | Applicable search completed and fully accounted with one or more rows. |
| `COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY` | Applicable search completed and fully accounted with no row in the exact declared search space. |
| `INSUFFICIENT_INFORMATION` | Required comparison information or reverse-complement alphabet is unavailable or indeterminate. |
| `BOUNDARY_LIMITATION` | A required terminal boundary is missing or unresolved. Positive observed rows remain reportable. |
| `INPUT_INVALID` | Candidate or required input validation failed. |
| `SEQUENCE_UNAVAILABLE` | Candidate identity is valid but source sequence bytes are unavailable. |
| `DEPENDENCY_UNAVAILABLE` | A separately approved, selected branch's required dependency is unavailable. Not expected for the dependency-free baseline. |
| `EXECUTION_FAILED` | Selected method execution failed. |
| `OUTPUT_INVALID` | Method output, parser result, or saved artifact is malformed or fails integrity validation. |
| `INTERRUPTED` | Execution stopped before complete accounting. |
| `TRUNCATED` | A configured cap prevents complete enumeration/accounting. |
| `NOT_SELECTED` | Optional method was not selected; not a result. |
| `NOT_APPLICABLE` | Method does not apply under its declared profile; not a negative result. |
| `NOT_STARTED` | Selected method has not begun; not a result. |
| `RUNNING` | Method is in progress; not a result. |

Each branch also has `evidence_status`, exactly `EVIDENCE_FOUND` or
`NO_EVIDENCE_REPORTED`. `EVIDENCE_FOUND` may accompany `TRUNCATED`,
`INTERRUPTED`, `OUTPUT_INVALID`, or `BOUNDARY_LIMITATION` when valid rows were
accounted before that state. Preserve those rows and their provenance.

`COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY` is allowed only when the candidate is
valid, the branch is applicable, all required boundaries are established, the
entire declared search space completed successfully, output was valid, and all
rows/counts were accounted. For an incomplete branch with no known rows,
`evidence_status` is `NO_EVIDENCE_REPORTED`; this is not a no-match.

### 6.3 Aggregate status

`aggregate_status` is exactly `COMPLETE` or `PARTIAL`. `COMPLETE` requires
valid candidate input and completion/accounting of every required baseline
branch. `INSUFFICIENT_INFORMATION`, `BOUNDARY_LIMITATION`,
`INPUT_INVALID`, `SEQUENCE_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`,
`EXECUTION_FAILED`, `OUTPUT_INVALID`, `INTERRUPTED`, or `TRUNCATED` in a
required branch makes the candidate aggregate `PARTIAL`. `NOT_SELECTED` for a
required baseline branch also makes the aggregate `PARTIAL`; an optional
deferred method recorded as `NOT_SELECTED` does not affect M10 baseline
completion. Preserve independent completed rows and branch outcomes.

A no-match means only that the exact, fully accounted declared software policy
reported no row. It is not biological absence, linearity, completeness, or
absence of a terminal structure.

## 7. Typed artifacts and provenance

The M10 result bundle MUST provide a verified manifest, candidate accounting,
and typed normalized evidence. A dependency-free baseline emits deterministic
native results; it MUST NOT invent an external raw-output artifact. An optional
future external method must preserve its raw output and link parsed rows to the
raw record/ordinal.

Minimum logical record fields:

### 7.1 Candidate/accounting record

- Schema and contract version; M10 stage/method and implementation identity.
- Candidate and sequence IDs; source artifact ID/hash; exact sequence
  SHA-256/length; declared molecule type; source alphabet and completeness/
  boundary metadata.
- Supplied M6/M7/M8/M9 context descriptors, hashes, original statuses, and
  validation state; explicit absence when not supplied.
- `input_status`, required/selected branch plan, each `branch_status`,
  `evidence_status`, `aggregate_status`, reason/limitations, expected and
  accounted row counts, and effective caps.
- Normalized configuration and its digest; alphabet, comparison-view,
  enumeration, canonicalization, and ordering policy IDs; parser/normalizer
  identity; stage implementation identity; artifact references and hashes.

### 7.2 Terminal relationship evidence

- Stable evidence/alignment IDs; candidate/sequence IDs and source digest.
- Relationship class(es), branch/method ID, orientation, source intervals,
  interval-overlap flag, aligned length, definite identity numerator and
  denominator, ambiguity-compatible/incompatible counts, and exact-match
  disposition.
- Comparison-view identity and source-coordinate mapping; completeness/
  boundary context; method and policy versions; configuration digest; evidence
  provenance and any linked class records.

### 7.3 Internal repeat evidence

- Stable evidence/alignment IDs; candidate/sequence IDs and source digest.
- `INTERNAL_DIRECT_REPEAT` or `INTERNAL_REVERSE_COMPLEMENT_REPEAT` class,
  orientation, both canonical source intervals, maximal span, overlap flag,
  definite identity numerator/denominator, ambiguity context, and source-view
  coordinate mapping.
- Method/policy versions, configuration digest, low-complexity descriptive
  context when emitted, branch status/accounting linkage, and provenance.

### 7.4 Topology-compatible evidence

If emitted, the only baseline-compatible topology wording is
`CIRCULAR_COMPATIBLE_SEQUENCE_ARCHITECTURE_REPORTED`. It is a derived record,
not a separate alignment or independent observation. It MUST identify the
underlying completed or partially accounted direct suffix-prefix evidence ID,
candidate/sequence/source digest, exact intervals and orientation, overlap
length/identity, supplied boundary state, method/policy/configuration, and
limitations. It MUST NOT be derived solely from an inverted-terminal or
internal-repeat record.

### 7.5 Bundle and deterministic reuse integrity

All normalized records have stable IDs, explicit coordinate conventions,
deterministic ordering, and explicit nulls for non-applicable fields. Hash every
persisted artifact and bind it in the manifest. Reuse only a completed result
whose manifest identity and output hashes verify. Corruption, missing files,
schema incompatibility, or digest mismatch is `OUTPUT_INVALID` and triggers
safe recomputation or a visible failure; it never becomes a no-match.

## 8. Reporting floor and resource caps

There is no biological minimum repeat length and no candidate-length
eligibility threshold. Freeze these deterministic v1 software defaults per
candidate and affected branch:

| Configuration | Default | Semantics |
| --- | ---: | --- |
| `max_candidate_symbols` | 1,000,000 | Over-limit input remains eligible, but branches are `TRUNCATED` before search. Never analyze a silent prefix. |
| `max_symbol_comparisons_per_branch` | 50,000,000 | Counts each aligned symbol pair examined, including maximal-extension comparisons, in the fixed traversal order. |
| `max_evidence_rows_per_branch` | 100,000 | Counts unique canonical alignment/evidence rows after same-class mirrored deduplication; linked class labels for the same alignment do not count as separate observations. |

An explicit positive override MAY be used for a run; effective values and policy
version are normalized configuration and affect M10 identity. These are
computational/output protections, not biological thresholds. Do not use
wall-clock time as a deterministic cap; a stop before completion is
`INTERRUPTED`.

If the next comparison would exceed its cap, or a row beyond the output cap is
found, preserve accounted rows/counts and set the affected `branch_status` to
`TRUNCATED`. A branch exactly at its cap may be complete only if enumeration
proves that no further comparison/row remains. Record each effective cap,
pre-cap traversal/ordering policy, observed lower-bound count, and whether full
accounting was proven. A truncated branch or aggregate can NEVER report
`COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY`.

## 9. Cache identity and invalidation

Use the current stage-scoped identity model from the
[stage-identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md). M10 declares its own
registration and semantic dependencies; it MUST NOT substitute a package-wide
source digest or complete registry for M10's implementation identity.

M10 identity includes, where consumed:

- Exact candidate sequence digest/length, candidate/sequence IDs, source
  artifact and manifest identity, molecule/boundary metadata, and provenance.
- Optional M6/M7/M8/M9 artifact descriptors, hashes, and statuses actually
  validated, consumed, or passed through.
- M10 stage registration, implementation/algorithm, schema and named
  contract-semantic versions.
- Alphabet, ambiguity, comparison-view, reverse-complement, enumeration,
  maximality, canonicalization, orientation, coordinate, deterministic
  ordering, status, and topology-derivation semantics.
- Normalized parameters, effective caps, required-branch plan, and any
  display/reporting policy that changes output.
- Parser/normalizer identity and selected dependency-inspector/tool identity
  when applicable.

An M10-only input, implementation, configuration, parser, schema, or semantic
change invalidates M10 only. Verified M6–M9 artifacts remain reusable when
their own consumed inputs and identities are unchanged; this includes M9 keys
if/when such artifacts exist, without claiming M9 is currently implemented.
Changed candidate/context content consumed by M10 changes M10 identity. A
genuine shared-validator semantic or workflow-cache/reuse semantic version
change may have the broader invalidation defined by the current identity model.

## 10. Synthetic implementation acceptance matrix

All fixtures are generated artificial strings and synthetic artifacts. They
validate software behavior only, not biological truth, performance, or
topology.

| Fixture | Required assertion |
| --- | --- |
| Unrelated complete ends | Fully accounted branches may report `COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY`; scope is the exact tested policy. |
| Exact suffix-prefix / end-to-start | Correct proper-border lengths, intervals, orientation, quantitative fields, and deterministic order. |
| Direct terminal repeat | Shares the underlying alignment with same-geometry suffix-prefix evidence; no double count. |
| Inverted terminal / reverse-complement terminal | Correct complement policy, orientation, and mapping to source coordinates. |
| Internal direct repeat | Correct maximal intervals, identity metrics, and canonical pair. |
| Internal reverse-complement repeat | Correct inverted intervals/orientation; mirrored generation appears once. |
| Nested and overlapping terminal/internal relationships | Preserve all distinct proper lengths and coordinate pairs; permit source-interval overlap. |
| Competing direct/inverted relationships | Retain all rows; do not select a winner or collapse classes. |
| One-base and other very short valid sequences | Eligible; exhaustive empty search space is distinguished from invalid input. |
| Partial 5′/3′ boundary | Retain positive observed rows; `BOUNDARY_LIMITATION` prevents terminal no-match at an unresolved end. |
| Declared DNA and RNA | Validate literal and reverse-complement branches under the matching alphabet; source representation/digest unchanged. |
| Valid IUPAC ambiguity | Deterministic complements and compatibility accounting; ambiguity never becomes definite identity or wildcard. |
| Unknown type, mixed `T`/`U`, or declaration inconsistency | Literal branch behavior remains defined; reverse branch is `INSUFFICIENT_INFORMATION`. |
| Invalid character or candidate identity/hash | `INPUT_INVALID`; no evidence or completed no-match. |
| Low-complexity/homopolymer/periodic relationship | Retain exact rows and descriptive context; apply row/comparison caps transparently. |
| Symmetric/mirrored internal relationships | Canonicalize only same-class mirrored duplicates; retain different intervals, orientations, and relationship classes. |
| Output/comparison cap below, at, and above known result count | Deterministic pre-cap order; exact-at-cap completion only when end-of-search is proven; otherwise `TRUNCATED`. |
| Completed scoped no-match | Allowed only after valid input, applicable complete branch, complete boundaries, successful execution, and full accounting. |
| Insufficient alphabet/orientation information | `INSUFFICIENT_INFORMATION`, not no-match. |
| Corrupted/incompatible input or saved artifact | `INPUT_INVALID` or `OUTPUT_INVALID` as appropriate; safe failure/recompute, never no-match. |
| Execution failure and interruption | `EXECUTION_FAILED` or `INTERRUPTED`; preserve independent rows; no completed no-match. |
| Dependency unavailable | If a separately approved selected extension is tested, `DEPENDENCY_UNAVAILABLE`; baseline exact methods require no external dependency. |
| Deterministic repeated run | Identical normalized records, identifiers, statuses, ordering, and derived-view digests. |
| Unchanged workflow reuse | Reuse only after manifest and output-hash verification. |
| M10-only implementation/config/parser/semantic change | M10 identity changes; verified unchanged M6–M9 identities and outputs remain reusable. |
| Changed candidate or consumed optional context | M10 identity changes; unrelated upstream stage identities remain stable. |
| Shared validator/cache semantics version change | Broader invalidation is allowed only as specified by the shared identity mechanism. |

Every error, insufficiency, boundary limitation, interruption, and truncation
fixture MUST assert that no branch or aggregate reports a completed scoped
no-match unless the entire applicable search space was completed and accounted.

## 11. Downstream boundary

M10 emits evidence and limitations for possible later use; it does not decide
downstream questions:

- **M11:** may consider sequence architecture alongside its own RNA structure
  and ribozyme predictions. M10 does not infer folds, catalytic function, or
  activity.
- **M12:** owns read-origin, source-artifact, assembly, library, and technical
  artifact adjudication. M10 does not analyze reads, identify contamination,
  or validate an assembly.
- **M13:** owns DVG-versus-satellite differential evidence. M10 does not
  classify candidates or resolve alternatives.
- **M14:** owns helper association and dependence evidence. M10 does not infer
  helper status or dependence.
- **M15:** owns any later evidence integration or prioritization under a
  separately approved method. M10 does not create a composite score or
  biological ranking.
- **M16:** owns blinded benchmarking and claim-appropriate biological
  validation. No biological validation is required to implement or test this
  synthetic/offline software contract.

## 12. Implementation gate and approval boundary

The exact-first synthetic/offline baseline is sufficiently specified for
production coding of the software contract. Implementation approval covers only
the four exact branches, typed accounting and artifacts, deterministic
canonicalization, and failure-safe cache behavior defined here. It does not
authorize biological searches, external repeat/topology tools, optional
approximate alignment, raw-read analysis, biological thresholds, or
classification. No additional blocker is created merely because independent
biological benchmarking remains future work.

M10 baseline contract: APPROVED FOR IMPLEMENTATION