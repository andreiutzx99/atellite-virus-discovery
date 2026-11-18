# M36 Phase 2B scientific preregistration completion proposal

**State: PROPOSED FOR INDEPENDENT SCIENTIFIC REVIEW.** This is a decision
proposal, not an amendment, approval, frozen parameter set, or execution plan.
No option below is adopted by this document. The registered matrix remains
disabled and **NOT RUN**.

The review-completed, decision-ready algorithm details are in
[`M36_PHASE2B_AMENDMENT_SPECIFICATION.md`](M36_PHASE2B_AMENDMENT_SPECIFICATION.md).
That companion remains proposed and does not adopt or freeze any option.

## Scope and guardrails

This proposal resolves the scientific questions needed to make the existing
synthetic design reproducible. It preserves the 12 independent sequence
families, the 4/4/4 development/tuning/held-out split, two technical repeats,
all registered assignments, and the maximum of 520 assembly executions. The
family remains the independent statistical unit; repeats are summarized within
family and are not additional independent observations.

No family/read seeds, family-to-split assignments, sequences, or truth mappings
are generated or included here. No M6, M8, or M31 behavior is changed; no
registered attempt, biological input, storage/signing setup, pipeline
promotion, or M37 work is authorized. Any approved choice that changes the
frozen design must first be recorded as a preregistration amendment and reviewed
before the catalog or digest is changed.

## Evidence and provenance reviewed

| Source | Relevant record | Provenance / integrity |
|---|---|---|
| `docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json` | Frozen baseline, conditions, 12 families, split counts, endpoints, and execution gates. | Read from PR #103 head `bafccd8a5516f8ab881d0fb8f8e899fbfab2de75`; SHA-256 `9bf43bc8dc3e947de87bac66a5d2f5d9dd27f967544144aee58f19f67c06df8f`. |
| `satellite_discovery/m25_read_coverage.py` | `_make_starts` (107–118); `_make_fastq` (163–280); `coverage_summary` (58–104). | Same PR head; SHA-256 `fc78491ff60c77dbd234a204bd198dd5951d43fda3830ff6151aff4aec89c47f`. |
| `satellite_discovery/m19_benchmark.py` | `SEED=190076`; `_sequence`; existing synthetic target/background generation and seed use. | SHA-256 `a1cf460a83fc7851bb7d7c6242aeead97403f267aea76a9d94f470184b9be325`. |
| `satellite_discovery/m36_runner.py` | `expected_condition_parameters` and `validate_evaluator_manifest`; blocked labels, exact catalog matching, seed-role and 4/4/4 checks. | Same PR head; SHA-256 `0e4f11bb4ddb8c1adff97b075a71216aa1c860d8c2ba8869561fc3a514cc146a`. |
| `docs/M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.md` and `.json` | 5/35 eligible target-absent cases prioritized; all five eligible near-target cases prioritized; four SPAdes execution failures, including substitution-only. | Tracked M34 summary SHA-256 `7649242ea37fba32abfef8ab475683163479ea0e52979f48d4a55432b90f1dd5`; source Actions run `42609565425`, artifact `13670022421`. |
| `docs/M35_SPECIFICITY_ASSEMBLY_ROOT_CAUSE.md` and `.json` | Three exact-positive controls unevaluable; 21 target-absent decoys; 26/28 SPAdes failures across 14 settings; eight held-out conditions reproducible. | M35 Actions run `42815490595`, source commit `41962cc3a5bef690b8715feb7e35b74381860f40`, artifact `13765202624`, ZIP SHA-256 `3abf0833ec7f21b879748024072c73fc9170987548a3fa9adc61cab341a8cf49`; design SHA-256 `ce1e5ebbc112416023cec48735977ee676012172974523d7109e3f19ca0ba54a`. |
| `docs/M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.md` | M27 shows low-complexity filtering can remove generated target reads; it is not evidence that any particular M36 sequence recipe is representative. | SHA-256 `9b285a72c224b9b97d9e539db5f80da0c7f718ab4896cfc7f69b932726d618ed`; synthetic-only M27 record. |

M34/M35 are synthetic diagnostics, not biological sensitivity, specificity, or
sequencing-platform error estimates. M34's 5/5 result is among eligible
near-target cases; three of eight generated cases in that category were
unevaluable. Its four SPAdes failures are execution failures, not measured
reconstruction losses. M35's three exact positives had no supported assembly
and are unevaluable, not negative. Its controlled SPAdes comparisons are
descriptive, not causal; the separately namespaced alternative assembler was
not run. These constraints limit what the proposed design can conclude.

