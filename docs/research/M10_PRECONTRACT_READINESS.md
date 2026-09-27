# M10 pre-contract readiness: exact-first baseline

**Verdict: exact-first M10 is not yet ready for formal contract freeze.** The
research establishes a narrow, dependency-light baseline and provides a strong
synthetic test plan. Two implementation-determinative policies remain
illustrative rather than approved: alphabet/reverse-complement behavior, and
the exact repeat-enumeration/canonicalization/resource-limit contract. Both
change normalized evidence, status, and cache identity. No biological
validation, external reference panel, read evidence, or M9 result is needed to
resolve them.

This is a historical pre-contract review only. At the time it was prepared,
M10 remained planned and unimplemented. It does not approve production use,
alter another milestone, or classify any candidate.

## 1. Scope and current authority

At the time of this review, the [roadmap](../ROADMAP.md) described M1–M8 as
implemented software and M9–M16 as planned. The roadmap now records current
milestone status. The [M9 contract freeze](../M9_CONTRACT_FREEZE.md) records
approval of a synthetic/offline M9 software baseline; that historical approval
was not itself an M9 implementation. The [module-interface inventory](../MODULE_INTERFACES.md)
warned that proposed interfaces were not released workflow stages.

The [M10 architecture research](M10_ARCHITECTURE_DESIGN_RESEARCH.md) and
[M10 synthetic validation plan](M10_EMPIRICAL_VALIDATION_PLAN.md) are design
proposals, not M10 contracts. The
[post-M7 roadmap reconciliation](../POST_M7_ROADMAP_RECONCILIATION.md)
supports sequence-only M10 work independently of M9 ORFs; its historical
proposals do not override current milestone status or create callable stages.

The current [M6-to-M8 candidate handoff](../M8_CONTRACT_AND_BLASTN_VALIDATION.md)
provides a suitable source of candidate identity for a future M10 design:
producer-declared candidate and sequence IDs, exact sequence digest and length,
source-artifact provenance, molecule type, completeness state, and M6 support
state. FASTA wrapping is not sequence identity; byte-identical sequences from
different declared candidates remain separate candidate records. This
candidate-sequence-plus-provenance unit is sufficient as M10's core input
boundary. M6/M7/M8 context can be preserved when supplied; M9 context can be
preserved when supplied later. M9 absence, status, or ORF count must not gate
M10 eligibility.

The minimum M10 scope should consume and validate the submitted sequence; it
should not repair letters, convert T/U, trim or join ends, circularize input,
read raw reads, or introduce an external reference database. Read-origin and
technical-artifact review remain M12 concerns. M10 reports software evidence
about the submitted string and its declared boundaries, not biological
topology.

## 2. Exact-first baseline assessment

