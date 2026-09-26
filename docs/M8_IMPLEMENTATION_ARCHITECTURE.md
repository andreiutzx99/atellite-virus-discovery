# M8 Implementation Architecture

**Status: design only.** This document maps the implemented M1–M7 codebase to a
future M8 nucleotide/reference-homology stage. It does not select reference
panels, approve redistribution, select a search engine or parameters, implement
M8, or change M1–M7 behavior.

**Inspected baseline:** `81ce4709e1670b3fcbe525723683f4dac7f4e3ff`.

## Recommendation

Add M8 as a trusted artifact-workflow stage consuming a typed candidate-sequence
handoff and immutable, role-specific reference-panel snapshots. Keep reference
membership, search execution, parsing, evidence, and lifecycle state explicit.
Reuse the current stage registry, artifact contracts, reference snapshot,
external-tool, and workflow-report infrastructure. Do not treat the existing
BLAST comparison stage as M8.

The current M6→M7 path does **not** guarantee sequence bytes for every contig
that M8 is intended to assess: M6 only copies its contig FASTA to the workflow
root when at least one contig passes support. The cleanest handoff is a new
logical M6 `candidate_sequence_set`, physically represented by a FASTA and a
checksum-bound manifest, emitted from valid assembly output before M6's
read-support promotion gate. Preserve the existing `supported_contigs.fasta`
contract and M7 recurrence semantics. M8 receives M7 recurrence/provenance as
optional context, not as its candidate list or an eligibility condition.

## 1. Existing components inspected

### Artifact and workflow contracts

- `satellite_discovery/artifact_contracts.py:19-75` defines the current stable
  contract names. It includes `reconstruction_evidence`, M6 read-support
  artifacts, and M7 observation, recurrence, validation, and provenance
  artifacts; it has no M8 contracts.
- `satellite_discovery/stage_registry.py:20-35,44-110` supplies the immutable
  `StageDefinition` and validates registered stage kinds, versions, input
  fields, artifact contracts, and handlers. Workflow data selects trusted
  registrations; it does not load arbitrary Python modules or shell commands.
- `satellite_discovery/artifact_workflow.py:45-236` builds the trusted registry.
  M7 is registered as `independent_recurrence` with dynamic, typed inputs
  (`177-189`); `workflow_report` declares its accepted artifact types
  (`190-207`); `blast_compare` is a separate supplied-reference comparison
  (`209-226`).
- The workflow validator checks stage handoffs against declared output and
  input contracts and rejects consumers of skipped stages
  (`artifact_workflow.py:343-405`). A future M8 stage should use those same
  checks, not open-ended paths or inferred artifact types.

### M6 and M7 sequence flow

- `satellite_discovery/residual_evidence_adapter.py:304-389` triages reads,
  runs assembly on the eligible residual reads, then evaluates read-back
  support. The root-level `supported_contigs.fasta` is copied only when the
  aggregate support state is `READ_SUPPORTED_ASSEMBLY` (`387-389`).
- M6 `reconstruction_evidence.json` records the sample, aggregate status,
  contig support records, assembler/QC/reference details, and residual-manifest
  provenance (`residual_evidence_adapter.py:455-474`). The contig records from
  `read_support.assess_read_support` contain IDs, lengths, support metrics, and
  status (`read_support.py:254-293`), not the sequence bytes.
- M6 support is intentionally evidence-sensitive: a contig is promoted only
  when distinct-read, fragment, breadth, and depth criteria are met
  (`read_support.py:243-269`). That is a support result, not an M8 eligibility
  rule.
- `satellite_discovery/independent_recurrence.py:39-52` declares M7's inputs
  and output contracts. `_m6_contigs` validates the FASTA against all declared
  contig IDs when aggregate M6 status is supported, but creates recurrence
  sequence rows only for `READ_SUPPORTED_ASSEMBLY` contigs (`326-393`). A
  non-supported aggregate rejects a supplied FASTA or any supported contig
  record (`343-354`). M7 computes exact and orientation-aware sequence hashes
  (`369-415`), but its output tables contain IDs, hashes, recurrence, and
  provenance—not sequence text (`928-980`).
