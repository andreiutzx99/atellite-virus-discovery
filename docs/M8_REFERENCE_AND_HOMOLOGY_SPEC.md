# M8 — Reference and homology evidence specification

**Status: READY FOR REVIEW — design only; M8 is not implemented.**

This document specifies a proposed, provenance-bound comparison layer for
typed candidate-sequence artifacts, retaining whatever upstream evidence state
is available. The approved [roadmap](ROADMAP.md) assigns nucleotide/reference
homology to M8, translated and protein evidence to M9, and read-origin and
technical-artifact review to M12. The milestone ownership and eligibility
principles follow those decisions. The separate
[M8 reference-panel policy](M8_REFERENCE_PANEL_APPROVAL.md) records source and
acquisition recommendations and selects local, pinned BLASTN as the initial
nucleotide-search baseline. It does not clear third-party redistribution or
instantiate reference snapshots. The exact BLAST+ release, tasks, parameters,
reporting limits, full output contracts, and biological thresholds remain
subject to review. Search results are evidence about comparisons that were
actually run, not identities assigned to candidates.

## 1. M8 scientific purpose

Under the approved milestone scope, M8 asks: **what evidence in explicitly
declared reference collections provides plausible sequence-level explanations
or relationships for a candidate sequence?** It compares
nucleotide candidates with role-separated references, retains competing
evidence, and records the limits of each comparison.

A match may motivate review of the aligned reference, its provenance, and
alternative explanations. It does not by itself establish that the candidate
is a satellite, virus, helper, host sequence, contaminant, or biological
entity. A no-hit is scoped to a completed search of frozen, declared references;
it does not establish novelty or absence from all relevant sequences.

## 2. Evidence boundary

M8 is a sequence-similarity evidence stage. It is not an automatic classifier,
biological winner-selection step, probability estimator, origin attribution
from reads, or test of function, replication, helper dependence, or biological
reality. It must not turn evidence absence, a weak alignment, or a no-hit into
a negative biological assertion.

Panel roles describe why records were included in a comparison, not what the
candidate is. A sequence can match records in multiple panels, and the same
reference may be present in more than one independently versioned role panel.
Keep those observations separate and link them by immutable reference
identity. M8 must not pool reads, reassemble candidates, or modify a candidate
sequence to improve an alignment.

## 3. Candidate-sequence input and upstream evidence contract

M8 accepts a typed candidate-sequence artifact with its available upstream
provenance and evidence state attached. It searches candidate sequence bytes,
not source reads:

1. The artifact identifies one candidate sequence with a stable candidate ID,
   sequence ID, exact sequence bytes and digest, declared molecule type, and
   any known completeness or observation links.
2. Upstream evidence is carried with its source and status. M6 reconstruction
   state and artifacts are linked from the required candidate-set handoff.
   Optional M7 observation or recurrence artifacts are supplied separately as
   typed M8 inputs and linked by explicit candidate/sequence identity. The M6
   candidate-set artifact cannot embed M7 tables. Source-read checksums and
   independence metadata may be included when available. Recurrence is
   contextual evidence and is not a substitute for sequence bytes or an
   upgrade to reconstruction support.
3. Missing, weak, partial, unresolved, unsupported, or failed upstream evidence
   remains explicit in the M8 record. An unavailable upstream result is not
   treated as an empty candidate set or a completed search with no match.

Candidate eligibility and evidential strength are separate. A candidate is
eligible for M8 when its typed sequence artifact passes identity, alphabet,
and integrity validation; M8 must not require an M6 `READ_SUPPORTED_ASSEMBLY`
state or another minimum upstream support category. M8 preserves upstream
states and must not upgrade them. A reference match does not establish
biological reality, and a no-hit does not establish novelty. Invalid or
corrupt sequence artifacts may be rejected for technical reasons.

Identical sequence bytes may reuse a comparison, but each candidate and
observation remains linked to its own evidence record. Batch execution, if
provided, must keep candidate queries and observations separate. M8 consumes no
FASTQ, SAM, pooled reads, or assembly request and must not alter or synthesize
candidate sequence bytes.

## 4. Reference-panel architecture

Build independent, role-labelled panels rather than one unannotated “all
references” database. Keep biologically overlapping concepts in separate
subpanels so that overlap is visible and no taxonomy is inferred from the
panel name.

