# M36 Phase 2B scientific decision record

**Record status: DRAFT FOR DESIGN-OWNER APPROVAL.**
**Decision status: ALL FIVE ITEMS PENDING APPROVAL.**

This record presents the five proposed definitions for explicit design-owner
approval. The independent scientific review was reported as passed at commit
`baf5a611370ff2a8bd1162dc25f560e8cbae7adb` on draft PR #103. That review is
not design-owner approval. No choice in this record is adopted, frozen, or
authorized for execution.

The full algorithm details remain in
[`M36_PHASE2B_AMENDMENT_SPECIFICATION.md`](M36_PHASE2B_AMENDMENT_SPECIFICATION.md).
This decision record does not modify the frozen preregistration, condition
catalog, code, adapters, private source map, or evaluator values. Phase 2B
remains **NO-GO / NOT RUN**.

## Source and version scope

Unless noted otherwise, these sources are identified at reviewed PR-head commit
`baf5a611370ff2a8bd1162dc25f560e8cbae7adb`. SHA-256 values are over the exact
file bytes at that commit.

| Ref | Source | Version or digest |
|---|---|---|
| D1 | `docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json` | Frozen registered design; SHA-256 `9bf43bc8dc3e947de87bac66a5d2f5d9dd27f967544144aee58f19f67c06df8f`. |
| C1 | Condition catalog derived from D1 | SHA-256 `780718e0a16801d18815c0e4db04266eb49695e146fa28b24292569f9e27f99c`; derived by `condition_catalog_sha256` in S7 from the exact registered conditions. |
| P1 | `docs/M36_PHASE2B_PREREGISTRATION_PROPOSAL.md` | SHA-256 `c633f7e802d350095dff0388b31805bc45c0a246f7a3b994fece4303630da0b0`. |
| S1 | `docs/M36_PHASE2B_AMENDMENT_SPECIFICATION.md` | Reviewed specification; SHA-256 `ecfe6fafbed4355728fa2bc5bdaffc605cbd204c27aea5df2eb702fab613ab77`. |
| S2 | `satellite_discovery/m25_read_coverage.py` | SHA-256 `fc78491ff60c77dbd234a204bd198dd5951d43fda3830ff6151aff4aec89c47f`. |
| S3 | `satellite_discovery/m19_benchmark.py` | SHA-256 `a1cf460a83fc7851bb7d7c6242aeead97403f267aea76a9d94f470184b9be325`. |
| S4 | `satellite_discovery/m36_manifest_builder.py` | SHA-256 `38f5c637a08db5261750aecb0c928bca99e509012d793e54a847fae23d9c1bb3`. |
| S5 | `docs/M36_PHASE2B_SCIENTIFIC_INTEGRATION.md` | SHA-256 `ce0a4522185949c50ee1f03c05d48aabcf8495915387adb0f9b8b9f3baa85e97`. |
| S6 | `docs/M36_PHASE2B_RUNNER_REVIEW.md` | SHA-256 `25ee14b2b86e3c8ccaa4706d4f01d1eabd8a967aebb11cbcd771497c12b96803`. |
| S7 | `satellite_discovery/m36_runner.py` | SHA-256 `0e4f11bb4ddb8c1adff97b075a71216aa1c860d8c2ba8869561fc3a514cc146a`; catalog derivation and registered-condition validation. |

The condition catalog is not a separate frozen file: C1 is the digest of the
canonical catalog derived from D1 by S7. If the design or catalog changes, or
the derivation version changes, this record's source scope must be reviewed
again. No private evaluator source map, seed, split mapping, or generated
sequence is included.

## Proposed decisions

### 1. Target/background read-record ratio

**Status: PENDING APPROVAL.**

- **Proposed decision:** Measure primary FASTQ records after generation and
  before filtering. Let target records be
  `T = ceil(C × L_target / R)`, using the registered target coverage rule, and
  require exactly `B = 9 × T` synthetic-background records. Allocate `B`
  across background sources in proportion to source length using the
  largest-remainder rule; break equal remainders by ascending UTF-8 bytewise
  canonical source ID. Exclude `technical_reference` records from both counts,
  report them separately, independently recount FASTQ records, and fail closed
  as `GENERATOR_INVALID` on any ledger/FASTQ mismatch.
- **Scientific rationale:** This makes the registered 1:9 label measurable in
  the unit directly allocated by the generator while preserving technical
  references as a separate role.
- **Preregistration classification:** Proposed **change requiring amendment**,
  unless an authoritative approval source already fixes this exact denominator,
  stage, allocation, and failure policy. The frozen label alone does not define
  these details.
- **Interpretation and analysis:** This is a synthetic read-record ratio, not
  10% of all FASTQ records, output bases, or coverage. Length-weighted
  allocation can create source-specific depth/composition differences. Keep
  the family as the inferential unit; reads and the two technical repeats are
  not independent observations.
