# M9 Pre-Implementation Contract Freeze

**Status: APPROVED FOR BASELINE SOFTWARE IMPLEMENTATION (synthetic/offline only); M9 remains PLANNED / NOT IMPLEMENTED.**
This approval authorizes only the baseline software scope below, validated with
synthetic fixtures. It does not authorize biological database retrieval, real
biological searches, or biological validation or claims.

**Evidence scope:** the method observations cited here used synthetic sequences
and artificial profiles only. No biological candidate dataset or biological
protein/profile database was searched or downloaded for this freeze.

## 1. Purpose, authority, and evidence boundary

M9 is a **protein-level evidence stage**. It may report nucleotide-derived ORF
hypotheses and translations, local protein similarities, translated-nucleotide
similarities, and profile-HMM/model matches under named methods and immutable
reference snapshots. Each is a scoped prediction or comparison result, not a
candidate classifier.

M9 alone must not conclude that a candidate is a satellite, non-satellite,
novel, non-novel, helper-dependent, functional, expressed, replicating, or
biologically real. An ORF is not evidence of expression; a protein alignment
or profile match does not demonstrate identity, activity, or function; no ORF
is not a noncoding call; and a completed no-hit is not novelty. Do not emit a
biological winner, class, or uncalibrated confidence score. Preserve competing
matches and unresolved explanations.

The current [roadmap](ROADMAP.md) and [README](../README.md) govern milestone
status: M1–M8 are implemented software and M9–M16 are planned. M8 owns nucleotide
homology; M9 owns translated and protein evidence. M10 topology, M11 RNA
predictions, M12 read-origin review, M13 differential evidence, M14 helper
dependence, and M16 biological validation remain outside M9.

The [empirical method validation](M9_EMPIRICAL_METHOD_VALIDATION.md) is the
source for observed synthetic behavior and method limitations. The
[pre-M9 stage identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md) is authoritative
for current cache semantics. M8/M6 interface constraints are described in the
[M8 contract and BLASTN validation](M8_CONTRACT_AND_BLASTN_VALIDATION.md),
[M8 reference and homology specification](M8_REFERENCE_AND_HOMOLOGY_SPEC.md),
[M6 residual support record](M6_RESIDUAL_ASSEMBLY_SUPPORT.md), and
[M7 recurrence record](M7_INDEPENDENT_RECURRENCE.md). The historical
M9 architecture is design context only; its broad ORF/search separation is
compatible, but its earlier shared-module cache concerns are superseded by the
stage-scoped cache audit. Nothing in that historical document changes current
M6–M8 contracts.

This document distinguishes:

- **Observed:** a result reproduced with the named synthetic fixture and tool
  settings. It supports software behavior only.
- **Selected baseline:** the method or semantic rule selected for this
  contract. Selection alone is not approval for biological use.
- **Approved for baseline software implementation:** authorized for the
  synthetic/offline software scope recorded here; not approval for real
  biological references, searches, or thresholds.
- **Human approval required:** a decision deliberately left to an authorized
  reviewer before the corresponding real-resource or production use.
- **Deferred:** an untested, out-of-baseline, or resource-intensive method.

## 2. Candidate handoff and eligibility

### 2.1 Source of candidate identity

The M9 candidate source is the existing validated M6-produced
`m8_candidate_sequence_set` (`m8-candidate-sequence-set-v1`) and its paired
FASTA when available. Revalidate the manifest, exact FASTA sequence bytes,
record IDs, hashes, lengths, source-artifact bindings, assembly manifest, and
M6 reconstruction-evidence reference using the current
[candidate handoff contract](../satellite_discovery/m8_candidate_handoff.py).
The source sequence hash is over the exact sequence letters in the FASTA
record; line wrapping is not part of that sequence digest.

Preserve every producer-declared candidate and sequence identity, including
different candidates with identical sequence bytes. Keep the original candidate
IDs, sequence IDs, FASTA record IDs, source-artifact IDs and hashes, declared
molecule type, completeness state, sequence length/hash, and all supplied
observation links. Byte-identical candidates may share a computation only if
each candidate remains independently represented and linked to the shared
result; never merge their identities.

Keep all M6 information that is available through the handoff or separately
declared typed inputs: reconstruction and read-support states, assembly and
source artifact identities, residual/QC/reference provenance where supplied,
and upstream unavailable, failed, unsupported, or unresolved states. Missing
optional provenance stays explicitly missing; it is not inferred from a
candidate name, match, or neighboring record. M9 must not upgrade, downgrade,
rewrite, or replace any M6 record or result.

### 2.2 Optional M7 and M8 context

M7 observations, recurrence groups, validation, and provenance are optional,
separate typed context. Preserve exact input descriptors and their hashes.
Missing M7 context means **no M7 link supplied**, not no recurrence. Recurrence
does not establish independence beyond declared metadata, does not promote M6
support, and is not an M9 eligibility condition.

