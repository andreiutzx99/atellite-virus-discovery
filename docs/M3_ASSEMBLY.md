# M3 — Registered assembly

**Status: IMPLEMENTED.** M3 provides registered assembly for supplied,
validated reads. Successful assembly execution is not biological validation.
See the [README](../README.md) and [roadmap](ROADMAP.md).

## 1. Purpose

Run supported assemblers through trusted adapters and return outputs under a
declared artifact contract.

## 2. Why this milestone exists

Assembly is a reusable technical operation, but it should be invoked with
validated inputs, controlled arguments, explicit dependencies, and
inspectable results rather than arbitrary workflow commands.

## 3. Implemented functionality

Registered SPAdes and Tadpole adapters accept supplied single- or paired-end
FASTQ within validated configuration/resource bounds. Outputs are checked
before they are published as assembly artifacts.

## 4. Inputs

Inputs are supplied validated FASTQ, an explicit layout, a selected registered
assembler, and bounded tool settings. M3 does not acquire or select biological
samples on its own.

## 5. Outputs

The adapter records execution status, tool identity/configuration, and
validated assembly FASTA/output artifacts. Empty or malformed assembly output
is not reported as a successful reconstruction.

## 6. External tools and dependencies

SPAdes or BBTools/Tadpole must be independently installed and discoverable in
the execution environment. They are optional external tools, not bundled
Python dependencies.

## 7. Evidence produced

The tests support adapter invocation, input/layout handling, bounded
execution, output validation, provenance, and failure behavior. They are not a
biological assembly benchmark.

## 8. Provenance and reuse

The recorded identity includes declared read inputs, configuration, selected
tool identity, and output checks. Reuse is rejected if the verified identity
or artifacts differ.

## 9. Failure and dependency semantics

Missing assemblers, failed execution, time/resource limits, and invalid output
are explicit outcomes. They are not converted into an empty assembly result
that could be mistaken for biological absence.

## 10. Interpretation

An assembly artifact is a computational reconstruction from its input reads.
Its existence does not establish that the sequence is accurate, complete,
viral, satellite, or biologically present as an independent molecule.

## 11. Limitations

Assembler behavior can depend on version, parameters, read quality, depth, and
sequence properties. No biological sensitivity, specificity, or recovery
performance is claimed for the supported adapters.

## 12. What M3 does not establish

It does not establish taxonomy, novelty, helper dependence, function,
contamination status, candidate significance, or independent validation.

## 13. Relevant tests and records

See the [registered assembly guide](ASSEMBLY.md), [test suite](../tests/),
and [M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md).

## 14. Relevant literature

The SPAdes method is described by
[Bankevich et al. (2012)](https://doi.org/10.1089/cmb.2012.0021). The
reference describes an assembly method; it is not a validation benchmark for
this project or for any specific sample.

## 15. Relationship to other milestones

M3 is a generic registered assembly capability. M4 can pass typed artifacts
between selected stages; M6 can optionally assemble only its eligible
reference-relative residual reads. M7–M16 biological evidence layers remain
planned in the [roadmap](ROADMAP.md).