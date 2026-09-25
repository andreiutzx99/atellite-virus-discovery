# Registered assembly stage

The artifact workflow has a generic `assembly` stage backed by a trusted registry of two adapters: `spades` and `tadpole` (BBTools). Workflow data selects an identifier and supplies input artifact paths. It cannot provide commands, executable paths, modules or arbitrary tool arguments.

## Workflow contract

`read1` is required and `read2` is optional. `layout` must be declared as `single-end` or `paired-end`, and must agree with the files supplied. Pairing is based on those declared inputs, not filename inference. Accepted names end in `.fastq`, `.fq`, `.fastq.gz` or `.fq.gz`. Compressed files are passed directly to the selected assembler.

```json
{
  "schema": "artifact-workflow-v1",
  "stages": [
    {
      "id": "assemble",
      "kind": "assembly",
      "inputs": {
        "read1": "reads_R1.fastq.gz",
        "read2": "reads_R2.fastq.gz"
      },
      "config": {
        "assembler": "spades",
        "layout": "paired-end",
        "threads": 2,
        "memory_mb": 2048
      }
    },
    {
      "id": "catalogue",
      "kind": "inventory",
      "inputs": {
        "fasta": {"stage": "assemble", "artifact": "contigs.fasta"}
      }
    }
  ]
}
```

Supported configuration keys are `assembler`, `layout`, `threads` (1–8) and `memory_mb` (256–16384). Defaults are two threads and 2048 MiB for SPAdes or 512 MiB for Tadpole. SPAdes memory must be a whole number of GiB. The adapters leave k-mer and other assembler-specific biological settings at each tool's documented defaults; they do not add filtering or interpretation options.

## Input validation and resource limits

Before launch, the stage checks each declared input is a readable, non-empty regular file in a supported FASTQ form. It streams the full input to validate four-line records, identifiers, nucleotide symbols, quality encoding, and paired record counts/orientation. Inputs are SHA256-hashed and checked again after execution to reject files changed during assembly.

Execution uses the existing argv-only external-tool adapter and bounded process runner. Each stage has a 180-second timeout and a 400 MB output budget; both tools receive the declared thread count. SPAdes receives its configured memory in GiB. Tadpole's `memory_mb` controls Java heap only, not total process memory. These are cooperative/tool-level bounds, not OS-enforced CPU, memory, or filesystem quotas.

## Assemblers and dependencies

- **SPAdes**: requires `spades.py` or `spades` on `PATH`, with a successful version check identifying SPAdes. Supports single reads (`-s`) and explicitly declared pairs (`-1/-2`).
- **Tadpole**: requires Java plus the repository's pinned BBTools 40.01 runtime. The adapter verifies the archive checksum and installed runtime files before execution; missing or mismatched runtime is reported as `dependency_missing`. Supports single reads and paired reads.

Both adapters preserve the assembler's complete raw output beneath `raw/`, along with stdout/stderr logs. Raw files are never replaced by canonicalization.

## Outputs, validation and provenance

The downstream contract is:

- `contigs.fasta`: canonical nucleotide FASTA, validated against the existing catalogue limits and ID/alphabet rules.
- `assembly_manifest.json`: assembler, adapter/tool identities, versions, executable path and checksum where available, declared layout, input names/sizes/SHA256 values, parameters, timestamps, duration, exit status, workflow state, output hashes/inventory, Git revision, warnings/errors and resource-limit qualifications.
- `raw/`: retained assembler-specific output files.
- `manifest.json`: external-tool identity, dependency report, input/configuration identity and checksummed outputs used for verified reuse.

Tadpole's raw headers use comma-separated metrics in the first token, which does not satisfy the existing FASTA catalogue ID contract. The canonical FASTA assigns a safe unique ID and records a hash mapping for altered source headers; the raw Tadpole FASTA remains unchanged under `raw/`. Contig count, lengths and checksum are computed from the validated canonical FASTA.

Reuse is accepted only when input hashes/layout, selected registered adapter, tool identity/version, adapter source/version, configuration, output inventory and output contract match. A changed input/configuration/assembler, malformed manifest, altered contig, or missing raw output rejects reuse; existing evidence is preserved.

The canonical FASTA can feed the existing descriptive sequence catalogue. That catalogue reports nucleotide composition and exact-sequence groups only. This stage does not make novelty, viral classification, helper-dependence, DVG, candidate-ranking or biological-quality claims. Artificial software fixtures verify execution and file contracts only; they do not validate biological assembly performance.

Milestone 4's artifact workflow consumes this declared `contigs.fasta` output directly through its canonical-contig contract. It can continue to the existing exact-sequence catalogue, supplied-reference comparison, declared sample/control occurrence summaries, and consolidated report. The workflow validates each handoff and records its input/output checksums; it does not rerun historical QC or interpret assembly/comparison results biologically. See [conditional tools and artifact workflow](CONDITIONAL_TOOLS.md) for the typed configuration, preflight, and resume behavior.