| Panel role / subdivisions | Scientific purpose and recommended sources | Acquisition, release identity, and construction | Licensing, redistribution, and update policy |
| --- | --- | --- | --- |
| `satellite_subviral`: satellite RNAs, satellite viruses, other named subviral elements; keep viroids and deltavirus-like agents as distinct contextual subroles | Compare to accessioned sequences and curated records from primary literature. Use INSDC nucleotide records (NCBI GenBank, ENA, or DDBJ) as sequence records; use ICTV only for current virus taxonomy where applicable, not as a complete satellite catalogue. | Curator-maintained, accession-version allowlist; retrieve exact records through provider APIs/archives and retain source response/file, cited publication, accession.version, and retrieval time. Locally curate literature-only records with a source citation and explicit review state. A panel is a finite selected set, never “all known satellites.” | NCBI says GenBank data have no NCBI-imposed use or distribution restrictions, but verify each record and linked publication's terms. Check ENA/DDBJ and supplementary-file terms per source. Redistribute only when permitted; otherwise publish the accession manifest and provide a local-construction recipe. Updates create a new reviewed snapshot, never replace a used snapshot. |
| `virus_helper`: viral genomes and declared potential-helper references; retain complete/partial, segmented, and taxonomic groups as separate metadata | NCBI RefSeq Virus / NCBI Datasets virus packages for curated reference records; INSDC accessions for additional named or study-relevant sequences. ICTV MSL release is a taxonomy crosswalk, not proof of helper status or a sequence database. | Pin RefSeq/NCBI Datasets package or exact accession.version set, retrieval date, NCBI Taxonomy dump and ICTV release where used. “Helper” is an explicitly reviewed inclusion rationale, not a field inferred from taxonomy. | Record data-source and record-level terms, plus any third-party annotations. The current ICTV taxonomy page states CC BY 4.0; capture the exact release and license with the crosswalk. NCBI's sequence and taxonomy terms are not assumed to license every linked annotation. Redistribute only after review; otherwise users construct from pinned identifiers and terms. Release changes produce new snapshots and documented membership diffs. |
| `host_nuclear`: declared host nuclear assemblies; optional transcript records remain a separate subpanel | NCBI RefSeq genome assemblies and, where justified, exact GenBank/INSDC assemblies for the host organisms declared by the study. A broad organism choice is not a verified host assignment. | Pin assembly accession.version, component/alternate/haplotype policy, annotation release if used, FASTA hashes, and taxonomy snapshot. Select host scope explicitly before search; do not silently query a moving organism database. | Review the assembly provider, submitter, and annotation terms for the chosen records. Publish or redistribute only if allowed; otherwise provide accession.version and construction instructions. Re-evaluate updates as a new snapshot, not a mutation. |
| `host_organelle`: mitochondrial, plastid, and other relevant organelle sequences | RefSeq/INSDC organelle accessions linked to the declared host; preserve organelle type, host taxon, and accession.version. Keep distinct from nuclear sequences because sequence roles and possible integrations differ. | Pin organelle records, source assembly link, provider release/retrieval date, sequence hashes, and taxonomy provenance. Add transcript references only as a separately declared subpanel. | Apply the source and record-level licensing checks above. Do not infer that an organelle-like hit proves organelle origin. Version and review changes independently of the nuclear panel. |
| `microbial`: bacterial, archaeal, fungal, and other microbial records as needed | NCBI RefSeq microbial assemblies are a practical starting point. GTDB may be used as a separately identified taxonomy/sequence resource when its scope and release are appropriate; it is licensed CC BY-SA 4.0. Avoid mixing rRNA-only collections with whole-genome panels without declaring that different scope. | Declare included domains/groups and representative-versus-all-record policy; pin assembly accession.version, exact GTDB release if used, taxonomy files, acquisition date, and all sequence/metadata hashes. A local build must retain its query, filters, deduplication rules, and build software identity. | Review NCBI, GTDB, submitter, and third-party terms independently. GTDB redistribution must meet its stated license. If mixed terms prevent redistribution, distribute a reproducible accession manifest and local acquisition instructions instead. New provider releases create new snapshots. |
| `vector`, `adapter`, and `plasmid`: three separate technical subpanels | NCBI UniVec for vector screening; adapter sequences from the documented library-kit/vendor version actually relevant to a study; plasmid/construct sequences from versioned GenBank/INSDC records or a locally declared construct inventory. These roles should not be merged: their provenance and likely explanations differ. | Pin UniVec build/release, each adapter's kit/document version and retrieval date, and plasmid accession.version or local construct revision. Include exact sequence hashes, orientation, and documented source. Local lab plasmids require a controlled, curator-reviewed inventory. | Follow UniVec/NCBI terms, vendor documentation restrictions, and plasmid record terms independently. For example, [Illumina states](https://support.illumina.com/downloads/illumina-adapter-sequences-document-1000000002694.html) that its adapter sequence information is for use with Illumina instruments; obtain legal review before redistribution or broader reuse. If rights are unclear, do not bundle the sequence; users construct locally from the cited source. Update only with a new panel release. |
| `technical_contaminant`: common laboratory/reagent, cell-line, and study-specific technical sequences | No universal authoritative complete contaminant collection is assumed. Construct locally from documented kit/reagent lots, positive controls, laboratory stocks, cell lines, synthetic controls, and other study-specific sources. Keep a generic literature/accession list separate from the local panel. | Requires a named curator, evidence/source for every entry, dates/lot or revision where available, approval record, sequence hash, and explicit scope. Protect sensitive supplier, sample, or laboratory metadata. Build from a controlled local manifest; missing local references mean “not assessed,” not a negative result. | Terms may be contractual, confidential, or third-party; assume no redistribution until reviewed. Provide a local construction template without protected sequences or metadata. Updates require a reviewed new local snapshot and change log. Do not call a match “contamination” solely from this panel. |
| `mobile_element`: DNA transposons, retroelements, endogenous viral elements, and related repeats as distinct subroles | Dfam consensus sequences are a possible source for nucleotide repeat context; accessioned full-length exemplars may be added from INSDC. Dfam profile-HMM/domain interpretation is outside M8 and remains an M9 concern. | Pin exact Dfam release and downloaded files, source accessions for added exemplars, sequence and metadata hashes, taxonomy/source files, and construction/version identity. Preserve family and consensus-vs-observed-sequence distinctions. | Dfam publishes release-specific terms; check the exact release (the current release notes identify CC0 1.0) and each added record's terms. Do not infer a candidate's biological category from a repeat-family match. Freeze and diff updates. |
| `polinton_related`: Polinton/Polinton-like elements, virophages, and related viral or mobile-element sequences | Curate accessions and literature-linked sequences from INSDC/primary studies; use ICTV only where the current taxonomy explicitly applies. Keep Polinton-like mobile elements, virophages, and other related groups as distinct inclusion roles, with endogenous/integrated records flagged. | Maintain a reviewed accession.version list and cited literature for each inclusion; pin taxonomy release, source files, retrieval date, sequence hashes, and local curation history. Include this as an optional contextual panel only when relevant to the study and approved. | Terms follow the underlying source record/publication; locally curated supplements may not be redistributable. Provide local-build instructions when required. A taxonomy or literature update creates a new snapshot; it does not relabel prior results. |

