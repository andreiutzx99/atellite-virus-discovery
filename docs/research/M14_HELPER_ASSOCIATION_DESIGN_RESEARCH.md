# M14 helper association and dependence: design research

**Status: research and architecture proposal only.** M14 is planned, not an
implemented production stage. The current [roadmap](../ROADMAP.md) assigns
helper association and separately validated dependence evidence to M14. This
report uses no private sample metadata, candidate sequences, or biological
dataset.

This report distinguishes **LITERATURE/EMPIRICAL SUPPORT**,
**PROJECT DESIGN PROPOSAL**, and **UNRESOLVED DECISION**.

## 1. What the evidence can mean

### LITERATURE/EMPIRICAL SUPPORT

The ICTV satellite overview distinguishes satellite viruses and satellite
nucleic acids and describes dependence on a helper for missing functions. It
also distinguishes satellite-like agents and other virus-dependent nucleic
acids whose dependence can involve different helper-provided functions [1].
That report is a useful terminology framework, not a rule that maps
co-occurrence or sequence similarity to biological class. Satellite/helper
systems are diverse; different satellites can use different helpers and
functions. Published satellite-helper work uses direct experimental
observations to address interaction and infection biology [2,3].

Co-detection in a sample, study, or sequencing run is observational association.
It does not establish that either agent was present in the same cell, that the
candidate uses that helper, or that the candidate depends on it. Sequencing
depth, host/tissue, environment, study design, batch, geography, co-infection,
and shared references can confound apparent association. Repeated samples or
processing runs from the same source are not independent replicates; the
project's M7 records declared metadata but does not verify its truth.

### PROJECT DESIGN PROPOSAL

Keep at least these M14 evidence dimensions separate:

1. **Co-occurrence:** candidate/helper detections at named units (sample,
   biological specimen, run, or study), with denominator, detection method,
   controls, missingness, and source.
2. **Sequence association:** a named sequence/model match or homology
   relationship, preserving coordinates, reference release, and competing
   roles. This is not proof of source, interaction, or dependence.
3. **Recurrence:** repeated co-observation across independently justified
   biological units or studies. Report the independence rule and any unresolved
   sample/run/study identity.
4. **Abundance association:** candidate and helper abundance/covariation with
   assay, normalization, detection limits, and uncertainty. Read counts are
   compositional and library depth is not biological abundance by itself.
5. **Intervention evidence:** an independently supplied experiment that
   manipulates, removes, complements, or rescues the proposed helper function.
   Keep experimental methods and results separate from observational summaries.

Only direct, claim-appropriate experiments can support biological dependence.
M14 computational outputs should use language such as “co-detected in
X/Y evaluable units” or “abundance association under the declared model.”
Do not label a helper as causal or dependence as demonstrated from
co-occurrence, a correlated abundance pattern, recurrence, or sequence
similarity alone.

Keep helper identity/taxonomic annotation and its source confidence; candidate–
helper homology and alignment scope where relevant; sample- and study-level
association; temporal or intervention metadata when supplied; control
patterns; abundance measures; recurrence across justified independent units;
and explicit negative observations with their detection scope. Taxonomic
labels and sequence similarity remain provenance-bearing hypotheses, not
verified helper attribution.

## 2. Unit of analysis and sparse-data safeguards

### PROJECT DESIGN PROPOSAL

The core input should be an explicit candidate/helper/observation table with
stable observation and source IDs, study/sample/run relationships, tested
denominators, detection method and sensitivity limits, control status,
metadata provenance, and `present` / `not detected within scope` / `unknown`
states. A missing observation must never be treated as a negative. Preserve
multiple observations from one sample without counting them as independent
biological replicates.

For sparse public data:

- Start with transparent counts and denominators, stratified by study and
  relevant host, sample type, batch, and detection scope.
- Use a 2×2 table or conditional association estimate only when all four
  cells and the evaluated sampling denominator are defined. Show sparse cells
  and uncertainty; do not rely on a nominal p-value as a dependence claim.
