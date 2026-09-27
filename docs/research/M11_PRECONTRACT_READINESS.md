# M11 pre-contract readiness review

**Review type: read-only scientific and architectural assessment.** M11 remains
planned and unimplemented. This review does not change production code, tests,
the README, or the roadmap; install tools; retrieve model/database payloads; or
analyze candidate sequences.

## 1. Executive readiness verdict

The existing research is sufficient to recommend a narrow, synthetic/offline,
folding-first M11 architecture. It is **not sufficient to freeze the contract
without reviewer decisions** about input views, region policy, outputs,
resource limits, and tool/distribution terms. Contract work can proceed; freeze
and implementation should wait for those decisions.

The current [roadmap](../ROADMAP.md) is authoritative: M1–M10 are implemented
as scoped software milestones, while M11–M16 remain planned. Some M11–M16
planning documents still describe M10 as planned. That historical status
wording does not override the roadmap or the implemented
[M10 contract](../M10_CONTRACT_FREEZE.md).

M11 should report model-dependent predicted structure and, if separately
selected, matches to named structural models. These are computational
observations, not proof of native folding, catalytic activity, expression,
biological function, satellite identity, helper dependence, or novelty. A
synthetic/offline pass can validate software behavior and accounting only; it
cannot establish biological performance.

## 2. The M11 scientific question and boundary

M11 should answer: **What secondary structure does a specified RNA analytical
view predict under a named model and conditions, and does that view match any
of a specified set of structural family models?**

Keep these as separate evidence records:

1. A single-sequence fold prediction, including the exact input view,
   orientation, model, parameters, and limitations.
2. Optional named-family/profile matches with model identity, thresholds,
   coordinates, alignment, competing matches, and search completeness.
3. Optional ribozyme-compatible evidence only when it comes from a named,
   defensible family/model review with adequate sequence and structural context.
4. Any supplied assay result as its own experimental record, never inferred
   from the computational records.

M11 is an optional evidence layer, not a required pass/fail gate for other
stages. It must not infer native structure, catalytic activity, self-cleavage,
RNA expression, replication role, satellite identity, helper dependence,
novelty, or biological function. A fold energy is not a calibrated probability.
A model no-hit means only that a completed search did not meet the declared
criteria in the named model set.

These boundaries follow the M11 research and cross-stage architecture, and are
consistent with the current M10 ownership and handoff contracts.

## 3. Recommended baseline

| Classification | Recommendation |
| --- | --- |
| **CORE** | One single-sequence secondary-structure prediction for an explicitly defined RNA analytical view, using ViennaRNA RNAfold as the selected engine. Initially retain the MFE structure and energy, with full tool/model/parameter provenance and typed execution accounting. This is a core M11 capability, but M11 itself remains optional to the wider pipeline. |
| **OPTIONAL** | Partition-function/ensemble evidence from the same pinned ViennaRNA release, if a downstream uncertainty question justifies retaining it. A separate Infernal `cmscan` branch against one frozen, versioned Rfam model snapshot may be added only after its model set, thresholds, and accounting are approved. |
| **DEFERRED** | R-scape or other comparative covariation analysis until eligible alignments and independent variation are defined; hand-coded ribozyme motifs; custom covariance models; additional folding packages; candidate-level shuffled-background scoring; and any catalytic or functional claim. These add distinct validation and provenance obligations without being necessary for a minimal M11 baseline. |

The fold runner should not silently substitute another engine or normalize
input. If the selected runtime is missing, report `DEPENDENCY_UNAVAILABLE`.
That state does not block M1–M10 or turn into a no-fold/no-signal result.
ViennaRNA's redistribution terms need project approval before bundling or
distribution; if they are unacceptable, defer the folding implementation or
make a separately reviewed engine choice rather than silently switching.

## 4. Method and tool review

### ViennaRNA / RNAfold

The official RNAfold 2.7.2 manual documents minimum-free-energy (MFE) structure
and energy output. With partition-function mode, it also reports ensemble free
energy, MFE frequency, ensemble diversity, and base-pairing probabilities.
The manual warns that MFE and partition-function calculations can use different
energy settings unless dangling-end behavior is made explicit. If both branches
are selected, freeze a consistent parameter profile rather than relying on
defaults. The core contract should pin the executable/library version, energy
model, temperature, constraints, dangling-end setting, parser, and output
format.

As checked on 27 September 2026, ViennaRNA 2.7.2 is the latest listed release.
The official Python package listing contains CPython 3.11 and 3.12 wheels for
Windows x86-64 and Linux x86-64, in addition to other platform wheels. This
aligns with the project's Windows and Linux CI targets, but the selected wheels
and actual import/fold smoke tests must be verified in those environments
before CI provisioning. The official installation guide also describes
precompiled Linux and Windows binaries and a separately installable Python
interface.

