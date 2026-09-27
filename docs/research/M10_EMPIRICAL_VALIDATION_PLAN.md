# M10 empirical validation plan: synthetic and offline

**Status: proposed validation protocol; not yet executed.** This plan specifies
software experiments on generated artificial nucleotide strings to select a
minimal M10 architecture-method baseline. It uses no biological candidate
datasets, downloaded sequences, or reference databases. It does not implement
M10 or set biological thresholds.

The plan is a companion to the
[M10 architecture design research](M10_ARCHITECTURE_DESIGN_RESEARCH.md). Its
method names, states, and acceptance checks are proposed software behavior, not
released interfaces. A successful synthetic run would show that an algorithm
does what its configured software contract says on controlled strings; it
would not show biological sensitivity, specificity, topology, or completeness.

## 1. Decision to be tested

### PROPOSED M10 DESIGN — preliminary method selection

The simplest defensible first implementation is a dependency-free exact
sequence baseline:

1. **Exact prefix/suffix terminal comparison** — enumerate exact suffix-prefix
   overlaps and retain every qualifying overlap under the declared comparison
   alphabet.
2. **Exact direct terminal-repeat comparison** — compare the submitted
   5′-end and 3′-end arms in the same orientation, retaining all lengths and
   coordinates. When its geometry is the same as an exact suffix-prefix
   overlap, link the observations to the same alignment rather than treating
   them as independent evidence.
3. **Exact reverse-complement/inverted terminal comparison** — compare the two
   terminal arms in reverse-complement orientation under an explicit DNA/RNA
   alphabet policy.
4. **Exact internal-repeat search** — enumerate maximal exact direct and
   reverse-complement repeat intervals inside the observed candidate, excluding
   the trivial self-diagonal and canonicalizing mirrored pairs.

These checks are deterministic, require no external executable or database,
expose exact coordinates, and have direct synthetic oracles. Use bounded
resource/output policies and keep low-complexity matches visible with explicit
annotations.

**Do not make approximate/banded end alignment a required first-release
method.** Evaluate it as an optional, separately named method profile. It can
recover controlled substitutions and indels that exact comparisons necessarily
miss, but its score, band, ambiguity, and tie policies introduce additional
ways for short or repetitive strings to have several plausible alignments.
Promote it only after the comparison demonstrates a useful, reviewable gain
under one declared profile and the project approves its reporting and resource
rules. It must never silently replace or erase exact results.

**Defer general local self-alignment** unless the experiment shows a specific
need not met by exact internal-repeat enumeration or the optional banded end
method. Its broader local search can find gapped/partial matches, but also
returns trivial self hits, symmetric duplicates, many overlapping low-complexity
matches, and parameter-dependent ties.

This recommendation is a software-design choice, not a biological claim.
Method-specific output floors and caps are for reporting/resource control only.
They do not establish that a biological repeat or terminal structure exists.

### UNRESOLVED DECISION

The experiments below should quantify the trade-offs before the implementation
profile is frozen. If approximate alignment is useful but produces a large,
hard-to-interpret result set, retain it as an opt-in sensitivity branch rather
than expanding the minimal baseline. No synthetic accuracy value establishes a
universal biological minimum repeat length, mismatch percentage, identity
cutoff, or topology threshold.

## 2. Offline experiment controls

### PROPOSED M10 DESIGN

- Generate every FASTA record, provenance manifest, optional context artifact,
  and expected alignment locally from fixed artificial strings. Do not access
  user candidate data, public biological sequences, or external databases.
- Use a small generator with an explicitly fixed pseudo-random algorithm and
  seed list. Store each generated sequence literal, generator version, seed,
  feature recipe, and expected coordinates with the test result so a fixture
  does not depend on a future PRNG implementation.
- Use distinct synthetic fixture namespaces/IDs that cannot be mistaken for
  candidate or reference accessions. No taxonomy, organism names, or biological
  truth labels are needed.
- For each method, record the exact input hash, method ID/version, configuration,
  expected features, actual coordinates/orientation, aligned and ambiguous
  columns, mismatches, gaps, score when applicable, result count, runtime, and
  completion state.