- Consider stratified or hierarchical models only when independent units,
  covariates, missingness, and sample size support them. Account for repeated
  measures, multiple testing, study selection, uneven sequencing depth, and
  ascertainment.
- Analyze abundance only with an approved normalization and assay model;
  preserve raw counts, detection limits, and study-level effects. Do not
  interpret a relative-abundance correlation as a physical interaction.
- Include negative controls and unassociated/helper-only/candidate-only units
  where the sampling design supports them. An absent control or an untested
  sample is `UNKNOWN`, not a clean non-association.

No universal number of observations, association cutoff, abundance ratio,
odds ratio, or statistical significance rule is approved. M14 must be able to
return “insufficient matched evidence.”

## 3. Resources, licensing, and validation

M14's minimum observational summaries need verified metadata and denominators,
not a large biological database or mandatory external executable. Candidate
and helper identity/context may link to M8/M9 outputs, but labels and database
annotations remain evidence records, not verified taxonomy. M7 observations
may be linked only with their declared provenance and limitations.

Before any real dataset is used, human reviewers must approve its source terms,
sample metadata use, access/privacy constraints, candidate/helper role curation,
and release/version provenance. Any external statistical package or named
reference collection needs independent license and maintenance review. No
reference sequences or datasets are acquired by this report.

**Software validation:** synthetic observation tables for denominators,
duplicate sample/run identities, multiple studies, missing/unknown states,
imbalanced detection, sparse cells, controls, confounders, depth-normalization
branches, incomplete provenance, and deterministic output. Unit tests verify
the calculation and reporting contract, not the biological truth of association.

**Biological validation:** independent datasets with defined sample units,
controls, detection methods, and ascertainment are required before making
performance or association claims. External labels should be curated with
confidence levels and source citations.

**Experimental confirmation:** helper perturbation or omission, rescue or
complementation, appropriate controls, and a measured replication/encapsidation/
movement phenotype may be needed to support a dependence claim. The exact assay
depends on the system; M14 performs no experiments.

An M14 cache identity should include matched observation tables and their
provenance, denominators, control and study metadata actually consumed,
normalization/statistical model, candidate/helper evidence links, tool/runtime
if any, contract/schema semantics, and verified outputs. Changes to metadata
that alter grouping or denominators must invalidate M14. They must not
retroactively rewrite M7 recurrence.

## 4. UNRESOLVED DECISIONS

1. Which evidence is permitted to identify a helper candidate, and which
   records are only hypothesized context?
2. What counts as an independent biological unit, and what external verification
   of sample/run/study declarations is required?
3. Which source terms, privacy rules, controls, and metadata fields are
   approved?
4. Which statistical summaries can be computed under sparse/missing data, and
   which are withheld pending a larger matched dataset?
5. What experimental evidence standard is needed for each dependence claim?

## 5. Sources checked

1. ICTV. “Satellites and Other Virus-dependent Nucleic Acids,” Ninth Report
   (2009 taxonomy release).
   [ICTV chapter](https://ictv.global/report_9th/subviral/Satellites-introduction).
   Its taxonomy release is historical; re-check current terminology before a
   production contract.
2. Krupovic M, et al. “A classification system for virophages and satellite
   viruses.” *Archives of Virology* (2016).
   [doi:10.1007/s00705-015-2622-9](https://doi.org/10.1007/s00705-015-2622-9).
3. “Simultaneous entry as an adaptation to virulence in a novel satellite-helper
   system infecting *Streptomyces* species.” *The ISME Journal* (2023).
   [doi:10.1038/s41396-023-01548-0](https://doi.org/10.1038/s41396-023-01548-0).
4. Lazic SE. “The problem of pseudoreplication in neuroscientific studies: is
   it affecting your analysis?” *BMC Neuroscience* 11 (2010): 5.
   [doi:10.1186/1471-2202-11-5](https://doi.org/10.1186/1471-2202-11-5).
5. [M7 recurrence evidence and declared-independence limits](../M7_INDEPENDENT_RECURRENCE.md).

M14 remains planned. Association, sequence similarity, recurrence, and
demonstrated dependence are separate evidence classes.
