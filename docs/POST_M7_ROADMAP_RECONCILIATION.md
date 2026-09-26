# Post-M7 roadmap reconciliation: proposed M8–M16

**Status: proposed design only.** This document reconciles the current milestone
register with the M8/M9 and M10/M11 design-research briefs. It proposes future
evidence layers; it does not implement them, establish new software contracts,
set scientific thresholds, or classify any candidate. M1–M7 are the current
implemented software baseline; M8–M16 remain planned pending the approvals and
validation described below.

> **Subsequent decision:** The milestone ownership proposed here was later
> adopted in the current [roadmap](ROADMAP.md). Approved refinements clarify
> that M8 accepts valid typed candidate-sequence artifacts regardless of
> upstream support strength and performs nucleotide/reference comparisons
> only; translated and protein evidence belongs to M9. This document preserves
> the original proposal as design history. M8–M16 remain planned; adoption of
> milestone ownership does not approve reference panels, software contracts,
> thresholds, or biological claims.

## 1. Current state and evidence boundary

The current [README](../README.md), [milestone roadmap](ROADMAP.md), and
[M7 documentation](M7_INDEPENDENT_RECURRENCE.md) are the status baseline:
**M1–M7 IMPLEMENTED** as scoped software milestones. This does not mean that the
pipeline is biologically validated. M6's read-back uses reads associated with
assembly; M7 compares exact sequences from individually supported M6
observations and retains declared source-read checksum and sample/run/study
metadata. Neither layer establishes identity, novelty, function, helper
dependence, or biological independence of declared metadata.

M5's `NO_DVG_EVIDENCE_DETECTED` is scoped to a completed, accounted ViReMa run
and is not a non-DVG result. M6 residual status is scoped to the declared
reference FASTA and mapper behavior; residual does not mean novel. The
[M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md) and
[M6 audit](M6_AUDIT.md) document these boundaries. Software tests and workflow
contracts are not truth-set performance or biological validation.

The research briefs remain unchanged historical design research. Statements
within them that describe only M1–M6, say M7 is not available, or assume an
unimplemented M7 input are historical scoping statements from when those briefs
were prepared. They do not supersede the current merged M7 documentation or
create released M8–M11 interfaces. All handoffs below are proposals, not
existing contracts.

The governing principle for future work is cumulative, separately traceable
evidence—not manufactured discoveries. A no-hit can only describe the completed
method and references searched. It must not automatically mean novel, viral,
satellite, non-host, biologically real, or helper-dependent.

## 2. Original conflicts and proposed numbering decision

The current roadmap and the two design briefs assign different work to the same
milestone numbers. The following sequence resolves those conflicts while
preserving all useful topics. This records the proposal's original comparison;
the adopted ownership is listed in the current roadmap.

| Milestone | Roadmap assignment at time of proposal | Research-brief assignment | Proposed assignment, later adopted in roadmap |
| --- | --- | --- | --- |
| M8 | Host/read-origin attribution | Broad reference and homology assessment | Broad, role-separated **candidate-sequence** reference and homology assessment |
| M9 | General candidate characterization | ORF, translated protein, domain/profile-HMM, and remote-homology evidence | ORF and protein/domain/profile/remote-homology evidence |
| M10 | DVG-versus-satellite differential | Genome architecture, termini, and topology | Guarded genome architecture and topology evidence |
| M11 | Helper association | RNA structure and ribozyme discovery | RNA structure and ribozyme prediction evidence |
| M12 | Reference-aware novelty analysis | Not assigned | Read-origin and technical-artifact review, distinct from candidate homology |
| M13 | Contamination and artifact review | Not assigned | DVG-versus-satellite differential evidence |
| M14 | Evidence integration | Not assigned | Helper association and separately validated dependence evidence |
| M15 | Candidate prioritization | Not assigned | Final evidence integration and transparent, optional prioritization |
| M16 | Blinded biological validation | Not assigned | Blinded benchmarking and, where claims require it, biological validation |

This proposal puts candidate/reference similarity before detailed protein
interpretation, places evidence specific to topology and RNA structure in
separate descriptive layers, then adds read-source attribution and competing
biological explanations before association and integration. It separates
candidate-sequence homology (M8) from read/source attribution (M12): matching a
contig to a host, vector, or virus reference is not the same as demonstrating
where the observed reads originated or whether a laboratory artifact explains
them.

Older design prose in the briefs also predates the current M7 status. M8 may
carry M6/M7 evidence when available, but candidate eligibility is based on a
valid typed sequence artifact, not an upstream support threshold. Recurrence
must never be used to infer identity or substitute for candidate sequence
bytes.

## 3. Proposed authoritative milestone sequence

The milestone ownership below follows the current roadmap; every milestone
remains **PLANNED**, while implementation contracts and scientific methods still
require review. These are evidence layers, not automatic stages that every
sequence must pass through. Unavailable, failed, incomplete, unsupported, and
not-evaluated states must remain distinguishable from completed no-signal
results.