| Contract area | Readiness | Assessment |
| --- | --- | --- |
| Candidate identity and provenance | **Sufficient** | Use the validated M6-produced candidate sequence set and paired FASTA when available. Bind each result to the declared candidate/sequence IDs, exact letters, hash, length, source artifact, and supplied completeness/molecule/support metadata. Preserve separate IDs for byte-identical sequences. |
| Eligibility and context | **Sufficient** | A valid available sequence is eligible irrespective of M6 support, M7 recurrence, M8 result, or M9 ORF evidence. Treat unavailable bytes, invalid input, and a complete empty set as distinct from an evaluated no-match. M6/M7/M8/M9 context is optional, linked, and not rewritten. |
| Exact suffix-prefix / end-to-start comparison | **Sufficient in scope; exact enumeration rule is a blocker** | Exact, same-orientation terminal comparison is a suitable core method. The design already requires coordinates, orientation, quantitative identity, nested/competing observations, and narrowly scoped evidence. The precise set of emitted border lengths, treatment of overlapping terminal intervals, and full-span self-match exclusion still need one normative rule. |
| Exact direct terminal-repeat relationship | **Sufficient in scope; exact enumeration rule is a blocker** | Compare observed 5′ and 3′ arms in the same orientation. When this is the same pair of intervals as a suffix-prefix overlap, link the views to one alignment instead of counting two independent observations. |
| Exact reverse-complement / inverted terminal relationship | **Sufficient in scope; alphabet rule is a blocker** | Retain reverse-complement orientation and map coordinates back to the immutable submitted string. Whether the branch is applicable and how ambiguous or mixed DNA/RNA symbols behave must be fixed. |
| Exact internal direct and reverse-complement repeats | **Sufficient in scope; exact enumeration rule is a blocker** | Keep internal intervals distinct from end-touching relationships; exclude trivial self-diagonal and mirrored duplicates; preserve distinct, nested, and overlapping coordinate pairs. Define what “maximal” means for a pair and how results are capped. |
| Coordinates, orientation, and quantitative fields | **Sufficient** | The design specifies zero-based, half-open normalized coordinates, both intervals, orientation, aligned bases, identity numerator/denominator, ambiguity, mismatch/gap counts, coverage denominators, and method/configuration provenance. |
| Evidence and execution outcomes | **Sufficient semantically** | Separate input validity, method applicability, execution/completeness, evidence presence, boundary limitations, and aggregate completion. A no-match is permitted only after valid input and complete accounting within the declared method/search scope. |
| Topology-compatible wording | **Sufficient with narrow language** | Any derived compatibility record must link to explicit terminal evidence and remain a sequence-representation observation. Do not emit confirmed circularity, linearity, closure, completeness, or biological class. A derived record is not an independent repeat observation. |
| Cache identity and reuse | **Sufficient as design policy** | The stage identity audit defines the current scoped-key model. M10 should fingerprint only its own registration, inputs, code, configuration, contract semantics, parsers, and selected dependencies. An M10-only change must leave verified M6–M9 results reusable; a genuinely changed consumed input invalidates M10. |
| Method scope | **Sufficient for exact-first selection** | Exact terminal and exact internal methods are suitable for the minimal dependency-free core. Approximate/banded alignment remains optional. General local self-alignment and external tools remain deferred absent a concrete need. |

The remaining blockers concern the exact output function of the first four
methods, not whether those methods belong in an exact-first baseline. The
synthetic plan is a validation protocol; it has not been run and makes no
biological performance claim.

## 3. Decisions that block contract freeze

These are the only unresolved choices identified here that prevent an
implementable exact-first contract from being frozen. The recommendations
below are a proposed resolution for review, not an assertion that the choices
have already been approved.

### BLOCKER 1 — alphabet and reverse-complement policy

The current M10 research prohibits silent T/U conversion and wildcard
interpretation but leaves DNA, RNA, IUPAC, and unknown/mixed-label handling
open. This changes whether a terminal or internal reverse-complement record
exists and therefore changes the normalized output and cache key.

**Recommended minimal deterministic policy:**

- Preserve the original sequence letters, declared molecule type, and source
  hash exactly. Do not normalize or rewrite T/U.
- For same-orientation exact comparisons, A, C, and G match themselves;
  T matches only T; U matches only U. T and U are not interchangeable.
- Treat every IUPAC ambiguity symbol as an uncertainty boundary for exact
  nucleotide identity: it is not a wildcard and is not a definite match even
  to the same ambiguity code. Do not extend an exact match across it. Retain
  its coordinate and symbol so the affected comparison can report an ambiguity
  limitation.
- Run a reverse-complement branch only when the declared molecule type selects
  one deterministic alphabet: DNA uses A↔T and C↔G; RNA uses A↔U and C↔G.
  Do not infer molecule type from which branch gives a longer match. If the
  type is unknown, mixed, or inconsistent with T/U content, mark the
  reverse-complement branch `INSUFFICIENT_INFORMATION`; same-orientation
  literal comparisons may still run.
- For a declared DNA/RNA sequence containing ambiguity symbols, the minimal
  exact reverse-complement branch may compare only unambiguous A/C/G/T or
  A/C/G/U runs, preserving ambiguous sites and any separately observable
  exact runs. Do not score an ambiguous column as an exact nucleotide match.

This is deliberately conservative: it may leave some potentially compatible
relationships unassessed, but it is deterministic and cannot turn ambiguity
into a definite exact match. The project must approve or replace this policy
before freezing the exact-match contract.

### BLOCKER 2 — repeat enumeration, canonicalization, and resource policy

The research requires all distinct/nested relationships and suggests maximal
internal intervals, but it does not define a single canonical output rule.
Homopolymers and periodic strings can produce very large sets of overlapping
matches. Different choices about submatches, overlapping intervals, or
deduplication change evidence rows, result counts, and truncation behavior.

**Recommended exact-first contract rule:**

