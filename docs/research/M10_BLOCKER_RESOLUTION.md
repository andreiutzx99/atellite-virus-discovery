# M10 blocker resolution: minimal exact-first software policies

**Decision:** the two policy gaps identified by the
[pre-contract readiness review](M10_PRECONTRACT_READINESS.md) are resolved for
a synthetic/offline exact-first M10 contract by the normative rules below.
These rules define software observations only. They do not implement M10,
approve a released interface, validate biological performance, or classify a
candidate.

This report resolves only (1) alphabet and reverse-complement behavior and
(2) exact relationship enumeration, canonicalization, and resource limits.
It does not reopen method selection or require biological benchmarking.

## 1. Frozen alphabet and comparison-view policy

### 1.1 Immutable source and derived views

The validated candidate sequence and its provenance remain the source of truth.
For every result, retain the producer-declared candidate and sequence IDs, the
upstream sequence digest and length, and source-artifact identity. Do not rewrite
the candidate letters, repair symbols, trim sequence, or convert `T` and `U`.
Candidate IDs remain distinct even when their sequence letters are identical.

M10 may derive analytic views, but these are not replacement candidates:

- A comparison view maps ASCII lowercase letters to uppercase, one symbol to
  one source coordinate. Its digest is
  `SHA-256("M10-COMPARE-IUPAC-v1" + NUL + uppercase_sequence_bytes)`.
- A reverse-complement view may be derived only when the molecule type selects
  one alphabet under §1.3. Its digest is
  `SHA-256("M10-REVERSE-COMPLEMENT-v1" + NUL + alphabet_id + NUL + view_bytes)`.
- Each derived-view record carries the source candidate/sequence IDs and source
  digest, transformation and policy version, derived-view digest and length,
  and a one-to-one coordinate map. For a reverse-complement view, view interval
  `[a,b)` maps to source interval `[n-b,n-a)` and is reported with
  `REVERSE_COMPLEMENT` orientation.

The hash inputs above are UTF-8/ASCII bytes exactly as displayed, with each
quoted label encoded as ASCII; `NUL` is one zero byte. The source digest remains
the validated upstream digest and is not replaced by either derived digest.
FASTA parsing and source-digest rules remain those of the validated upstream
candidate handoff.

### 1.2 Accepted symbols and exactness

The accepted case-insensitive nucleotide symbols are the standard IUPAC
one-letter DNA/RNA symbols:

| Symbol | Possible bases |
| --- | --- |
| `A` | A |
| `C` | C |
| `G` | G |
| `T` / `U` | T in DNA / U in RNA |
| `R` | A or G |
| `Y` | C or T/U |
| `S` | C or G |
| `W` | A or T/U |
| `K` | G or T/U |
| `M` | A or C |
| `B` | C, G, or T/U |
| `D` | A, G, or T/U |
| `H` | A, C, or T/U |
| `V` | A, C, or G |
| `N` | A, C, G, or T/U |

Only equal canonical singleton symbols are a **definite exact base match**:
`A=A`, `C=C`, `G=G`, `T=T`, and `U=U`. `T` never matches `U`.

An IUPAC ambiguity symbol is never an exact base match, including when the
symbols are identical. For comparison accounting, two symbols containing
ambiguity are `AMBIGUITY_COMPATIBLE` only if their represented base sets
intersect; otherwise they are `AMBIGUITY_INCOMPATIBLE`. Compatibility is not
identity and does not extend an exact run. Ambiguity-only tracts do not produce
exact repeat rows. The baseline does not enumerate compatibility-only repeats;
any later such method must have a separate method ID and output policy.

Any sequence symbol outside the accepted set, ignoring ASCII case, is
`INPUT_INVALID`. Do not silently remove gaps, punctuation, whitespace embedded
in the validated sequence, or other characters. FASTA formatting is handled
only by the upstream candidate parser.

### 1.3 Molecule type and reverse complements

The molecule type is explicit input metadata; never infer it from the longest
match or from sequence composition.

| Declared type / symbols | Same-orientation literal comparison | Reverse-complement branch |
| --- | --- | --- |
| DNA with no `U` | Run using literal symbols and the exactness rules above. | Applicable; use DNA complements. |
| RNA with no `T` | Run using literal symbols and the exactness rules above. | Applicable; use RNA complements. |
| Unknown type | Run using literal symbols and the exactness rules above. | `INSUFFICIENT_INFORMATION`. |
| Both `T` and `U` present | Run using literal symbols and the exactness rules above. | `INSUFFICIENT_INFORMATION`; do not choose an alphabet. |
| DNA declaration containing `U`, or RNA declaration containing `T` | Run using literal symbols and the exactness rules above. | `INSUFFICIENT_INFORMATION`; preserve and report the declaration/symbol inconsistency. |