| Milestone | Purpose | Main inputs | Proposed outputs and narrow evidence meaning | Dependencies / independent work |
| --- | --- | --- | --- | --- |
| **M8 — Candidate sequence-reference nucleotide homology** | Compare each valid typed candidate sequence with frozen, role-separated nucleotide reference panels. | Exact individual candidate sequence/hash; available upstream evidence state; optional M6/M7 provenance; declared nucleotide panels. | Coordinate-linked nucleotide alignments, competing hits, panel-level execution/accounting, and scoped no-hit. A hit is similarity to named records under a method, not biological identity. | Candidate eligibility is separate from upstream evidence strength; retain short and incomplete candidates without a length-only biological cutoff. Do not upgrade upstream evidence. M8 runs independently per candidate and does not perform translated/protein searches. |
| **M9 — ORF, protein, domain, and remote-homology evidence** | Generate and review coding hypotheses and progressively more sensitive protein-family evidence. | Exact candidate sequences; optional M8 hits as context; declared genetic-code and reference/profile snapshots. | ORF predictions, translated similarities, profile/domain records, bounded remote-homology candidates, competing evidence, and missingness. These are predictions or model similarities, not expression, function, or classification. | Can run from candidate sequence if M8 is unavailable; M8 context is helpful but not a gate. May proceed independently of M10–M12. |
| **M10 — Genome architecture and topology evidence** | Describe sequence architecture, termini, repeats, completeness limits, and carefully scoped topology signals. | Exact candidate sequence; optional linked M9 annotations; authorized reads/library metadata if read-junction analysis is approved. | Coordinates and measurements for features, termini, repeats, and any junction-support signal, with alternatives and evaluation status. A computational signal is not confirmed circularity or genome completeness. | Sequence-only descriptions can run independently; read-junction analysis requires separately approved source reads and controls. Does not depend on an M9 ORF being present. |
| **M11 — RNA structure and ribozyme prediction evidence** | Evaluate RNA structural hypotheses and known-family/model matches where relevant. | RNA sequence or explicitly declared RNA region; orientation, boundaries, optional credible independent related sequences. | Predicted folds/ensembles, covariance-model matches, candidate ribozyme-family evidence, and limits. A fold or motif/model match is not a functional ribozyme. | Independent of M8–M10 for a single-sequence prediction; comparative structure requires an eligible alignment and independent observations. Not applicable or uninformative is not a negative result. |
| **M12 — Read-origin and technical-artifact review** | Assess read-level source alternatives and whether controls, batches, library processes, or reconstruction artifacts explain observations. | Original reads/read manifests and provenance; M6 artifacts; controls, batch/lane and library metadata where authorized; optionally M8 reference-hit coordinates. | Per-read/fragment and control-context findings, source attribution support or unresolved alternatives, and explicit accounting. A sequence match or control recurrence alone does not prove source or contamination. | May proceed in parallel with M8–M11 when source data exist. M8 may suggest targets/decoys, but M8 no-hit does not establish read origin. Requires appropriate controls and trustworthy metadata for source claims. |
| **M13 — DVG-versus-satellite differential evidence** | Place caller-specific DVG evidence alongside satellite/subviral and other alternatives without forcing a binary class. | M5 run/event records; individual M6/M7 evidence; relevant M8–M12 outputs and their completeness. | A structured comparison of supporting, conflicting, absent-within-scope, and unavailable evidence for DVG, satellite/subviral, helper-derived, host/mobile, and artifact alternatives. It does not decide biological identity. | Full differential review benefits from M8–M12; preliminary evidence accounting can proceed from available M5/M6 records. M5 zero events cannot exclude DVG. |
| **M14 — Helper association and dependence evidence** | Examine candidate/helper association across suitable observations and distinguish association from demonstrated dependence. | Matched candidate/helper observations, study design and denominators, M7 metadata, candidate/helper identities under review, and controls. | Association/co-occurrence/covariation summaries with sample units, missingness, and confounders; separately reported experiments if available. Association is not dependence. | Dataset assembly and independent-unit review can proceed alongside M8–M13. Biological dependence claims require an appropriate perturbation/complementation or equivalent experiment, not merely sequence similarity or co-occurrence. |
| **M15 — Final evidence integration and transparent prioritization** | Present evidence dimensions, alternatives, dependencies, and unresolved items together; optionally support a predeclared follow-up ranking. | Available M5–M14 records, provenance, run states, and approved interpretation policy. | An auditable evidence dossier with source-linked claims, correlated-evidence warnings, missingness, alternatives, and (only if approved and validated) a transparent follow-up priority. No automatic biological class or uncalibrated confidence score. | Depends on whatever upstream evidence was evaluated; each layer retains its own scope. Integration can begin with partial data only if gaps are conspicuous and no missing layer is silently treated as negative. |
| **M16 — Blinded benchmarking and biological validation** | Measure performance on independent, appropriately held-out examples and use orthogonal or experimental tests for biological claims. | Frozen methods/configuration/references; independently curated positives, difficult negatives and decoys; blinded holdouts; approved assays and controls as applicable. | Stratified benchmark metrics with denominators/uncertainty, failure and ambiguity rates, leakage audit, and separate experimental outcomes. A computational benchmark does not establish the identity or function of a particular candidate. | Benchmark design and truth-set curation can start earlier; final blinded evaluation follows frozen methods and thresholds. Biological experiments may run independently but must be interpreted against their own controls and claim scope. |

### M8 — Candidate sequence-reference and homology assessment

- **Purpose:** Assess similarity of each candidate sequence to declared reference
  records while keeping competing biological and technical roles visible.
- **Inputs:** One candidate sequence at a time, stable identity and exact
  sequence hash, available upstream M6/M7 records, and versioned reference
  snapshots with record roles and provenance. Searches must not combine reads
  or observations to construct a query.
