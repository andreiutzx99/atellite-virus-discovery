# M8/M9 design research: homology and protein evidence

**Research status: design only.** This report follows the attached M8/M9
research brief. It recommends evidence contracts and validation work; it does
not implement, integrate, or validate a biological classifier. No current
candidate is classified here. A database match or no-match, predicted ORF,
domain/profile hit, or remote-homology result is computational evidence—not
proof of identity, expression, function, helper dependence, novelty, or
contamination.

> **Historical design record:** This report preserves the research scope and
> roadmap discrepancy recorded when it was prepared. The project later adopted
> the M8/M9 ownership shown in the current [roadmap](../ROADMAP.md). This report
> remains a proposal, not an implementation or released interface.

## 1. Scope and current milestone labels

The attached brief assigns **M8** to known-reference/broad homology
classification and **M9** to ORF, protein-profile/HMM, and remote-homology
discovery. The current [roadmap](../ROADMAP.md) assigns different topics:
**M8** is host/read-origin attribution and **M9** is candidate characterization.
This report follows the attached brief as its research scope, records the
numbering discrepancy for later approval, and does not edit the roadmap.

The current checked-in README and roadmap describe M1–M7 as implemented scoped
software stages. M6 provides reference-scoped residual accounting and
technical reconstruction/read-back support; that support uses the reads
associated with assembly and is not independent biological validation. Current
M7 documentation describes exact recurrence over individually supported M6
observations; recurrence is not classification. The attached M7 implementation
brief is a proposed specification, not evidence by itself that a capability
exists. This design uses the currently documented M7 artifacts only as a
prospective input boundary; it does not assume unimplemented behavior from the
attachment.

Current contracts already provide useful engineering precedents: explicit
artifact types, checksummed immutable reference snapshots, per-record source
and accession/version metadata, and explicit execution and failure states.
They do not provide a general homology classifier or protein annotation stage.
The current supplied-reference BLAST adapter is descriptive, uses caller-
supplied references, and does not add biological identity thresholds. These
boundaries should be preserved rather than silently expanding the meaning of
existing M4/M6/M7 outputs.

## 2. Literature findings

### 2.1 Similarity is scoped to method, query, and reference collection

BLAST provides local sequence similarity searches and statistical scores, not a
universal identity rule for naming biological entities [1, 2]. Nucleotide
searches can find close or conserved nucleotide regions, while protein
translation can retain evidence after synonymous substitutions and nucleotide
divergence have obscured direct nucleotide similarity. Protein-search methods
such as DIAMOND and MMseqs2 make large translated searches practical, but their
sensitivity, speed, and reported hits depend on mode, parameters, database
composition, and query length [3, 4].

Profile hidden Markov models (HMMs) represent position-specific family
conservation and can detect relationships too weak for a single-sequence
search. HMMER3 provides an efficient profile-HMM search implementation [5];
Pfam supplies curated family/domain alignments and profiles [6]. InterProScan
combines multiple member databases, and HH-suite supports profile/profile and
remote-homology searches [7–9]. These methods extend the searchable evidence
space; they do not remove the need for alignment coverage, model provenance,
competing-hit review, or false-positive controls. Several signatures returned
by an integrated resource can be correlated because they reuse related
underlying data and should not be counted as independent confirmations.

Sequence databases undersample the virosphere. Metagenomic studies have
repeatedly found viral sequences without recognizable homologues in the
available databases [12]. Consequently, a completed no-hit result only
describes the candidate, tool, parameters, and references actually searched.
It is not evidence that the sequence is novel or absent from nature.

### 2.2 Satellite and virus-like element proteins are not a universal checklist

Satellite RNAs and satellite viruses differ biologically. Many satellite RNAs
are short, do not encode a capsid protein, and rely on a helper virus for one
or more processes; satellite viruses can encode their own capsid protein
while still depending on a helper for other parts of their life cycle [19].
For example, the satellite tobacco necrosis virus genome contains a coat-
protein coding region. An ORF or capsid hit is therefore informative only in
its sequence and reference context; absence of a predicted protein does not
exclude a satellite RNA.

