# M8 Pre-Implementation Consolidation Review

**Historical review outcome (2026-09-26): M8 implementation gate was NOT READY.**
**Current disposition:** see the final-gate reconciliation at the end of this
document. No production M8 search stage, candidate-data search, biological
benchmark, or M9 work was performed.

## Scope and method

The original review compared the eight requested M8 documents: the implementation
architecture, reference-panel approval, reference and homology specification,
benchmark fixture design, BLASTN baseline, starter catalogue Markdown and JSON,
and roadmap. The original starter-curation task brief was also checked; it was
unavailable during the earlier catalogue draft and has since been reviewed in
the record-by-record curator review.

The statements below preserve that review's findings at the time. The
subsequent implementation-gate work added typed handoff/profile helpers and
tests, independently verified BLAST+ `2.17.0+`, and fetched the 14 approved
accession.version records to an external temporary directory for source-term
review and index construction. No candidate data were searched. Curator
catalogue/review files remain unchanged; the accession-pinned snapshot manifest
and hashes are recorded in
[`M8_REFERENCE_SNAPSHOT_MANIFEST.json`](M8_REFERENCE_SNAPSHOT_MANIFEST.json),
while sequence payloads and the database index remain outside the repository.

## Executive decision

At the time of the original review, the scientific boundaries were
substantially consistent: M8 is nucleotide
similarity evidence only; M9 and M12 retain their distinct responsibilities;
short candidates remain eligible; matches are not biological classifications;
and a no-hit is scoped to a completed search of validated references.

The original review found the documents **not sufficiently specified for full
M8 implementation without the implementation agent choosing rules**. The
reconciliation below records which of those technical blockers are now
resolved, and which explicit scope limits remain.

## Cross-document decision table

The requested statuses mean: `READY` is a settled design decision;
`READY_WITH_TECHNICAL_VALIDATION` needs a defined, non-biological software
check; `HUMAN_REVIEW_REQUIRED` needs a named curator or policy decision; and
`BLOCKING_CONFLICT` means documents currently give different names or
contracts for the same implementation surface.

