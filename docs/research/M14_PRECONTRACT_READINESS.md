# M14 pre-contract readiness: helper association and dependence

**Readiness: READY FOR CONTRACT FREEZE (descriptive observation contract
only).** The current [roadmap](../ROADMAP.md) keeps M14 planned. This report
freezes a software-safe descriptive baseline while deferring dataset-specific
independence, inferential models, and experimental claims.

## 1. Resolved contract boundary

The input explicitly declares its observation unit; software does not decide
that a run, sample, specimen, extraction, or study is biologically independent.
The descriptive baseline reports tested denominators and scoped co-detection.
It may report an association estimate only when a separate analysis profile
declares a justified unit mapping, denominator, controls, detection scope, and
model. M14 never converts association into helper dependence.

The exact schema can be frozen without selecting a public or private dataset.
Use explicit `UNKNOWN` for absent/unverified metadata. M7 sample/run/study IDs
are provenance links, not proof of independence.

See [M7 recurrence limits](../M7_INDEPENDENT_RECURRENCE.md),
[M14 design research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md),
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md), and the
[decision register](M12_M16_DECISION_REGISTER.md).

## 2. Smallest useful baseline

Implement an offline typed observation-table validator and transparent
stratified counts over synthetic records. Each row describes one declared
candidate/helper observation at one declared unit and method scope. The core
does not require an external statistical package or sequence database.

### Inputs

Required fields:

- Stable observation, candidate, helper, and source IDs.
- `unit_id` and explicit `unit_type` (for example sample/specimen, library/run,
  experiment, or study); relationships to other units where known.
- Candidate/helper detection values and state; method, assay/detection limit,
  tested status, and observation date/scope where permitted.
- Evaluable denominator and control role/status; unknown and missing values
  must be represented explicitly rather than inferred from absent rows.
- Metadata source/version, curation/provenance, and applicable access/terms
  status.

Optional inputs are abundance measures with assay/normalization metadata,
confounders, replicate/extraction relations, and independently supplied
intervention/assay evidence. Optional fields do not become default
requirements for a descriptive co-detection table.

### Output

- Validated observation records with original values and provenance.
- Candidate/helper co-detection counts stratified by the declared unit type,
  study and stated covariates where denominators permit.
- Explicit tested/evaluable counts, missing/unknown counts, controls,
  detection scope, and method limits.
- Optional association estimates only under a frozen analysis profile that
  declares a sampling frame, independent unit, all evaluated cells, model,
  assumptions, and uncertainty.
- Experimental dependence evidence linked as a separate record with assay,
  controls, perturbation/rescue, measured phenotype, and source. It is not an
  output inferred by the observational calculation.

### Typed states

For each candidate/helper at a unit:

- `PRESENT`;
- `NOT_DETECTED_WITHIN_SCOPE` (only if that unit was tested under a declared
  method/sensitivity);
- `UNKNOWN` (not supplied, untested, or provenance insufficient).

For the computation:

- `COMPLETED_DESCRIPTIVE`;
- `COMPLETED_ASSOCIATION` only for an explicitly enabled valid model;
- `INSUFFICIENT_MATCHED_EVIDENCE`;
- `NOT_APPLICABLE`, `DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`,
  `INCOMPLETE`, or `INVALID_INPUT`.

Absence of an observation row is `UNKNOWN`, not `NOT_DETECTED`. Preserve
biological-unit verification separately from the declared identifier. The
baseline does not output `DEPENDENCE_DEMONSTRATED`.

### Provenance, cache, and failure semantics

Bind a result to the exact observation-table bytes/hash, source and metadata
provenance, unit/relationship map, detection method and limits, denominator
rules, control definitions, candidate/helper links, and selected statistical
profile/runtime if any, plus schema and output hashes. A change to grouping,
denominator, metadata, or model changes M14 identity; it does not rewrite M7.

Invalid or incomplete rows are retained with explicit reasons where safe.
Failed/unavailable calculations cannot become zero association. A missing
control is not a negative control. Deterministic sorting and normalization make
outputs stable for the same inputs and settings.

## 3. Deterministic offline acceptance fixtures

1. A small synthetic table yields hand-calculated candidate/helper counts and
   denominators by declared sample and study units.
2. Multiple runs from one sample and multiple libraries from one specimen
   remain linked and are not silently counted as independent biological units.
3. Missing, untested, and tested-not-detected are distinct; absent rows never
   become negatives.
4. Sparse/empty cells yield `INSUFFICIENT_MATCHED_EVIDENCE` or an appropriately
   qualified descriptive table, not an unsupported association estimate.
5. Missing controls, mismatched methods, incomplete denominators, and
   unverified sample/run/study provenance remain visible.
6. Optional abundance summaries require matching assay/normalization metadata;
   raw read counts alone cannot become biological abundance.
7. Experimental perturbation/rescue fixtures are linked separately and cannot
   be generated from observational co-detection.
8. Repeated runs over identical data/config produce deterministic outputs;
   changing a unit map or denominator changes M14 identity only.

## 4. Contract blockers versus deferred decisions

**No unresolved decision blocks freezing the descriptive record and summary
contract.** The following rule resolves the software ambiguity: unit identity
and unit type are explicit input fields; no universal independence inference is
made. Model-specific association and biological dependence remain separate.

| Decision | Effect |
| --- | --- |
| What observation unit is independent for a particular study/claim, and how is that declaration verified? | Blocks that inferential analysis profile and real-data association interpretation; does not block descriptive contract freeze. |
| Which matched cohorts, controls, denominators, and metadata are authorized? | Blocks real-data execution only; synthetic records exercise the contract. |
| Which statistical model, normalization, sparse-data policy, and uncertainty method are appropriate? | Blocks the optional inferential/abundance branch, not descriptive counts. |
| What experiment, perturbation/rescue and phenotype establish dependence in a given system? | Blocks a dependence claim only; observational M14 remains distinct. |
| Which source terms/privacy rules apply to an actual dataset? | Blocks access and real-data execution only. |

**Milestone disposition:** `READY FOR CONTRACT FREEZE` for descriptive
observations, explicit denominators, and missingness. Defer inferential models
until the relevant independent units and matched data are justified. Defer
dependence claims until claim-appropriate experiments exist.

## 5. M1–M10 compatibility and boundaries

M14 can link M7’s declared identifiers without treating them as verified
independence. Candidate/helper identity may link M8/M9 records with their
reference and annotation limitations; M5/M6/M10 may be linked as separate
evidence dimensions. No M1–M10 interface or scientific behavior needs to
change. M14 may consume only stable typed output and provenance; it must not
relabel M7 recurrence. M15 may later include the M14 bundle as a separate
evidence source.
