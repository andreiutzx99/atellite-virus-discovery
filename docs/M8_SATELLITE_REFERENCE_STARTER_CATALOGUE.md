# M8 Satellite/Subviral Reference Starter Catalogue

**Status: READY FOR REVIEW — initial reference curator review complete; M8 is not implemented.**
**Curation date: 2026-09-26.**

This document records a small, intentionally incomplete set of accessioned
nucleotide references and related context for future M8 snapshots. It is not
an exhaustive catalogue, a benchmark truth set, a binary classifier, legal
clearance, or evidence that an unknown sequence has any particular identity,
origin, helper dependence, or function. Membership means only that a reviewed
record is included for a named comparison role.

M8 remains nucleotide/reference comparison only. Translated or protein
evidence belongs to M9; read-origin, controls, and technical-artifact
interpretation belong to M12. Matches are similarity evidence scoped to exact
records and methods, not biological assignments. A no-hit cannot establish
novelty or exclude an unrepresented category.

## 1. Scope and curation method

The catalogue keeps separate roles for:

- plant satellite RNAs, satellite viruses, and DNA satellites;
- virus/helper reference context;
- deltavirus-like agents;
- viroids;
- virophages;
- Polinton/Polinton-like and endogenous/proviral elements; and
- other plausible biological or technical explanations that a future
  analysis may select as separate M8 panels.

The first four accessioned plant entries below are approved
`satellite_subviral` members. Deltavirus, viroid, virophage, proviral, and
Polinton-like records are contextual roles, not interchangeable satellite
classes. Helper virus records are separately labelled `virus_helper`.
See the [record-by-record curator review](M8_REFERENCE_CURATOR_REVIEW.md) for
states, evidence scope, source terms, and remaining caveats.

### Metadata verification

On 2026-09-26, accession.version, record title, source database, NCBI Taxonomy
ID/name, and available sequence metadata were checked with NCBI E-utilities
ESummary and Taxonomy ESummary. The per-record links below resolve to NCBI
nucleotide and taxonomy records. Sequence bytes were **not** retrieved,
downloaded, copied, or committed. Therefore this curation does not claim
sequence hashes, independent sequence integrity, experimental pairing of a
particular isolate unless cited, or an immutable taxonomy snapshot.

Where NCBI’s summary did not return a field such as strand state, the gap is
marked rather than silently filled from assumptions. Biological descriptions
such as positive-sense RNA or ssDNA are attributed to the cited literature or
ICTV report when available. NCBI provider names are preserved as returned;
ICTV terminology is a separate cross-reference and is not used to overwrite
historical record titles.

The original curation brief was reviewed alongside the panel policy,
specification, fixture design,
pre-implementation review, and this catalogue. Its role-separation, evidence,
provenance, and no-sequence requirements are reflected here.

## 2. Inclusion and exclusion rules

### Include as a proposed starter member when

1. An exact accession.version resolves to an authoritative sequence record.
2. The record’s current provider name, TaxID (when assigned), sequence type,
   molecule length, topology, and segment identity can be recorded without
   guessing.
3. A primary publication or authoritative taxonomy/database source supports
   the proposed biological role.
4. Helper association and dependence are described at the level actually
   supported, with the relevant experiment or review linked.
5. The sequence source and its redistribution class are explicit; uncertain
   rights remain a review item.

### Exclude from the proposed core, or retain only as context, when

- the record’s title and current taxonomy assignment conflict materially;
- an element may be integrated, proviral, or mobile rather than a freely
  propagating virus;
- a term such as “virophage,” “satellite,” or “Polinton-like” is used
  differently by the current database and literature;
- a source is a literature supplement without record-level terms and
  accession provenance;
- a record lacks an exact version or cannot be tied to a supported role; or
- a source would blur satellite, helper-virus, host, mobile-element, technical,
  or endogenous evidence.

No broad live search query is itself membership. The set is deliberately
small. Absence from this set means “not represented here,” not “not a
satellite,” “not a virus,” or “not present in nature.”

## 3. Approved plant satellite/subviral members

All four records are approved for the initial `satellite_subviral` metadata
panel, with distinct subroles. Record metadata and accession-linked study
provenance were checked against NCBI/INSDC, NCBI Taxonomy, ICTV where
applicable, and primary literature. Approval does not authorize bundling
sequence payloads; the source/terms caveats below and in the curator review
remain binding.