These are recommendations, not approved reference selections. A category may be
`NOT_SELECTED` with a recorded reason or `NOT_APPLICABLE`; it must not silently
disappear from the declared panel plan. Role overlap is allowed, but each
panel-role search and provenance record stays independently addressable.

## 5. Reference provenance and snapshot requirements

M2 already provides checksum-pinned supplied-reference snapshots and imported
record artifacts; it does not automatically curate or certify panel
completeness. M8 would need a role-aware, sequence-level manifest on top of
those file-level integrity contracts. A suggested snapshot manifest records:

- Stable `snapshot_id`, `panel_role`, subrole, panel specification version,
  parent snapshot when applicable, validation state, creation time, and a
  content-derived snapshot digest.
- Source institution/resource, exact release/build, accession.version or
  local record ID, retrieval timestamp (UTC), retrieval endpoint/query and
  relevant filters, original file/response digest, and source citation.
- For every record: stable reference ID, exact sequence SHA-256, sequence
  length, molecule/alphabet, canonicalization rule, original record digest,
  title, accession/version, taxon ID and taxon-name source/release, metadata
  provenance, role/subrole, inclusion rationale, and license/redistribution
  status or an explicit unknown/pending state.
- Included, excluded, duplicate, withdrawn, superseded, and benchmark-withheld
  membership lists with reasons; do not erase records during deduplication.
- Raw source and normalized FASTA/metadata hashes, manifest hash, reference
  index/build command, builder and parser versions/identities, generated
  database-file hashes, and validation checks/counts.
- License text or stable license reference per source/component, redistribution
  decision, required attribution, and any local-only restriction.

An accession and taxonomy label alone are not sequence identity. Sequence
hashes must be computed over a declared representation, with original provider
bytes retained or hashed separately. Do not silently convert U to T, reverse
complement records, trim sequence, or merge records while building a panel.
Any intentional normalization or duplicate collapse must be described and
reversible through the manifest.

