# M21 Phase 5 — control scoring eligibility

Phase 4 control qualification remains unchanged. Phase 5 consumes a separate, digest-bound eligibility record that names opaque sample IDs, control class, evaluation state, independent review state, study ID, replicate group, and an explicit exclusion reason when not eligible.

Only `EVALUABLE`, independently reviewed records may be marked eligible. `PENDING` and `UNEVALUABLE` controls stay out of truth and performance denominators. A target-specific negative with unknown sensitivity cannot qualify itself. Helper-positive and helper-negative strata remain separate. Px31 remains `NEGATIVE_CONTROL_SUITABILITY_PENDING`.

Every eligibility record has a canonical SHA-256 digest. The scorer rejects digest changes, conflicting sample assignment, and technical replicates with inconsistent labels or candidate truth. It groups replicates by the declared replicate group instead of counting them as independent samples.