- **Outputs:** Raw/normalized alignments with coordinates, orientation/frame,
  aligned length, identity, query and subject coverage, score, database and
  record IDs, parameters, masking, competing hits, and panel-specific
  complete/partial/unavailable/failed states. Preserve source annotation and
  uncertainty; do not report only a top hit.
- **Reference roles:** Known satellites/subviral agents; viruses and candidate
  helpers; hosts and organelles; microbes; vectors, adapters, plasmids and
  reagents; mobile elements including Polinton/PLV-related material; and
  project-relevant technical controls/contaminants. Taxonomy is versioned
  descriptive metadata, not truth.
- **Methods:** Candidate classes include local nucleotide alignment, translated
  nucleotide-to-protein searching where appropriate, and sensitivity-staged
  methods. BLAST-family tools are a comprehensible baseline; DIAMOND or MMseqs2
  may be evaluated for scaled protein searches. Tool, panel, model and
  configuration choices are unapproved until benchmarked and licensed.
- **Evidence semantics:** A proposed
  `NO_MATCH_WITHIN_SEARCHED_REFERENCES` is permitted only when the declared
  searches completed with query/panel accounting. It means no reported
  qualifying hit in those named searches—not universal absence, novelty,
  non-viral status, or satellite-negative status. Failed, partial, missing, or
  not-run searches are not no-match results.
- **Dependencies and parallelism:** Requires approved panel contents, frozen
  releases, and licensing/provenance rules. Candidate searches can run
  independently; M9 can proceed without a completed M8 search if this is
  disclosed.
- **Limits:** No universal identity, E-value, coverage, or alignment-length
  cutoff is approved. Scores from different panel sizes are not directly
  interchangeable. A host/mobile/vector match is an alternative for review,
  not automatic rejection; a viral match does not establish satellite identity.

### M9 — ORF, protein, domain, and remote-homology evidence

- **Purpose:** Preserve coding hypotheses and examine translated evidence at
  increasing levels of sensitivity without assuming all candidates encode
  proteins.
- **Inputs:** Exact candidate sequence, optional M8 hits as contextual evidence,
  declared molecule type, genetic-code assumptions, and frozen protein/profile
  references.
- **Outputs:** ORF predictions retaining strand, frame, coordinates, start/stop,
  translation table, overlap, ambiguous bases, and caller identity; translated
  alignments; domain/profile-HMM hits; remote-homology review records;
  provenance, competing hits, and per-method missingness.
- **Methods:** Six-frame enumeration is a transparent candidate-generation
  baseline; context-specific callers such as Prodigal or PHANOTATE require
  evaluation on relevant genome classes. Protein similarity may use BLASTp,
  DIAMOND or MMseqs2; profile/domain evidence may use HMMER/Pfam or
  InterProScan; bounded profile-profile review may use HH-suite. These are
  method classes to evaluate, not selected dependencies. Correlated databases
  and signatures must not be counted as independent votes.
- **Evidence semantics:** `ORF_PREDICTED`, profile match, translated similarity,
  and remote-homology candidate describe computational predictions or
  similarities. They do not establish translation, expression, protein
  function, viral identity, replication, or helper dependence. A
  `NO_MATCH_WITHIN_SEARCHED_PROTEIN_REFERENCES` is limited to completed named
  searches.
- **Dependencies and parallelism:** Exact sequence and method provenance are
  required. M8 can aid context but is not a prerequisite; M9 can operate in
  parallel with M10–M12.
- **Limits:** Do not require an ORF, a universal ORF minimum, a multi-gene
  hallmark set, or any protein hit. Satellite RNAs may be noncoding; small
  candidates can have chance ORFs; partial/chimeric sequences, unusual genetic
  codes, low complexity and caller training can mislead. ORF callers must not
  be merged into a synthetic consensus protein. Do not silently join contig
  ends to predict boundary-spanning ORFs.

### M10 — Genome architecture and topology evidence

- **Purpose:** Describe sequence organization and evaluate topology-related
  signals without converting sequence or assembly patterns into confirmed
  molecule topology.
- **Inputs:** Exact candidate sequence and boundaries; optional linked M9
  predictions, independently sourced related observations, and—only if
  separately approved—raw reads, library construction and molecule metadata.
- **Outputs:** Feature coordinates/orientation; direct and inverted terminal
  repeat alignments; end-to-end overlap; boundary/completeness notes;
  composition summaries; and, if assessed, per-read evidence for a proposed
  junction with unique anchors, alternate mappings and duplicate accounting.
- **Methods:** Bounded sequence comparisons and repeat analysis; explicit
  comparison of original linear representation and any proposed joined
  representation; read mapping or long-read/orthogonal methods only under an
  approved, technology-specific validation design. Comparative completeness
  tools such as CheckV are only context for inputs within their validated
  assumptions.
- **Evidence semantics:** Report e.g. a terminal-repeat signal, an
  assembly-level circularity indication, or reads consistent with a specified
  adjacency. None alone proves circularity, closure, completeness, replication,
  or biological function.
- **Dependencies and parallelism:** Sequence-only feature and repeat
  descriptions can run independently of M9 ORFs and M11 RNA models. Raw-read
  analysis needs authorized source reads, adequate provenance, controls, and
  benchmarks; M6 read-back is not independent validation.