No live database query is a reproducible panel by itself. Acquisition must
resolve to immutable files and a manifest before search. Reference indexes
must be built from those files with pinned tools and validated against the
manifest. Snapshot completeness means only that the declared build completed
against the declared membership, not that the panel contains all relevant
biology. Updates create a new snapshot with a parent link and membership/hash
diff; existing results continue to name the original snapshot.

## 6. Search hierarchy

The initial method baseline is local, pinned BLASTN, as selected by the
reference-panel policy. Its exact release, tasks, parameters, reporting limits,
and method-specific applicability rules require approval and
software/benchmark evaluation. Any alternative aligner needs an explicit
method identity and comparative validation. The design should be staged and
panel-specific:

1. **Validate and scope.** Verify candidate and snapshot manifests, alphabets,
   IDs, checksums, panel roles, holdout exclusions, generated database hashes,
   and complete index-build state. Record nucleotide molecule type as declared
   (`DNA`, `RNA`, or `unknown`); do not silently convert T/U.
2. **Nucleotide local similarity.** Run the pinned local BLASTN baseline
   separately against each approved panel. The method must examine both
   orientations and support local/fragmented alignments. Record exact
   program/task, executable or container identity, database build, parameters,
   masking, reporting limits, and raw output. Other nucleotide aligners require
   an explicit method identity and comparative validation.
3. **Short-query and sensitivity branches.** Where technically appropriate and
   supported by validation, include an explicitly declared short-query mode
   such as BLASTN `blastn-short`, and low-complexity-masked and unmasked
   branches. Preserve branch outcomes independently. Do not apply one default
   scoring configuration to every query length and panel without validation.
   Any limits on reported target sequences, HSPs, or alignments must be
   recorded, and truncation must be exposed rather than described as a complete
   competing-hit set.
4. **M9 boundary.** M8 performs nucleotide/reference comparisons only. It does
   not run translated nucleotide-to-protein searches, call ORFs, search protein
   or domain databases, run profile-HMMs, or interpret remote homology. M8 may
   preserve candidate identity, exact sequence bytes, nucleotide alignments,
   and provenance needed by a later M9 assessment. M9 owns translated and
   protein-level evidence; those predictions and matches do not establish
   expression or function.

For each nucleotide HSP retain the query and reference coordinates, strand,
alignment length, mismatches/gaps, identities, query/reference coverage
components, raw/bit score, and E-value or method-specific statistic exactly as
reported. Statistical values are method-, database-, and composition-dependent;
they are not calibrated biological probabilities and must not be compared as
if a universal cross-panel score existed. M8 defines no biological threshold.

Local/fragmented alignments are evidence about aligned segments, not proof that
a candidate is a complete genome, one continuous molecule, or one biological
entity. If multiple HSPs are summarized together, retain the original HSPs and
the explicit, versioned aggregation rule. Repeats and low-complexity sequence
can produce broad or non-specific similarity: expose composition/masking
metadata and retain the alignments with that caveat rather than using them as
automatic classifications.

## 7. Short- and incomplete-sequence handling

There is **no arbitrary biological minimum candidate length**. M8 must retain
short and incomplete candidates and record their observed length,
ambiguity/composition, declared completeness, and any upstream limitations.
Candidate completeness may be `unknown`, `partial_as_supplied`, or
`complete_as_declared`; none of these labels proves biological completeness.

Short sequences need their own method-aware evaluation. E-values, percent
identity, aligned length, query coverage, and whole-query coverage can each
look persuasive or uninformative in isolation for a very short query. Therefore:

- Report absolute aligned bases and coordinates along with identity and both
  query- and reference-side coverage; state each denominator and whether
  ambiguous positions are included.
- Preserve raw/bit scores and significance values with the exact database
  size, scoring/masking settings, and tool version. A high identity over a tiny
  segment is not automatically strong evidence.
- Record whether the method can meaningfully evaluate the query under the
  declared protocol. A query that is too short, ambiguous, repetitive, or
  otherwise uninformative for that method receives
  `INSUFFICIENT_INFORMATION`; it is not converted into a novelty statement.
- Do not set a length-only biological eligibility cutoff. Any technical
  method-specific applicability rule must be explicit, justified for the
  search implementation, tested on software fixtures, and reviewed before
  use; its presence does not classify biology.
- Preserve a real reported exact or local match as evidence even when the
  query is short, but also report interpretability limitations. Do not claim
  that a tiny alignment resolves identity or origin.

An incomplete candidate can be searched as supplied, with all results labelled
as fragment-scoped. Failure to search, an uninformative query, and a completed
search that reported no hit are distinct states. A no-hit for a short query,
when a search was technically completed, remains only a no-hit within that
specific declared searchable scope; it is never a novelty claim.

