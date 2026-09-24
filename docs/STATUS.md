# Release status

PR #1 and PR #2 are merged. The final-audit update promotes the tested QC audit and revised metadata gates, adds compressed-SAM input, BLAST-table import and optional dependency checks, and improves observation-summary scaling.

The authoritative component-by-component status is [PERMITTED_ROADMAP.md](PERMITTED_ROADMAP.md). Historical architecture documents describe an original ambition, not a validated implementation. Existing QC runs and local prototypes remain preserved. The source release does not include the historical mapping, assembly or BLAST execution adapters.

Scientific validation remains distinct from passing software tests. No end-to-end known-positive satellite benchmark, discovery sensitivity, false-positive rate, DVG probability or helper-dependency result is claimed.

The conditional-tools follow-up is described in [PROGRESS_REPORT.md](PROGRESS_REPORT.md), with every former partial/dependency entry evaluated in [PARTIAL_FEATURE_FOLLOWUP.md](PARTIAL_FEATURE_FOLLOWUP.md). It adds executable supplied-reference BLAST, optional BAM/CRAM decoding, reference snapshots, context/quantitative reporting and a resumable artifact workflow. Existing category-4 boundaries remain unchanged.

## Supplied-artifact validation follow-up

See [ARTIFACT_VALIDATION_REPORT.md](ARTIFACT_VALIDATION_REPORT.md) for implementation, test evidence and explicit remaining limitations. This adds bounded fallback retries/history, file-level reference metadata, digest/control evaluation (menu23 and workflow stage), and a paired artificial Tadpole diagnostic. It does not deliver a biological discovery chain.

## Process reliability follow-up

See [PROCESS_RELIABILITY_REPORT.md](PROCESS_RELIABILITY_REPORT.md) for the subprocess tree cleanup, budget scanning, lock-owner diagnostics, validation and remaining scope. This is a partial infrastructure delivery; no ViReMa/DVG integration is included.