- Repeat each deterministic case at least twice in clean temporary output
  locations. Compare normalized records byte-for-byte after canonical ordering;
  compare raw process output too if a future external tool is selected.
- Keep the source string unchanged. Derived reverse complements and alignment
  views are temporary analytic representations with explicit orientations, not
  edited candidate bytes.
- Run algorithmic and status tests without installed third-party tools. If a
  local tool is later compared, use only its existing executable against
  synthetic FASTA, record its identity and exact command, and do not download
  or bundle it as part of this plan.

The artificial letters are not a model of any particular genome class. They
provide exact construction truth: where a motif was inserted, how it was
mutated, and what coordinates should be recoverable under the tested policy.

## 3. Synthetic sequence design

### 3.1 Construction vocabulary

Build each sequence from:

- `R`: a generated repeat arm;
- `B`: an unrelated generated body/spacer;
- `U`: a generated unique background with no intentionally inserted repeat;
- `RC(X)`: the reverse complement of an artificial string under a declared
  alphabet;
- `mutate(X, profile)`: a deterministic substitution/indel/ambiguity operation
  that records every changed position.

Core constructions:

| Construction | Artificial string | Intended software geometry |
| --- | --- | --- |
| Exact suffix-prefix overlap / direct end repeat | `R + B + R` | Same-orientation prefix/suffix relation. The geometry can support both an exact suffix-prefix overlap observation and a direct terminal-repeat observation; those are linked views of one alignment, not independent confirmations. |
| Inverted terminal relationship | `R + B + RC(R)` | Reverse-complement relationship between observed terminal arms. |
| Exact internal direct repeat | `U_left + R + B + R + U_right` | Two matching internal intervals that do not touch either sequence end. |
| Exact internal inverted repeat | `U_left + R + B + RC(R) + U_right` | Internal reverse-complement pair that does not touch the ends. |
| Unrelated-end control | `U` with separately constructed nonmatching terminal windows | No intended terminal relationship within the tested scope. The generator records any incidental matches instead of assuming random strings have none. |
| Partial-boundary construction | A known positive construction with one declared boundary absent/unresolved, or a derived string trimmed at 5′ or 3′ | Evidence on observed bytes can be reported, but a missing biological boundary cannot be called a completed terminal no-match. |

For a direct-repeat versus overlap semantic check, give both labels to the
same `R + B + R` fixture and require one shared coordinate-linked alignment.
The sequence alone does not establish whether the observed duplicated ends
represent a native repeat or an assembly representation. The test must not
force a biological distinction from identical coordinates.

For clean negative controls, generate candidate end regions and inspect them
with an independent fixture-oracle routine. Reject or separately label a
generated control if it accidentally contains one of the exact features the
case is meant to exclude. Preserve incidental short matches as challenge
observations; do not silently delete them from results.

### 3.2 Factor levels

Use a staged design rather than a single unmanageable full factorial:

| Factor | Synthetic levels to exercise | Purpose |
| --- | --- | --- |
| Repeat-arm length | 4, 8, 16, 32, and 64 nt where the candidate length permits | Locate indexing/off-by-one errors and observe output growth. These are test points, not minimum biological repeat lengths. |
| Candidate length | 32, 64, 128, 512, and 1,024 nt, plus the shortest valid project-contract sequence | Compare short and longer software inputs and resource behavior. These values are not biological cutoffs. |
| Substitution burden | 0, 1, 2, 5, 10, and 20 changed positions per 100 aligned positions, rounded and explicitly recorded | Measure exact-method loss and approximate-method recovery as identity varies. No percentage is a recommended M10 cutoff. |
| Indels | No indel; one- and two-base insertion/deletion; a longer gap beyond a selected band; indel near an arm boundary | Test alignment coordinate shifts, band limits, and gap accounting. The configured band is a software-search limit only. |
| Ambiguity | No ambiguous letters; one ambiguous site; several distributed sites; ambiguity at the only potential match; ambiguity outside the match | Ensure ambiguity is recorded and not treated as a universal wildcard or silently converted. |
| Complexity | Seeded mixed-base strings at several GC compositions; homopolymer; alternating dinucleotide; short periodic motifs | Measure accidental and combinatorial match growth in low-complexity inputs. Composition is a controlled software stressor, not a biological prior. |
| Boundary state | Declared complete; 5′ partial; 3′ partial; both ends unresolved; sequence bytes unavailable | Verify the method answers only questions supported by observed boundaries. |
| Competing relationships | Equal-length ties; nested exact matches; direct and inverted candidates; multiple distinct terminal windows | Verify all rows, stable ordering, and absence of winner selection. |
| Output/report policy | No output cap; cap below the known row count; cap exactly at a boundary; several configured reporting floors | Verify complete accounting versus truncation and expose the consequence of report floors. |