## 8. Machine-readable match evidence

Store normalized results without discarding raw tool output. A match record
should include at least:

```json
{
  "schema": "m8-match-evidence-v1",
  "candidate": {
    "candidate_id": "stable-id",
    "sequence_id": "sequence-id",
    "sequence_sha256": "…",
    "length": 0,
    "molecule_type": "unknown",
    "completeness": "unknown",
    "m7_observation_ids": [],
    "m6_artifact_digests": {}
  },
  "comparison": {
    "panel_role": "virus_helper",
    "snapshot_id": "immutable-id",
    "snapshot_sha256": "…",
    "panel_manifest_sha256": "…",
    "method": "blastn",
    "tool_version": "exact-version",
    "tool_identity": "executable-or-container-digest",
    "parameters": {},
    "implementation_identity": "parser-and-runner-digest",
    "execution_status": "SEARCH_COMPLETED_MATCHES_REPORTED",
    "panel_status": "VALID"
  },
  "hit": {
    "reference_id": "stable-reference-id",
    "accession_version": "accession.version",
    "reference_sha256": "…",
    "reference_length": 0,
    "taxonomy": {},
    "metadata_provenance": {},
    "strand": "+",
    "alignments": [],
    "raw_output": {
      "path_or_object_id": "…",
      "sha256": "…"
    }
  }
}
```

The ellipses and zeroes above are schema examples, not real evidence. Each
alignment entry should retain query/reference start/end coordinates, coordinate
convention, aligned length, identities, mismatches, gaps, query and reference
coverage values and denominators, score, E-value or method-specific statistic
(nullable when undefined), mask branch, and HSP ordinal. Retain raw output by
content hash and a stable artifact reference. Record command arguments in a
safe structured form; do not store credentials or secret environment values.

Also retain query-level execution records for panels with zero hits, including
candidate hash, panel role/snapshot/manifest hashes, search method/tool,
parameters, searched-record/base counts, exclusions, branch completion,
reporting truncation, raw-output hash, timestamps, and status. Preserve
taxonomy and other annotations as source metadata with their release and
provenance; do not relabel reference records through an unrecorded current
taxonomy lookup.

## 9. Execution and evidence statuses

Statuses are per candidate × panel × method branch. Keep input suitability,
panel validity, execution outcome, and evidence result as separate fields so a
single status cannot erase missingness.

Required execution/evidence outcomes:

- `SEARCH_COMPLETED_MATCHES_REPORTED` — the declared search branch completed
  and reported one or more hits. This does not imply the hit set is exhaustive
  if a reporting limit was reached.
- `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` — the branch completed
  against a valid, complete declared snapshot and reported no hit under its
  recorded parameters. Scope is the exact snapshot and method only.
- `INSUFFICIENT_INFORMATION` — input or method/query combination cannot support
  an informative search under the approved protocol. Preserve any diagnostic
  output separately; this is not a no-hit.
- `DEPENDENCY_UNAVAILABLE` — a required executable, database builder, runtime,
  or other dependency is absent/unusable.
- `SEARCH_FAILED` — execution or output validation failed.
- `SEARCH_INTERRUPTED` — execution was cancelled, timed out, or stopped before
  complete accounting.
- `REFERENCE_PANEL_INVALID` — manifest, hashes, index, role, or validation
  checks fail; do not interpret its search as a valid result.
- `REFERENCE_PANEL_INCOMPLETE` — the declared membership/build is known to be
  partial or incomplete. Positive alignments may be retained with this panel
  warning, but a scoped no-hit cannot be asserted for the intended panel.
- `INPUT_INVALID` — malformed sequence, contradictory identity, failed
  checksum, or invalid handoff prevents a search.

For the frozen Linux BLASTN profile, the software-only method-applicability
check selects the task and compares query length with its explicit word size.
A query shorter than that word size remains a valid, eligible candidate but
its branch is `INSUFFICIENT_INFORMATION` with diagnostic reason
`QUERY_SHORTER_THAN_WORD_SIZE`; it is not a completed no-hit. For the selected
profile this applies only below 7 nt. The 50-nt task selector is not an
eligibility cutoff, and any reported alignment remains evidence.

`NOT_SELECTED`, `NOT_APPLICABLE`, `NOT_STARTED`, and `RUNNING` may be represented
as planning/lifecycle values, not as successful search outcomes. A
`SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` must never be emitted
for missing dependencies, invalid/incomplete panels, parser errors, capped or
interrupted searches, or insufficient information. Aggregate status must say
`PARTIAL` when a required panel/branch did not complete; it must not summarize
partial execution as an overall no-hit.