Virophage genomes provide a different, more protein-rich example. The
originally described Sputnik is a satellite virus of a giant virus [13].
Subsequent virophage surveys identify recurring morphogenesis and packaging
proteins, including major/minor capsid proteins, a DNA-packaging ATPase, and
protease, alongside variable replication-related proteins [14, 15]. These
are useful search targets for virophage-like DNA elements, not universal
satellite markers.

Polintons and Polinton-like viruses/transposons show why context and competing
roles matter. Polintons can encode protein-primed family-B DNA polymerase
(pPolB), retrovirus-like integrase, packaging ATPase, protease, and putative
major/minor capsid proteins [16, 17]. Reported Polinton-like virus lineages
can retain parts of this module without every Polinton hallmark [18]. Thus
PolB, integrase, ATPase, or capsid similarity may motivate a mobile-element or
viral-family review, but none alone identifies a satellite or establishes
replication, helper dependence, or function.

## 3. Recommended M8 search design

### 3.1 Separate nucleotide and translated evidence

1. **Nucleotide similarity:** retain BLASTn results against each declared
   reference panel. A fast close-match mode may be useful for screening, with
   a more sensitive nucleotide configuration for divergent or short queries.
   Preserve which mode was used; a single default search is not guaranteed to
   be sensitive to all query lengths or divergence levels.
2. **Translated similarity:** search translated candidate sequence (for
   example, BLASTX or six-frame translations) against protein references when
   coding homology is plausible. TBLASTX may be evaluated for suitable small
   datasets, but is substantially more expensive. If M9 supplies predicted
   ORFs, link protein searches to those ORF hypotheses as a separate evidence
   type. Nucleotide and protein hits must not be conflated.
3. **Scale:** BLAST+ is an understandable baseline; DIAMOND and MMseqs2 are
   candidates for larger local protein panels. Use a more sensitive confirmatory
   search or profile method for borderline candidates only under an approved,
   recorded policy. Do not let a fast prescreen's no-hit silently stand in for
   a completed broader assessment.
4. **Scope:** run role-separated panels and preserve results from all panels.
   A host, microbial, vector, plasmid, mobile-element, or contaminant match is
   an alternative explanation to inspect—not an automatic rejection. A viral
   match is not by itself proof that a sequence is a satellite.

Search output should retain, at minimum, candidate/region ID and sequence hash;
query type; reference-record ID and role; database/snapshot ID; query and
subject coordinates; strand/frame; aligned length; percent identity; query and
subject coverage; gaps/mismatches; bit score and E-value; low-complexity or
masking settings; and the raw hit row. E-values depend on search-space size,
so scores from different panels should not be compared as if they shared one
common scale. Retain all materially competing hits (with a declared output
cap and explicit truncation indicator if a cap is needed), not only one top
hit. Preserve ties and hits from different roles/taxa.

Coverage is essential: a short conserved motif or local domain is not whole-
sequence identity. Conversely, a short candidate may not have enough length
to meet a whole-query coverage threshold even when its similarity is
meaningful. No universal identity, coverage, E-value, or alignment-length
threshold is recommended here. Any later rule must be predeclared and
benchmarked by candidate length, sequence class, database panel, and intended
claim.

### 3.2 Role-aware reference panels

Use immutable, explicitly scoped panels. A single giant database obscures why
a hit was found and makes competing interpretations harder to review.

| Panel role | Candidate sources and contents | Interpretation safeguards |
| --- | --- | --- |
| Known satellites/subviral agents | Curated records with accession/version and source citation; satellite RNAs, satellite viruses, viroids and other relevant subviral records. | Manual curation is required because labels and annotations vary. Retain source wording and uncertainty; do not treat database labels as verified truth. |
| Viruses and candidate helpers | Versioned NCBI RefSeq Viral/NCBI Virus and, if approved, broader GenBank-derived viral records; include relevant segmented genomes and protein records. | Taxonomy and completeness are reference annotations, not proof the candidate is a helper or satellite. Record the exact release and filtering/build recipe. |
| Hosts and organelles | Relevant host genome and transcriptome releases, plus mitochondrial/chloroplast references where appropriate. | A missing host record or tissue-specific transcript does not exclude host origin. Record organism and assembly/transcriptome version. |
| Microbes | Declared bacterial, archaeal, fungal, and other microbial genomes/proteomes relevant to the study. | Taxonomic similarity alone does not establish laboratory contamination; microbial sequences can be genuine sample contents. |
| Vectors, adapters, plasmids, reagents | NCBI UniVec/adapters, declared vector and plasmid collections, and documented reagent/cell-line contaminants where available. | Short adapter/vector matches are not sufficient for source attribution; retain coordinates and read/context evidence separately. |
| Mobile elements | Curated transposon/mobile-element resources such as Dfam where appropriate, and a specific Polinton/PLV collection. | Mobile-element homology can explain protein modules without establishing a virus or satellite. Repbase or other restricted resources require a separate access/redistribution decision. |
| Controls and contamination references | Explicit technical-control sequences and validated, project-relevant contamination panels. | Do not infer a contaminant from a common sequence alone; retain control/sample context and the exact tested panel. |
| Taxonomy mapping | Frozen NCBI Taxonomy and/or ICTV mapping appropriate to each reference release. | Store taxonomy release and record-level mapping. Taxonomy is descriptive context; disagreements remain visible rather than being silently reconciled. |