M8 query statuses, nucleotide matches, summary, commands, reference-snapshot
identity, and raw-output provenance are optional context. Preserve any supplied
M8 artifacts and their own statuses verbatim, including hits, scoped no-hits,
`INSUFFICIENT_INFORMATION`, partial execution, unavailable dependencies, and
invalid or incomplete panels. A hit, a completed scoped no-hit, an
insufficient-information result, or an unavailable/failed M8 branch does not
gate M9 eligibility when the candidate bytes are valid. Do not copy M8 rows
into M9 protein matches, reinterpret M8 statuses, or modify M8 artifacts.

If supplied M8 context is internally inconsistent or cannot be verified,
report that context as invalid/incomplete; do not silently discard it or
relabel it as no-hit. M9 remains runnable without M8 context. The M8 canonical
`REFERENCE_PANEL_INVALID` and `REFERENCE_PANEL_INCOMPLETE` values remain M8
values; M9 uses its separately scoped snapshot vocabulary below.

When M8 context is supplied as a stage result, bind its query-status, match,
summary, command, and raw-output artifacts to the same verified M8 stage
manifest and candidate-set identity. Check that candidate IDs and sequence
hashes agree; snapshot IDs/digests agree across inputs and summaries; and each
raw-output reference/hash resolves to the corresponding verified output. Keep
M8 branch statuses, tool/settings, panel membership, and incomplete accounting
as M8 evidence. If the bundle lacks sufficient provenance to verify a claimed
completed result, retain the supplied artifact identity but mark the M8
context unresolved/incomplete; never silently drop it or convert it to a
completed no-hit.

### 2.3 Eligibility and prohibited transformations

Eligibility is technical: a candidate with valid, available sequence bytes is
eligible regardless of M6 read-support category, M7 recurrence, M8 result, ORF
count, ORF length, or apparent match. A valid candidate record with unavailable
sequence bytes remains in M9 accounting as
`CANDIDATE_SEQUENCE_UNAVAILABLE`; malformed or contradictory identity is
`INPUT_INVALID`. A complete empty candidate set is not a no-ORF result and not
a protein-search no-hit.

M9 consumes candidate sequence bytes and declared typed evidence only. It does
not consume or pool reads, request or perform reassembly, fabricate or repair
sequence, concatenate candidates, circularize the source, or change upstream
files. Any analytical representation needed for translation is derived,
separately identified, and never substituted for the original M6 sequence.

## 3. ORF enumeration and translation baseline

### 3.1 Enumeration policy

**Approved baseline for synthetic/offline implementation:** deterministic enumeration of all six strand/frame
combinations under a recorded translation table, start set, stop set, and
partial-boundary policy. Enumerate every configured start codon through the
first definite in-frame stop; retain nested and overlapping hypotheses rather
than choosing a longest ORF. Record complete and partial hypotheses as
different rows. Do not use a learned gene model or infer expression.

The approved baseline settings are:

| Setting | Approved baseline policy |
| --- | --- |
| Strands and frames | Three frames on the supplied sequence and three on its reverse complement. |
| Genetic code | NCBI translation table 1 (standard code), declared as a technical hypothesis even when molecule type is `RNA` or `unknown`; this does not establish the candidate's true code. |
| Complete-ORF starts | `ATG` only. Treat it as an initiator under the declared table and translate the initiating residue as methionine. |
| Complete-ORF stop | First unambiguous in-frame stop under the declared table; record its codon and coordinates, but exclude the terminal stop from the peptide. |
| Enumeration | Emit every configured start, including nested starts; preserve overlaps and all strand/frame-specific rows. |
| 5′ partial | Per frame, emit the leading complete-codon segment through its first definite in-frame stop only when no configured start precedes that stop. It has no inferred initiator. |
| 3′ partial | For every configured start without a downstream in-frame stop, emit a separate partial through the final complete codon. The initiating residue follows the declared start policy. |
| Ambiguous codon | Translate to `X`, preserve the exact source codon and position, and do not interpret an ambiguous codon as a start or stop. |
| Length | No universal biological ORF or peptide minimum. Retain every non-empty hypothesis produced by the policy; any future technical storage/reporting bound must be declared and accounted as truncation. |
| Topology | Linear sequence only. No origin-spanning or circular translation in this baseline. |

Use complete codons only. Record any trailing one or two nucleotides not
translated under the selected frame. For a reverse-strand interval `[a,b)` in
reverse-complement coordinates on an input of length `n`, map it to original
coordinates `[n-b,n-a)` and retain the negative strand. Use zero-based,
half-open intervals throughout normalized output. Store the stop separately
from the peptide span where a complete ORF includes a terminal stop.

For declared RNA, `U` may be interpreted as the RNA equivalent of `T` in a
temporary translation view; for an unknown molecule, any such analytical
interpretation must be recorded. Do not edit or normalize the original
candidate bytes or their hash. Any derived oriented nucleotide representation
has its own policy and digest. Do not silently remove ambiguous symbols,
resolve them to a preferred base, or repair frameshifts.

`NO_ORF_PREDICTED_WITHIN_POLICY` means enumeration completed with zero
hypotheses under these exact declared settings. It is not a biological
noncoding conclusion. Keep the candidate and upstream evidence. Do not submit
an empty peptide set to BLASTP or HMMER and call it a completed no-hit; the
protein-derived branches are `NOT_RUN_NO_ORF`. An independently selected
BLASTX branch may still assess the nucleotide sequence.