- M7 carries declared candidate/sample/run/study IDs, M6 artifact and manifest
  links, missing-metadata state, and recurrence context
  (`independent_recurrence.py:435-547,815-825,934-980`). Unknown or conflicting
  metadata is retained as unresolved; it is not filled by inference
  (`550-584,872-879`).

### Reusable reference, tool, report, and test infrastructure

- `satellite_discovery/reference_snapshot.py:16-75,78-122` creates
  checksum-pinned snapshots of explicitly supplied files and verifies them
  read-only. It records supplied source/version/role metadata and never
  infers database completeness or biological suitability.
- `satellite_discovery/reference_record_import.py:398-459` materializes
  per-record sequence length, sequence hash, source, and parent-snapshot
  provenance. It reports duplicate/metadata conflicts rather than collapsing
  them and does not infer taxonomy, completeness, or suitability.
- `satellite_discovery/external_tool.py:84-206,218-260,286-436` provides a
  tool-agnostic trusted adapter base: dependency inspection, JSON-safe
  configuration, argv-only command construction, bounded execution, safe
  provenance, output validation, and explicit failure/interruption records.
  This is the preferred execution boundary for the selected initial local
  BLASTN baseline after its release and configuration are pinned and validated.
- `satellite_discovery/local_comparison.py:14-62,81-86` and
  `blast_import.py:1-60` are specifically BLAST+ and outfmt-6 oriented.
  The current comparison uses BLAST defaults, reports descriptive supplied
  matches, and has neither the M8 panel-completion model nor M8 evidence
  semantics. Its parser may be reusable for the initial BLASTN adapter only
  after its assumptions are validated; it does not provide M8 execution or
  panel/status handling.
- `artifact_workflow.py:504-558` fingerprints stage version, normalized
  configuration, typed input digests, dependency report, and implementation
  identity; it reuses only complete stages with verified manifests and outputs.
  `artifact_stage_handlers.py:327-555` and
  `artifact_workflow.py:721-855` provide consolidated descriptive reports.
- `satellite_discovery/artifact_benchmark.py:9-73` verifies fixture digests and
  accounting; it does not search sequences, estimate sensitivity, or validate
  biological interpretation. Synthetic M8 software fixtures must remain
  separate from later blinded biological validation.

## 2. Frozen M6 candidate and optional M7 input contract

The present M7 output cannot be the sole M8 input: M7 deliberately receives only
supported contigs and does not emit their sequence bytes. M8 should receive:

1. **Required candidate sequence set:** a typed, checksum-bound logical
   `candidate_sequence_set`, physically a FASTA plus a manifest mapping each
   FASTA ID to a stable `candidate_id`, `sequence_id`, exact sequence SHA-256,
   length, declared molecule type, completeness state, and source artifact.
   Candidate IDs must be producer-declared. M8 must not derive identity from
   sequence equality or merge candidates because their sequence hashes match.
2. **Required M6 evidence linkage when the candidate came from M6:** retain the
   M6 reconstruction state, per-contig support state, source M6 artifact
   digests, residual-manifest/QC/reference links, and M6 manifest identity.
   Emit valid assembled sequences before the read-support promotion gate, while
   leaving `supported_contigs.fasta` and its current meaning unchanged. If
   assembly was not attempted or failed and no sequence bytes exist, M8 must
   preserve that upstream state; it must not invent an empty candidate set or a
   completed no-hit.
3. **Optional M7 context:** supply matching `m7_observation_table`,
   `m7_exact_recurrence_table`, and `m7_provenance_manifest` as separate typed
   M8 inputs when available. The M6 candidate-set artifact cannot embed M7
   context. Link by explicit candidate and sequence IDs plus sequence hash;
   preserve the original M7 records and their artifact digests. A missing M7
   input means “no M7 link available,” not “no recurrence.” Recurrence cannot
   qualify an unsupported sequence or upgrade its M6 support state.