Use a fixed set of at least 20 recorded seeds for stochastic-background and
mutation-placement cells. Report fixture counts and denominators by factor
combination. This is a repeatability/coverage plan for artificial cases, not a
statistical sample of biological sequences.

For a software reporting-floor sweep, test settings such as 1, 4, 8, and 16
aligned bases as named configuration values. These are deliberately arbitrary
engineering test points. The run manifest must call the setting a
`minimum_reported_span` or equivalent **software/reporting policy**; it must
not call it a minimum terminal repeat, minimum biological structure, or
classification threshold. Preserve either the full detector count or a
content-addressed complete raw event list so that filtering rows for display
cannot masquerade as a no-match.

## 4. Method-by-method experiment matrix

### 4.1 Exact prefix/suffix terminal comparison

Run same-orientation suffix-prefix comparisons for all configured overlap
lengths, not only the longest. Include:

- `R + B + R` fixtures across repeat and candidate lengths;
- nested cases where several prefix/suffix lengths match;
- unrelated-end controls and seeded incidental matches;
- partial boundaries and ambiguous bases at, adjacent to, and outside the
  matching interval;
- low-complexity sequences that generate many possible matching lengths;
- off-by-one cases at the first/last compared base and exactly at each software
  window/reporting limit.

Assertions: emitted interval endpoints match the constructed coordinates;
aligned length, identity numerator/denominator, and coverage denominators are
correct; all distinct overlaps remain visible; no exact result is emitted
across an incompatible or unknown symbol under the declared exact policy; and
low-complexity multiplicity is accounted for.

Expected limitation: any substitution or indel in the queried overlap breaks
an exact match spanning that altered position. A shorter exact sub-overlap may
still be emitted. The result must report that shorter interval rather than
claim that the complete repeated arm was recovered.

### 4.2 Direct terminal repeats

Compare the 5′ and 3′ arms in the same orientation using the same generated
strings as exact prefix/suffix tests plus wider terminal windows containing
unrelated adjacent sequence.

Assertions: preserve both arm coordinates, orientation, total and per-arm
coverage, every nested/partial exact match, and the link to the shared alignment
record where geometry duplicates a prefix/suffix call. The number of evidence
records must not imply two independent observations when both labels refer to
one pairwise comparison.

Expected limitation: identical terminal arms are a sequence pattern only.
The software must not choose between native terminal repeat, duplicated
assembly boundary, or other construction explanations.

### 4.3 Reverse-complement/inverted terminal relationships

Generate `R + B + RC(R)` for each arm length and repeat the comparison with
substitutions, indels, ambiguity, and declared DNA/RNA alphabets.

Assertions: orientation is explicitly reverse-complement; both source
coordinates map back to the original candidate correctly; strand conversion
does not alter the input hash; ties with same-orientation results remain
separate; and IUPAC complement behavior is fully specified and tested.

For `molecule_type=unknown` or mixed T/U strings, require the declared
orientation policy to return an explicit inapplicable/insufficient branch or a
separately named alphabet hypothesis. Do not silently convert T to U or choose
an alphabet based on which yields a longer match.

Expected limitation: an inverted repeat does not identify a mobile element,
cohesive physical ends, or a topology. The evidence object should remain an
orientation-qualified repeat observation.

### 4.4 Exact internal repeats

Scan both same-orientation and reverse-complement internal pairs. Include
non-overlapping repeats, nested repeats, tandem arrays, separated repeats,
overlapping repeat intervals, and matches immediately adjacent to—but not
touching—the sequence ends.

