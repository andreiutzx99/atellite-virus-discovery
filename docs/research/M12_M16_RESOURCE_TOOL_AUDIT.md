# M12–M16 resource and tool audit

**Status: planning audit only; reviewed 27 September 2026.** This report
converts the existing milestone research into resource and provisioning
guidance. It does not approve access to source data, select reference-panel
membership, resolve software rights, install tools, or authorize M12–M16
implementation.

The current [roadmap](../ROADMAP.md) governs status: M1–M11 are implemented as
scoped software milestones; M12–M16 remain planned and not implemented. This
audit's M11 resource notes are historical and do not supersede the current M11
contract or implementation documentation. Older local planning snapshots that
describe M10 or M11 as planned are superseded by the roadmap. Historical text
in the M9 contract is also superseded. This audit does not change roadmap
status, authorize access, or select tools.

## 1. M12: what current artifacts can and cannot answer

M12 can begin with an offline, artifact-bounded review. It should not represent
that review as a new source-origin analysis. The current artifacts can document
what was compared, how reads were accounted for, and what remains unknown; they
do not supply the matched controls, technical metadata, or universal reference
coverage needed to attribute origin.

| Evidence or question | Available when the corresponding artifact is retained | Additional input needed for a new or broader assessment | Boundary |
| --- | --- | --- | --- |
| Reference-scoped read accounting | M6 `reference_screen.sam`, `read_triage.csv`, `residual_manifest.json`, and residual/eligible/retained FASTQ artifacts. These describe a declared reference, M6 mapping settings, and that run’s read partition. | Original or approved clean FASTQ if M6 must be rerun against another reference or settings; the matching reference FASTA, role table, QC manifest, and mapper identity. | A residual read means it was not primarily mapped under that M6 comparison, not that it is novel, biological, or absent from other sources. |
| Contig read-back support | M6 `support_alignments.sam`, `read_support.csv` / `.json`, reconstruction evidence, and the associated supported-contig FASTA. | Source FASTQ or validated read artifact, exact contig, and any independent reads/library needed for a genuinely independent check. | M6 read-back reuses reads eligible for assembly. It is not an independent sample or orthogonal assay. |
| Caller-specific DVG junctions | M5 native ViReMa output, normalized `dvg_evidence`, summary, parameters, run status, and provenance when retained. | FASTQ plus the declared reference and exact caller environment to rerun; paired-read input is not supported by the current M5 adapter. | M5 counts and junctions are caller-scoped. Its output is not a per-read alignment table and a completed zero is not a biological non-DVG result. |
| Paired-fragment relationships | M6 records paired-end layout when run with both mates; paired M6 SAM/read artifacts retain run-scoped mate information. | Both mates, or a validated paired alignment with mate/read-group metadata and complete accounting, for new pair-level analysis. | M5 ViReMa integration accepts single-end FASTQ only. Single-end artifacts cannot reconstruct a missing mate. |
| Quality, adapter, and rejected-read review | Existing QC manifest and outputs, if retained, may describe the QC stage and its declared settings. | Original FASTQ and matching QC outputs to reassess pre-QC bases, qualities, adapters, and discarded records. | M6 uses validated clean FASTQ inputs; its residual outputs are not a substitute for original pre-QC reads. |
| Multi-mapping, clipping, and alternative placements | The M6 SAM can be reviewed within its exact reference and mapper settings. | A SAM/BAM/CRAM with the needed secondary/supplementary alignments and tags, or FASTQ plus a newly approved reference/decoy panel and mapper. CRAM may require its exact reference. | M6’s saved SAM is scoped to its own declared reference and configuration; it is not a general all-reference remapping. |
| Read-level mapping from external alignment files | No general M12 interface is currently established. | Validated SAM, BAM, or CRAM; reference identity; read/sample identity; aligner/version/parameters; record and mate accounting; provenance and access approval. | Do not treat an unsupported alignment file or partial accounting as a negative result. |
| Batch, lane, index, library, UMI, and control comparisons | M7 can carry declared sample/run/study identifiers; M6 records its run’s sample label and paired layout. | Authorized, matched sample/control FASTQ or alignments plus study, extraction, library, lane, index/barcode, batch, protocol, and control-role metadata as applicable. | M7 identifiers are declared metadata, not externally verified source or independence. Existing M5/M6 results do not encode a matched negative-control design. |
| Reagent, vector, host, or source attribution | Existing M8 sequence/reference results may be linked as hypotheses; M5/M6 read records may be linked within their scope. | A versioned, role-separated reference/control panel and provenance relevant to the suspected source, often with matched controls or laboratory records. | A sequence match or technical signature alone does not establish contamination or biological origin. |

