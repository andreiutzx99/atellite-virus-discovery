# M16 pre-contract readiness: benchmark and validation

**Readiness: CONDITIONAL FOR SYNTHETIC IMPLEMENTATION, WITH REAL-DATA
DECISIONS DEFERRED.** M16 remains planned under the [roadmap](../ROADMAP.md).
The offline manifest/split-validation design is ready, but M16 implementation
must wait until the separate shared cache/source-identity prerequisite is
merged and its regression/CI gates pass. See
[M16 registration/cache decoupling](M16_REGISTRATION_CACHE_DECOUPLING.md).
This report does not select a biological truth set, actual holdout, or
performance claim.

## 1. Smallest useful baseline

Implement a benchmark-manifest and leakage-check harness over synthetic
records. It can validate stable IDs, label-state separation, exact and
near-duplicate grouping, split consistency, access/rights metadata, custody
events, and metric denominators without retrieving sequence or read payloads.
The harness must refuse to call ambiguous/unknown labels positive or negative.

The software contract separates:

1. software correctness;
2. benchmark performance on a defined and adjudicated population;
3. biological validation; and
4. claim-specific experimental confirmation.

These results must not be combined into a single pass/fail or interpreted as
proof about any one candidate. See [M16 design research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md),
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md), and the
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md).

## 2. Contract proposal

### Inputs

Each manifest item contains:

- Stable item/source IDs; accession.version, repository commit, or controlled
  artifact ID; source publication/experiment; source and sequence/read hashes
  where permitted; retrieval/version provenance.
- Claim being tested and claim-specific label state, label tier, evidence
  citation, curator/adjudicator provenance, confidence, and uncertainty.
- Relationship/group IDs for exact and near-duplicate sequences, family/clade,
  parent/helper, sample/donor, extraction/library, run, study, and laboratory
  where known.
- Rights/access/consent/privacy and redistribution fields, attribution, source
  terms, and permitted benchmark use.
- Inclusion/exclusion rationale, prior exposure by tools/curators, split
  assignment, freeze version, and custody/blinding metadata.

No actual benchmark set is selected here. Keep development, tuning/validation,
and sealed final holdout labels separate. Do not include payloads in ordinary
CI.

### Output

- Manifest-validation and leakage audit with per-item provenance and group
  assignments.
- Frozen evaluation identity and split record; no actual split/holdout
  assignment is performed by this review.
- Per-claim, per-class outcomes for adjudicated items, with explicit
  denominators, confusion counts, uncertainty and coverage.
- Separate counts for ambiguous/unknown labels, not applicable inputs, missing,
  failed, interrupted, incomplete, and truncated executions.
- Protocol-readiness output when no suitable truth set is available, with no
  accuracy, sensitivity, specificity, calibration, or biological-validity
  claim.

### Typed label and execution states

Label state is separate from workflow execution state:

- Claim label: `ADJUDICATED_POSITIVE`,
  `ADJUDICATED_NEGATIVE_WITHIN_CLAIM_SCOPE`, `DISPUTED`, `UNKNOWN`,
  `NOT_APPLICABLE`, or `NOT_YET_ADJUDICATED`.
- Evaluation execution: `COMPLETED`, `NOT_EVALUATED`, `DEPENDENCY_UNAVAILABLE`,
  `FAILED`, `INTERRUPTED`, `INCOMPLETE`, `TRUNCATED`, or `INVALID_INPUT`.
- Decision outcome: predicted/observed class or abstention, linked to the
  frozen method and claim. Do not infer truth from execution status.

Compute confusion metrics only for labels adjudicated for that specific claim.
Do not force disputed or unknown cases into the negative denominator.
Report coverage and all execution-state denominators separately. Synthetic
truth is software-fixture truth only.

### Leakage, freeze, and custody

Before evaluation, identify exact and near duplicates and group related items
at the highest relevant dependence level. Do not split one specimen/library’s
reads between partitions. Keep close homologous families, parent genomes,
source study, donor/sample, lab, extraction/library, and run together when
relevant to the intended claim. Maintain a manifest that explains any residual
relationship that could cross partitions.

