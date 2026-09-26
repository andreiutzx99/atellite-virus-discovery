# M10/M11 design research: genome architecture and RNA evidence

**Status: design research only.** This report proposes evidence layers for future
work; it does not implement, integrate, or validate them. It makes no claim that
any project candidate is a satellite, has a circular genome, or encodes a
functional ribozyme.

> **Historical design record:** This report preserves the research scope and
> roadmap discrepancy recorded when it was prepared. The project later adopted
> the M10/M11 ownership shown in the current [roadmap](../ROADMAP.md). This
> report remains a proposal, not an implementation or released interface.

## 1. Scope and milestone-number discrepancy

This report follows the supplied M10/M11 research brief:

- **M10:** genome architecture, termini, completeness, and topology.
- **M11:** RNA structure and ribozyme discovery.

The current [roadmap](../ROADMAP.md) assigns different topics to those numbers:
M10 is DVG/satellite differential evidence and M11 is helper association. This
report records that discrepancy without editing the roadmap. The intended
milestone numbering and ownership need resolution before implementation.

The project currently has implemented M1–M6 software, not a validated
biological discovery chain. M1–M4 support declared, provenance-bearing
artifacts and bounded workflows. M5 can report scoped ViReMa junction evidence;
`NO_DVG_EVIDENCE_DETECTED` means that the configured, completed run reported no
supported events, not that a sequence is biologically non-DVG. M6 accounts for
reads against a declared reference, partitions residual reads, and may assemble
eligible reads and align those same reads back to contigs. M6's
`READ_SUPPORTED_ASSEMBLY` is technical, run-scoped evidence, not independent
confirmation, topology evidence, or a biological classification.

The current artifact contracts describe formats and provenance, not biological
identity or function. M9-like ORF, domain, and structure assessment is not
implemented in this discovery context. A separate M7 brief proposes
independent recurrence, but M7 output is not an available/implemented input
contract assumed here. If later supplied, M7 recurrence must remain a separate
reproducibility layer, not biological validation or an upgrade to M6 support.
Likewise, M8/M9 handoffs below are prospective; their design briefs are not
released interfaces.

## 2. Design principles

1. Keep sequence observations, read support, topology indications, comparative
   annotations, RNA models, and experimental results as distinct evidence
   records.
2. Report what was evaluated, with which input, configuration, and database
   snapshot. Missing, unavailable, failed, and incomplete evidence are not
   negative findings.
3. Use scoped language such as **junction-spanning reads observed**,
   **terminal-repeat signal detected**, **RNA family model match**, and
   **predicted secondary structure**. Do not turn these into “confirmed
   circular,” “complete genome,” “ribozyme,” “functional,” “satellite,” or
   “novel” labels.
4. Do not add a single evidence score or classification unless an independently
   labelled benchmark later supports its calibration and the project separately
   approves that interpretation.
5. Preserve alternative explanations, including linear genomes with terminal
   repeats, assembly collapse, host/mobile-element sequence, chimeric molecules,
   and nonfunctional structural lookalikes.

## 3. M10 — genome architecture, termini, and topology

### 3.1 Evidence types and what they can support

| Evidence | Proposed measurement | Narrow interpretation |
| --- | --- | --- |
| End-to-end sequence overlap | Exact and local alignment of the candidate's beginning and end, with repeat length, identity, orientation, and alignment coordinates | A direct-repeat or terminal-redundancy signal exists in this sequence representation. It does not establish a circular molecule or completeness. |
| Terminal inverted repeat (TIR) | End-to-end reverse-complement comparison, retaining both arms, spacer, mismatches, and coordinates | An inverted-repeat pattern exists. TIRs also occur in transposons and other mobile elements. |
| Read evidence across a proposed junction | Read/fragment alignments spanning the specific end-to-start adjacency, with unique anchors on both sides and per-read mapping/edit evidence | The sampled library contains reads consistent with that adjacency. It is not, by itself, proof of the original molecule's topology. |
| Genome architecture | Descriptive coordinates and orientation of features; link any ORFs/domains to separately versioned M9 annotations | A feature arrangement was observed or predicted under the stated annotation method. It does not establish protein expression or function. |
| Completeness/boundary evidence | Explicitly describe supported sequence ends, unresolved ends, possible overlap, and any known-reference comparison | Sequence boundary support under the evaluated methods. “No missing gene found” is not completeness evidence. |
| Composition | Length, GC, ambiguity, k-mer/dinucleotide summaries and, if justified, comparisons to explicit backgrounds | Descriptive sequence statistics only. Short candidates, biased libraries, host sequence, and low complexity can dominate these values. |
| Conserved termini or UTRs | Compare ends/UTRs across independently sourced, appropriately oriented related observations; retain aligned regions and denominator | Similarity in the evaluated set. Conservation does not establish a replication signal or biological role. |