| Issue | Decision at original review | Evidence/source | Historical status | Implementation consequence at that time |
| --- | --- | --- | --- | --- |
| M8/M9/M12 boundaries | M8 reports nucleotide/reference relationships only. M9 owns translated/protein/domain/profile evidence; M12 owns read-origin and technical-artifact interpretation. A match is not identity, origin, function, dependence, contamination, or novelty. | `ROADMAP.md:20-34`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:33-46,439-464`; `M8_BLASTN_BASELINE.md:18-23` | READY | Preserve these boundaries in the stage, artifacts, and reports; never emit a biological role label from a BLASTN match. |
| Candidate eligibility | A valid typed sequence is eligible regardless of M6 read-support promotion; M7 is optional context and cannot upgrade support. No biological minimum sequence length is approved. | `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:48-78,195-229`; `M8_IMPLEMENTATION_ARCHITECTURE.md:112-145`; original curation brief, lines 85-100 | READY | Do not filter candidates by M6 support, M7 recurrence, or an invented length cutoff. |
| M6→M8 identity handoff | The proposed handoff requires candidate and sequence IDs, exact hashes, lengths, molecule type, completeness, and source linkage. The candidate-ID/sequence-ID crosswalk for weak or unsupported contigs is still explicitly open. | `M8_IMPLEMENTATION_ARCHITECTURE.md:112-145,437-445`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:48-78` | READY_WITH_TECHNICAL_VALIDATION | Freeze the producer-declared crosswalk and all-candidate export before building the production stage. Never derive candidate identity from sequence equality. |
| Panel framework vs membership | The role-separated, immutable, provenance- and license-bound snapshot framework is explicit. The policy's “approved for M8 implementation” applies to role support. Exact metadata membership is now reviewed; record-specific terms remain a gate before materialized sequence snapshots. | `M8_REFERENCE_PANEL_APPROVAL.md:18-33,326-402,481-501`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:80-143`; `M8_REFERENCE_CURATOR_REVIEW.md` | HUMAN_REVIEW_REQUIRED | Preserve approved roles and accession versions; do not interpret metadata approval as sequence redistribution permission. |
| Panel-role vocabulary | The specification proposes distinct roles such as `host_nuclear`, `host_organelle`, `vector`, `adapter`, and `plasmid`; the fixture design uses broader names such as `host`, `organelle`, and `vector_plasmid`; the catalogue adds `delta_related_subviral` and `related_non_satellite`. Subroles preserve some distinctions, but there is no single normative enum/mapping. | `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:87-102`; `M8_BENCHMARK_FIXTURE_DESIGN.md:148-153`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:21-35`; catalogue JSON entries | BLOCKING_CONFLICT | Freeze one role vocabulary and explicit aliases/mappings before panel manifests or role-specific result aggregation are implemented. Do not promote contextual records into `satellite_subviral` to resolve naming differences. |
| BLAST+ release and ordinary/short tasks | Local BLASTN is the selected method family. `2.17.0+` is a release recommendation; `blastn` for 50 nt or longer and `blastn-short` below 50 nt is proposed, not fixture-validated. Archive SHA-256 pins are not yet recorded. | `M8_IMPLEMENTATION_ARCHITECTURE.md:219-226`; `M8_BLASTN_BASELINE.md:30-83,97-130,285-301` | READY_WITH_TECHNICAL_VALIDATION | Treat 50 nt strictly as a proposed method selector, never an eligibility or biological threshold. Pin and verify the executable before real searches; test the selector boundary first. |
| Low complexity, scores, reporting limits | The baseline proposes separate masked/unmasked test branches and forbids universal identity, E-value, alignment-length, or coverage thresholds. Exact scoring overrides, E-value/reporting settings, caps, and whether both branches run remain open. | `M8_BLASTN_BASELINE.md:116-145,285-306`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:195-229`; `M8_REFERENCE_PANEL_APPROVAL.md:419-449` | READY_WITH_TECHNICAL_VALIDATION | Select and record exact technical parameters through declared synthetic tests. A reached cap must be explicit truncation, never a complete no-hit. Do not invent a biological cutoff. |
| Evidence fields and competing hits | The baseline proposes stable tabular fields, coordinate-derived query/reference coverage, preservation of raw output, all competing hits, and a deterministic normalized sort. Cross-panel score comparison and “winner” selection are prohibited. | `M8_BLASTN_BASELINE.md:146-176`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:228-270`; `M8_BENCHMARK_FIXTURE_DESIGN.md:68-81` | READY_WITH_TECHNICAL_VALIDATION | Validate parser fields, coordinate conventions, tie handling, output ordering, and truncation on synthetic fixtures. Keep raw rows and panel provenance. |
| Execution-state enums | The specification defines the per-query/panel/method outcomes. The fixture document still contains illustrative `COMPLETE`, `PARTIAL`, `UNAVAILABLE`, `FAILED`, `AMBIGUOUS`, and `KNOWN/SIMILAR` labels and says the final enums need approval. | `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:295-331`; `M8_BENCHMARK_FIXTURE_DESIGN.md:35-38,83-94`; `M8_IMPLEMENTATION_ARCHITECTURE.md:254-277` | BLOCKING_CONFLICT | Use the specification as the normative execution contract and map every fixture alias to it before implementing status serialization. Do not introduce `AMBIGUOUS` or `KNOWN/SIMILAR` as biological classifications without an approved definition. |
| No-hit and failure semantics | `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` is permitted only after valid input/snapshots, successful execution and parsing, and complete accounting. Missing dependencies, invalid/incomplete references, interruption, failure, or truncation cannot become a no-hit. | `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:295-331,351-369`; `M8_IMPLEMENTATION_ARCHITECTURE.md:254-277`; `M8_BLASTN_BASELINE.md:177-205` | READY | Keep the canonical status scoped to declared records and parameters; no-hit is not novelty or a biological negative. Test each failure path. |
| Redistribution and snapshot provenance | NCBI/INSDC records are Class B by default: external acquisition and manifest/provenance in the repository, not blanket permission to rehost data. Exact record/source terms require review. Immutable snapshots need exact membership and source/build identity. | `M8_REFERENCE_PANEL_APPROVAL.md:35-70,326-402`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:104-143`; catalogue Markdown `319-342` | HUMAN_REVIEW_REQUIRED | Approve each chosen record and any local material before snapshot construction or redistribution. Do not infer rights from public availability or Class B. |
| Catalogue and curation brief | The original task brief asks for distinct categories, authoritative provenance, helper-evidence scope, licensing, coverage gaps, and future holdout fields; it does not prescribe a fixed accession roster. The record-by-record curator review documents those decisions and limitations. | `M8_REFERENCE_CURATOR_REVIEW.md`; original task brief `37-82,103-151,184-230` | READY | Keep the brief's role-separation, evidence-scope, and no-sequence requirements in force. |
| Benchmark leakage and biological validation | The design specifies independent label custody, family/clade/study holdouts, exclusion ledgers, and no sensitivity/specificity claims from synthetic fixtures. The starter catalogue has no sequence hashes or assigned holdouts, and leakage review is `NOT_RUN`. | `M8_BENCHMARK_FIXTURE_DESIGN.md:234-283`; catalogue Markdown `377-396`; catalogue JSON top-level fields and each entry's `benchmark_holdout_fields` | HUMAN_REVIEW_REQUIRED | Do not claim biological validation or start the M16 benchmark. This is not a prerequisite for a synthetic software harness; freeze holdout membership before any blinded benchmark. |
| Cache isolation | The architecture identifies that a package-wide implementation identity could invalidate M6/M7 after an M8-only code change; stage-scoped identity and an M8-only reuse test are required. | `M8_IMPLEMENTATION_ARCHITECTURE.md:296-329,455-457` | READY_WITH_TECHNICAL_VALIDATION | Prove M6/M7 reuse after an M8-only panel or code change before claiming isolated M8 cache behavior. |