The official license page permits research, educational, and commercial use and
modification subject to stated conditions: the package and derived works are
not redistributed for a fee other than media costs, authors and the University
of Vienna institute receive credit, and commercial-product users are asked to
contact the authors. These are the published terms, not a legal conclusion
about this project's distribution model. Obtain approval before bundling.

RNAfold's documented handling of T/U makes an explicit analytical view
important: it can automatically substitute T with U by default. M11 must not
delegate a silent transformation to that default. Preserve the immutable
upstream sequence and create a separately identified, hashed, coordinate-mapped
RNA view only under an approved policy.

### Infernal and Rfam

Infernal `cmscan` searches sequences against a covariance-model database;
`cmsearch` searches a covariance model against sequence targets. Rfam's
official downloads page describes `Rfam.cm.gz` as the family covariance models
file for use with `cmscan`. The current official release is Rfam 15.1 (January
2026); the site states that Rfam data are CC0 and provides a mutable `CURRENT/`
path as well as versioned archives. Infernal's official site lists version
1.1.5 (September 2023) and a standard BSD license. Its official prebuilt
distribution lists Linux and macOS binaries, not Windows binaries; native
Windows support should not be assumed.

These terms make a frozen profile branch feasible to evaluate, but do not make
it necessary for the synthetic folding baseline. Do not use `CURRENT/` as a
reproducible input. If approved later, pin the Rfam release, selected model
accessions and clan policy, model-file hash, threshold source, Infernal build,
and retrieval provenance. Run the optional external-tool branch in a platform
where its build is verified; use synthetic model fixtures for cross-platform
parser/accounting tests. A no-hit is permitted only after every declared model
and query has completed with valid output and complete accounting.

No Rfam payload, Infernal database, or candidate sequence was retrieved or
searched for this review.

## 5. Ribozyme evidence strategy

Do not add a generic motif detector to the first baseline. Short sequence motifs
can match by chance, and a predicted fold or motif alone does not establish the
complete family context, conserved catalytic residues, or cleavage geometry.
Do not report “functional ribozyme” or “self-cleaving” from M11 computation.

An optional named Rfam/Infernal model match may be reported as a model match.
A stronger “ribozyme-compatible candidate” label requires a separately frozen
family-specific rule for the required sequence and structural context,
catalytic features, competing matches, and completeness. Any activity claim
requires a suitable cleavage assay with controls and product/site checks;
mutant/rescue evidence and in-vivo context may be needed for the corresponding
biological-role claim. Experimental results remain separate from prediction
records.

## 6. MFE, ensemble evidence, and controls

For the minimal baseline, retain the MFE structure and energy under a named
energy model and conditions. The MFE is an optimum under that model, not a
confidence value, and standard secondary-structure prediction does not
represent all pseudoknots, tertiary contacts, cellular conditions, or
co-transcriptional effects.

Partition-function outputs are a defensible **optional** extension when the
contract needs an uncertainty description: ensemble free energy, ensemble
diversity, and base-pair probabilities. Do not add centroid/MEA structures or
normalized-energy scores merely because the engine can produce them. If
probabilities are retained, specify their representation, any storage
threshold, and the corresponding raw-output hash. Do not compare raw MFE values
as candidate significance scores across different lengths or compositions.

Length-, mono-/dinucleotide-composition-, and complexity-matched nulls can help
evaluate whether a proposed fold-based candidate-generation rule overcalls
ordinary sequences. They should be part of a separately designed empirical
validation or M16 benchmark, not a required per-candidate M11 computation.
Any normalized statistic requires a predeclared null-generation policy and
validation; no such score is justified by the current research.

## 7. Input, length, and applicability policy

The source of truth is the validated M6 candidate handoff. M10 accepts declared
molecule type and IUPAC nucleotide symbols, preserves exact source letters, and
does not silently equate T and U. M11 may create a derived analytical view, but
must not alter or replace that source record. M7–M10 results are optional
context and must not determine basic folding eligibility.

Recommended initial policy:

- Fold the exact supplied candidate in its producer-declared orientation; do
  not reverse-complement, trim, join, close, rotate, or create windows.
- For a declared DNA sequence, a T-to-U conversion may be used only as an
  explicit derived RNA view with its own digest, one-to-one coordinate map, and
  recorded transformation policy. Do not infer molecule type.