Assertions: exact maximal intervals and coordinates match the fixture oracle;
the self-diagonal is excluded; mirrored query/target rows canonicalize to one
pair; distinct repeat pairs remain distinct; and internal-only matches do not
produce terminal or topology-compatible records.

Expected limitation: exact internal search misses any pair split by a
substitution or indel. Homopolymers and short-period arrays can yield many
overlapping matches. A configured report floor may reduce displayed rows only
as a recorded software policy; cap-induced omission must be marked truncated.

### 4.5 Approximate/banded end alignment

Run against the same exact fixtures, then mutate only one arm at a time.
Evaluate separate profiles for substitutions, single/multiple insertions,
deletions, and gaps near the outer boundary. For each test profile, record
scoring values, band width, end anchoring, ambiguity treatment, tie policy,
maximum reported alignments, and all coordinate transforms.

Assertions:

- The exact fixture is still reported by the exact branch; approximate evidence
  is a separate method result.
- Altered alignments whose required path fits inside the declared band are
  recovered with the expected interval, mismatch/gap counts, identity
  denominators, and orientation.
- A constructed gap wider than the band is not silently recovered by a
  different fallback. If the configured band is fully searched, its outcome
  means only no qualifying path within that exact search policy; preserve an
  applicability/configuration note.
- Multiple equal-scoring paths are deterministically ordered or all retained
  within caps. Tie-breaking cannot depend on dictionary order, platform, or
  thread scheduling.
- Ambiguous columns are counted separately from matches and mismatches under
  the declared policy. They cannot be awarded a definite match merely because
  a wildcard comparison improves the score.
- The method reports all candidate alignments required by its output policy.
  If a reporting cap prevents complete enumeration, status is `TRUNCATED`.

Compare exact-only and approximate outputs on identical input bytes. Tabulate
cases missed by exact comparison but recovered by the configured approximate
method, additional alignments on unrelated and low-complexity controls,
coordinate correctness, ties, output size, runtime, and memory. Do not pool
approximate scores with exact-match counts into one score.

Expected limitation: an approximate match exists relative to a scoring/band
policy, not a universal biological similarity threshold. Several parameter
profiles may return different plausible intervals, especially on repetitive
strings. Retain the profile and competing outcomes.

### 4.6 Local self-alignment where justified

Treat local self-alignment as a comparator, not an assumption. Evaluate a
deterministic local-alignment implementation on exact internal repeats,
mutated/indel-bearing internal pairs, terminal-to-internal matches,
reverse-complement matches, unrelated controls, and low-complexity sequences.

Assertions:

- Remove the trivial self-diagonal and canonicalize symmetric duplicate
  alignments without removing distinct coordinate pairs.
- Preserve multiple local HSPs, exact coordinates, score, aligned length,
  mismatch/gap counts, and configured score/reporting policy.
- Test whether it adds a constructed, intended partial/gapped relationship not
  found by exact internal repeats or bounded end alignment.
- Quantify extra/spurious local rows on unrelated, periodic, and homopolymer
  controls; exercise output cap and deterministic tie behavior.
- Never interpret a local alignment score or E-value from a self-search as
  biological significance.

Keep local self-alignment out of the minimal baseline unless it supplies a
specific, reproducible evidence class that simpler exact/banded methods cannot
provide at acceptable resource/output cost. If it does, make it a separate
method with its own configuration and cache identity.

## 5. Combined challenge cases and status semantics

### PROPOSED M10 DESIGN

Run these end-to-end synthetic cases after each individual method has passed
its coordinate and accounting tests:

