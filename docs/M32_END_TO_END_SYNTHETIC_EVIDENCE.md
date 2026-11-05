# M32 — End-to-end synthetic evidence integration

Synthetic-only software integration; no biological discovery claims.

## Pre-registered case outcomes

| Case | Experiment | Reference panel | Expected triage |
|---|---|---|---|
| development-m29-positive_control | known_reference_positive | PRESENT | REVIEW_PRIORITY |
| development-m29-repeat_challenge | reference_absent_adversarial | ABSENT | INSUFFICIENT_EVIDENCE |
| tuning-m29-synthetic_background | known_reference_positive | PRESENT | REVIEW_PRIORITY |
| held_out-m29-positive_control | known_reference_positive | PRESENT | REVIEW_PRIORITY |
| held_out-m29-sequencing_errors | reference_independent_challenge | ABSENT | INSUFFICIENT_EVIDENCE |
| held_out-m29-target_absent_negative | target_absent_no_contig | NOT_APPLICABLE | INSUFFICIENT_EVIDENCE |
| held_out-m32-target_absent_background | target_absent_supported_background | NOT_APPLICABLE | INSUFFICIENT_EVIDENCE |

Known-reference cases measure synthetic retrieval/integration, not independent discovery. The reference-independent challenge is checked against the frozen panel without consulting held-out truth during screening.

## Reconstruction and M6-to-M8 handoff

| Case | Split | Assembly | Contigs | Handoff |
|---|---|---|---:|---|
| development-m29-positive_control | development | READ_SUPPORTED_ASSEMBLY | 1 | VALIDATED |
| development-m29-repeat_challenge | development | NO_SUPPORTED_ASSEMBLY | 1 | VALIDATED |
| tuning-m29-synthetic_background | tuning | READ_SUPPORTED_ASSEMBLY | 1 | VALIDATED |
| held_out-m29-positive_control | held_out | READ_SUPPORTED_ASSEMBLY | 1 | VALIDATED |
| held_out-m29-sequencing_errors | held_out | READ_SUPPORTED_ASSEMBLY | 1 | VALIDATED |
| held_out-m29-target_absent_negative | held_out | NO_SUPPORTED_ASSEMBLY | 0 | NO_CONTIGS |
| held_out-m32-target_absent_background | held_out | READ_SUPPORTED_ASSEMBLY | 1 | VALIDATED |

## M8 and triage

Triage is panel-relative synthetic evidence only; it is not biological acceptance.

| Case | Candidate | Query SHA-256 | M6 support | M8 | Panel result | Triage |
|---|---|---|---|---|---|---|
| development-m29-positive_control | NODE_1_length_900_cov_38.343195 | bfab27d81bd92161f54ffacf159194ad7a6de5675652a6902a8d7ba3c1d7fcac | READ_SUPPORTED_ASSEMBLY | COMPLETE | MATCH_REPORTED SYN001.1,SYN002.1,SYN004.1 | REVIEW_PRIORITY |
| development-m29-repeat_challenge | NODE_1_length_65_cov_3240.000000 | e73cffc6653973f42cf33f183973bd4b967b6fd8e1fef17fa519a187d30cf5a0 | UNSUPPORTED_ASSEMBLY | COMPLETE | NO_REPORTED_MATCH  | INSUFFICIENT_EVIDENCE |
| tuning-m29-synthetic_background | NODE_1_length_900_cov_38.343195 | 8cb5b5000f6db0889c52fca63f198f77b2babb9330b71f055f985f73537b44f7 | READ_SUPPORTED_ASSEMBLY | COMPLETE | MATCH_REPORTED SYN001.1,SYN002.1 | REVIEW_PRIORITY |
| held_out-m29-positive_control | NODE_1_length_900_cov_38.343195 | 5f0626f0f6ebf4d9acbeb9b2d4179a53f9d031c51519c89ff54fa41efdf0d90b | READ_SUPPORTED_ASSEMBLY | COMPLETE | MATCH_REPORTED SYN003.1,SYN006.1 | REVIEW_PRIORITY |
| held_out-m29-sequencing_errors | NODE_1_length_899_cov_7.450237 | 772608d50730f6f670e2c2f34f5513203592685a89395ff8e1000f6bc8d052d2 | READ_SUPPORTED_ASSEMBLY | COMPLETE | MATCH_REPORTED SYN001.1,SYN002.1,SYN007.1 | INSUFFICIENT_EVIDENCE |
| held_out-m29-target_absent_negative | — | — | — | NOT_RUN | — | INSUFFICIENT_EVIDENCE |
| held_out-m32-target_absent_background | NODE_1_length_900_cov_38.343195 | f1110e3df74d3ae9e6ce3e06c5ff19147fea6171c5a579abd161b447d44e1ef2 | READ_SUPPORTED_ASSEMBLY | COMPLETE | NO_REPORTED_MATCH  | INSUFFICIENT_EVIDENCE |

Target-absent background control: 1 M6-supported contig(s); M8 complete=True. This is a synthetic technical control and is not biological acceptance.

## Limits

Biological sensitivity, specificity, and false-discovery rate are NOT_EVALUATED. M6 support is technical read-back evidence, not independent biological validation.

Retrospective truth comparisons are reported only after every available M8 search and triage result.

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