### 3.2 Alternative genetic codes and starts

Table 1 and `ATG`-only are defaults for a transparent first hypothesis, not a
universal biological assertion. An alternative code or initiator set is a
separate, explicitly declared hypothesis. Record its table identifier, exact
start and stop sets, initiator-residue treatment, reason/source, and separate
ORF/protein identities. Alternative policies require human approval before
production use. Do not infer a code or add alternative starts because they
produce a longer ORF, a preferred match, or a desired biological interpretation.
The synthetic code-comparison fixtures establish that a table can change
translations and stops; they do not identify the right table for any candidate.

Boundary-spanning circular ORFs, RNA editing, programmed frameshifting, and
sequence repair are not assessed by this baseline. Circular translation would
require a separately reviewed, typed topology hypothesis and a distinct method
identity; M9 cannot infer confirmed circularity. Prodigal, ORFfinder as a
production dependency, or another context-specific caller is not a replacement
for the selected enumerator without separate version-pinned synthetic
validation and human approval.

### 3.3 ORF and protein identity

Every ORF row must bind to its candidate ID, sequence ID, exact original
sequence SHA-256 and length, source artifact and M6 evidence references, plus
the derivation-policy identity. Give each hypothesis a stable identifier
derived from candidate identity, original coordinates, strand/frame, and
policy; protein sequence identity alone is insufficient. Retain the exact
derived amino-acid sequence in a separate FASTA artifact (or equivalent
content-addressed object) and record its SHA-256 and length. Preserve the
candidate and derived-protein records separately; do not create a consensus
protein.

## 4. Search branches and composition policy

### 4.1 ORF-derived protein search: BLASTP

**Approved core baseline for synthetic/offline software implementation:** a
local ordinary NCBI BLASTP adapter, contracts, and parser validated against
synthetic, role-separated protein fixtures. This does not authorize biological
reference retrieval or searching. Record exact executable/version/hash, database-builder identity,
database/index hashes, command arguments, task, scoring/matrix and gap settings,
composition-based statistics, SEG setting, reporting thresholds, target/HSP
limits, thread count, output schema, parser identity, and query/snapshot hashes.
The production executable and exact parameter profile still require approval
before real biological searches; the tested local binary is not a bundled or
portable dependency.

Search each derived protein as its own query. Short peptides are retained; there
is no biological length cutoff. A short query may produce no row, a weak row,
or a high-identity tiny local alignment depending on task, masking, scoring,
and reference scope. Report the query length, aligned residues, both query and
reference coverage with denominators, identity, positives if emitted, gaps,
raw/bit score, E-value, and composition/masking settings. Keep weak,
composition-sensitive, partial, tied, and competing rows visibly qualified;
do not choose a hit threshold, ranking rule, or biological cutoff from the
synthetic examples.

**Short-query handling:** `blastp-short` is a separate, optional method branch,
not a fallback silently substituted for ordinary BLASTP. If selected, record
its distinct task and settings and retain its results separately; do not
cross-compare its scores or E-values as if calibrated to ordinary BLASTP.
Use `INSUFFICIENT_INFORMATION` only when a predeclared, human-reviewed
technical applicability rule prevents an informative assessment and no
reportable alignment is retained. If a real row is reported, retain it as
`SEARCH_COMPLETED_MATCHES_REPORTED` with an applicability/interpretability
warning; do not erase it by relabeling the branch insufficient.

**Composition/masking handling:** the baseline search configuration explicitly
records low-complexity SEG masking and composition-based-statistics settings;
the selected primary profile uses SEG masking enabled. A no-SEG or alternate
composition setting, if selected, is a separately identified sensitivity
branch, never a silent fallback or replacement. Retain query identity and
composition warnings in either branch. The synthetic `A`-rich fixture showed
that masked and unmasked searches can differ; it does not validate a preferred
biological setting or a complexity threshold.

Do not suppress rows solely because they are weak, short, low-complexity, or
composition-sensitive. Preserve all rows the declared tool reports, including
ties, and record any configured reporting threshold and cap. A reached target,
HSP, row, byte, or output cap is `SEARCH_TRUNCATED` unless complete accounting
is independently demonstrated. Successful process exit alone does not prove
that tied or competing hits were not omitted. The empirical E-value `2000`
setting was an exposure setting for artificial fixtures, not a selected
production threshold.

### 4.2 Independent translated-nucleotide search: BLASTX

BLASTX is a separate optional branch from each original candidate nucleotide
sequence directly against an approved protein snapshot. It translates the
nucleotide query in six frames under its own explicitly recorded genetic-code
setting. It does not require a canonical start codon, does not depend on an
ORF-derived peptide, and must not retroactively confirm, merge, or change an
ORF. Retain nucleotide coordinates, strand/frame, translated alignment
coordinates, code, snapshot, tool and parameters, and raw output separately.

The synthetic exact translated-alignment fixture supports runner mechanics
only. BLASTX is not required for a candidate to be M9-eligible. If it is not
selected, record `NOT_SELECTED`; if selected, its applicability, resource
limits, and required-branch role must be declared before execution. Use its own
query accounting and outcome status.

### 4.3 Profile-HMM branch