| Challenge | Construction | Required software result |
| --- | --- | --- |
| Exact direct terminal relation | Same-orientation repeated end arms | Exact terminal evidence with expected coordinates and shared relation linkage. |
| Exact inverted terminal relation | Opposing ends are reverse complements | Reverse-complement evidence; no topology/classification assertion. |
| Exact internal-only repeat | Matching intervals are away from both ends | Internal repeat only; no terminal-compatible derivative. |
| Approximation-only relation | One arm has controlled substitutions/indel | Exact branch misses the altered span but may retain shorter exact submatches; approximate branch reports only under its named profile. |
| Out-of-band indel | Required alignment path exceeds configured band | No hidden fallback; scoped no-match or insufficient state per declared applicability contract, never a false completed result for unsearched space. |
| Ambiguous potential match | Ambiguous letters occupy otherwise matching positions | Definite matches exclude those columns; ambiguity count and method limitation remain visible. If the only evidence is indeterminate, status is insufficient/ambiguous, not completed no-match. |
| Low-complexity ends | Homopolymer, dinucleotide, or periodic ends | Reported rows are complexity-marked; competing alignments and caps are accounted; no topology conclusion from motif length. |
| Partial 5′/3′ boundary | Declared incomplete boundary or unavailable terminal region | Preserve positive observed alignments; terminal no-match is prohibited for the unobserved boundary and aggregate remains boundary-limited/partial. |
| Several competing repeats | Equal and nested matches in direct and inverted orientations | Retain all rows in stable order; do not pick a best architecture. |
| Output cap below row count | Low-complexity or deliberately multi-hit string exceeds configured cap | Preserve available rows and observed/expected counts; status is `TRUNCATED` (or approved equivalent), never completed no-match. |
| Invalid/corrupt sequence handoff | Bad FASTA, altered sequence hash, contradictory ID, or invalid alphabet | Reject evidence generation for that candidate and return invalid-input accounting; never no-match. |
| Completed unrelated-end control | Valid complete string with no qualifying relationship under full declared policy | Only case that may return completed no-match, scoped to the tested methods, windows, alphabet, and report policy. |

Statuses below are examples; freeze actual names only with the eventual
contract. Assertions must operate on separate input-validity, boundary,
execution, result, and aggregate axes rather than a single overloaded status.

| Condition | Expected handling | Completed no-match allowed? |
| --- | --- | --- |
| Valid, applicable, complete search; every declared window/alignment candidate accounted; no reportable rows under the stated policy | `COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY` or equivalent | **Yes**, only within that exact scope. |
| One or more reported rows and complete accounting | `COMPLETED_MATCHES_REPORTED` | No; report the match result. |
| Input hash/alphabet/manifest invalid or sequence bytes unavailable | `INPUT_INVALID` / `SEQUENCE_UNAVAILABLE` | **No.** |
| Required optional dependency absent | `DEPENDENCY_UNAVAILABLE` | **No.** |
| Process failure, parser error, malformed output, or interrupted run | `EXECUTION_FAILED` / `OUTPUT_INVALID` / `INTERRUPTED` | **No.** |
| Candidate/method too short, alphabet branch not applicable, or information insufficient to assess a requested relation | `INSUFFICIENT_INFORMATION` | **No.** |
| Required terminal boundary is declared partial/unresolved | `PARTIAL_BOUNDARY_LIMITATION` / `INSUFFICIENT_INFORMATION`; retain positive observed rows | **No terminal no-match.** Internal-only scans may separately state their limited observed-fragment scope, but the candidate aggregate remains boundary-limited. |
| Search/output cap prevents full enumeration | `TRUNCATED` with expected/observed counts | **No.** |
| Some independent branches complete while one required branch fails or truncates | Preserve completed rows; aggregate `PARTIAL` | **No aggregate no-match.** |

Add explicit negative assertions to every failure, truncation, insufficiency,
and partial-boundary test: the result object must not contain the completed
no-match value, and the human-readable summary must not paraphrase the state as
“no repeat,” “no terminal structure,” or equivalent. A positive alignment
found before a later branch fails remains linked evidence, but does not upgrade
the failed branch or aggregate to complete.

## 6. Measurements and decision rules

### 6.1 Software measurements

For each method/profile and fixture class, report:

- **Constructed-feature recovery:** count of expected exact or approximate
  pairs found / number of constructed pairs; stratify by arm length,
  candidate length, substitution/indel profile, ambiguity, complexity, and
  boundary state.
- **Coordinate accuracy:** exact agreement of both intervals, orientation,
  repeat length, and indel placement with the fixture construction oracle.
- **Alignment accounting:** aligned bases, identities, mismatches, ambiguous
  columns, gaps/gap opens, denominator choices, and coverage values recomputed
  independently from the artificial strings.
