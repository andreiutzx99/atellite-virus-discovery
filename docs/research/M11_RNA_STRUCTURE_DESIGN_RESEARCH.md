# M11 RNA structure and ribozyme evidence: design research

**Status: research and architecture proposal only.** M11 is planned, not an
implemented production stage. This report follows the current
[roadmap](../ROADMAP.md), where M11 owns RNA-structure and ribozyme-prediction
evidence. Earlier combined M10/M11 research is not authoritative for current
ownership.
No candidate sequence was examined for this report.

This report separates **LITERATURE/EMPIRICAL SUPPORT**,
**PROJECT DESIGN PROPOSAL**, and **UNRESOLVED DECISION**. Literature evidence
about methods does not establish project-specific predictive performance.

## 1. Baseline and scientific boundary

### LITERATURE/EMPIRICAL SUPPORT

RNA secondary-structure methods produce model-dependent structural hypotheses.
Thermodynamic folding estimates an optimal or ensemble structure under a
specified energy model and conditions; it does not directly measure native
in-cell structure. Covariance models (CMs) combine sequence and conserved
secondary-structure information and can recognize homologous structured RNAs
when sequence identity alone is weak [1–3]. R-scape tests whether observed
sequence covariation supports a conserved structure beyond phylogenetic
expectation; it requires an alignment with enough independent evolutionary
variation and cannot establish a structure from one sequence [4].

Self-cleaving ribozymes are catalytic RNAs, but a short motif or plausible fold
is not evidence that the candidate cleaves. Family context, full structural
geometry, conserved catalytic residues, and the expected cleavage site matter.
Even in-vitro cleavage does not by itself establish a native biological role
[5].

### PROJECT DESIGN PROPOSAL

M11 should report separate records for:

1. **Predicted fold/ensemble:** input region and orientation, exact sequence
   digest, software/version, model and parameter set, constraints, predicted
   structures, free-energy values, ensemble or base-pair probability outputs,
   and limitations.
2. **Known-family/profile evidence:** model/database release, accession,
   threshold provenance, coordinates, orientation, alignment, score, and
   competing matches. A completed no-hit is limited to named models and their
   release.
3. **Ribozyme candidate evidence:** candidate family, model/motif source,
   structural-context and catalytic-residue observations, completeness of
   required context, alternative matches, and review state.
4. **Experimental result, if supplied:** separately typed assay, controls,
   measured cleavage site/products, conditions, and provenance. It must not be
   synthesized from the prediction records.

The permitted interpretation is “predicted RNA structure,” “family/model match,”
or “ribozyme candidate.” Do not emit “functional ribozyme,” “self-cleaving,”
“replication element,” or biological function from computational evidence.
RNAfold energy is not a calibrated probability. A fold or motif match does not
establish native structure, catalytic activity, satellite identity, or function.

### UNRESOLVED DECISION

Reviewers must choose whether the first M11 contract is a narrow single-sequence
folding layer, a frozen known-family search, or both; which molecule/region
types are eligible; whether full-length and bounded-window folds are both
reported; and whether comparative analyses are in scope. No family-specific
threshold, required ribozyme set, or minimum sequence length is approved here.

## 2. Candidate methods and resources

| Method/resource | Appropriate evidence | Limits and proposed use |
| --- | --- | --- |
| ViennaRNA `RNAfold` | Single-sequence MFE and partition-function/ensemble outputs; a practical optional baseline for ordinary secondary-structure hypotheses. | Must record conditions, model details and version. Standard secondary structure omits many pseudoknots and tertiary contacts. Short windows can create artificial stems; long sequences can hide local alternatives. Optional external dependency, not selected for implementation by this report. |
| Infernal `cmscan` with Rfam covariance models | Known-family sequence/structure-model matches with model alignment and family-specific threshold context. | A match is to a named model, not proof of identity or function; no-hit is not absence of an unknown family. Freeze exact Rfam release and retain model accession and threshold. |
| R-scape | Statistical assessment of covariation support in an eligible multiple-sequence alignment. | Requires credible alignment and adequate independent variation. Closely related or duplicated observations can inflate apparent support; low power is not evidence against structure. Defer unless sequence provenance and alignment eligibility are contractually defined. |
| RNAstructure or other folding package | A separately named comparative or alternative modeling branch if it demonstrates a needed evidence distinction. | Do not combine predictions as independent confirmations without dependence accounting. Additional model, platform and licensing review is required. |
| Hand-coded motifs/custom CMs | At most candidate generation for a narrow, justified family. | No generic motif detector is approved. Custom models require expert-curated alignments, family-specific held-out tests, and controlled decoys before any candidate-facing use. |

The initial family review should consider hammerhead and hairpin ribozymes and
HDV-like ribozymes only where sequence/molecule context makes that comparison
scientifically appropriate; other Rfam catalytic RNA families can be screened
as named model matches, not as presumed satellite signatures. The Rfam/CM
branch and a specialized motif-search branch are distinct proposals. A
sequence/structure hit needs complete family context and conserved catalytic
features to justify a candidate label; activity still requires a cleavage
assay. RNAstructure or another folding method should be added only if it answers
a defined question that is not already covered by the proposed ViennaRNA
baseline, and its release/license/platform support must be reviewed separately.

**Version and licensing check (26 September 2026):** the official Rfam site
reports release 15.1 (January 2026; 4,227 families) and states that its data are
available under CC0 [6]. Infernal's official site lists version 1.1.5
(7 September 2023) and a standard BSD license [7]. This corrects the older
M10/M11 report's GPLv3 statement for Infernal; the official current source was
used here. The official ViennaRNA license page permits research, educational,
and commercial use and modification subject to attribution and a redistribution
condition (no fee other than media costs); it asks commercial-product users to
contact the authors [8]. These terms do not automatically authorize bundling,
redistribution, or use of a particular release in this project. The R-scape
software license was not verified in this review and must be checked before
provisioning. Review software and model-data terms separately.