- **Limits:** Direct terminal repeats, inverted repeats, terminal redundancy,
  cohesive ends and circular permutation are distinct architectures. Repeats
  can result from mobile elements, assembly collapse, linear genomes or
  library artifacts. Read junctions can be inflated or mimicked by duplicates,
  multimapping, PCR/RT template switching, ligation, chimeras or misassembly.
  No existing M6 threshold is a validated M10 threshold.

### M11 — RNA structure and ribozyme prediction evidence

- **Purpose:** Add sequence- and structure-based RNA evidence for candidates
  where RNA structure is biologically relevant.
- **Inputs:** Declared RNA sequence or region, exact orientation and boundaries,
  folding conditions, optional credible alignment of independent related
  observations, and frozen family models.
- **Outputs:** Predicted structure/ensemble with parameters; covariance or
  family-model matches and alignments; candidate ribozyme family, catalytic
  residue/context review, alternative models, and execution/missingness states.
- **Methods:** Single-sequence thermodynamic folding (e.g. ViennaRNA RNAfold);
  alignment-aware structure/covariation analysis (e.g. ViennaRNA comparative
  tools and R-scape) only where alignment and independent sampling support it;
  known-family covariance-model searches (Infernal against a frozen Rfam
  release); and carefully validated family-specific candidate-generation
  methods where approved.
- **Evidence semantics:** A fold is `RNA_STRUCTURE_PREDICTED`; a family hit or
  candidate motif is model evidence. Neither establishes native structure,
  self-cleavage, ribozyme activity, replication, satellite identity, or
  function. Functional claims require appropriately controlled biochemical or
  biological evidence.
- **Dependencies and parallelism:** Basic single-sequence evaluation can run
  independently of M8–M10. Comparative covariation depends on a credible
  alignment and enough independent observations. RNA-specific work may be
  uninformative or inapplicable for some candidates.
- **Limits:** MFE is not an in-vivo structure probability; standard secondary
  structure models omit some pseudoknots and tertiary context. Sequence window,
  cut-site rotation for circular inputs, composition bias, multiple testing,
  incomplete family databases and short motifs affect results. No-hit applies
  only to the searched models and release.

### M12 — Read-origin and technical-artifact review

- **Purpose:** Review evidence about where reads may have come from and whether
  technical processes, controls or reconstruction behavior offer alternatives.
  This is intentionally different from M8's comparison of candidate sequence
  against reference sequences.
- **Inputs:** Original read identifiers/sequences and checksums, M6 residual,
  assembly and read-back records, declared run/sample/study and library
  metadata, negative/positive controls, batch/lane information and relevant
  reference-hit coordinates where available. Access to raw reads or sensitive
  metadata requires explicit project approval and handling rules.
- **Outputs:** Per-read/fragment/accounting summaries, control and batch
  comparisons, evidence for or against specified source hypotheses, alternative
  explanations such as adapters, vectors, reagents, host/organelle, microbes,
  mobile elements, index/lane effects, chimeras or assembly artifacts, and
  unresolved/unevaluated states.
- **Methods:** Role-aware read mapping or targeted comparison, control
  concordance, read-pair/fragment context, base-quality and duplication review,
  batch-aware comparisons, and provenance validation. Each method must record
  its reference, query, scope, parameters and completion.
- **Evidence semantics:** A match to a control/reference is evidence to inspect,
  not conclusive attribution. A control-negative result does not rule out a
  contaminant if controls, coverage, or metadata are inadequate. M8 no-hit is
  not evidence of non-host origin.
- **Dependencies and parallelism:** Can proceed in parallel with M8–M11 if
  source reads, controls and provenance are available. M6 outputs are useful
  but read-back only reuses reads used for assembly. M7 recurrence is separate
  and does not verify sample/run/study labels.
- **Limits:** Missing controls, incomplete laboratory records, shared reagents,
  index misassignment, environmental content and biological presence can be
  difficult to distinguish. Do not label contamination or origin from
  sequence similarity alone.

### M13 — DVG-versus-satellite differential evidence

- **Purpose:** Structure a comparison among DVG, satellite/subviral, helper or
  other viral, host/mobile-element and technical-artifact hypotheses.
- **Inputs:** M5 caller-specific event/run status and accounting; M6
  reconstruction evidence; M7 recurrence as its own evidence dimension; M8/M9
  homology and protein evidence; M10 architecture; M11 RNA predictions; M12
  read-origin/artifact review; and curated, independently supported comparison
  examples when available.
- **Outputs:** A transparent differential evidence matrix showing which
  observations support, conflict with, or do not address each hypothesis;
  method scope and completeness; and alternatives requiring review.
- **Methods:** Side-by-side evidence review, event/sequence coordinate linkage,
  class-appropriate architecture and coding expectations, reference alternatives
  and case review against benchmark examples. M5 output stays caller-specific;
  no universal hallmark checklist is proposed.
- **Evidence semantics:** This milestone describes comparative support and
  unresolved explanations; it does not assign DVG/non-DVG or
  satellite/non-satellite identity. A completed M5 zero-event outcome is
  `NO_DVG_EVIDENCE_DETECTED` only within its caller/input/configuration scope
  and does not exclude a DVG.
- **Dependencies and parallelism:** A full differential benefits from M8–M12,
  but bookkeeping and partial review can proceed with available evidence if
  missingness is explicit. DVG caller evidence can be analyzed independently
  from RNA folding or helper association.
- **Limits:** DVG caller sensitivity and specificity for project use are
  unestablished. Incomplete candidates, short noncoding RNAs and divergent
  agents may lack expected signals. No fixed criteria or thresholds are
  approved.