**Optional method family—not required for the first baseline implementation:**
if included, use local HMMER `hmmscan` against separately approved, immutable
profile snapshots, only when a complete compatible indexed profile payload is
supplied. Synthetic profiles may be used for runner, contract, or parser
fixtures. Real biological profile retrieval or execution remains separately
approval-gated. Protein queries are derived ORFs. Record profile
collection and model accession/version, exact model and snapshot hashes,
source alignment/model provenance, `hmmscan` version/hash, `hmmpress` identity
and index hashes, parameters, filter settings, thresholds, parser, and raw
`--tblout` and `--domtblout` hashes. A missing/incompatible pressed index is a
reference or execution failure, not no-hit.

Use a reviewed model-specific gathering threshold when the selected model
provides one and its provenance is approved. Otherwise, a profile branch may
run only with an explicitly approved reporting threshold fixed before the
search. Record threshold source and model-specific score/E-value fields; a
generic synthetic-profile threshold is not transferable to a biological
collection. Preserve HMMER's selected filter/bias settings. `--nobias`,
`--nonull2`, and `--max` are not hidden defaults; if evaluated, each is a
separate named sensitivity branch. HMMER tables list reported models/domains,
not an explicit no-hit row for every query, so maintain external expected-query
accounting.

A profile or domain match means compatibility with a named model and threshold
only. It is not a full-protein identity, expression, activity, function, or
candidate classification. Keep partial domains, low scores, composition/bias
information, competing/overlapping models, and all domain coordinates.

### 4.4 Deferred methods

DIAMOND may be considered later as an explicitly named comparator after
version-pinned evaluation; its output is not interchangeable with BLASTP.
MMseqs2 was not available or tested in the empirical environment and is not
selected. CDD/RPS-BLAST, InterProScan, HH-suite/profile-profile methods, remote
services, and other broad or remote-homology methods are deferred. Their
runtime, source/privacy, license, profile scope, thresholds, and comparability
require separate review and validation. They are not required M9 dependencies
and no result from them is implied by this contract.

## 5. Reference roles, snapshots, and approvals

Protein references and profile-HMM models are distinct resource types with
distinct manifests, payload hashes, and search branches. Keep each selected
role and snapshot independently addressable, even if content is shared. Roles
describe why records/models were included, not what the candidate is. Candidate
matches to competing roles remain visible; a panel name does not assign
candidate taxonomy or function.

Potential scopes for future human selection include satellite/subviral,
virus/helper, host nuclear, host organelle, microbial, technical/vector/
plasmid, mobile-element, and related non-satellite contexts. This list is not
an approved panel, source, collection, membership, or license. M8 nucleotide
panel membership does not automatically approve a protein collection or
profile set, and M8 roles/statuses are not rewritten by M9.

Before any real resource is retrieved or used, authorized reviewers must
approve:

1. Named curator/owner; scientific inclusion rationale; role/subrole and
   annotation provenance for every record/model; exact scope and exclusions.
2. Provider and exact release/accession/model versions, source terms, software
   and data licenses separately, attribution, privacy/locality, and any
   redistribution or local-build restrictions. Unknown/pending rights block
   acquisition/use until resolved.
3. Immutable snapshot membership and payload hashes, source-response hashes,
   model/profile and prepared-index hashes, builder/tool identities, validation
   counts, and the membership/exclusion/holdout manifest. A snapshot is complete
   only relative to its declared membership, not all relevant biology.
4. Per-role search plan, exact query/report settings, thresholds and their
   provenance, required branches, technical output/resource caps, and the
   policy for incomplete or excluded records.

No large biological protein or profile database is selected, retrieved,
bundled, or authorized by this contract. Snapshot updates create a new
versioned snapshot and membership/hash diff; they never mutate a snapshot
already named by a result.

## 6. Outcomes, accounting, and no-hit semantics

Keep candidate-input validity, ORF enumeration, query applicability, snapshot
validity, execution state, evidence result, and aggregate completion as
separate typed fields. A canonical branch outcome may summarize these axes
using the fail-closed meanings below, but it must not erase their individual
states or reasons. Do not reuse the M8 status vocabulary where M9 snapshot
semantics differ.

### 6.1 ORF and branch outcomes