4. **Declared metadata:** carry `sample_id`, `sequencing_run_id`, and
   `study_id` only when present in the source artifacts. Keep missing or
   conflicting values explicitly unresolved. Do not infer a run from a sample,
   study from a run, or candidate identity from a match.

The M8 boundary is candidate sequence bytes only. It consumes no FASTQ or SAM,
does no read pooling, and never invokes assembly. Each candidate remains a
separate query even when execution batches several queries.

## 3. Proposed minimal modules and interfaces

Names below are proposed future additions, not existing APIs.

| Proposed component | Responsibility |
| --- | --- |
| `m8_reference_panels.py` | Validate approved panel membership, role-specific snapshot manifests, licensing/provenance fields, sequence hashes, and index-build identity. Reuse M2 file snapshots and record imports; do not choose or download panels automatically. |
| `m8_search_adapters.py` | Define the narrow nucleotide-search adapter contract and later provide only the approved concrete implementation. Keep executable discovery, database/index construction, invocation, and tool-specific parsing behind trusted code. |
| `m8_homology.py` | Validate the typed candidate and panel inputs, execute candidate × panel × method branches, parse and normalize results, account for all work, and emit M8 evidence/status artifacts. |
| Existing `artifact_contracts.py` | Add versioned contracts and validators for candidate sequence FASTA/manifest and M8 panel, search, match, query-status, summary, and raw-output artifacts. |
| Existing `artifact_workflow.py` | Register the trusted M8 stage and its exact input/output contracts; wire it into workflow declarations without making M8 a dependency of M6 or M7. |
| Existing `artifact_stage_handlers.py` | Extend consolidated reporting to show M8 execution scope, status counts, provenance, and limitations without classification or ranking. |

Prefer one logical typed candidate artifact over a new orchestration framework.
The manifest and FASTA are separate physical files so sequence bytes need not
be duplicated inside JSON. The workflow stage should consume them as declared
artifact inputs with exact contracts. Keep M7 unchanged: it remains an
independent recurrence analysis over its existing supported-contig contract.

## 4. Reference snapshot contract

An M8 panel manifest should extend—not replace—the existing M2 checksum-pinned
snapshot contract. Each immutable, role-specific manifest should bind:

- schema/version, `panel_role`, subrole, snapshot ID, parent snapshot, and a
  content-derived manifest digest;
- source/provider, exact release/build, retrieval time and method, source
  response/file hashes, cited provenance, and per-record accession.version or
  local record ID;
- each stable reference ID to exact sequence SHA-256, length, declared
  molecule/alphabet, source metadata, and license/redistribution state;
- declared included, excluded, duplicate, withdrawn, superseded, and
  benchmark-withheld membership with reasons;
- index/database builder identity, command, parameters, database/index hashes,
  and validation/completeness accounting.

Logical panels must remain separate search scopes with separate membership
digests, even when they refer to one shared content-addressed sequence store.
This avoids duplicating identical sequence bytes without collapsing panel
provenance or comparing scores across different search spaces. A snapshot is
complete only relative to its declared membership; it does not certify
biological completeness. New membership or source releases create new
snapshots, never mutate snapshots already cited by results.

The separate reference-panel policy supplies the role-level framework and
source/acquisition recommendations. Exact snapshot membership and release
pins, local materials, per-record license and redistribution decisions, and
curation ownership still require human review. This architecture selects none
of those records or terms.

## 5. Search-adapter contract

The workflow registry—not workflow JSON—selects a trusted adapter. The adapter
must provide equivalent capabilities to:

- inspect the required executable/runtime and report
  `available` or `dependency_missing` with exact tool identity/version;
- build or verify an index only from the validated immutable snapshot;
- run a named nucleotide query against one panel and declared method branch;
- return raw output and safe structured invocation provenance;
- parse output through a deterministic parser that can be tested without the
  external executable.

