# M15 pre-contract readiness: evidence integration

**Readiness: READY FOR CONTRACT FREEZE (lossless descriptive dossier; no
ranking).** The [roadmap](../ROADMAP.md) defines M15 as evidence integration
and optional transparent prioritization; M15 remains **PLANNED / NOT
IMPLEMENTED**. This review resolves the software state/interface choice
without making biological policy.

## 1. Resolved software contract

Freeze a **lossless evidence envelope** around each upstream record. Preserve
the producer’s raw artifact, schema/version, status and provenance exactly;
add a normalized interpretation envelope without replacing the producer data.
This supports an M15 descriptive dossier without requiring upstream stages to
rename or weaken their existing statuses.

### Inputs

- Typed M5–M14 evidence records when present; M1–M4 run/workflow provenance;
  exact M6 candidate identity; and immutable artifact references/digests.
- Producer stage, schema/version, original status, method/configuration,
  inputs/reference snapshot, scope, limitations, and dependency/shared-source
  links.
- Explicit absence for an optional stage or branch not supplied.

M11 was outside this pre-contract review. The later M15 freeze deliberately
excludes M11 artifacts; admitting them requires a separately reviewed M15
contract version. Their absence is not negative evidence. Do not rerun an
upstream stage to populate M15.

### Output

One dossier bundle contains stable candidate and evidence IDs, source artifacts
and hashes, producer metadata, raw status and payload references, dependency
graph or equivalent links, normalized semantic axes, summary tables, and
integrity/provenance manifest. Filtering or display cannot erase raw evidence,
scope, conflict, or missingness.

### Typed evidence envelope

Use these orthogonal axes, with `UNKNOWN` when a source record does not support
a mapping:

| Axis | Allowed semantic values |
| --- | --- |
| Input/artifact validity | valid, invalid, unknown |
| Applicability | applicable, not applicable, unknown |
| Execution | not started, completed, dependency unavailable, failed, interrupted |
| Completeness | complete, incomplete, truncated, unknown |
| Method-scoped observation | observed, completed no-signal within declared scope, no observation |
| Interpretation | supports a named hypothesis, conflicts, unresolved, not interpreted |

Always retain the exact producer status beside the normalized axes. A
completed no-signal is valid only when producer accounting and scope are
complete. Missing, not applicable, unavailable, failed, interrupted,
incomplete, invalid, and truncated remain distinct; none becomes a negative.
Evidence can support more than one hypothesis, and two records sharing a read,
alignment, reference, model, or prior caller result are linked rather than
counted as independent confirmations.

The initial M15 contract has no score, Bayesian probability, biological
classification, or winner. Any future priority ranking is an optional
decision-support branch and must declare its objective, dependencies,
missingness, weights/model, uncertainty, calibration, and review/override path.

### Provenance, cache, and failure semantics

Bind M15 identity to the exact upstream result manifests, schema and status
values consumed, their hashes and integrity results, dependency links,
normalization/mapping version, dossier schema, selected display/filter policy,
and output digest. Missing optional inputs are explicit inputs to M15. A
changed producer artifact causes M15 to recompute; a M15-only change does not
invalidate unchanged upstream stages. Shared stage-identity semantics follow
the existing [identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).

Preserve valid partial rows when another source fails. Report source
unavailable, failed, interrupted, invalid, incomplete, truncated, conflict,
and unresolved separately. The dossier may describe a `COMPLETED` no-signal
only for a completed, accounted producer branch.

## 2. Deterministic offline acceptance fixtures

1. Combine synthetic M5–M14 records containing positive, scoped no-signal,
   missing, not applicable, unavailable, failed, interrupted, incomplete,
   truncated, invalid, conflicting, and unresolved examples.
2. Round-trip each producer’s raw status/schema and artifact references without
   lossy coercion.
3. Two report rows sharing the same source event/read/reference appear once in
   the dependency graph and are not described as independent support.
4. Missing optional M11/M12/M13/M14 records remain missing; they do not become
   zeros or no-hit findings.
5. A corrupt artifact or unrecognized status fails or maps to an explicit
   unknown/invalid state, never to success or no-signal.
6. Preserve partial valid evidence with a failed branch and render the failure
   prominently.
7. Same evidence and display policy yields deterministic dossier and manifest
   hashes; a M15 schema/render change invalidates M15 only.
8. No rank/score/class verdict is emitted in the baseline.

## 3. Freeze blockers versus optional branches

The previous research identified canonical cross-stage state/interface
semantics as unresolved. This readiness review resolves the software choice:
**preserve raw producer status and schema, and add the lossless semantic axes
above.** No M5–M14 enum migration or biological interpretation rule is needed
for the descriptive M15 contract.

| Decision | Effect |
| --- | --- |
| Which raw status is authoritative? | Resolved: the producing stage’s exact status and schema are authoritative and retained. |
| How are incomplete/missing/unavailable/failed/conflicting observations integrated? | Resolved for the baseline: separate axes and states; no coercion to negative or winner. |
| Which source dependencies should be deduplicated? | Resolved for baseline: link shared source evidence by immutable record/artifact identity and show dependency; do not add it as another independent vote. |
| Should M15 include a numeric/rule-based priority score? | Blocks only the optional ranking branch. The dossier can freeze and implement without a score. |
| Who approves weights/objective/calibration for ranking? | Blocks ranking use only; not a blocker to dossier freeze. |
| Can restricted source data be included in an export? | Blocks that export/use only; source rights remain attached and are not altered by aggregation. |

**Milestone disposition:** `READY FOR CONTRACT FREEZE` for the lossless
descriptive dossier. Ranking, classification, and external sharing of
restricted evidence are not part of the baseline.

## 4. M1–M10 compatibility and boundaries

The envelope consumes M1’s declared stage identity/provenance; M2 immutable
reference snapshots; M3/M4 typed workflow artifacts; M5 caller-specific event
and run states; M6 accounting/support/reconstruction; M7 exact recurrence and
declared metadata; M8 role-scoped nucleotide matches; M9 ORF/protein states;
and M10 exact architecture evidence. It preserves each producer’s source
status, hash and semantics, and does not rerun, remap, reclassify, or change
cache identity upstream. No M1–M10 code or contract change is required.

M12–M14 records are optional producers as they become available. M15 can first
be contract-tested on synthetic typed bundles; final integration is additive.