## Starter catalogue entry audit (pre-curation baseline)

The entry assessments in this section record issues identified before the
initial reference curator review. They are a historical baseline, not current
membership decisions. The report
[`M8_REFERENCE_CURATOR_REVIEW.md`](M8_REFERENCE_CURATOR_REVIEW.md) and current
catalogue JSON supersede its proposed-membership, unresolved-study-ID, and
record-specific role conclusions. The term discussion below is historical;
the final gate later records the limited Class B external-analysis disposition.

The catalogue has 14 entries: four `satellite_subviral` members, five
context records (one deltavirus-related and four other non-satellite related
records), and five helper records. This role separation is the correct
interpretive boundary. The 14 JSON entries retain their original
`human_review_required: true` flags; those flags are not edited by this task.
They reflected the source-term review state before the external snapshot was
built. The final gate permits only accession-pinned external analysis under
Class B; it does not approve bundling, rehosting, or redistribution.

The catalogue reports that accession and taxonomy metadata were checked against
live NCBI ESummary/Taxonomy ESummary on 2026-09-26; no archived taxonomy release
was used. The external snapshot now records the accession-pinned source
organism/TaxID and sequence/source-response hashes. Holdouts remain
`UNASSIGNED`, and leakage checks remain `NOT_RUN`; no biological benchmark was
performed. The phrase “passed required ... checks” in the catalogue completion
section remains document/field validation only, not factual, licensing,
completeness, or holdout approval.

