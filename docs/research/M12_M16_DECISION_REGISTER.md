# M12–M16 decision register

**Status: unresolved-decision inventory for later review; 27 September 2026.**
This register distinguishes work that can proceed with existing artifacts and
synthetic fixtures from choices that gate optional branches, real data, or
biological claims. A missing optional resource is not a core implementation
blocker and must not cause candidate rejection.

The current [roadmap](../ROADMAP.md) is authoritative: M1–M11 are implemented
as scoped software milestones; M12–M16 remain planned and not implemented.
Earlier local planning snapshots that list M10 or M11 as planned are historical
and superseded. The M9 contract also contains a historical status note. This
register does not change roadmap status or authorize implementation.

Blocking labels below use the requested categories:

- **BLOCKS CONTRACT FREEZE** — semantics/interfaces for the named branch
  cannot be frozen until the choice is made.
- **BLOCKS CORE IMPLEMENTATION** — the required baseline path cannot be
  implemented safely until the choice is made.
- **BLOCKS OPTIONAL BRANCH** — only the explicitly optional tool, model,
  statistic, or ranking branch waits.
- **BLOCKS REAL-DATA EXECUTION** — synthetic design can proceed; actual source
  data cannot be accessed/analyzed yet.
- **BLOCKS BIOLOGICAL CLAIMS** — software output may exist, but the named
  biological statement is not supported without additional evidence.
- **NON-BLOCKING / DEFERRED** — no current core contract or implementation
  depends on this choice.

