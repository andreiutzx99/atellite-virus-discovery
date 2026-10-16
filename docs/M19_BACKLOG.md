# M19 backlog

M19 work is not part of the M18 implementation:

1. Expand the synthetic benchmark matrix with controlled sequencing error,
   coverage, divergence, and difficult-repeat factors, then quantify false
   residual and assembly calls.
2. Add bounded paired-end and additional assembler-version integrations, with
   explicit resource limits and honest optional-tool skips.
3. Add a synthetic-only, explicitly declared reference snapshot for exercising
   M8 homology handoffs without biological curation or classification claims.
4. Evaluate cache/recovery behavior across interrupted M6 and downstream runs
   while preserving the existing M4 provenance and identity contracts.
