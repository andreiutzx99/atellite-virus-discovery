# M36 Phase 1 — Synthetic Positive-Control Recovery and Assembly Investigation

**Status: DESIGN ONLY — experiments are not authorized or run. Do not execute experiments from this design.** This preregistration addresses M35's three unevaluable exact-positive controls and 26/28 SPAdes execution failures. It does not revise M34/M35 results, M6/M8 settings, M31 thresholds, governance, or production status.

## 1. Questions and hypotheses

### A. Where does positive-control recovery fail?

M35's three exact-positive controls produced no read-supported assembly and are unevaluable, not negative detections. M36 will localize loss using ordered evidence checkpoints:

1. **Generation:** Do generated FASTQ bytes and generator placement records contain target-derived reads at the declared abundance, coverage, length, composition, and error settings?
2. **Assembly:** Does the assembler complete and emit sequence that can be linked to the generated target?
3. **Support validation:** Do the existing read-support rules recognize the recovered sequence from the actual reads?
4. **Detection:** Given a qualifying supported candidate, does the frozen downstream screen report its evidence and state?

H1: Recovery varies with realized target-read abundance/coverage, read length, sequence complexity, and error profile. H2: Some apparent loss occurs after assembly, at support evidence linkage or downstream handoff. H3: generator-to-assembler interactions explain outcomes not explained by the marginal factors. These are hypotheses, not conclusions.

### B. What is associated with SPAdes failure?

H4: The M35 near-zero substitution contrast is reproducible across independent sequence families. H5: the M35 invalid-k-mer-coverage-histogram message is associated with one or more read/error/composition/coverage conditions. Neither hypothesis presumes that substitutions cause the failure. Logs and exit status will be retained; a causal mechanism requires stage-specific evidence or a separately validated intervention.

For every failure, retain the complete raw assembler log and identify the last documented stage reached (including graph construction and coverage estimation when the tool exposes those markers). If logs do not locate the failure, report its stage as unresolved rather than inferring a mechanism from the summary error string.

### C. Do existing alternative assembly strategies change diagnostic outcomes?

H6: Separately namespaced SPAdes and Tadpole runs may differ in completion, contig recovery, and read support on identical frozen synthetic inputs. This is descriptive software comparison only. It cannot replace M6's configured assembler or establish biological performance.

## 2. Frozen design and experimental units

The machine-readable specification is `docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json`. It is the source of truth for IDs, factors, counts, budgets, gates, and governance.

