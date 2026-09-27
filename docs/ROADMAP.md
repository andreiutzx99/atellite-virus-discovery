# Milestone roadmap and evidence boundaries

This is the current milestone register for the source tree after the M11
RNA-fold prediction baseline. It supersedes older roadmap snapshots where their
status differs. M1–M11 are implemented as scoped software milestones; M12–M16
remain planned. A milestone marked implemented describes software behavior,
not biological validation.

## M1–M11 — implemented

| Milestone | Status | Implemented evidence layer | Boundary |
| --- | --- | --- | --- |
| M1 — Foundation | **IMPLEMENTED** | Trusted stage execution, typed inputs, bounded external calls, explicit states, provenance, and reuse checks. | Workflow correctness does not establish biological correctness. |
| M2 — Reference records and acquisition | **IMPLEMENTED** | Provenance-bearing reference snapshots/imports and registered public-read acquisition paths. | Transfer and record integrity do not certify biological identity, reference completeness, or suitability. |
| M3 — Assembly | **IMPLEMENTED** | Registered SPAdes/Tadpole adapters for supplied validated reads. | Successful execution and valid output do not measure assembly accuracy on biological samples. |
| M4 — Integrated artifact workflow | **IMPLEMENTED** | Typed handoffs, supplied-reference comparisons, context summaries, reports, preflight, and verified reuse. | This is modular supplied-artifact processing, not an autonomous discovery chain. |
| M5 — DVG evidence | **IMPLEMENTED** | Optional ViReMa caller-specific junction parsing, completion/accounting checks, scoped statuses, and provenance. | A zero-event status is not evidence that a sample or sequence is biologically non-DVG. |
| M6 — Residual assembly support | **IMPLEMENTED** | Reference-scoped primary-mapping accounting, residual triage, optional assembly, and separate read-back alignment. | Read-back uses the same eligible reads as assembly; results are technical and run-scoped. |
| M7 — Independent recurrence | **IMPLEMENTED** | Typed M6 evidence handoff and exact recurrence groups over individually read-supported contigs; declared source-read checksums and sample/run/study metadata remain visible. | Exact recurrence only; declared independence metadata is unverified, and there is no pooling, co-assembly, related-sequence clustering, or biological classification. |
| M8 — Candidate/reference nucleotide homology | **IMPLEMENTED (SOFTWARE)** | Typed candidate and snapshot inputs, role-scoped local BLASTN evidence, separate masking branches, raw outputs, and explicit incomplete/unavailable/truncated states; validated with synthetic fixtures. | Reference payloads and indexes are caller-supplied and remain external. No candidate dataset was searched during implementation. Similarity is not identity or classification; no-hit is scoped to the completed snapshot and method. |
| M9 — Translated and protein evidence | **IMPLEMENTED** | Deterministic six-frame ORF hypotheses and translation under the approved table-1/ATG-only policy, preserving nested, overlapping, and partial hypotheses. Ordinary local BLASTP against an explicitly supplied typed protein snapshot; typed no-ORF/no-hit/failure/incomplete outcomes; provenance and integrity; stage-scoped cache/reuse; synthetic/offline validation. | Protein-level computational evidence only. It does not classify satellites, establish novelty or helper dependence, or prove expression or biological function. No biological candidate dataset or protein database was searched for this implementation milestone. |
| M10 — Genome architecture and topology (exact-first baseline) | **IMPLEMENTED (SCOPED)** | Deterministic exact-first reporting of direct/inverted terminal repeats and maximal internal repeats over the validated candidate handoff, with source-linked evidence, branch accounting, provenance, and explicit limits/statuses; validated with synthetic fixtures. | Exact sequence patterns only under the frozen policy. No biological dataset or reference search, confirmed topology/circularity, completeness claim, biological classification, or functional inference. Optional M7–M9 inputs are context only. |
| M11 — RNA minimum-free-energy structure baseline | **IMPLEMENTED (OPTIONAL)** | Optional, hash-pinned ViennaRNA 2.7.2 MFE predictions for validated whole-sequence or explicitly requested regions, with source provenance, per-request accounting, and bounded isolated execution. | Predicted folds are model-dependent hypotheses, not observed structures or evidence of ribozyme activity/function. Ribozyme-family matching is not implemented. |

## M12–M16 — planned, not implemented

M12–M16 remain planned and are not implemented.

| Milestone | Status | Question / intended evidence layer | Dependencies and limits |
| --- | --- | --- | --- |
| M12 — Read-origin and technical-artifact review | **PLANNED** | What do source reads, controls, batches, and technical evidence support about candidate origin or artifacts? | Requires suitable references, controls, provenance, and read accounting; sequence similarity alone does not establish source attribution. |
| M13 — DVG-versus-satellite differential evidence | **PLANNED** | How do scoped observations bear on DVG, satellite/subviral, and other alternatives? | Requires curated independent examples and an unresolved outcome; M5 caller output alone is insufficient. |
| M14 — Helper association and dependence | **PLANNED** | What association is supported across matched observations, and is there separate evidence of dependence? | Requires suitable samples, controls, denominators, and claim-appropriate experiments; association does not prove dependence. |
| M15 — Evidence integration and transparent prioritization | **PLANNED** | Can scoped evidence and alternatives be integrated and, if justified, ranked for follow-up? | Preserve provenance, missingness, dependencies, and correlated evidence. Ranking is not classification and requires predeclared objectives and validation. |
| M16 — Blinded benchmarking and claim-appropriate validation | **PLANNED** | How does a frozen workflow perform on independent holdouts, and what biological claims receive orthogonal or experimental validation? | Requires justified positives/negatives, leakage controls, predeclared criteria, and appropriate assays; software benchmarks do not establish a candidate's identity or function. |

## Supporting documents

- [Current project overview and operating limits](../README.md)
- [M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md)
- [M6 workflow audit](M6_AUDIT.md)
- [M1 foundation](M1_FOUNDATION.md) · [M2 acquisition and references](M2_REFERENCE_ACQUISITION.md) · [M3 assembly](M3_ASSEMBLY.md)
- [M4 artifact workflow](M4_INTEGRATED_WORKFLOW.md) · [M5 DVG evidence](M5_DVG_EVIDENCE.md) · [M6 residual support](M6_RESIDUAL_ASSEMBLY_SUPPORT.md)
- [M7 independent recurrence](M7_INDEPENDENT_RECURRENCE.md)
- [M8 reference and homology specification](M8_REFERENCE_AND_HOMOLOGY_SPEC.md) · [M8 benchmark fixture design](M8_BENCHMARK_FIXTURE_DESIGN.md)
- [M10 exact-first implementation contract](M10_CONTRACT_FREEZE.md)
- [M11 frozen contract](M11_CONTRACT_FREEZE.md) · [M11 implementation notes](M11_IMPLEMENTATION.md)
- [Post-M7 roadmap reconciliation proposal](POST_M7_ROADMAP_RECONCILIATION.md)
- [M8/M9 design research](research/M8_M9_DESIGN_RESEARCH.md) · [M10/M11 design research](research/M10_M11_DESIGN_RESEARCH.md)