- **Applies to:** D1, C1, P1, S1, and S2.
- **Independent tests before implementation acceptance:** Independently parse
  FASTQ and compare with the role ledger; test exact 1:9 totals, zero and
  fractional allocation remainders, equal-remainder ID ordering, one and
  multiple backgrounds, technical-reference exclusion, omitted/duplicate IDs,
  and `GENERATOR_INVALID` failures.

### 2. Composition-matched periodic low-complexity sequence

**Status: PENDING APPROVAL.**

- **Proposed decision:** For each registered family, apportion the baseline
  target's 900-nt base counts to a 20-nt motif by Hamilton's largest-remainder
  rule, with ties ordered `A,C,G,T`. Fisher–Yates shuffle from index 19 down
  to 1 using 19 accepted bounded-integer draws per candidate. Reject
  nonprimitive motifs and immediately use the next 19 accepted draws, with no
  intervening discard. Stop after 1,000 candidates and report
  `GENERATOR_INVALID` if none is primitive. Repeat an accepted motif 45 times.
  Require a 900-nt `ACGT` sequence, exact apportioned motif counts, exact
  period 20, per-base fraction difference at most 0.05, and absolute base
  Shannon-entropy difference at most 0.15 bits; verify its deterministic digest
  under the proposed stream version.
- **Scientific rationale:** This creates a defined artificial periodic stress
  while approximately matching broad base composition; it does not claim to
  model natural low-complexity genomes.
- **Preregistration classification:** Proposed **change requiring amendment**;
  the original condition did not freeze a sequence recipe, motif length, RNG
  behavior, or these acceptance criteria.
- **Interpretation and analysis:** Periodicity and short-range correlations
  are deliberately changed and may interact with assembly and filtering.
  Some compositions cannot meet the acceptance rules; such cases remain
  `GENERATOR_INVALID` rather than being tuned, replaced, or omitted. Preserve
  the existing 12-family paired analysis; sequence metrics are descriptors,
  not additional observations.
- **Applies to:** D1, C1, P1, S1, and S3.
- **Independent tests before implementation acceptance:** Independently verify
  Hamilton counts, exact period and entropy/fraction bounds, feasibility
  witnesses and impossible profiles; replay the public two-candidate retry
  vector and the 1,000-candidate boundary; verify deterministic bytes across
  repeats and paired assembler arms. Use synthetic sequences only.

### 3. Clustered substitutions with preserved per-read counts

**Status: PENDING APPROVAL.**

- **Proposed decision:** Preserve registered insertion/deletion semantics.
  Delete source positions first, then set
  `k = min(round_half_to_even(R × s), surviving_positions)`. Select uniformly
  among eligible contiguous 20-position windows containing at least `k`
  survivors, then select exactly `k` surviving positions without replacement
  and substitute each with one of the other three bases uniformly. Apply
  insertions afterward. If no valid window exists, fail as
  `GENERATOR_INVALID`; do not widen the window or fall back to dispersed
  substitutions.
- **Scientific rationale:** This changes substitution placement while
  preserving the registered per-read count and keeping indels outside the
  placement change.
- **Preregistration classification:** Proposed **change requiring amendment**;
  the original condition does not specify event classes, spatial scale, or
  placement law.
- **Interpretation and analysis:** This is a synthetic 20-nt clustering stress,
  not a sequencing-platform error model. Clustering can interact with read
  starts, deletions, filtering, and coverage. Per-read event counts validate
  the generator but do not enlarge the family-level sample size.
- **Applies to:** D1, C1, P1, S1, and S2.
- **Independent tests before implementation acceptance:** Independently
  reproduce M25's per-read substitution count; test boundary and impossible
  windows, post-deletion eligibility, exact counts, positions, replacement
  bases, qualities/origins, insertion/deletion marginals, and the declared
  clustering statistic.

### 4. Domain-separated random streams and stable source IDs

**Status: PENDING APPROVAL.**

- **Proposed decision:** For RNG v1, preserve existing approved non-negative
  integer seeds unchanged in the private source map and encode each as exactly
  32 unsigned big-endian bytes, zero-padded on the left; require
  `0 <= n < 2^256` and never coerce out-of-range values. Derive
  `K_root = SHA256(UTF8("M36/2B/RNG/v1") || 0x00 || seed32)` and
  `K_child = HMAC-SHA256(K_root, UTF8(domain_label))`; use S1's versioned
  HMAC stream blocks and rejection sampling for bounded integers. Use
  `family-target-<registered-family-id>` for targets,
  `synthetic-background-<registered-family-id>-<source-key>` for backgrounds,
  and `technical-reference-<registered-family-id>-<source-key>` for technical
  references. The registered targets are `family-target-f01` through
  `family-target-f12`. Each `<source-key>` must match
  `[a-z][a-z0-9]*(?:-[a-z0-9]+)*`, be at most 48 characters, and be assigned
  before generation to one immutable logical source in the restricted
  inventory. Full IDs must be unique; do not derive IDs from list positions.