- For valid ambiguous IUPAC symbols outside the engine's explicitly tested
  alphabet, preserve the valid source but mark the folding branch
  `NOT_APPLICABLE` under the selected input policy. Do not expand ambiguities
  into multiple sequences in v1. Invalid source symbols or identity/provenance
  failures are `INVALID_CANDIDATE`.
- Conflicting, unknown, or mixed molecule-type information that prevents an
  unambiguous analytic view is `INSUFFICIENT_INFORMATION`; do not silently
  normalize T/U.
- A partial candidate may be folded as the exact supplied fragment if it meets
  the declared method/input policy. Mark its supplied completeness and avoid
  claims about missing flanks or the full molecule.
- Low-complexity, homopolymer, GC-rich, and AU-rich inputs may yield a predicted
  fold; they are not biological evidence by themselves. Do not introduce a
  biological minimum length. Define any maximum length, memory, CPU, or timeout
  as an explicit software/resource cap. A pre-run cap should be reported as a
  limitation, not as a biological exclusion; interrupted or partially
  accounted execution must not become a completed result.
- Treat the source as the supplied linear representation. M10's
  `CIRCULAR_COMPATIBLE_SEQUENCE_ARCHITECTURE_REPORTED` is not proof of
  circularity. Rotation, wraparound windows, or circular folding are deferred
  unless separately authorized as hashed derived views with coordinate maps
  and a frozen policy.

The RNAfold version's behavior for every accepted ambiguity code must be tested
directly before widening the baseline alphabet. Do not assume that an upstream
IUPAC validator guarantees that a folding engine assigns scientifically
appropriate semantics to those symbols.

## 8. Typed outcome recommendations

Keep input validity, applicability, execution/completeness, and evidence as
separate axes.

| Branch | Completed result | Other required outcomes |
| --- | --- | --- |
| **Structure prediction** | `PREDICTION_REPORTED` when a valid, applicable, complete fold and parsed output are preserved. A completed fold is a prediction, not a “match” or biological positive. | `INVALID_CANDIDATE`, `SEQUENCE_UNAVAILABLE`, `INSUFFICIENT_INFORMATION`, `NOT_APPLICABLE`, `NOT_SELECTED`, `DEPENDENCY_UNAVAILABLE`, `EXECUTION_FAILED`, `EXECUTION_INTERRUPTED`, `TRUNCATED_INCOMPLETE_ACCOUNTING`, and `OUTPUT_INVALID`, as applicable. |
| **Profile/model search** | `MODEL_MATCHES_REPORTED` when one or more model matches are fully accounted. `NO_MATCH_WITHIN_TESTED_MODELS` only when the named model snapshot, thresholds, queries, output and accounting are complete and valid. | The same invalid, not-selected, unavailable, failed, interrupted, truncated, and output-invalid states; incomplete searches are not no-hits. |
| **M11 aggregate** | `COMPLETE` when every selected required branch is valid and complete. | `PARTIAL` when any selected required branch is incomplete or failed, while retaining valid evidence from other branches. An unselected optional branch is `NOT_SELECTED` and does not make the aggregate partial. Preserve branch states instead of collapsing them into a biological verdict. |

Exact enum names and whether input/applicability are separate fields remain
contract decisions. Do not mechanically reuse an M8/M9 “no hit” state for a
folding calculation.

## 9. Minimum evidence and provenance

Do not freeze Python class names in this review. The contract should define
records equivalent to:

- **`RNA_STRUCTURE_EVIDENCE`**: candidate and source-artifact identities;
  source sequence hash; analytic-view sequence hash and transformation;
  coordinate map, length, molecule type, completeness, region, and orientation;
  engine/library version and binary/build identity; energy-model identity;
  temperature and all folding parameters/constraints; structure representation
  and MFE energy; optional ensemble fields; limitations; branch status;
  raw-output and normalized-output hashes; parser/schema/stage identity.
- **`RNA_PROFILE_MATCH_EVIDENCE`** (optional): candidate/view identity;
  Infernal version/build; Rfam release and exact model-set hash; model accession
  and clan; threshold source/value; coordinates and strand; score and any
  reported significance fields; alignment; competing matches; complete
  query/model accounting; raw and normalized output hashes.
- **`RIBOZYME_COMPATIBLE_EVIDENCE`** (deferred/optional): named family and
  evidence source; required context/residues and their observed status;
  structural/motif method; competing interpretations; completeness; and
  explicit non-activity interpretation.
- **`M11_AGGREGATE_RESULT`**: exact upstream records consumed; selected branch
  set; per-branch states and evidence links; completeness; limitations; and
  provenance. It must not contain an inferred biological classification.