For end-repeat analysis, compare both same-orientation direct repeats and
reverse-complement inverted repeats. Record repeat length, percent identity,
alignment coverage, mismatches/gaps, sequence complexity, and whether the
candidate is shorter than or comparable to the proposed repeat. Avoid a
standalone “repeat present” flag without coordinates and sequence context.
Terminal redundancy, direct terminal repeats, inverted terminal repeats,
cohesive ends, and circular permutation are different architectures and should
not be collapsed into one topology class.

For read evidence, a future workflow could map reads to a circularized
representation that explicitly joins the proposed ends, while also comparing
the original linear representation. A short-read observation should span the
join with enough uniquely mappable sequence on both sides; paired-end
association alone is weaker than one read crossing the adjacency. Retain
secondary/multimapping information rather than silently dropping competing
placements. Long reads or independent end-targeted assays may add evidence, but
their error profiles and library construction must also be recorded.

### 3.2 Circularity indication is not biological confirmation

An overlap between assembled contig ends is an **assembly-level circularity
indication**, not proof of a covalently closed circle. Short-read assemblers
can output a circular-looking contig from repeated sequence, collapsed copies,
or a circularized representation chosen for convenience. Direct terminal
repeats can arise during assembly of circular genomes, but can also arise in
linear genomes replicated through concatemers or with circular permutation.
Terminal inverted repeats are common in mobile elements. CheckV explicitly uses
terminal-repeat signals in its closure calls and discusses these alternative
origins; its method is useful precedent, not a biological truth oracle for
small or highly divergent satellites.

Read support has additional failure modes:

- PCR duplicates, optical duplicates, and reads without unique molecular
  identifiers can inflate apparent independent support.
- Repetitive ends, low-complexity anchors, conserved motifs, and closely related
  references create multimapping or false placements.
- Ligation, reverse-transcription template switching, PCR recombination,
  rolling-circle amplification, and library chimeras can create junction-like
  molecules. Their relevance depends on the assay and must be documented.
- Reads supporting an assembly are not an independent sample if they are the
  same reads used to assemble it. This is exactly the M6 limitation: its
  read-back step reuses assembly-eligible reads.
- A read that crosses a join in an arbitrary linearization of a circle is
  compatible with a circular template, but can also be generated by a
  chimera or an assembly error. A mapping decision alone cannot distinguish
  these.

Safeguards should include end-to-end unique-anchor checks, alternate-reference
and decoy mapping, duplicate/molecule accounting where the library supports
it, explicit review of repeats and base qualities, raw-read provenance, and
negative controls processed with the same library protocol. Require replication
from an independently prepared library or an orthogonal topology assay before
using biological confirmation language. Any numeric threshold for number of
spanning reads, anchor length, MAPQ, identity, or coverage must be calibrated on
the relevant read technology, genome class, and control set; M6's technical
read-support defaults are not validated M10 thresholds.

Where topology matters biologically, confirmation should come from an
appropriate experiment, not an in-silico label. Possible orthogonal evidence
includes controlled nuclease/topology assays, end-specific or junction-specific
validation with appropriate linear and circular controls, and physical
molecule-level evidence. Each assay has its own artifacts: exonuclease
resistance is not uniquely diagnostic, and RT-PCR can create template-switch
artifacts. The choice and interpretation require expert approval for the
organism, molecule type, and sample preparation.

### 3.3 Completeness and architecture