- **Synthetic families:** 12 independently generated target/background families, with 4 assigned to each of development, tuning, and held-out partitions before reads or outcomes are generated. Family identity—not a technical rerun—is the independent unit.
- **Seed roles:** each family has a fixed sequence-family seed and separately derived read-simulation seeds. Changing a technical-repeat seed cannot change the family sequence or split. Repeat IDs are not independent families. Family-to-split mappings and seed values are held in the restricted evaluator sidecar, not the analysis-visible manifest.
- **Blinding:** the restricted sidecar maps random analysis tokens to family, split, truth, factor, and condition labels. Analysis-visible paths, FASTQ headers, stage identifiers, and analyst-facing logs use only fresh opaque run tokens and contain none of those labels. Raw tool logs are retained in restricted evidence storage; blinded analysis receives sanitized copies with paths and factor-revealing command echoes removed. The evaluator may open the mapping only after raw evidence and analysis outputs are hashed, denominator/status checks pass, the design and analysis are frozen, and the independent reviewer authorizes locked unblinding. The JSON contains an abstract registered case manifest, not the sidecar mapping.
- **Positive and negative controls:** synthetic target-present exact-positive controls; target-absent background-only negatives; and a generator/read audit control that confirms the expected synthetic target-read payload. A no-read or malformed-read fixture is a pipeline integrity control, not a biological negative.
- **Frozen baseline:** use the M35 synthetic generator and the previously registered baseline values where available (900-nt target, nominal coverage 48, read length 100, substitution rate 0.02, insertion and deletion rates 0.01, uniform read starts, synthetic background coverage). Report realized—not only requested—coverage, read counts, error counts, and target fraction. Do not revise these settings to force a desired outcome.
- **Factors:** recovery diagnosis varies coverage (24/48/80), read length (75/100/150), target-to-background abundance (the M35 generator baseline and an explicit 1:9 target:background condition), and sequence complexity (family-native and a separately generated low-complexity stress condition). Two prespecified coverage-by-abundance corner conditions (24×1:9 and 80×1:9) provide a limited interaction check. This is not a full factorial and cannot estimate all interactions. The 1:9 condition is blocked until generator audit confirms it can be realized and measured exactly.
- **SPAdes diagnosis:** the fixed nine-condition matrix includes the M35 baseline; substitution rates 0, 0.0025, and 0.005 with indel rates held at baseline; low/high coverage; short/long reads; and an alternate error-position distribution at the same declared rates. Low-complexity stress is in the positive-recovery block only, not the SPAdes diagnostic block. This is a bounded one-factor-at-a-time diagnostic, not an interaction-complete design. Arbitrary k-mer settings are not available through the current adapter; the k-mer factor remains blocked and `NOT_RUN` until a separately reviewed adapter supports a registered, version-compatible option.
- **Target-absent controls:** one background-only, target-absent condition is assigned to each of the 12 registered family tokens, including one assignment per split as specified only in the restricted sidecar. Two independently simulated read sets per family are assembled with SPAdes. These 12 family-condition units and 24 executions are included in the revised workload; they are not fixtures outside the matrix.
- **Technical repeats:** repeats 1 and 2 use independent read-simulation seeds, so they are separate technical realizations, not byte-identical replicates. For the assembler comparison, both assemblers receive byte-identical reads within each family-condition-repeat pair; repeat 1 and repeat 2 use different reads. Technical repeats quantify pipeline stability; they do not increase the independent-family denominator.
- **Alternative strategies:** only existing registered adapters are candidates: SPAdes and BBTools Tadpole. Four development families are used for exploratory compatibility/output-contract checks; four held-out families are reserved for a locked final paired comparison after tools, inputs, and analyses are frozen. No third assembler or arbitrary SPAdes flags are introduced in this phase.

### Planned workload

| Block | Planned family-condition units | Technical executions |
|---|---:|---:|
| Positive-control recovery, 9 conditions × 12 families | 108 | 216 (2 repeats) |
| SPAdes error diagnostic, 9 conditions × 12 families | 108 | 216 (2 repeats) |
| Target-absent controls, 1 condition × 12 family tokens | 12 | 24 (2 repeats) |
| Exploratory assembler compatibility, 2 assemblers × 2 arms × 4 development families | 16 | 32 (2 repeats) |
| Locked assembler comparison, 2 assemblers × 2 arms × 4 held-out families | 16 | 32 (2 repeats) |
| **Total** | **260** | **520 assembly executions maximum** |

These are planned counts, not observed results. The target-absent control is a matrix block, not an existing fixture, and is included in the 520 executions. Alternative blocks are gated on exact tool identity and input compatibility. If a required executable cannot be pinned or provisioned, affected cases are `NOT_RUN` with their blocker; do not substitute an unregistered tool. The JSON `registered_case_manifest` is the complete product registration. Structural tests expand each family × condition × repeat × assembler assignment and derive denominators and totals rather than trusting hand-entered totals.

## 3. Outcomes, exclusions, and analysis

### Primary endpoints

1. **Generation validity:** target-derived read count, realized target coverage and target/background fraction agree with the simulator's placement ledger and byte-level input digests.
2. **Assembly completion:** stage outcome (`COMPLETE`, `FAILED`, `INTERRUPTED`, `NOT_RUN`) and reason from the exit status, manifest, and raw logs. A failure is not a reconstruction loss.
3. **Recovery:** exact or preregistered partial target reconstruction, with numerator and target-length denominator, evaluated independently from assembly completion.
4. **Read support:** existing support status and its raw evidence, reported separately from contig production and downstream detection.
5. **Detection handoff:** the frozen downstream output for candidates that pass the applicable evidence gate. Report no output as not evaluated when upstream evidence is absent; never convert it to a negative result.

Secondary endpoints include contig count/length, target breadth and depth from known simulator placements, observed error composition, GC and k-mer summaries, support-read identities, stage durations, and output hashes. Do not treat alignment of a contig alone as read support.

### Inclusion and unevaluable rules

