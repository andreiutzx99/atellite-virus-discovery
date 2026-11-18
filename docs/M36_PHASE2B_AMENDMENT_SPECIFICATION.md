# M36 Phase 2B decision-ready amendment specification

**Status: PROPOSED FOR INDEPENDENT SCIENTIFIC REVIEW; NOT APPROVED OR FROZEN.**
This document makes the preferred options in
[`M36_PHASE2B_PREREGISTRATION_PROPOSAL.md`](M36_PHASE2B_PREREGISTRATION_PROPOSAL.md)
algorithmically reproducible for review. It is not an amendment, execution
authorization, or change to the registered design. The frozen JSON, catalog,
digest, and code remain unchanged. Phase 2B remains **NO-GO / NOT RUN**.

The values below are proposed specifications, not claims about biological
sequencing. An independent reviewer and the design owner must approve or revise
them before an amendment is written. If approved, the decision record must state
whether each item clarifies an authoritative existing definition or changes the
registered design.

## Scope and preserved design

This specification does not change the 12 synthetic sequence families, the
4 development / 4 tuning / 4 held-out split, two technical repeats, the
registered family-condition-assembler assignments, the 520-attempt ceiling,
endpoints, exclusion rules, or planned family-level statistical comparisons.
There are no new cases or attempts. A technical repeat remains a repeated
measurement within a family, not an independent unit. No seed values, split
assignments, truth sequences, registered inputs, or private source map are
included. Do not run the matrix, enable Phase 2B, merge the PR, use biological
data, promote production behavior, or start M37.

The proposed algorithms would affect generation and therefore require a new
generator version and input digests. Options 2–4 and any replacement of the
current M25 random-number behavior are preregistration amendments. Option 1
requires an amendment unless a controlling approval source already defines the
same read-record denominator and allocation. Option 5's interpretation can
clarify the frozen `uniform` setting only if the controlling source confirms it;
replacing M25's current start calculation, or changing coverage/error
semantics, is an amendment. No current choice is silently treated as approved.

## 1. Exact target/background read-record ratio

### Current frozen definition

The frozen condition is labelled `target_background_abundance_1_to_9`. It does
not define whether the ratio is read records, output bases, or coverage. M36's
existing audit concept counts `target_truth` and `synthetic_background` read
records and excludes `technical_reference`, but that implementation is not an
approval of the denominator.

### Proposed precise definition

1. Count primary FASTQ records after all generator transformations and
   immediately before any filtering, assembly, or downstream handoff. A record
   is one complete FASTQ entry, independent of its output length.
2. Assign each generated record exactly one immutable origin role:
   `target_truth`, `synthetic_background`, or `technical_reference`. Count only
   the first two roles. Technical-reference records are excluded from both
   numerator and denominator and reported separately.
3. Let `T` be the number of target-truth records. Compute the target count using
   the registered coverage rule for each target sequence:
   `T = ceil(C × L_target / R)`, where `C` is nominal target depth, `L_target`
   is source length, and `R` is configured source-read length. Do not round this
   value or alter it to satisfy the ratio.
4. Set the required number of synthetic-background records to `B = 9 × T`.
   Where multiple background source records exist, allocate `B` across them in
   proportion to their source lengths. For each background `j`, compute
   `q_j = B × L_j / sum(L)`, assign `floor(q_j)`, then assign remaining records
   in descending fractional-remainder order; break ties by the UTF-8 bytewise
   ascending stable background-role identifier. This largest-remainder rule
   preserves the exact total and is independent of iteration order.
5. Use the normal registered start rule for each source's assigned count.
   Record the realized per-source counts and realized coverage; do not describe
   the background depth as matched to target depth. This construction changes
   background exposure in order to define abundance by records.
6. Validate the role ledger against FASTQ IDs and record counts before
   filtering. Require `T > 0`, `B > 0`, unique IDs, one role per ID, no missing
   or unaccounted FASTQ records, and exact integer equality `B == 9*T`.
   Independently recount FASTQ records and compare with the ledger. A mismatch
   blocks the condition; do not drop, duplicate, relabel, or top up reads to
   make it pass. Preserve the invalid input and report `GENERATOR_INVALID`.
7. Report technical-reference record count, target/background output-base
   totals, source-base totals, per-source counts, read-length summaries, and
   post-filter counts separately. None substitutes for the registered ratio.

### Scientific implications and tests

