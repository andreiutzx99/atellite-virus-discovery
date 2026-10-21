# M21 Phase 5 — synthetic reference exclusion

`satellite_discovery.m21_reference_exclusion` checks a local, approved FASTA panel against a frozen exclusion policy. No downloads, database searches, or biological reference material are used.

The policy binds its version and ID, excluded sequence digests, and explicit query-coverage/identity thresholds. Checks compare both orientations with local alignment, so exact matches, reverse complements, substitutions, insertions, deletions, partial matches, and excluded strings embedded in longer references can be rejected. Similarity is an exclusion signal only; it does not establish biological relatedness.

The validator verifies the expected policy digest and panel-byte digest before checking references, rechecks panel bytes afterward, and returns a per-reference decision and matching evidence. Policy or content mismatch is `FAIL`; a missing file or exhausted sequence/alignment budget is `INCOMPLETE`. Neither state accepts the panel. Input limits are part of the approved policy.

The checker searches every excluded-query substring that can meet the coverage threshold against every reference substring. For each query substring, semiglobal dynamic programming tests whether any alignment path meets the exact identity threshold; it does not select one highest-scoring local hit and discard alternative qualifying hits. Search work across both orientations, all queries, and all references uses one approved `max_alignment_cells` budget. If that complete existence search cannot finish within the budget, the panel is `INCOMPLETE` and cannot be accepted.

Coverage is the fraction of excluded-query bases consumed by the alignment; identity is exact matches divided by aligned columns, including gaps. A reference is rejected when both configured minima are met. The panel/policy digests establish byte integrity and binding, not authenticated scientific approval or biological relatedness.
