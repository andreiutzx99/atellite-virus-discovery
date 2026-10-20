# M21 capability-gap assessment (design only)

**Scope:** compare the M21 question to registered stage contracts on main at `2f66cdb09c183373ddf1ea628479c4e25d1d8731`. Planning only: no code, contract, fixture, or validation changes and no biological execution.

## Existing-stage compatibility

| Existing registered capability | Potential future use | Gap / boundary |
|---|---|---|
| M4 `fastq_qc` accepts `raw_read`/`validated_fastq`, R1 and optional R2 | Validate public FASTQ and produce QC reads/manifests | Archived layout, Ion Torrent/sRNA fragment size, adapters and read lengths have not been assessed against assumptions. Separate single- and paired-end strata. |
| M4/M6 workflow and M6 residual-evidence adapter | Alignments, support/triage, reconstruction and residual evidence under existing contracts | Mapped/residual reads are not ground truth. Freeze M6 reference/roles separately from held-out target. No biological read tested here. |
| M5 DVG evidence (`dvg_virema`) | Report DVG evidence and characterize DVG confounders | DVG is not satellite RNA. PRJNA525871 is not a satellite-negative set without separate orthogonal testing. Caller availability/sample mapping need later verification. |
| M7 independent recurrence | Summarize exact recurrence/independence | Technical lanes/subsamples from one plant are not independent biological recurrence. Preserve sample grouping for external scoring. |
| M8 nucleotide homology | Compare candidates with pinned, approved reference snapshot | Including held-out target leaks truth. Exclude target/close homologs before blinded analysis and record snapshot/exclusions. This is not a novelty test. |
| M9 ORF translation/BLASTP | Descriptive coding/protein comparison | Many satellite RNAs are noncoding; no ORF/protein hit is not absence or function evidence. Secondary only. |
| M10 exact-first/repeat evidence | Repeated sequence/architecture evidence | Repeat signals do not confirm satellite identity. Report separately from target detection and specificity. |
| M12 artifact review and M15 evidence dossier | Artifact identity, producer provenance, completeness, missingness | They validate technical provenance/completeness, not biological truth. Keep labels out of inputs/config/cache/artifacts. M20 shows M15 can remain partial with M13/M14 absent. |

These stage capabilities and contract types are described in the live M20 registered contract map. M20 Phase 5 explicitly classifies biological discovery as NOT VALIDATED; stage presence is not performance evidence.

## Gaps before any biological benchmark

1. **Accession-to-label provenance (resolved for three paper samples):** NCBI SRA per-record Experiment summaries link Px15 SRX28192996 / SAMN47635716 / SRR32918045, PxBG2 SRX28192998 / SAMN47635718 / SRR32918043, and Px31 SRX28192997 / SAMN47635717 / SRR32918044. Experiment sample names match the publication and each Run links to a BioSample. Confidence is high for those mappings; do not use accession order for the other six records. These are candidates for feasibility, not yet authorized or data-use-cleared.
2. **Appropriate negatives:** require an independently tested satellite-absent sample. Non-reporting, no assembly, low depth, or a study that did not mention satellites is not a negative. Prefer helper-positive negatives with adequate read quality/depth.
3. **Library heterogeneity:** PRJNA667593 is single-end Ion Torrent size-selected small RNA; PRJNA1244124 is paired-end Illumina viral RNA. Do not pool their sensitivity estimates.
4. **Reference leakage:** freeze a target-excluded reference snapshot. Keep expected satellite sequence, PCR results, and labels out of pipeline inputs until scoring.
5. **Truth vs prediction:** orthogonal PCR/sequence evidence is distinct from assembler output and reference similarity. Pipeline output cannot validate its own label.
6. **Specificity strata:** use clean verified negatives, ordinary isolate variation, mixed infection, and DVG-containing samples separately. PRJNA525871 is a DVG challenge, not a clean satellite negative.
7. **Evaluation protocol:** define sample-level binary calls before scoring. Specificity is TN/(TN+FP) only over independently verified, evaluable satellite-negative biological samples; one sample contributes at most one sample-level FP even if it contains multiple false candidates. Report false candidate calls per negative sample and per million input reads/read pairs separately. Report candidate-level precision and recall only under frozen candidate deduplication and one-to-one matching rules; do not call FP/(FP+TN) a candidate-level false-positive rate without a defined candidate-negative universe. Publish counts, denominators, uncertainty, and UNEVALUABLE reasons.
8. **Provenance/legal review:** pin accession metadata, future approved file checksums, reference FASTAs, source terms, and article licences. Public archive access is not automatically unrestricted redistribution.
9. **No contract modification in M21:** if contracts cannot accept a read class or preserve evidence, record the gap; do not change M1–M20 to force a dataset through.

## Recommendation

Advance PRJNA1244124 from a previously unverified run map to a **mapped, conditional feasibility candidate**, not execution-ready. The direct SRA mapping is Px15 SRR32918045 and PxBG2 SRR32918043 (satellite-positive by HTS plus satellite-specific 551-bp RT-PCR/Sanger), and Px31 SRR32918044 (no target-associated reads/no expected-size satellite RT-PCR product reported; target-specific screen-negative with unknown assay detection limit). BRSV helper is independently detected in all three by HTS and RT-PCR, with Sanger confirmation for detected amplicon regions. The publication describes satellite records PV541158/PV541159 as nearly complete; do not score exact termini from those records based on the partial PCR amplicon. The minimal potential set is these three distinct plants in one study, only after FASTQ checksum/read adequacy, reuse terms, and review of negative evidence. It supports feasibility only; broader sensitivity/specificity requires leave-study-out and independent-study validation. Keep DVG as a separate challenge outside clean-negative denominators. No biological reads have been acquired or run.

## Source records

- Main: `docs/M20_REGISTERED_CONTRACT_MAP.json`, `satellite_discovery/stage_registry.py`, `M20_PHASE5.md`, `.agents/outputs/m20-phase5/report.md`.
- Archive and paper references: `M21_DATASET_CATALOGUE.md`.