For every panel, record source URL, retrieval time, source release, accession
versions, sequence/protein file hashes, role/category, taxonomy release,
license/usage terms, retrieval/build procedure, tool and database-build
versions, and records deliberately excluded for benchmark withholding. A
snapshot's checksum proves which bytes were used, not that the panel is
complete, current, correctly labelled, or biologically suitable.

### 3.3 M8 result semantics

Separate **execution/completeness state** from **similarity interpretation**.
Suggested scoped interpretation states are:

| State | Meaning |
| --- | --- |
| `KNOWN/SIMILAR` | A completed, declared search produced one or more matches satisfying a later approved evidence rule. Report this as similarity to named records/regions under the stated method—not as confirmed biological identity. |
| `AMBIGUOUS` | Search evidence is present but does not support a unique, adequately covered, non-conflicting interpretation; examples include short/low-complexity alignments, limited coverage, similarly supported competing roles/taxa, or inconsistent annotations. |
| `NO_MATCH_WITHIN_SEARCHED_REFERENCES` | The relevant declared searches completed with adequate accounting and no hit met the declared reporting rule. This is expressly **not a novelty claim**, not absence from unsearched databases, and not a satellite-negative result. |

Also report execution as `COMPLETE`, `PARTIAL`, `NOT_RUN`, `UNAVAILABLE`,
`FAILED`, or `INTERRUPTED` (or an approved equivalent). A failed database
build, unavailable executable, missing panel, invalid input, interrupted
search, or incomplete query accounting must never generate
`NO_MATCH_WITHIN_SEARCHED_REFERENCES`. If only some panels completed, retain
panel-level results and mark the aggregate partial/unassessed. A successful
search with no hits is different from a failed or unattempted search.

## 4. Recommended M9 protein-evidence design

### 4.1 ORF prediction is a hypothesis-generation layer

Start with transparent six-frame ORF enumeration that retains strand, frame,
coordinates, start/stop positions, translation table, length, overlap
relationships, and ambiguous bases. Do not apply a universal minimum ORF
length that silently removes small viral/satellite proteins. Report alternative
starts and overlapping ORFs where caller methods differ. Circular/boundary-
spanning ORFs should only be evaluated if a separately justified sequence
representation is supplied; do not silently circularize or join contig ends.

Evaluate callers by sequence context rather than treating one as universal:

| Method | Appropriate use to evaluate | Important limit |
| --- | --- | --- |
| Prodigal | Prokaryotic-like genomes and metagenomic contigs; well-established bacterial gene prediction [10]. | Its training and gene model are not universal for RNA viruses, eukaryotic viruses, short satellite genomes, unusual starts, overlapping viral genes, or frameshifts. |
| PHANOTATE | A phage-oriented caller worth benchmarking for compact, overlapping bacteriophage-like genomes [11]. | Phage-specific performance does not imply coverage of eukaryotic viruses, satellite RNAs, or all virophages/Polintons. |
| Six-frame enumeration / simple ORF finder | Transparent baseline and recall-oriented candidate generation for short or unfamiliar sequences. | Produces many chance ORFs; an ORF alone is not evidence of translation or function. |
| Other context-specific callers | Evaluate only when a stated viral class, host, genetic code, and benchmark justify them. | Record the model/training scope and do not extrapolate performance across genome classes. |