Record adapter name/version, executable or container digest, database-builder
identity, panel/index digest, parameters, masking and strand/query mode,
reporting limits, safe command arguments, environment identity, input hashes,
raw stdout/stderr/output hashes, and expected/completed/unaccounted work.
Use the existing argv-only `ExternalToolAdapter` process boundary for bounded
execution, timeout, output-size limits, dependency gating, and manifest
validation. Do not accept arbitrary command strings or module names from a
workflow document.

Keep the interface nucleotide-only. The initial method baseline is local,
pinned BLASTN, as selected by the reference-panel policy. The exact BLAST+
release, short-query task, parameters, masks, result caps, and
method-specific applicability rules still require review and benchmarking.
Use a documented short-query-aware mode such as `blastn-short` only when
technically appropriate; current BLAST defaults must not silently stand in
for an approved configuration. Alternative aligners require an explicit
method identity and comparative validation.

## 6. Match-evidence contract

Use one query-level execution record per candidate × panel × method branch and
one normalized evidence record per reported hit/HSP. Preserve raw output by
content hash and stable artifact reference. The typed evidence should include:

- candidate ID, sequence ID/hash/length, molecule type, declared completeness,
  upstream M6 status/support and M6 artifact digests, plus optional M7
  observation/recurrence/provenance references;
- panel role, snapshot and manifest hashes, panel/index state, reference ID and
  exact reference hash/length, and source/taxonomy/license metadata with its
  provenance;
- method, adapter/tool/version and executable/container identity,
  parameters, branch/masking settings, implementation/parser identity, and
  reporting caps/truncation state;
- strand, query/reference coordinates and coordinate convention, aligned
  bases, identities, mismatches/gaps, query and reference coverage with
  denominators, score and method-specific significance value (nullable if
  undefined), HSP order, and raw-output reference/hash.

Keep absolute aligned bases and both coverage denominators so short and partial
matches remain interpretable. Retain competing hits and all panel identities;
do not choose a winner by comparing scores across panels. Do not add a
`SATELLITE`/`NOT_SATELLITE` field or infer identity, origin, function,
dependence, contamination, or novelty.

## 7. Status model

Store input suitability, panel validation/completeness, execution outcome, and
reported evidence separately. Use the proposed specification's per
candidate × panel × method-branch outcomes:

- `SEARCH_COMPLETED_MATCHES_REPORTED`
- `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`
- `INSUFFICIENT_INFORMATION`
- `DEPENDENCY_UNAVAILABLE`
- `SEARCH_FAILED`
- `SEARCH_INTERRUPTED`
- `REFERENCE_PANEL_INVALID`
- `REFERENCE_PANEL_INCOMPLETE`
- `INPUT_INVALID`

`NOT_SELECTED`, `NOT_APPLICABLE`, `NOT_STARTED`, and `RUNNING` are lifecycle or
scope values, not successful searches. The scoped no-hit is valid only after
input and snapshot validation and full accounting of the declared search.
Missing dependencies, parser errors, truncation, interruption, or an incomplete
panel can never become zero hits or a biological negative. Aggregate status is
`PARTIAL` whenever a required panel or branch did not complete. This preserves
the execution/evidence distinctions already specified in
`docs/M8_REFERENCE_AND_HOMOLOGY_SPEC.md:286-322`.

## 8. Short-sequence engineering review

