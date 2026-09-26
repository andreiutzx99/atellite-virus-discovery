# M8 Reference-Panel Policy

**Status: READY FOR REVIEW — policy recommendations; M8 software path implemented; snapshot payload rights remain per-snapshot review items.**
Provider pages were checked on 2026-09-26. This policy recommends panel roles,
source products, acquisition routes, and implementation dispositions. It is
not legal advice, a legal clearance, a complete biological catalogue, or
permission to redistribute third-party material. No reference database or
search tool was downloaded for this policy.

M8 remains nucleotide/reference comparison only. Translated and protein
evidence belongs to M9; read-origin and technical-artifact interpretation
belongs to M12. A sequence match is scoped similarity evidence, not identity,
origin, contamination, helper dependence, or function. A no-match is not
novelty. See the [M8 specification](M8_REFERENCE_AND_HOMOLOGY_SPEC.md), the
[benchmark fixture design](M8_BENCHMARK_FIXTURE_DESIGN.md), and the
[milestone roadmap](ROADMAP.md).

## 1. Disposition and redistribution vocabulary

The dispositions below are recommendations for the M8 design/implementation
gate, not authorization to acquire or redistribute a particular third-party
record.

- **APPROVED FOR M8 IMPLEMENTATION** — the role, acquisition pattern, and
  provenance requirements are sufficiently specified to implement support for
  that role. A project still has to select and validate its exact records and
  snapshots.
- **DEFERRED / OPTIONAL** — useful in a declared analysis, but not a default
  panel or a prerequisite for M8. Scope, records, or scientific utility must be
  selected for the analysis.
- **REQUIRES HUMAN REVIEW** — a named curator must approve the proposed
  membership, source terms, and any local or third-party data before that
  material is placed in a panel. Unreviewed content is not an assessed panel.

Redistribution classes are assigned to the source product as recommended here.
They do not replace a record-level review:

- **A — safe/appropriate to redistribute required reference content in the
  repository.** The source states a redistribution license suitable for that
  content, subject to its attribution/share-alike conditions. This is not a
  recommendation to commit a large database.
- **B — retrieve externally at setup/runtime; store only manifest and
  provenance in the repository.** The provider offers an acquisition route and
  does not impose a blanket restriction on the data product, but external
  records or components may carry other terms. Do not bundle or rehost sequence
  data by default. Promote an uncertain component to C.
- **C — redistribution/reuse unclear; human/legal review required.** Do not
  assume that public search, download, or a citation permits reuse or
  redistribution. Keep potentially restricted content out of a shared panel
  until reviewed.
- **D — unsuitable for this pipeline's default panel.** Do not use it as a
  default M8 source. A separately licensed, specifically justified use would
  need a new review.