ORF boundaries from different callers should remain separate predictions,
not be merged into a consensus protein. A missing ORF is not evidence that a
sequence is noncoding. Candidate contigs may be incomplete, error-prone, or
chimeric; translated annotations inherit those limitations.

### 4.2 Protein similarity, profiles, and remote homology

Recommended staged evaluation, subject to later approval:

1. **Translated similarity:** search predicted proteins and, where useful,
   six-frame translations against frozen protein panels using BLASTp,
   DIAMOND, or MMseqs2. Keep raw alignments, coordinates, identity, coverage,
   score/E-value, database IDs and competing hits. A sequence no-hit remains
   limited to the protein references and sensitivity settings used.
2. **Profile/domain evidence:** use HMMER `hmmscan`/`hmmsearch` against a
   pinned Pfam release and selected, explicitly curated viral/virophage/
   Polinton profiles. InterProScan can provide a broad member-database pass;
   preserve individual signature evidence, release, and member database rather
   than only an aggregated label [5–7]. A profile match supports similarity to
   a modelled family/domain, not complete protein function or biological role.
3. **Remote-homology review:** use HH-suite/HHpred-type profile-profile
   comparison as a bounded second-line review for difficult candidates [8, 9].
   Retain query/template profile versions, alignment span/coverage, probability
   and scores, sequence/secondary-structure evidence, and template provenance.
   Such outputs should remain `REMOTE_HOMOLOGY_CANDIDATE` pending review; a
   remote match probability is not a calibrated probability that a candidate
   has a particular function.
4. **Avoid double counting:** InterProScan member databases may overlap with
   standalone Pfam/HMMER, and DIAMOND/MMseqs2 hits may represent the same
   underlying homologous records. Store evidence provenance and dependencies
   so repeated labels from shared data are not presented as independent
   confirmations.

### 4.3 Hallmarks vary by class

| Protein/feature | Where it can be informative | Why it must not be universal |
| --- | --- | --- |
| Major/minor capsid proteins | Virophage and some virus-like Polinton/PLV morphogenesis modules; capsid protein can also be encoded by a satellite virus such as STNV. | Many satellite RNAs encode no capsid protein and use helper functions; protein families can be highly divergent and structure/profile evidence may be needed. |
| DNA-packaging ATPase | Virophage and some dsDNA virus/Polinton-related packaging modules. | Generic ATPase motifs occur broadly; a short motif or isolated ATPase-like hit is not a viral hallmark diagnosis. |
| Maturation protease | Some virophage/Polinton-like morphogenesis modules. | Proteases are widespread and may be remote or absent from partial/divergent sequences. |
| Primase/helicase | Replication-related proteins in some DNA viruses/virophages and related elements. | These are broad protein families found in many organisms and mobile elements; absence is not exclusionary. |
| Integrase | Mobile-element/Polinton and some related virus contexts. | Strongly compatible with transposon/mobile-element alternatives; not a satellite marker or proof of integration in the sampled host. |
| PolB / pPolB | Polintons and related lineages; protein-primed PolB is a useful contextual clue. | Not required across PLVs or virophages and not expected for RNA satellites; generic PolB similarity needs domain and phylogenetic context. |

Do not require any fixed combination of these proteins for all candidates.
Where a class-specific module is studied, report the observed component
evidence, sequence coverage, family/profile, and missing/unassessed proteins
individually. Module co-occurrence is a descriptive pattern, not proof of
virion production, genome completeness, or helper dependence.

Suggested M9 evidence states include `ORF_PREDICTED`,
`TRANSLATED_SIMILARITY`, `PROFILE_DOMAIN_MATCH`,
`REMOTE_HOMOLOGY_CANDIDATE`, `AMBIGUOUS`,
`NO_MATCH_WITHIN_SEARCHED_PROTEIN_REFERENCES`, plus execution states such as
`UNASSESSED`, `UNAVAILABLE`, `FAILED`, and `PARTIAL`. These are proposed
evidence labels, not a candidate class or functional annotation. “Protein
detected/expressed” requires separate expression/proteomics evidence, which
M9 sequence prediction does not provide.

## 5. False-positive and divergent-sequence limits

### False-positive risks