### M14 — Helper association and dependence evidence

- **Purpose:** Evaluate association with plausible helper systems and reserve
  helper-dependence claims for evidence that directly tests dependence.
- **Inputs:** Matched observations with candidate and helper evidence, declared
  sample/run/study metadata and denominators, controls, host/environment
  context, and sequence/homology evidence as appropriate. Preserve missing and
  unmatched observations.
- **Outputs:** Co-occurrence or covariation summaries at explicitly stated
  observational units; uncertainty and confounders; independently reported
  intervention/functional evidence if it exists; and unresolved cases.
- **Methods:** Stratified association or co-variation analysis with
  pseudoreplication safeguards, appropriate negative/positive controls, and
  later experiments such as helper perturbation, complementation or rescue
  where the biological claim warrants them.
- **Evidence semantics:** Co-occurrence, shared sample, correlated abundance,
  compatible sequence similarity, or a proposed helper match supports an
  association hypothesis only. Computational evidence alone does not prove
  dependence or direct interaction.
- **Dependencies and parallelism:** Can be planned and data-curated in parallel
  with M8–M13. Inferential analysis requires matched designs and verified
  denominators; dependence requires a separately approved experimental
  standard.
- **Limits:** Shared host, environment, sampling, sequencing depth and batch
  effects can create association. Declared M7 study/sample IDs are not
  independently verified. Satellite classes differ in what helper functions
  they use; no universal co-occurrence rule is appropriate.

### M15 — Final evidence integration and transparent prioritization

- **Purpose:** Assemble an auditable account of evidence and alternatives and,
  if separately approved, present a transparent priority for follow-up.
- **Inputs:** Available scoped outputs from M5–M14, their hashes, configurations,
  reference snapshots, execution states, and relationships between methods
  that share data or assumptions.
- **Outputs:** Candidate-centered evidence dossiers linking every statement to
  source records; a matrix of support, conflict, unassessed scope and
  alternatives; and an optional, explainable follow-up ranking with its
  objective, uncertainty and validation status.
- **Methods:** Provenance graph/evidence dependency tracking, explicit
  correlation and double-counting review, expert review and—only after
  approval—benchmark-calibrated prioritization. Keep technical reconstruction,
  recurrence, homology, ORF/domain, topology, RNA, read-origin, differential
  and association evidence as distinguishable dimensions.
- **Evidence semantics:** Integration summarizes evidence; it must not silently
  promote predictions to facts or turn a missing layer into negative evidence.
  No single score or automatic biological classification is proposed.
  Prioritization is a decision aid, not a classification or significance claim.
- **Dependencies and parallelism:** The integration format can be designed
  alongside other work; a complete dossier depends on available upstream
  outputs. Partial reports are acceptable only when gaps and unresolved
  alternatives are prominent.
- **Limits:** Correlated hits/signatures and reused reads are not independent
  confirmations. Candidate ranking can inherit ascertainment bias, database
  sampling bias and unvalidated assumptions; ranking policy and target use
  require approval.

### M16 — Blinded benchmarking and biological validation

- **Purpose:** Independently test future methods and, when needed, evaluate
  specific biological claims with appropriate orthogonal or experimental
  evidence.
- **Inputs:** Frozen software, configurations, thresholds and reference
  snapshots; truth-set provenance; blinded family/clade/study holdouts;
  difficult negatives/decoys; and approved biological assays where appropriate.
- **Outputs:** Predeclared sensitivity/recall, false-positive burden,
  ambiguity and missingness rates by sequence class/length/divergence/reference
  role, confidence intervals and denominators; leakage audit; separate
  experimental results and limitations.
- **Methods:** Known positives, difficult negatives, host/microbial/vector/
  mobile-element decoys, short/incomplete/low-complexity/divergent candidates,
  simulated divergence series, family/clade and study-level holdouts, blinded
  review, and claim-appropriate orthogonal assays. Biochemical ribozyme assays
  and topology/helper experiments are distinct from computational benchmark
  performance.
- **Evidence semantics:** A benchmark estimates performance on its defined
  held-out population; it does not make any individual candidate novel,
  biologically real, circular, functional, or helper-dependent. Simulation
  alone is not biological validation.
- **Dependencies and parallelism:** Truth-set curation, licensing and benchmark
  protocol design can begin early. Final evaluation requires locked methods,
  predeclared acceptance criteria, withholding of close relatives where
  appropriate, and independent custody or blinding.
- **Limits:** No sensitivity, specificity, generalization or biological
  validation is currently established for M8–M16. Unsupported classes must be
  stated; aggregate accuracy must not conceal weak performance on short
  satellites or divergent candidates.

## 4. Short-sequence and divergent-candidate safeguards

Short satellite/subviral candidates must remain eligible for review. Do not
invent a biological minimum length, and do not require long nucleotide
alignments, conventional ORFs, multi-gene hallmark sets or whole-query coverage
for every evidence type. Candidate length and sequence class affect the
information available, not whether a candidate is biologically possible.

For each method, report the actual query/window boundaries, aligned span,
coverage denominator, method sensitivity and reason an assessment is
uninformative. A short local hit can be meaningful context but is not whole-
sequence identity; low-complexity motifs can be misleading. A missing ORF or
profile hit is not exclusion evidence for noncoding satellites. Where a method
cannot evaluate a sequence, report it as unassessed/insufficient-for-that-method,
not as a biological negative.