Use distinct development, tuning/validation, and sealed final holdout sets.
Freeze tools, references/models, configurations, interpretation policy,
eligible branches, metrics, strata, uncertainty method, and stop rules before
unblinding. A custodian independent of threshold selection controls sealed
labels and records access. Post-unblinding changes require a new independent
holdout for confirmatory performance claims.

### Provenance, identity, and failure semantics

Bind an evaluation identity to the frozen executable/configuration, reference
and model snapshots, manifest and relationship graph, split assignment,
claim-specific truth-label version, access/custody events, metric/report code,
and output digests. Any label, split, threshold, tool, reference, or policy
change creates a new evaluation identity.

Invalid hash, split leakage, missing required source, unblinding before freeze,
or version mismatch blocks confirmatory evaluation and is reported explicitly.
It is not a biological failure or a negative. Preserve per-item partial
execution states and report coverage rather than silently dropping failed rows.

## 3. Deterministic offline acceptance fixtures

1. Generated manifest with exact duplicates, near-duplicates, related-family
   links, shared samples/runs/studies, and independent groups; verify no
   forbidden group crosses splits.
2. A sample/library’s paired reads are kept together; a source group cannot be
   split by row order or random seed.
3. Adjudicated, disputed, unknown, and unadjudicated labels remain separate;
   only adjudicated claim labels enter corresponding metric denominators.
4. Missing labels and hidden holdout values remain inaccessible to the
   synthetic scoring function until an explicit fixture unblinding event.
5. Corrupt hashes, mismatched manifest/tool versions, post-freeze config
   changes, and premature label access block a confirmatory result.
6. Deterministic confusion counts, coverage, and uncertainty mechanics match
   hand-calculated fixture values at the declared independent unit.
7. Changing labels, split, thresholds, references, or scoring code changes
   evaluation identity; upstream M12–M15 identities remain independent.
8. With no adjudicated truth, output protocol readiness and fixture validation
   only, never a performance metric.

## 4. Contract blockers versus deferred decisions

The generic manifest, state, leakage-check, custody-log, and metric-accounting
interfaces can be frozen now. The final **evaluation profile** for any
biological performance claim remains blocked until the claim owner and
independent reviewers decide:

| Decision | Effect |
| --- | --- |
| Claim-specific positive/negative label tier and adjudication standard? | Blocks that claim’s final benchmark profile and biological performance claim. Does not block a synthetic manifest validator. |
| Which labels are eligible, and how are unknown/disputed examples treated? | Blocks final metric denominators for that claim; baseline keeps them separate. |
| What is the highest relevant grouping unit for each target population, and who verifies relationships? | Blocks actual split assignment and confirmatory real-data execution; synthetic grouping mechanics can proceed. |
| Who controls the sealed holdout, label blinding, unblinding, and audit trail? | Blocks actual final holdout evaluation only. |
| What minimum denominator, metric, uncertainty, strata, threshold, and stop rule are defensible? | Blocks final protocol freeze and performance claims; software can expose explicit denominators without setting a biological threshold. |
| Which sources/assays are rights-cleared and ethically/biosafety approved? | Blocks affected data/experimental execution and claims, not offline harness work. |

**Milestone disposition:** `CONDITIONAL FOR SYNTHETIC IMPLEMENTATION WITH
DEFERRED REAL-DATA DECISIONS`. The shared cache/source-identity prerequisite
must first be merged with the M1–M15 regression boundary passing. After that,
M16 still requires a real offline synthetic M15 execution, its authenticated
`m15_result_bundle`, and M16 consuming that exact artifact. This is not `READY`
for a final biological benchmark or generalized performance claim. No actual
holdout is selected or assigned.

## 5. M1–M10 compatibility and boundaries

M16 evaluates a frozen M12–M15 workflow by its exact run/artifact identity; it
does not modify M1–M10 behavior, consume untyped upstream guesses, or rerun
earlier analyses. M5–M10 synthetic acceptance evidence is not biological truth.
M7 declared independence is a relationship lead to verify, not ground truth.
M8/M9/M10 evidence remains scoped to its methods and snapshots. No upstream
contract change is required. M15’s optional ranking, if ever selected, must be
frozen as part of the evaluated pipeline before the holdout is opened.