Keep experimental assays as separately typed supplied records. Preserve
competing folds and matches within deterministic output accounting rather than
choosing a biologically preferred interpretation silently.

## 10. Cache and reuse

An M11 cache key should include, when consumed: exact candidate and analytic
view bytes/digests; molecule-type declaration; transformation policy and
coordinate map; selected region/orientation; branch and parameter profile;
engine version/build and energy-model identity; parser/normalizer/schema
semantics; and, for profile search, exact model snapshot, thresholds, and model
selection. Cache reuse is valid only after verifying the full result manifest
and output hashes. Incomplete, malformed, or corrupt results are not no-results.

An M11-only implementation, parameter, or model change must invalidate M11
only. It must not invalidate otherwise-valid M6–M10 artifacts. Shared
validator/cache semantics may follow the project's existing shared identity
policy.

## 11. Synthetic/offline acceptance matrix

Synthetic fixtures can freeze software behavior without establishing biological
accuracy. At minimum, test:

1. A deterministic short canonical RNA and a synthetic structured/comparator
   pair, preserving structure, energy, tool version, and parameters.
2. Canonical RNA input; declared DNA with the explicit T-to-U derived view;
   valid ambiguous IUPAC input; conflicting or mixed T/U declarations; invalid
   symbols; and unsupported modified bases.
3. Partial candidate input, low-complexity/homopolymer, GC-rich/AU-rich, and
   sequence lengths at the operational resource boundary. Confirm there is no
   biological minimum-length rule.
4. Exact source-coordinate preservation for derived views, orientation, and
   boundary maps. Confirm no implicit trimming, joining, rotation, or circular
   interpretation.
5. Reproducible MFE output under a frozen build/parameter profile; when the
   optional ensemble branch is enabled, verify consistent energy settings and
   probability parsing.
6. Missing dependency, execution failure, malformed output, interruption,
   resource-cap rejection, and truncated/incomplete accounting. None may be
   serialized as a completed no-match.
7. Optional profile branch only: synthetic model match, completed no-match in
   an explicitly named toy model set, competing matches, missing model,
   unavailable runtime, malformed output, and interrupted/truncated search.
   These fixtures validate mechanics, not biological family recognition.
8. Identical-input reuse; M11 parameter/tool/model changes invalidating M11;
   and M11-only changes preserving M6–M10 reuse.

Null/shuffled controls, curated structured-RNA positives and non-catalytic
comparators, family/clade holdouts, and external reference-search correctness
are not validated by these software fixtures.

## 12. Biological-validation boundary and downstream handoff

Separate acceptance into:

- **Software correctness:** validation, provenance, deterministic serialization,
  status preservation, accounting, and cache isolation.
- **Tool integration correctness:** pinned engine invocation, parameter
  application, output parsing, and complete/error-state handling.
- **Reference-search correctness:** complete execution against the exact
  approved model snapshot and threshold policy.
- **Benchmark performance:** requires curated, rights-reviewed examples,
  relevant negative/non-catalytic structured-RNA comparators, matched decoys,
  independent family/clade holdouts, and declared metrics. This belongs to
  later empirical work/M16, not synthetic acceptance.
- **Biological structure accuracy:** requires appropriate independent evidence;
  a fold prediction alone does not validate native structure.
- **Catalytic activity or biological function:** requires claim-appropriate
  experiments. For catalysis, this includes predicted-site/product checks and
  suitable positive/negative controls; mutant/rescue evidence may be necessary.

M13 may consume an M11 record as one evidence dimension but cannot promote it
to a DVG/satellite classification or catalytic claim. M15 should preserve
uncertainty, missingness, and conflicting folds/matches. M16 can test software
and later benchmark a frozen method, but synthetic fixtures cannot validate
biological performance or any specific candidate.

## 13. Blocker classification

