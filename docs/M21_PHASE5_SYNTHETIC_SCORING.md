# M21 Phase 5 — scoring definitions

Scoring policy version: `m21-synthetic-scoring-v1`.

- Candidate calls are deduplicated within each sample and matched only by exact opaque `candidate_id`; a truth candidate can match only once in its biological replicate group.
- Positive sample groups are true positive when any curated truth candidate is detected; otherwise false negative.
- Negative sample groups with one or more candidate calls count as one sample-level false positive, irrespective of candidate count.
- Candidate precision/recall use only independently qualified positive truth items and candidate calls. False candidate burden counts candidate IDs after replicate-group deduplication.
- False-candidate-per-million uses read counts from evaluable negative groups, labelled explicitly as reads or read pairs. A zero or absent denominator is `NOT_ESTIMABLE`, never zero.
- Specificity and sensitivity require eligible independent negative and positive groups respectively. Undefined metrics carry a reason and null numerator/denominator/value.
- The report includes eligible groups, exclusions, confusion counts, study count, provenance digests, and explicit limitations. No confidence intervals are computed.

The machine report is marked `SYNTHETIC SOFTWARE VALIDATION — NOT BIOLOGICAL PERFORMANCE EVIDENCE`. Passing the software validator never grants biological execution approval.