These branch limitations do not mutate or invalidate otherwise valid source
letters. Illegal symbols or failed identity/provenance validation are instead
`INPUT_INVALID`; they cannot produce a no-match.

For an applicable branch, reverse-complement the full derived comparison view
using these deterministic maps (case is uppercase in the derived view):

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

Although every valid IUPAC symbol has a deterministic complement, ambiguity
still breaks definite exact runs as specified in §1.2. It is not converted to a
wildcard by reverse-complementing.

## 2. Frozen exact enumeration and canonicalization

### 2.1 Shared record conventions

- Use zero-based, half-open coordinates on the original submitted sequence.
- Preserve candidate ID, sequence ID, source digest, derived-view digest where
  applicable, method ID, relationship class, and orientation on every record.
- Report both source intervals, span, definite identical-base count and
  denominator, ambiguity-compatible and ambiguity-incompatible column counts
  when a fixed comparison includes ambiguous symbols, and the branch outcome.
  An exact row has only definite identical columns; it has no ambiguous,
  mismatching, or gapped columns.
- Use `DIRECT` and `REVERSE_COMPLEMENT` as orientation values. Coordinate
  intervals always refer to the immutable source, including for reverse
  comparisons.
- Retain a boolean `source_intervals_overlap`. Overlap in source coordinates
  is allowed and does not make a relationship invalid.
- Keep relationship classes distinct. If the same interval pair and alignment
  support more than one class, retain the class linkage; do not merge internal,
  terminal, direct, inverted, or topology-compatible meanings.

An alignment/comparison record is the shared quantitative observation. A
relationship-class record points to it. This permits a direct terminal repeat
and suffix-prefix observation with identical geometry to share one alignment
without being counted as independent evidence.

### 2.2 Terminal relationships

For sequence length `n`, enumerate every proper length `k` from `1` through
`n-1`. Do not apply a minimum length or a terminal window.

1. **Suffix-prefix / direct terminal:** compare source intervals `[0,k)` and
   `[n-k,n)` in `DIRECT` orientation. Emit a definite exact row only if all
   `k` aligned positions are definite exact base matches. This is the full
   enumeration of exact proper borders, including nested lengths and cases
   where the two source intervals overlap. Never emit `k=n` or a full-sequence
   self-match.
2. The **direct terminal-repeat** class refers to this same equal-length
   terminal-arm comparison. If it has the suffix-prefix geometry above, attach
   both class labels to the shared alignment; do not create a second independent
   count. A different relationship class is not discarded solely because its
   coordinates coincide.
3. **Inverted terminal:** for the same proper `k` values, compare `[0,k)` with
   `[n-k,n)` in `REVERSE_COMPLEMENT` orientation using the declared alphabet.
   Emit every definite exact proper relationship; preserve source coordinates
   and the reverse-complement view mapping. If that branch is inapplicable,
   report its typed insufficient state, not a negative result.
4. A terminal comparison that encounters ambiguity does not extend a definite
   exact row across that symbol. Record ambiguity context for the tested
   comparison; shorter fully definite proper lengths may still be emitted.

Lengths are visited in ascending `k`. A one-symbol candidate has an empty
proper-border search space; it remains eligible and can complete with no
proper-border match if the applicable branch is fully accounted.

### 2.3 Internal direct and inverted repeats

An internal repeat pair has two distinct, equal-span source intervals, each
strictly inside the candidate (`start > 0` and `end < n`). Terminal-to-internal
comparisons are outside these two internal-repeat classes in the minimal
baseline.

For each orientation, enumerate distinct interval pairs and retain the
**maximal definite exact extension**: extend in both directions for as long as
each next aligned pair is a definite exact base match under that orientation.
An interval pair is maximal when neither end can be extended by one more
definite exact matching base. Ambiguity, mismatch, or a sequence boundary stops
extension. Do not emit every shorter subinterval of one maximal pair.

Canonicalization is by source coordinates and class:

1. Order the two intervals lexicographically by `(start,end)` and store the
   lower tuple first.
2. Exclude an identical-interval self-comparison in either orientation.
3. Emit a given `(relationship class, orientation, interval A, interval B)`
   at most once. Suppress a mirrored query/target generation of that same
   record.
4. Preserve every distinct coordinate pair, including nested, overlapping, and
   tandem pairs. Preserve separate `DIRECT` and `REVERSE_COMPLEMENT` records
   even when they have identical coordinates. Coordinate overlap alone never
   deduplicates records.

No minimum repeat span applies. A valid one-symbol or otherwise short candidate
remains eligible; if its complete internal search space is empty, the software
may report a scoped no-match for that branch.

### 2.4 Stable output ordering

Canonical output order is independent of thread scheduling, hash-map order, or
platform:

