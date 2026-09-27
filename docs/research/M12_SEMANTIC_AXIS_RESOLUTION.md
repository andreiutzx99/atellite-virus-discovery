# M12 semantic-axis resolution

**Disposition: RESOLVED AND APPROVED FOR IMPLEMENTATION OF THE FROZEN
SYNTHETIC/OFFLINE BASELINE. M12 remains PLANNED / NOT IMPLEMENTED until
production implementation is merged.** This resolution defines deterministic,
producer-scoped mappings for retained M5/M6 artifacts. It does not expand M12
into read analysis, source attribution, control interpretation, or candidate
classification.

The normative clarification is in the [M12 contract](../M12_CONTRACT_FREEZE.md#41-semantic-clarification-contract-erratum).
The
[`m12-input-v1` same-workflow registration boundary](M12_IMPLEMENTATION_EXECUTION_PLAN.md)
is separately resolved; explicit typed handoffs bind each producer reference
to its verified workflow output without changing these semantic axes.

## 1. Decision: retain only supported dimensions

M12 reports artifact review and explicitly typed, method-scoped producer
observations. It does not interpret them as evidence that a candidate is real,
false, biological, artifactual, or from a particular source.

| Concept considered | M12 representation | Why no additional axis is needed |
| --- | --- | --- |
| Input/artifact validity | Existing `review_state` | Identity, integrity, schema, and review outcome are distinct from the producer's analysis result. `VERIFIED` is not biological validity. |
| Analysis execution | `analysis_execution_status` | Separates completed, not-started, unavailable-dependency, failed, interrupted, and unknown producer analyses. |
| Analysis/accounting completeness | `accounting_status` | Carries only completeness proved by the typed producer contract and its exact scope. |
| Producer observation | `observation_status`, with `scope`, raw status, artifact reference, and payload preserved | A generic observation state is useful only when its producer-specific meaning remains attached. It is never an artifact/source classification. |
| Evidence availability | Existing artifact review state and the four `external_evidence` entries with their exact six-value states | `PRESENT_NOT_CONSUMED` is availability metadata, not an observation. An omitted optional artifact is not a negative or an inferred `NOT_APPLICABLE`. |
| Technical-artifact evidence | Preserve exact M5/M6 observations; no generic artifact axis or `ARTIFACT_COMPATIBLE` value | M5 reports caller-scoped junction evidence; M6 reports reference-screen, triage, assembly, or read-support outcomes. None is a generic artifact classifier. |
| Source/read origin | No axis; preserve the `source_reads` availability state | The baseline does not consume the payload behind external-evidence slots or compare source hypotheses. |
| Control/comparator adequacy | No axis; preserve the `controls` availability state | The baseline does not consume or match controls. It cannot assert that a control is adequate, clean, or matched. |
| Metadata completeness | No axis; preserve the `sample_metadata` availability state | The baseline does not consume metadata payloads or validate their completeness. |
| Interpretation | No per-record interpretation axis; summary remains `biological_conclusion = "NONE"` | Interpretation would add a claim that the frozen M12 scope does not support. |

## 2. Canonical record axes

Every M12 review record retains its existing identity, provenance, scope,
limitations, dependency references, and exact `producer_status_raw`. It also
uses the following normative fields:

### `review_state`

This is the outcome of M12's artifact review, not the upstream scientific
result:

| Value | Meaning |
| --- | --- |
| `VERIFIED` | Producer manifest, artifact identity, digest, path, declared contract, and applicable schema checks pass. This says nothing about whether the producer analysis succeeded. |
| `NOT_EVALUATED` | M12 did not evaluate an artifact or evidence dimension. An empty artifact list is not a completed zero. |
| `UNAVAILABLE` | A referenced artifact cannot be retrieved or read. |
| `NOT_APPLICABLE` | The producer explicitly declares the named artifact dimension not applicable. M12 must not infer this from an omitted optional artifact. |
| `INVALID` | Identity, path, digest, schema, status, or required cross-artifact checks fail. Do not interpret the payload. |
| `INCOMPLETE` | The artifact is reviewable, but its declared accounting or evidence scope is incomplete. |
| `FAILED` | The M12 review of this artifact failed; this is not an upstream analysis status. |
| `INTERRUPTED` | M12 review was interrupted before it could finish; this is not an upstream analysis status. |

### `analysis_execution_status`

This describes the producer analysis represented by the row, not M12's own
workflow lifecycle:

| Value | Meaning |
| --- | --- |
| `COMPLETED` | A recognized producer status records completion for this exact analysis dimension. |
| `NOT_STARTED` | The producer explicitly records `NOT_EVALUATED`, `ASSEMBLY_NOT_ATTEMPTED`, or an equivalent skipped/not-started state. |
| `DEPENDENCY_UNAVAILABLE` | The producer explicitly records an unavailable dependency or the verified producer lifecycle is `dependency_missing` / `external_module_required`. |
| `FAILED` | The producer explicitly records analysis, execution, or result-validation failure. |
| `INTERRUPTED` | The producer explicitly records interruption. |
| `UNKNOWN` | No unique mapping is supported, the status is unrecognized, or relevant statuses conflict. |
| `NOT_APPLICABLE` | The artifact is configuration/provenance/raw-input material and does not represent an analysis execution. |

Where an artifact has a typed status for its own analysis dimension, that status
is authoritative for that dimension; the enclosing M1 lifecycle remains
preserved verbatim in `producer_status_raw`. If no artifact-level status exists,
map only a verified terminal M1 lifecycle value. A failure in one M6 branch does
not rewrite a separately verified completed M6 reference comparison.

### `accounting_status`

Allowed values are `COMPLETE`, `INCOMPLETE`, `TRUNCATED`, `INVALID`, `UNKNOWN`,
and `NOT_APPLICABLE`.

- `COMPLETE` requires explicit producer accounting that reconciles for the
  declared input and scope. A valid M5 completed status or M6 comparison
  manifest may establish this only under the mappings below.
- `INCOMPLETE` requires explicit incomplete accounting or a verified missing
  portion of the declared scope.
- `TRUNCATED` requires an explicit producer truncation state or a verified
  truncation condition. A missing file or failed parser alone does not prove
  truncation.
- `INVALID` means the declared accounting or its required consistency checks
  fail.
- `UNKNOWN` means the artifact does not prove whether accounting is complete.
- `NOT_APPLICABLE` is reserved for artifacts that do not represent a counted
  analysis. It is not inferred from absent data.

### `observation_status`

Allowed values are `OBSERVATION_REPORTED`, `NO_SIGNAL_WITHIN_SCOPE`,
`NO_OBSERVATION`, `UNKNOWN`, and `NOT_APPLICABLE`.

- `OBSERVATION_REPORTED` means a validated producer artifact explicitly
  reports a signal or scoped observation. Its producer, method, scope, and raw
  status remain attached; this does not establish biological presence.
- `NO_SIGNAL_WITHIN_SCOPE` is permitted only for an explicit completed
  producer-scoped zero with `accounting_status = COMPLETE` and no conflicting
  status. It never means absent outside the stated method/input/reference
  scope.
- `NO_OBSERVATION` means the producer explicitly did not evaluate the
  dimension, a dependency was unavailable, or the analysis failed/interrupted.
- `UNKNOWN` means the available typed artifacts do not uniquely establish an
  observation state.
- `NOT_APPLICABLE` is for an input/configuration/provenance artifact that does
  not itself report an observation. It is not inferred from missing evidence.

An unavailable artifact has `review_state = UNAVAILABLE`,
`analysis_execution_status = UNKNOWN`, `accounting_status = UNKNOWN`, and
`observation_status = NO_OBSERVATION`. An invalid artifact has
`review_state = INVALID`; do not inspect it to generate a signal or a zero.
External-evidence slot values are copied exactly and do not change these axes.

## 3. Deterministic M5/M6 mappings

Mappings apply only after the producer run and artifact reference pass identity,
integrity, contract-version, and applicable upstream validation. Preserve every
raw status and native record; never aggregate different producers into one
source or artifact verdict. Status names in the table below are typed payload
statuses; the enclosing `ArtifactRef.producer_status` is the raw M1 lifecycle
value and is used only as the documented fallback.

| Producer artifact/status | Execution | Accounting | Observation |
| --- | --- | --- | --- |
| M5 `DVG_EVIDENCE_DETECTED` | `COMPLETED` | `COMPLETE` | `OBSERVATION_REPORTED` |
| M5 `NO_DVG_EVIDENCE_DETECTED` | `COMPLETED` | `COMPLETE` | `NO_SIGNAL_WITHIN_SCOPE` |
| M5 `NOT_EVALUATED` | `NOT_STARTED` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `ANALYSIS_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `ANALYSIS_FAILED` | `FAILED` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `INVALID_RESULT` | `FAILED` | `INVALID` | `NO_OBSERVATION` |
| M6 `residual_read_manifest`: comparison `complete`, input and accounted read counts equal, `counts.residual_fragments` positive | `COMPLETED` | `COMPLETE` | `OBSERVATION_REPORTED` |
| M6 `residual_read_manifest`: same complete accounting, `counts.residual_fragments = 0` | `COMPLETED` | `COMPLETE` | `NO_SIGNAL_WITHIN_SCOPE` |
| M6 `read_support_evidence` `READ_SUPPORTED_ASSEMBLY` | `COMPLETED` | `COMPLETE` when the producer's required query accounting validates; otherwise `UNKNOWN`/`INVALID` | `OBSERVATION_REPORTED` |
| M6 `read_support_evidence` `NO_SUPPORTED_ASSEMBLY` | `COMPLETED` | `COMPLETE` when the producer's required query accounting validates; otherwise `UNKNOWN`/`INVALID` | `NO_SIGNAL_WITHIN_SCOPE` only for the completed read-support test; it means no contig met the declared support criteria |
| M6 `NOT_EVALUATED` / `ASSEMBLY_NOT_ATTEMPTED` | `NOT_STARTED` | `UNKNOWN` or `NOT_APPLICABLE` according to artifact type | `NO_OBSERVATION` |
| M6 `DEPENDENCY_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | `UNKNOWN` | `NO_OBSERVATION` |
| M6 `EXECUTION_FAILED`, `READ_SUPPORT_FAILED`, `INVALID_OUTPUT`, or `INVALID_SUPPORT_OUTPUT` | `FAILED` | `INCOMPLETE`, `INVALID`, or `UNKNOWN` only as explicitly established by the artifact; otherwise `UNKNOWN` | `NO_OBSERVATION` |
| M6 `INTERRUPTED` | `INTERRUPTED` | `INCOMPLETE` only when explicitly established; otherwise `UNKNOWN` | `NO_OBSERVATION` |

M5's completed statuses are scoped to its configured caller, input, and settings;
the M5 contract and parser require completed output and read accounting.
`NO_DVG_EVIDENCE_DETECTED` therefore maps to a completed caller-scoped
no-signal, never to a biological negative.

The M6 residual mapping is scoped to its declared reference and settings.
`residual_fragments = 0` means no residual fragments were reported by that
completed comparison; it does not establish source, identity, contamination,
or absence. An accounting mismatch cannot map to `NO_SIGNAL_WITHIN_SCOPE`.

For M6 read support, map the typed `read_support_evidence` status, not a
similar-looking top-level `reconstruction_evidence` status in isolation.
`NO_SUPPORTED_ASSEMBLY` in reconstruction evidence is ambiguous when no
read-support result proves that the support test actually ran (for example,
there may have been no eligible reads); in that case use
`analysis_execution_status = UNKNOWN` or `NOT_STARTED` as explicitly supported,
`accounting_status = UNKNOWN`, and `observation_status = NO_OBSERVATION`.
Per-contig statuses such as `LOW_SUPPORT_ASSEMBLY`, `UNSUPPORTED_ASSEMBLY`, and
`AMBIGUOUS_ASSEMBLY` remain producer-native technical observations. They are not
M12 artifact classifications.

For configuration/identity artifacts that do not represent an analysis, use
`NOT_APPLICABLE` for the axes that do not apply. For raw or per-read artifacts
without a summary outcome—including M5 raw caller output and M6
SAM/triage/support tables—`observation_status = NOT_APPLICABLE` only for the
normalized aggregate field; preserve the raw rows unchanged. Set their
execution/accounting states to `UNKNOWN` unless a linked typed producer record
establishes them. This does not mean that a per-read artifact contains no
observations, and M12 must not scan it to invent an aggregate signal.

## 4. Precedence and non-inference rules

Apply these rules in order:

1. Validate the M12 manifest and immutable producer/artifact identities before
   reading payloads. Invalid identity, digest, path, schema, or status means no
   payload-derived observation.
2. Retain the exact raw producer status and artifact rows. Map only recognized
   statuses under the exact artifact contract/version; unknown future values
   map to `UNKNOWN`, never to the nearest known zero.
3. A producer-specific result status controls only its own method dimension.
   Preserve independent M5/M6 rows and conflicts; do not select a winner.
4. A positive producer observation may be retained when explicitly present,
   even if another branch is incomplete. A `NO_SIGNAL_WITHIN_SCOPE` mapping
   additionally requires explicit completion, complete accounting, and
   satisfaction of the relevant test prerequisites.
5. Any failed, interrupted, unavailable, invalid, incomplete, truncated, or
   conflicting state prevents a no-signal mapping for that same dimension.
   `TRUNCATED` is emitted only when truncation is explicit; otherwise report
   the verified invalid/incomplete/unknown state.
6. Missing optional artifacts and external-evidence slots do not become
   `NO_SIGNAL_WITHIN_SCOPE`, `NOT_APPLICABLE`, clean-control findings, or
   candidate rejection.

`NO_SIGNAL_WITHIN_SCOPE` is not `ABSENT`. `UNKNOWN`, unavailable,
not-applicable, failed, interrupted, invalid, incomplete, and truncated states
remain distinct and never map to a completed no-signal.

No M12 value asserts biological reality/falsity, source or read origin,
contamination, artifact status, DVG/satellite class, helper dependence,
function, or candidate rejection. A technical status may motivate a hypothesis;
that hypothesis remains unadjudicated.

## 5. Required synthetic distinctions

| Case | Synthetic input | Deterministic M12 result | Claim boundary |
| --- | --- | --- | --- |
| A. Evidence present plus no signal in a scoped screen | Valid M5 event evidence and a valid, fully accounted M6 residual manifest with zero residual fragments | M5 `OBSERVATION_REPORTED`; M6 `NO_SIGNAL_WITHIN_SCOPE` for the declared reference screen | The M6 result is not “no artifact detected” or a source-negative. No generic artifact test exists in this baseline. |
| B. Evidence plus an artifact-compatible technical pattern | Valid M6 per-contig `LOW_SUPPORT_ASSEMBLY` or `AMBIGUOUS_ASSEMBLY` record, with its M6 support provenance | Preserve the producer-native row and scope; the normalized aggregate observation status remains separate and follows the producer's endpoint status. | The row may motivate an artifact hypothesis, but M12 does not emit `ARTIFACT_COMPATIBLE`. If no permitted input explicitly reports an artifact-specific signal, that assessment remains unassessed. |
| C. Evidence present but artifact assessment unavailable | Valid M5/M6 evidence exists, but no permitted typed artifact evaluates a technical-artifact hypothesis | Preserve the available producer observations; the unsupported artifact question is `UNKNOWN`/unassessed, not negative | Existing M5/M6 evidence is not reinterpreted as an artifact assessment. |
| D. Source evidence unavailable | `external_evidence.source_reads.state = UNAVAILABLE` (or another exact declared availability state) | Copy that state and note exactly; no source-origin axis is emitted | Unavailable is not “source absent” or a source-negative. |
| E. Matched control unavailable | `external_evidence.controls.state = UNAVAILABLE` or `NOT_SUPPLIED` | Copy the state; control adequacy/comparison is not assessed | No clean-control or matched-control assertion. |
| F. Analysis failed | M5 `ANALYSIS_FAILED` or M6 `READ_SUPPORT_FAILED` | `analysis_execution_status = FAILED`, no no-signal; keep any independently verified completed rows | Failure is not zero evidence. |
| G. Analysis interrupted or truncated | M6 `INTERRUPTED`, or an explicitly verified truncated producer result | `INTERRUPTED` and `NO_OBSERVATION`; accounting is `TRUNCATED` only when proven, otherwise `INCOMPLETE`, `INVALID`, or `UNKNOWN` as supported | M5 parser-detected truncation is invalid, never a completed zero. |
| H. Relevant analysis completed but feature not detected | Valid M5 `NO_DVG_EVIDENCE_DETECTED`, valid M6 zero-residual screen, or a completed M6 read-support result with `NO_SUPPORTED_ASSEMBLY` and its prerequisites satisfied | `COMPLETED` + `COMPLETE` + `NO_SIGNAL_WITHIN_SCOPE` for that producer method | The wording must name the method and scope; it does not mean the feature is biologically absent. |

## 6. Implementation boundary

These definitions resolve only the semantic-axis ambiguity within the approved
synthetic/offline contract. They do not implement M12, register input/output
validators in production code, authorize real reads/controls/metadata, or
expand the contract. The same-workflow `m12-input-v1` binding decision is
resolved separately in the [M12 contract](../M12_CONTRACT_FREEZE.md) and
[implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md); production
registration remains implementation work. M12 remains PLANNED / NOT
IMPLEMENTED until production implementation is merged. No M5/M6 artifact,
status, validator, or scientific behavior changes.