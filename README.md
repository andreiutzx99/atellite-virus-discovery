# Satellite Virus Discovery

**Version 0.3.0 · Python package:** `satellite-discovery`

## Overview

This project is building a reproducible, evidence-oriented workflow for
investigating satellite/helper-dependent viral elements and other unexplained
sequencing-derived candidates. The implemented M1–M6 software provides
provenance-aware acquisition and reference records, registered assembly,
typed artifact workflows, optional caller-specific DVG evidence, and a
reference-scoped residual-read and read-back stage.

M1–M6 implement technical software stages. They do **not** demonstrate that
the software discovers novel satellite viruses, classifies biological
sequences, or establishes helper dependence. This is not yet an autonomous,
biologically validated discovery pipeline.

## Scientific problem

Satellite and other subviral elements are diverse. Their interpretation can
be difficult when sequences are short, divergent, under-represented in
reference collections, dependent on helper systems, or similar to defective
viral genomes. Assembly errors, host sequences, mobile elements,
contamination, and other alternatives can also produce candidate-like
sequences. Homology searches are useful evidence, but a match or no-match
result is limited to the sequences and settings actually compared. These
biological contexts are discussed in the literature on plant satellite
RNAs/viruses, virophages, deltaviruses, and circular RNAs; those publications
do not validate this software's output or technical defaults. See
[References](#references).

## Design philosophy

- **Residual does not mean novel.** In M6 it means no primary mapping under the
  run's declared reference FASTA and configured minimap2 settings.
- **An assembled contig is a reconstruction hypothesis, not a biological
  discovery.**
- **No database match does not establish novelty.**
- **`NO_DVG_EVIDENCE_DETECTED` does not establish that a sequence is not a
  DVG.** It records a scoped result from a completed configured caller run.
- **Helper-virus co-occurrence does not prove helper dependence.**
- **The pipeline accumulates evidence rather than forcing classification.**
- Project-specific defaults are technical settings, not biologically
  validated thresholds.

## Implemented workflow — M1 to M6

| Milestone | Implemented software capability | Evidence boundary |
| --- | --- | --- |
| M1 — Foundation | Trusted stage registry, typed configuration, bounded external-tool execution, explicit states, manifests, and verified reuse. | Workflow-contract behavior, not biological analysis. |
| M2 — Reference records and acquisition | Provenance-bearing reference snapshots/imports and registered ENA acquisition with a conditional NCBI SRA Toolkit path. | Input identity and transfer checks do not certify reference completeness or biological suitability. |
| M3 — Assembly | Registered SPAdes and Tadpole adapters for supplied validated FASTQ. | Execution and output-contract checks do not validate assembly accuracy on biological samples. |
| M4 — Integrated artifact workflow | Typed handoffs, supplied-reference BLAST, occurrence/context summaries, provenance, preflight, reuse, and reports. | Modular supplied-artifact processing, not one autonomous discovery chain. |
| M5 — DVG evidence | Optional ViReMa integration that records supported caller-specific junction evidence and scoped outcomes. | Caller-specific evidence only; no DVG/non-DVG or satellite classification. |
| M6 — Residual assembly support | Reference-scoped primary-mapping accounting, conservative residual triage, optional assembly, and separate read-back support. | Technical reconstruction support using the same eligible reads, not independent biological validation. |

Detailed retrospective documents: [M1](docs/M1_FOUNDATION.md),
[M2](docs/M2_REFERENCE_ACQUISITION.md), [M3](docs/M3_ASSEMBLY.md),
[M4](docs/M4_INTEGRATED_WORKFLOW.md), [M5](docs/M5_DVG_EVIDENCE.md),
[M6](docs/M6_RESIDUAL_ASSEMBLY_SUPPORT.md). The
[M1–M6 scientific audit](docs/M1_M6_SCIENTIFIC_AUDIT.md) and
[M6 workflow audit](docs/M6_AUDIT.md) explain the evidence limits.

## Pipeline architecture

The components can be used independently or connected by a declared workflow;
the diagram is not a promise that every dataset passes through one automatic
end-to-end chain.

```text
sequencing reads and declared references
                 │
                 ├── M2 acquisition / input validation / provenance
                 ├── M2 reference snapshots and record import
                 ├── M3 registered assembly and sequence catalogues
                 └── M4 typed artifact workflow and supplied-reference review
                              │
                 optional M5 caller-specific DVG evidence
                              │
                 M6 primary mapping against declared reference FASTA
                              ↓
                 conservative residual-read triage
                              ↓
                 optional assembly of eligible residual reads
                              ↓
                 separate read-back alignment using those same reads
                              ↓
                 technical support evidence or unresolved status
                              ↓
                 planned evidence layers M7–M16
```

In paired data, a primary mapping for either mate excludes the whole fragment
from the residual pool. M6 then applies read-length, ambiguity, entropy, and
quality criteria to residual reads. Reads shorter than the default 50 bp are
preserved as residual evidence but are not eligible for assembly by default.
The assembly/read-back path does not establish the biological identity of a
contig.

## Evidence interpretation

| Evidence type | What it can support here | What it does not establish |
| --- | --- | --- |
| Technical evidence | That a declared software stage completed and met its input/output contract. | That its biological premise is true. |
| Reconstruction support | That eligible source reads passed configured read-back criteria for a contig. | Independent replication, a real satellite genome, or biological validation. |
| Sequence similarity | A reported match under the supplied reference set and comparison settings. | Reference completeness, novelty from a no-hit, or taxonomy by itself. |
| Biological association | Co-occurrence or a supplied association in the examined records. | Causation or helper dependence. |
| Biological classification | Not produced by the implemented M1–M6 pipeline. | Satellite, DVG, helper, host, or contaminant identity. |
| Experimental confirmation | Not produced by the software. | Replication, function, or biological significance. |

## Current status and future roadmap

- **M1–M6: IMPLEMENTED** as scoped software milestones.
- **M7–M16: PLANNED**, not implemented by this consolidation.

The authoritative milestone register is [docs/ROADMAP.md](docs/ROADMAP.md).
M7–M16 are not started here. Do not treat the roadmap as evidence that a
planned feature exists.

## Installation

Python 3.11 or newer is required. To install the package in an activated
virtual environment:

```console
python -m pip install .
```

The base package has no mandatory third-party Python dependencies.
Bioinformatics executables, reference databases, and files under `.tools` are
external and are not bundled by a source checkout. See
[deployment and recovery](docs/DEPLOYMENT.md) and
[conditional-tool requirements](docs/CONDITIONAL_TOOLS.md).

## Usage

Use the interactive review menu or inspect the command options:

```console
satellite-reviews --help
satellite-discovery --help
```

`satellite-reviews` opens the numbered review interface. `satellite-discovery`
handles the supported metadata and bounded QC workflow; `--wizard` starts its
interactive prompts. On Windows, `Start.cmd` or `Run-reviews.cmd` opens the
review menu; on Linux, use `Run-reviews.sh`. Existing data are not modified by
these examples. For detailed inputs, see the
[user test guide](docs/USER_TEST_GUIDE.md), [file contracts](docs/REVIEW_INFRASTRUCTURE.md),
and [registered assembly guide](docs/ASSEMBLY.md).

## Testing and CI

Run the default suite from the repository root:

```console
python -m unittest discover -s tests -q
```

The configured GitHub Actions workflow runs Python 3.11 and 3.12 on Ubuntu
and Windows, plus an Ubuntu optional-tools job for the configured artificial
runtime checks. Test fixtures and artificial-tool runs verify software
contracts; they are not biological benchmark results. The optional-tools job
is distinct from the dependency-free matrix.

## Limitations

- **Reference-scope dependence:** M6 screens only against the declared FASTA
  and configured minimap2 behavior; an unrepresented sequence may remain
  residual.
- **No-hit is not novelty:** supplied BLAST or mapping results do not establish
  absence from all known references.
- **Read-back is not independent validation:** M6 uses eligible reads
  associated with assembly for a separate alignment step; it is not an
  independent sample, held-out set, or orthogonal assay.
- **Short reads and small sequences:** the default 50 bp assembly-eligibility
  threshold preserves shorter residual reads but excludes them from assembly.
  Assembler-specific limits may further affect short-contig recovery.
  Biological recovery performance for very small satellite/subviral
  sequences has not been benchmarked.
- **DVG caller limits:** ViReMa reports caller-specific junction evidence;
  its zero-event state is scoped to a completed run and its settings.
- **No demonstrated helper dependence or validated satellite classification.**
- **No established sensitivity, specificity, or false-positive rate for novel
  satellite discovery.**
- M6 defaults (including 50 bp, 5% ambiguity, 1.2-bit entropy, Phred 20,
  MAPQ 20, 80% aligned fraction, 95% identity, two fragments, 80% breadth,
  and 2x depth) are configurable project settings, not biologically
  calibrated thresholds.

## References

These references provide biological or methodological context only. They do
not validate the pipeline, its thresholds, or any candidate classification.

### Satellite, subviral, and circular-RNA context

- Hu C-C, Hsu Y-H, Lin N-S. (2009). [Satellite RNAs and Satellite Viruses of
  Plants](https://doi.org/10.3390/v1031325). *Viruses*, 1(3), 1325–1350.
- Páez-Espino D, et al. (2019). [Diversity, evolution, and classification of
  virophages uncovered through global metagenomics](https://doi.org/10.1186/s40168-019-0768-5).
  *Microbiome*, 7.
- Bellas C, Sommaruga R. (2021). [Polinton-like viruses are abundant in
  aquatic ecosystems](https://doi.org/10.1186/s40168-020-00956-0).
  *Microbiome*, 9.
- Bergner LM, et al. (2021). [Diversification of mammalian deltaviruses by
  host shifting](https://doi.org/10.1073/pnas.2019907118). *PNAS*, 118.
- Netter HJ, et al. (2021). [Hepatitis Delta Virus (HDV) and Delta-Like
  Agents: Insights Into Their Origin](https://doi.org/10.3389/fmicb.2021.652962).
  *Frontiers in Microbiology*, 12.
- Wu Q, et al. (2012). [Homology-independent discovery of replicating
  pathogenic circular RNAs by deep sequencing and a new computational
  algorithm](https://doi.org/10.1073/pnas.1117815109). *PNAS*, 109(10),
  3938–3943.
- Yutin N, et al. (2015). [A novel group of diverse Polinton-like viruses
  discovered by metagenome analysis](https://doi.org/10.1186/s12915-015-0207-4).
  *BMC Biology*, 13.
- Mougari S, et al. (2019). [Virophages of Giant Viruses: An Update at
  Eleven](https://doi.org/10.3390/v11080733). *Viruses*, 11(8), 733.
- Fischer MG. (2021). [The Virophage Family
  Lavidaviridae](https://doi.org/10.21775/cimb.040.001).
  *Current Issues in Molecular Biology*, 40, 1–24.
- Weinberg CE, Weinberg Z, Hammann C. (2019). [Novel ribozymes: discovery,
  catalytic mechanisms, and the quest to understand biological
  function](https://doi.org/10.1093/nar/gkz737). *Nucleic Acids Research*,
  47(18), 9480–9494.

### Software and data resources

- Altschul SF, et al. (1990). [Basic local alignment search
  tool](https://doi.org/10.1016/S0022-2836(05)80360-2). *Journal of Molecular
  Biology*, 215(3), 403–410.
- Bankevich A, et al. (2012). [SPAdes: A new genome assembly algorithm and
  its applications to single-cell
  sequencing](https://doi.org/10.1089/cmb.2012.0021). *Journal of
  Computational Biology*, 19(5), 455–477.
- Li H. (2018). [Minimap2: pairwise alignment for nucleotide
  sequences](https://doi.org/10.1093/bioinformatics/bty191).
  *Bioinformatics*, 34(18), 3094–3100.
- Routh A, Johnson JE. (2014). [Discovery of functional genomic motifs in
  viruses with ViReMa—a virus recombination mapper—for analysis of
  next-generation sequencing
  data](https://doi.org/10.1093/nar/gkt916). *Nucleic Acids Research*, 42(2),
  e11.
- Sotcheff S, et al. (2023). [ViReMa: a virus recombination mapper of
  next-generation sequencing data characterizes diverse recombinant viral
  nucleic acids](https://doi.org/10.1093/gigascience/giad009). *GigaScience*,
  12, giad009.
- Leinonen R, Sugawara H, Shumway M. (2011). [The Sequence Read
  Archive](https://doi.org/10.1093/nar/gkq1019). *Nucleic Acids Research*,
  39(Database issue), D19–D21.
