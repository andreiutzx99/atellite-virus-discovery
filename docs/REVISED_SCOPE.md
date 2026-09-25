# Revised metadata scope

> This document describes the acquisition search gates, not the full current
> capability set. See the [README](../README.md) and [M1–M16 roadmap](ROADMAP.md)
> for current M1–M6 status and limits.

The new acquisition workflow recognizes exactly these user-requested model keys: `oc43-vr1558`, `229e-vr740`, `hpiv3-c243`, `hrv1a-2060`, `pr8-vr1469`, `rotavirus-wa`, `rsv-long`, and `adenovirus2-vr846`. Requested catalogue identifiers and source links are recorded in `satellite_discovery/model_scope.json`.

These are metadata constraints, not certification of a sample, organism, stock or downstream biological method. Broad legacy labels cannot start a new acquisition run. Additional query text is combined with the model query, rather than replacing it.

A matching sample catalogue identifier or supported structured strain plus organism evidence is required. Study-title mentions alone cannot establish sample identity. OC43, 229E and adenovirus 2 require catalogue evidence. Missing, mixed, modified, reassortant, conflicting or excluded-target metadata is held or rejected. This conservative approach can hold legitimate studies and cannot detect unreported organisms.

Scope decisions and the policy digest enter acquisition provenance. RNA/DNA library review describes the sequenced material independently of the helper's genome type. Existing QC artifacts and historical installations are preserved; the separate audit can inspect them without imposing a new metadata search.

These gates do not enable the original biological discovery workflow. The
earlier local mapping/reference prototypes mentioned in this scope note are
distinct from the later registered M6 declared-reference screen and residual
stage; see the [M6 description](M6_RESIDUAL_ASSEMBLY_SUPPORT.md). The
[historical feature audit](PERMITTED_ROADMAP.md) records the earlier source
baseline.