| Issue | Classification | Why |
| --- | --- | --- |
| Choose whether M11 v1 requires folding; select the core engine and release; approve the engine/license/packaging path. | **BLOCKS CONTRACT FREEZE** and **BLOCKS CORE IMPLEMENTATION** | The research currently calls RNAfold optional and unselected. A recommendation is not an approved dependency or distribution policy. |
| Freeze accepted molecule types, canonical/ambiguous alphabet behavior, explicit T-to-U view policy, and outcome for conflicting/unknown type. | **BLOCKS CONTRACT FREEZE** | M10 requires declared type and immutable source letters; the fold engine's conversion behavior must not silently define M11 semantics. |
| Freeze full supplied sequence versus windows, orientation, circular/rotation policy, and software resource caps. | **BLOCKS CONTRACT FREEZE** | Region/view choices affect the scientific question, coordinates, reproducibility, and cache identity. |
| Decide core MFE-only outputs versus optional ensemble/probability outputs; freeze temperature, energy model, parameters, and exact status vocabulary. | **BLOCKS CONTRACT FREEZE** | These choices change evidence meaning, schema, runtime, and completeness accounting. |
| Approve exact ViennaRNA 2.7.2 package builds for Python 3.11/3.12 on supported Linux/Windows runners, smoke tests, and any distribution constraints. | **BLOCKS CORE IMPLEMENTATION** | Current PyPI wheels are listed for the project's main x86-64 platform/runtime combinations, but they still require project CI verification and license approval. |
| Select Infernal/Rfam release, exact model subset/clans, threshold policy, payload hashes, and optional-tool platform. | **BLOCKS OPTIONAL BRANCH**; model execution additionally **BLOCKS REAL BIOLOGICAL RESOURCE USE** until approved | The branch is not needed for folding. Rfam is CC0 and Infernal BSD according to their official sources, but reproducible model selection/provisioning remains unresolved. |
| Verify R-scape terms and approve eligible alignments/variation before any comparative analysis. | **BLOCKS OPTIONAL BRANCH** | It is not suitable as a single-sequence baseline and is deferred here. |
| Curated positives, non-catalytic comparators, decoys, independent holdouts, and claim-specific assays. | **BLOCKS BIOLOGICAL PERFORMANCE CLAIMS** | No project-specific accuracy, catalytic activity, or function is established by the research or synthetic tests. This does not block a software-only contract. |
| Reconcile stale M10-planned wording in the M11–M16 planning documents. | **NON-BLOCKING / DOCUMENTATION RECONCILIATION** | The current roadmap and merged M10 contract govern actual state; this review does not edit other documents. |

Unresolved profile/R-scape resources, empirical performance, and assay
questions do **not** block a minimal fold-centered synthetic/offline contract
once its core policies are approved.

## 14. Decisions required before contract freeze

Reviewers should explicitly decide:

1. Approve the recommended core: ViennaRNA RNAfold MFE prediction, with M11
   optional to the wider pipeline; or select a different core/defer folding.
2. Approve the version, Python interface/CLI, packaging mode, platform CI plan,
   and license/distribution conditions.
3. Freeze the allowed input alphabet and exact molecule-type rules, including
   whether and how declared DNA becomes an explicit RNA view.
4. Choose full supplied sequence versus bounded windows, orientation handling,
   circular/rotated-view policy, and operational CPU/memory/length/time limits.
5. Select MFE-only core output versus any required ensemble/probability fields
   and specify the energy model, temperature, and folding parameters.
6. Freeze separate folding, profile-search, and aggregate status semantics.
   Decide whether Rfam/Infernal is an optional v1 branch or deferred.
7. Keep dedicated ribozyme detection, comparative covariation, null-based
   scoring, and biological validation outside the initial core unless a
   separately validated need is approved.

Once those decisions are recorded, the current research supports a narrow
synthetic/offline contract and acceptance plan. It does not support broader
biological claims.

## 15. Sources checked

### Project contracts and research

- [Current roadmap](../ROADMAP.md)
- [M10 exact-first contract and handoff](../M10_CONTRACT_FREEZE.md)
- [M11 RNA structure design research](M11_RNA_STRUCTURE_DESIGN_RESEARCH.md)

### Authoritative tool and model documentation

- [RNAfold 2.7.2 manual](https://viennarna.readthedocs.io/en/latest/man/RNAfold.html)
- [ViennaRNA installation guide](https://viennarna.readthedocs.io/en/latest/install.html)
- [ViennaRNA 2.7.2 PyPI files](https://pypi.org/project/ViennaRNA/2.7.2/)
- [ViennaRNA license](https://viennarna.readthedocs.io/en/latest/license.html)
- [Infernal official site, release, and BSD terms](https://infernal.janelia.org/)
- [Infernal 1.1.5 user guide](http://eddylab.org/infernal/Userguide.pdf)
- [Rfam downloads, versioned archives, and CC0 statement](https://rfam.org/downloads)
- [Rfam release notes](https://rfam.org/release-notes)

The official documentation and package listings above were checked on
27 September 2026. The scientific limits and validation recommendations are
consistent with the citations in the linked M11 research report, including
ViennaRNA folding methods, Infernal covariance models, Rfam, R-scape, and
ribozyme review literature.

M11 remains planned. This is a readiness review, not an implementation,
biological validation, or approval to retrieve biological resources.

M11 CONTRACT FREEZE: BLOCKED