NCBI states that it places no restrictions on GenBank data and does not accept
records whose submitters requested reuse restrictions, while also noting that
submitters may assert intellectual-property rights in some or all of a record.
ENA's [ENA/INSDC policy](https://www.ebi.ac.uk/ena/browser/about/policies)
states that sequence records have no use restrictions or licensing
requirements attached and that database use/redistribution is unrestricted;
DDBJ likewise states that its public sequence data may be retrieved and
redistributed. These provider policies support external acquisition, but do
not resolve separate publication-supplement rights, local/vendor terms, or
other source-specific exceptions. Therefore NCBI/INSDC records are **B** for
the project’s external-retrieval, manifest-only policy, not blanket permission
to redistribute. Check source notices and record provenance; unclear cases are
**C**. The detailed
[NCBI usage policy](https://www.ncbi.nlm.nih.gov/genbank/about) and
[NCBI website/data policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)
are not legal advice.

## 2. Decision table

| Requested role | Preferred source and exact nucleotide data | Alternative and acquisition route | Version, identifiers, and taxonomy | Class | Approximate scale and disposition |
| --- | --- | --- | --- | --- | --- |
| **1. Satellite/subviral** | Curated accession-version records from INSDC: nucleotide sequences of satellite RNAs, satellite viruses, and other explicitly named subviral agents. Maintain distinct subroles for viroids and deltavirus-like agents. | Primary-paper-linked GenBank/ENA/DDBJ accessions; ICTV MSL for taxonomy only where applicable. Retrieve accession-specific FASTA/flat files with NCBI E-utilities, NCBI Datasets virus packages, or the ENA Browser API. | Pin accession.version, source record version, source response hash, citation, and retrieval query. Preserve original provider taxonomy; pin NCBI Taxonomy and ICTV release separately when used. | **B** for accession records; **A** for ICTV MSL taxonomy; **C** for literature supplements or unclear record terms. | Curated allowlist likely tens to thousands of records, not a complete catalogue. Role framework approved; each membership list requires human review. |
| **2. Virus/helper** | NCBI RefSeq viral nucleotide genome records, using exact GenBank nucleotide accessions in an NCBI Datasets Virus package; sequence data only, not protein products. “Helper” is a curated inclusion rationale. | Additional study-relevant INSDC nucleotide accessions through E-utilities or ENA API. ICTV MSL is a taxonomy crosswalk, not a helper annotation or sequence database. | RefSeq release/build plus accession.version; save package metadata and retrieval query. Preserve NCBI Taxonomy TaxID and snapshot; optionally cross-reference a pinned ICTV MSL release. | **B** for NCBI/INSDC sequences; **A** for ICTV MSL taxonomy. | RefSeq viral scope is on the order of 10⁴ records; broad GenBank-derived selections can be much larger. Core role approved; broad GenBank expansion optional. |
| **3. Host nuclear** | Per-analysis NCBI RefSeq assembly nucleotide FASTA for the host declared by the user; include only selected nuclear assembly components under an explicit haplotype/alternate/decoy policy. | Exact GenBank/INSDC assembly or user-supplied assembly, where justified. Retrieve by assembly accession.version with NCBI Datasets or an archived provider package. | Pin assembly accession.version, component names, annotation release if used, file hashes, declared host taxon, and a dated/hash-pinned NCBI Taxonomy snapshot. | **B** for provider records; **C** for locally supplied or third-party material with unclear terms. | Usually one to a few declared assemblies; bases range from small genomes to multi-gigabase assemblies. Approved as a per-analysis input, never as an all-host default. |
| **4. Host organelle** | Per-analysis mitochondrial, plastid, and other relevant organelle nucleotide records linked to the declared host; keep organelle identity explicit and separate from nuclear FASTA. | Organelle records linked to the selected NCBI RefSeq/GenBank assembly or exact INSDC accessions. Retrieve by accession.version through Datasets, E-utilities, or ENA API. | Record organelle type, host taxon, accession.version, source assembly/accession, sequence hash, and frozen taxonomy provenance. | **B** for provider records; **C** for unclear third-party content. | Typically a small set per host but may include multiple haplotypes/strains. Separate role approved; never silently merge with nuclear records. |
| **5. Bacterial/microbial** | Context-specific subset of NCBI RefSeq bacterial, archaeal, fungal, and other microbial assembly nucleotide FASTAs, selected from declared study/environment/lab context. | A separately declared representative set from NCBI RefSeq; optional GTDB release files for broad microbial context. GTDB taxonomy/metadata is CC BY-SA 4.0; bundled genome-sequence components still need source-level review. | Pin assembly accession.version and NCBI Taxonomy snapshot for RefSeq. For GTDB, pin exact GTDB release and file hashes, GTDB taxonomy identifiers, and any crosswalk release; do not silently replace GTDB names with NCBI labels. | **B** for RefSeq; **A** for GTDB taxonomy/metadata if CC BY-SA terms are met; **C** for GTDB sequence packages pending component review. | Context panels may range from 10² to 10⁴ assemblies; representative scope is smaller; broad all-genome collections can reach 10⁵ or more. Context-specific default approved; representative and broader collections are optional. |
| **6. Vectors** | NCBI UniVec and, if separately justified, UniVec_Core nucleotide sequences. The source product includes vector and cloning-related segments; preserve record labels and sequence provenance. | Accessioned vector records from INSDC or a project-declared vector inventory. Retrieve UniVec from the [NCBI UniVec FTP directory](https://ftp.ncbi.nlm.nih.gov/pub/UniVec/) and pin the exact source file/build. | Record UniVec file/build identity and hash, source IDs/accessions where present, sequence hash, and any NCBI Taxonomy metadata supplied. | **B** for UniVec/provider data; **C** for entries with unclear underlying rights. | Compact compared with genome collections; use the exact pinned file size/count rather than a moving estimate. Role support approved; keep separate from plasmid and adapter roles. |
| **7. Plasmids** | Curated NCBI/INSDC plasmid nucleotide records with plasmid/replicon status and accession.version retained. | User-provided construct or plasmid inventory with revision, owner/source, and sequence hash; search NCBI Nucleotide through E-utilities or a pinned accession list. | Preserve accession.version, record version, source host/taxon where assigned, plasmid/replicon metadata provenance, and taxonomy snapshot. Local construct IDs must be revisioned and stable within the project. | **B** for provider-accessioned records; **C** for local or third-party constructs until rights are reviewed. | Tens to many thousands of records depending on the explicit selection. Role support approved; no universal all-plasmid panel by default. |
| **8. Adapters/reagents/technical contaminants** | Study-specific nucleotide sequences from the exact library-kit/vendor documentation and controlled local reagent, cell-line, synthetic-control, or laboratory inventory. No complete authoritative universal contaminant set is assumed. | Labeled adapter/linker/primer entries in UniVec; exact vendor documentation; user-supplied records with lot/kit/revision and curator approval. | Pin kit and document revision, vendor source, local lot/inventory revision, sequence hash, retrieval time, and inclusion rationale. Taxonomy is generally not applicable; do not invent it. | **C** for vendor/local sequence content pending terms and human review; UniVec components **B** subject to source-record review. | Usually a small, study-specific set, potentially growing to hundreds of sequences. Requires human review; local content is not shared by default. |
| **9. Mobile genetic elements** | Dfam release-specific nucleotide consensus sequences for transposable-element/repeat context; sequence consensuses only, not HMM/profile results. | Explicit INSDC full-length exemplars or a justified organism-specific repeat library with complete provenance. Dfam release files are available from its [release archive](https://www.dfam.org/releases). | Pin exact Dfam release (current release page identifies Dfam 4.0), file names/hashes, family IDs, classification/taxonomy files, and any added accession.version records. | **A** for Dfam data under its published CC0 terms; **B/C** for accessioned additions according to their source terms. | Dfam contains thousands to tens of thousands of family models/consensuses across a broad scope; selected taxa/content should be recorded from the pinned release. Optional role approved; not a universal exclusion screen. |
| **10. Polinton/Polinton-like/virophage-related** | Curator-reviewed INSDC nucleotide accession allowlist linked to primary studies; distinguish Polinton mobile elements, Polinton-like virus reports, and virophages as separate subroles. | Relevant RefSeq Virus records and Dfam consensuses may contribute selected records; ICTV MSL only for groups it formally classifies. None is a complete nucleotide catalogue for this combined role. | Pin accession.version, study citation, inclusion status/rationale, sequence hash, NCBI Taxonomy/ICTV release where applicable, and original curation notes. Preserve “unclassified/uncertain” source labels. | **C** for curated accession/supplement mixtures pending per-record terms; **A** only for Dfam/ICTV components under their own license and attribution rules. | Likely a small, curated allowlist rather than a comprehensive database. Deferred/optional; each new record and source term requires human review. |

“Approximate scale” is a planning order of magnitude, not a promise of provider
counts or completeness. Count actual included records, bases, exclusions, and
bytes from each pinned release at snapshot-build time. No search of a full
provider database is implied by this table.

## 3. Role-specific decisions, acquisition, and limitations

### 3.1 Satellite and subviral references

- **Data and source.** Build a curator-maintained, accession.version allowlist
  of nucleotide records from GenBank/ENA/DDBJ and primary studies. ICTV’s
  [Master Species List](https://ictv.global/msl) supplies virus taxonomy, not
  sequence coverage and not a universal list of satellite agents. Use the MSL
  only where a group is formally represented. Access sequences by exact NCBI
  accession with [E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
  or [NCBI Datasets Virus](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/how-tos/virus/virus-download/);
  ENA also documents [FASTA/flat-file retrieval through its Browser API](https://www.ebi.ac.uk/ena/browser/api/).
- **Practicality and identity.** Accession-level automated retrieval is
  practical; deciding whether a record is a satellite, satellite virus,
  viroid, deltavirus-like agent, or other subviral record is not reliably
  automated from taxonomy alone. Keep the source record’s annotation and a
  separately curated inclusion rationale. Literature-only sequence material
  remains C until its reuse terms are established.
- **Coverage gap.** No consulted source is a comprehensive, maintained
  nucleotide catalogue for all satellite RNAs, satellite viruses, viroids,
  deltavirus-like agents, and other subviral records. ICTV is a virus taxonomy,
  not a complete satellite sequence inventory. RefSeq prioritizes reference
  records and does not promise complete satellite/subviral coverage. INSDC
  contains accessioned records but has variable annotations and uneven
  sampling; some reports are represented chiefly in article supplements.
  Virophages and Polinton-like elements also have overlapping literature and
  mobile-element interpretations, so link to the dedicated role below rather
  than silently treating that panel as complete satellite coverage.
- **Scale and overlap.** Start with a small, reviewed allowlist (tens to
  thousands of records as a planning range); include selected viral records
  in both satellite and virus/helper roles when justified, with a shared
  sequence identity but independent role membership and search result.
- **Disposition.** The role schema, accession-based recipe, and missingness
  behavior are approved for M8 implementation. The initial membership list,
  source notices, and literature additions require human review. An absent
  record is an uncovered area, not evidence against an identity.

### 3.2 Virus and potential-helper references

- **Data and source.** Use RefSeq viral **nucleotide genome records** as a
  reproducible curated core. NCBI Datasets can package virus genomes by taxon
  or GenBank nucleotide accession; use accession.version inputs for exact
  records. For genome assemblies, use an appropriate RefSeq release package.
  Expand with exact GenBank/INSDC accessions only when a study needs additional
  diversity. Do not include protein records or translated products in M8.
- **Identifiers and taxonomy.** Save the RefSeq release/build, Datasets
  package metadata, accession.version, source nucleotide record version,
  retrieval query and timestamp. Preserve the NCBI Taxonomy TaxID and a
  date/hash-pinned [NCBI Taxonomy dump](https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/).
  The ICTV MSL can be a separate virus-taxonomy crosswalk; the current ICTV
  page lists 2025 MSL 41 v1 and states CC BY 4.0. Pin its downloaded file and
  do not use current names to overwrite historical provider annotations.
- **Retrieval and scale.** NCBI Datasets CLI/API and RefSeq release files are
  suitable for scripted acquisition. RefSeq viral records are an order of
  10⁴ collection; a broader GenBank query may be far larger and must be
  explicitly bounded. Update from a named provider release or fixed accession
  allowlist, never from an unrecorded live query.
- **Terms and overlap.** Class B applies to NCBI sequences: the project stores
  manifests/recipes, not bundled FASTA. ICTV taxonomy is class A under its
  stated CC BY 4.0 terms when attribution is retained. Same nucleotide records
  may also be in the satellite/subviral or Polinton-related role, but retain
  the role-specific rationale. “Helper” is a curator’s question/inclusion
  rationale, not a taxonomy-derived property.
- **Limitations and disposition.** RefSeq is curated, not exhaustive; taxonomy
  and host metadata are descriptive. A virus match does not establish
  helper-dependence or candidate identity. The RefSeq core and role separation
  are approved; broader GenBank expansion is optional and needs an explicit
  query, filters, and review.

### 3.3 Host nuclear and 3.4 host organelle references

- **Per-analysis inputs.** M8 is generic: each analysis declares the host
  organism/strain or states `unknown/not supplied`. Select one or more exact
  nuclear assembly accession.versions appropriate to that analysis. Do not
  download every possible host or infer a host from the candidate. If the
  host is unknown or no suitable reference is supplied, record these roles as
  not selected/not assessed rather than a no-match.
- **Separate sequences and roles.** The nuclear panel contains the selected
  nuclear assembly components under a declared primary/alternate/haplotype,
  decoy, and unplaced-contig policy. The organelle panel contains selected
  mitochondrial, plastid, or other relevant organelle records, each explicitly
  typed and linked to the host taxon and, when possible, source assembly.
  Do not silently combine organelles into the nuclear panel or strip their
  identity during normalization. Nuclear insertions of organelle-like sequence
  remain nuclear records if present in the assembly.
- **Acquisition and provenance.** NCBI Datasets downloads by assembly
  accession.version are practical for RefSeq and supported GenBank assemblies;
  exact accession retrieval via E-utilities/ENA is an alternative. Preserve
  provider, assembly, component, annotation release, file hash, TaxID, taxonomy
  snapshot, and any user-declared host rationale. Records from all providers
  remain class B or C as stated in the table.
- **Scope, scale, and limitations.** One or a few assemblies per analysis are
  a reasonable default; a large eukaryotic host may be multi-gigabase. Several
  organelle records may be relevant for a host with multiple haplotypes,
  organelles, or strains. Assembly gaps, alternate haplotypes, tissue-specific
  transcripts, strain variation, and missing host declaration limit coverage.
  A hit supports sequence similarity only; it does not establish host origin.
- **Disposition.** Per-analysis nuclear and separately declared organelle
  inputs are approved for implementation. The user/analysis must choose
  organism, assemblies, and components; no project-wide host panel is selected.

### 3.5 Microbial scope

Use three scopes and record exactly which one is searched:

1. **Context-specific default — approved.** Start with RefSeq bacterial,
   archaeal, fungal, or other microbial assemblies relevant to the declared
   sample, environment, host-associated microbiome, reagent/control inventory,
   or study question. The curation query may combine declared taxa and a
   bounded set of representative assemblies. Retain selection rules and
   source-reason annotations. “Relevant” is a project input, not a biological
   finding.
2. **Curated representative option — optional.** Use RefSeq reference/
   representative assemblies or a release-pinned GTDB representative set.
   This can reduce redundancy and make updates tractable, but underrepresents
   strain diversity and rare taxa. Preserve exact assembly accession.version,
   taxonomy release, and representative-selection rule.
3. **Broader optional scope — deferred.** A much larger RefSeq/GenBank/GTDB
   collection can improve breadth at substantial storage, search-space, update,
   and licensing cost. Do not make an all-microbial search the default. GTDB
   releases are downloadable and identify release files; GTDB publishes
   CC BY-SA 4.0 terms for its data. For genome sequence packages, check
   underlying source record and component terms before sharing or bundling;
   classify uncertain packages C.

NCBI Taxonomy or GTDB taxonomy labels are descriptive provenance and must not
be silently reconciled. RefSeq assemblies and GTDB representatives overlap in
underlying public genome records; shared sequence content can be stored once
with separate source and role metadata, while each declared role remains
independently searchable. Microbial matches do not establish contamination or
sample origin. Report the selected domains, taxa, assembly count, bases, and
known exclusions; a completed panel build does not establish microbial
completeness.

### 3.6 Vectors; 3.7 plasmids

- **Vectors.** UniVec is a nonredundant nucleotide collection for identifying
  vector-origin segments and includes some adapters, linkers, and primers.
  UniVec_Core is a distinct, smaller subset intended to reduce false-positive
  vector hits. Download the exact UniVec/UniVec_Core files from the NCBI FTP
  route, record retrieval timestamp and file hash, and keep the source labels.
  Automated retrieval is practical. Do not collapse vector matches into
  contamination conclusions.
- **Plasmids.** Use a declared accession.version list or a reproducible
  Entrez nucleotide query for plasmid records, with plasmid/replicon metadata
  preserved. A lab’s own construct list is a separate, revisioned,
  curator-reviewed source; it is not a public database. Acquisition is
  practical for fixed accession lists; broad live search results must be
  frozen into membership before use.
- **Overlap.** UniVec may contain vector fragments that also occur in plasmid
  records; the same record or exact sequence can appear in both logical roles.
  Store underlying sequence bytes once if suitable, but record both role
  memberships and independent results. Adapters and cloning primers found in
  UniVec remain adapter/technical roles when that provenance is available.
- **Terms, limits, and disposition.** NCBI’s general use policy is subject to
  source-record terms; class B does not authorize bundling. Local plasmids
  without clear rights are C. The role mechanisms are approved, but each
  inventory/query and any uncertain source record must be reviewed. Plasmid
  or vector similarity alone does not demonstrate laboratory source.

### 3.8 Adapters, reagents, and technical contaminants

- **No universal contaminant reference.** Construct an optional, local panel
  from exact library-kit and instrument revisions, documented reagent/lot
  sequences, cell lines, controls, synthetic constructs, and laboratory
  inventories. Each record needs a curator, source, sequence hash, version or
  lot where available, use scope, approval state, and an explicit license/
  redistribution status. Do not expose confidential supplier, sample, or
  laboratory metadata in a shared manifest.
- **Adapters.** Use adapter sequence documentation for the library kit and
  version actually used. Illumina’s current adapter page says its sequence
  information is for use with Illumina instruments only. This is class C for
  generic redistribution or broader reuse; do not bundle it into a
  repository-wide adapter panel. A lab must confirm that its planned local
  use fits its applicable terms. UniVec is an alternative source for some
  adapters/primers but is not a substitute for kit-specific documentation.
- **Evidence boundary.** A short adapter/reagent match is sequence similarity
  only. M12, not M8, evaluates read context, controls, batch/lane, and
  technical-origin hypotheses. Missing local references mean “not assessed,”
  not a negative result.
- **Disposition.** The optional role and provenance format are defined;
  actual vendor/local sequences require human review before use. Keep local
  data local unless the owner has approved sharing and any applicable terms
  allow it.

### 3.9 Mobile genetic elements

- **Preferred data.** Use nucleotide consensus sequences from an exact Dfam
  release for repeat/mobile-element context. Dfam describes its data as
  CC0, including data and site software; class A applies to Dfam data subject
  to preserving provenance and checking any identified third-party component.
  The current release notes identify Dfam 4.0. Extract/record consensus
  sequence data only for M8; HMM/profile searches and interpretation belong
  to M9.
- **Alternatives and terms.** Add full-length exemplars only from a cited,
  versioned INSDC accession list or an explicitly scoped organism-specific
  library. Those additions are class B/C by source, not covered by Dfam’s
  license. Do not select restricted collections as a default M8 source.
- **Practicality and limits.** Dfam release downloads and version labels are
  available; a nucleotide consensus subset is more practical than a broad
  collection of genome annotations. Family consensuses are models, not a
  complete set of extant elements or observed full-length copies. Taxonomic
  coverage is uneven; prokaryotic mobile elements and endogenous viral
  elements are not comprehensively represented by a single eukaryotic repeat
  resource. A consensus match does not prove integration, mobility, or
  candidate identity.
- **Overlap and disposition.** A Polinton-family consensus may overlap the
  Polinton-related role; retain subrole and Dfam family identity. Dfam-backed
  optional nucleotide context is approved for implementation; broad scope and
  any accession additions remain optional/reviewed. A no-hit cannot rule out
  a mobile element.

### 3.10 Polinton, Polinton-like, and virophage-related references

There is no single authoritative nucleotide source that comprehensively
represents Polintons, Polinton-like viruses/elements, and virophages as one
biological category. Curate a small accession.version list from primary
studies and INSDC, preserving the original author/provider description,
study citation, evidence and curator rationale. Include selected RefSeq Virus
records where they exist; use ICTV only for groups included in a pinned MSL.
Dfam can contribute mobile-element consensuses but does not replace
virus-associated sequence records. Accession retrieval is practical; deciding
which emerging or integrated sequences belong is a scientific curation task.

Keep mobile Polintons, Polinton-like viral reports, virophages, endogenous/
integrated sequences, and unresolved related records as separate subroles.
Their literature, taxonomy, and sequence records overlap but are not
interchangeable. A record may appear in both the mobile-element and
Polinton-related panels with independent inclusion rationales. Underlying
INSDC records are B; literature supplements or any unclear records are C;
Dfam/ICTV components retain their own class and terms. Curated membership is
deferred/optional and requires human review. Small size does not imply
completeness; retain explicit coverage gaps and source dates.

## 4. Shared records and panel separation

Use **role-separated manifests**, not one unlabeled “all references” database.
Separate manifests make scope, rights, inclusion rationale, exclusions, and
no-hit meaning reviewable. Do not duplicate identical sequence bytes merely
because the same source record has two valid roles: a content-addressed record
store may be shared, while role membership, metadata provenance, and
role-specific search outputs remain separate. A physical combined index is
acceptable only if every hit maps losslessly to the exact role membership and
each role’s searched membership and database/search-space identity can be
reconstructed. Otherwise build separate role indexes.

Expected intentional overlaps include:

- virus/helper with satellite/subviral and Polinton/virophage records;
- nuclear and organelle content when the provider assembly combines them
  (the M8 roles must still distinguish them);
- microbial assemblies and plasmids associated with a microbial host;
- UniVec vector segments with plasmid and adapter/reagent sequences; and
- Dfam Polinton-related consensuses with the optional Polinton-related role.

Deduplication may identify equal sequence hashes but must not erase original
records, accession versions, taxonomy, source terms, or panel-role membership.
Do not compare scores across separately sized panel searches as if they were a
common ranking scale.

## 5. Snapshot, acquisition, and update policy

Before search, every selected role must resolve to an immutable local snapshot
or an explicit not-selected/not-applicable state. A live provider query is not
a snapshot. The manifest and content set must contain or reference at least:

- **Snapshot identity:** stable `snapshot_id`; panel role/subrole; manifest
  schema and policy version; creation time (UTC); status; parent snapshot ID;
  and a content-derived whole-snapshot digest.
- **Source and retrieval:** provider/institution, database/product, exact
  release/build, source URL/API/FTP endpoint, UTC retrieval time, exact query,
  accession list and filters, request options, response/file names and hashes,
  citations, and acquisition client/tool version.
- **Record membership:** included, excluded, duplicated, withdrawn, and
  superseded IDs with reasons; provider accession and sequence version (or
  assembly accession.version/local revision); stable local reference ID; exact
  sequence SHA-256 over a declared representation; length, alphabet, molecule
  type, original record/file hash, and source description.
- **Taxonomy and annotation provenance:** taxon ID and name exactly as
  supplied; taxonomy provider and frozen release/date/file hash; any ICTV or
  GTDB crosswalk release and mapping provenance; source metadata and metadata
  hash. Unknown/missing taxonomy remains explicit and is never filled by an
  unrecorded live lookup.
- **Rights:** source-specific license/terms URL and archived text or text hash,
  retrieval date, attribution/citation, source/record-level restrictions,
  redistribution class and decision, reviewer/approval state, and local-only
  restriction where applicable. Unknown/pending is an explicit state, not
  permission.
- **Construction and integrity:** raw source and normalized FASTA/metadata
  hashes; declared normalization and duplicate policy; membership-manifest
  hash; index/build command, builder/parser and tool versions/identities;
  generated index file hashes; validation checks/counts; and whole-snapshot
  checksum over a canonical manifest and deterministically ordered file
  digests. Avoid a self-referential checksum by defining which digest fields
  are excluded from the canonical digest input.

Retain the provider source bytes when terms and storage policy allow. Hash
source files separately from parsed records and normalized FASTA. Do not
silently convert U/T, reverse-complement records, trim bases, relabel taxonomy,
collapse records, or remove duplicate membership. Any normalization or
deduplication must be reversible from the manifest.

Once an analysis uses a snapshot, freeze its membership, source metadata,
taxonomy, license records, FASTA, and index identities for that analysis.
Provider corrections, withdrawals, taxonomy changes, license clarifications,
or refreshes create a **new linked snapshot** with a parent ID, new
whole-snapshot digest, and explicit membership/metadata diff. Never overwrite
or silently update a snapshot used by a past analysis. Reproducible acquisition
means that the exact pinned release/query/accession list and software recipe
can reconstruct or verify the bytes; it does not promise that a provider will
keep a moving endpoint available forever.

## 6. Nucleotide search policy

This policy chooses a reproducible nucleotide-search approach, not biological
cutoffs or a validated classifier.

1. **Local, pinned search.** Implement local BLASTN as the initial transparent
   baseline, with a pinned BLAST+ release and recorded executable identity,
   index/database hashes, exact task/mode, and full parameters. Alternative
   nucleotide aligners require an explicit method identity and comparative
   validation; a remote live service alone is not a reproducible analysis.
2. **Both orientations and fragments.** Search both query/reference
   orientations explicitly and retain strand and original coordinates.
   Preserve local/fragment alignments and HSPs; do not require whole-reference
   or whole-query identity to retain an alignment. Do not rewrite reference
   orientation or candidate bases.
3. **Short queries.** Keep all valid candidates eligible without an arbitrary
   biological minimum length. Use a documented short-query-aware mode, such
   as BLASTN `blastn-short`, when technically appropriate; record mode,
   scoring, word size, masking, and method applicability. Do not assert that
   a hit or no-hit for a very short sequence identifies or excludes a role.
   Method-specific technical applicability rules require software validation
   and review, not biological interpretation.
4. **Low complexity.** Record masking configuration. Where appropriate, keep
   masked and unmasked branches separately, including filtered-hit counts and
   raw outputs. Repetitive/low-complexity hits remain visible but are not
   promoted to a role identity by themselves.
5. **Competing hits and limits.** Retain coordinate-linked alignments from all
   declared roles, including ties, overlapping HSPs, and identical reference
   sequence hashes. Record every output cap; a truncated hit list is not a
   complete competing-hit set. Keep panel-specific scores/statistics with their
   database size and parameters; do not rank across different search spaces as
   one calibrated scale.
6. **No universal threshold.** M8 policy sets no identity, E-value, aligned
   length, or coverage cutoff. Any reporting or summary threshold must be
   method- and use-specific, predeclared, and benchmarked; it cannot be
   presented as a universal biological boundary.
7. **No-hit semantics.** `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`
   is reportable only after successful complete execution and accounting
   against every required, valid, exact declared snapshot and method branch.
   State exact snapshot IDs/hashes, reference membership, method/tool,
   parameters, masking branches, exclusions, and any reporting limits.
   Missing, invalid, incomplete, capped without explicit truncation,
   interrupted, failed, or technically uninformative searches cannot become a
   complete no-hit. A completed no-hit says nothing beyond those references
   and settings; it is not `NOVEL`, `SATELLITE`, `VIRUS`, `NON-HOST`, or
   `NON-MOBILE-ELEMENT`.

M8 remains nucleotide-only. ORF calling, translated search, protein/domain
searches, profile-HMMs, and remote protein homology remain M9. Read-origin,
control, batch, contamination, and technical-source conclusions remain M12.

## 7. Explicit implementation gate and unresolved decisions

### Approved for M8 implementation

- Role-aware immutable manifests and the snapshot fields/update rules in §5.
- Independent role membership and provenance, with shared underlying bytes
  permitted only when role-level membership and search scope remain explicit.
- Per-analysis host nuclear inputs and separately typed organelle inputs.
- NCBI RefSeq viral nucleotide records as the virus/helper core; curated
  accession-based subviral records; RefSeq context-specific microbial records;
  and accession-driven vector/plasmid roles, subject to per-record terms.
- Dfam nucleotide consensus data as an optional mobile-element source under
  its published CC0 terms, while retaining release and family provenance.
- The local-search and no-hit safeguards in §6; no biological thresholds are
  approved.

### Deferred / optional

- A broad GenBank virus/helper expansion, broader microbial databases, GTDB
  sequence packages, Dfam scope beyond selected nucleotide consensus data,
  local contaminant inventories, and Polinton/virophage-specific panels.
- Any automatic panel refresh, provider-wide “complete” collection, or
  repository-bundled external database.
- Any M9 protein/profile search, M12 read-origin assessment, or biological
  candidate classification.

### Requires human review

- Satellite/subviral accession curation and literature supplements, including
  source labels and exact terms.
- Any source or component whose reuse/redistribution status is not explicit;
  adapters under vendor restrictions; local plasmids, reagents, and
  contaminant/control sequences; GTDB genome-sequence components; and
  Polinton/virophage accession mixtures.
- Analysis-specific host, microbial, vector/plasmid, mobile-element, and
  technical-reference membership, including the scientific rationale and
  whether the scope is appropriate.

Before production implementation consumes real reference content, reviewers
must still decide: (1) who curates and approves accession allowlists;
(2) which exact release and host/microbial scopes are initially supported;
(3) record-level terms, attribution, and local-only handling for each selected
content source; (4) which technical-query limitations count as
`INSUFFICIENT_INFORMATION`; (5) tool version, parameters, masks, reporting
limits, runtime/resource budgets, and benchmark-derived summaries; and
(6) who owns blinded holdout and leakage review. These decisions do not change
the adopted M8 nucleotide-only, M9 protein, or M12 read-origin boundaries.

## 8. Provider pages checked

These links document source products, retrieval, release identity, and terms;
they are not legal opinions and must be rechecked for the exact content when
building a real snapshot.

- [NCBI GenBank data usage](https://www.ncbi.nlm.nih.gov/genbank/about) and
  [NCBI website/data policies](https://www.ncbi.nlm.nih.gov/home/about/policies/)
  — NCBI says it imposes no restrictions on GenBank data, while noting that
  submitters may assert rights in some or all of a record.
- [NCBI Datasets: download virus genome data packages](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/how-tos/virus/virus-download/)
  — CLI/API routes by taxon or GenBank nucleotide accession.
- [NCBI Datasets CLI reference](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/command-line/datasets/)
  and [RefSeq release directory](https://ftp.ncbi.nlm.nih.gov/refseq/release/)
  — release and product acquisition context.
- [NCBI Taxonomy FTP](https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/) and
  [Taxonomy database overview](https://www.ncbi.nlm.nih.gov/taxonomy) — dated
  taxonomy dumps and taxon identifiers.
- [ICTV current taxonomy](https://ictv.global/taxonomy) and
  [Master Species List releases](https://ictv.global/msl) — current/released
  taxonomy spreadsheets; the site states CC BY 4.0 unless otherwise noted.
- [ENA Browser API](https://www.ebi.ac.uk/ena/browser/api/) — FASTA, XML, and
  flat-file retrieval by accession. See also
  [ENA/INSDC policies](https://www.ebi.ac.uk/ena/browser/about/policies).
- [DDBJ public sequence data use](https://www.ddbj.nig.ac.jp/data-processing-e.html)
  — describes retrieval and redistribution of public sequence data.
- [GTDB downloads](https://gtdb.ecogenomic.org/downloads) — versioned data
  releases; GTDB states CC BY-SA 4.0 terms.
- [NCBI UniVec](https://www.ncbi.nlm.nih.gov/tools/vecscreen/univec/) and
  [UniVec FTP](https://ftp.ncbi.nlm.nih.gov/pub/UniVec/) — vector screening
  content and download route.
- [Illumina adapter sequence documentation](https://support-docs.illumina.com/SHARE/AdapterSequences/Content/Nextera_Illumina-Sequences.htm)
  and [Illumina adapter information terms](https://support.illumina.com/downloads/illumina-adapter-sequences-document-1000000002694.html)
  — kit documentation and “Illumina instruments only” use statement.
- [Dfam about and license](https://www.dfam.org/about) and
  [Dfam releases](https://www.dfam.org/releases) — nucleotide consensus/
  family resource, release archive, and CC0 statement.

## 9. Validation and scope confirmation

- Documentation links and local anchors checked for this policy and the M8
  specification cross-reference; whitespace checked with `git diff --check`.
- Only this policy and a minimal policy cross-reference in
  `docs/M8_REFERENCE_AND_HOMOLOGY_SPEC.md` were changed.
- No production source or test source changed; M1–M7 and the roadmap were not
  changed.
- No full biological database, reference snapshot, index, or search tool was
  downloaded or installed; no searches were run.
- No M9 work began. M8 software is implemented, but this policy does not
  supply or download reference payloads or indexes and does not clear
  redistribution rights.

M8 reference-panel policy: READY FOR REVIEW