| Milestone / unresolved choice | Safe working baseline | Actual blocking scope | Decision owner / when to revisit |
| --- | --- | --- | --- |
| **M12 — permitted read and metadata access, purpose, privacy/consent, retention, and deletion rules** | Design artifact-only summaries and synthetic fixtures; do not access new reads or sensitive metadata. | **BLOCKS REAL-DATA EXECUTION** for any new raw-read/control analysis; **BLOCKS BIOLOGICAL CLAIMS** about source or contamination. It does not block an offline contract or artifact review. | Data owner and authorized privacy/scientific reviewers, before real-data use. |
| **M12 — whether FASTQ, SAM, BAM, or CRAM is the accepted optional input boundary; required accounting/reference tags** | Consume validated saved M5/M6 artifacts by identity; show missingness for absent files. | **BLOCKS OPTIONAL BRANCH** for formats not already supported. Does not block M12 artifact-only baseline. | M12 contract owner, before defining any new reader or remapping branch. |
| **M12 — control roles, matching criteria, batch/library/index fields, and adequacy rules** | Preserve controls as unknown/unavailable unless explicitly declared and matched. | **BLOCKS CONTRACT FREEZE** for control-comparison interpretation; **BLOCKS REAL-DATA EXECUTION** and **BLOCKS BIOLOGICAL CLAIMS** for control-based attribution. | M12 scientific/data owners, before use of real controls. |
| **M12 — approved source hypotheses, reference/control panel, and language for attribution** | Link existing M8/M6 context as hypotheses; no automatic source verdict or rejection. | **BLOCKS OPTIONAL BRANCH** for new panel searches; **BLOCKS BIOLOGICAL CLAIMS** for a source attribution. | Authorized curator and scientific reviewer, before panel selection or source claim. |
| **M13 — canonical cross-caller event identity, coordinate normalization, and supported class vocabulary** | Import M5 records unchanged into a descriptive hypothesis/evidence matrix; keep caller and reference scope attached. | **BLOCKS CONTRACT FREEZE** for any cross-caller normalization/agreement output; **BLOCKS OPTIONAL BRANCH** for comparative caller execution. It does not block importing M5 records. | M13 method owner and biological reviewer, before combining caller outputs. |
| **M13 — curated comparator membership, evidence tier, and exclusions** | Define manifest schema and use synthetic fixtures; no comparator label is treated as universal truth. | **BLOCKS REAL-DATA EXECUTION** for comparator evaluation; **BLOCKS BIOLOGICAL CLAIMS** about differential performance or class. A basic M13 dossier can precede it. | Curator and benchmark reviewer, before empirical comparison. |
| **M13 — DI-tector source/version/terms; VODKA2 and DVGfinder code, model, dependency, and data rights** | Keep them out of required CI and do not install/bundle; use existing M5 artifacts only. | **BLOCKS OPTIONAL BRANCH** for each unresolved external caller. It does not block M13 core evidence linkage. | Software rights/provisioning reviewer, before optional evaluation. |
| **M13 — whether event evidence alone may be summarized as a DVG differential** | Preserve deletion/copy-back/snap-back/recombination hypotheses separately from caller event observations; retain unresolved alternatives. | **BLOCKS BIOLOGICAL CLAIMS** of identity/interference; any classifier or threshold branch is also **BLOCKS OPTIONAL BRANCH** pending validation. | Scientific reviewer, before making class or interference claims. |
| **M14 — observational unit and verified independence rule** | Preserve explicit sample/run/study IDs, missingness, and tested denominators; report descriptive counts only where defined. | **BLOCKS CONTRACT FREEZE** for inferential grouping/association semantics and **BLOCKS REAL-DATA EXECUTION** where units cannot be linked. Basic synthetic schema/count tests can proceed. | M14 scientific/data owners, before association estimates. |
| **M14 — matched candidate/helper datasets, detection limits, controls, confounders, and denominators** | Do not treat absent rows or unmatched samples as negatives; allow “insufficient matched evidence.” | **BLOCKS REAL-DATA EXECUTION** for association estimates; **BLOCKS BIOLOGICAL CLAIMS** beyond descriptive scoped co-occurrence. | Curator/statistical reviewer, before interpreting observational analysis. |
| **M14 — abundance normalization/model and sparse-data threshold for any inferential branch** | Report raw counts/denominators or no estimate; no mandatory statistical dependency. | **BLOCKS OPTIONAL BRANCH** for abundance modeling; does not block descriptive summaries. | Statistical reviewer, before model selection; retain uncertainty and study structure. |
| **M14 — experiment sufficient to support dependence** | Keep dependence separate from association and describe it as untested when no experiment is supplied. | **BLOCKS BIOLOGICAL CLAIMS** of demonstrated dependence, not the observational M14 contract. | Biological investigators and institutional reviewers, before a dependence claim or assay. |
| **M15 — canonical cross-stage state axes and evidence-link/interface semantics (resolved by frozen contract)** | Preserve exact source artifact/schema/status and add the six lossless semantic axes and supported dependency edges defined by the [M15 contract](../M15_CONTRACT_FREEZE.md#4-evidence-envelope-and-outputs). | **RESOLVED — DOES NOT BLOCK CONTRACT FREEZE OR CORE IMPLEMENTATION.** This was formerly open; the frozen contract now defines the dossier interface and its lossless mapping boundary. Optional ranking and restricted export remain separate deferred choices. | Resolved by the M15 contract freeze. Revisit only if extending its accepted producer types or interface. |
| **M15 — whether any ranking is in scope; objective, missingness/dependence treatment, calibration** | Dossier/matrix first; no score, classifier, or biological winner. | **BLOCKS OPTIONAL BRANCH** for ranking only. It does not block M15 core dossier implementation. | Product/scientific reviewer, before any ranking is designed or used. |
| **M16 — claim-specific label tiers and adjudication standards** | Keep ambiguous and computational-only examples separate; develop a synthetic manifest validator. | **BLOCKS CONTRACT FREEZE** for final truth/metric definitions and **BLOCKS BIOLOGICAL CLAIMS** of benchmark performance; fixture work remains available. | Independent curators and scientific reviewers, before a truth set is used. |
| **M16 — grouping/leakage policy, split freeze, holdout custodian, and blinding** | Draft family/study/sample/lab grouping and custody protocol; do not assign actual holdouts. | **BLOCKS REAL-DATA EXECUTION** of a final confirmatory benchmark and **BLOCKS BIOLOGICAL CLAIMS** based on held-out performance. Harness implementation can use synthetic examples. | Independent benchmark custodian, before split assignment and method freeze. |
| **M16 — source terms, privacy, holdout release, and assay resources** | Keep datasets and assay resources unselected; test only manifest mechanics offline. | **BLOCKS REAL-DATA EXECUTION** for affected examples/assays; **BLOCKS BIOLOGICAL CLAIMS** requiring them. Does not block synthetic benchmark tooling. | Data owners, ethics/biosafety reviewers, and assay owners before acquisition or execution. |
| **All — exact benchmark population, minimum denominators, metrics, uncertainty, and stop rules** | Report denominators, coverage, abstentions, and limitations; do not report ungrounded accuracy/calibration. | **BLOCKS CONTRACT FREEZE** for final M16 evaluation protocol and **BLOCKS BIOLOGICAL CLAIMS** of general performance; does not block software correctness tests. | Benchmark/statistical reviewers before any final evaluation. |
| **All — optional CI/container versions and exact dependency licenses** | Keep core CI synthetic and offline; version-pin only after terms and compatibility checks. | **BLOCKS OPTIONAL BRANCH** provisioning only. No current required CI/core implementation blocker. | Maintainer and rights reviewer when selecting an external tool. |

## Decisions that do not block the current core path

- M12 can begin with verified M5/M6 artifact review and synthetic tests without
  new FASTQ, controls, or metadata. Any absence remains explicit.
- M13 can link caller-scoped M5 output and produce an unresolved evidence
  matrix without DI-tector, VODKA2, DVGfinder, or a curated biological
  comparator set.
- M14 can freeze explicit observation/missingness fields and test descriptive
  summaries with synthetic tables before a matched real cohort exists.
- M15’s first implementation should preserve state and provenance in a
  descriptive dossier. A ranking decision is not a blocker to that baseline.
- M16 manifest, leakage, and metrics machinery can be tested with artificial
  fixtures. No actual holdout is selected or assigned by this task.
- Optional resources, unavailable evidence, and failed branches must not be
  promoted to core blockers or interpreted as candidate rejection.

## Boundaries and source records

- The current roadmap sets M12 as read-origin/technical-artifact review, M13
  as DVG differential, M14 as helper association and separately supported
  dependence, M15 as transparent integration/prioritization, and M16 as
  blinded benchmarking/claim-appropriate validation.
- Current M5/M6/M7/M8/M9/M10 contracts define existing software boundaries;
  none establishes biological validation for M12–M16.
- See [resource/tool and licensing audit](M12_M16_RESOURCE_TOOL_AUDIT.md),
  [validation logistics and platform matrix](M12_M16_VALIDATION_LOGISTICS.md),
  [M12 contract](../M12_CONTRACT_FREEZE.md),
  [M12 implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md), and
  [M12 semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md),
  [M13 research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md),
  [M14 research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md),
  [M15 research](M15_EVIDENCE_INTEGRATION_DESIGN_RESEARCH.md),
  and [M16 research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md).