- **Extra rows:** number of reported alignments not part of the constructed
  target set on a negative/challenge fixture; distinguish incidental exact
  substrings from coordinate or parser defects.
- **Status correctness:** expected versus actual input, execution, boundary,
  evidence, truncation, and aggregate states. Count any failure that becomes
  a completed no-match as a release-blocking defect.
- **Determinism:** byte-identical normalized output on repeated identical
  runs; stable tie/order behavior across supported runtime platforms if more
  than one is supported.
- **Resource behavior:** elapsed time, peak memory if available, number of
  candidate alignments considered/emitted, and behavior as length, complexity,
  and repeat multiplicity grow. Record host/runtime; do not turn fixture
  timing into a biological criterion.

Use explicit denominators. Synthetic recovery/extra-row fractions summarize
only the constructed fixture matrix. Do not call them sensitivity, specificity,
or calibrated performance for biological candidates unless a separate,
independent truth-set study later justifies those terms.

### 6.2 Method selection gates

| Method | Recommended first-implementation disposition | Synthetic gate |
| --- | --- | --- |
| Exact prefix/suffix terminal comparison | **Core baseline** | Recover every inserted exact overlap, all configured/nested lengths, exact coordinates, deterministic order, and scoped no-match only after exhaustive completion. |
| Direct terminal repeats | **Core baseline**, linked to the same underlying alignment where it duplicates prefix/suffix geometry | Recover same-orientation end arms; preserve geometry and provenance; do not double-count identical evidence or infer assembly/biological meaning. |
| Reverse-complement/inverted terminal relationships | **Core baseline** | Recover exact ITR constructions and original-coordinate mapping; validate DNA/RNA/IUPAC policy and deterministic orientation; no topology/class inference. |
| Exact internal repeats | **Core baseline** | Recover constructed direct and inverted internal pairs, suppress only diagonal/mirrored duplicates, preserve distinct overlaps, and bound repetitive output with visible truncation. |
| Approximate/banded end alignment | **Optional candidate for promotion; not required by minimal v1** | Must add reproducible recovery for controlled substitutions/indels within the declared band that exact-only misses; coordinate/metric accounting must be correct; ties, ambiguity, outside-band behavior, low-complexity extras, caps, and resources must be acceptable under a reviewed software policy. |
| General local self-alignment | **Deferred unless it demonstrates a distinct need** | Promote only if it adds a well-defined, repeatable evidence class beyond exact internal/banded end methods and diagonal, symmetry, low-complexity, ties, output growth, and resource behavior can be controlled and explained. |

All four exact methods should pass their correctness and status gates before
forming the minimal baseline. A method that is deterministic but produces
unbounded output still requires an explicit cap and truncation behavior. A
method that performs well on simple cases but fails closed-status assertions
does not pass.

For approximate alignment, decide based on the **incremental** recovery and
cost table, not on a score threshold selected to resemble expected biological
behavior. If reviewers cannot state an acceptable output/ambiguity policy
without implying biological meaning, defer the method. Any promotion decision
must record the exact configuration and keep the exact branch available as an
independent method.

### 6.3 Reporting floors and caps

Prefer exhaustive exact detection followed by transparent reporting. If a
`minimum_reported_span` is necessary to control report volume:

1. Keep it in normalized configuration and cache identity.
2. Name and display it as an output/reporting policy.
3. Retain an accounting count of below-floor matches and the tested span range.
4. State that “no match” means no match at or above that software floor under
   the exact configured search, not that no shorter biological motif exists.
5. Never describe the value as an accepted minimum repeat length or as evidence
   for a biological terminal structure.

For a hit/alignment cap, create deliberate over-cap fixtures. If the system
cannot prove that all in-scope records were accounted for, require a
truncation state, expected/observed counts, retained partial rows, and no
completed no-match.

## 7. Cache-isolation validation plan (no cache-code changes)

### PROPOSED M10 DESIGN

When a future M10 stage exists, test its key and workflow reuse using synthetic
candidate artifacts and the current scoped-identity model documented in the
[stage identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md). This plan does not
modify production cache code.

