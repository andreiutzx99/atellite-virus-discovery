# M5 — Caller-specific DVG evidence

**Status: IMPLEMENTED.** M5 records optional ViReMa caller evidence under
explicit run scope and completion checks. It does not classify a sequence as
DVG, satellite, or non-DVG. See the [README](../README.md) and
[roadmap](ROADMAP.md).

## 1. Purpose

Run the registered ViReMa integration on supported inputs and preserve
caller-specific junction evidence and run outcomes.

## 2. Why this milestone exists

Recombination/DVG caller output can be relevant context for candidate review,
but incomplete execution or an unscoped zero count must not be mistaken for
biological absence.

## 3. Implemented functionality

The adapter validates supported input/configuration, invokes the registered
caller, parses its supported native output family, checks completion and read
accounting, and emits normalized events and scoped status/provenance.

## 4. Inputs

Inputs include supported read data, declared reference/caller configuration,
and an available ViReMa installation. The adapter does not infer a reference
or substitute caller defaults without recording them.

## 5. Outputs

Outputs include normalized caller-reported junction records, a run summary,
and explicit completed, unavailable, incomplete, or failed states. A
completed zero-event outcome is `NO_DVG_EVIDENCE_DETECTED`.

## 6. External tools and dependencies

ViReMa and its required alignment/runtime dependencies are external and are
not bundled by the base package. Availability and version identity are
recorded or checked by the trusted adapter.

## 7. Evidence produced

The tests support parsing, event normalization, run completion/accounting,
failure semantics, typed output, and prevention of a zero count being rendered
as confirmed non-DVG identity.

## 8. Provenance and reuse

The result is bound to its declared read inputs, caller settings/tool
identity, and outputs. Reuse is based on validated run identity and integrity,
not merely the presence of a prior event table.

## 9. Failure and dependency semantics

Missing tools, execution failure, malformed output, incomplete runs, and
unaccounted reads remain distinct from a completed zero-event result.
Unavailable or incomplete evidence is not rewritten as zero events.

## 10. Interpretation

`NO_DVG_EVIDENCE_DETECTED` means this configured caller reported no supported
junctions in a completed, accounted run. It is scoped to that caller, input,
and configuration.

## 11. Limitations

Caller sensitivity and specificity on this project's biological use cases
have not been established. A caller can miss events, and its output may include
events requiring review; no independent truth set is supplied by a passing
software test.

## 12. What M5 does not establish

It does not establish that a sequence is or is not a DVG, a satellite, a
helper, a contaminant, or biologically significant. It does not establish
absence of recombination when no event is reported.

## 13. Relevant tests and records

See [DVG evidence semantics](DVG_EVIDENCE.md), the
[M5 workflow audit](M5_AUDIT.md), the [test suite](../tests/), and the
[M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md).

## 14. Relevant literature

ViReMa was described by [Routh and Johnson (2014)](https://doi.org/10.1093/nar/gkt916)
and updated by [Sotcheff et al. (2023)](https://doi.org/10.1093/gigascience/giad009).
These publications describe the tool and its use; they do not validate its
sensitivity, specificity, or biological interpretation in this project.

## 15. Relationship to other milestones

M5 evidence is optional context that may be carried into M6 or reviewed with
other artifacts. M6 does not turn zero caller events into a non-DVG label.
Differential biological evidence and validation remain planned in M10 and
M16; see the [roadmap](ROADMAP.md).