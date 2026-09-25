# M1–M6 scientific-claims and documentation audit

## Scope and conclusion

This is a scientific-claims review, separate from the M6 software/workflow
audit. It compares milestone documentation, current implementation, and the
relevant tests. M6 was merged to the authoritative `main` branch in PR #18 at
`d597c3f6e86555dfbca64d249dde3fe726bed654`; the five configured checks on that
merge commit passed. This review concerns software evidence and scientific
claims, not biological validation.

**Conclusion:** M1–M6 provide evidence that specified software stages,
provenance checks, and technical evidence calculations operate as implemented.
They do **not** establish satellite or helper-dependent identity, novelty,
biological function or significance, DVG/non-DVG identity, reference-panel
completeness, or biological discovery performance. “Supported” below refers to
the stated software behavior, not to a biological interpretation.

## Findings

| Topic | Disposition | Evidence and limit |
| --- | --- | --- |
| M1–M4 scope | **Supported with qualification.** M1 is workflow/adapter infrastructure; M2 records supplied reference provenance and imports records; M3 provides registered generic assembly; M4 connects typed artifacts, supplied-reference comparison, and reporting. These are not a validated discovery chain. | Current scope and boundaries are summarized in the [M1 foundation](M1_FOUNDATION.md), [M2 reference/acquisition](M2_REFERENCE_ACQUISITION.md), [M3 assembly](M3_ASSEMBLY.md), and [M4 integrated workflow](M4_INTEGRATED_WORKFLOW.md) documents. They describe software behavior and artificial tests, not biological validation. |
| Reference scope | **Supported only for the declared inputs.** M4 BLAST compares against supplied references with BLAST defaults and no additional identity/coverage thresholds. M6 checks reference FASTA IDs against the roles table and binds evidence to that FASTA's digest. Its minimap2 command uses `-a -x sr --secondary=no`; the screen does not apply read-support MAPQ, identity, or aligned-fraction cutoffs. | M4 says reference roles come from supplied metadata, no automatic curation occurs, and a no-hit means no match under that comparison ([conditional tools](CONDITIONAL_TOOLS.md#L44-L48), [BLAST scope](CONDITIONAL_TOOLS.md#L80-L90)). M6 input checks and command are in [residual evidence adapter](../satellite_discovery/residual_evidence_adapter.py#L200-L253). Tests reject undeclared references and incomplete accounting ([residual read tests](../tests/test_residual_reads.py#L52-L84)). Therefore “residual” does not mean absent from all relevant genomes, novel, or biologically unclassified; it means no primary mapped record under this run's declared reference and mapper settings. |
| M5 DVG evidence | **Supported as caller-specific evidence; biological classification is unsupported.** The ViReMa adapter can report normalized events and scoped statuses when its completion and read-count checks pass. `NO_DVG_EVIDENCE_DETECTED` means this configured caller reported no supported junctions in a completed run; it does not establish non-DVG identity. | Current limits are documented in the [M5 audit](M5_AUDIT.md) and [M5 DVG evidence summary](M5_DVG_EVIDENCE.md). Tests verify a zero-event result is not rendered as confirmed non-DVG ([DVG workflow tests](../tests/test_dvg_workflow.py#L111-L129)); completion/read-count requirements are covered in [DVG parser tests](../tests/test_dvg_evidence.py#L95-L150)). No sensitivity, specificity, or biological truth-set result is supplied. |
| M6 residual classification | **Supported as a technical partition, with important scope limits.** Every input read must have exactly one primary SAM record, and mapped coordinates and reference dictionaries must match the declared FASTA. A fragment is excluded from residuals if either mate has a primary mapping; only fragments with no mapped primary record are retained. Read length, ambiguous-base fraction, entropy, and mean quality then divide residuals into assembly-eligible and retained-unassembled. | The implementation validates accounting and reference bounds ([SAM validation](../satellite_discovery/residual_reads.py#L146-L232)) and assigns paired/read outcomes ([triage](../satellite_discovery/residual_reads.py#L310-L343)). Tests cover incomplete accounting, mismatched reference scope, and a mapped mate excluding both mates ([residual read tests](../tests/test_residual_reads.py#L52-L108)). A mapped primary record is not required to pass M6's later read-support MAPQ/identity/fraction criteria to count as mapped at the reference-screen step. |
| M6 assembly/read-back | **Supported as configured technical read-back, not independent biological confirmation.** Only eligible residual fragments enter assembly and read-back. `READ_SUPPORTED_ASSEMBLY` means the contig meets the configured alignment-quality, distinct-sequence, distinct-fragment, breadth, and depth rules. Crucially, the read-back mapper receives the same eligible source fragments used for assembly; it is a separate alignment step, not an independent sample, held-out read set, or orthogonal assay. Fragment IDs and distinct sequence hashes are not proof of independent molecules. | Assembly receives the eligible FASTQ, and those same fragment IDs are selected again for support mapping ([adapter](../satellite_discovery/residual_evidence_adapter.py#L328-L385)). Default criteria are in [M6 defaults](../satellite_discovery/residual_evidence_adapter.py#L27-L35); per-read and per-contig rules are in [read support](../satellite_discovery/read_support.py#L166-L268), with paired resolution requiring both mates on one supported contig ([paired resolution](../satellite_discovery/read_support.py#L294-L309)). Synthetic tests exercise support, insufficient support, and cross-contig paired ambiguity ([read-support tests](../tests/test_read_support.py#L52-L202)). This does not validate assembly accuracy on biological samples. |
| Small-sequence caveat | **The implementation limit is documented; biological impact is unvalidated.** M6 has no positive minimum contig-length cutoff beyond non-empty FASTA validation. Its default 50-base minimum read length can keep shorter residual reads out of assembly while retaining them as residual evidence. Assembler-specific behavior may separately affect which contigs are emitted. Neither fact establishes recovery or exclusion performance for very small satellite/subviral sequences. | The defaults and configuration bounds are in [M6 adapter](../satellite_discovery/residual_evidence_adapter.py#L27-L35) and [triage validation](../satellite_discovery/residual_evidence_adapter.py#L172-L198); FASTA parsing rejects empty sequences but imposes no minimum positive length ([sequence catalogue](../satellite_discovery/sequence_catalogue.py#L23-L69)). The [M6 audit](M6_AUDIT.md) records the implementation and biological limits. No biological small-sequence benchmark was identified. |
| Biological identity, significance, and performance | **Unsupported.** No M1–M6 evidence justifies a confirmed satellite, helper-dependence, novelty, non-DVG, contamination, candidate-significance, or calibrated performance claim. | The [M4 workflow](M4_INTEGRATED_WORKFLOW.md), [M5 DVG evidence](M5_DVG_EVIDENCE.md), and [M6 audit](M6_AUDIT.md) distinguish synthetic software checks from reference completeness, biological truth, and validated performance. |

## Documentation corrections in the post-M6 consolidation

The following documentation changes reconcile current capability statements
without changing M6 production behavior or scientific thresholds:

1. M6 residuals are defined against the declared FASTA and recorded minimap2
   settings; either mapped mate excludes a pair, and later read-support cutoffs
   do not change the reference-screen decision.
2. Read-back is described as a separate alignment using the same eligible
   reads supplied to assembly. `READ_SUPPORTED_ASSEMBLY` is a technical status,
   not independent biological validation.
3. Configurable defaults are identified as operational project settings, not
   biologically calibrated thresholds.
4. The README and milestone documents distinguish implemented M1–M6 software
   from the unvalidated biological discovery goal.
5. M4-era handoff, M1 audit, and earlier progress/roadmap reports are
   explicitly marked as historical, with links to current M5/M6 documentation.
6. M5 wording now describes caller-specific junction evidence; zero events
   remain narrowly scoped to a completed configured run.
7. The current roadmap marks M1–M6 implemented and M7–M16 planned; no M7 work
   or production-science changes are included.

No thresholds were changed, no M7 work was started, and this review makes no biological identity or significance claim.