This estimates a synthetic 1:9 source-read-record allocation, not 10% of all
FASTQ records (because technical references are excluded), not 10% of emitted
bases, and not a coverage ratio. Length-weighted allocation can create
background depth differences and composition/source-specific effects; report
these as potential confounders. Test zero and non-integral allocation
remainders, equal remainders and tie order, one and multiple background
records, FASTQ/ledger omissions and duplicates, technical-reference exclusion,
and exact ratio failure. Recompute all counts using an independent parser.

**Amendment decision:** required if no authoritative approval record already
specifies this exact denominator, allocation, stage, and failure policy.

## 2. Composition-matched periodic low-complexity sequence

### Current frozen definition

The registered condition names a low-complexity stress sequence but freezes no
construction, motif length, complexity statistic, or acceptance criteria. M19's
`AAAAC` sequence is an example, not an approved M36 recipe.

### Proposed precise definition

For each of the 12 already-registered families, use that family's 900-nt
synthetic baseline target as the composition reference. Do not use split labels,
read seeds, assembly outcomes, M27 filtering results, or any held-out result in
construction.

1. Set target length to the frozen 900 nt and motif length to exactly 20 nt.
   Let `c_A,c_C,c_G,c_T` be base counts in the family's baseline target and
   `p_b = c_b / 900`.
2. Allocate 20 motif positions by Hamilton's largest-remainder apportionment:
   set `x_b = 20*p_b`, initially assign `floor(x_b)`, then assign remaining
   positions by descending fractional remainder, ties in `A,C,G,T` order.
   Thus motif composition is the closest integer 20-base composition to the
   family target composition under that tie rule.
3. Construct the multiset of allocated bases in `A,C,G,T` order. Shuffle it
   using Fisher–Yates from index 19 down to 1. At step `i`, draw an unbiased
   integer `j` in `[0,i]` from the family's domain-separated
   `low_complexity/motif` stream specified in section 4, then swap positions
   `i` and `j`. Do not retry based on downstream performance.
4. Accept only a primitive 20-base motif: for each proper divisor `d` of 20,
   require at least one `motif[i] != motif[i mod d]`. Otherwise consume the next
   twenty draws from the same stream and repeat the shuffle, up to 1,000
   candidates. If none is primitive, fail the family condition as
   `GENERATOR_INVALID`; do not substitute another algorithm.
5. Repeat the accepted motif exactly 45 times to produce 900 nt. Preserve the
   resulting sequence as the low-complexity target for both technical repeats
   and all registered paired downstream comparisons. Its digest is a generated
   input digest, not a family or seed value.
6. Record and validate: (a) exact length 900 and alphabet `ACGT`; (b) primitive
   period exactly 20; (c) motif counts equal the apportioned counts; (d) each
   base fraction differs from the baseline target by at most 0.05; (e) base
   Shannon entropy `H1 = -sum(p_b log2 p_b)` for both source and stress target,
   with absolute difference at most 0.15 bits; and (f) deterministic sequence
   digest under the specified stream version. Zero-frequency terms contribute
   zero. Define periodicity as the minimum exact period of the 900-nt string;
   report the number of distinct linear 10-mers and 20-mers (using all
   overlapping windows, without circular wraparound). These are descriptive
   metrics; the acceptance criteria are the exact period and the bounds above.
   If any criterion fails, fail the family condition as `GENERATOR_INVALID`;
   do not tune thresholds or choose another motif length. Also report the
   generated and post-filter read counts as outcomes; do not use them as
   construction criteria or tune M6 thresholds.

### Scientific implications and tests

The 20-nt period is an explicit artificial stress, not a model of natural
low-complexity genomes. Approximate composition matching controls broad base
composition but may not match dinucleotide frequencies; periodicity and
short-range correlations are intentionally changed and can interact with
assembly and M6 triage. The family remains the independent unit, with one
paired condition per existing family; no family or repeat is added. Validate
all 12 family sequences without exposing split membership, test largest
remainder ties, primitive-period rejection and retry determinism, entropy and
fraction bounds, exact-repeat construction, and identical bytes across repeats
and paired assembler arms.

**Amendment decision:** required. The recipe, motif length, seed domain,
complexity acceptance rules, and generated input bytes are new frozen details.

## 3. Clustered substitutions with preserved per-read counts

### Current frozen definition

The condition says “alternate error-position distribution, same rates” but
does not identify event classes or spatial rules. M25's baseline applies
per-source-base deletion and insertion Bernoulli draws and chooses a rounded
substitution count from surviving positions without replacement.

### Proposed precise definition

Only substitution placement changes. Insertion and deletion rates and their
M25 semantics remain unchanged. For each read of configured source length `R`:

1. Apply the registered deletion rule first: independently delete each source
   position with probability `d`, preserving source-coordinate order.