The implementation evidence is recorded in the current
[M5 contract](../M5_DVG_EVIDENCE.md),
[M6 contract](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md),
[M7 record](../M7_INDEPENDENT_RECURRENCE.md),
[M8 specification](../M8_REFERENCE_AND_HOMOLOGY_SPEC.md), and
[M10 contract](../M10_CONTRACT_FREEZE.md). The current M6 adapter’s persisted
artifact list and paired-read path are visible in
[`residual_evidence_adapter.py`](../../satellite_discovery/residual_evidence_adapter.py);
the M5 caller input and output boundaries are in
[`virema_adapter.py`](../../satellite_discovery/virema_adapter.py) and
[`dvg_evidence.py`](../../satellite_discovery/dvg_evidence.py).

### Useful minimal offline baseline

The following is a useful proposed M12 core even when no raw-read reacquisition
is approved:

1. Validate retained M5/M6 manifests, artifact hashes, declared inputs,
   reference identity, parameters, tool identity, completion state, and read
   accounting.
2. Summarize only the stored M6 per-read/per-fragment partition and read-back
   evidence, and the stored M5 event records. Keep the original stage and run
   identities visible; do not relabel imported artifacts as M12-generated
   observations.
3. Report missing source reads, controls, metadata, reference scope, and
   independent observations as missing/unassessed. Do not turn those gaps into
   clean-control, no-signal, artifact, or rejection findings.
4. Validate the future manifest and evidence-state rules with artificial
   FASTQ/SAM fixtures. Fixtures establish parser, accounting, and reporting
   behavior only.

| M12 planning class | What belongs here |
| --- | --- |
| **CORE** | Offline validation and transparent summary of retained, integrity-verified M5/M6 artifacts; explicit provenance and missingness; deterministic synthetic fixtures. |
| **OPTIONAL** | Linking M7 identifiers, M8 reference hits, M10 sequence descriptors, or other available typed artifacts as context; adding optional SAM/BAM/CRAM readers after a contract and tests exist. |
| **REQUIRES SOURCE DATA** | New or expanded read-origin analysis using original/approved FASTQ, additional SAM/BAM/CRAM, paired mates, controls, batch/library/index metadata, or source-specific reference panels. Access, source terms, privacy, and retention approval are separate gates. |
| **DEFERRED** | Automatic candidate rejection, universal contaminant/source classifier, unsupported source verdicts, and any interpretation that requires unavailable controls or experimental confirmation. |

Unavailable optional inputs should produce a visible unassessed/unavailable
state, not an automatic candidate rejection. A candidate may still be reviewed
using its available evidence; the claim must be limited to that evidence.

## 2. M13 comparator and caller audit

M13 should consume M5 evidence as caller-scoped input by default. The three
other named tools are potential external comparators, not required votes. No
tool was installed or run for this audit. Repository state and documentation
were checked on 27 September 2026; a repository’s publication license is not a
software license.

### ViReMa