### 3.1 Cucumber mosaic virus satellite RNA — satellite RNA

- **Record:** [NC_002602.2](https://www.ncbi.nlm.nih.gov/nuccore/NC_002602.2),
  NCBI RefSeq title “Cucumber mosaic virus satellite RNA, complete genome”.
- **Current NCBI name / taxonomy:** Cucumber mosaic virus satellite RNA,
  TaxID **12436** ([Taxonomy](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=12436)).
- **Sequence metadata:** 336 nt, RNA, single-stranded, linear, complete.
  One satellite RNA molecule; it is not a numbered CMV genomic segment.
- **Curation rationale:** a small RNA satellite, distinct from satellite
  viruses that encode their own capsid and from DNA satellites.
- **Helper evidence:** Cucumber mosaic virus is the helper in the documented
  CMV satellite-RNA system. Helper dependence is experimentally established
  at the system/class level; the precise CMV isolate paired with this RefSeq
  record is unresolved. See Liao et al. ([PMID 17342261](https://pubmed.ncbi.nlm.nih.gov/17342261/))
  and the plant satellite review
  ([PMC3185516](https://pmc.ncbi.nlm.nih.gov/articles/PMC3185516/)).
- **Source and redistribution:** public NCBI RefSeq record; sequence bytes not
  retrieved. **Class B** under the project policy: manifest/provenance only by
  default; review record-level source terms before distributing sequence.
- **Decision:** approved as an initial satellite-RNA reference. The CMV helper
  relationship is system-level; no exact helper accession/isolate pairing is
  asserted.

### 3.2 Panicum mosaic satellite virus — satellite virus

- **Record:** [NC_003847.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_003847.1),
  NCBI RefSeq title “Panicum mosaic satellite virus, complete genome”.
- **Current NCBI name / taxonomy:** Panicum mosaic satellite virus, TaxID
  **154834** ([Taxonomy](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=154834)).
- **Sequence metadata:** 826 nt, single-stranded RNA, linear, complete; one
  satellite-virus genomic RNA, not segmented.
- **Curation rationale:** a satellite virus with its own capsid-protein coding
  region. It must not be conflated with noncoding satellite RNAs.
- **Helper evidence:** Panicum mosaic virus (PMV; TaxID **40279**) is an
  experimentally established helper for replication and spread. Omarov et al.
  report PMV dependence and the SPMV capsid’s role
  ([PMID 16014937](https://pubmed.ncbi.nlm.nih.gov/16014937/)); Pyle et al.
  report that PMV-encoded RNA polymerase supports replication of its satellite
  agents ([PMID 31455653](https://pubmed.ncbi.nlm.nih.gov/31455653/)).
  The contextual PMV record is
  [NC_002598.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_002598.1), but its
  accession is not asserted to be the experimental helper isolate in every
  cited study.
- **Source and redistribution:** public NCBI RefSeq record; sequence bytes not
  retrieved. **Class B**; manifest/provenance only by default.
- **Decision:** approved as an initial satellite-virus reference. Keep it
  separate from PMV and do not infer that `NC_002598.1` is the isolate used in
  every cited helper experiment.

### 3.3 Satellite tobacco necrosis virus 1 — satellite virus

- **Record:** [V01468.1](https://www.ncbi.nlm.nih.gov/nuccore/V01468.1),
  INSDC/GenBank title “Satellite tobacco necrosis virus 1 genome including
  reading frame for the viral coat protein”.
- **Current NCBI name / taxonomy:** **Albetovirus alphatabaci**, TaxID
  **3426007** ([Taxonomy](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=3426007)).
  The accession title preserves the older Satellite tobacco necrosis virus 1
  name; both are recorded rather than reconciled silently. ICTV's 2025
  Tonesaviridae interim report also identifies V01468 as *Albetovirus
  alphatabaci*.
- **Sequence metadata:** 1,239 nt RNA, linear. The queried NCBI summary did
  not expose strand state or completeness. The ICTV report describes the
  species as a positive-sense ssRNA satellite virus. One genomic RNA; not
  segmented. Do not describe the accession as complete based on the record
  title.
- **Curation rationale:** representative satellite virus with its own coat
  protein coding region.
- **Helper evidence:** ICTV describes dependence on helper viruses in genera
  *Alphanecrovirus* or *Betanecrovirus* (family *Tombusviridae*). This is
  group-level support, not an exact helper accession/isolate pairing. See the
  [ICTV Tonesaviridae report](https://ictv.global/report/chapter/tonesaviridae/tonesaviridae)
  and the plant satellite review
  ([PMC3185516](https://pmc.ncbi.nlm.nih.gov/articles/PMC3185516/)).
- **Source and redistribution:** public INSDC record; sequence bytes not
  retrieved. **Class B**; do not bundle by default.
- **Decision:** approved as an initial satellite-virus reference. Preserve the
  historical accession title and current ICTV/NCBI name separately. Exact
  helper accession/isolate remains unresolved.

### 3.4 Cotton leaf curl Multan betasatellite — DNA satellite

- **Record:** [AJ298903.1](https://www.ncbi.nlm.nih.gov/nuccore/AJ298903.1),
  INSDC/GenBank title “Cotton leaf curl Multan betasatellite c1 gene”.
- **Current NCBI name / taxonomy:** Cotton leaf curl Multan betasatellite,
  TaxID **306025**
  ([Taxonomy](https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id=306025)).
- **Sequence metadata:** 1,349 nt DNA, circular; the NCBI summary did not
  expose strand state. The primary literature describes the DNA-beta class as
  single-stranded DNA. The record is marked complete by NCBI; one circular
  satellite molecule, not segmented.
- **Curation rationale:** a DNA-satellite architecture distinct from RNA
  satellites and satellite viruses.
- **Helper evidence:** trans-replication by Cotton leaf curl Multan virus was
  reported experimentally; additional compatible begomoviruses have also
  been studied. This supports a helper association but does not identify one
  exclusive helper for this record. See
  [PMID 14551819](https://pubmed.ncbi.nlm.nih.gov/14551819/).
- **Source and redistribution:** public INSDC record; sequence bytes not
  retrieved. **Class B**; manifest/provenance only by default.
- **Decision:** approved as an initial DNA-satellite reference. NCBI's
  accession-linked primary paper is PMID 11437658; the record summary reports
  a complete circular molecule. The cited PMID 14551819 remains supporting
  system literature, not the accession's source-study identifier.

## 4. Related comparison roles — not plant satellite members

These records are contextual alternatives, not positive or negative labels.
Their separate roles prevent “related sequence” from being turned into a
single biological class.

| Role | Record and current NCBI taxonomy | Sequence metadata | Supported interpretation and limits |
| --- | --- | --- | --- |
| `delta_related_subviral` | Hepatitis delta virus, [NC_001653.2](https://www.ncbi.nlm.nih.gov/nuccore/NC_001653.2), TaxID **12475** | 1,682 nt circular, non-segmented, single-stranded negative-sense RNA per ICTV | ICTV places genus *Deltavirus* in family *Kolmioviridae*. HBV surface antigen supports envelope/particle formation and transmission; this does not show that HDV RNA replication requires HBV. This remains a distinct deltavirus role, not an ordinary plant satellite class. [ICTV](https://ictv.global/report/chapter/kolmioviridae/kolmioviridae/deltavirus); accession-linked sequence studies [PMID 3627276](https://pubmed.ncbi.nlm.nih.gov/3627276/) and [PMID 2374010](https://pubmed.ncbi.nlm.nih.gov/2374010/). |
| `viroid_context` | Potato spindle tuber viroid, [NC_002030.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_002030.1), TaxID **12892** | 359 nt circular, single-stranded RNA | Viroids are related subviral agents, not satellites; they do not have a helper-virus association. Host replication machinery is not helper-virus dependence. [ICTV Pospiviroid](https://ictv.global/report/chapter/pospiviroidae/pospiviroidae/pospiviroid); accession-linked primary sequence study [PMID 643081](https://pubmed.ncbi.nlm.nih.gov/643081/). |
| `virophage_context` | Sputnik virophage, [NC_011132.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_011132.1), TaxID **543939** | 18,343 bp circular, double-stranded DNA; complete, single genome | The primary study reports growth in a co-infected giant-virus factory, not multiplication in amoebae alone. Helper evidence is system-level. NCBI links this RefSeq record to the paper (PMID 18690211), whose original accession is EU606015.1; sequence equivalence was not checked, so keep the accessions distinct. |
| `virophage_and_proviral_context` | Cafeteriavirus-dependent mavirus, [KU052222.1](https://www.ncbi.nlm.nih.gov/nuccore/KU052222.1), TaxID **1932923** | 40,196 nt DNA; NCBI summary identifies a linear proviral genome class; strand state not returned | This exact accession is a proviral-context record, not a free-virus isolate. Mavirus/CroV system biology is supported by the experimental literature; the accession-linked integration/reactivation study is [PMID 27929021](https://pubmed.ncbi.nlm.nih.gov/27929021/). |
| `polinton_like_virus_context` | Adoxophyes honmai entomopoxvirus “L” virophage 1, [KJ683044.1](https://www.ncbi.nlm.nih.gov/nuccore/KJ683044.1), TaxID **1612310** | 11,449 nt circular DNA; complete record; strand state not returned | The NCBI record title says “virophage.” The 2024 primary paper directly maps KJ683044 to AHEV_PLV1 and analyzes it as a Polinton-like virus ([PMID 39100687](https://pubmed.ncbi.nlm.nih.gov/39100687/)). Preserve both attributed descriptions; this remains contextual, not satellite membership. |

The Polinton/Maverick class includes mobile and virus-like elements with
overlapping evolutionary and architectural features. Some related records are
integrated or endogenous; not every element is an experimentally verified
infectious virus. These are mobile-element or virus-like contextual roles, not
satellite members. Dfam nucleotide consensuses can be considered later under
the separate `mobile_element` role, with a pinned Dfam release and its own
provenance/terms. No Dfam sequence or consensus is included here.

## 5. Helper-virus reference context

Keep helper genomes in `virus_helper`, not in the satellite member list.
Helper status is a reviewed inclusion rationale, not an NCBI taxonomic
property. These accessioned records are useful reference context, but no
particular isolate pairing is inferred unless the cited experiment supports
it.

| Helper context | Accession.version and current NCBI taxon | Sequence / segment metadata | Curation note |
| --- | --- | --- | --- |
| Panicum mosaic virus | [NC_002598.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_002598.1); TaxID **40279**, *Panicum mosaic virus* | 4,326 nt ssRNA, linear, one genomic RNA | Experimentally established helper for SPMV; exact experimental isolate linkage is not assumed. |
| Cucumber mosaic virus RNA 1 | [NC_002034.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_002034.1); TaxID **12305**, `cucumber mosaic cucumovirus` | 3,357 nt ssRNA, linear; segment RNA 1 | Separate segment record; part of a tripartite helper-virus genome. |
| Cucumber mosaic virus RNA 2 | [NC_002035.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_002035.1); TaxID **12305** | 3,050 nt ssRNA, linear; segment RNA 2 | Separate segment record; do not merge with RNA 1 or RNA 3. |
| Cucumber mosaic virus RNA 3 | [NC_001440.1](https://www.ncbi.nlm.nih.gov/nuccore/NC_001440.1); TaxID **12305** | 2,216 nt ssRNA, linear; segment RNA 3 | Separate segment record; all three segments are context, not a claim of an isolate-matched helper for NC_002602.2. |
| Hepatitis B virus, strain ayw | [NC_003977.2](https://www.ncbi.nlm.nih.gov/nuccore/NC_003977.2); TaxID **10407**, Hepatitis B virus | 3,182 nt circular DNA; strand state not returned by the queried summary | Context for HBV surface-antigen provision to HDV; not asserted as the matched helper isolate for NC_001653.2. |

The experimental helper isolate should be chosen from the primary study
provenance rather than substituted by a convenient current genome record.
Exact helper accession/version pairings remain unresolved for STNV,
Sputnik, and the betasatellite. PMV, CMV, and HDV/HBV evidence is preserved at
the system level unless a cited experiment supports a particular pair.

## 6. Taxonomy and name provenance

- The accession.version, provider record title, TaxID, and NCBI current
  organism name are separate recorded values. Names from older publications
  are preserved as source/citation text, not used to overwrite the current
  NCBI record.
- NCBI Taxonomy was checked as a live source on 2026-09-26. No taxonomy
  dump/release was frozen here. Any M8 snapshot must save the exact taxonomy
  source/release and hash, plus any ICTV crosswalk release, separately.
- ICTV taxonomy is applicable only where the taxon is formally covered.
  Satellite nucleic-acid lists in ICTV materials are not comprehensive
  accession catalogues. The current ICTV taxonomy/release page is
  [ictv.global/taxonomy](https://ictv.global/taxonomy); see the current
  [Master Species Lists](https://ictv.global/msl) and the current
  [Deltavirus report chapter](https://ictv.global/report/chapter/kolmioviridae/kolmioviridae/deltavirus).
- NCBI’s virus taxonomy updates can change current names and RefSeq metadata
  while historical record titles remain. Preserve both values and the
  retrieval date.

### Resolved record caveats and source limits

1. **NC_001557.1 is not used as a starter member.** The current NCBI summary
   returned organism `Satellite tobacco mosaic virus` (TaxID 12881) but record
   title “Tobacco necrosis satellite virus, complete genome”. The mismatch is
   material; do not resolve it by guessing which label is intended.
2. **V01468.1 retains historical and current names.** NCBI/INSDC preserves the
   title “Satellite tobacco necrosis virus 1”; current NCBI Taxonomy and the
   ICTV Tonesaviridae interim report use *Albetovirus alphatabaci*. ESummary
   does not report completeness; do not mark it complete by inference.
3. **Sputnik accession relationship is bounded.** NCBI links RefSeq
   NC_011132.1 to the 2008 study (PMID 18690211), which cites EU606015.1.
   Sequence equivalence and isolate identity were not checked.
4. **Mavirus accession KU052222.1 is proviral.** It is approved only as an
   explicitly proviral context record, not as a free-virus reference. The
   integration/reactivation study is PMID 27929021.
5. **KJ683044.1 has two attributed descriptions.** The NCBI record title says
   “virophage”; PMID 39100687 directly maps it to AHEV_PLV1 in a Polinton-like
   virus study. It remains a separate contextual role, not a satellite.
6. **AJ298903.1 source mapping is verified.** NCBI links it to PMID 11437658;
   the older ICTV satellite list gives AJ292769 as a representative and does
   not establish sequence identity with AJ298903.1.
7. **Exact helper isolate pairings are not assigned** for CMV satellite RNA,
   SPMV, STNV, the betasatellite, Sputnik, Mavirus, or HDV/HBV where only
   system-level evidence is established.
8. The initial curation brief is now available and was reviewed. Its evidence,
   role-separation, provenance, and no-sequence requirements are reflected in
   the curator review.

## 7. Coverage and deliberate gaps

Represented satellite architectures are one CMV satellite RNA, one satellite
virus in the Panicum system, one legacy-named satellite virus record, and one
begomovirus-associated circular DNA betasatellite. This is a starter sample,
not a balanced survey.

Not represented in the proposed satellite core include:

- other CMV satellite-RNA variants and other helper-virus satellite RNAs,
  including Umbravirus, nepovirus, tombusvirus, and other plant systems;
- additional DNA satellites, including alphasatellites and diverse
  betasatellite lineages;
- dsRNA satellites and non-plant satellite agents;
- other satellite viruses and their diverse helper systems;
- broader deltavirus diversity and newly reported delta-like agents;
- viroids outside the single PSTVd comparator;
- additional virophages and giant-virus helper groups;
- well-supported standalone Polinton/Polinton-like records, which require
  separate review of mobile, endogenous, and infectious-virus interpretations;
- host nuclear/organelle, microbial, vector/plasmid, adapter/reagent, and
  technical-contaminant references; and
- exact local study isolates, controls, and laboratory inventories.

Those other roles should remain separately selectable under the M8 policy.
Missing references mean “not assessed”; they are not biological negatives.
No broad provider collection or literature supplement was downloaded or
included.

## 8. Provenance, rights, and redistribution

Every entry links to its NCBI nucleotide record, and where applicable its NCBI
Taxonomy record and literature/taxonomy support. Provider metadata is not
proof of label correctness, completeness, current taxonomy in another
authority, or helper dependence.

Under the approved [M8 reference-panel policy](M8_REFERENCE_PANEL_APPROVAL.md),
NCBI/INSDC accession records are **Class B** for this project’s external
retrieval, manifest-only default: store accession.version and provenance,
retrieve exact data only when building an approved snapshot, and do not bundle
sequence data by default. This is not blanket permission to redistribute.
Review record notices, submitter/publication terms, and source-specific
exceptions before use. Literature supplements with unclear terms remain
**Class C** and are not included. ICTV taxonomy is separately published under
CC BY 4.0 per the policy; retain attribution and the exact release if a
crosswalk is used. This catalogue is not legal advice or legal clearance.

The companion
[`M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json`](M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json)
contains identifiers, role metadata, provenance links, helper-evidence
summaries, curator decisions, redistribution classes, and future holdout
fields. It contains **no biological sequence payloads**. Sequence hashes are
null because no sequence bytes were retrieved. Curation states are recorded
separately from the original panel roles.

## 9. Conversion to a future immutable snapshot

This catalogue is not a snapshot. Before any M8 search, a reviewed build
should:

1. Assign a stable snapshot ID, role/subrole, schema and policy version,
   creation time, parent ID, status, and whole-snapshot digest.
2. Retrieve exact accession.version records from a declared provider endpoint;
   save retrieval time, query/options, response/source files, hashes, and
   acquisition tool version. Do not substitute a live search result for a
   frozen membership list.
3. Save every included, excluded, duplicate, withdrawn, or superseded record
   with a reason. Preserve original accession/title/taxonomy and distinct
   role memberships even if identical sequence bytes are content-addressed
   once.
4. Record sequence length, molecule/alphabet, strand/topology/segment identity
   as supplied, exact sequence hash over a declared representation, source
   file/response hash, and any normalization/duplicate policy. Do not silently
   convert U/T, reverse-complement, trim, or merge sequences.
5. Freeze the NCBI Taxonomy and, when used, ICTV release/crosswalk as
   separately hashed metadata inputs. Keep original provider taxonomy and
   later crosswalks distinct.
6. Record the helper-association evidence level, supporting citation,
   curator/rationale, human approval state, redistribution class, exact
   terms/attribution, and local-only restrictions.
7. Validate accession versions, record and sequence hashes, taxonomy
   provenance, role separation, counts, and source-term decisions before
   marking the snapshot usable. Updates create a new linked snapshot; never
   overwrite a snapshot already used in an analysis.

No sequence retrieval, reference snapshot, search index, BLAST installation,
or M8 implementation is part of this curation task.

## 10. Future benchmark holdout fields

The JSON companion leaves holdout assignment and leakage review unassigned.
Future snapshot/benchmark metadata should support at least:

- exact accession.version and exact sequence hash/group;
- close-relative cluster/group ID and the method/evidence used to define it;
- family/clade ID and the taxonomy release used for grouping;
- study ID/DOI/PMID and derivative-supplement provenance;
- panel role, snapshot ID, and source/reference path;
- whether withheld, exclusion reason, curator, independent label custodian,
  approval state, and frozen exclusion-manifest hash; and
- exact/near-duplicate, close-relative, family/clade, and study-level leakage
  audit status.

Freeze the holdout rules before labels are opened. Remove benchmark sequences,
derived duplicates, close relatives, and held-out-study records from every
searchable source and derived index when required. Do not use a future truth
set as an ordinary reference panel. This task assigns no holdouts, computes no
sequence hashes, and runs no benchmark.

## 11. Validation and completion scope

- Both curation files are metadata/documentation only; no sequence payloads
  are present in the JSON.
- Approved accession.version values, NCBI titles, current NCBI organism names,
  TaxIDs, and available sequence metadata were checked against NCBI ESummary
  and Taxonomy ESummary on 2026-09-26.
- Accession-linked PubMed source studies and applicable ICTV/taxonomy support
  were checked and normalized in the new
  [curator review](M8_REFERENCE_CURATOR_REVIEW.md). Remaining helper, source
  equivalence, and rights caveats are explicit.
- JSON parsing, all-14 record counts, role/state/inclusion consistency, study
  IDs, and absence of sequence payloads are validated in the curator review.
- No production source code, tests, roadmap, search tools, full biological
  databases, sequence files, benchmark labels, or reference snapshots were
  changed or added.

M8 starter reference catalogue: READY FOR REVIEW