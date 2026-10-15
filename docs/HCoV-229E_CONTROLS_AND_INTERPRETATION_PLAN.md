# HCoV-229E controls and interpretation plan

**Scope:** proposed future work only for GSE155986 / SRR12424250. This is not an execution authorization. No reads or reference artifacts were downloaded, and no workflow was activated.

## Before any future technical pilot

1. **Resolve sample design from source records.** Obtain a sample sheet or protocol that identifies when the 0-hour material was collected relative to inoculation, whether it is mock-treated, and what happened to the 96-hour samples listed in the GEO sample protocol and article but absent from the GEO series run set.
2. **Establish the experimental unit.** Determine whether each R1/R2/R3 label represents a separately cultured and infected MRC-5 preparation or a technical subdivision. Record cell passage, stock source, infection batch and replicate grouping. Do not treat distinct runs/accessions as independent biological replicates without this evidence.
3. **Establish input provenance.** Confirm the exact ATCC VR-740 lot/passage and any available stock sequence or certificate; confirm MRC-5 source, passage and authentication status. Keep reported stock identity separate from sequence confirmation in the run.
4. **Obtain library protocol details.** Determine whether poly-A selection, rRNA depletion, or another enrichment was applied; confirm adapters, strandedness if known, read-length distribution and library-control outcomes. Do not derive these from `cDNA` or the kit name.
5. **Resolve reference and reuse terms.** Before any reference artifact is acquired, select exact versioned host and virus records, annotation membership, rRNA representation, contaminants and controls. Review terms for the actual files, capture artifact SHA-256, keep unacquired checksums null, and keep the panel inactive until separately approved.
6. **Establish approvals separately.** Any future scientific decision, policy exception, operator authorization, and acquisition preflight are distinct, separately reviewed steps. This plan supplies none of them.

## Control design

| Control | Purpose | Required matching / interpretation |
|---|---|---|
| Infection-matched mock | Estimate host and library signals without virus exposure. | Same cell source/passage, culture timing, inoculum vehicle, handling, extraction and library preparation as infected material. The deposited 0-hour “Untreated” samples are **not** assumed to be these controls. |
| Uninfected time-matched cell control | Distinguish infection-associated changes from time-in-culture and handling effects. | At each comparison time, matched medium/handling and independent culture units. It cannot substitute for a mock if inoculum vehicle or procedures differ. |
| Extraction blank and library blank | Detect reagent, extraction and library contaminants. | Process alongside samples through the corresponding steps; retain index/barcode and batch records. A no-template PCR control does not replace these blanks. |
| Positive process control | Verify that the workflow can recover expected viral and junction evidence. | Use an independently characterized, authorized material or non-biological synthetic control. Label it clearly; synthetic recovery validates software only, not sample infection. |
| Sequencing/run controls | Identify instrument and index-related contamination. | Obtain exact control identity, lot, index design, run placement and observed results. A PhiX reference is not evidence that a particular PhiX lot was used. |
| Technical replicate | Assess library/sequencing variability. | Preserve as technical replication; do not count it as a separate biological sample. |
| Biological replicate | Support biological inference. | Separate, documented culture/infection preparations with defined experimental unit and randomization. R1/R2/R3 names alone are insufficient. |

No confirmed mock or extraction/library blank is established by the reviewed deposited series. Do not choose the 0-hour samples as negative controls until their exposure timing is clarified.

## Technical review plan if separately authorized

- Run integrity and quality checks as a technical gate: manifest, checksum, read/base counts, quality, adapters, length distribution, duplication, and contamination-control comparison. These measurements describe the file; they do not establish infection.
- Use exact pinned host and virus references only after source-term and artifact review. Keep human transcript/mitochondrial/rRNA and virus records versioned; compare against alternatives only under a documented sensitivity design.
- Preserve unmapped, multi-mapped and ambiguous reads for review. A read not mapping to the proposed HCoV-229E reference is not evidence of novelty.
- Map with a validated primary workflow and an independently implemented confirmation method on retained candidate junctions. Record tool versions, parameters, reference hashes and all supporting read identities. Synthetic benchmark performance is not a substitute for real-run validation.
- Predefine candidate filters from synthetic and control experiments before inspecting biological candidate calls. Report exact and tolerance-based breakpoint support, uniqueness of both flanks, orientation, read quality, artifact overlap, strand/library context where known, negative-control occurrence and caller disagreement. Do not invent a universal support threshold from this one run.
- Keep ordinary viral coverage, host response, transcript junctions, DVG-compatible patterns, unexplained RNA candidates and biological classifications in separate output sections.

## Interpretation tiers

| Tier | Permitted statement | Evidence needed | Not sufficient |
|---|---|---|---|
| A. Ordinary coronavirus RNA/transcription | “Reads/junctions are compatible with coronavirus RNA or transcription.” | Verified sample/run identity; quality-controlled reads; reference-aware mapping; inspect canonical leader-body/TRS context and coverage. | A GEO exposure label, one alignment, or a known reference match alone. |
| B. DVG-compatible junction | “A computationally detected junction has a deletion/rearrangement pattern compatible with a DVG.” | Multiple informative reads supporting both junction boundaries; unique/competitive mapping; adequate controls; reproducibility under alternate caller/reference settings; retained raw evidence. | A caller label, one split read, or a leader-body junction by itself. |
| C. Unexplained RNA candidate | “The sequence remains unexplained under the reviewed references.” | Competitive mapping, host/virus/reference panel review, controls, ambiguity and contamination assessment, independent confirmation. | A no-hit or unannotated region; neither proves novelty nor a new replicon. |
| D. Potential satellite-like RNA | Use only as an explicitly provisional research hypothesis after sequence validation. | Distinct replicon evidence, independent confirmation, reproducible detection, and evidence separating it from normal subgenomic RNA, DVGs, contaminants and library artifacts. | Co-detection with HCoV-229E, a short junction, no-hit, or RNA folding prediction. |
| E. Replication/helper dependence | Claim only after appropriate biological experiments. | Controlled helper-present/helper-absent comparisons, perturbation and rescue where feasible, replication/propagation evidence, independent repeats and orthogonal assays. | Co-occurrence, temporal correlation, computational structure, or a DVG-compatible pattern. |

## Interpretation and reporting safeguards

- A normal coronavirus subgenomic RNA leader-body junction is expected biology and is not automatically a DVG.
- Distinguish alignment evidence from caller-derived events; preserve disagreement and unknown/ambiguous reads.
- Separate observed evidence, study-reported metadata, computational interpretation, and biological conclusion.
- Report negative findings with measured detection limits and controls; absence of a call does not establish absence of viral RNA.
- Require independent experimental confirmation before claims about replication, interference, viral fitness, or helper dependence.
- Do not label the run sequence-confirmed until evidence from that exact run is assessed under an authorized process.

## Current decision

This plan is preparatory only. Current state remains **HELD**, sequence confirmation **NOT_ASSESSED**, technical decision **NO-GO for real-read analysis**, and acquisition disabled. No controls, approvals, reference activation, or real-data workflow are created here.