- Short ORFs arise by chance, especially in short or compositionally biased
  sequences. A short local alignment can look strong while covering little of
  the candidate or reference protein.
- Low complexity, repeats, coiled-coils, transmembrane segments, and biased
  amino-acid composition can produce spurious sequence/profile matches.
  Generic ATPase, polymerase, nuclease, protease, or helicase motifs are not
  taxonomic identities.
- High-throughput searches can create a large multiple-testing burden; an
  E-value and score must be considered with query length, database size,
  coverage, alignment context, and competing matches.
- Viral databases contain uneven taxonomic sampling, old or inconsistent
  annotations, and duplicated records. A top hit can reflect sampling bias
  rather than the closest biological source. Taxonomy inherited from one
  hit is not a classification result.
- A host, microbial, plasmid, reagent, transposon, or Polinton-like sequence
  can encode proteins resembling viral modules. A match alone cannot
  distinguish true sample content from contamination or establish its source.
- Chimeric/incorrect contigs, sequencing errors, frameshifts, pseudogenes,
  translation-table mismatch, and incorrect ORF boundaries can produce
  misleading protein matches.
- Repeated databases/signatures are correlated evidence, not independent
  votes. A single weak hit must not be upgraded by counting repeated copies
  of that same underlying signature.

### Divergence and negative evidence

No single search strategy spans all evolutionary distances. Nucleotide
similarity may disappear before protein-level conservation; protein sequence
similarity can also become undetectable. HMM/profile and structure-assisted
approaches may recover deeper relationships but depend on profile quality,
sampling, alignment span, and model calibration. Convergent folds, biased
composition, and profile drift remain concerns. A candidate may be too short
or incomplete to contain a recognizable hallmark, and noncoding satellite
RNAs may have no protein target for M9 at all.

Accordingly, a no-hit result means only “no qualifying hit was reported in
the named completed searches.” Report database roles/releases and which
searches were not performed. Do not call it novel, unknown-to-science, absent,
nonviral, or non-satellite.

## 6. Licensing, distribution, and reference stewardship

Software licenses and database/data terms are separate. The following
project-facing summary is a packaging precaution, not legal advice; exact
release licenses, bundled dependency terms, platform binaries, and reference
redistribution rights must be rechecked before any implementation or
distribution:

| Resource | Current public terms to verify before use/distribution |
| --- | --- |
| HMMER | Upstream source identifies BSD 3-Clause. |
| Prodigal | Upstream source identifies GPL-3.0. |
| DIAMOND | Upstream source identifies GPL-3.0. |
| MMseqs2 | Upstream source is GPL-licensed; inspect the exact release and dependencies. |
| HH-suite | Upstream source identifies GPL-3.0. |
| InterProScan | InterPro states Apache licensing for InterProScan; included tools and signature collections may have differing terms. Its downloadable InterPro/Pfam/PRINTS/SFLD data are offered under CC0 1.0, with citation/copyright requirements described by EBI. |
| UniProtKB | Copyrightable database content is under CC BY 4.0; preserve attribution and check source-specific exceptions. |
| NCBI/RefSeq/GenBank and third-party records | Follow current NCBI molecular-data usage/disclaimer terms; deposited records may include third-party rights or terms. Do not assume every item is freely redistributable as a bundled database. |

Prefer downloadable snapshot manifests and instructions over bundling large,
frequently updated reference sets. If redistribution is approved, ship only
data whose exact license and provenance allow it, with attribution and
license records intact. Software may be available for a platform while its
database or an included signature component has different terms.

## 7. Computational and operational expectations

Basic ORF enumeration and modest local BLAST searches are relatively
lightweight; large translated searches and repeated profile/remote-homology
passes can become storage-, memory-, CPU-, and time-intensive. InterProScan
and HH-suite database installation/searches are especially unsuitable for
unbounded interactive runs. Requirements depend strongly on sequence count,
panel size, database indexing, tool mode, CPU/thread count, and local storage;
this research does not prescribe a hardware minimum or runtime target.

Before selecting tools, benchmark representative panels and candidate
lengths. Record the actual index/database size, peak memory, wall time, CPU
allocation, I/O, and output volume. Require explicit budgets, bounded process
execution, resumable per-panel jobs, interruption/failure reporting, and
cache invalidation whenever sequence, configuration, tool, database, profile,
taxonomy mapping, or implementation identity changes. Remote web services
may be useful for manual exploration but should not be the sole reproducible
analysis path; rate limits, changing remote databases, data retention, and
network failure must be addressed if considered.