Length-aware criteria, if later proposed, require class-stratified independent
benchmarks. They are not specified here. Progressively less identity-dependent
methods—nucleotide similarity, translated similarity, profiles/remote
homology, architecture, RNA structure and context—are optional evidence
opportunities, not a mandatory path every candidate must traverse.

## 5. Anti-artifact invariants

The following safeguards preserve individual observations and prevent evidence
from being manufactured during future milestone work:

- Do not pool samples or observations merely to create candidates.
- Do not combine unrelated residual reads or co-assemble them to strengthen an
  apparent candidate.
- Retain original read, candidate and observation records and their provenance;
  derived evidence must link back to them.
- Keep recurrence and assembly as separate evidence. M7 recurrence compares
  exact individually supported sequences; it does not justify pooling, create
  a biological consensus, or verify metadata independence.
- Do not fabricate consensus genomes by merging unrelated observations.
- Do not substitute read-back of assembly-associated reads for independent
  replication, a held-out sample or an orthogonal assay.
- Do not count repeated database signatures, overlapping alignments, or shared
  underlying references as independent confirmations.
- Keep unavailable, failed, partial and incomplete evaluations distinct from
  completed no-hit/no-signal outcomes.

## 6. Benchmarking and validation strategy

Benchmarking must be designed before thresholds or interpretation rules are
selected. Freeze reference and model snapshots and retain accession versions,
provenance, checksums, license terms and withheld records. Hold out whole
families/clades and, where feasible, source studies; random record splits can
leak close relatives into both development and test data and overstate
generalization [17].

Build class-stratified positives and difficult negatives including satellite
RNAs and viruses, helper viruses, virophages, Polintons/PLVs, host and
organelle sequences, microbial sequences, vectors/plasmids, mobile elements,
documented technical contaminants, and linear or unrelated sequences. Include
short, incomplete, low-complexity, divergent and chimeric candidates; controlled
divergence series; composition-matched shuffles and motif/domain decoys; and
representative controls processed with realistic library protocols. Synthetic
examples test known perturbations but do not substitute for independently
labelled biological examples.

Evaluate M8/M9 no-hit and competing-hit semantics, reference-role conflicts,
ORF boundary/overlap recovery, profile coverage, remote-homology ambiguity and
missingness. Evaluate M10 with positive and negative topology/terminus classes,
repeat architectures, simulated read lengths/depth/errors, duplicates,
multimapping, chimeras, misassemblies and negative controls. Evaluate M11
candidate generation, family assignment and catalytic hypotheses separately
using experimentally supported ribozymes, related-family holdouts,
non-catalytic structured RNAs and length/composition/complexity-matched decoys.
Evaluate M12 read-origin/artifact conclusions with controls and batch/lane
challenge cases. Evaluate M13/M14 differential and association claims on
independent matched observations, not reused samples counted as independent.

Report denominators, uncertainty, ambiguity and failure rates, sensitivity and
false-positive burden by class, length, divergence, reference role and
technology. Predeclare thresholds, review rules and acceptance criteria.
Biological confirmation requires a claim-appropriate independent assay; for
example, computational topology indication is not molecule-level confirmation,
and a predicted ribozyme fold is not a cleavage assay. If independent truth data
or experiments are unavailable, describe the work as software-tested or
computationally benchmarked within scope, not biologically validated.

## 7. Migration from the current planned register

| Old roadmap topic/location | Proposed destination | Disposition |
| --- | --- | --- |
| M8 — Host/read-origin attribution | **M12** for read/source attribution; relevant host/organelle/vector/etc. reference panels are also present in **M8** | Split query-level homology from read-origin inference; no capability dropped. |
| M9 — Candidate characterization, features, coding and structure | **M9** for ORF/protein evidence; **M10** for architecture/topology; **M11** for RNA structure/ribozyme predictions | Decomposed into evidence-specific layers so unlike predictions remain distinct. |
| M10 — DVG/satellite differential evidence | **M13** | Preserved after M8–M12 evidence is available; M5 alone remains insufficient for classification. |
| M11 — Helper association | **M14** | Preserved, with association separated from experimental dependence. |
| M12 — Reference-aware novelty analysis | **M8** candidate/reference homology, with protein-focused extension in **M9** | Reframed: the capability is scoped similarity assessment, never an automatic novelty determination. |
| M13 — Contamination and artifact review | **M12**, with technical-control and contaminant panels in **M8** | Split reference comparisons from read/control/batch source review. |
| M14 — Evidence integration | **M15** | Preserved as provenance-aware integration with correlation, missingness and alternatives visible. |
| M15 — Candidate prioritization | **M15** | Retained as an optional, transparent follow-up ranking within final integration; requires separate approval and calibration. |
| M16 — Blinded biological validation | **M16** | Expanded to include blinded computational benchmarking and distinct claim-appropriate biological validation. |
| Brief M8/M9: reference homology; ORF/protein/profile/remote homology | **M8/M9** | Preserved and made authoritative for those numbers. |
| Brief M10/M11: architecture/topology; RNA/ribozyme evidence | **M10/M11** | Preserved and made authoritative for those numbers. |

All useful capabilities in the two briefs and the current roadmap have an
assigned destination. No capability is intentionally dropped. Some future
methods remain unassigned at the tool level by design: selecting a particular
caller, database, assay, threshold, schema or classifier requires the approvals
and validation below.

## 8. Open decisions requiring approval

