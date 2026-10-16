# M18: Synthetic read-to-candidate integration

M18 is an opt-in integration exercise for the existing registered M4, QC, M6,
M9, and M10 paths. It creates only seeded artificial A/C/G/T reads and
references. It does not download, activate, or use biological sequencing data,
and does not activate the HCoV-229E pilot.

## Run

Install the project and its declared dependencies, and make `minimap2` and
SPAdes available on `PATH`. Then run:

```sh
satellite-m18 --output generated-artifacts/m18
```

The output contains deterministic gzipped FASTQ and FASTA inputs under
`inputs/datasets/`, a source digest manifest, a separate fixture-truth sidecar,
the actual M4 stage manifest and outputs, and JSON/HTML summaries. The fixture
truth sidecar is not an input to any analysis stage. M4 invokes the registered
QC engine, M6 residual screening/assembly/read-back, M9 ORF derivation, and M10
architecture analysis.

The full integration requires `minimap2` and SPAdes on `PATH`. The report
distinguishes M4 graph completion from M18 expected-outcome completion; an M6
assembly failure remains explicit and gives the CLI a nonzero exit status.

For a simulated missing-assembler dependency, an incomplete case reports fields
like these. The `null` counts mean “not evaluated,” not zero findings:

```json
{
  "m4_stage_statuses": {
    "qc": "complete",
    "m6": "dependency_missing",
    "m9": "blocked",
    "m10": "blocked"
  },
  "stage_diagnostics": {
    "m6": {
      "m4_status": "dependency_missing",
      "report_status": "UNAVAILABLE",
      "error": {"code": "DEPENDENCY_MISSING", "message": "SPAdes is unavailable"},
      "reason": "Required optional assembler was not found."
    }
  },
  "assembly_and_read_back": {
    "candidate_availability": "UNAVAILABLE",
    "candidate_count": null,
    "support_status": "NOT_EVALUATED"
  },
  "m9_orf_evidence": {
    "aggregate_status": "BLOCKED",
    "observed_orf_count": null
  },
  "m10_architecture_evidence": {
    "aggregate_status": "BLOCKED",
    "candidate_count": null,
    "branch_statuses": null
  }
}
```

The workflow intentionally includes RNA- and DNA-labelled fixture metadata,
mapped-only controls, residual overlaps, low-quality and ambiguous reads,
low-complexity reads, and a stringent low-support read-back case. RNA/DNA labels
are declared metadata; they are not inferred from A/C/G/T sequence characters.
The synthetic-only guard checks the generated payload bytes against the
deterministic generator, rather than trusting a self-asserted manifest hash.
Changed fixture inputs are rejected.

## Reading the result

`m18-report.json` preserves QC, reference-accounting, residual, assembly,
read-back, M9, and M10 states separately. If an optional executable is absent,
the registered workflow's unavailable/blocked state is reported; it is not
replaced by fabricated alignments, contigs, or support. Exit status is nonzero
unless M4 reports a complete graph.

An M6 read-back result is technical support from the same artificial fragments
used for assembly, not independent validation. ORFs and repeats remain
descriptive hypotheses. No M8 homology source is used. Nothing in M18 establishes
biological identity, function, novelty, circularity, or satellite status.

## Frozen contracts and scope

M18 composes the existing stage contracts without changing M1–M17 behavior. It
does not loosen authorization, data-access, policy, or pathogen boundaries; it
does not claim satellite discovery. All generated artifacts are reproducible
for the fixed seeds. Generated report paths and outputs should remain outside
source control except for the checked-in synthetic sample summary.
