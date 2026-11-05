# M30 synthetic candidate specificity and false-positive validation

**Conclusion: NOT_VALIDATED.** The existing repository has partial sequence-evidence capability, but no demonstrated end-to-end candidate-specificity pathway.

## Stage capability audit

| Stage | Capability | M30 status |
|---|---|---|
| M7 | Optional independent recurrence/context evidence; not a classifier | NOT_EVALUATED |
| M8 | Frozen BLASTN nucleotide similarity evidence; does not accept/reject candidates | DEPENDENCY_UNAVAILABLE |
| M9–M15 | ORF/repeat/RNA prediction, review, dossiers and provenance; no final acceptance classifier | NO_END_TO_END_ACCEPTANCE_STAGE |

Detailed stage roles:

- M9: AVAILABLE_EVIDENCE_STAGE — ORF translation/protein-search evidence; not identity or acceptance.
- M10: AVAILABLE_EVIDENCE_STAGE — Repeat and sequence-pattern evidence; not acceptance.
- M11: AVAILABLE_PREDICTION_STAGE — RNA fold predictions; prediction is not demonstrated function.
- M12: AVAILABLE_REVIEW_STAGE — Artifact review and evidence validation; not an automated final classifier.
- M13: AVAILABLE_DOSSIER_STAGE — Evidence dossier; does not establish candidate identity.
- M14: AVAILABLE_DESCRIPTIVE_STAGE — Descriptive observations; not classification.
- M15: AVAILABLE_PROVENANCE_STAGE — Provenance and workflow-state reporting; not biological acceptance.

M29 historical context: {"case_count": 17, "confirmatory_held_out_supported_exact_recoveries": 1, "exact_recoveries": 6, "experimental_negative_control_accepted_false_positive_candidates": "NOT_EVALUATED", "experimental_negative_control_raw_contigs": 1, "experimental_negative_control_read_supported_contigs": 1, "held_out_supported_exact_recoveries": 3, "m29_success_criterion_met": false, "negative_control_accepted_false_positive_candidates": "NOT_EVALUATED", "negative_control_raw_contigs": 0, "negative_control_read_supported_contigs": 0, "positive_cases": 13, "production_promotion_decision": "NO_PROMOTION", "supported_exact_recoveries": 6, "target_absent_controls": 4}

M8 limitation: M8 requires verified 2.17.0+ on Linux x86_64; detected blastn='2.16.0+', makeblastdb='2.16.0+'.

M8 status is similarity evidence only. A match is not a satellite-virus classification; a no-match is limited to the searched synthetic panel. No external biological reference was queried.

## Blind synthetic fixture matrix

Fixtures are split across development, tuning and held-out partitions. Candidate sequences and opaque IDs are in `M30_SYNTHETIC_CANDIDATE_INPUTS.json`; scenario labels and target truth are separate in `M30_SYNTHETIC_CANDIDATE_TRUTH.json`. Candidate inputs contain no scenario or target label. Fixture support statuses are declarations for test design, not measured M6 evidence.

| Candidate | Split | Sequence SHA-256 | Assembly | Read support | M8 | Final acceptance |
|---|---|---|---|---|---|---|
| m30q001 | development | 3e83dd26658686d4ca88e5cdb494705fa0bfa0e593be8858efaf2cd2e41b65e2 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q002 | development | edf69845c95601782a7caab53a313513f175a37ddfd96039543c918903cf0358 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q003 | development | 1748dfb880fc460fc31049caba0b2856aaf0715584ab7cccba24f1e9055b61d4 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q004 | development | 043abc44db8f69527aa6e7a9dc243d4f013ebeb6e4d93e0ba59e931f24672141 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q005 | tuning | 9594a8789367548280efe6df58ddc3a9e999a8c73cb50c2fd804bf3f076c2f69 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q006 | tuning | 3e83dd26658686d4ca88e5cdb494705fa0bfa0e593be8858efaf2cd2e41b65e2 | SYNTHETIC_FIXTURE_ONLY | UNSUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q007 | held_out | 3e83dd26658686d4ca88e5cdb494705fa0bfa0e593be8858efaf2cd2e41b65e2 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q008 | held_out | ec239b174e0049252a41c238d4109a0015ed57d71ca4296c2468815aac279d0d | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q009 | held_out | a915aaad1c291b092545e2f3b8e062f6236d4616cd7fa1575ffd5dc527a8b380 | SYNTHETIC_FIXTURE_ONLY | READ_SUPPORTED_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q010 | held_out | NONE | SYNTHETIC_FIXTURE_ONLY | NOT_EVALUATED | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |
| m30q011 | held_out | 3e83dd26658686d4ca88e5cdb494705fa0bfa0e593be8858efaf2cd2e41b65e2 | SYNTHETIC_FIXTURE_ONLY | AMBIGUOUS_ASSEMBLY | DEPENDENCY_UNAVAILABLE | NOT_EVALUATED |

Cases cover exact target-like sequences, unrelated background, target-absent input, near-target decoys, repeats/low complexity, truncated target-like sequence, unsupported exact sequence, and ambiguous evidence.

## Specificity and sensitivity

Metrics status: **NOT_EVALUATED**. No candidate completed an end-to-end discovery-specific acceptance pathway.

No candidates were treated as true negatives merely because screening was unavailable. Sensitivity, specificity, precision, false-discovery proportion, and confidence intervals are NOT_EVALUATED.

## Reproduction

Run `python -m satellite_discovery.m30_candidate_specificity --output /tmp/m30-specificity`. The command writes blinded inputs, separate truth labels, and JSON/Markdown reports. It queries no external reference service and executes no biological data.

## Limitations and governance

M8 defines and implements similarity-evidence searches, but its pinned runtime is unavailable here and its results are not a biological classifier. M7 is optional recurrence context. M9–M15 provide analyses and review/provenance artifacts, not a frozen final acceptance classifier. End-to-end synthetic candidate specificity is therefore not demonstrated.

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