1. candidate ID, then sequence ID;
2. branch order: direct terminal, inverted terminal, internal direct, internal
   inverted;
3. within terminal branches, ascending `k`;
4. within internal branches, ascending first source interval tuple, then
   ascending second source interval tuple, then descending span for any
   otherwise tied rows;
5. relationship class in the fixed order suffix-prefix, direct-terminal,
   inverted-terminal, internal-direct, internal-inverted; then method ID.

If multiple class records link to one alignment, each class record follows this
order but retains the shared alignment identity.

## 3. Reporting floor, caps, and outcome semantics

### 3.1 No biological reporting floor

The exact baseline has no minimum repeat or overlap length. Do not exclude a
valid candidate because it is short. If a later presentation layer filters rows,
that is a separate software-only display policy; it must retain complete
underlying accounting and must not change detector status or imply biological
absence.

### 3.2 Deterministic v1 software caps

Use the following default caps per candidate and affected branch:

| Configuration field | Default | Counting rule |
| --- | ---: | --- |
| `max_candidate_symbols` | 1,000,000 | Source sequence symbols. An over-limit candidate remains eligible but its M10 branches are `TRUNCATED` before search; do not silently analyze a prefix. |
| `max_symbol_comparisons_per_branch` | 50,000,000 | Each aligned pair of symbols examined, including maximal-extension comparisons, in the normative traversal order. |
| `max_evidence_rows_per_branch` | 100,000 | Unique canonical evidence rows emitted for that candidate and branch, after same-class mirrored deduplication. |

These are engineering defaults, not biological thresholds. A run may use a
different explicit positive cap, but the effective values and policy version
are normalized configuration and part of M10 cache identity. Do not use
wall-clock time as a deterministic enumeration cap; an externally interrupted
run is `INTERRUPTED`.

For terminal branches, visit `k` in ascending order and compare aligned
positions from the first position to the last. For internal branches, visit
candidate start pairs lexicographically (first start, then second start), then
extend each seed in the defined orientation. Count every symbol-pair
comparison. If the next required comparison would exceed the cap, stop that
branch and mark it `TRUNCATED`. Output rows follow this discovery order for
capped branches; uncapped canonical artifacts use §2.4 ordering.

If a branch reaches the evidence-row cap, continue only far enough to determine
whether an additional unique row exists, subject to the comparison cap. If
enumeration proves that the total is exactly the cap, it may complete. If an
additional row exists or remaining work cannot be fully accounted within the
comparison cap, retain the first capped rows, record the cap, ordering, and
observed lower-bound count, and mark the branch `TRUNCATED`. Do not claim a
complete count when enumeration stopped early.

A symbol-count cap prevents search rather than shortening or modifying the
candidate. The result remains linked to the complete source input and clearly
states that no exact branch result was completed.

### 3.3 Scoped states and no-match rule

Keep validity, applicability, execution, evidence, boundary limitations, and
aggregate completion as separate fields. At minimum, preserve these meanings:

| Condition | Required outcome |
| --- | --- |
| Invalid identity, provenance, or symbol | `INPUT_INVALID`; no search and no no-match. |
| Valid input, but unknown/inconsistent molecule type for reverse comparison | Reverse branch `INSUFFICIENT_INFORMATION`; literal direct branches may still complete. |
| Applicable branch completed with rows | `COMPLETED_MATCHES_REPORTED`, with the rows. |
| Applicable branch completed with no rows after full accounting | `COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY`, scoped to that exact branch and configuration. |
| A technical cap prevents full search/accounting | `TRUNCATED`; preserve rows/counts already accounted; never completed no-match. |
| Partial candidate with a missing required terminal boundary | Preserve positive observed rows; mark that boundary `BOUNDARY_LIMITATION`; do not emit terminal no-match for the unobserved boundary. |
| Execution, parser, or output-integrity failure | Typed failure state; preserve independently completed rows, but do not report a completed no-match for failed work. |
| Complete empty candidate set | Record no candidates searched; do not synthesize a candidate no-match. |

An aggregate is complete only when every required branch for that run is
applicable, completed, and accounted for. If a required branch is insufficient,
truncated, interrupted, invalid, or boundary-limited, preserve other branch
results but mark the aggregate partial/limited as appropriate. A no-match means
only that the complete declared exact search found no rows under the recorded
policy; it is not a claim that a biological structure is absent.

Retain exact matches in low-complexity sequence. Do not mask them or promote
them automatically. Where emitted, attach deterministic composition context
(source interval, canonical-base counts, ambiguity count, Shannon entropy over
unambiguous bases, and longest homopolymer run) as descriptive metrics, not a
biological low-complexity verdict or topology score.

## 4. Topology wording boundary

