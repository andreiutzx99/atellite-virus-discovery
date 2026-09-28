# M16 benchmarking and validation: design research

**Status: research and architecture proposal only.** M16 is planned, not an
implemented benchmark or validation stage. The current
[roadmap](../ROADMAP.md) assigns it blinded benchmarking and claim-appropriate
validation. No benchmark data, sequences, or experiments were obtained or run
for this report.

This report distinguishes **LITERATURE/EMPIRICAL SUPPORT**,
**PROJECT DESIGN PROPOSAL**, and **UNRESOLVED DECISION**.

## 1. Three distinct validation questions

| Layer | Question answered | What it does not establish |
| --- | --- | --- |
| Software validation | Does the implementation satisfy its frozen input, output, status, accounting, deterministic reuse, and failure contracts? | Biological sensitivity, specificity, or truth. |
| Benchmark performance | How does the frozen workflow perform on a defined, curated, independently held-out example population? | Identity/function of an individual future candidate, or performance on unrepresented classes. |
| Biological validation | Do independent observations and orthogonal evidence support the biological interpretation under study? | A causal/function claim unless the design directly tests it. |
| Experimental confirmation | Does an appropriate controlled experiment demonstrate the specified physical, catalytic, replication, interference, or dependence claim? | Broader claims outside that experiment's design and conditions. |

These outcomes require separate reports, provenance, and acceptance criteria.
Synthetic fixtures are software truth, not biological truth. A benchmark result
does not validate every candidate.

## 2. Benchmark composition and truth provenance

### PROJECT DESIGN PROPOSAL

Freeze a versioned benchmark manifest before evaluation. Each item should have
stable identifiers, source accession/version or source-artifact identity,
sequence/read hashes where permitted, curation provenance, label confidence,
evidence supporting the label, relationships to other records, permitted use,
terms/license, split assignment, and inclusion/exclusion rationale. Do not
silently label uncharacterized cases as negatives.

Build separate sets for distinct questions:

- **Known positives:** experimentally supported satellites/subviral elements
  and, as separate categories, experimentally supported DVG/DI examples,
  known structured RNAs/ribozymes, and other scoped target classes.
- **Biological comparators/hard negatives:** ordinary viral fragments and
  complete genomes, host/organelle and microbial sequences, mobile elements,
  vectors/reagents, non-catalytic structured RNAs, and known DVGs when testing
  satellite differential behavior.
- **Ambiguous/unknown cases:** partial sequences, disputed or weak annotations,
  conflicting labels, and cases with incomplete evidence. These test
  abstention/coverage and must not be forced into positive/negative counts.
- **Synthetic fixtures and simulations:** planted motifs/junctions, mutations,
  errors, chimeras, duplicates, and composition-matched decoys. These test
  software and controlled method behavior, not biological prevalence.

Positive and negative status must be claim-specific. A sequence may be a known
family member but have no experimentally established function; a DVG may be
real without a measured interference phenotype; and a detected read may not
prove independent source molecules.

## 3. Holdouts, blinding, and leakage controls

### LITERATURE/EMPIRICAL SUPPORT

Random cross-validation can overstate generalization when data have temporal,
spatial, hierarchical, or phylogenetic structure. Grouped or structured
holdouts are needed when observations are dependent [1].

### PROJECT DESIGN PROPOSAL

Before method/threshold freeze, partition at the highest relevant dependence
level. Depending on the claim, keep close homologous families/clades, source
studies, sample donors, labs, runs, reference accessions, and replicate
libraries together. Deduplicate identical and near-identical sequences before
split assignment. Preserve a manifest proving no related record crosses
development, tuning, and final holdout sets. If one split cannot prevent every
leakage path, document residual dependence and narrow the performance claim.

Use at least three logically separate collections:

1. **Development set** for method and fixture construction.
2. **Tuning/validation set** for threshold or configuration choices.
3. **Sealed final holdout** administered by a reviewer who did not choose
   settings or curate method-specific borderline cases.

Pre-register evaluation question, accepted label tier, eligibility, required
branches, threshold/settings, tie and abstention handling, strata, metrics,
confidence intervals, and stop rules. Blind candidate identities/labels during
execution and review where feasible. Freeze executable, references, models,
software, settings, and M15 interpretation policy before unblinding. Any
threshold change after results are observed requires a new independent
holdout, not a second look at the same test set.

Do not split reads from the same specimen/library between partitions. Do not
allow benchmark references or model-training alignments to contain test
sequences or their close relatives unless the evaluation explicitly measures
that familiar-reference scenario. Keep benchmark truth curation separate from
the operator running the blinded workflow where practical.

