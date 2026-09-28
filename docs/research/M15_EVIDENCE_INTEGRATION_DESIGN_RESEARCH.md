# M15 evidence integration and transparent prioritization: design research

**Status: research and architecture proposal only.** M15 is planned, not an
implemented production stage. The current [roadmap](../ROADMAP.md) defines it as
evidence integration and optional transparent prioritization. No candidate
evidence is integrated or ranked in this report.

This report distinguishes **LITERATURE/EMPIRICAL SUPPORT**,
**PROJECT DESIGN PROPOSAL**, and **UNRESOLVED DECISION**.

## 1. Integration is not classification

### LITERATURE/EMPIRICAL SUPPORT

Weight-of-evidence practice makes explicit that heterogeneous evidence can be
integrated qualitatively or quantitatively, and that the selected criteria and
weights embody decisions [1]. Bayesian or multicriteria methods do not remove
the need for defensible inputs, priors/weights, dependence assumptions, and
validation. Repeated methods that share reads, reference databases, training
examples, or assumptions are not independent confirmations.

### PROJECT DESIGN PROPOSAL

M15's first defensible product should be an **auditable evidence dossier and
matrix**, not a classifier or composite score. Each claim should link to its
source evidence record, stage/method identity, exact input and reference
snapshot, execution state, scope, and limitations. Preserve M5–M14 dimensions
individually, including the competing explanations considered by M13.

The evidence matrix should distinguish:

| State/dimension | Required interpretation |
| --- | --- |
| Positive observation | A method-scoped signal was reported; retain the raw/normalized source and exact scope. |
| Completed scoped no-signal | The declared method completed with adequate accounting and reported none in its tested scope; not universal absence. |
| Missing / not supplied | Evidence was not provided; it is neither positive nor negative. |
| Not applicable | The method does not apply under its declared input/model conditions. |
| Failed / unavailable / interrupted | No valid completed conclusion for that branch. |
| Incomplete / truncated | Some work or output exists, but accounting is incomplete; preserve available rows and uncertainty. |
| Conflicting | Evidence items support incompatible or competing interpretations; do not hide the conflict with an aggregate winner. |
| Unresolved | Available evidence does not distinguish among live alternatives. |

These are semantic categories for review, not approved enum spellings. Keep
validity, applicability, execution, result, and interpretation as separate
axes. A completed no-hit is not the same as a failed search; a non-detection is
not evidence against a class unless an independently justified sensitivity
model supports that interpretation.

## 2. Dependencies, correlated evidence, and optional ranking

Evidence should be represented as a provenance/dependency graph or equivalent
traceable structure. Examples of dependence to expose include M6 assembly and
read-back using the same source reads; M5 and M13 reusing the same caller
events; M7 and M14 using declared observation metadata; M8 and M9 sharing
related database records; and multiple tools consuming one alignment or model
family. A single event or source observation must not be counted repeatedly
because it appears in multiple report tables.

M15 should first support filtering, grouping, and display while retaining raw
states. If a future reviewer approves a follow-up ranking, the policy must
declare:

- the decision being prioritized (for example, assay follow-up capacity), not
  a biological class;
- eligible evidence dimensions and dependency/correlation handling;
- the treatment of missing, failed, conflicting, and not-applicable evidence;
- any weights or objective functions and their rationale;
- uncertainty, rank stability, sensitivity to weights and missingness, and
  benchmark calibration status;
- the human review/override path and output language.

No default Bayesian score, likelihood ratio, weighted sum, or “confidence”
number is approved. Naive addition of correlated evidence can overstate support.
Even a calibrated priority is a decision aid, not identity, novelty, function,
or helper-dependence classification.

Rule-based evidence matrices, likelihood/Bayesian integration, and
multi-criteria decision analysis are candidate design families, not
interchangeable implementations. The descriptive matrix is the recommended
initial baseline because it conserves the evidence states without inventing
priors or weights. A future quantitative method must justify its dependence
model, missingness assumptions, intended decision, and calibration against an
independent benchmark before it influences follow-up priority.

M15 introduces no new biological reference set by default. It must carry
forward each linked artifact's source, version, provenance and applicable use
terms; aggregation does not grant permission to redistribute upstream records.
Before exporting a dossier or benchmark bundle, confirm that the underlying
read, reference, model, and evidence licenses/access terms permit that use.

## 3. Validation and cache identity

**Software validation:** synthetic typed upstream bundles exercising one
positive, scoped no-hit, missing, not-applicable, dependency failure,
interruption, truncation, invalid artifact, and conflicting-evidence
combination; repeated/shared source dependencies; deterministic dossier
assembly; partial inputs; and corrupted provenance. Assert that no incomplete
or missing item turns into a negative and no shared evidence is duplicated as
independent support.

**Biological validation:** any numeric integration or ranking requires
independently curated labels, explicit intended-use population, and held-out
validation in M16. Without these, test only rendering and record conservation.

**Experimental confirmation:** M15 does not perform or infer experiments.
Functional, topology, DVG interference, and helper-dependence claims remain
dependent on the corresponding claim-specific assays and controls.

A future M15 cache identity should bind the exact upstream result manifests,
hashes and status axes actually consumed; the dossier schema, evidence-link and
dependency semantics; the ranking objective/policy if selected; and the
renderer/normalizer identities affecting output. Missing optional upstream
branches must be represented explicitly. M15 changes must not invalidate
unchanged upstream stages.

### UNRESOLVED DECISION

Decide whether M15 initially stops at a descriptive dossier or includes any
ranking; which evidence state names and cross-stage provenance references are
canonical; and who approves a ranking objective, weights, and calibration
standard. The no-classification boundary is not optional.

## 4. Sources checked

1. Linkov I, Massey O, Keisler J, Rusyn I, Hartung T. “From ‘weight of
   evidence’ to quantitative data integration using multicriteria decision
   analysis and Bayesian methods.” *ALTEX* 32 (2015): 3–8.
   [doi:10.14573/altex.1412231](https://doi.org/10.14573/altex.1412231).
2. Wilkinson MD, et al. “The FAIR Guiding Principles for scientific data
   management and stewardship.” *Scientific Data* 3 (2016): 160018.
   [doi:10.1038/sdata.2016.18](https://doi.org/10.1038/sdata.2016.18).
3. [Current stage-scoped identity and reuse policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).
4. [Current M5–M14 evidence boundaries](../ROADMAP.md) and the
   [frozen M15 contract](../M15_CONTRACT_FREEZE.md), which deliberately
   excludes M11 artifacts.

M15 remains planned. Ranking is not classification, and missing evidence is not
negative evidence.
