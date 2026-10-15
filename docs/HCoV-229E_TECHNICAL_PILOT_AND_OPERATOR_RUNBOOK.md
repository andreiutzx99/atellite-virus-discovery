# HCoV-229E technical pilot preparation and operator checklist

**Scope:** one future, separately approved technical pilot for SRR12424250.
This document and the runnable demonstration use synthetic software fixtures
only. The demonstration does not acquire data, accept external FASTQ, or make a
biological claim. Public-virus status remains **HELD** and sequence
confirmation remains **NOT_ASSESSED**.

## Existing pipeline capability audit

| Capability | Existing implementation | Remaining limitation |
| --- | --- | --- |
| FASTQ integrity | Acquisition providers verify archive checksums; `quality_control.run_qc` fingerprints local inputs and outputs. | Neither verifies biological sample identity. Do not use for an unapproved file. |
| Read quality and counts | Portable streaming QC reports read/base counts, mean Phred, Q20/Q30, base composition, lengths, and rejection accounting. | It is a baseline, not FastQC/fastp or a validated biological filter. |
| Adapter detection and trimming | Exact configured adapter match plus end-quality trimming; rejected reads and surviving orphans are retained. | No mismatch-tolerant adapter search or adapter-specific performance validation. |
| Host/virus mapping | `alignment_adapter` reviews supplied SAM/BAM/CRAM; M6's minimap2 adapter maps residual reads back to supplied evidence. | No end-to-end host/virus mapping workflow for raw pilot reads. |
| Unmapped reads | QC outputs retain rejected/orphan categories; existing alignment review can report supplied unmapped SAM records. | No sample-wide unmapped-read extraction/review workflow. |
| Coverage | `coverage_review` reports coverage from supplied SAM or alignment blocks. | Descriptive alignment coverage only; not molecule support or biological validation. |
| Assembly | Existing M6 residual assembly and fixed artificial diagnostics use configured assemblers. | Not a complete raw-pilot assembly or candidate-discovery workflow. |
| Contamination | `contamination_review` summarizes supplied reference matches and technical-control observations. | Does not run a search or infer a contaminant source. |
| DVG evidence | M5 preserves caller-scoped observations and evidence; later stages maintain explicit review boundaries. | No DVG identity, interference, or helper-dependence claim follows from these outputs. |
| Provenance | Stage manifests, file digests, tool/runtime identity, and reports exist across supported workflows. | Reference provenance and access terms must be reviewed before selecting any real host/virus panel. |

## Synthetic-only workflow

The versioned demonstration generates five artificial reads—host-like,
virus-reference-like, unrelated, adapter-bearing, and low-quality—and two
deterministically generated reference sequences, runs the portable QC and
minimap2 against those synthetic references, parses the resulting SAM with the
existing coverage review, and writes:

- input/reference integrity digests;
- read count, quality, adapter-match, trimming, and rejection summaries;
- reference-labelled mapped counts, unmapped count, and synthetic coverage;
- reference provenance and minimap2 version;
- elapsed time, input/output byte counts, and explicit limitations;
- JSON, CSV, and HTML reports.

Run it only in a new output directory:

```sh
python -m satellite_discovery.technical_pilot --output /tmp/hcov229e-synthetic-demo
```

The command accepts no FASTQ, SRA accession, reference panel, or network
argument. It cannot process SRR12424250. Its host-like and virus-reference-like
labels describe fixture roles, not biological sequences.

## Readiness and operator checklist

The project has no genuine scientific approval or production operator
authorization for this pilot. The approval JSON in `docs/` is a template, not a
signed decision. A valid signature by itself does not authorize acquisition.
The live single-run path remains blocked unless the independent trust, approval,
authorization, fresh-source, and audit checks all pass.

Before any future action, an authorized operator should verify each item with
the responsible data owner/security reviewer:

- [ ] Confirm the intended run and scope remain exactly SRR12424250 / HCoV-229E.
- [ ] Review the saved source evidence and verify its current refresh result.
- [ ] Confirm the scientific decision is genuinely signed by separate trusted
      owner and independent-reviewer keys; do not create or edit signatures.
- [ ] Confirm an independent operator authorization is valid, single-use, and
      bound to the run, manifest, policy, and limits.
- [ ] Perform a non-executing readiness check first; a blocked result is a stop,
      not a prompt to bypass a check.
- [ ] Inspect the durable audit and resolve any incomplete/failed state before
      attempting another operation.
- [ ] Validate any future acquired file against the approved manifest and
      checksum before downstream QC.
- [ ] Preserve input, reference, tool, configuration, report, and audit
      provenance together.
- [ ] Keep every technical result separate from biological interpretation.

Do not download reads, run real-data QC/mapping/assembly, create production
keys, issue authorizations, or change the 1 GB limit under this preparation.
The synthetic report is not evidence of viral presence, novelty, DVG status,
helper dependence, or satellite-virus discovery. A no-hit does not establish
novelty; co-detection does not establish helper dependence; one run does not
establish reproducibility.

## Blockers to the genuine pilot

The real-data path remains blocked pending genuine externally provisioned trust,
scientific approvals, operator authorization, approved reference provenance and
terms, and review of a complete real-read technical workflow. The synthetic
demonstration validates only software behavior on generated fixtures.