| Existing location | Current behavior | M8 consequence |
| --- | --- | --- |
| `satellite_discovery/quality_control.py:18-35,101-126`; CLI default at `cli.py:25` | Read QC has a default `min_length=30` and retains rejected reads as rejected records. | This is an upstream read filter, not an M8 candidate-length rule. It may limit which short reads reach assembly; M8 must report the available candidate set and not imply it searched excluded reads. |
| `residual_evidence_adapter.py:28,172-198`; `residual_reads.py:310-318` | M6 residual-read triage defaults to `min_length=50` for assembly eligibility. | Also a read-level assembly gate. M8 cannot reverse it or treat its output as candidate sequence absence. |
| `sequence_catalogue.py:23-89,147-152` | Catalogue rejects empty sequences and applies record/base resource caps, but no positive minimum sequence length; measurements do not reject records. | Reusable sequence input behavior, but M8 still needs explicit identity/alphabet/integrity validation. Preserve every valid short candidate. |
| `blast_import.py:10-45,52-60` | BLAST outfmt-6 parser requires positive lengths and valid coordinates, not a biological minimum. | Potential parser reuse for the initial BLASTN adapter only after validating its assumptions; it does not provide M8 execution or panel states. |
| `local_comparison.py:35-62` | Existing BLAST+ call has tool defaults and no explicit short-query task, word size, masking, or M8 reporting policy. | Short alignments may be missed or filtered by tool defaults. Make method applicability/configuration explicit and test it; do not silently inherit defaults. |

M8 must not impose a length-only eligibility cutoff. A technically valid short
query remains in the evidence record even if the approved method reports
`INSUFFICIENT_INFORMATION`; preserve any real raw match and its limitations.
Test the approved method on the fixed short-query and low-complexity fixtures.
Do not turn the fixture-only 32-nt warning in
`docs/M8_BENCHMARK_FIXTURE_DESIGN.md:52-54` into a production threshold.

## 9. Reuse and invalidation graph

```text
candidate FASTA/manifest change ───────────────┐
panel membership/snapshot/index change ────────┤
tool/dependency/parameters/branch change ──────┼─> invalidate affected M8 search
runner/parser/normalizer/schema change ────────┘
                                                   └─> refresh M8 summary/report

M6 candidate input and configuration ──> M6 candidate artifact
M6 evidence + supported FASTA ──────────> existing M7 recurrence
M8 panel or search changes ─────────────X─> must not rerun M6 or M7
```

Declare candidate sequence, panel manifest, index identity, tool/dependency
report, parameters, parser/runner identity, and output schema as M8 stage inputs
or configuration. `artifact_workflow._stage_cache_key`
(`artifact_workflow.py:504-524`) already fingerprints typed input hashes,
configuration, dependency report, stage version, and implementation identity.
Verified reuse requires a complete prior stage with valid manifest and output
hashes (`artifact_workflow.py:527-558`). The consolidated workflow report
declares M8 artifacts as inputs so it can refresh when M8 changes while M6/M7
remain reusable.

**Cache isolation risk:** absent a handler-provided
`cache_implementation_identity`, the workflow key also includes the
package-wide source hash (`artifact_workflow.py:505-521`). An M8 code/parser
edit under the package can therefore invalidate ordinary M6/M7 stage keys even
when their inputs are unchanged. Give new M8 code a scoped implementation
identity and resolve the package-wide identity behavior for affected existing
stages before relying on code-change-only reuse. Independently, a
reference-snapshot data change must remain an M8 input only and must never be
added to M6/M7 inputs. Add an integration test proving those stages report
verified reuse after an M8-only panel change.

## 10. Workflow and report integration

Register a versioned M8 stage in `artifact_workflow.build_default_registry`
using `StageDefinition` contracts and the selected trusted adapter. Require an
explicit candidate-set input and immutable panel manifest; declare optional
M6/M7 context with exact artifact types. Reject mismatched IDs, hashes, or
contracts before execution. Do not create implicit M6/M7 dependencies on M8.

Add M8 contract types to `workflow_report`'s accepted input list and extend
`artifact_stage_handlers.workflow_report` to report:

- requested, completed, not-selected, incomplete, and unaccounted
  candidate/panel/branch counts;
- linked candidate, panel, tool, raw-output, and manifest identities;
- matches and scoped no-hits as descriptive similarity evidence;
- invalid, unavailable, failed, interrupted, or insufficient-information
  outcomes and explicit limitations.