## 8. Proposed M7 → M8 → M9 interfaces

These are design proposals only; they are not current workflow contracts.

### M7 → M8

- Input each candidate sequence as an individual M7-linked record with stable
  observation/candidate/sequence IDs, exact sequence SHA256, sequence length,
  M6 reconstruction state, M7 recurrence members/summary, and source artifact
  references.
- Search each sequence independently. Do not pool reads, merge observations,
  replace members with a consensus, or use recurrence as an identity label.
- Bind every panel result to the exact query bytes and immutable database
  snapshot. Preserve panel-level complete/partial/unavailable/failed status.

### M8 → M9

- Pass the exact candidate sequence and hash, coordinate-linked M8 nucleotide
  and translated hits, reference IDs/roles/taxonomy, competing-hit records,
  search configuration, and execution/missingness states.
- M9 may use M8 hits as context or as a candidate ORF/region selection aid,
  but should not turn M8 failure/no-hit into evidence for or against ORFs.
  Protein annotation should remain possible as an independently scoped
  assessment when M8 is unavailable, with that dependency state disclosed.

### M9 outputs and shared provenance

Proposed immutable outputs include: ORF prediction table and translated
protein FASTA; translated-similarity hits; domain/profile hits; remote-
homology review records; a hallmark-component evidence table; a validation/
missingness summary; and a provenance manifest. Every row should link to
candidate and ORF hashes, coordinates, method/tool/version, parameters,
profile/database snapshot IDs, raw source result, status, and relevant
limitations. The manifest should bind input/output hashes, implementation
identity, exact command/configuration, runtime, and execution state.

Preserve results from M6 technical reconstruction, M7 recurrence, M8
sequence similarity, and M9 predicted protein evidence as distinct
dimensions. Do not produce a single confidence score or automatic
biological class unless separately approved and calibrated on independent
truth sets.

## 9. Recommended tests and benchmarks

### Contract and failure tests

- Exact and near nucleotide matches; reverse-orientation matches; partial,
  short, and low-complexity hits; overlapping and competing hits across
  viral, host, microbial, vector, and mobile-element roles.
- Duplicate accessions/sequence records, version conflicts, missing taxonomy,
  conflicting taxonomy, empty or incomplete panels, and taxonomy snapshot
  changes.
- All requested panels completed with zero qualifying hits versus one missing
  panel, missing executable, failed database build, interrupted search,
  invalid output, or incomplete query accounting. Only the first may yield
  the scoped no-match state.
- ORFs on all strands/frames, alternate starts, short and overlapping ORFs,
  ambiguous bases, nonstandard genetic-code declarations, partial contigs,
  caller disagreement, and changed ORF/profile/database provenance.
- Domain/profile hits with low coverage, low-complexity warnings, repeated
  overlapping signatures, multiple remote templates, and HMMER/InterPro/HH-
  suite failures. Verify that shared underlying signatures are not counted as
  independent evidence.
- Deterministic ordering, retained raw-hit evidence, bounded output caps with
  explicit truncation, invalid/corrupted inputs, output-hash validation, and
  reuse invalidation after any relevant input/tool/database/config change.

### Independent benchmark design

Build separate frozen training/reference and blinded holdout sets. Withhold
whole families or clades (and ideally source studies), not random records from
families represented in the search database; otherwise close homolog leakage
will overstate performance. Include independently supported examples from
satellite RNAs, satellite viruses, helper viruses, virophages, Polintons/
PLVs, host and organelle sequences, bacterial/fungal/other microbial
sequences, vectors/plasmids, and mobile elements. Include documented
contaminants only when the label/source is independently justified.

Use negative and difficult-decoy panels: composition-matched shuffles,
unrelated proteins, short ORFs, common-domain decoys, low-complexity regions,
chimeras, truncated/fragmentary sequences, simulated divergence series, and
representative host/mobile/vector sequences. Synthetic perturbations are
useful for controlled sensitivity tests but are not a substitute for
independently labelled biological examples.