Do not infer a complete genome solely from a circular-looking assembly, a
terminal repeat, a fixed length, or detection of expected genes. A future
completeness record should state the exact candidate sequence and version,
whether both sequence boundaries are supported, which regions remain
unresolved, whether an overlap was trimmed or retained, and which independent
evidence supports closure. For RNA satellites and viroids, “complete” must not
be conflated with coding capacity: many are noncoding, and their expected
architecture differs from that of dsDNA virophages or protein-coding viruses.

Feature order, strand, intergenic regions, ORFs, repeat placement, and
composition are descriptive. ORFs should be linked to the M9 tool and output
that produced them and remain predictions until experimentally supported.
Composition and short ORFs are particularly weak evidence on small sequences.
Conserved termini/UTRs can be useful comparative evidence if orientation,
sequence identity, and independent observation counts are retained; a motif
match alone is not evidence of replication or function.

CheckV is a reasonable candidate for comparative quality/completeness context
when inputs fit its metagenome-assembled viral genome assumptions and its
reference database is frozen. It should not be treated as calibrated for very
small, noncoding, highly divergent satellite RNAs or all genome classes.
Tool output should be retained alongside its version, database version, input
hash, and limits. A future local end-repeat/read-junction analysis should remain
separable from CheckV and from any ORF-based annotation.

## 4. M11 — RNA structure and ribozyme discovery

### 4.1 Secondary-structure prediction

ViennaRNA `RNAfold` is a sensible baseline for single-sequence, thermodynamic
secondary-structure hypotheses. The package can report a minimum-free-energy
(MFE) fold and ensemble quantities such as base-pair probabilities; these
should be presented together rather than treating one optimal drawing as the
unique native structure. Record sequence orientation, sequence boundaries,
folding conditions/parameters, software version, and whether constraints were
used. Do not interpret energy as a probability that a structure exists in vivo.

Important limitations:

- The nearest-neighbor thermodynamic model does not reproduce all cellular
  conditions, proteins, ligands, ions, transcription kinetics, or competing
  conformations. MFE is a model optimum, not an experimental structure.
- Standard secondary-structure folds do not represent all pseudoknotted
  structures. Some ribozymes depend on tertiary contacts or pseudoknots, so a
  weak or absent ordinary fold is not exclusion evidence.
- For a circular RNA, a linear input has an arbitrary cut site. The fold may
  depend on sequence rotation and does not itself encode covalent closure.
  Circular folding modes or cut-rotation sensitivity should be reviewed if
  adopted; the input topology must remain a separate evidence record.
- Folding a short motif without sufficient flanking sequence can produce
  misleading stems; folding a long molecule may obscure local alternatives.
  Report searched windows and their boundaries.
- GC-rich, low-complexity, or repeated sequences often have stable-looking
  predicted stems without a specific biological role.

