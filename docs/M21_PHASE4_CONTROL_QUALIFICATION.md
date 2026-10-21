# M21 Phase 4 — synthetic control qualification rules

Control records are structured decisions, not biological labels. The schema and `validate_control_qualification` enforce these rules:

- Separate positive evidence from screen-negative evidence. A failed target-specific screen is not proof of absence.
- A negative with unknown or limited sensitivity is `UNEVALUABLE` and excluded from sample-level specificity denominators.
- Mark the helper state explicitly; helper-positive and helper-negative comparators are distinct strata. Co-detection alone does not demonstrate dependence.
- Keep within-study validation separate from independent-study validation.
- Do not call near-complete sequences terminally verified.
- Review candidate-level false positives separately from sample-level false positives.
- Unevaluable and pending controls are excluded from performance denominators. Report exclusions and denominator definitions before scoring.

Px31 remains `NEGATIVE_CONTROL_SUITABILITY_PENDING`. Its published target-specific screen-negative has no reported limit of detection; this milestone does not upgrade it or claim absence.

Synthetic control fixtures use opaque `CTL-` identifiers only. This module does not calculate biological sensitivity, specificity, or discovery performance.