The sequence above is a proposal, not an approval of scope, thresholds or
implementation. At minimum, resolve:

| Decision area | Approval needed before implementation or interpretation |
| --- | --- |
| Reference scope and stewardship | Target host/helper scope; contents and curation of every M8 role panel; source/release cadence; taxonomy mapping; benchmark withholding; record exclusions; snapshot provenance; privacy; and redistribution/license terms for software, models and data. |
| Search methods and semantics | Default versus staged nucleotide/translated/protein searches; what counts as `KNOWN/SIMILAR` versus `AMBIGUOUS`; hit retention; treatment of competing roles; partial-panel summaries; and any length-aware thresholds after independent validation. No thresholds are set here. |
| ORF/protein evidence | Required baseline caller(s), genetic-code/context assumptions, short/overlapping ORF handling, profile collections, remote-homology workflow versus manual review, external-service data policy, output schemas and compute budgets. |
| Architecture/topology | Accepted molecule classes; whether source reads may be re-read; read/library metadata and privacy controls; algorithms, duplicate/molecule accounting, anchor/mapping criteria, accepted orthogonal assays, and whether CheckV is appropriate for particular inputs. M6 settings are not M10 criteria. |
| RNA/ribozyme evidence | RNA classes and windows; folding and circular-input handling; frozen Rfam/model releases and gathering thresholds; custom covariance models or specialized searches; family-specific validation; and what biochemical evidence supports any functional wording. |
| Read-origin/artifact review | Access to original reads, control design, batch/lane and reagent metadata; suitable attribution evidence; handling of shared environmental/host signals; and criteria for unresolved outcomes. |
| Differential and helper evidence | Curated independent DVG/satellite examples; differential review language; observational unit, matched-sample design and denominators; confounder handling; definition of dependence; and experimental perturbation/complementation standards. |
| Integration and prioritization | Evidence-dependency/correlation model; whether any score or ranking is desired; the use/objective and calibration of a ranking; acceptable missingness; review/correction process; and prohibition or conditions for automated class labels. |
| Blinded validation | Truth-set custody and independent labels; short/divergent class representation; holdout levels; hard-negative and decoy design; predeclared metrics/acceptance criteria; assay controls; licenses; and independent reviewers. |
| Implementation contracts and operations | Typed artifact schemas and statuses; tool/version pinning; resource/runtime budgets; optional-dependency policy; failure/reuse semantics; storage/retention; and whether any future tool is bundled or user-supplied. |

## 9. Literature rationale

These publications support method choices or biological context; they do not
validate this project's thresholds, reference panels, future software, or any
candidate claim.