| Scope | Canonical value | Meaning |
| --- | --- | --- |
| ORF enumeration | `ORF_PREDICTED` | Enumeration completed under the declared policy and emitted one or more hypotheses. Not expression or function. |
| ORF enumeration | `NO_ORF_PREDICTED_WITHIN_POLICY` | Enumeration completed and emitted zero hypotheses under the recorded policy. Not a noncoding conclusion. |
| Branch | `SEARCH_COMPLETED_MATCHES_REPORTED` | Valid informative branch completed with one or more reported rows and complete accounting. Weak rows remain qualified; if accounting is incomplete, retain rows with `SEARCH_TRUNCATED`, not this completed status. |
| Branch | `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` | Valid informative query and complete declared snapshot were fully accounted and parsed with no reportable row under the exact named method/settings. Scope is that query, method, and snapshot only. |
| Branch | `INSUFFICIENT_INFORMATION` | A predeclared, reviewed technical rule says this query/method cannot support an informative search. Preserve query and reason; not a no-hit. |
| Candidate/branch | `CANDIDATE_SEQUENCE_UNAVAILABLE` | Valid upstream identity exists but sequence bytes are unavailable. Preserve the candidate and reason. |
| Candidate/branch | `INPUT_INVALID` | Candidate identity, alphabet, hash, manifest, or contract is malformed or contradictory. Do not accept derived evidence. |
| Snapshot | `REFERENCE_SNAPSHOT_INVALID` | Manifest, membership, payload, index, model, or hash validation fails. No valid no-hit may be emitted. |
| Snapshot | `REFERENCE_SNAPSHOT_INCOMPLETE` | Required declared membership or payload is known missing/incomplete. Retain any positive rows as incomplete-scope evidence; no scoped no-hit. |
| Execution | `DEPENDENCY_UNAVAILABLE` | Required executable, runtime, builder, or index is absent or unusable. |
| Execution | `SEARCH_FAILED` | Nonzero execution, malformed/contradictory output, parser failure, or output validation failure prevents complete accounting. |
| Execution | `SEARCH_INTERRUPTED` | Timeout, cancellation, or other stop before complete accounting. |
| Execution | `SEARCH_TRUNCATED` | A reached or externally applied hit/target/HSP/row/byte/output/resource cap prevents complete accounting. |
| Lifecycle | `NOT_SELECTED`, `NOT_APPLICABLE`, `NOT_STARTED`, `RUNNING` | Planning or execution lifecycle only; none is a successful negative result. |
| Protein branch | `NOT_RUN_NO_ORF` | No protein query exists because completed ORF enumeration emitted zero hypotheses. Not a no-hit. |
| Aggregate | `COMPLETE` | ORF enumeration completed and every required, applicable query branch completed with `SEARCH_COMPLETED_MATCHES_REPORTED` or `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`. When no ORF exists, `NOT_RUN_NO_ORF` is expected accounting for non-applicable protein branches, not a no-hit or an automatic partial result. |
| Aggregate | `PARTIAL` | Any required and applicable branch is missing, unselected, uninformative, invalid, unavailable, failed, interrupted, or truncated, or accounting is incomplete. A completed no-ORF assessment alone is not partial; preserve completed branch results. |

ORF enumeration also requires an explicit technical failure/input state when
it cannot complete; such failure is never `NO_ORF_PREDICTED_WITHIN_POLICY`.
Each candidate receives a candidate-level accounting record even when it has
no sequence bytes or no ORF. For each selected search plan, account for every
candidate/ORF query × method × role × snapshot branch, including no-row queries.
Do not infer HMMER or BLAST no-hit from the absence of a row in a hit table.

Precedence is fail-closed: invalid candidate or snapshot, unavailable
dependency, failed/interrupted execution, incomplete accounting, and
truncation cannot become a completed no-hit. If the snapshot is incomplete,
positive matches may be retained with the incomplete-scope status, but an
aggregate cannot be `COMPLETE`. An aggregate is complete only relative to the
required branch plan declared before execution and the queries applicable to
that candidate; it does not mean biologically complete. For a candidate with
zero ORFs, a selected BLASTX branch remains independently applicable, while
BLASTP and HMMER retain `NOT_RUN_NO_ORF`. If BLASTX was not selected, its
lifecycle state remains visible without becoming a required search.

### 6.2 No-hit boundary

`SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` means only that a
specific informative query completed against the exact valid, complete named
snapshot and reported no row under the recorded method, threshold, masking,
composition, and reporting settings. It does not mean that no homolog exists,
that all relevant references were included, or that the candidate is novel,
noncoding, nonviral, non-satellite, or functionless. A no-ORF state, a
not-selected branch, a failure, an incomplete snapshot, and insufficient
information are not no-hits.

## 7. Normalized evidence records

All normalized records use deterministic ordering, stable IDs, explicit nulls,
declared coordinate conventions, and a versioned schema. Preserve raw output
and safe invocation provenance by content hash and stable artifact reference.
Do not store credentials or secret environment values in commands or manifests.

### 7.1 Candidate, ORF, and translated protein fields

Every candidate result retains:

- Candidate/sequence IDs; exact original sequence SHA-256 and length; FASTA
  record ID; declared molecule type and completeness; source-artifact identity;
  M6 evidence links/statuses; and any supplied M7/M8 artifact identities,
  hashes, and unresolved states.
- Candidate byte-availability state and reason, ORF policy identity, ORF
  enumeration status, expected/observed ORF counts, and any technical
  truncation or failure.

Every ORF/protein row retains:

- Stable `orf_id`; candidate and sequence IDs; exact source sequence hash and
  length; strand, frame, zero-based half-open original-sequence coordinates,
  start codon/coordinates, stop codon/coordinates if present, and partial
  flags.
- Translation-table identifier, start/stop sets, initiator handling,
  ambiguous-codon policy, sequence-orientation/U/T view policy, enumerator
  identity/version, configuration and derivation digest, and overlap/nesting
  relationships or enough source coordinates to derive them deterministically.
- Exact protein artifact/FASTA record ID, amino-acid sequence hash and length,
  and positions of `X` or other explicitly represented ambiguous residues.
  The amino-acid bytes are derived evidence; they do not replace nucleotide
  bytes.