An optional topology-compatible record may be derived only from an explicit
end-to-start terminal alignment. It must link the exact source alignment ID,
candidate/sequence IDs and digest, coordinates, orientation, configuration,
and supplied boundary/completeness state. It describes a sequence
representation compatible with that observed relationship only.

M10 exact geometry must not emit or imply
`CIRCULAR_GENOME_CONFIRMED`, `LINEAR_GENOME_CONFIRMED`, `COMPLETE_GENOME`,
`SATELLITE`, `NON_SATELLITE`, or equivalent biological conclusions. Low
complexity, an exact terminal repeat, or a derived compatibility record is not
independent confirmation of topology.

## 5. Synthetic acceptance matrix

These tests establish deterministic software behavior only. They do not
estimate biological performance or topology truth.

| Fixture | Required assertion |
| --- | --- |
| DNA and RNA canonical complements | Each defined canonical complement is deterministic; source letters and source digest remain unchanged. |
| Every IUPAC symbol and complement | Each ambiguity complement follows §1.3; ambiguity never contributes a definite exact base. |
| Identical and intersecting ambiguity codes | `N`/`N` and e.g. `R`/`A` are compatibility accounting only, not exact matches; disjoint sets are incompatible. |
| Unknown type, mixed `T`/`U`, and declaration/symbol inconsistency | Direct literal comparison can run; reverse-complement branch is `INSUFFICIENT_INFORMATION`, never guessed or normalized. |
| Illegal character, failed digest, or mismatched candidate provenance | `INPUT_INVALID`; no evidence or no-match is generated. |
| One-base valid candidate | Candidate remains eligible; empty proper-border/internal spaces complete only when fully accounted. |
| Nested proper borders, including overlapping source intervals | Emit every exact proper `k`, stable ascending length; omit only `k=n`. |
| Direct terminal and suffix-prefix same geometry | One shared alignment observation with linked classes, not duplicate support. |
| Inverted terminal with each declared alphabet | Correct reverse-complement orientation and original-coordinate mapping. |
| Internal direct and inverted, including mirrored generation | Correct maximal intervals; suppress mirrored duplicates only; keep distinct pairs and distinct orientations. |
| Nested/overlapping/tandem internal pairs | Preserve distinct canonical coordinate pairs; do not emit shorter subintervals of the same maximal pair. |
| Same coordinate pair under different relationship classes | Preserve each class linkage; do not collapse classes because coordinates coincide. |
| Homopolymer/periodic input | Retain exact rows, deterministic ordering, descriptive composition context, and cap accounting. |
| Partial 5′/3′ boundary | Preserve observed positive evidence; prohibit terminal no-match for an unobserved boundary. |
| Candidate above `max_candidate_symbols` | No prefix search; branch is explicitly truncated and candidate remains linked/eligible. |
| Comparison and row caps below, at, and above known totals | At-cap completion only when the search proves it ended; otherwise `TRUNCATED`, with rows and lower-bound counts preserved. |
| Repeated identical run | Identical normalized output, derived digests, statuses, and order. |
| Identical sequence bytes under two candidate IDs/provenances | Distinct result identities remain; internal compute reuse cannot merge candidate records. |
| Truncated, failed, insufficient, or invalid branch | Negative assertion: no completed scoped no-match for that branch or aggregate. |

## 6. Cache identity and implementation boundary

The policies above become M10 semantic inputs. An implementation must include
the alphabet/comparison-view and reverse-complement policy versions, exact
enumeration/canonicalization versions, effective caps and ordering, selected
method/configuration, candidate digest and provenance, M10 output semantics,
and parser/normalizer/dependency identities actually consumed in the M10
stage-scoped key. Derived-view digests are linked to the source digest and
transformation version.

An M10-only change must invalidate M10 while verified M6–M9 outputs remain
reusable when their consumed inputs and identities are unchanged. A changed
candidate or optional context actually consumed by M10 changes M10 identity.
Only a genuinely shared validator or workflow-cache semantic change may cause
the broader invalidation defined by the existing
[stage-identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md). This report does not
change cache code or claim any proposed M10 interface already exists.

## 7. Acceptance decision and source documents

The alphabet, ambiguity, molecule-type, exact-enumeration, canonicalization,
ordering, reporting-floor, cap, truncation, and topology-language decisions
required to freeze a synthetic/offline exact-first software contract are
specified above. No additional biological-validation blocker is introduced.
The policy does not authorize approximate alignment, external tools, raw-read
analysis, biological benchmarking, or any production implementation.

Documents reconciled:

- [M10 pre-contract readiness review](M10_PRECONTRACT_READINESS.md)
- [M10 architecture design research](M10_ARCHITECTURE_DESIGN_RESEARCH.md)
- [M10 synthetic validation plan](M10_EMPIRICAL_VALIDATION_PLAN.md)
- [Pre-M9 stage identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md)

M10 BLOCKERS: RESOLVED