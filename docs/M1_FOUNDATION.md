# M1 — Foundation

**Status: IMPLEMENTED.** M1 supplies controlled workflow infrastructure. It
does not perform biological discovery. For current project status, see the
[README](../README.md) and [roadmap](ROADMAP.md).

## 1. Purpose

Define a trusted, testable contract for running registered workflow stages and
preserving their results.

## 2. Why this milestone exists

Later technical stages need predictable inputs, bounded execution, explicit
outcomes, and a record of which configuration and tools produced each output.

## 3. Implemented functionality

The foundation includes a fixed stage registry, typed configuration and
artifact contracts, bounded external-tool execution, explicit stage states,
workflow manifests, and checks for safe reuse of completed outputs.

## 4. Inputs

Workflows select registered stage identifiers and validated data/configuration.
They do not supply arbitrary executable code or shell commands.

## 5. Outputs

Stages produce declared artifacts and status/provenance records. Output
contracts let downstream stages verify the type and identity of their inputs.

## 6. External tools and dependencies

M1 does not require a bioinformatics executable for its basic registry and
workflow contracts. A registered adapter may declare an external dependency;
the trusted runner checks and invokes it within configured bounds.

## 7. Evidence produced

M1 tests support claims about registration, validation, state transitions,
bounded execution, artifact contracts, provenance, and reuse behavior.

## 8. Provenance and reuse

Workflow identity binds declared inputs, configuration, tool identity, and
output integrity. Reuse is allowed only when the recorded identity and
validated outputs still match.

## 9. Failure and dependency semantics

Unknown stages, invalid configuration, missing dependencies, failed execution,
and invalid outputs remain explicit failure/unavailable states; they are not
converted into successful empty results.

## 10. Interpretation

An M1 success means the registered software contract completed. It says
nothing about whether the assumptions encoded in a later biological stage are
true.

## 11. Limitations

The runner is not a universal operating-system sandbox or a hard resource
quota. A stage can be technically reliable while its scientific method is
inappropriate or unvalidated.

## 12. What M1 does not establish

It does not establish sequence identity, taxonomy, novelty, contamination
source, helper dependence, biological function, candidate significance, or
discovery performance.

## 13. Relevant tests and records

See the [test suite](../tests/), [external-tool adapter contract](EXTERNAL_TOOL_ADAPTERS.md),
and [historical M1 capability audit](APPLICATION_CAPABILITY_AUDIT.md).
Tests exercise software fixtures, not biological truth sets.

## 14. Relevant literature

M1 is workflow infrastructure and makes no biological claim requiring a
biological reference. Software and biological context references are listed in
the [README](../README.md#references); they do not validate M1 or downstream
defaults.

## 15. Relationship to other milestones

M1 is the foundation used by later registered workflows. M2–M6 add specific
technical capabilities. M7–M16 remain planned in the
[roadmap](ROADMAP.md).