## Decision options for scientific review

### 1. Target-to-background abundance (registered label: 1:9)

M25 computes read counts from nominal depth and source length; it also emits
technical-reference reads. Insertions and deletions change output read lengths.
The current audit counts `target_truth` and `synthetic_background` records and
excludes `technical_reference`; it blocks unless the two read counts are
exactly 1:9. The frozen registration does not yet state this denominator or
whether abundance means records, bases, or covered positions.

| Option | Rationale and implementation | Confounding, validation, interpretation | Amendment |
|---|---|---|---|
| **A — source-read count ratio (preferred for review)** | Define 1:9 as generated target-truth read records : synthetic-background read records, measured after generation and before downstream filtering. Exclude technical-reference records explicitly. Require integer counts in exactly 1:9; no rounding tolerance. Report technical-reference counts, total read bases, and realized lengths separately. | Directly tests read allocation, which the generator controls. It does not mean 10% of all reads or bases when technical-reference reads or indels are present. Validate role counts against the placement ledger and FASTQ IDs; fail closed on missing/duplicate roles or non-exact counts. Interpret only as a synthetic read-record ratio. | **Likely required** because the current design label does not define this denominator; confirm against the authoritative approval record first. |
| B — output-base ratio | Define abundance by the sum of emitted target and background read lengths after errors, excluding technical-reference bases. Set lengths/counts until the ratio lies within an approved tolerance. | Answers base-mass rather than molecule/read abundance. Indel rates can change the ratio and couple the abundance factor to the error model; tolerance and rounding become additional parameters. Validate independent recount from FASTQ and per-read origin ledger. | Required unless explicitly present in the approved source. |
| C — source-coordinate coverage ratio | Define abundance by total pre-error source interval bases sampled from target and background; separately report distinct-base breadth. | Separates source sampling from inserted output bases, but overlapping intervals mean it is not unique-base coverage. Validate interval ledger and independently recompute interval totals and breadth. Interpretation is simulated source exposure, not read count. | Required unless explicitly present in the approved source. |

**Recommendation:** ask the design owner to approve A or supply the controlling
source for another definition. A zero-tolerance rule is a proposed acceptance
rule, not a value already approved. Keep technical-reference counts outside the
1:9 denominator and show them separately.

### 2. Low-complexity sequence construction

M36 names `low_complexity_stress_sequence` but specifies no sequence recipe,
complexity statistic, or acceptance threshold. M19 contains a 5-base periodic
`AAAAC` example; that has fixed composition and is not family-specific. M27
shows that low-complexity screening can remove reads, so this condition must
record generated and post-screen reads separately.

| Option | Rationale and implementation | Confounding, validation, interpretation | Amendment |
|---|---|---|---|
| **A — whole-target periodic motif** | Create a 900-nt target by repeating a short motif to exact length. Select the motif deterministically from a family-specific stream and publish the motif-generation algorithm, composition constraints, and truncation rule. | A clear, reproducible extreme stress; motif GC and periodicity can dominate recovery and M6 filtering. Validate length/alphabet, per-family sequence digests, motif period, GC, Shannon entropy, distinct-k-mer spectrum, and deterministic regeneration. Interpret only as response to this artificial periodic sequence. | Required unless the frozen source already specifies the exact motif and metrics. |
| **B — composition-matched periodic target (preferred for review)** | For each family, derive a fixed-length motif from that family's synthetic target base composition, repeat it to 900 nt, and specify the motif length, shuffle algorithm, tie/rounding rules, and family-seed namespace. | Holds broad base composition closer to the paired family while adding periodicity. Motif length and arrangement still affect assembly and filtering, and family-specific motifs may differ in difficulty. Validate exact length, per-base counts, period, entropy/k-mer metrics, digest stability, and M25 retained-read counts. Interpret as a controlled periodicity stress, not natural low complexity. | Required because no motif recipe or complexity acceptance criteria are registered. |
| C — constrained low-entropy sequence | Generate a family-specific sequence under declared GC/base-count bounds and an entropy or k-mer-complexity band, using a pinned algorithm and rejection rule. | More flexible, but entropy thresholds and rejected draws can change the family population and select easier sequences. Validate acceptance rates, all generated/rejected digests, bounds, and deterministic regeneration before assembly. | Required; all bounds and thresholds must be approved. |