For multiple related sequences, an alignment-aware prediction (for example,
ViennaRNA's comparative tools) can use conservation and covariation, but only
when the alignment is credible and the observations are independent enough to
support comparison. R-scape provides statistical tests for covariation above
phylogenetic expectation. Significant covariation can support conserved base
pairs; lack of significant covariation can reflect insufficient sequence
variation or sample size and does not disprove structure. A single candidate
cannot provide comparative covariation evidence.

### 4.2 Covariance models and reference databases

Infernal builds and searches covariance models (CMs) that encode both sequence
and conserved secondary-structure patterns. `cmscan` against a frozen Rfam CM
release is recommended for known-family searches. Preserve the Rfam accession,
release, model-specific gathering threshold, hit coordinates, score,
orientation, and alignment. Prefer curated gathering thresholds over a
project-wide arbitrary score cutoff.

As checked for this research, Rfam 15.1 (January 2026) lists 4,227 families,
provides alignments and CMs, and makes downloads available under CC0. It
contains ribozyme families and recent additions including the Hairpin-meta1
virus-like ribozyme family (RF04190). Family coverage is incomplete: an Infernal
no-hit means only that no family match passed the evaluated model thresholds in
that Rfam snapshot. It does not exclude an unknown ribozyme or remote
homologue. Model hits can also be false positives, especially for short,
low-complexity, or compositionally biased sequences.

For known hammerhead, hairpin, HDV-like, and other ribozymes, combine Rfam/
Infernal matches with family-specific structural constraints and curated
positive/negative examples. If a family lacks an adequate CM, a custom model
could be considered only with expert-curated alignments, held-out evaluation,
and explicit threshold provenance. A hand-written motif or regular expression
should be a candidate-generation filter, not a detector with biological
specificity. Rfam's family models are intentionally conservative for annotated
families and will not substitute for discovery of novel structural classes.

### 4.3 Specialized ribozyme search and functional limits

The starting papers and additions support several useful distinctions:

- Hammerhead ribozymes were first associated with viroids and plant satellite
  RNAs, where self-cleavage can process multimeric replication intermediates.
  Computationally detected hammerhead-like folds in other organisms show that
  the sequence/structure family is diverse, but do not make every motif a
  functional ribozyme.
- Hairpin ribozymes also occur in plant-virus satellite RNA contexts. Rfam's
  newer Hairpin-meta1 family demonstrates that additional virus-like ribozyme
  lineages continue to be discovered.
- HDV-like self-cleaving ribozymes are known in hepatitis delta virus and in
  other biological contexts. A hit to a known family supports similarity to
  that model, not cleavage in the candidate's native transcript.
- Other self-cleaving families (for example, VS and glmS) can be included in
  broad Rfam screening, while interpretation should account for their known
  contexts and mechanisms rather than assuming they are satellite signatures.

Ribozyme discovery should therefore be staged: candidate generation by known
CMs and/or carefully specified structural searches; inspection of conserved
catalytic residues and complete structural context; comparative evidence where
available; then experimental testing. A predicted motif or a matching CM must
not be emitted as proof of self-cleavage, replication, satellite identity, or
function. Strong functional support requires an assay that measures cleavage
at the predicted site and controls for transcript abundance and spontaneous
degradation. Depending on the claim, follow-up may include cleavage kinetics,
expected product-end chemistry, catalytic-residue disruption and rescue, and
testing in a relevant biological context. In-vitro cleavage still does not
alone establish in-vivo role.

False-positive mechanisms include short catalytic-motif coincidences, multiple
testing across many sequences/windows, over-permissive custom models, alignment
errors, low-complexity and base-composition bias, plausible but nonnative
thermodynamic folds, and matches to conserved stems without catalytic residues.
Safeguards include family-specific thresholds, decoy sequences matched for
length/composition/complexity, reporting all competing hits, correction or
calibration for the number of searches, and independent experimental
validation. A negative search is scoped to the tested families, models,
parameters, input sequence, and release.

## 5. Prospective handoffs and evidence contract

These are proposed inputs, not existing M10/M11 interfaces.

| Source | Prospective input | Boundary |
| --- | --- | --- |
| M6 | Candidate FASTA/contig identity; assembly and reconstruction status; residual manifest; source/QC hashes; read-back alignment/support records; when authorized and available, the exact source reads and library metadata | Read-back is against the same eligible reads used for assembly. It is not independent validation. A failed, unavailable, unsupported, or unresolved M6 state must remain visible and cannot be promoted by a topology or RNA prediction. |
| M7 | If later implemented, observation identities, sequence hashes, independence metadata, and exact/related recurrence evidence | Treat recurrence as reproducibility evidence only. Do not pool reads or treat recurrence as topology, ribozyme function, or biological confirmation. No current M7 output is assumed. |
| M8 | If later implemented, frozen reference snapshot, taxonomic/source metadata, scoped nucleotide or translated matches, alignment intervals, and competing hits | No-hit is limited to the searched database and method. It does not establish novelty or exclude mobile-element/host explanations. |
| M9 | If later implemented, ORF coordinates/strand, domain/profile matches, RNA-region annotations, method and reference versions | ORFs, domains, and predicted features remain descriptive predictions. They are not expression or function evidence. |

A future typed output should preserve, at minimum:

- stable candidate/sequence ID, exact sequence hash and length, strand or
  orientation convention, source artifact hash, and upstream M6 state;
- method/tool and version, parameters, database release and model accession,
  relevant threshold policy, input hashes, output hashes, and execution status;
- raw or normalized end-repeat alignments and coordinates, repeat class,
  junction-spanning read IDs and alignment evidence, competing mappings,
  per-fragment/molecule accounting where available, and the read/library
  provenance needed to interpret them;
- architecture/ORF/UTR annotations as linked descriptive records, not an
  unqualified genome label;
- RNA fold output, ensemble/base-pair probabilities, input window and
  orientation, Rfam/Infernal hit evidence, candidate ribozyme family and
  structural evidence, and any experimental results in a separate field;
- status and limits that identify which individual evidence was evaluated,
  unavailable, incomplete, invalid, or failed.

Suggested status vocabulary should remain evidence-scoped. Examples:

- `CIRCULARITY_INDICATION_DETECTED` — sequence or read evidence meets a
  predeclared computational criterion; never synonymous with confirmed
  circular topology.
- `TERMINAL_REPEAT_SIGNAL_DETECTED` — a specified direct or inverted repeat
  was found with reported coordinates and alignment details.
- `NO_SIGNAL_WITHIN_EVALUATED_SCOPE` — no indication met the declared method
  and threshold; not biological absence.
- `RNA_STRUCTURE_PREDICTED` — a model output was generated, not experimentally
  verified.
- `RIBOZYME_FAMILY_MATCH_REPORTED` / `RIBOZYME_CANDIDATE_REPORTED` — a model
  or motif candidate was reported, not proven catalytic.
- `NOT_EVALUATED`, `DEPENDENCY_UNAVAILABLE`, `EXECUTION_FAILED`,
  `INCOMPLETE`, `INVALID_INPUT`, and `REVIEW_REQUIRED` — retain these distinct
  from a completed no-signal result.

Avoid statuses such as `CONFIRMED_CIRCULAR`, `COMPLETE_GENOME`,
`FUNCTIONAL_RIBOZYME`, `NON_RIBOZYME`, or a satellite identity unless a future,
separately approved evidence standard and appropriate biological validation
support them. The human-readable report should state evaluated scope, missing
inputs, unresolved alternatives, and evidence limits adjacent to every summary.

## 6. Benchmarking and validation

### M10

Build independent, stratified positive and negative sets covering circular
RNA/DNA genomes, linear genomes, genomes with direct or inverted repeats,
terminally redundant and circularly permuted phages, integrated elements,
transposons, and sequence classes relevant to satellites. Freeze source
accessions, topology evidence, and curation decisions. Hold out entire related
families or taxonomic groups where possible; near-identical sequences must not
leak between development and test sets.

Generate controlled read simulations across read lengths, depth, error rates,
repeats, and insert-size distributions, then add challenge cases for duplicated
reads, low-complexity junctions, multimapping, chimeric reads, assembly
misjoins, and partial contigs. Include end-to-end negative controls processed
with representative library protocols. Report sensitivity and false-positive
rates by genome class, repeat class, read technology, and control type, with
denominators and uncertainty. Do not use one aggregate accuracy number to imply
performance on unrepresented satellite classes.

Before evaluating real candidates, predeclare thresholds and review criteria.
Validate read-junction rules with independent extractions/libraries and
orthogonal topology assays. If such truth data are unavailable, report the
pipeline as software-tested on artificial fixtures only, not biologically
validated.

### M11

Use curated, experimentally supported ribozyme sequences and alignments as
positives, split by family or clade to test distant generalization, and
composition/length/complexity-matched non-ribozyme sequences as decoys. Include
known structured RNAs without catalytic activity, shuffled sequences preserving
base composition, and sequence windows with coincidental motif matches.
Benchmark candidate generation, family assignment, and catalytic prediction
separately. Report precision/recall and false positives per searched sequence
or window, family-specific performance, score distributions, and calibration
limits. Compare predictions with experimentally determined structures or
chemical probing where available; do not treat an RNAfold energy or Rfam hit as
ground truth.

For functional validation, use blinded, predeclared cleavage assays with
positive and negative controls, predicted-site product checks, catalytic
mutants, and rescue where appropriate. Separate sequence/structure prediction
benchmarks from biochemical and biological function experiments. Any future
M16-style biological benchmark must be independent of the data used to design
models or choose thresholds.

## 7. Computational, dependency, and data considerations

- M10 sequence statistics and end-repeat comparisons are generally modest
  compute tasks, but read mapping and long-read analysis scale with source-read
  volume. Stream large inputs, cap resource use, and preserve exact reference
  and read digests. Candidate-only repeat checks are not a substitute for
  read-level evidence.
- MFE folding algorithms have steep length-dependent time and memory costs
  (classically cubic time and quadratic space for general secondary-structure
  dynamic programming). Bound sequence/window lengths, expose timeouts, and
  measure practical limits on representative candidates before choosing
  defaults. Ensemble calculations and sampling add further work.
- Infernal's accelerated filters make known-family searches practical, but
  runtime depends on sequence length, model set, and search mode. Prefer
  release-pinned Rfam CMs and targeted `cmscan` use for candidate sequences;
  benchmark any whole-database search or custom CM workflow.
- ViennaRNA and Infernal should be optional external dependencies with explicit
  executable/library versions and failure states. Do not install or integrate
  them as part of this research task. Check the exact release license and
  distribution obligations before bundling executables or libraries. Infernal
  1.1 is reported as GPLv3; current ViennaRNA documentation identifies the
  package as free software and directs commercial-product users to contact the
  authors. Rfam data downloads are CC0, but every future input database and
  bundled component still needs its own license review.
- Freeze reference and model snapshots, including release/date, accession,
  checksums, and license. “Current database” is not a reproducible provenance
  value.

## 8. Unresolved decisions for later approval

1. Resolve the M10/M11 numbering conflict with the current roadmap and confirm
   the ownership of the proposed architecture and RNA-structure evidence.
2. Decide which candidate types M10/M11 accept (RNA, DNA, both; circular,
   linear, segmented, integrated) and what minimum M6 state is required.
3. Decide whether exact raw reads may be re-read for junction analysis, and
   which library metadata, UMI information, and privacy/sample controls are
   required. M6's existing read-back artifact alone is not a substitute.
4. Choose whether CheckV is included as an optional comparative context tool
   and define explicit unsupported-input behavior for small satellites and
   RNA agents.
5. Select repeat and junction algorithms, mapping settings, thresholds,
   duplicate/molecule handling, and accepted orthogonal confirmation criteria
   through class-stratified benchmarks, not intuition or M6 defaults.
6. Choose folding modes, circular-RNA handling, window strategy, and which
   Rfam version/model gathering thresholds are frozen at implementation time.
7. Decide whether custom covariance models or specialized ribozyme pattern
   searches are in scope; establish family-specific held-out validation before
   applying them to candidates.
8. Define typed artifact schemas, evidence status names, resource limits,
   optional-dependency policy, and output retention/reuse rules.
9. Define what level of external biochemical evidence, if any, is required
   before describing a predicted motif as an experimentally supported
   self-cleaving ribozyme. No computational-only label should make that claim.

## 9. Literature and checked DOI references

The supplied starting literature has been retained and its scope clarified.
DOI metadata and article records were checked during preparation; sources below
are primary research unless identified as a review or software/database paper.

1. Bergner LM, Orton RJ, Broos A, et al. **Diversification of mammalian
   deltaviruses by host shifting.** *Proceedings of the National Academy of
   Sciences.* 2021;118(3):e2019907118.
   [doi:10.1073/pnas.2019907118](https://doi.org/10.1073/pnas.2019907118).
   Satellite context and host shifts; not a genome-topology method.
2. Weinberg CE, Weinberg Z, Hammann C. **Novel ribozymes: discovery, catalytic
   mechanisms, and the quest to understand biological function.** *Nucleic
   Acids Research.* 2019;47(18):9480–9494.
   [doi:10.1093/nar/gkz737](https://doi.org/10.1093/nar/gkz737). Review
   recommended by the brief; useful for separating discovery from function.
3. Wu Q, Wang Y, Cao M, et al. **Homology-independent discovery of replicating
   pathogenic circular RNAs by deep sequencing and a new computational
   algorithm.** *Proceedings of the National Academy of Sciences.*
   2012;109(10):3938–3943.
   [doi:10.1073/pnas.1117815109](https://doi.org/10.1073/pnas.1117815109).
   Primary circular-RNA/viroid discovery method; does not make a generic
   assembly-junction call proof of circularity.
4. Bellas CM, Sommaruga R. **Polinton-like viruses are abundant in aquatic
   ecosystems.** *Microbiome.* 2021;9.
   [doi:10.1186/s40168-020-00956-0](https://doi.org/10.1186/s40168-020-00956-0).
   Adjacent viral/mobile-element diversity, not a universal satellite
   architecture template.
5. Nayfach S, Camargo AP, Schulz F, et al. **CheckV assesses the quality and
   completeness of metagenome-assembled viral genomes.** *Nature
   Biotechnology.* 2021;39:578–585.
   [doi:10.1038/s41587-020-00774-7](https://doi.org/10.1038/s41587-020-00774-7).
   Comparative viral-genome quality method; documents repeat-based closure
   signals and their alternatives.
6. Li S, Fan H, An X, Fan H, Jiang H, Chen Y, Tong Y. **Scrutinizing Virus
   Genome Termini by High-Throughput Sequencing.** *PLoS ONE.*
   2014;9(1):e85806.
   [doi:10.1371/journal.pone.0085806](https://doi.org/10.1371/journal.pone.0085806).
   Primary survey of diverse phage genome termini and packaging architectures.
7. Lee BD, Neri U, Roux S, et al. **Mining metatranscriptomes reveals a vast
   world of viroid-like circular RNAs.** *Cell.* 2023;186(3):646–661.e4.
   [doi:10.1016/j.cell.2022.12.039](https://doi.org/10.1016/j.cell.2022.12.039).
   Primary large-scale discovery of viroid-like circular RNAs and candidate
   ribozymes; computational discovery remains distinct from experimental
   function.
8. Perreault J, Weinberg Z, Roth A, et al. **Identification of Hammerhead
   Ribozymes in All Domains of Life Reveals Novel Structural Variations.**
   *PLoS Computational Biology.* 2011;7(5):e1002031.
   [doi:10.1371/journal.pcbi.1002031](https://doi.org/10.1371/journal.pcbi.1002031).
   Primary comparative/computational hammerhead discovery.
9. Nawrocki EP, Eddy SR. **Infernal 1.1: 100-fold faster RNA homology
   searches.** *Bioinformatics.* 2013;29(22):2933–2935.
   [doi:10.1093/bioinformatics/btt509](https://doi.org/10.1093/bioinformatics/btt509).
   CM search methods and software.
10. Ontiveros-Palacios N, Cooke E, Nawrocki EP, et al. **Rfam 15: RNA families
    database in 2025.** *Nucleic Acids Research.* 2025;53(D1):D258–D267.
    [doi:10.1093/nar/gkae1023](https://doi.org/10.1093/nar/gkae1023).
    Database/model release paper.
11. Lorenz R, Bernhart SH, Höner zu Siederdissen C, et al. **ViennaRNA Package
    2.0.** *Algorithms for Molecular Biology.* 2011;6:26.
    [doi:10.1186/1748-7188-6-26](https://doi.org/10.1186/1748-7188-6-26).
    RNA secondary-structure software and methods.
12. Rivas E, Clements J, Eddy SR. **A statistical test for conserved RNA
    structure shows lack of evidence for structure in lncRNAs.** *Nature
    Methods.* 2017;14(1):45–48.
    [doi:10.1038/nmeth.4066](https://doi.org/10.1038/nmeth.4066).
    R-scape covariation testing and the importance of statistical, not visual,
    support for comparative structures.

## 10. Project files reviewed

- `docs/M5_DVG_EVIDENCE.md`
- `docs/M6_RESIDUAL_ASSEMBLY_SUPPORT.md`
- `docs/M1_M6_SCIENTIFIC_AUDIT.md`
- `docs/MODULE_INTERFACES.md`
- `docs/ROADMAP.md` (read only)
- `satellite_discovery/artifact_contracts.py`
- `satellite_discovery/residual_evidence_adapter.py`
- The separate M7, M8/M9, and M10/M11 research briefs in `attached_assets/`

No production source, README, roadmap, active M7 work, tool installation, or
integration was changed for this report.

M10/M11 research status: READY FOR REVIEW