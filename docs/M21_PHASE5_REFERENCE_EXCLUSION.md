# M21 Phase 5 — synthetic reference exclusion

`satellite_discovery.m21_reference_exclusion` checks a local, approved FASTA panel against a frozen exclusion policy. No downloads, database searches, or biological reference material are used.

The policy binds its version and ID, excluded sequence digests, and explicit query-coverage/identity thresholds. Checks compare both orientations with local alignment, so exact matches, reverse complements, substitutions, insertions, deletions, partial matches, and excluded strings embedded in longer references can be rejected. Similarity is an exclusion signal only; it does not establish biological relatedness.

The validator verifies the expected policy digest and panel-byte digest before checking references, rechecks panel bytes afterward, and returns a per-reference decision and matching evidence. Policy or content mismatch is `FAIL`; a missing file or exhausted sequence/alignment budget is `INCOMPLETE`. Neither state accepts the panel. Input limits are part of the approved policy.

The algorithm is bounded Smith–Waterman local alignment with match +2, mismatch −1, and gap −2. Coverage is the fraction of excluded-query bases aligned; identity is exact matches divided by aligned columns, including gaps. A reference is rejected when both configured minima are met.