## 4. Metrics and limits

For a binary, adjudicated question with a defensible reference standard, report
sensitivity/recall, specificity, precision, false-positive rate, confusion
counts, class denominators, and uncertainty. Precision and predictive values
depend on prevalence and sampling; do not transfer them to a different
population. AUC or calibration summaries are appropriate only when the method
actually emits scores/probabilities and the truth labels/sample size support
them. A score is not a calibrated probability by naming convention.

For multi-class or differential outcomes, report per-class confusion and
ambiguous/unresolved outcomes, not only aggregate accuracy. Report coverage:
fraction of eligible inputs receiving an analyzable result, and separately the
fractions missing, not applicable, failed, interrupted, incomplete, or
truncated. Provide per-class, length, completeness, divergence, data-source,
and study strata where denominators permit. Confidence intervals must reflect
the independent unit (for example family or study), not millions of correlated
reads as independent examples.

If truth labels are incomplete or disputed, report only the subset with
adjudicated labels and make coverage limits prominent. If no suitable truth
set exists, publish software validation and benchmark protocol readiness
without claiming sensitivity, specificity, accuracy, or biological validation.

## 5. Claim-specific experimental follow-up

**PROJECT DESIGN PROPOSAL:** predefine assays according to the claim, with
positive, negative, mock, and process controls, blinding, replicate structure,
and analysis criteria.

- Ribozyme activity: measure cleavage at the predicted site and products;
  include catalytic-residue mutants and rescue where suitable. In-vitro
  cleavage alone does not establish in-vivo function.
- Physical topology: use an orthogonal molecule/topology assay with appropriate
  linear/circular controls; read junctions and assembly closure are not enough.
- DVG interference: measure the proposed interference phenotype against the
  parental/helper system and controls; junction evidence alone is not
  interference.
- Helper dependence: perturb or omit the proposed helper function and assess
  rescue/complementation under a controlled biological system.
- Source/artifact attribution: use independent extraction/library or
  targeted confirmation and controls matched to the suspected mechanism.

Experimental designs and sample access require separate scientific, ethics,
biosafety, and resource approval. This report does not authorize or perform
experiments.

## 6. Licensing, reproducibility, and unresolved decisions

Truth-set sequence/data terms, article supplementary files, tool licenses,
prepared databases, and derived benchmark manifests may have different
conditions. Record attribution, redistribution/local-use restrictions, privacy
or consent limits, exact snapshots and hashes, curation history, and holdout
custody. Never bundle or publish a reference set merely because its article is
open access. No database or benchmark payload is selected or acquired here.

**Software validation:** M16's own manifest/split validator needs synthetic
fixtures for duplicate/near-duplicate leakage, group assignment, hidden labels,
incomplete truth, corrupted hashes, version mismatch, reproducibility and
metric denominators.

**Biological validation:** requires independent experts and well-documented
truth evidence; the required level differs by target class.

**Experimental confirmation:** requires claim-specific assays and controls;
it is not a metric of the computational benchmark.

### UNRESOLVED DECISIONS

Truth-label tiers, holdout units for each milestone,
acceptable independence and adjudication rules, benchmark data custodians,
release/access policies, minimum denominators and uncertainty reporting, and
which assays are feasible and justified. These decisions precede any
performance claim.

An M16 cache identity should include frozen software/configuration, selected
references/models, benchmark manifest and split assignment, truth-label
version, metric/report code, and any blinded execution artifacts. A change to
the holdout, labeling, or thresholds creates a new evaluation identity.
Upstream evidence identities remain independently scoped.

## 7. Sources checked

1. Roberts DR, et al. “Cross-validation strategies for data with temporal,
   spatial, hierarchical, or phylogenetic structure.” *Ecography* 40 (2017):
   913–929. [doi:10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881).
2. Sandve GK, et al. “Ten Simple Rules for Reproducible Computational Research.”
   *PLoS Computational Biology* 9 (2013): e1003285.
   [doi:10.1371/journal.pcbi.1003285](https://doi.org/10.1371/journal.pcbi.1003285).
3. [M5 caller-specific DVG boundaries](../M5_DVG_EVIDENCE.md),
   [M6 read-support boundary](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md), and
   [M7 recurrence limitations](../M7_INDEPENDENT_RECURRENCE.md).
4. [Current benchmark/validation roadmap scope](../ROADMAP.md).

M16 remains planned. Software checks, benchmark performance, biological
validation, and experimental confirmation are separate results.