**Recommendation:** review B against A. B better separates periodicity from
large GC shifts; do not use an M27 filtering outcome as a reason to tune the
recipe or M6 thresholds. The number of retained reads and support status are
outcomes, not construction acceptance criteria.

### 3. Alternate sequencing-error-position distribution

M25's baseline deletes source positions by per-base Bernoulli draws, chooses a
rounded substitution count uniformly without replacement among surviving
positions, and inserts after surviving bases by per-base Bernoulli draws.
“Alternate error-position distribution, same rates” does not identify which
error classes or which count semantics should change.

| Option | Rationale and implementation | Confounding, validation, interpretation | Amendment |
|---|---|---|---|
| **A — clustered substitutions, unchanged indel process (preferred for review)** | Preserve each read's existing rounded substitution count, deletion process, insertion process, and order. Place substitutions within one contiguous source-coordinate window with a uniformly chosen valid start and a specified rule when deletion positions overlap the window. | Isolates spatial clustering of substitutions while preserving per-read substitution counts. Clustering is a stress model, not a claim about a platform; it may interact with M6 quality filtering. Validate exact per-read counts, positions, rates, quality strings, origin maps, and a predeclared clustering statistic. Analyze by family, not by read as independent. | Required unless the original preregistration defines the same event scope and placement rule. |
| B — end-biased substitution positions | Preserve per-read substitution counts but sample positions without replacement under a declared end-weighting function and parameter. Keep indel semantics unchanged. | Tests positional bias with less local clustering. The weighting parameter and orientation can interact with read-start and terminal-coverage effects. Validate realized position histograms against the prespecified distribution and test both orientations if orientation is part of the design. | Required; the weighting function and parameter must be approved. |
| C — reposition substitutions, insertions, and deletions | Draw event counts under the frozen M25 rules, then assign each event class under a separately declared common or class-specific spatial distribution. | Broadly changes error structure and may make the factor hard to interpret; overlapping events and indel ordering can change read lengths and bases. Validate counts, collisions, ordering, per-base origins, and realized rates by family and repeat. | Required; define every event class and collision rule before use. |

**Recommendation:** review A as a narrowly interpretable synthetic stress. Do
not describe it as a sequencing-platform model. Keep “same rates” explicit:
the proposed invariant is each read's M25-derived event count, not merely a
similar matrix-wide mean. If the scientific question instead concerns all
error classes, review C as a distinct proposal rather than silently extending
A.

### 4. Family, background, technical-reference generation, and seed mapping

M19 generates synthetic sequences using `random.Random` and role-specific
integer offsets. M25 initializes one RNG per case from
`m19.SEED + sum(analysis_id.encode())`, then consumes it across reference,
background, and target-read generation. The additive ID mapping permits
collisions and couples streams to generation order. M36 correctly requires
separate family/read seed roles, distinct family seeds, independent technical
repeat read seeds, and byte-identical paired-assembler inputs, but does not
freeze a sequence recipe or substream mapping.

| Option | Rationale and implementation | Confounding, validation, interpretation | Amendment |
|---|---|---|---|
| **A — domain-separated deterministic streams (preferred for review)** | Keep the evaluator's 12 private family seeds and read seeds as inputs. Derive independent, versioned streams for family target, background, technical reference, and each read-generation block/condition/repeat using a documented domain-separated digest mapping and a pinned byte-to-random-value algorithm. Keep exact 4/4/4 assignment restricted; publish only algorithm/version and artifact digests. | Avoids collisions and accidental cross-role coupling; preserves family as the independent unit and repeat independence. Requires a precise mapping, version pin, and protected source-map provenance. Validate domain separation, distinct streams, deterministic bytes, cross-runtime replay, ledger/FASTQ agreement, and paired input equality. | Required unless an approved source already defines this mapping; family/read seeds themselves remain evaluator-only. |
| B — pre-generated synthetic sequence bank | Generate and review a synthetic target/background/reference bank once, bind each record to exact digests, and map families through the restricted evaluator source map. Seed/read generation remains a separate, specified step. | Makes source records easy to audit but sequence-bank reuse can make nominally independent families share sequence features and understate family variation. Validate uniqueness/similarity, composition, family-level independence rationale, and exact digest membership. | Required for any new bank or changed family mapping. |
| C — retain M19/M25 additive seed derivation | Reuse existing seeded generators and current per-case ID derivation. | Easiest migration, but additive byte sums collide and the shared RNG sequence couples references/backgrounds to target reads and iteration order. Determinism of one case does not establish independent streams or domain separation. Validate collision tests and exact bytes; this option is not recommended for a registered design. | Required if adopted as a clarification; must be justified against the frozen seed-role requirement. |

