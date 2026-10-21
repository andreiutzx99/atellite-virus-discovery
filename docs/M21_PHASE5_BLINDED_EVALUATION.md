# M21 Phase 5 — blinded evaluation handoff

The analysis input is intentionally limited to opaque sample IDs, opaque candidate IDs, read counts, and read units. It has no fields for truth labels, control classes, expected sequences, exclusion mappings, or eligibility labels. Its canonical digest is bound into a separate read-only truth bundle.

The scoring function requires two distinct, synthetically named reviewer IDs and an authorization record bound to the exact truth-bundle digest. It rejects unapproved or changed bundles and analysis/truth digest mismatches. This software check is not a cryptographic signature or a real access-control system; actual unblinding still requires an independently operated custody process and protected storage.

Unblinding is permitted only at scoring after approval. The scoring function returns a machine-readable audit summary and does not write truth into operator directories. No real credentials, keys, or truth records are provided.