| Issue | Current decision | Evidence/source | Status | Implementation consequence |
| --- | --- | --- | --- | --- |
| CMV satellite RNA — `NC_002602.2` | Proposed plant satellite-RNA member; not a CMV genomic segment. Helper dependence is described at system level, while the exact helper isolate paired to this accession remains unresolved. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:99-119`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:12-69`; source IDs include PMID 17342261. | HUMAN_REVIEW_REQUIRED | Curator must approve this exact representative and preserve the isolate limitation; do not associate it to a particular helper accession without evidence. |
| Panicum mosaic satellite virus — `NC_003847.1` | Proposed satellite-virus member, distinct from the PMV helper. PMV is a documented system-level helper, but the cited experimental isolate is not asserted to be `NC_002598.1`. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:121-143`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:72-131`; PMV helper entry is separately `NC_002598.1`. | HUMAN_REVIEW_REQUIRED | Keep the satellite and helper in separate roles. Confirm the representative and source-term decisions before panel inclusion. |
| Satellite tobacco necrosis virus 1 — `V01468.1` | Proposed satellite-virus member. The historical record title and current NCBI name `Albetovirus alphatabaci` are both retained; the draft does not reconcile the naming difference. Completion is title/summary-based, and the NCBI summary did not return strand state. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:145-168,264-268`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:134-188`; `source_study_ids` is unassigned. | HUMAN_REVIEW_REQUIRED | Curator must approve taxonomy/name presentation and verify that literature-supported biological claims are separated from database fields before freezing the record. |
| Cotton leaf curl Multan betasatellite — `AJ298903.1` | Proposed plant satellite-DNA member. The record title references a “C1 gene,” while the metadata summary calls the record complete and circular; the exact full-unit interpretation and accession/publication mapping need confirmation. Helper evidence is not an exclusive accession pairing. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:170-192,280-283`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:191-247`; PMID 14551819 is listed as a source study. | HUMAN_REVIEW_REQUIRED | Confirm that this exact accession is suitable as a complete satellite representative; do not treat the helper association as proof of one matched isolate. |
| Hepatitis delta virus — `NC_001653.2` | Context-only deltavirus-related record, not a plant satellite member. HBV surface antigen evidence concerns envelopment/transmission, not HDV RNA replication. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:200-203`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:250-308`; source includes PMID 2430299. | HUMAN_REVIEW_REQUIRED | Keep in a separate contextual subrole if selected. Do not infer that HBV supports HDV replication or promote the candidate to satellite status. |
| Potato spindle tuber viroid — `NC_002030.1` | Context-only viroid, not a satellite or helper-virus member. The entry has no benchmark `source_study_ids` despite an ICTV source link. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:200-204`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:311-362`; holdout fields are unassigned. | HUMAN_REVIEW_REQUIRED | Preserve viroid context as a distinct comparison role; add study provenance before any study-level leakage review. |
| Sputnik virophage — `NC_011132.1` | Context-only virophage. The catalogue itself flags a publication association with `EU606015.1` requiring reconciliation against the proposed RefSeq accession; helper/isolate linkage is not established for this record. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:200-205,269-272`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:365-421`; source includes PMID 18690211. | HUMAN_REVIEW_REQUIRED | Confirm accession-to-publication identity and keep the helper relationship scoped to the supported experimental system. |
| Mavirus proviral record — `KU052222.1` | Context-only proviral sequence. The entry does not establish that this accession is a free-virus/propagated isolate or resolve its integration boundaries. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:200-205,273-275`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:424-482`; source includes DOI 10.1126/science.1199412. | HUMAN_REVIEW_REQUIRED | Retain the proviral qualifier; do not use it as an ordinary free-virus member without curator evidence for the exact record. |
| Entomopoxvirus-associated record — `KJ683044.1` | Context-only record with an unresolved category label: the record is described as virophage-associated while later literature discusses Polinton-like viruses. Helper status is unresolved; `source_study_ids` is empty despite literature links. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:200-206,276-279`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:485-540`. | HUMAN_REVIEW_REQUIRED | Curator must resolve its contextual subrole and record the study IDs before panel or benchmark use. Do not label it a satellite. |
| Panicum mosaic virus helper — `NC_002598.1` | Helper-context entry, not a satellite member. PMV is established as a helper for SPMV, but this exact RefSeq accession is not claimed to be the isolate used in every cited experiment. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:224-227`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:543-595`; sources include PMIDs 16014937 and 31455653. | HUMAN_REVIEW_REQUIRED | Keep the helper record separate and preserve the accession/isolate caveat. |
| CMV helper RNA 1 — `NC_002034.1` | One segment of a tripartite CMV helper genome, not a complete helper genome by itself. Exact isolate pairing with `NC_002602.2` is unresolved. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:224-229`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:598-646`; source study PMID 7503683. | HUMAN_REVIEW_REQUIRED | Store and search it as a separately provenanced segment; do not merge it with RNAs 2/3 or imply matched-isolate evidence. |
| CMV helper RNA 2 — `NC_002035.1` | Separate CMV helper segment; same system-level evidence and unresolved exact isolate pairing as RNA 1. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:224-229`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:649-697`; source study PMID 7503683. | HUMAN_REVIEW_REQUIRED | Preserve the accession and segment identity as its own record and panel evidence. |
| CMV helper RNA 3 — `NC_001440.1` | Separate CMV helper segment; same system-level evidence and unresolved exact isolate pairing as RNAs 1/2. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:224-229`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:700-748`; source study PMID 7503683. | HUMAN_REVIEW_REQUIRED | Preserve the accession and segment identity as its own record and panel evidence. |
| HBV helper context — `NC_003977.2` | Context for HDV particle envelopment, not a claim that HBV enables HDV RNA replication or is the matched strain for `NC_001653.2`. `source_study_ids` is empty despite an ICTV evidence link. | `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.md:224-230`; `M8_SATELLITE_REFERENCE_STARTER_CATALOGUE.json:751-799`; taxonomy/source terms and strain relevance remain review notes. | HUMAN_REVIEW_REQUIRED | Retain only as a separately identified helper-context record after review; add study provenance before benchmark leakage review. |

