# Revised metadata scope

The new acquisition workflow recognizes exactly these user-requested model keys: `oc43-vr1558`, `229e-vr740`, `hpiv3-c243`, `hrv1a-2060`, `pr8-vr1469`, `rotavirus-wa`, `rsv-long`, and `adenovirus2-vr846`. Requested catalogue identifiers and source links are recorded in `satellite_discovery/model_scope.json`.

These are metadata constraints, not certification of a sample, organism, stock or downstream biological method. Broad legacy labels cannot start a new acquisition run. Additional query text is combined with the model query, rather than replacing it.

A matching sample catalogue identifier or supported structured strain plus organism evidence is required. Study-title mentions alone cannot establish sample identity. OC43, 229E and adenovirus 2 require catalogue evidence. Missing, mixed, modified, reassortant, conflicting or excluded-target metadata is held or rejected. This conservative approach can hold legitimate studies and cannot detect unreported organisms.

Scope decisions and the policy digest enter acquisition provenance. RNA/DNA library review describes the sequenced material independently of the helper's genome type. Existing QC artifacts and historical installations are preserved; the separate audit can inspect them without imposing a new metadata search.

These gates do not enable the original biological discovery workflow. See [the feature audit](PERMITTED_ROADMAP.md) for published functionality. Earlier local mapping/reference prototypes are not distributed or connected to the released interface.