The report must not rank panel roles, label candidate biology, or summarize
partial execution as a no-hit. Keep raw tool output and normalized evidence
linked from machine-readable `report.json` and human-readable `report.html`.

## 11. Concrete future test plan

Use fixed synthetic FASTA literals and the fixture classes in
`docs/M8_BENCHMARK_FIXTURE_DESIGN.md`; no live databases or network are needed
for software tests.

1. **Handoff and eligibility:** valid supported, low-support, unsupported,
   ambiguous, partial, and unresolved candidate records retain their exact IDs,
   bytes, hashes, M6 state, and metadata. Verify no M8 eligibility check
   requires `READ_SUPPORTED_ASSEMBLY`; M7 links are optional and never promote
   support. Reject corrupt bytes, hash mismatch, duplicate/conflicting IDs, and
   invalid declared alphabets distinctly.
2. **Panel validation:** valid frozen manifest; same physical sequence in two
   panel roles; invalid file/record/manifest hashes; incomplete build; withheld
   record exclusion; duplicate/accession conflicts; license state retained.
   Verify one panel’s failure does not erase completed results for another.
3. **Adapter and parser:** injected fake adapter for exact match, no-hit,
   reverse complement, partial HSP, competing hits, malformed output,
   truncation, missing dependency, nonzero exit, timeout, and interruption.
   Assert failed or incomplete accounting can never return
   `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`.
4. **Short/composition cases:** fixed short candidate, low-complexity repeat,
   ambiguous bases, and partial fragment. Assert no candidate is dropped for
   length alone; output retains lengths, coordinates, both coverage
   denominators, masking branch, and any raw hit.
5. **Determinism and reuse:** identical inputs reuse only verified output;
   candidate, panel membership, index, tool version, parameters, parser, or
   schema changes invalidate M8; corrupted saved output fails closed. Change
   only an M8 panel and verify M6/M7 are verified-reused and their output
   hashes remain unchanged.
6. **Workflow/report boundaries:** typed handoff rejects wrong contracts and
   skipped stages; reports preserve missing M7 links and explicit partial
   status; no FASTQ/SAM input, read pooling, assembly invocation, biological
   classification, or cross-panel score winner occurs.
7. **Blinded benchmark readiness:** test exact and close relatives, family/clade
   holdouts, study leakage checks, and exclusion-manifest identity as separate
   audit fixtures before labels are opened. Synthetic software fixtures do not
   substitute for M16 blinded validation.

Existing hooks include typed M6→M7 handoff and provenance tests
(`tests/test_independent_recurrence.py:410-515`,
`tests/test_residual_evidence_adapter.py:689-713,745-755,839-868`), reusable
external-adapter failure/reuse tests
(`tests/test_external_tool_adapters.py:19-60,63-323`), and reference snapshot
integrity tests (`tests/test_conditional_tools.py:46-68`).

## 12. Safe parallelism

After a panel index is fully built and verified, independent
candidate × panel-role × method-branch searches may run concurrently. Keep each
invocation's temporary directory, raw output, status, and accounting isolated;
share only immutable read-only indexes. Apply bounded worker, process, memory,
runtime, and output limits through the adapter.

Sort normalized outputs deterministically by candidate ID, panel role,
method/branch, reference ID, and HSP ordinal. Aggregate only after all expected
work is accounted for. Do not share a mutable database builder between workers,
deduplicate evidence across candidate IDs, compare scores across panel search
spaces, or let one interrupted branch erase already completed independent
results. Concurrency limits and tie/truncation behavior must be part of the
declared configuration and identity.

## 13. Likely implementation order

1. Apply the panel policy's role framework and local BLASTN baseline. Complete
   human review of exact panel membership, source terms, and redistribution;
   pin and validate the exact BLAST+ release, search branches, parameters,
   result caps, and output contracts before implementation.
2. Freeze the candidate ID/sequence ID crosswalk and typed all-candidate M6
   export. Add its contract without changing the meaning of the existing
   supported-contig output or M7 recurrence.