For backgrounds and technical references, the owner must also choose whether
each family receives its own generated sequence or a digested shared bank, set
length/composition rules, and specify whether technical-reference reads receive
coverage, errors, or both. In every option, technical-reference reads must be
identified separately and must not silently enter the target/background
denominator. These choices are unresolved; no technical-reference sequence or
private seed is supplied here.

### 5. Coverage, indels, and read-start semantics

M25 calculates the read count as `ceil(nominal_depth × source_length /
read_length)`. `uniform` places starts at evenly spaced valid positions;
`random` samples valid starts independently with replacement. They have
different breadth and overlap distributions. The frozen M36 JSON says
`uniform`; the M36 generator audit fixture currently says `random`.

| Option | Rationale and implementation | Confounding, validation, interpretation | Amendment |
|---|---|---|---|
| **A — retain frozen `uniform` (preferred for review)** | Use M25's deterministic evenly spaced starts for target reads as the frozen M36 record states. Define nominal coverage by the pre-error source-read count formula above; report actual read count, pre-error sampled source bases, post-error output bases, distinct-base breadth, and gaps. Preserve M25 indel semantics: deletions are per-source-base Bernoulli events; substitutions are rounded per read over surviving positions; insertions are per-surviving-base Bernoulli events. | Best preserves the registered setting. Uniform tiling is not iid sampling and may yield fewer stochastic gaps than `random`; distinguish nominal depth from realized breadth. Validate start arrays, count formula, full per-base depth, exact event accounting and read length/base-origin reconciliation. Inference remains conditional on this synthetic generator. | No change if the authoritative approved record confirms these semantics; fix any contradictory audit fixture only after this proposal is reviewed. |
| B — switch to M25 `random` | Use independent iid starts with replacement, keeping the same nominal read-count formula and report realized breadth. | Better represents random sampling but duplicates starts and changes overlap/gap variability; it changes the frozen M36 setting and can change assembler success. Validate the empirical start and breadth distributions using synthetic-only generator tests. | Required amendment because the frozen record says `uniform`. |
| C — redefine nominal coverage as a fixed number of emitted bases | Choose read counts/lengths to meet an exact base total or a fixed realized depth criterion, with explicit treatment of indels. | Makes the denominator more literal but changes M25's ceil-based count and can force condition-dependent read counts. It may confound coverage with indel burden. Validate the base-count identity, coverage breadth, and read-length distribution. | Required amendment unless this is already the approved definition. |

**Recommendation:** review A first because it honors the frozen M36 value.
Retain realized base breadth and coverage gaps as outcomes; do not call nominal
depth an observed uniform depth. Do not substitute `random` solely because it
appears in the audit fixture. The owner must confirm whether insertion/deletion
rates mean the current M25 per-source-base probabilities; output read lengths
must be reported because indels alter them.

## Decision register