1. Use zero-based, half-open coordinates on the original submitted sequence.
   Search the complete submitted sequence; do not add an arbitrary terminal
   window or repeat-length cutoff to the exact method.
2. For exact suffix-prefix and same-orientation terminal comparisons, report
   every matching proper border length (`1 <= k < sequence_length`) under the
   selected exact alphabet. Keep nested lengths in deterministic order. Allow
   the prefix and suffix intervals to overlap in source coordinates, record
   that fact, and do not report the full-length sequence as its own terminal
   match.
3. Link direct-terminal-repeat wording to the same coordinate pair where it
   duplicates an exact suffix-prefix observation. Do not count those labels as
   independent evidence.
4. For exact inverted terminal relationships, use the corresponding
   reverse-complement comparison over the same proper-border search space and
   retain original-sequence coordinates and orientation.
5. For internal repeats, emit one maximal exact extension for each distinct
   pair of start coordinates and orientation. “Maximal” means that the pair
   cannot be extended by one more concrete matching base on either side under
   the declared orientation. Exclude only the identical-interval self-match
   and mirrored duplicate of the same pair. Allow overlapping intervals;
   retain nested or overlapping results when their coordinate pairs differ.
   Do not emit every shorter subinterval of the same start-pair maximal match.
6. Use no minimum repeat length in the baseline. Require an explicit,
   positive software output/resource cap in the run configuration. If the cap
   prevents proving that all in-scope rows were emitted/accounted, report
   `TRUNCATED`, retain available rows and counts, and prohibit completed
   no-match. The cap value is a resource/reporting policy, not a biological
   threshold, and must be included in M10 configuration identity.

This rule produces finite deterministic output without omitting short matches
by a biological assumption. Internal pair enumeration and low-complexity
output can still grow quadratically with candidate length; the explicit cap
exists to bound software cost and result volume. The project must approve this
canonicalization/cap policy or specify an alternative before freezing the
contract.

## 4. Reporting-floor decision

Exact repeat enumeration can be defined without a biological minimum repeat
length. A finite candidate has a finite set of exact borders and internal
coordinate pairs. The first exact-first contract should therefore use **no
repeat-length reporting floor**.

A floor is not required for correctness. If a later user-facing report needs
one to limit display volume, name it as `minimum_reported_span` (or equivalent),
record it in configuration and cache identity, preserve the underlying
accounting/counts, and state that it filters software output only. It must not
be presented as the shortest biologically meaningful repeat or used to infer
absence below the floor.

An explicit output/resource cap is different from a minimum length. It bounds
worst-case time or emitted rows for repetitive sequences. When it prevents
complete accounting, the only valid outcome is truncation/partial completion,
never a completed no-match. This cap is a **software policy** and is not
evidence for a biological terminal structure.

## 5. Evidence semantics and failure-safe outcomes

The research supports these distinct semantic outcomes; exact enum spellings
can be frozen in the M10 schema by adopting the current M8-style distinction
between completed evidence and incomplete/error states:

| State | Required meaning | May become completed no-match? |
| --- | --- | --- |
| Evidence found | One or more exact rows are reported with coordinates, orientation, quantitative details, and source method. | No; report the rows. |
| Completed scoped no-match | Valid input; applicable complete method; the entire declared search space and accounting were completed with no row under the declared exact policy. | Yes, only as “no match within this tested method and scope.” |
| Insufficient information | Required sequence bytes, alphabet/orientation, or comparison information is unavailable or indeterminate. | **No.** |
| Partial-boundary limitation | A required biological end is not established by the supplied boundary/completeness metadata. Positive observed matches remain reportable. | **No terminal no-match.** Aggregate remains partial/boundary-limited. |
| Invalid candidate/input | Sequence, manifest, ID, hash, or alphabet validation fails. | **No.** |
| Execution failure | A selected method or its parser fails. Preserve other completed branch rows separately. | **No.** |
| Interrupted | The declared work did not finish. | **No.** |
| Truncated/incomplete accounting | A cap or other limit leaves in-scope rows or branches unaccounted. | **No.** |
| Complete empty input set | Valid input accounting contains no candidates. | **No candidate was searched; do not emit a no-match candidate row.** |