## 10. Competing-hit policy

Retain relevant evidence from every searched role panel, including weak
satellite/subviral similarity, stronger host similarity, microbial similarity,
technical sequence similarity, or mobile-element similarity when present.
Do not choose a biological winner, suppress a category because another score
is higher, compute an uncalibrated confidence score, or use a tie-break to
assign identity.

Within a method branch, hits may be sorted deterministically for display by a
declared technical ordering (for example, reported score then stable reference
ID), but the original tool order and all retained values remain available.
Record tied hits, overlapping HSPs, multiple references with identical
sequence hashes, and any configured output cap. A capped result is
`reporting_truncated=true`; it cannot be described as the complete set of
competing references. Panel labels and taxonomic metadata are explanations to
review, not adjudicated candidate labels.

## 11. No-hit semantics

“No hit” means only that a specific completed method branch returned no
reported alignment against the exact valid snapshot and recorded settings.
The report must name the panel roles, snapshot IDs/hashes, methods, parameters,
masking/search branches, and exclusions actually searched. It cannot mean:

- no homolog exists in nature, all databases, or all taxa;
- novel, unclassified, non-host, non-viral, satellite, or biologically real;
- no alignment exists below a reporting/filtering limit or outside the search
  method's sensitivity;
- all relevant records were included merely because a panel build completed.

If the search plan requires several panels or branches and any required one is
unavailable, invalid, incomplete, or interrupted, preserve completed results
but report the overall assessment as partial/unresolved. A panel that was not
selected is not a negative observation. An informative completed no-hit and
`INSUFFICIENT_INFORMATION` are distinct, and neither supports universal
novelty.

## 12. Deterministic reuse and invalidation

Reuse is allowed only when the full semantic identity matches, including:

- canonical candidate bytes/hash, alphabet and normalization policy, candidate
  ID linkage, and M7/M6 evidence identities;
- panel snapshot bytes/hash, sequence-level membership manifest hash,
  taxonomy/metadata snapshot hashes, holdout/exclusion manifest, and generated
  database/index hashes;
- tool and database-builder versions plus executable/container digests,
  commands, search parameters, masking, query mode, output/report limits, and
  environment details that affect output;
- runner, parser, normalization, and aggregation implementation identities;
- output schema/version and validated raw/normalized output hashes.

Use deterministic ordering, explicit nulls, stable identifiers, fixed
serialization, and a declared locale/time policy for semantic outputs.
Retrieval and execution timestamps are provenance, not substitutes for content
identity. A candidate or panel content/manifest change invalidates only the
affected M8 comparison and downstream M8 summary. A changed reference must not
force M6 assembly or M7 recurrence to rerun. Reuse validation is read-only and
fails closed if any input, index, implementation, or output hash differs.

## 13. Compatibility with future blinded validation

Design every snapshot to support exact-sequence, close-relative, family/clade,
and study-level withholding. A benchmark plan must identify the labelled
sequence/accession set, relatedness grouping and provenance before panel
construction. Exclude benchmark sequences and, for divergent-discovery tests,
predeclared close homologues or entire appropriate families/clades from every
panel and derived index. Record the exclusion manifest and verify no withheld
record or derived duplicate remains. Study holdouts must account for accessions
or supplements from the held-out studies that entered references through
another route.

The holdout policy and leakage checks must be frozen before labels are opened.
Report both what was withheld and what could not be verified. A database that
still contains close relatives is not an adequate divergent-discovery test;
post hoc removal after seeing results invalidates blinding. M8 outputs must
carry snapshot and exclusion-manifest identities so future M16 can audit these
conditions.

## 14. Proposed M8 output contract

The proposed typed outputs are:

- `m8_panel_manifest`: role-specific immutable snapshot and sequence-level
  provenance, licensing, membership, release, build, validation, and
  benchmark-exclusion metadata.
- `m8_search_manifest`: candidate/input identities, M6/M7 links, methods,
  tool/configuration identities, branch and panel status, counts, warnings,
  and output hashes.
- `m8_match_evidence`: one reconstructable record per reported hit/HSP,
  retaining competing matches and source metadata.
- `m8_query_status`: one row per candidate × panel × method branch, including
  explicit no-hit, insufficient-information, unavailable, failed, interrupted,
  invalid, incomplete, and not-selected states.
- `m8_summary`: descriptive counts and links to evidence with scope and
  limitations. No biological winner, class, novelty call, or uncalibrated
  confidence score.
- `m8_raw_output`: immutable native output/logs or content-addressed references
  and hashes, with bounded and safe command/environment provenance.

