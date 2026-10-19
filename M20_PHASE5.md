# M20 Phase 5: synthetic release-readiness audit

Phase 5 audits a completed Phase 4 output without changing frozen Phase 1–3
inputs. It writes JSON, Markdown, and HTML reports:

```sh
python -m satellite_discovery.m20_phase5 \
  --phase2b-output PATH_TO_PHASE2B \
  --phase3-output PATH_TO_PHASE3 \
  --phase4-output PATH_TO_PHASE4 \
  --previous-phase4-output PATH_TO_PRE_FIX_PHASE4 \
  --validation-results PATH_TO_VALIDATION_JSON \
  --ci-results PATH_TO_CI_JSON \
  --output PATH_TO_PHASE5_REPORT
```

The previous Phase 4 directory is optional; when supplied, it lets the audit classify the five
historical M12 `INVALID` rows. Those rows came from `read_support_evidence`
artifacts whose producer status was `NOT_EVALUATED`, with 40 declared support
inputs and zero query records because reconstruction had failed upstream. The
old M12 path incorrectly required completed-query reconciliation and emitted
`M6 support queries do not reconcile to declared inputs`. This is a validator
defect, not malformed provenance or a negative observation. M12 now reports
the artifact as `VERIFIED` for identity, `NOT_STARTED` execution, `UNKNOWN`
accounting, and `NO_OBSERVATION`; completed no-support results still require
exact non-empty query reconciliation.

The replay audit compares the Phase 4 M4/M6 run to frozen Phase 2B by exact
artifact bytes and hashes. It permits no normalization of alignment records or
evidence values. The observed changes are output-root strings in minimap2
`@PG CL` headers and M6 JSON path/digest references derived from those paths;
SAM alignment records match byte-for-byte after removing only the `@PG` line.
Any other leaf or record difference is reported as unresolved.

The capability matrix is rebuilt from the live registry and frozen M12/M15
allowlists. M15 provenance state is reported separately from payload validity.
M13 and M14 remain absent, M15 completeness remains partial, and the decision
explicitly separates software integration validation from biological
discovery, which is not validated.

Resource limits are reported from the frozen Phase 2B benchmark manifest, not
inferred from a local run. Cache/reuse, adversarial-test, and CI observations
are included only when supplied by the caller as validation data; they are not
assumed from a successful Phase 4 run.