### Catalogue-wide disposition at the time of this review

- The first four entries are the only satellite/subviral starter
  members. The five contextual records and five helper records must remain
  separate; their relationship to satellites is not a candidate role.
- All 14 entries are Class B. Under the panel policy this means external
  retrieval and manifest/provenance-only in the repository by default. It is
  not a license grant or permission to bundle/rehost any particular sequence.
- The catalogue is metadata-only. It cannot yet verify exact sequence identity,
  duplicates/near-relatives, sequence completeness, or a stable taxonomy
  snapshot because sequence hashes and archived taxonomy releases are absent.
- `source_study_ids` is empty for `V01468.1`, `NC_002030.1`, `KJ683044.1`, and
  `NC_003977.2`; source URLs alone do not provide the normalized study key
  needed by the proposed study-level leakage ledger.
- No record is benchmark-ready: holdout assignments are unassigned and leakage
  review has not run. This blocks a future blinded biological benchmark, not
  synthetic parser testing.

## Post-curation update (2026-09-26)

The record-by-record review approves four `APPROVED_INITIAL_REFERENCE`
satellite/subviral members and ten `APPROVED_CONTEXT_REFERENCE` records in
their existing contextual or helper roles. All 14 are included in the initial
metadata panel definition; this does not classify future candidates or approve
sequence bundling. Accession-linked `source_study_ids` have been normalized
only where verified, replacing the earlier empty/unassigned values in the
historical audit above.

The membership portion of blocking decision 4 below is resolved. Record- and
source-specific terms still require review before any materialized sequence
snapshot or redistribution. The overall M8 implementation gate remains NOT
READY for the independent candidate-handoff, role-vocabulary, and BLASTN
technical decisions listed above.

## BLASTN baseline classification at original review