A partial candidate can have a completed exact internal-repeat scan of the
observed fragment, but absence of a terminal relationship at an unresolved
boundary cannot be represented as a completed terminal no-match. If one required
branch fails, truncates, or is insufficient, preserve any independent positive
rows but mark the aggregate partial. The synthetic validation plan already
requires negative assertions for error, truncation, insufficiency, and partial
boundary states.

For topology terminology, keep the evidence label narrow: a
`CIRCULAR_COMPATIBLE_SEQUENCE_ARCHITECTURE_REPORTED`-style record, if retained,
must cite the exact end-to-start alignment and supplied boundary state. It
describes compatibility of a sequence representation only. It must not be
rendered or transformed into confirmed circularity, closure, completeness,
replication, or biological classification.

## 6. Unresolved-topic classification

| Topic from the research | Classification | Reason |
| --- | --- | --- |
| Candidate handoff and provenance | **NON-BLOCKING** | The current M6-produced candidate sequence-set contract supplies the stable identity, exact bytes/hash, length, and provenance needed by M10. M10 itself must define its output artifact, but no new input source is needed. |
| M9 status and optional context | **NON-BLOCKING** | Current roadmap status remains planned/not implemented. M10 can consume the exact candidate without M9; any supplied M9 artifact is optional context with its own identity and status. Waiting for M9 is not a technical M10 dependency. |
| DNA/RNA/IUPAC and mixed/unknown orientation | **BLOCKING** | The current proposals prohibit unsafe normalization but do not select a deterministic exact-match/reverse-complement policy. See blocker 1. |
| Coordinate convention | **NON-BLOCKING** | Zero-based, half-open coordinates on the original sequence are already recommended and are straightforward to lock in the new contract. |
| Exact terminal/internal repeat enumeration | **BLOCKING** | “All/nested” and “maximal” are both proposed without an agreed canonical record rule, overlap treatment, or self/mirror suppression rule. See blocker 2. |
| Duplicate/symmetry canonicalization | **BLOCKING** | Exact internal direct/inverted output counts depend on which mirrored or same-interval rows are the same observation. Approve the pairwise rule in blocker 2. |
| Biological reporting floor | **NON-BLOCKING** | No biological floor is needed. Recommend no minimum span in the exact baseline. |
| Technical output/resource cap | **BLOCKING** | Exact internal output can grow substantially on low-complexity inputs. Require an explicit positive software cap and frozen truncation semantics as in blocker 2. |
| Truncation and failed-work semantics | **NON-BLOCKING** | The research and synthetic plan already prohibit translating cap hits, failures, interruption, malformed output, or incomplete accounting into a completed no-match. |
| Low-complexity handling | **OPTIONAL** | Do not mask or discard exact rows in the minimal baseline. Low-complexity annotation can be separately added; deterministic output bounds are covered by blocker 2. |
| Partial-candidate semantics | **NON-BLOCKING** | Preserve supplied completeness/boundary metadata, report positive observed evidence, and prohibit terminal no-match at an unresolved boundary. |
| Topology-compatible terminology | **NON-BLOCKING** | The evidence boundary is already clear if wording remains representation-compatible and is derived from explicit terminal evidence only. |
| Cache dependencies and M6–M9 isolation | **NON-BLOCKING** | The current stage-identity audit supplies the applicable model. Later implementation must name M10-specific code, registration, semantics, parser, configuration, and optional dependencies; these names cannot be fixed before code exists. |
| Approximate/banded alignment | **OPTIONAL** | The synthetic plan recommends keeping it outside the minimal exact-first contract; promote only through a separately approved, named method profile. |
| General local self-alignment and external tools | **DEFERRED** | No demonstrated requirement justifies their extra parameters, dependencies, output, or cache surface for the minimal baseline. |
| Raw-read/topology and artifact attribution | **DEFERRED** | Sequence-only M10 does not own read-origin evidence. Any later read branch requires separate authorization, accounting, and M12 ownership. |
| Biological performance, topology truth, or completeness claims | **BIOLOGICAL-VALIDATION ONLY** | These need independent, claim-appropriate validation. They are not prerequisites for freezing or testing an exact software contract. |

The two blocker entries above describe the same two decisions, not additional
independent blockers. All other open topics can be explicitly scoped, deferred,
or represented in the contract without blocking a synthetic/offline exact-first
baseline.

## 7. Synthetic test readiness and missing software fixtures