Predeclare search modes and decision rules. Report recall/sensitivity and
false-positive burden by sequence class, length, divergence, coverage, and
reference role, with uncertainty and denominators. Evaluate the rate of
ambiguous outcomes, rank/competing-hit behavior, ORF boundary/overlap
recovery, profile-domain coverage, and whether incomplete assessments are
correctly kept unassessed. Benchmark the no-hit semantics directly. Do not
claim general sensitivity/specificity or choose a novelty threshold from
exploratory candidates.

## 10. Decisions requiring approval before implementation

1. Resolve the mismatch between the attached brief's M8/M9 topics and the
   current roadmap labels. This report does not decide whether roadmap
   numbering or the brief should change.
2. Approve target organism/helper scope and the exact reference-panel roles,
   source releases, taxonomy mapping, update cadence, license review, and
   benchmark-withholding policy.
3. Decide whether M8 requires nucleotide, translated nucleotide, and
   protein searches by default or uses staged optional passes; define how
   partial panel coverage is summarized.
4. Approve an explicit rule for `KNOWN/SIMILAR` versus `AMBIGUOUS`, including
   the level of interpretation (region, ORF, or whole sequence), competing-hit
   behavior, and length-aware thresholds after validation. This report sets
   no thresholds.
5. Select the ORF caller set and genetic-code/context handling for candidate
   classes, including whether six-frame enumeration is a required baseline.
6. Decide which profile databases and custom satellite/virophage/Polinton
   profiles are acceptable; approve database licenses, software distribution,
   and compute budgets before bundling or deployment.
7. Define whether HH-suite/remote-homology evidence is a manual review tool
   or a routine stage, and whether any external service may receive candidate
   sequences.
8. Approve independent truth-label custodians, family/study-level holdouts,
   negative/decoy panels, and acceptance criteria before calibrating any
   later classification or ranking.

## 11. Primary literature and data-resource citations

These papers support methods or biological context; they do not validate
project thresholds, references, or any future candidate classification.
DOIs are linked to their publisher records.