| Classification | Decisions | Evidence/source | Status | Implementation consequence |
| --- | --- | --- | --- | --- |
| A. Justified and ready to freeze | Local nucleotide-only similarity evidence; `-strand both`; raw and normalized evidence linked by hashes; preserve all competing hits; no biological winner; canonical scoped no-hit and distinct execution failures. | `M8_BLASTN_BASELINE.md:146-205`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:228-270,295-369` | READY | These are normative boundaries for future work. |
| B. Technical defaults that can be selected as a starting profile | NCBI task profiles document word size 11 for `blastn`, 7 for `blastn-short`, and gap-open/extend 5/2; a proposed 50-nt task selector uses `blastn-short` below 50 nt. | NCBI manual cited in `M8_BLASTN_BASELINE.md:308-321`; proposed selector and task values `:97-130` | READY_WITH_TECHNICAL_VALIDATION | Record effective release-specific defaults and verify with boundary fixtures before freezing the executable profile. This is not a minimum candidate length. |
| C. Settings requiring empirical software validation | SHA-256 archive pins and runner compatibility; 49/50/51-nt selector behavior; DUST branches; exact scoring overrides and E-value/reporting settings; target/HSP caps; resource and thread limits; deterministic raw/normalized ordering; index validation; insufficient-information rules. | `M8_BLASTN_BASELINE.md:30-83,116-145,206-306`; `M8_BENCHMARK_FIXTURE_DESIGN.md:25-72` | READY_WITH_TECHNICAL_VALIDATION | Do not let an implementation agent inherit undocumented BLAST defaults. Validate using fixed artificial panels only before real-panel searches. |
| D. Biological thresholds/rules that must not be invented | No universal minimum length, identity, E-value, alignment-length, coverage, novelty, helper-dependence, or candidate-role threshold is approved. | `M8_REFERENCE_PANEL_APPROVAL.md:419-449`; `M8_REFERENCE_AND_HOMOLOGY_SPEC.md:195-229`; `M8_BLASTN_BASELINE.md:139-145` | READY | Preserve quantitative evidence and uncertainty. Do not convert technical reporting settings into biological classification rules. |

## Blocking decisions at original review (preserved)

The following decisions genuinely blocked the full production M8 stage at the
time of the original consolidation review:

1. **Freeze the candidate identity/handoff contract.** Approve the producer-
   declared candidate-ID/sequence-ID crosswalk and all-candidate M6 export,
   including how absent or failed upstream sequence bytes remain visible.
2. **Normalize the contracts before schema implementation.** Approve one
   panel-role vocabulary and map fixture roles and fixture state labels to the
   normative specification. Define any summary-state label separately; do not
   add biological `AMBIGUOUS`/`KNOWN` classes by inference.
3. **Approve and validate the real BLASTN profile.** Pin the exact executable
   and per-platform digests; select the task/masking branches, effective
   scoring and reporting settings, caps, resource policy, and determinism
   contract; then validate those choices on synthetic fixtures. Keep every
   valid short query and do not add biological thresholds.
4. **Confirm exact record/source terms before a materialized panel snapshot.**
    Metadata membership and separate roles are approved in
    `M8_REFERENCE_CURATOR_REVIEW.md`; record-level attribution, source terms,
    and redistribution treatment still require review before retrieving or
    rehosting sequence payloads. No sequence snapshot is approved here.

The scientific scope, no-hit semantics, no-minimum-length rule, competing-hit
preservation, and M9/M12 boundaries are otherwise sufficiently clear. The
holdout and leakage work remains a gate for future M16 biological benchmarking,
not a reason to invent or run a benchmark in this task.

**Historical decision:** M8 implementation gate was NOT READY at the time of
the original consolidation review.

## Final M8 gate reconciliation (2026-09-26)

| Original blocker | Current disposition | Evidence |
| --- | --- | --- |
| Candidate identity and all-contig M6 handoff | CLOSED | Typed candidate-set validation binds sequence IDs, exact FASTA hashes/lengths, IUPAC alphabet, source assembly, completed assembly manifest/count, and M6 reconstruction evidence. M7 context is a separate optional typed input. |
| One role vocabulary and software status contract | CLOSED | Normative role/status enums and fixture aliases are implemented and tested. The approved `KU052222.1` label maps specifically to proviral context; ambiguous generic labels remain rejected. |
| BLAST+ release, profile, caps, masking, and method applicability | CLOSED for Linux x86-64 | Archive and binaries are hash-pinned; synthetic tests cover short/ordinary task boundary, both DUST branches, deterministic raw output, coordinates, and target/HSP cap truncation. A query shorter than the selected word size receives `INSUFFICIENT_INFORMATION`, not a no-hit. |
| Supported platform/runtime policy | CLOSED by explicit limitation | Linux x86-64 with the exact `2.17.0+` pair is the only supported runtime. Windows and other platforms map to typed `DEPENDENCY_UNAVAILABLE`; no fallback is permitted. |
| Approved panel snapshot and source terms | CLOSED for external Class B analysis only | The 14-record accession-pinned snapshot and BLASTDB v5 index were verified and are documented in `M8_REFERENCE_SNAPSHOT_MANIFEST.json`. Exact source-response, normalized sequence, and index-file hashes, source TaxIDs/organism names, and study citations are recorded. Payloads remain external/untracked. No explicit rights marker was found in the records, but this is not legal clearance; redistribution is not approved. |
| M6/M7 cache identity isolation | CLOSED | Stage-scoped cache regression tests cover M8-only identity changes while retaining shared M6 handoff validation in M6's identity. |

The earlier per-record and per-setting findings above remain as an audit
history, not as current blockers. The scope remains limited: no production M8
search stage, candidate-data search, biological benchmark, or M9 work was
performed; no sequence payload or BLAST index was committed. Biological
holdout/leakage review remains for a future benchmark, not this technical gate.

**M8 IMPLEMENTATION GATE: READY**