### 7.2 Protein-alignment evidence

Each BLASTP or BLASTX row records:

- Candidate ID, source nucleotide hash, ORF/protein query ID and hash when
  applicable, query length, method/branch, role, snapshot ID and digest,
  reference stable ID/accession-version, reference sequence hash/length, and
  reference metadata provenance.
- Program/task, exact tool and database-builder identity, scoring and
  composition/masking settings, reporting thresholds, cap values, parser
  identity, branch status/accounting, and raw-output artifact reference/hash.
- HSP ordinal; query and reference coordinates with convention; strand and
  translation frame where applicable; aligned length, identity, positives
  when available, mismatches, gaps/gap opens, query/reference coverage values
  and denominators, raw and bit scores, and E-value or method statistic as
  reported (nullable only when undefined).
- Tie/competition and partial/weak/short/composition-sensitive flags or
  explicit warnings. Retain all rows the selected branch reports; do not
  reduce evidence to a top hit.

For BLASTX, keep the original nucleotide query identity and frame/coordinates
with the translated alignment. Do not store the BLASTX translation as a
canonical ORF or merge it into the ORF table.

### 7.3 Profile/domain evidence

Each HMMER table/domain row records:

- Candidate and ORF/protein query identities/hashes/length; profile collection
  and snapshot ID/digests; model stable ID/accession/version/hash/length;
  profile/source provenance and role; tool, index-builder and parser identities.
- Sequence-level and domain-level bit scores, E-values and bias; model
  threshold value/source/type (including gathering/curated threshold where
  used); query, HMM, alignment, and envelope coordinates; model and query
  coverage values/denominators; domain ordinal/count; and weak/partial/
  composition or filter warnings.
- Branch status, query accounting, competing/overlapping model IDs, raw
  `tblout`/`domtblout` references and hashes, and all selected filter and
  reporting settings.

Retain raw tool output even when parsing fails or output is partial, subject to
declared safe byte limits. A missing raw output, unexpected query, malformed
row, or mismatched output hash is an accounting/validation failure, not an
empty result.

## 8. Stage-scoped reuse and cache dependencies

Use the current stage-scoped cache mechanism described in the
[pre-M9 identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md): M9 implementation
identity, its exact stage registration metadata, declared input descriptors,
configuration, dependency inspection, named contract semantic versions, and
the shared workflow-cache semantics version. Do **not** use the package-wide
source hash as M9's scoped implementation identity and do not hash the entire
workflow registry or unrelated shared contract definitions. Adding M9 must not
invalidate M6, M7, or M8 outputs.

The M9 semantic identity must include every output-affecting dependency:

1. Exact candidate sequence bytes/hash, candidate/sequence identity links,
   declared molecule/completeness metadata, and relevant supplied M6 artifact
   digests. Include supplied M7/M8 artifact digests when their provenance is
   emitted or otherwise affects M9 output.
2. ORF enumerator and normalization semantics; start/stop/partial policy;
   genetic-code table/version; ambiguity and U/T-view policy; derived protein
   serialization/schema; and relevant contract-validator semantic versions.
3. Per-branch program/task, all search/scoring/masking/composition/filter/
   threshold/report settings, thread/resource/cap policy, required-branch plan,
   tool and builder versions/executable identities, parser/normalizer/
   aggregator identities, and output schema semantics.
4. Exact protein/profile snapshot manifests and membership/exclusion hashes,
   sequence/model payload hashes, taxonomy/annotation snapshot hashes when
   used, prepared index hashes, and all source/license state that is serialized
   into result provenance.
5. M9-only stage implementation and registration identity. Keep translation
   derivation and reference-dependent search as separate cache dependency
   scopes so a protein/profile snapshot change does not invalidate unchanged
   ORF/protein derivation. A single workflow registration is acceptable only
   if its scoped identities prove this invalidation boundary.

Timestamps are provenance, not substitutes for content identity. Reuse only
when the complete semantic key and output verification match. Read-only reuse
must fail closed on changed inputs, tool/profile/snapshot identities,
implementation semantics, or corrupted raw/normalized outputs. Version bumps
for shared cache behavior and named contract semantics follow the explicit
rules in the audit; do not reintroduce broad source hashing.

## 9. Required software-validation matrix

This matrix defines implementation acceptance tests. In particular,
no-ORF and incomplete-search cases are required tests during implementation;
they are not separate prerequisites that delay approval of the baseline.
All baseline and optional method tests must be offline and use deterministic
synthetic nucleotide/protein fixtures and artificial profile alignments only.
Pin fixture digests, tool versions/executable identities, commands, and parser
versions. The matrix validates software accounting and normalization, not
biological sensitivity or specificity. Conditional branch tests apply only if
that optional branch is included.