- **Current source/version:** the author’s current
  [ViReMa repository](https://github.com/andrewrouth/ViReMa) describes version
  0.33, reports Python 3.7 and Bowtie 0.12.9, and was last pushed 8 April 2026.
  The repository has no formal release or tag at review time. The current
  repository reports MIT terms in
  [`LICENSE.txt`](https://github.com/andrewrouth/ViReMa/blob/main/LICENSE.txt);
  this does not by itself settle the terms of every older snapshot or bundled
  dependency.
- **Inputs and outputs:** its README describes a reference/index and single-read
  FASTQ or FASTA input, with native recombination output. The project’s existing
  [M5 adapter](../../satellite_discovery/virema_adapter.py) is narrower: it
  accepts validated single-end FASTQ plus a declared reference, pins ViReMa
  0.25 source hashes and Bowtie 0.12.9 binary hashes, and normalizes the
  supported native virus–virus junction output. It does not accept M6 SAM/BAM
  as a substitute for reads.
- **Evidence classes:** ViReMa reports caller-specific recombination/junction
  coordinates and orientations. It is not a universal DVG taxonomy. The M5
  adapter interprets virus–virus output only; do not silently equate a junction
  with a deletion, copy-back, snap-back, or interference label.
- **Runtime/platform:** the current README gives a Python 3.7 minimum and
  Bowtie 0.12.9; the project adapter explicitly supports its pinned path only
  on Linux x86-64 and checks NumPy and the exact source/binary identity. Windows
  native operation and Python 3.11/3.12 compatibility of the full caller stack
  are not established by the README.
- **Existing artifacts and recommendation:** import existing M5 output without
  rerunning the tool. **Recommendation: SAFE AS OPTIONAL EXTERNAL TOOL** for
  the already scoped M5 path only. Keep it external and pinned; do not upgrade
  the project pin or redistribute an older source/binary without checking the
  exact snapshot’s terms and each dependency.

### DI-tector

- **Current source/version:** the paper-author
  [repository](https://github.com/Guillaume-Beauclair/Di-tector) currently
  contains only an 11-byte README, with no code, release/tag, or declared
  software license. Its only commit is dated 7 June 2017. The
  [2018 publication](https://doi.org/10.1261/rna.066910.118) describes the
  method; its article license is not a software license.
- **Inputs and outputs:** the paper describes a Python script analyzing
  next-generation sequencing reads and characterizing detected DI genomes.
  Its experimental example used single-end FASTQ. The present repository does
  not provide a verifiable command-line contract, current executable, or
  complete output schema. The paper discusses BWA/SAMtools and BEDTools for
  supporting confirmation, and R packages for its figures; these should not be
  assumed to be a complete or current installation recipe.
- **Evidence classes:** the publication describes deletion/insertion DI
  genomes and copy-back/snap-back (including 5′ and 3′ forms). This is a
  publication-level method description, not current code-level compatibility
  evidence.
- **Runtime/platform:** Python is described, but exact Python and dependency
  versions, supported operating systems, current maintenance, and
  Python 3.11/3.12 compatibility are unresolved. Existing M5 evidence is not a
  DI-tector native input.
- **Recommendation: DEFER.** Reconsider only if a source-authorized,
  versioned executable/source snapshot, terms, dependency recipe, and testable
  I/O contract become available. Software and redistribution terms remain
  unresolved.

### VODKA / VODKA2

- **Current source/version:** the
  [VODKA2 repository](https://github.com/lopezlab-washu/VODKA2) identifies its
  scripts as VODKA2.0 for the associated study. It has no formal release/tag
  and no repository license; the latest source push reported by GitHub was
  5 July 2023. The
  [VODKA2 paper](https://doi.org/10.1261/rna.079747.123) is published under
  CC BY-NC-ND terms, which do not establish code or dependency rights.
- **Inputs and outputs:** the README accepts a list of FASTQ files, a virus
  reference FASTA, and generated Bowtie2 indices; it provides separate
  copy-back and deletion workflows. Its documented requirements are Perl 5,
  Bowtie2 2.4.1 or higher, BLAST 2.11.0 or higher, and R 4.3 or a supplied
  Docker image. The scripts produce VODKA2 workflow outputs/reports; these are
  not M5-native artifacts and the tool requires reads and a declared viral
  reference.
- **Evidence classes:** the repository exposes copy-back (`cbVG`) and deletion
  (`delVG`) workflows. It does not document snap-back as a separate supported
  class. Do not treat any inferred event as evidence of interference.
- **Runtime/platform:** Bash/Perl/R and the listed native tools indicate a
  Linux-oriented execution path. Windows-native support and Python 3.11/3.12
  are not applicable/documented. Exact container digest, source snapshot,
  parameters, and dependency versions must be pinned before any optional
  execution.
- **Recommendation: REQUIRES LICENSE REVIEW.** Keep it out of required CI and
  do not bundle or install it unless software, container, dependency, and
  example-data terms are separately reviewed.

### DVGfinder

- **Current source/version:** the
  [repository’s `v3.1` branch](https://github.com/MJmaolu/DVGfinder/tree/v3.1)
  is the current documented line; GitHub reports its last push as 12 June
  2025. The branch has no corresponding formal release; the repository’s
  latest release/tag is `v2` from 3 November 2021. No repository software
  license is declared. The
  [2022 paper](https://doi.org/10.3390/v14051114) is CC BY 4.0, not a code
  grant.
- **Inputs and outputs:** the README describes a FASTQ sample, viral FASTA, and
  BWA/Bowtie reference indices. Its Conda environment pins Python 3.9.12,
  Perl 5.26.2, Bowtie 1.3.1, BWA 0.7.17, SAMtools 1.15, Biopython 1.79,
  NumPy 1.21.2, and scikit-learn 1.0.1 among other packages. It writes
  `FinalReports` and an HTML report. It does not consume this project’s
  normalized M5 output in lieu of raw reads.
- **Evidence classes and dependence:** the wrapper integrates ViReMa-a 0.23
  and DI-tector 0.6 and applies a gradient-boosting filter. Its outputs are
  dependent on those callers and its training/model resources; it is not a
  third independent caller vote. Its documented scope includes copy-back DVG
  examples, but callers’ supported classes and disagreements must remain
  separately identified.
- **Runtime/platform:** the documented Python 3.9.12 Conda environment and
  Unix-style setup do not establish Python 3.11/3.12 or Windows-native
  support. Linux x86-64 is the plausible optional-provisioning target; it has
  not been tested in this project.
- **Recommendation: REQUIRES LICENSE REVIEW.** Review wrapper, embedded
  caller scripts, model, labeled training data, and all dependencies
  independently. Do not count its ensemble output as independent support or
  include it in required CI.

## 3. Resource licensing, redistribution, and snapshots

“External retrieval preferred” means use a versioned manifest and obtain the
payload only under a separately approved access/terms decision. It is not
permission to retrieve, redistribute, or bundle the resource. No sequence
payload, database, or benchmark set was retrieved in this audit.

| Resource | Purpose and official source | Terms observed / redistribution and bundling posture | Attribution and snapshot strategy | Open question |
| --- | --- | --- | --- | --- |
| ViReMa source | [Current repository](https://github.com/andrewrouth/ViReMa) and [license file](https://github.com/andrewrouth/ViReMa/blob/main/LICENSE.txt). | Current repo states MIT; no formal release. M5’s older 0.25 pin must be checked at its exact source revision. Keep code/binaries external unless exact snapshot and dependencies are approved. | Record commit, source hashes, executable/binary hashes, version, commands, reference and read digests; cite Routh & Johnson. | Does the stated current license cover the exact M5 0.25 source and any provisioned archive? |
| Bowtie 0.12.9 / Bowtie2 | [Bowtie source](https://github.com/BenLangmead/bowtie) and [Bowtie2 source](https://github.com/BenLangmead/bowtie2); versions are tool dependencies, not the caller license. | Review each exact binary/source version and license separately. Do not infer the license of either tool from ViReMa, VODKA2, or DVGfinder. | Pin release/commit and binary digest; record build/runtime, architecture, and exact command. | Which versions and build provenance will a future approved CI job use? |
| BWA, SAMtools, BEDTools, BLAST+, R/Perl and Python packages | Optional caller dependencies documented by the relevant upstream repositories and papers. | Component-specific terms; no aggregate license or redistribution grant. Do not create a combined image before each component and version is reviewed. | Record a software bill of materials, exact versions, source URLs, environment/container digest, and hashes. | Which dependencies are actually required by the selected branch, and are their pinned versions compatible with the chosen platform? |
| DI-tector software | [Author repository](https://github.com/Guillaume-Beauclair/Di-tector), [2018 paper](https://doi.org/10.1261/rna.066910.118). | Current repository exposes no code or license. The article’s CC BY-NC terms cover the article as stated, not a software redistribution right. No bundling or mirror copy. | If source is supplied by its authors, retain explicit release/commit, written terms, hashes, and attribution. | Can authors provide an identifiable version and applicable software license/terms? |
| VODKA2 software, container, and demo files | [Repository](https://github.com/lopezlab-washu/VODKA2), [paper](https://doi.org/10.1261/rna.079747.123), and the container reference linked by its README. | Repository has no license. Paper’s CC BY-NC-ND terms do not license code, image, or demo data. Do not bundle code, container, or test payload absent separate terms. | Freeze source commit, exact container digest, dependency inventory, scripts/configuration, reference/index hashes, and output hashes if approved. | What terms cover the repository scripts, image, and demo files? |
| DVGfinder wrapper, embedded callers, model, and training CSV | [Current branch](https://github.com/MJmaolu/DVGfinder/tree/v3.1), [release list](https://github.com/MJmaolu/DVGfinder/releases), [paper](https://doi.org/10.3390/v14051114). | No repository license is declared. Paper CC BY 4.0 is not a software/data/model license. Review embedded ViReMa-a, DI-tector, model, CSV labels, and packages separately; no bundling. | Pin branch commit (not just branch name), model and training-data hashes, environment lock, dependency terms, and source attribution. | What licenses/terms apply to each embedded component and labeled/model artifact? |
| SRA/ENA/DDBJ read datasets and associated metadata | NCBI SRA / [NCBI data-use policies](https://www.ncbi.nlm.nih.gov/home/about/policies/#data), [ENA](https://www.ebi.ac.uk/ena/browser/), and [DDBJ](https://www.ddbj.nig.ac.jp/index-e.html). | Terms, consent, controlled-access status, privacy, publication restrictions, and redistribution rights are dataset-specific. Public visibility is not blanket approval to republish reads or metadata. | Record accession.version/run IDs, BioProject/study/sample links, source response/file hashes, retrieval time, original submitter/study, filters, access class, and permitted purpose. | Which exact data and metadata may be used, retained, shared, and placed in CI or a benchmark? |
| NCBI nucleotide records, RefSeq/NCBI Datasets, and NCBI Virus | [NCBI molecular-data policy](https://www.ncbi.nlm.nih.gov/home/about/policies/#data), [NCBI Datasets](https://www.ncbi.nlm.nih.gov/datasets/), and [NCBI Virus](https://www.ncbi.nlm.nih.gov/labs/virus/vssi/). | NCBI’s policy distinguishes public-domain U.S.-government material from third-party material. Check each record, submitter, annotation, and linked work. No panel or redistribution approval is made here. | Use accession.version allowlists, release/retrieval date, source response and sequence hashes, taxonomy version, filters, and immutable panel membership. | Are selected third-party records/annotations and derived panels redistributable under their actual terms? |
| INSDC/GenBank/ENA/DDBJ sequence records | [INSDC](https://www.insdc.org/) member databases; use records as accessioned provenance leads rather than a presumed universal reference set. | Provider and record-level terms may differ; inspect source and linked publication. External accession manifests are preferable until exact payload rights are resolved. | Preserve accession.version, record/source hash, retrieval endpoint/date, sequence hash and normalization policy. | What licensing and attribution apply to each selected record and annotation? |
| ICTV taxonomy crosswalk | [Current ICTV Master Species List](https://ictv.global/msl). | ICTV states that its work is CC BY 4.0 unless otherwise noted. This applies to the taxonomy resource, not an underlying sequence or a biological helper claim. | Pin MSL release and file hash; cite ICTV and preserve versioned taxon identifiers. | Are any separately incorporated annotations or figures under different terms? |
| M12 controls, adapters, vectors, and local reagent inventories | Supplier documentation, the specific sequencing-kit version, laboratory records, and authorized local control inventories; example [Illumina adapter documentation](https://support.illumina.com/downloads/illumina-adapter-sequences-document-1000000002694.html). | Vendor, institutional, or confidential terms vary. The Illumina document limits its stated use to Illumina instruments; do not assume general redistribution. Do not bundle private lot/sample metadata. | Store local controlled manifests with curator, purpose, revision/lot, exact sequence hash, source and approval; keep protected material outside the public repository. | Which local controls and vendor-derived sequences may be used and redistributed? |
| M13 comparator records and labels | Published examples, accessioned sequences, source FASTQ, and curation evidence; see the manifest protocol in [validation logistics](M12_M16_VALIDATION_LOGISTICS.md#2-m13-comparator-manifest-and-provenance-logistics). | Each paper, sequence, read dataset, supplementary file, and label has separate terms. A publication license does not automatically clear its data or underlying sequences. | Accession/version or stable source ID, publication/experiment, label evidence and confidence, source and record hashes, curation history, prior tool exposure, rights, and split status. | Which reviewed examples have sufficiently strong truth evidence and terms for the intended use? |
| M14 observational datasets and metadata | Study-linked public sequencing metadata or separately authorized internal cohort tables; no dataset is selected. | Public metadata may be incomplete or restricted; privacy, consent, and source terms apply independently from sequence access. | Preserve source study and sample IDs, metadata version, unit mapping, denominator, detection method, and source terms; minimize sensitive fields. | Are matched samples, controls, denominators, and required metadata accessible for the stated purpose? |
| M15 linked evidence | Existing M5–M14 artifacts and their respective source records; no new reference set is proposed. | Integration does not grant new rights. Preserve source restrictions when displaying, exporting, or sharing linked artifacts. | Link immutable artifact IDs, digests, schemas, original state axes, methods, and source terms; export only fields permitted by every source. | Can a dossier be shared externally without exposing restricted reads, metadata, or reference content? |
| M16 truth sets, holdout, and assay resources | Curated benchmark examples, controlled holdout custody, and claim-specific assay materials; none is selected here. | Per-source sequence/read/data terms, privacy/consent, publication supplements, assay protocols/materials, and institutional approvals must be reviewed. Do not distribute a composite benchmark by default. | Freeze manifest and labels separately; retain source hashes, curator/adjudicator records, access conditions, split ownership, and an audit trail. | Who may curate, hold, execute, unblind, and release each benchmark/assay component? |

## 4. Resources deliberately not selected

- No DVG caller beyond the existing scoped M5 ViReMa path is approved for
  installation, bundling, or required CI.
- No M12 control/reference panel, M13 comparator membership, M14 study cohort,
  or M16 truth/holdout set is selected.
- No statistical package is required for M14’s descriptive offline baseline;
  a future named modeling package needs its own version, license, and
  reproducibility review.
- No database, sequence payload, benchmark dataset, or biological candidate
  data was retrieved or analyzed.

## 5. Sources and local records checked

- [Current roadmap](../ROADMAP.md); [M5](../M5_DVG_EVIDENCE.md),
  [M6](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md), [M7](../M7_INDEPENDENT_RECURRENCE.md),
  [M8](../M8_REFERENCE_AND_HOMOLOGY_SPEC.md), [M9](../M9_CONTRACT_FREEZE.md),
  and [M10](../M10_CONTRACT_FREEZE.md).
- [M12 contract](../M12_CONTRACT_FREEZE.md),
  [M12 implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md),
  [M12 semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md),
  [M13 research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md),
  [M14 research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md),
  [M15 research](M15_EVIDENCE_INTEGRATION_DESIGN_RESEARCH.md),
  [M16 research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md),
  [decision register](M12_M16_DECISION_REGISTER.md), and
  [implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md).
- Upstream repositories, papers, and policy pages linked in the tables above;
  publication availability was not treated as software or data permission.