2. Set the substitution count `k = min(round_half_to_even(R*s), number of
   surviving source positions)`, where `s` is the registered substitution
   rate. `round_half_to_even` is Python-compatible ties-to-even, specified
   mathematically rather than delegated to a runtime. This count is exactly the
   M25 per-read count for the same source length and rate.
3. If `k == 0`, make no substitution. Otherwise define candidate windows as all
   contiguous 20-position windows in the original read coordinates whose
   surviving positions number at least `k`. Choose one candidate window
   uniformly with an unbiased integer draw from the
   `substitution_window` stream. Boundaries are inclusive: valid starts are
   `0..R-20`. If no candidate window exists, fail the read and condition;
   do not widen the window or fall back to dispersed substitutions.
4. Choose exactly `k` surviving positions uniformly without replacement from
   the chosen window using the `substitution_positions` stream. This forbids
   substitution at deleted positions. Insertions are not eligible substitution
   positions because they do not exist yet.
5. At each chosen position, replace the source base uniformly with one of the
   other three bases using the `substitution_bases` stream. Mark each changed
   base with quality `5`; unchanged bases retain quality `I`.
6. Then apply the existing insertion rule after each surviving source base:
   independent Bernoulli probability `i`; when inserted, choose one base
   uniformly from `A,C,G,T`, mark it quality `5`, and set its origin to null.
   The insertion process does not alter the already fixed substitution count.
   Preserve deletion, substitution, insertion ordering in the origin map.
7. Report `R`, `k`, deletion count, insertion count, selected window start,
   substituted source coordinates, per-read output length, and realized event
   rates. Any count mismatch, event on a deleted coordinate, substitution
   outside the selected window, or malformed origin/quality map invalidates the
   generator condition; do not retry a read.

### Scientific implications and tests

This is a 20-nt clustered synthetic substitution stress. It is not a
sequencing-platform error model. For 100-nt reads at the frozen 0.02 rate,
`k` is 2; at the zero-substitution registered arm, `k` is 0. A fixed window
length imposes a spatial scale and can interact with read starts, deletions,
quality filtering, and coverage. Validate exact count preservation against an
independent implementation of M25's count rule, window eligibility after
deletions, boundary starts, impossible windows, no collisions with deleted
positions, replacement bases, qualities/origins, unchanged insertion/deletion
marginals, and a predeclared clustering statistic: maximum pairwise distance
between substituted source coordinates must be `<20` for `k>1` and zero for
`k<=1`. Compare per-family outcomes, not reads as independent observations.

**Amendment decision:** required. The event scope, 20-nt window, conditional
eligibility rule, and placement law are new design parameters.

## 4. Domain-separated deterministic random streams

### Current frozen definition

M36 requires separate family/read seed roles and independent technical-repeat
read seeds, but does not define the derivation algorithm or random-number
implementation. M19/M25 use Python `random.Random` with additive analysis-ID
seed derivation and a shared generator across roles; this is not a
cross-runtime, domain-separated specification.

### Proposed precise definition

The evaluator provides each registered family seed and each registered
family-condition-repeat read seed as exactly 32 secret bytes in the restricted
sidecar. Do not generate, publish, or copy these values into this document,
source control, analysis inputs, or analyst-visible logs. For each root seed:

1. Derive `K_root = SHA256(UTF8("M36/2B/RNG/v1") || 0x00 || seed32)`.
2. A child stream has a fixed ASCII domain label. Encode it as UTF-8, require
   nonempty bytes and no NUL. Derive
   `K_child = HMAC-SHA256(key=K_root, message=UTF8(domain_label))`.
   Required labels are:
   `family/target/v1`, `family/background/<stable-source-id>/v1`,
   `family/technical-reference/<stable-source-id>/v1`,
   `low_complexity/motif/v1`, and
   `read/<registered-block-id>/<registered-condition-id>/<repeat-id>/<event>/v1`.
   `<event>` is one of `starts`, `deletions`, `substitution_window`,
   `substitution_positions`, `substitution_bases`, `insertions`, or
   `insertion_bases`. Identifiers use their frozen registered ASCII spellings;
   they are not derived from list position, processing order, opaque case IDs,
   or split names. Separate registered root seeds are used for family sequence
   generation and each technical repeat's read generation.
3. Generate block `n` (zero-based unsigned 64-bit big-endian) as
   `HMAC-SHA256(key=K_child, message=UTF8("M36/2B/STREAM/v1") || 0x00 ||
   uint64_be(n))`. Concatenate each 32-byte block in ascending `n` to provide
   bytes. A stream may not wrap its 64-bit counter.