- **Scientific rationale:** Domain separation and stable identifiers prevent
  random-stream coupling and make source/read outputs insensitive to unrelated
  source insertion or processing order. They do not prove statistical
  independence.
- **Preregistration classification:** Proposed **change requiring amendment**;
  the current manifests and M25 shared-stream behavior do not define this
  derivation or byte mapping. Existing integer manifests must not be silently
  reinterpreted.
- **Interpretation and analysis:** This changes generated bytes for registered
  units but not their assignments or the family-level inferential unit. The
  existing source-map schema remains unchanged: `family_id` identifies family
  seed/split rows, read seeds use registered assignment tuples, and
  `provenance.source_id` identifies the approval source document. Source IDs
  are a separate restricted identity layer and must not expose private
  mappings.
- **Applies to:** D1, C1, P1, S1, S4, S5, S6, and S7.
- **Independent tests before implementation acceptance:** Use synthetic seed
  values only to test encoding boundaries, invalid types/ranges, HMAC vectors,
  unbiased sampling, stream/domain separation, and independent CPython 3.11.11
  and Node.js 22.13.1 conformance. Test malformed/duplicate source IDs and
  source-order/unrelated-source invariance; verify paired assemblers receive
  identical bytes. Do not access or create private evaluator seeds for these
  checks.

### 5. Uniform read starts, coverage, and indel semantics

**Status: PENDING APPROVAL.**

- **Proposed decision:** For source length `L`, read length `R`, and coverage
  `C`, require `L >= R > 0`; compute `N = ceil(C × L / R)` with exact decimal
  arithmetic. For `N > 0`, use
  `s_i = round_half_to_even(i × (L-R) / max(1,N-1))` for `i=0..N-1`.
  Retain repeated starts when `N > L-R+1`; never deduplicate or resample. Report
  nominal depth separately from realized depth/breadth. For each read, delete
  each source position independently with probability `d`; substitute
  `min(round_half_to_even(R × s), survivor_count)` surviving positions without
  replacement unless the approved clustered model in decision 3 is used; then,
  after each surviving source base, independently insert at most one uniformly
  selected `A,C,G,T` base with probability `i`. Reconcile output length and
  source-origin accounting.
- **Scientific rationale:** This makes the frozen `uniform` interpretation
  explicit as deterministic tiling and separates nominal coverage, source
  exposure, output bases, and realized breadth.
- **Preregistration classification:** **Conditional.** This is a clarification
  only if the controlling approved source confirms the exact formula and
  semantics. A changed start/count result versus M25, or any changed indel
  semantics, is a **change requiring amendment**.
- **Interpretation and analysis:** Deterministic tiling differs from iid random
  starts and can reduce random gap variability. Repeated starts are intentional
  when requested counts exceed valid positions. Report coverage metrics as
  outcomes, not additional observations; maintain the family-level analysis.
- **Applies to:** D1, C1, P1, S1, S2, and S7.
- **Independent tests before implementation acceptance:** Compare an
  independent reference calculator with M25 across the complete registered
  grid and boundary fixtures (`L=R`, `N=0`, `N=1`, `D=0`, half ties, frozen
  `L=900,R=100,C=48`, 75/150-nt arms, and coverage 24/80). Compare exact
  starts, counts, depth arrays, breadth, output lengths, and source-coordinate
  event accounting. Record any difference as an amendment requirement.

## Design-owner approval checklist

Every item remains **PENDING APPROVAL** until the design owner explicitly
records a choice. For each item, select **approve**, **revise**, or **reject**,
confirm the proposed classification, and supply any revision or rationale.

| Item | Owner decision | Classification confirmed | Notes / required revision |
|---|---|---|---|
| 1. Read-record ratio | PENDING APPROVAL | PENDING APPROVAL | |
| 2. Periodic motif | PENDING APPROVAL | PENDING APPROVAL | |
| 3. Clustered substitutions | PENDING APPROVAL | PENDING APPROVAL | |
| 4. Random streams and source IDs | PENDING APPROVAL | PENDING APPROVAL | |
| 5. Starts, coverage, and indels | PENDING APPROVAL | PENDING APPROVAL | |

**Owner name:** PENDING  
**Approval date:** PENDING  
**Approval reference:** PENDING

Approval of this record would document scientific choices only. Before
implementation acceptance, complete the independent tests listed above. Any
approved changes must then be entered as a separately reviewed preregistration
amendment with updated generator/version and input digests. This record does
not change D1 or C1 and does not authorize Phase 2B execution. Execution
requires separate authorization and all existing operational gates.