| Status | Decision item | Current record and source/provenance | Next approval needed |
|---|---|---|---|
| **APPROVED** | Synthetic-only scope; no biological or production claim. | M36 JSON `governance`, `limitations`, and `acceptance_gates_for_phase2`; M34/M35 reports. | None for this proposal. |
| **APPROVED** | Twelve independent families; development/tuning/held-out counts 4/4/4; family is the independent unit; repeats are technical. | M36 JSON `experimental_units` and `analysis`; `m36_runner.py::validate_evaluator_manifest` enforces counts. | Preserve through any amendment. |
| **APPROVED** | Existing matrix size and maximum of 520 executions; registered attempts remain NOT RUN. | M36 JSON `matrix`, `planned_totals`, and `governance`; current PR #103 head above. | Any change requires a new design review; this proposal changes none. |
| **APPROVED** | Baseline values as currently frozen: target 900 nt, nominal coverage 48, read length 100 nt, substitution 0.02, insertion/deletion 0.01, `uniform` starts, synthetic-background coverage. This status records the registered values only; it does not resolve their scientific interpretation. | M36 JSON `frozen_baseline`. | Confirm source authority and definitions below before execution. |
| **PROPOSED** | Define 1:9 by target/background source-read records, exact 1:9, excluding technical reference. | Option A above; current audit implementation in `m36_preparation.py::audit_m25_generator` uses this count denominator but does not make it approved. | Design owner and independent scientific reviewer; amend if the authoritative source is silent. |
| **PROPOSED** | Use family-specific composition-matched periodic targets for the low-complexity arm. | Option B above; M19's `AAAAC` sequence is only an example, not an M36-approved recipe. | Approve exact recipe and metrics; amend. |
| **PROPOSED** | Cluster substitutions only while preserving M25-derived per-read substitution counts and unchanged indel generation. | Option A above. | Confirm error class scope, collision rule, and model interpretation; amend. |
| **PROPOSED** | Use versioned, domain-separated seed streams for target/background/reference/read simulation. | Option A above; M36 seed-role checks and M25/M19 current additive mapping reviewed. Test that sequence bytes/covariates for a registered family-condition-repeat are unchanged when other cases are added or removed; never derive them from current list position. | Approve algorithm/version and source provenance; keep actual values restricted. |
| **PROPOSED** | Preserve M25 `uniform` starts and define coverage/indel metrics as above. | Option A above; M36 frozen record versus audit-fixture discrepancy. | Design owner confirms authoritative source; amendment required to switch to `random`. |
| **UNRESOLVED** | Abundance denominator, rounding/tolerance, technical-reference treatment, and whether 1:9 refers to reads, bases, or coverage. | M36 condition name and generator audit; no source found defining the intended measure. | Resolve before marking the abundance condition READY. |
| **UNRESOLVED** | Low-complexity recipe, family variation, sequence-complexity metric, threshold, and acceptance procedure. | M36 condition name; M19 example; M27 screening evidence. | Resolve before marking the condition READY. |
| **UNRESOLVED** | Alternate error-position event classes, position distribution, event counts, and collision/order semantics. | M36 condition name; M25 baseline implementation. | Resolve before marking the condition READY. |
| **UNRESOLVED** | Target/background/technical-reference recipes, seed-to-RNG mapping, coverage denominator, and read-start discrepancy. | M36 frozen record, M25/M19 implementation, and M36 audit fixture. | Resolve from an authoritative source and record amendment status. |
| **BLOCKED** | Registered execution, 520 attempts, production authorization, and Phase 2B enabling. | M36 governance says `INCOMPLETE` / `BLOCKED_FOR_BENCHMARK_EXECUTION`; this proposal supplies no approval. | Separate user authorization after independent scientific review and all operational gates. |
| **BLOCKED** | Private family/read seeds and family-to-split assignments. | M36 JSON requires a restricted evaluator sidecar; current proposal contains no such values. | Evaluator-only approved source map; never place values in source control or PR text. |
| **BLOCKED** | Exact SPAdes identity/k-mer configuration, durable restricted storage/signing, and operational M6/assembly stages. | M36 JSON `capability_gaps` and `acceptance_gates_for_phase2`; M35 notes exact SPAdes version was not pinned. | Resolve and independently verify before any execution proposal. |

`APPROVED` for a frozen baseline row means only that the listed values are
present in the current registration; it does not imply that unresolved
scientific meanings have been approved. The register is a proposal snapshot and
does not update the frozen JSON, condition catalog, or digest.

## Review and amendment sequence

1. The design owner identifies the controlling source/version for each
   unresolved definition, or explicitly authorizes a proposed amendment.
2. An independent scientific reviewer selects or revises options and evaluates
   the confounding, validation, endpoint, and statistical implications.
3. Record each decision, approval reference, exact source/digest, and amendment
   requirement in a new decision record. Keep unapproved options labelled
   `PROPOSED`; do not silently update the catalog.
4. Only after review, separately amend the frozen preregistration if needed and
   rerun the design/schema checks. Reconfirm that 12 families, 4/4/4 allocation,
   independent-family inference, and the 520-execution ceiling are preserved.
5. Any later execution still requires separate authorization and all technical,
   security, storage, and tool-identity gates. This proposal does not grant it.

**Stop point:** this document is ready for independent review. Do not change the
frozen preregistration or start any registered attempt until review and the
required approvals are complete.
