# M20 Phase 4: synthetic M12/M15 handoffs

Phase 4 extends the frozen synthetic Phase 2B and Phase 3 outcomes with the
registered M12 artifact review and M15 evidence dossier. Run it with:

```sh
python -m satellite_discovery.m20_phase4 \
  --phase2b-output PATH_TO_PHASE2B \
  --phase3-output PATH_TO_PHASE3 \
  --output PATH_TO_PHASE4
```

The Phase 2B and Phase 3 directories are inputs and are not modified. M12 needs
direct, typed M6 handoffs from earlier stages in the same workflow, so Phase 4
runs the existing M4/M6 workflow against the frozen synthetic inputs in its
own output directory and binds M12 only to those verified M6 outputs. It
records an artifact-digest comparison against frozen Phase 2B M6 outputs; a
replay is never presented as the original run. M7–M10
are sent directly to M15 from their original Phase 2B/3 producer workflows.
M15 also receives M6 and the M12 outputs with authenticated producer workflow,
stage, manifest, path, contract-version, and digest references.

The run writes `report.json`, `report.md`, and `report.html`. The JSON report
includes per-case M12/M15 states, producer bindings and digests, upstream
Phase 3 outcomes, dossier counts, and rejected or unavailable evidence. Its
`deterministic_semantic_outcomes_sha256` covers case outcomes while excluding
run-specific workflow IDs and manifest digests; those provenance identities
remain present in the report and naturally differ between fresh executions.
Use a new empty output directory for each run; workflow-stage cache identities
within the M12 workflow invalidate changed inputs and implementation sources.

M12 reviews allowlisted M6 artifacts only. M15 validates provenance and
completeness; it does not make biological claims. External evidence remains
`NOT_SUPPLIED`. In particular, SPAdes failures, partial reconstruction,
unevaluable controls, zero M7 recurrent groups, and M8 dependency-unavailable
states are retained from Phase 3. No held-out truth is passed into an analysis
stage.

The existing M15 parser does not accept M10's JSONL candidate-accounting table
as a dossier payload. Phase 4 therefore leaves that table out of M15 and
records the rejection reason; the M10 repeat evidence and result bundle remain
eligible when their producer contract and provenance validate. No M1–M19
contracts are changed.