The [synthetic validation plan](M10_EMPIRICAL_VALIDATION_PLAN.md) covers the
principal exact and optional methods, controlled substitutions/indels,
ambiguity, low complexity, partial boundaries, competing relationships,
truncation, deterministic reuse, and M10-only cache invalidation with M6–M9
reuse. The earlier
[M10 software-validation matrix](M10_ARCHITECTURE_DESIGN_RESEARCH.md#7-synthetic-software-validation-matrix)
also calls for invalid/corrupt inputs, parser/dependency/interruption failures,
missing provenance, and tampered saved outputs. These are sufficient fixture
families for contract testing; the following precise cases should be added to
the implementation test inventory before the tests are considered complete:

1. **Alphabet truth table:** declared DNA and RNA; each unambiguous complement
   pair; every supported IUPAC ambiguity symbol; ambiguity positioned inside,
   adjacent to, and outside a possible repeat; unknown molecule type; T-only,
   U-only, and mixed T/U; and declaration/symbol inconsistency. Assert no input
   mutation, no wildcard match, and branch-specific insufficient status where
   reverse-complement orientation is undefined.
2. **Short and degenerate terminal cases:** shortest valid sequence; sequence
   shorter than a configured display/window size; one-base match; exact
   `k = n - 1` border; overlapping prefix/suffix intervals; and exclusion of
   the trivial `k = n` whole-sequence self-match.
3. **Internal enumeration oracle:** overlapping and nested pairs, direct and
   inverted pairs, repeated motifs with different start coordinates, one
   canonical row versus its mirrored row, and a homopolymer that reaches the
   cap. Assert the approved maximal-extension and canonicalization rule.
4. **Candidate identity preservation:** two producer-declared candidate IDs
   with identical sequence bytes but different provenance remain separate
   result identities, even if an internal computation is reused.
5. **Input-state separation:** complete empty candidate set, candidate record
   with unavailable bytes, malformed FASTA/hash/manifest, and valid partial
   candidate each receive their own input/boundary state and never collapse
   into a searched no-match.
6. **Cap boundary accounting:** known result count below, exactly at, and above
   the configured cap. Completing exactly at the cap is complete only if the
   implementation proves enumeration ended; omitted or unverified results are
   `TRUNCATED`. Assert no completed no-match after truncation.

These are software-contract fixtures only. Missing biological truth sets,
read-based assays, or independent topology validation are not missing software
fixtures and must not be made prerequisites for this freeze.

## 8. Cache isolation after M10 implementation

Use the current [stage-identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md) as
the basis for future synthetic workflow tests. The M10 scoped key should include
the exact candidate input and provenance, optional context actually consumed,
M10 stage registration, M10-specific implementation/contract semantics,
normalized parameters, repeat/report caps, parser/normalizer identity, and
selected dependency identity. It should not substitute a package-wide source
digest for M10's own implementation identity.

Hold verified M6–M9 artifacts/configuration constant and change one M10-only
input to identity at a time: M10 code, configuration, parser, output schema or
named semantics, and optional tool identity. Each such change must recompute
M10 while leaving unchanged M6–M9 keys and verified outputs reusable. Separately
test a changed candidate/context digest, a corrupted M10 output, and an
intentional shared validator or workflow-cache semantics version bump. The
shared-semantics change may have the broader invalidation defined by the
existing model; it is not an M10-isolation failure. No production cache code
should be changed as part of this review.

## 9. Documents reviewed

- [M10 architecture design research](M10_ARCHITECTURE_DESIGN_RESEARCH.md)
- [M10 synthetic validation plan](M10_EMPIRICAL_VALIDATION_PLAN.md)
- [Current roadmap](../ROADMAP.md)
- [Post-M7 roadmap reconciliation](../POST_M7_ROADMAP_RECONCILIATION.md)
- [M9 contract freeze](../M9_CONTRACT_FREEZE.md)
- [M8 candidate handoff/search contract](../M8_CONTRACT_AND_BLASTN_VALIDATION.md)
- [M6 residual support context](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md)
- [Stage identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md)
- [Module interface inventory](../MODULE_INTERFACES.md)

No production code, tests, M9 files, README, roadmap, attachments, `.replit`,
or `.agents` files are modified by this review. No biological sequence or
database was accessed.

M10 CONTRACT FREEZE: BLOCKED