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

1. **Accession-to-label provenance:** for PRJNA1244124, link each positive and purported Px31 negative from article/supplement to exact SRA run(s); confirm the target sequence/PCR result applies to that biological material. Nine public paired Illumina FASTQ records were verified, but the full truth map was not.
2. **Appropriate negatives:** require an independently tested satellite-absent sample. Non-reporting, no assembly, low depth, or a study that did not mention satellites is not a negative. Prefer helper-positive negatives with adequate read quality/depth.
3. **Library heterogeneity:** PRJNA667593 is single-end Ion Torrent size-selected small RNA; PRJNA1244124 is paired-end Illumina viral RNA. Do not pool their sensitivity estimates.
4. **Reference leakage:** freeze a target-excluded reference snapshot. Keep expected satellite sequence, PCR results, and labels out of pipeline inputs until scoring.
5. **Truth vs prediction:** orthogonal PCR/sequence evidence is distinct from assembler output and reference similarity. Pipeline output cannot validate its own label.
6. **Specificity strata:** use clean verified negatives, ordinary isolate variation, mixed infection, and DVG-containing samples separately. PRJNA525871 is a DVG challenge, not a clean satellite negative.
7. **Evaluation protocol:** pre-register exact recovery and candidate-level matching, false-positive metrics, `UNEVALUABLE` reasons, denominators, confidence intervals, duplicate-contig handling, and thresholds. Score by biological sample, not reads.
8. **Provenance/legal review:** pin accession metadata, future approved file checksums, reference FASTAs, source terms, and article licences. Public archive access is not automatically unrestricted redistribution.
9. **No contract modification in M21:** if contracts cannot accept a read class or preserve evidence, record the gap; do not change M1–M20 to force a dataset through.

## Recommendation

Approve only the **curation question** for PRJNA1244124, not read acquisition or execution. Resolve positive and Px31 sample/run mapping and PCR evidence first. If exact links and adequate quality/depth are verified, the smallest defensible later benchmark is one satellite-positive Phlox library, one independently confirmed satellite-negative/helper-positive library from the same study, and one separate mixed-infection/ordinary-variation challenge, blinded and grouped by plant. Keep DVG data as a separate follow-on challenge, outside the initial sensitivity/specificity denominator. If controls cannot be linked, there is no approved initial benchmark yet.

## Source records

- Main: `docs/M20_REGISTERED_CONTRACT_MAP.json`, `satellite_discovery/stage_registry.py`, `M20_PHASE5.md`, `.agents/outputs/m20-phase5/report.md`.
- Archive and paper references: `M21_DATASET_CATALOGUE.md`.