| Area | Required synthetic coverage |
| --- | --- |
| Candidate handoff and preservation | Available, partially available, unavailable, invalid, and complete-empty candidate sets; exact source-byte/hash preservation; duplicate sequence bytes with distinct IDs; identity, provenance, and unresolved M6/M7/M8 states; M8 hit, scoped no-hit, insufficient-information, and failure each leave valid candidates eligible. |
| ORF enumeration | All six frames and both strands; original-coordinate mapping; nested starts and overlapping ORFs; two-residue and other short ORFs retained; complete, 5′ partial, 3′ partial, no-ORF, ambiguous codon to `X`, configured alternative start, code-table variation, no stop, terminal incomplete codons, no candidate mutation, and deterministic repeatability. |
| Translation artifacts | Exact derived protein bytes/hash; code/start/partial/ambiguity provenance; distinct ORF identities for same peptide from different loci or policies; zero-protein output validly represented without an empty search masquerading as no-hit. |
| Core BLASTP branch | Ordinary local BLASTP adapter, contracts, and parser; exact, partial, weak/random, short, low-complexity, masked/unmasked, composition-setting, duplicate-reference tie, competing-role, and multiple-HSP fixtures; normalized coordinates/coverage/statistics; deterministic repeated rows with pinned single-thread settings. |
| Optional BLASTP-short branch | If included, verify that it remains a separately identified task from ordinary BLASTP, with distinct settings, accounting, and results; do not treat its scores or E-values as calibrated to ordinary BLASTP. |
| Optional BLASTX branch | If included, test a six-frame translated hit without a canonical start; frame and nucleotide-coordinate normalization; separate code/settings/snapshot identity; no retroactive ORF creation; branch lifecycle and query accounting. |
| Optional profile-HMM branch | If included, use an artificial `hmmbuild`/`hmmpress`/`hmmscan` fixture; test full, partial, weak, competing, and no-row queries; default filter behavior and separately named bias/null2/max sensitivity modes; sequence/domain coordinates and thresholds; unpressed/corrupt profile failure; expected-query accounting independent of reported hit rows. |
| Status and completeness | Valid complete no-hit versus insufficient information, no-ORF, no-query, invalid candidate, unavailable dependency, invalid/incomplete snapshot, failed parser/execution, interruption, target/profile/output cap, post-capture truncation, and partially completed required branch. Verify none can be relabeled as complete no-hit or `COMPLETE`. |
| Raw outputs and artifacts | Safe argv, raw stdout/stderr/table hashes and links, malformed/contradictory rows, missing output, output-byte limits, deterministic normalization, serialization, and read-only integrity validation. |
| Cache identity and reuse | Candidate bytes, ORF/code policy, method/settings, tool/parser identity, protein/profile snapshot/membership/index, M9 contract/implementation/registration changes invalidate the affected M9 scope; unrelated M9 changes do not invalidate unchanged derivation where separable; M9-only additions preserve M6/M7/M8 keys; corrupt/stale outputs reject reuse. |

Synthetic methods tests must not download or search biological resources. A
later biological benchmark is a separate human-approved project: predeclare
curated labels, independent holdouts/leakage controls, positive/negative
definitions, length/composition/family strata, metrics, and error costs before
any evaluation. Synthetic software success cannot be reported as biological
validation, sensitivity, specificity, or candidate classification.

## 10. Decision and approval register

“Blocks implementation” below distinguishes the approved synthetic/offline
baseline from production configuration or real reference use. This contract
approves implementation of the ORF/translation baseline and ordinary BLASTP
adapter/contracts/parser with synthetic fixtures. It does not approve
biological reference retrieval, real searches, or biological thresholds.
Unresolved resource-specific approvals block only the corresponding real
resource retrieval or search.