The schemas are proposals; current `artifact_contracts.py` has M1–M7
contracts, not these M8 contracts. Implementation requires versioned,
validated contracts and explicit workflow states before M8 can be considered
software-complete.

## 15. M9, M12, and later milestone boundaries

- **M9 — translated and protein evidence:** owns translated searches, ORF
  hypotheses, protein similarity, protein/domain and profile-HMM evidence, and
  remote-homology leads. It links to M8 candidate and nucleotide-comparison
  identities without overwriting M8 results. Predictions and similarities do
  not establish expression, function, or classification.
- **M12 — read-origin and technical-artifact review:** assesses source reads,
  controls, contamination, batches, and reconstruction alternatives. It is a
  separate evidence dimension from M8 sequence/reference similarity; M8 hits
  do not establish the origin of reads or a candidate.
- **M10 and M11:** may add guarded architecture/topology and RNA
  structure/ribozyme prediction evidence, respectively. A topology signal does
  not confirm circularity; a fold or motif does not establish ribozyme
  function.
- **M13–M15:** may consume linked M8 evidence for DVG-versus-satellite
  differential review, helper-association analysis, evidence integration, or
  transparent prioritization only with missingness, scope, and dependencies
  visible. Similarity is not biological confirmation or a calibrated ranking
  input by itself.
- **M16:** may evaluate a frozen, blinded workflow against independent truth
  sets and documented controls. M8 matches/no-hits remain input evidence, not
  validation outcomes.

No downstream stage may reinterpret a failed, unavailable, incomplete, or
insufficient M8 search as a negative biological observation.

## 16. Software acceptance fixtures

Before software acceptance, deterministic synthetic and curated-record
fixtures should verify:

- a straightforward exact/near-identical nucleotide match and a completed
  no-match control with valid frozen panels;
- simultaneous competing matches in satellite/subviral, host, microbial,
  vector/plasmid, technical-contaminant, mobile-element, and virus/helper roles;
- panel role separation, stable ordering, ties, duplicate reference sequences,
  multiple HSPs, fragmented candidates, and reporting-cap behavior;
- reverse-complement matches, strand/coordinate conventions, ambiguous bases,
  DNA/RNA distinction, and no silent U/T conversion;
- short, incomplete, repetitive, low-complexity, and composition-biased
  queries, with informative evidence or `INSUFFICIENT_INFORMATION` as
  applicable and no arbitrary biological minimum or novelty label;
- full and masked/unmasked nucleotide-search branch accounting, with no
  translated or protein search performed in M8 and M9 provenance preserved as a
  separate evidence layer;
- corrupted/mismatched sequence hashes, manifest/index mismatch, invalid and
  incomplete panels, taxonomy metadata changes, missing dependencies,
  execution failure, interrupted searches, parser failure, and malformed raw
  output;
- correct raw-output and provenance hashes, exact reconstruction of
  coordinates/metrics, deterministic outputs and reuse, and invalidation after
  changing candidate, panel, tool, parameters, parser, or holdout manifest;
- candidate-sequence identity and hash traceability with optional M6/M7
  provenance; preservation of weak, incomplete, unsupported, failed, or
  unavailable upstream states; no read inputs and no changes to M6/M7 artifacts.

These fixtures validate software contracts and state semantics only. Generated
sequences and artificial alignments do not estimate sensitivity, specificity,
taxonomic accuracy, biological relevance, or discovery performance.

## 17. Scientific benchmarking requirements

Scientific evaluation is a separate later gate. It needs independently
labelled, accession- and study-traceable sets covering at least:

- known satellite/subviral positives with documented sequence and biological
  context;
- related non-satellite or otherwise plausible negative alternatives, with
  labels and limitations justified independently of M8;
- divergent family/clade holdouts with close homologues withheld from every
  panel and derived index;
- study-level holdouts that prevent test-study sequences and associated
  supplements from entering the reference snapshots;
- host, microbial, vector/plasmid, reagent/technical, mobile-element, and
  virus/helper decoys representative of intended use, plus appropriate
  negative/control observations.

Freeze candidate eligibility, panels, methods, parameters, outputs, analysis
plan, denominators, and blinded labels before evaluation. Report per-class and
per-study counts, unresolved cases, missing inputs, uncertainty, and all
exclusions. Evaluate sensitivity/specificity or other performance only when
independent truth labels and denominators support that calculation; do not
derive those claims from synthetic fixtures or a curated reference search
alone. No biological threshold or pass criterion is established by this
specification.

## 18. Literature and resource rationale