1. Altschul SF, Gish W, Miller W, Myers EW, Lipman DJ. (1990). Basic local
   alignment search tool. *Journal of Molecular Biology*, 215(3), 403–410.
   [doi:10.1016/S0022-2836(05)80360-2](https://doi.org/10.1016/S0022-2836(05)80360-2).
   Local similarity is method- and database-scoped.
2. Buchfink B, Xie C, Huson DH. (2015). Fast and sensitive protein alignment
   using DIAMOND. *Nature Methods*, 12, 59–60.
   [doi:10.1038/nmeth.3176](https://doi.org/10.1038/nmeth.3176).
3. Eddy SR. (2011). Accelerated profile HMM searches. *PLoS Computational
   Biology*, 7(10), e1002195.
   [doi:10.1371/journal.pcbi.1002195](https://doi.org/10.1371/journal.pcbi.1002195).
4. Mistry J, Chuguransky S, Williams L, et al. (2021). Pfam: The protein
   families database in 2021. *Nucleic Acids Research*, 49(D1), D412–D419.
   [doi:10.1093/nar/gkaa913](https://doi.org/10.1093/nar/gkaa913).
5. Söding J. (2005). Protein homology detection by HMM–HMM comparison.
   *Bioinformatics*, 21(7), 951–960.
   [doi:10.1093/bioinformatics/bti125](https://doi.org/10.1093/bioinformatics/bti125).
   Profile and remote-homology methods expand evidence but require review and
   provenance.
6. Hyatt D, Chen GL, LoCascio PF, Land ML, Larimer FW, Hauser LJ. (2010).
   Prodigal: prokaryotic gene recognition and translation initiation site
   identification. *BMC Bioinformatics*, 11, 119.
   [doi:10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119).
7. McNair K, Zhou C, Dinsdale EA, Souza B, Edwards RA. (2019). PHANOTATE: a
   novel approach to gene identification in phage genomes. *Bioinformatics*,
   35(22), 4537–4542.
   [doi:10.1093/bioinformatics/btz265](https://doi.org/10.1093/bioinformatics/btz265).
   Caller scope supports evaluating class-specific rather than universal ORF
   models.
8. Hu C-C, Hsu Y-H, Lin N-S. (2009). Satellite RNAs and satellite viruses of
   plants. *Viruses*, 1(3), 1325–1350.
   [doi:10.3390/v1031325](https://doi.org/10.3390/v1031325).
   Reviews biological diversity, including noncoding satellite RNAs and
   satellite viruses.
9. La Scola B, Desnues C, Pagnier I, et al. (2008). The virophage as a unique
   parasite of the giant mimivirus. *Nature*, 455, 100–104.
   [doi:10.1038/nature07218](https://doi.org/10.1038/nature07218).
10. Páez-Espino D, Roux S, Chen IMA, et al. (2019). Diversity, evolution, and
    classification of virophages uncovered through global metagenomics.
    *Microbiome*, 7, 157.
    [doi:10.1186/s40168-019-0768-5](https://doi.org/10.1186/s40168-019-0768-5).
11. Yutin N, Shevchenko S, Kapitonov V, Krupovic M, Koonin EV. (2015). A novel
    group of diverse Polinton-like viruses discovered by metagenome analysis.
    *BMC Biology*, 13, 95.
    [doi:10.1186/s12915-015-0207-4](https://doi.org/10.1186/s12915-015-0207-4).
    These works illustrate why virus-like and mobile-element alternatives and
    class-variable protein modules must remain visible.
12. Routh A, Johnson JE. (2014). Discovery of functional genomic motifs in
    viruses with ViReMa—a virus recombination mapper—for analysis of
    next-generation sequencing data. *Nucleic Acids Research*, 42(2), e11.
    [doi:10.1093/nar/gkt916](https://doi.org/10.1093/nar/gkt916).
13. Sotcheff S, et al. (2023). ViReMa: a virus recombination mapper of
    next-generation sequencing data characterizes diverse recombinant viral
    nucleic acids. *GigaScience*, 12, giad009.
    [doi:10.1093/gigascience/giad009](https://doi.org/10.1093/gigascience/giad009).
    These describe caller methods, not project-specific DVG sensitivity or
    biological classification.
14. Nayfach S, Camargo AP, Schulz F, et al. (2021). CheckV assesses the quality
    and completeness of metagenome-assembled viral genomes. *Nature
    Biotechnology*, 39, 578–585.
    [doi:10.1038/s41587-020-00774-7](https://doi.org/10.1038/s41587-020-00774-7).
15. Wu Q, Wang Y, Cao M, et al. (2012). Homology-independent discovery of
    replicating pathogenic circular RNAs by deep sequencing and a new
    computational algorithm. *PNAS*, 109(10), 3938–3943.
    [doi:10.1073/pnas.1117815109](https://doi.org/10.1073/pnas.1117815109).
16. Weinberg CE, Weinberg Z, Hammann C. (2019). Novel ribozymes: discovery,
    catalytic mechanisms, and the quest to understand biological function.
    *Nucleic Acids Research*, 47(18), 9480–9494.
    [doi:10.1093/nar/gkz737](https://doi.org/10.1093/nar/gkz737).
17. Roberts DR, Bahn V, Ciuti S, et al. (2017). Cross-validation strategies
    for data with temporal, spatial, hierarchical, or phylogenetic structure.
    *Ecography*, 40, 913–929.
    [doi:10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881).
    Structured holdouts help avoid overstating generalization through related
    examples in both train and test sets.
18. Lazic SE. (2010). The problem of pseudoreplication in neuroscientific
    studies: is it affecting your analysis? *BMC Neuroscience*, 11, 5.
    [doi:10.1186/1471-2202-11-5](https://doi.org/10.1186/1471-2202-11-5).
    Relevant to defining observational units for recurrence and association.
19. Lorenz R, Bernhart SH, Höner zu Siederdissen C, et al. (2011). ViennaRNA
    Package 2.0. *Algorithms for Molecular Biology*, 6, 26.
    [doi:10.1186/1748-7188-6-26](https://doi.org/10.1186/1748-7188-6-26).
20. Nawrocki EP, Eddy SR. (2013). Infernal 1.1: 100-fold faster RNA homology
    searches. *Bioinformatics*, 29(22), 2933–2935.
    [doi:10.1093/bioinformatics/btt509](https://doi.org/10.1093/bioinformatics/btt509).
21. Ontiveros-Palacios N, Cooke E, Nawrocki EP, et al. (2025). Rfam 15: RNA
    families database in 2025. *Nucleic Acids Research*, 53(D1), D258–D267.
    [doi:10.1093/nar/gkae1023](https://doi.org/10.1093/nar/gkae1023).
    Database releases are scoped resources, not complete catalogs of all
    structures or ribozymes.
22. Rivas E, Clements J, Eddy SR. (2017). A statistical test for conserved RNA
    structure shows lack of evidence for structure in lncRNAs. *Nature
    Methods*, 14(1), 45–48.
    [doi:10.1038/nmeth.4066](https://doi.org/10.1038/nmeth.4066).
23. Lee BD, Neri U, Roux S, et al. (2023). Mining metatranscriptomes reveals a
    vast world of viroid-like circular RNAs. *Cell*, 186(3), 646–661.e4.
    [doi:10.1016/j.cell.2022.12.039](https://doi.org/10.1016/j.cell.2022.12.039).
    Discovery reports motivate cautious computational follow-up; they do not
    establish the function of unrelated candidates.

## 10. Source documents and validation scope

This reconciliation uses the current README and roadmap, the M1–M6 scientific
audit, M6 audit and M7 documentation, and both unchanged research briefs:
[M8/M9 design research](research/M8_M9_DESIGN_RESEARCH.md) and
[M10/M11 design research](research/M10_M11_DESIGN_RESEARCH.md). The historical
briefs remain research context, not current status or released interfaces.

Validation for this documentation change should check internal links/anchors,
whitespace, and the complete diff. Confirm that only this reconciliation and
the aligned roadmap changed (the README needs no change because its status
wording and roadmap link are already consistent), both research briefs are
unchanged, and no production source code changed. Record the actual check
commands and outcomes in the review report; do not imply biological validation
or implementation of a planned milestone.