| Decision | Status | Supporting evidence | Selected baseline | Remaining human approval | Blocks implementation? |
| --- | --- | --- | --- | --- | --- |
| M9 scope and claims | **Approved for baseline software implementation** | Current [roadmap](ROADMAP.md); synthetic-only method review; M8/M6 boundaries. | Protein-level evidence only; no standalone satellite, novelty, helper-dependence, function, expression, or biological-class conclusion. | No further approval for the approved synthetic/offline baseline; production biological use remains gated below. | **No** for baseline implementation; biological use remains separately gated. |
| Candidate source and eligibility | **Approved baseline** | Implemented M6-to-M8 typed handoff; M8 eligibility does not require read support; M9 architecture context. | Exact M6 candidate bytes/IDs and provenance; M7/M8 are optional context and never eligibility gates. | Preserve the frozen handoff and preservation rules during implementation. | **No** for baseline implementation. |
| ORF method, code, starts, and partials | **Approved for baseline synthetic/offline implementation** | Six-frame synthetic enumerator retained nested, small, reverse, partial, and ambiguous cases; code changes outcomes. No biological length/code threshold validated. | Linear six-frame enumeration; table 1; ATG-only complete starts; first definite stop; both explicit boundary-partial policies; no biological minimum; ambiguity to `X`. | Human approval is required before production use of this policy; alternative policies require separate review and approval. | **No** for synthetic/offline implementation; **yes** before production use of the selected policy. |
| Core protein similarity baseline | **Approved for baseline synthetic/offline implementation** | Synthetic BLASTP repeated deterministically; ordinary and short-task results differed; caps hid tied targets. | Local ordinary BLASTP adapter/contracts/parser, SEG enabled, explicit composition settings; short-task and unmasked/composition alternatives separate and optional. | Approve exact production executable/build, report thresholds, caps, required branches, and any short-query applicability rule before real searches. | **No** for baseline implementation; **yes** for production search configuration. |
| Optional BLASTP-short branch | **Optional; not a baseline gate** | Synthetic ordinary and short-task results differed. | If implemented, keep it separately identified with its own settings and accounting. | Approve applicability rules and production parameters before real use. | **No** for core M9 implementation; **yes** before production execution of this branch. |
| Translated nucleotide branch | **Optional; not a baseline gate** | Synthetic BLASTX reported a six-frame hit without an ORF start codon. | Separate optional BLASTX against an approved protein snapshot; never an ORF confirmation. | Approve whether it is selected/required, its code, parameters, limits, and snapshot before production use. | **No** for core M9 implementation; **yes** to execute this branch against real resources. |
| Profile-HMM branch | **Optional; not a baseline gate** | HMMER synthetic runs repeat; filters changed rows/scores; missing index failed; machine tables omit explicit no-hit query rows. | Optional local `hmmscan` against approved indexed profiles; synthetic contracts/parsers may be added if justified; explicit filter and query accounting. | Approve exact real profile source/membership/terms, index, threshold, and settings before retrieval or execution. | **No** for core M9 implementation; **yes** to retrieve or execute a real profile branch. |
| Protein/profile roles and membership | **Open human approval** | M8 reference policy offers role-separated precedent; no M9 resource or membership was approved or searched. | Separate immutable role-labelled protein and profile snapshots; no role-based candidate labeling. | Name curator; approve source, role, release, membership, exclusions, metadata and holdouts. | **No** for synthetic-only implementation; **yes** before any biological retrieval/use. |
| Licensing and distribution | **Open human approval** | Software and database terms are independent; exact resource records may have distinct terms. | No automatic download/bundling; local immutable caller-supplied snapshots only after review. | Verify exact tool/dependency and every resource's terms, attribution, privacy, redistribution/local-build status. | **No** for synthetic fixtures; **yes** before retrieving or using real resources, and before redistribution. |
| Typed outcomes and no-hit | **Approved baseline** | M8 status/accounting contract plus M9 synthetic missing-row, cap, failure, and no-ORF observations. | Separate ORF, branch, snapshot, lifecycle, and aggregate fields; failure/incomplete/truncated/insufficient/no-ORF are distinct from no-hit. | Implement the approved status contract; do not reuse M8's snapshot status strings for M9. | **No** for baseline implementation. |
| Normalized fields and raw evidence | **Approved baseline** | M8 evidence-provenance model; empirical output and HMM table behaviors. | Preserve quantitative ORF/alignment/domain evidence, competing rows, raw-output hashes, and query-level accounting. | Schema names/serialization details are implementation work, subject to this required field set and versioning. | **No** for baseline implementation; no biological approval needed for schema implementation. |
| Cache identity | **Frozen baseline** | Merged [stage identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md) and `tests/test_stage_cache_identity.py`. | Stage-scoped keys; explicit M9 semantics and registration; separate derivation/search invalidation; no package-wide source hash. | Apply existing version-bump rules when implementation is added. | **No**; current mechanism supports M9 without changing M6–M8. |
| Operational thresholds and budgets | **Open for production use** | Synthetic permissive settings exposed weak rows; no biological E-value, score, length, memory, time, or hit cap was validated. | No biological cutoff selected; synthetic fixture settings are pinned for tests; every production technical threshold/limit is explicit, recorded, and truncation-aware. | Approve branch reporting thresholds, resource limits, output caps, timeout, and required-branch plan for each production profile. | **No** for synthetic/offline implementation; **yes** for production execution. |
| Alternative/remote methods | **Deferred** | DIAMOND differed from BLASTP on short synthetic queries; MMseqs2 unavailable/untested; CDD, InterProScan, and HH-suite untested. | Not a baseline dependency; no silent substitution or inferred method result. | Separate versioned method review and validation before later addition. | **No** for frozen baseline; **yes** before any deferred method is implemented or used. |
| Biological benchmark and claims | **Future human decision** | No biological benchmark was run; synthetic fixtures test software only. | M9 software validation remains separate from any blinded biological evaluation. | Approve labels, holdouts, leakage control, metrics, and claim-appropriate independent validation before biological performance claims. | **No** for baseline software implementation; **yes** for biological validation or performance claims. |

## 11. Freeze boundary and implementation gate

This contract is the approved M9 baseline for synthetic/offline software
implementation. M9 remains PLANNED / NOT IMPLEMENTED until that software is
built and validated. Implementation may proceed for the approved candidate
handoff, ORF/translation policy, ordinary BLASTP adapter/contracts/parser,
accounting, normalized evidence, and cache behavior using synthetic fixtures.
No biological resources may be retrieved or searched until the applicable
curator, source-term, license, snapshot, membership, threshold, and runtime
approvals in [§5](#5-reference-roles-snapshots-and-approvals) and
[§10](#10-decision-and-approval-register) are complete.

This freeze changes no README/roadmap status, M6–M8 behavior, upstream evidence,
or existing cache identity. It starts no M9 code, workflow registration,
artifact contract, test implementation, M10 work, biological candidate search,
or large database retrieval.

M9 baseline contract: APPROVED FOR IMPLEMENTATION