The [M8/M9 design research report](research/M8_M9_DESIGN_RESEARCH.md) is
preserved as historical design context, not as an implementation contract.
The following publications and official resources support the narrow
methodological and provenance recommendations; they do not validate this
software or its thresholds:

- Altschul SF, Gish W, Miller W, Myers EW, Lipman DJ. (1990). [Basic local
  alignment search tool](https://doi.org/10.1016/S0022-2836%2805%2980360-2).
  *Journal of Molecular Biology*, 215(3), 403–410. Foundational sequence
  similarity-search method.
- Camacho C, Coulouris G, Avagyan V, et al. (2009). [BLAST+: architecture and
  applications](https://doi.org/10.1186/1471-2105-10-421). *BMC
  Bioinformatics*, 10, 421. Documents the BLAST+ software family; the exact
  implementation and parameters still require pinning.
- Benson DA, Cavanaugh M, Clark K, et al. (2013). [GenBank](https://pubmed.ncbi.nlm.nih.gov/23193287/).
  *Nucleic Acids Research*, 41(Database issue), D36–D42. DOI:
  `10.1093/nar/gks1195`. Resource context for accessioned nucleotide records.
- O'Leary NA, Wright MW, Brister JR, et al. (2016). [Reference sequence
  (RefSeq) database at NCBI: current status, taxonomic expansion, and
  functional annotation](https://pubmed.ncbi.nlm.nih.gov/26553804/). *Nucleic
  Acids Research*, 44(D1), D733–D745. DOI: `10.1093/nar/gkv1189`. Resource
  context for curated reference records.
- Wilkinson MD, Dumontier M, Aalbersberg IJJ, et al. (2016). [The FAIR Guiding
  Principles for scientific data management and
  stewardship](https://doi.org/10.1038/sdata.2016.18). *Scientific Data*, 3,
  160018. General support for findable, accessible, interoperable, reusable
  data and provenance.

Official source and terms pages to consult when constructing an approved
snapshot:
[NCBI RefSeq](https://www.ncbi.nlm.nih.gov/refseq/),
[NCBI GenBank use and access](https://www.ncbi.nlm.nih.gov/genbank/about),
[NCBI Datasets virus downloads](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/how-tos/virus/virus-download),
[ICTV current taxonomy](https://ictv.global/taxonomy),
[GTDB downloads and license](https://gtdb.ecogenomic.org/downloads),
[NCBI UniVec information](https://www.ncbi.nlm.nih.gov/tools/vecscreen/univec/),
[Illumina adapter sequence documentation](https://support-docs.illumina.com/SHARE/AdapterSequences/Content/Nextera_Illumina-Sequences.htm),
[Illumina's adapter information terms](https://support.illumina.com/downloads/illumina-adapter-sequences-document-1000000002694.html),
and [Dfam releases](https://www.dfam.org/releases). Their current content,
release identity, and terms must be checked and archived when a panel is
actually built; this specification does not claim to have downloaded or
approved a release. NCBI itself notes that GenBank data carry no NCBI-imposed
use/distribution restrictions, while other sources can impose distinct terms.
For every mixed-source panel, licensing review remains per component and
record.

## 19. Remaining design decisions requiring review

1. **Panel instantiation:** which exact source releases, organism/taxon scope,
   accessions, local technical-contaminant material, curation owners, and
   taxonomy crosswalks are appropriate for intended studies under the
   role-level framework in the reference-panel policy?
2. **Licensing and distribution:** which snapshots may be redistributed,
   which require local construction, and how will per-record/vendor/repository
   terms, attribution, and local confidential materials be reviewed?
3. **Search configuration:** the policy selects local BLASTN as the initial
   baseline. Which exact BLAST+ release, tasks, masks, reporting limits,
   parameters, and method-specific insufficient-information rules should be
   evaluated and predeclared? Any alternative method requires comparative
   validation. No biological thresholds are selected here.
4. **Benchmark and leakage policy:** who will curate truth labels, define
   family/clade and study holdouts, audit close-relative exclusion, and set
   blinded M16 acceptance criteria?
5. **Contract/workflow ownership:** how should the proposed M8 artifact
   schemas integrate with the current trusted workflow registry and
   M1–M7 contracts without changing their behavior?

Milestone ownership, candidate eligibility principles, and the M8/M9/M12
boundaries follow the current roadmap and approved architecture decisions. The
role-level panel framework and initial local BLASTN baseline follow the
reference-panel policy. Exact reference snapshots and terms, BLAST+ release
and configuration, output contracts, biological thresholds, and benchmark
policies remain subject to review. This document does not implement M8/M9 or
support biological classification.

M8 specification: READY FOR REVIEW