- Include every preregistered family-condition-repeat in the execution denominator, including failed or interrupted attempts.
- Exclude a repeat from a particular recovery denominator only when its required upstream input is invalid or unavailable; preserve the reason and retain it in generation/assembly status counts.
- Mark positive-control detection **unevaluable** if no candidate reaches the required read-supported state. Do not count it as a miss or success.
- Mark incomplete/malformed FASTQ, generator-ledger mismatch, missing executable, timeout, invalid output, support-validation error, and downstream-stage failure as distinct statuses. Do not silently retry; retries, if later authorized, receive new attempt IDs and retain the original.
- Report all counts as `n/N`; no missing cases are imputed. Never remove a failure from the execution denominator.

### Uncertainty and interpretation

Report family-level rates and 95% Wilson intervals for binary endpoints where families are independent and denominators are nonzero. Summarize technical repeats within family-condition first; do not use a pooled repeat-level interval as if repeats were independent. For paired SPAdes/Tadpole comparisons, compute each repeat-paired difference within family and arm, summarize repeats within that family, then report the four family-level differences and their descriptive interval. Show all family outcomes; the held-out denominator is four families, not 16 repeat/arm rows. Report split-stratified results only after locked unblinding, plus realized rather than nominal covariates and all unevaluable counts. No threshold is fitted or changed in M36 Phase 1. No biological sensitivity, specificity, validated satellite discovery, or causal SPAdes claim is permitted.

## 4. Capability-gap analysis

| Capability | Existing support | Gap / Phase 1 disposition |
|---|---|---|
| Synthetic reads with coverage, length, error, abundance/background options | M25 generator is used by M34/M35; M35 has independent case and read seeds | Audit actual generator parameter semantics and placement ledger for target abundance, complexity, and stable family identity. The exact 1:9 target:background arm is blocked until the generator can set and verify that ratio. Add a new synthetic generator only if the audit proves necessary; Phase 1 does not implement it. |
| SPAdes and Tadpole execution | `assembly_adapters.py` registers both; Tadpole runtime is BBTools 40.01 with a pinned archive digest | Current general adapter does not expose SPAdes k-mer selection; arbitrary k-mer tuning is therefore unavailable without a separately reviewed adapter change. Capture exact SPAdes version and binary digest before any future run. |
| Assembly manifest, raw logs, output inventory | Existing adapter records executable identity, parameters, status, and artifact hashes | M36 runner must preserve per-attempt stdout/stderr, raw tool logs, generated FASTQ, contigs, manifests, and checksums in restricted evidence storage. Blinded analysis receives sanitized logs with paths and factor-revealing echoes removed; missing provenance makes an attempt non-evaluable. |
| Read-support validation | Existing M6 support evidence and M32/M35 handoff patterns | The assembled-candidate-to-simulator-truth crosswalk needs an explicit synthetic-only audit without adding truth to analysis inputs. Test support failure separately from assembly failure. |
| Downstream detection | Frozen M31 triage/reporting path and M35 evidence validators | Reuse only as a read-only, unchanged consumer after a candidate passes support. Keep unexecuted downstream cases `NOT_RUN`/unevaluable; no threshold tuning. |
| Alternative configuration namespace | Two adapters can be selected by identifier | Separate M36 stage IDs, output roots, manifests, and comparison reports are needed. Existing adapter version pins do not themselves establish scientific comparability. |
| CI design validation | Full suite runs via unittest discovery; Linux optional-tools jobs install SPAdes and run artificial checks | Add only structural tests in Phase 1. The existing CI must not invoke the M36 experimental matrix. A future execution workflow requires a separately approved trigger and explicit concurrency/time limits. |

## 5. Proposed future Actions execution plan (not enabled here)

Phase 1 adds no workflow dispatch, schedule, or experimental command. If Phase 2 is separately approved:

1. Use a manually approved, pinned workflow revision and synthetic-only fixtures. Before execution, freeze SPAdes version+binary digest, Tadpole archive/version, generator revision, and all parameters; fail closed on mismatch. Enforce one vCPU per attempt or revise the CPU estimate and cap.
2. Run one family-condition-repeat-tool assignment per isolated attempt, with a bounded matrix of at most four concurrent jobs. Set per-attempt timeout to 180 seconds, aggregate slot cap to 26 hours, and complete workflow wall budget to eight hours, including the setup and artifact-validation reserves. Record queued, skipped, timed-out, budget-exhausted, failed, and completed attempts.
3. Store artifacts under `m36/<design-sha>/<opaque-run-token>/`, including generator manifest, FASTQ digests, placement ledger, assembly manifests/logs, raw and canonical contigs, support evidence, downstream output when eligible, and validation results. Split, family, condition, and truth mappings remain in the restricted sidecar.
4. Emit a canonical JSON summary with design SHA-256, source commit, workflow/run identity, tool executable/version/digests, exact parameters, all denominators/statuses, and per-file SHA-256. Produce a sorted artifact inventory and an archive digest; no biological sequence or external reference input is permitted.
5. Validate exact synthetic fixture bytes against the deterministic generator, opaque ID grammar and split mapping, family/repeat uniqueness, truth isolation, tool provenance, raw-output digests, support evidence linkage, complete expected-case accounting, and no M6/M8/M31 contract drift before unblinding.

The 520 × 180-second cap is **26 aggregate attempt-slot hours**. At an enforced one-vCPU-per-attempt limit, that is an estimated maximum of 26 CPU-hours; this is a planning estimate, not measured consumption. Phase 2 is blocked unless the runtime can enforce that limit or the estimate is revised to match actual thread allocation. Actual CPU time will be recorded separately from wall time.

The eight-hour workflow wall limit is partitioned into a 6.5-hour matrix execution window, a 45-minute runner setup/teardown reserve, and a 45-minute evidence and artifact-validation reserve. Four-way concurrency makes the full 26 slot-hours fit in at most 6.5 hours at the per-attempt cap. At the first aggregate-slot or wall-time limit, stop launching queued attempts; preserve evidence for attempts already running, mark cancelled attempts `INTERRUPTED_BUDGET`, and mark unstarted cases `NOT_RUN_BUDGET_EXHAUSTED`. Do not retry automatically. Report the full preregistered denominator and these statuses; budget-exhausted cases are not negatives.

## 6. Acceptance gate from design to execution

No experiment may start until all are true:

- An independent scientific reviewer approves this design, the matrix, primary endpoints, exclusions, uncertainty plan, and computational budget.
- User approval explicitly authorizes Phase 2 synthetic execution; this document alone does not.
- The M25 generator audit resolves coverage/abundance semantics, deterministic family and read seeds, complexity controls, and byte-verifiable placement evidence; the target-absent arm confirms no target-derived reads.
- Exact executable versions and hashes are frozen for every proposed assembler; each input layout and output contract passes synthetic smoke validation.
- A truth-isolation review confirms held-out labels and factor/condition names cannot enter analysis-visible paths, FASTQ headers, stage identifiers, or logs before locked unblinding.
- CI proves that failures, missing evidence, NOT_RUN blocks, unevaluable positives, and denominators are preserved and that M6/M8 settings and M31 thresholds are unchanged.
- A final authorization record sets governance only for the exact synthetic matrix, commit, tools, and time/resource limits. Biological execution and production promotion remain separately unauthorized.

## 7. Limitations and open scientific questions

M35 had only three positive controls, all without supported assemblies, and 26/28 SPAdes attempts failed with the same reported histogram error. Neither observation identifies where positive evidence was lost or what caused SPAdes failure. The proposed family count remains small; the one-factor design will not resolve all interactions. Existing M35 reports do not pin the exact SPAdes version in the summary. The exploratory assembler comparison is limited to development families; the held-out comparison remains locked until analysis and inputs are frozen. Tadpole is a distinct algorithm and output profile, not a drop-in validation of SPAdes or M6; it does not replace M6's configured assembler. Phase 1 cannot determine whether either tool generalizes to biological sequences.

The outstanding questions include whether M35's read generator achieved intended target abundance and breadth, whether support evidence can link correctly when a contig is emitted, which SPAdes internal stage fails, and whether results repeat across independently generated families rather than technical repeats.

## Governance

`decision=INCOMPLETE`; `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`; `biological_execution_authorized=false`; `production_promotion=false`; `phase1_design_only=true`; `m36_experiments_executed=false`. This preregistration does not change M34 or M35 findings, frozen M6/M8 settings, M31 thresholds, or deployment governance.