No database download, model bundle, or tool installation is part of this
research. Prefer version-pinned local resources and record source URL, release,
retrieval date, exact model/payload hashes, license, attribution, and build
identity. Linux/macOS packaging is documented for Infernal; Windows and
cross-platform behavior must be tested rather than assumed. Any chosen external
tool should be optional at the workflow boundary, with `DEPENDENCY_UNAVAILABLE`
distinct from a no-hit.

## 3. False-positive and false-negative risks

### LITERATURE/EMPIRICAL SUPPORT

- Thermodynamic folds simplify cellular context, cotranscriptional folding,
  binding partners, ionic conditions, and competing conformations.
- Standard secondary-structure algorithms do not represent all pseudoknots or
  tertiary interactions.
- Circular RNA has an arbitrary linearization cut; predicted folds can change
  with rotation or window selection. M11 must not infer circularity from a fold.
- GC-rich, repeated, or low-complexity sequence can yield stable-looking
  structures without family-specific function.
- Short motif searches have substantial chance-match and multiple-testing risk.
- Missing family models, partial candidates, and insufficient homolog diversity
  create false negatives; a no-hit is strictly model/release scoped.

### PROJECT DESIGN PROPOSAL

Keep the original candidate bytes immutable. A selected region, orientation, or
rotated circular-input view must be explicitly derived, hashed, and linked to
the source. Preserve all competing structures and hits within deterministic,
visible output accounting. Use length-, composition-, and complexity-matched
synthetic decoys and known non-catalytic structured RNAs when measuring candidate
generation behavior. Do not turn tool defaults into biological cutoffs.

Suggested distinct states include input validity, method applicability,
execution/completeness, evidence result, and experimental status. For example,
`PREDICTED_STRUCTURE`, `MODEL_MATCH_REPORTED`,
`NO_MATCH_WITHIN_TESTED_MODELS`, `NOT_APPLICABLE`, `NOT_EVALUATED`,
`DEPENDENCY_UNAVAILABLE`, `FAILED`, `INCOMPLETE`, `TRUNCATED`, and
`EXPERIMENTAL_RESULT_SUPPLIED` must not be collapsed. Exact enum names remain
for contract review.

## 4. Validation boundary and cache scope

**Software validation:** offline fixtures for canonical/ambiguous alphabets,
orientation and boundary mapping, exact parameter recording, reproducible
folding output, multiple windows, rotated input sensitivity where applicable,
model hit/no-hit accounting, malformed model/output, missing dependency,
truncation, and deterministic reuse. Artificial motifs test parser and runner
behavior only.

**Biological validation:** independent curated families, non-catalytic
structured-RNA comparators, matched decoys, and family/clade holdouts are needed
to assess candidate-generation or family-search behavior. No performance is
established by this report.

**Experimental confirmation:** a catalytic claim requires an assay that
measures predicted-site cleavage with positive and negative controls, expected
product/site checks, catalytic-residue disruption and rescue where appropriate,
and later in-vivo context if the claim concerns biological role. No experiment
is performed here.

A future M11 cache identity should bind the exact candidate and region bytes,
orientation/boundary and molecule-type declarations, method and parameter
profile, optional context actually consumed, executable/library identity,
database/model release and hashes, parser/normalizer/schema semantics, and
output integrity. M11-only changes should invalidate M11 only; do not add its
identity to M6–M10. Shared validator/cache-semantic changes follow the existing
[stage identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).

## 5. Sources checked

1. Lorenz R, et al. “ViennaRNA Package 2.0.” *Algorithms for Molecular Biology*
   6, 26 (2011). [doi:10.1186/1748-7188-6-26](https://doi.org/10.1186/1748-7188-6-26);
   [RNAfold manual](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/man/RNAfold.html).
2. Nawrocki EP, Eddy SR. “Infernal 1.1: 100-fold faster RNA homology searches.”
   *Bioinformatics* 29 (2013): 2933–2935.
   [doi:10.1093/bioinformatics/btt509](https://doi.org/10.1093/bioinformatics/btt509);
   [official Infernal site and license](https://infernal.janelia.org/).
3. Kalvari I, et al. “Rfam 15: RNA families database in 2025.” *Nucleic Acids
   Research* (2025). [doi:10.1093/nar/gkae1023](https://doi.org/10.1093/nar/gkae1023);
   [live release and data terms](https://rfam.org/).
4. Rivas E, Clements J, Eddy SR. “A statistical test for conserved RNA structure
   shows lack of evidence for structure in lncRNAs.” *Nature Methods* 14 (2017):
   45–48. [doi:10.1038/nmeth.4066](https://doi.org/10.1038/nmeth.4066).
5. Weinberg CE, Weinberg Z, Hammann C. “Novel ribozymes: discovery, catalytic
   mechanisms, and the quest to understand biological function.” *Nucleic Acids
   Research* 47 (2019): 9480–9494.
   [doi:10.1093/nar/gkz737](https://doi.org/10.1093/nar/gkz737).
6. [Rfam release 15.1 and CC0 statement](https://rfam.org/), checked 26 September
   2026.
7. [Infernal official release/license page](https://infernal.janelia.org/),
   checked 26 September 2026.
8. [ViennaRNA official license](https://www.tbi.univie.ac.at/RNA/ViennaRNA/doc/html/license.html),
   checked 26 September 2026.

M11 remains planned; predictions are not experimentally established activity or
function.
