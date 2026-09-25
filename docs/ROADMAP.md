# Milestone roadmap and evidence boundaries

This is the current milestone register for the source tree after M7. It
supersedes older roadmap snapshots where their status differs. M1–M7 are
implemented as scoped software milestones; M8–M16 remain planned. A milestone
marked implemented describes software behavior, not biological validation.

## M1–M7 — implemented

| Milestone | Status | Implemented evidence layer | Boundary |
| --- | --- | --- | --- |
| M1 — Foundation | **IMPLEMENTED** | Trusted stage execution, typed inputs, bounded external calls, explicit states, provenance, and reuse checks. | Workflow correctness does not establish biological correctness. |
| M2 — Reference records and acquisition | **IMPLEMENTED** | Provenance-bearing reference snapshots/imports and registered public-read acquisition paths. | Transfer and record integrity do not certify biological identity, reference completeness, or suitability. |
| M3 — Assembly | **IMPLEMENTED** | Registered SPAdes/Tadpole adapters for supplied validated reads. | Successful execution and valid output do not measure assembly accuracy on biological samples. |
| M4 — Integrated artifact workflow | **IMPLEMENTED** | Typed handoffs, supplied-reference comparisons, context summaries, reports, preflight, and verified reuse. | This is modular supplied-artifact processing, not an autonomous discovery chain. |
| M5 — DVG evidence | **IMPLEMENTED** | Optional ViReMa caller-specific junction parsing, completion/accounting checks, scoped statuses, and provenance. | A zero-event status is not evidence that a sample or sequence is biologically non-DVG. |
| M6 — Residual assembly support | **IMPLEMENTED** | Reference-scoped primary-mapping accounting, residual triage, optional assembly, and separate read-back alignment. | Read-back uses the same eligible reads as assembly; results are technical and run-scoped. |
| M7 — Independent recurrence | **IMPLEMENTED** | Typed M6 evidence handoff and exact recurrence groups over individually read-supported contigs; declared source-read checksums and sample/run/study metadata remain visible. | Exact recurrence only; declared independence metadata is unverified, and there is no pooling, co-assembly, related-sequence clustering, or biological classification. |

## M8–M16 — planned, not implemented

No M8–M16 functionality was started by the post-M7 consolidation.

| Milestone | Status | Question / intended evidence layer | Dependencies and limits |
| --- | --- | --- | --- |
| M8 — Host/read-origin attribution | **PLANNED** | Which reads or candidate regions have support for host, organelle, vector, or other declared origins? | Requires appropriate references, contamination controls, and evidence accounting; absence of a match is not origin exclusion. |
| M9 — Candidate characterization | **PLANNED** | What sequence features, coding potential, motifs, and structural properties are supported? | Requires method/version provenance and cautious interpretation; predictions are not experimental function. |
| M10 — DVG/satellite differential evidence | **PLANNED** | Which evidence distinguishes satellite-like candidates from DVGs and other alternatives? | Requires curated independent examples and an unresolved class; M5 caller output alone is insufficient. |
| M11 — Helper association | **PLANNED** | Which candidates co-occur or covary with plausible helper systems across suitable observations? | Requires matched samples, controls, and denominators; association does not prove helper dependence. |
| M12 — Reference-aware novelty analysis | **PLANNED** | How similar are candidates to frozen, declared reference collections under recorded methods? | Requires auditable panel curation and withholding; no-hit does not prove universal novelty. |
| M13 — Contamination and artifact review | **PLANNED** | How well do negative controls, batch/lane evidence, and technical artifacts explain candidates? | Requires trustworthy controls and laboratory provenance; a control match is evidence, not automatic source attribution. |
| M14 — Evidence integration | **PLANNED** | Can independently scoped evidence be combined without hiding missingness or double-counting? | Requires declared dependencies, calibrated interpretation, and no circular reuse of the same evidence as independent support. |
| M15 — Candidate prioritization | **PLANNED** | Can candidates be ranked transparently for follow-up? | Requires predeclared objectives, validated calibration, uncertainty, and explicit unresolved outcomes; ranking is not classification. |
| M16 — Blinded biological validation | **PLANNED** | Does a frozen workflow recover independently labelled known positives while controlling false positives? | Requires held-out truth sets, justified negatives, reference withholding, predeclared criteria, and experimental or orthogonal confirmation as appropriate. |

## Supporting documents

- [Current project overview and operating limits](../README.md)
- [M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md)
- [M6 workflow audit](M6_AUDIT.md)
- [M1 foundation](M1_FOUNDATION.md) · [M2 acquisition and references](M2_REFERENCE_ACQUISITION.md) · [M3 assembly](M3_ASSEMBLY.md)
- [M4 artifact workflow](M4_INTEGRATED_WORKFLOW.md) · [M5 DVG evidence](M5_DVG_EVIDENCE.md) · [M6 residual support](M6_RESIDUAL_ASSEMBLY_SUPPORT.md)
- [M7 independent recurrence](M7_INDEPENDENT_RECURRENCE.md)