M10 identity should cover, where consumed: exact candidate sequence and
provenance digests; optional M6/M7/M8/M9 context digests; M10 algorithm and
implementation identity; normalized configuration (including ambiguity
policy, windows, scoring, report floors and caps); M10 contract/schema semantic
versions; parser/normalizer versions; dependency-inspection results and exact
tool identity if an optional tool is selected; and any raw/normalized output
accounting. Stage registration identity should describe M10 only, not the
entire registry or package.

Run the following key/reuse controls:

| Change between two otherwise identical synthetic workflows | Expected key/reuse behavior |
| --- | --- |
| No input or M10 identity change | Reuse M10 only if the completed M10 manifest and all output digests verify. |
| M10 algorithm implementation identity changes | M10 key changes; unchanged M6–M9 keys and verified outputs remain reusable. |
| M10 configuration changes (window, ambiguity, repeat floor/cap, alignment mode) | M10 key changes; M6–M9 remain reusable. |
| M10 parser, normalizer, output schema, or named M10 contract-semantic version changes | M10 key changes; M6–M9 remain reusable. |
| Selected optional method's executable/version/digest or dependency-inspector result changes | Affected M10 method/stage invalidates; M6–M9 remain reusable. |
| An optional M7/M8/M9 context artifact actually consumed by M10 changes | M10 invalidates because its declared input changed; upstream stages are not invalidated solely by the M10 dependency. |
| Candidate bytes/hash change in an isolated synthetic M10 input test | M10 invalidates. Any upstream invalidation is asserted only if that upstream stage's own declared inputs changed. |
| A change is made only to unrelated M10 source/registration code | M10 identity remains stable only if the selected dependency/code scope proves the changed code cannot affect M10 outputs; otherwise explicitly include it. |
| Shared artifact-validator or workflow-cache semantics version changes | Apply the broader invalidation defined by the current shared identity policy; this is an intentional exception, not an M10-only change. |
| Saved M10 manifest or output is altered after completion | Verified reuse is rejected; rerun or fail explicitly. It must not reuse or report a no-match from corrupted output. |

For the primary isolation proof, hold M6–M9 input artifacts and stage
configurations byte-identical, change one M10-only identity component at a
time, and verify all four upstream stages reuse their previous integrity-checked
outputs while M10 reruns. Record stage keys, expected action, actual action,
input/output hashes, and reuse verification results. Do not interpret a broad
package-wide source hash or an unrelated registry edit as an M10 dependency.

Also run one end-to-end control where a genuine M6 candidate artifact changes:
M10 must receive the new digest and invalidate. If the M6 change is caused by
changed M6 inputs/configuration, M6 may correctly rerun under its own identity;
that is not evidence of cache leakage. Separate this from the M10-only
isolation test.

## 8. Deliverable from a future validation run

The implementation team should retain an offline validation bundle containing:

- synthetic FASTA fixtures and their deterministic generation recipe;
- an expected-feature manifest with coordinates, orientation, mutation
  history, boundary status, and exact hashes;
- method-by-method configuration and tested parameter matrix;
- raw external-tool output only for any selected external comparator, linked
  to version and invocation; internal methods should retain their native
  deterministic result artifacts rather than inventing external raw output;
- normalized evidence and per-branch completion/accounting;
- coordinate, metric, status, cap, determinism, and cache-isolation test
  results with explicit denominators;
- unresolved ambiguity, extra-row, runtime, and resource observations; and
- a clear statement that all results use artificial sequences and do not
  validate biological performance or topology.

Do not create candidate classifications, topology verdicts, a composite
architecture score, external sequence panels, or biological benchmark claims
from this validation plan.

## 9. Project documents used

- [M10 architecture design research](M10_ARCHITECTURE_DESIGN_RESEARCH.md)
- [Current M10 roadmap scope](../ROADMAP.md)
- [M8 candidate handoff and search contract](../M8_CONTRACT_AND_BLASTN_VALIDATION.md)
- [Stage-scoped cache identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md)

No implementation or experiment has been run as part of this plan. It creates
no tests, cache-code change, external dependency, reference dataset, or change
to the existing M10 research report.

M10 empirical validation plan: READY FOR REVIEW