3. Specify and test role-specific immutable panel manifests using M2 snapshot
   and record-import primitives; include licensing and holdout metadata.
4. Implement the adapter protocol and fake adapter/parser tests. Add the
   initial local BLASTN adapter after its exact release, runtime, and
   configuration are reviewed; alternative methods require comparative
   validation.
5. Implement the M8 stage, status accounting, raw/normalized outputs, and
   stage-scoped cache identity.
6. Register M8 and extend the consolidated report; prove M6/M7 reuse for an
   M8-only input change.
7. Complete deterministic offline fixtures, then separately conduct the
   predeclared blinded biological benchmark. Do not start M9 as part of M8.

## 14. Risks and open questions

- **Candidate identity:** M6 currently exposes contig IDs, while M7 carries
  declared candidate IDs for supported observations. Freeze an explicit
  candidate-ID/sequence-ID crosswalk for weak or unsupported contigs; do not
  join candidates by sequence hash alone.
- **Unavailable sequence bytes:** M8 cannot search a failed, unattempted, or
  absent assembly. Preserve that upstream state and candidate accounting rather
  than claiming the candidate set was empty or searched.
- **Reference policy:** the separate policy supplies role-level and
  source/acquisition recommendations; exact snapshot membership, release pins,
  local-only materials, per-record terms, redistribution, and curators still
  require human review. Do not download or bundle a database before those
  decisions.
- **Method policy:** local BLASTN is the initial baseline. Exact BLAST+ version,
  short-query settings, masking, significance reporting, caps, and
  method-specific `INSUFFICIENT_INFORMATION` rules require review and
  benchmark evidence.
- **Cache granularity:** package-wide source identity can invalidate M6/M7 on
  unrelated Python edits. Resolve stage-scoped identity before M8 code changes
  are relied on for isolated reuse.
- **Scientific scope:** a sequence match is not identity, origin, function,
  helper dependence, contamination, or novelty. M9 owns translated/ORF/protein,
  domain, profile-HMM, and remote-homology evidence; M12 owns read-origin and
  technical-artifact review.
- **Migration:** introducing the typed all-candidate export may require one
  M6 rerun for existing workflows to materialize it. Once present, changing an
  M8 panel must not rerun M6 assembly or M7 recurrence.

## 15. Exact files likely to change during implementation

These are likely future paths, not changes made by this design task:

**Existing files likely to extend**

- `satellite_discovery/residual_evidence_adapter.py` — emit the typed
  all-candidate FASTA/manifest before support promotion while preserving
  current M6 support outputs and statuses.
- `satellite_discovery/artifact_contracts.py` — add and validate the candidate
  sequence and M8 artifact contracts.
- `satellite_discovery/artifact_workflow.py` — register the M8 stage, inputs,
  outputs, and report contract handoffs.
- `satellite_discovery/artifact_stage_handlers.py` — add descriptive M8
  summary rendering with no biological inference.
- `docs/M8_REFERENCE_AND_HOMOLOGY_SPEC.md` — reconcile proposed enums and
  contract fields with the panel policy, BLASTN baseline, and remaining
  implementation decisions before implementation.

**Proposed new production files**

- `satellite_discovery/m8_reference_panels.py`
- `satellite_discovery/m8_search_adapters.py`
- `satellite_discovery/m8_homology.py`

**Tests likely to add or extend**

- `tests/test_m8_reference_panels.py`
- `tests/test_m8_search_adapters.py`
- `tests/test_m8_homology.py`
- `tests/test_m8_workflow.py`
- `tests/test_residual_evidence_adapter.py` — all-candidate export and
  unchanged support-state behavior.

`pyproject.toml` or CI tool-install scripts should change only if the approved
adapter requires a managed runtime or executable. Local BLASTN is selected as
the initial baseline, but this design does not pin an exact BLAST+ release or
configuration, download a database, or install an executable. Do not change
the separate panel-approval document as part of this implementation
architecture work.