1. Altschul SF, Gish W, Miller W, Myers EW, Lipman DJ. (1990). Basic local
   alignment search tool. *Journal of Molecular Biology*, 215(3), 403–410.
   [doi:10.1016/S0022-2836(05)80360-2](https://doi.org/10.1016/S0022-2836(05)80360-2).
2. Altschul SF, Madden TL, Schäffer AA, Zhang J, Zhang Z, Miller W, Lipman DJ.
   (1997). Gapped BLAST and PSI-BLAST: a new generation of protein database
   search programs. *Nucleic Acids Research*, 25(17), 3389–3402.
   [doi:10.1093/nar/25.17.3389](https://doi.org/10.1093/nar/25.17.3389).
3. Buchfink B, Xie C, Huson DH. (2015). Fast and sensitive protein alignment
   using DIAMOND. *Nature Methods*, 12, 59–60.
   [doi:10.1038/nmeth.3176](https://doi.org/10.1038/nmeth.3176).
4. Steinegger M, Söding J. (2017). MMseqs2 enables sensitive protein sequence
   searching for the analysis of massive data sets. *Nature Biotechnology*,
   35, 1026–1028.
   [doi:10.1038/nbt.3988](https://doi.org/10.1038/nbt.3988).
5. Eddy SR. (2011). Accelerated profile HMM searches. *PLoS Computational
   Biology*, 7(10), e1002195.
   [doi:10.1371/journal.pcbi.1002195](https://doi.org/10.1371/journal.pcbi.1002195).
6. Mistry J, Chuguransky S, Williams L, et al. (2021). Pfam: The protein
   families database in 2021. *Nucleic Acids Research*, 49(D1), D412–D419.
   [doi:10.1093/nar/gkaa913](https://doi.org/10.1093/nar/gkaa913).
7. Jones P, Binns D, Chang HY, et al. (2014). InterProScan 5: genome-scale
   protein function classification. *Bioinformatics*, 30(9), 1236–1240.
   [doi:10.1093/bioinformatics/btu031](https://doi.org/10.1093/bioinformatics/btu031).
8. Söding J. (2005). Protein homology detection by HMM–HMM comparison.
   *Bioinformatics*, 21(7), 951–960.
   [doi:10.1093/bioinformatics/bti125](https://doi.org/10.1093/bioinformatics/bti125).
9. Steinegger M, Meier M, Mirdita M, Vöhringer H, Haunsberger SJ, Söding J.
   (2019). HH-suite3 for fast remote homology detection and deep protein
   annotation. *BMC Bioinformatics*, 20, 473.
   [doi:10.1186/s12859-019-3019-7](https://doi.org/10.1186/s12859-019-3019-7).
10. Hyatt D, Chen GL, LoCascio PF, Land ML, Larimer FW, Hauser LJ. (2010).
    Prodigal: prokaryotic gene recognition and translation initiation site
    identification. *BMC Bioinformatics*, 11, 119.
    [doi:10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119).
11. McNair K, Zhou C, Dinsdale EA, Souza B, Edwards RA. (2019). PHANOTATE:
    a novel approach to gene identification in phage genomes. *Bioinformatics*,
    35(22), 4537–4542.
    [doi:10.1093/bioinformatics/btz265](https://doi.org/10.1093/bioinformatics/btz265).
12. Kristensen DM, Mushegian AR, Dolja VV, Koonin EV. (2010). New dimensions
    of the virus world discovered through metagenomics. *Trends in
    Microbiology*, 18(1), 11–19.
    [doi:10.1016/j.tim.2009.11.003](https://doi.org/10.1016/j.tim.2009.11.003).
13. La Scola B, Desnues C, Pagnier I, et al. (2008). The virophage as a unique
    parasite of the giant mimivirus. *Nature*, 455, 100–104.
    [doi:10.1038/nature07218](https://doi.org/10.1038/nature07218).
14. Fischer MG, Suttle CA. (2011). A virophage at the origin of large DNA
    transposons. *Science*, 332(6026), 231–234.
    [doi:10.1126/science.1199412](https://doi.org/10.1126/science.1199412).
15. Páez-Espino D, Roux S, Chen IMA, et al. (2019). Diversity, evolution, and
    classification of virophages uncovered through global metagenomics.
    *Microbiome*, 7, 157.
    [doi:10.1186/s40168-019-0768-5](https://doi.org/10.1186/s40168-019-0768-5).
16. Kapitonov VV, Jurka J. (2006). Self-synthesizing DNA transposons in
    eukaryotes. *Proceedings of the National Academy of Sciences*, 103(12),
    4540–4545.
    [doi:10.1073/pnas.0600833103](https://doi.org/10.1073/pnas.0600833103).
17. Krupovic M, Bamford DH, Koonin EV. (2014). Conservation of major and
    minor jelly-roll capsid proteins in Polinton (Maverick) transposons
    suggests that they are bona fide viruses. *Biology Direct*, 9, 6.
    [doi:10.1186/1745-6150-9-6](https://doi.org/10.1186/1745-6150-9-6).
18. Yutin N, Shevchenko S, Kapitonov V, Krupovic M, Koonin EV. (2015). A
    novel group of diverse Polinton-like viruses discovered by metagenome
    analysis. *BMC Biology*, 13, 95.
    [doi:10.1186/s12915-015-0207-4](https://doi.org/10.1186/s12915-015-0207-4).
19. Hu CC, Hsu YH, Lin NS. (2009). Satellite RNAs and satellite viruses of
    plants. *Viruses*, 1(3), 1325–1350.
    [doi:10.3390/v1031325](https://doi.org/10.3390/v1031325).
    *(Review used to distinguish satellite RNA and satellite-virus biology.)*

Useful primary resource and licensing pages to recheck at implementation:
[NCBI Virus](https://www.ncbi.nlm.nih.gov/genome/viruses/),
[NCBI data policies](https://www.ncbi.nlm.nih.gov/home/about/policies/),
[UniProt license](https://www.uniprot.org/help/license),
[InterPro license](https://www.ebi.ac.uk/interpro/about/license),
[HMMER license](https://github.com/EddyRivasLab/hmmer/blob/master/LICENSE),
[Prodigal license](https://github.com/hyattpd/Prodigal),
[DIAMOND license](https://github.com/bbuchfink/diamond),
[MMseqs2 license](https://github.com/soedinglab/MMseqs2),
and [HH-suite license](https://github.com/soedinglab/hh-suite).

M8/M9 research status: READY FOR REVIEW