4. For a uniform integer in `[0,m)`, require `1 <= m <= 2^64`; read 8 bytes as
   unsigned big-endian `x`; let `limit = 2^64 - (2^64 mod m)`. Reject `x >=
   limit`, consume the next 8 bytes, and return `x mod m`. Do not use modulo
   without rejection. For a uniform choice from an ordered list, use that
   integer as its zero-based index. Each domain has its own counter initialized
   to zero; draws in one domain do not advance another.
5. Fisher–Yates is descending-index swaps as specified in section 2.
   Without-replacement sampling uses partial Fisher–Yates on an ordered
   ascending candidate list, taking the first `k` elements. Bernoulli events
   compare an unsigned 64-bit big-endian draw `x` against
   `floor(p*2^64)`; accept exactly when `x < floor(p*2^64)`. Rates are parsed
   as exact decimal rationals from the frozen JSON lexical value, not binary
   floating-point approximations.
6. Text manifests are UTF-8; domain labels are ASCII; all integers in stream
   derivation are unsigned big-endian. Sequence bytes are uppercase ASCII
   `ACGT`. These rules define the byte stream independently of Python, NumPy,
   platform, locale, and filesystem order.

### Public non-secret test vector

The following vector uses the public test-only seed bytes `00 01 ... 1f`; it is
not an evaluator seed and must never be substituted for one:

| Value | Expected hex |
|---|---|
| `K_root` | `225ca5009618c67cfec3d9e72174eae9f4fb2250753143bd74b0f06d81583a96` |
| `K_child`, domain `family/target/v1` | `e2123b582b711e2555910b570543a54541a2da5b1d219bc769e62fd94af69a64` |
| block 0 for that child | `bc00f654834b413c131eb88afbbc0a0cd786c75319d7209da82cf8fa8687df76` |
| `K_child`, domain `read/positive_recovery/condition-01/repeat-01/substitution_positions/v1` | `261a2f83fea132fa1d32da943e8e36e46a3ddc4682101b4ae595a036e1ca16b8` |
| block 0 for that child | `64c2570dca4e79bdd08b1c6d0ebf02949bcc8c163dc0ff06d109c35fbdddad9c` |

The second label above is an illustrative test label only; `condition-01` is
not asserted to be a registered identifier. Actual stream labels must use the
exact registered identifiers and event names. Test vectors must
be implemented independently in at least two languages/runtimes before
approval. Verify the full 32-byte outputs, rejection sampling, boundary
probabilities `p=0` and `p=1`, and that changing one domain or root seed
changes the child stream. Domain-separation tests are not a statistical
independence proof; the family is still the inferential unit.

### Scientific implications and tests

This algorithm removes shared-stream/order coupling and gives reproducible
substreams, but does not itself establish biological randomness or family
independence. Test stable bytes when unrelated conditions are added or removed,
distinct child keys for all distinct labels, repeated labels produce identical
bytes, no counter wrap, deterministic candidate selection, source and FASTQ
ledger agreement, and byte-identical paired assembler inputs. Record the
algorithm version, public test-vector result, and input/output digests; never
record private seed bytes or split mapping in public artifacts.

**Amendment decision:** required unless an authoritative approved source already
specifies an equivalent versioned derivation, byte encoding, and PRNG.

## 5. Uniform read starts, coverage, and indel semantics

### Current frozen definition

The frozen M36 JSON says `read_start_mode: uniform`. The current M25
implementation computes `N = ceil(C*L/R)` and for `N` reads uses Python's
`round(i*(L-R)/max(1,N-1))`. It uses Python's ties-to-even rounding. The M36
generator audit fixture has also been described as using `random`; that
contradiction must be resolved against the controlling approved source. M25
`uniform` starts are deterministic tiling, not independent random sampling.

### Proposed precise definition

For each target or background source of length `L`, configured source-read
length `R`, and nominal depth `C`:

1. Require integer `L >= R > 0` and finite `C >= 0`. Set
   `N = ceil(C*L/R)` using exact decimal-rational arithmetic for `C`.
   In the 1:9 abundance condition, use section 1's exact target and background
   allocation instead of independently recalculating background counts from
   nominal depth; report the resulting background exposure.
   If `N == 0`, produce no reads. If `N > 0`, define `D = L-R` and
   `s_i = round_half_to_even(i*D/max(1,N-1))` for integer
   `i=0..N-1`. This is Python-compatible ties-to-even rounding. Starts are
   zero-based, inclusive, and read intervals are `[s_i,s_i+R)`.
2. Require every start in `[0,L-R]`. When `N <= L-R+1`, require starts to be
   strictly increasing and unique. If a future design permits more reads than
   valid start positions, the formula may repeat starts; that situation must
   be explicitly preregistered rather than silently deduplicated. The current
   frozen M36 target settings do not require this exception.
3. Nominal depth is the requested `C`. Report nominal source-read depth
   `N*R/L`, source-window exposure `sum_i R / L` (which equals `N*R/L` here),
   and mean source-coordinate depth computed from the clipped intervals.
   Report breadth `count(position depth > 0)/L`, gaps, minimum/maximum per-base
   depth, terminal depth, and duplicate starts separately. Do not call `C` or
   `N*R/L` realized uniform depth.
4. Apply errors per read in source coordinates. At rate `d`, independently
   delete each of its `R` source positions with Bernoulli probability `d`.
   Among survivors, substitute exactly
   `min(round_half_to_even(R*s), survivor_count)` positions uniformly without
   replacement (unless the approved clustered model in section 3 is used).
   After each surviving source base, independently insert one base with
   Bernoulli probability `i`; multiple insertions after one source base are not
   allowed. Each inserted base is independently uniform over `A,C,G,T`.
   Insertion and deletion are per-source-base probabilities, not rates per
   emitted output base. Keep insertion/deletion processing and base-origin
   ordering explicit. Output length is `R - deletions + insertions`.
5. Report, per read and aggregate, source start and interval, `R`, output
   length, substitution/deletion/insertion counts, source bases sampled,
   output bases, role-specific counts, distinct-base breadth, and coverage
   gaps. Use the section 4 random-stream domains for errors. Paired assemblers
   receive byte-identical FASTQ inputs, including quality strings and order.

### Independent M25 verification

Before accepting this definition, implement a standalone reference calculator
that does not call M25. Compare it with M25 for the complete registered
parameter grid and boundary fixtures: `L=R`, `N=0`, `N=1`, `D=0`, even and
odd half ties, the frozen `L=900,R=100,C=48` case, the 75/150-nt arms, and
coverage arms 24 and 80. Confirm exact start lists, lengths, counts, coordinate
depth arrays, and breadth. Separately compare M25's source-coordinate
deletion/substitution/insertion accounting against the proposed semantics.
Because the domain-separated generator intentionally changes RNG streams and
M25 currently uses a shared `random.Random`, byte-for-byte output equality
with current M25 is not an acceptance criterion; document every intentional
difference. The independent check establishes semantic agreement, not approval.
M25 uses runtime floating-point `ceil` and `round`; exact decimal arithmetic
is the proposed normative rule. If any registered source/coverage combination
gives a different count or start than M25, record that difference as an
amendment requirement rather than calling the new result unchanged M25 behavior.

### Scientific implications and tests

Evenly spaced starts reduce random gap variability relative to iid starts and
can change assembly outcomes. Indels change output length and emitted bases
without changing the pre-error source-read count. This design therefore keeps
nominal coverage, source exposure, output bases, and realized breadth distinct.
Test exact starts and arithmetic, allowed boundaries, per-base depth, all
event/origin accounting identities, zero and unit indel probabilities, empty
survivor failure, quality length equality, and FASTQ/ledger agreement. Preserve
the 12 family units and paired family-level analysis; do not use per-read
counts as independent observations.

**Amendment decision:** the formula and metric definitions may be a clarification
only if the approved source confirms them exactly. Changing `uniform` to
`random`, the start formula, count formula, or indel semantics requires an
amendment and review.

## Evidence, interpretation, and approval gates

M34 and M35 are synthetic diagnostics only. M34's 5/35 target-absent result
refers to eligible cases; all five eligible near-target cases were prioritized,
but three of eight generated near-target cases were unevaluable. Its four
SPAdes failures, including a substitution-only case, are execution failures,
not measured reconstruction losses. M35's three exact-positive controls had no
supported assembly and are unevaluable, not negative; its 26/28 SPAdes failures
across 14 settings do not prove a mechanism. These observations motivate
diagnostic controls but do not establish biological sensitivity, specificity,
platform error behavior, or causal mechanisms. Do not tune these proposals to
recover or explain those results.

Before any amendment, the design owner must supply the controlling approval
source or explicitly approve a proposed change. An independent scientific
reviewer must assess confounding, endpoints, validation, and the amendment
classification. Record the reviewer/approval provenance and exact generator
version. Then separately amend and validate the frozen design, preserving the
12 families, 4/4/4 allocation, technical-repeat treatment, registered
comparisons, and 520-attempt ceiling. Execution still requires separate user
authorization and all existing operational gates. Until then, all proposed
values remain review-only and the registered matrix remains disabled and
**NOT RUN**.
