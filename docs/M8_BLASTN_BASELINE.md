# M8 BLASTN Baseline Configuration and Validation Design

**Status: design only; the production M8 stage is not implemented. The technical
profile is ready for implementation on Linux x86-64 only.**

**Selected release:** NCBI BLAST+ `2.17.0+`, archive and executable hashes
verified and recorded in
[`M8_CONTRACT_AND_BLASTN_VALIDATION.md`](M8_CONTRACT_AND_BLASTN_VALIDATION.md).

**Information checked:** 2026-09-26.

## 1. Scope and boundaries

This document turns the approved choice of local BLASTN as M8's initial
nucleotide-search baseline into a reviewable technical configuration. It
specifies evidence handling and validation plans, not biological classification.
It does not approve reference membership, licensing, a classifier, or final
search thresholds.

M8 remains nucleotide/reference homology only. Translated searches, ORF
hypotheses, protein/domain/profile-HMM evidence, and remote homology belong to
M9. Read-origin, controls, batch effects, and technical-artifact conclusions
belong to M12. M8 must preserve upstream M6/M7 evidence without upgrading it.
No BLASTN match or no-hit establishes identity, origin, function, dependence,
contamination, or novelty.

A separate task curates the initial satellite/subviral catalogue. This document
does not define accessions or change that task's catalogue files. No biological
reference database is downloaded or created for this design. No production
code, BLAST+ binary, or database index is added to the repository.

## 2. Release recommendation and acquisition source

Recommend pinning **NCBI BLAST+ `2.17.0+`** for the first implementation
candidate. On 2026-09-26, NCBI's official `LATEST` directory identified this as
the current release and provided both x86-64 Linux and Windows archives. This
is a version recommendation for review, not approval to implement. If another
release is current when implementation is approved, select it explicitly and
repeat the software fixtures; never let an automated build follow `LATEST`.

Use the version-specific NCBI release directory, not the mutable `LATEST`
alias:

| Platform | Official archive | NCBI-published MD5 sidecar value observed 2026-09-26 |
| --- | --- | --- |
| Linux x86-64 | [`ncbi-blast-2.17.0+-x64-linux.tar.gz`](https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/ncbi-blast-2.17.0+-x64-linux.tar.gz) | `bdec166721de3b55f90a3badc83538e8` |
| Windows x86-64 | [`ncbi-blast-2.17.0+-x64-win64.tar.gz`](https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/ncbi-blast-2.17.0+-x64-win64.tar.gz) | `dcd973097407a2910061ff4fb51b09fb` |

NCBI also publishes an installer for Windows. Prefer the versioned archive for
non-interactive CI so the executable can be unpacked in an isolated runner
directory without a machine-wide install. The runner's operating-system and
architecture compatibility must be tested; the Linux x86-64 and Windows
x86-64 packages are the proposed CI targets. Other operating systems and
architectures are not covered by this recommendation.

NCBI's `.md5` sidecars can detect transfer corruption but are not a strong
authenticity check. Before enabling CI acquisition, a maintainer should obtain
each exact archive over HTTPS from the versioned NCBI directory, verify its
NCBI sidecar, compute a SHA-256 digest, and independently review that digest.
Pin the reviewed SHA-256 value per platform in the future CI configuration.
The SHA-256 values are intentionally not supplied here: no executable archive
was downloaded for this documentation task. A missing or mismatched pin must
fail closed; do not silently use another release or an unverified cache.

The version-specific paths and the MD5 values above were checked in NCBI's
official release directory. Do not commit the binary archives to the
repository. CI may cache a verified tool installation outside the checkout,
keyed by operating system, architecture, release, and pinned archive digest.
That cache must never contain biological reference databases.

## 3. Executable discovery and identity

For a future M8 adapter, use one explicit discovery order:

1. An executable path supplied in the typed M8 tool configuration.
2. A documented `BLASTN_EXECUTABLE` override, if the application exposes one.
3. `blastn` discovered on `PATH`.

Resolve `makeblastdb` from the same configured distribution (or an explicit
matching override) when a panel index must be built. Do not search arbitrary
directories, infer an executable from a database path, or install/download a
tool at runtime. If the executable is absent, cannot run, or has an unapproved
version, report `DEPENDENCY_UNAVAILABLE` before searching; never substitute an
empty hit table.

Run bounded, argv-based version probes for both `blastn -version` and
`makeblastdb -version`. Parse and require the `2.17.0+` release token; retain
the full probe output, resolved executable path, operating system, and
executable SHA-256 in run provenance. A later approved release change must
update the expected version and checksum together. Use the existing
`ExternalToolAdapter` boundary with argument arrays, timeouts, output limits,
and explicit interruption handling; do not invoke shell command strings.

The search configuration must name the exact generated database prefix for
each declared panel. Do not rely on ambient `BLASTDB` paths or silently select
an installed database. Validate the panel manifest and built-index state before
running BLASTN.

## 4. Frozen search modes and configuration profile

The reviewed Linux x86-64 BLAST+ `2.17.0+` profile uses `blastn-short` below
50 bases and `blastn` at or above 50 bases. This is a **technical task
selector**, not a candidate eligibility rule:

| Query length | Task | Meaning |
| --- | --- | --- |
| 50 nt or longer | `-task blastn` | Ordinary nucleotide-search profile. |
| Shorter than 50 nt | `-task blastn-short` | Short-query-aware nucleotide-search profile. |

Both tasks are validated on synthetic queries, including 7, 16, 49, 50, and
51 nt. Every valid candidate remains in the M8 evidence record regardless of
length; the 50-nt selector does not create a minimum, exclude a query, or imply
that a short-query hit or no-hit identifies or excludes a biological role.
`blastn-short` uses word size 7; a valid query shorter than that seed size
remains eligible but the method branch is `INSUFFICIENT_INFORMATION` with
reason `QUERY_SHORTER_THAN_WORD_SIZE`, not a no-hit. No 32-nt or other
biological applicability threshold is used.

For both tasks:

- Pass `-strand both` explicitly and preserve subject strand plus original
  query/reference coordinates. Do not reverse-complement or rewrite candidate
  or reference bytes.
- Retain local HSPs and partial alignments with their coordinates and both
  query- and reference-side coverage denominators. A partial HSP is not
  whole-sequence identity.
- Record the selected `-task` and every effective scoring, gap, word-size,
  filtering, statistical-reporting, thread, and output-limit setting. NCBI's
  manual documents task-specific profiles, including word sizes of 11 for
  `blastn` and 7 for `blastn-short`, with gap-open 5 and gap-extend 2 for both.
  Treat task defaults as release-specific configuration, not as undocumented
  behavior: capture the effective values for the pinned executable and record
  any explicit overrides.
- Use an explicit low-complexity plan. Run both the DUST-masked branch
  (`-dust yes`) and the separate unmasked branch (`-dust no`) for every required
  candidate × panel × method combination; neither is a hidden fallback.
  Synthetic tests cover both short and ordinary task profiles. The profile uses
  `-soft_masking true`; any database soft-masking is separately recorded.
- Preserve the full tool output and filtered-hit diagnostics when available.
  A repetitive match alone must not be promoted to a role identity.

The reviewed profile explicitly sets `-evalue 1000`, `-max_target_seqs 1000`,
`-max_hsps 1000`, and `-num_threads 1`, in addition to the task-specific scoring
table above. These are technical reporting/execution settings, not biological
cutoffs. Reaching either target or HSP cap is conservatively reported as
truncation, even if the returned output might happen to include every possible
hit. Task defaults and any output truncation must not be hidden.

## 5. Output fields, competing hits, and ordering

Use a versioned, explicit tabular schema rather than relying on BLAST's default
columns. The proposed `-outfmt 6` field list is:

```text
qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen sstrand
```

Use stable, project-generated query IDs and stable reference IDs accepted by
the indexed database. The field list and schema version belong in the run
manifest. Derive query and reference coverage from their coordinates and
length denominators, and preserve absolute aligned bases; do not use percent
identity alone. Store the raw BLAST output byte-for-byte and retain its
SHA-256, along with a lossless reference from normalized evidence to each raw
row.

Search each approved role-separated panel as a distinct scope. Retain all
competing references, HSPs, ties, overlapping alignments, and duplicate
sequence hashes with their panel and snapshot provenance. Do not select a
biological winner or compare scores across panels with different search spaces.
If a future output cap is reached, mark the affected branch as truncated and
keep its completed results separate from complete branches.

Keep native row order in the raw output. For normalized display, use a declared
stable sort such as query ID, panel role, method branch, reference ID, query
coordinates, reference coordinates, strand, and then a stable raw-row
tie-breaker. Retain original row order as provenance. Test stable normalized
results on repeated fixture runs; do not assume that tool-native ordering is a
cross-platform sort contract.

## 6. Completion, no-hit, and failure states

Emit `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` only when the
candidate, each required panel snapshot, each required method/masking branch,
and the built database are valid; the expected executable ran successfully;
the output parsed; and query/panel accounting is complete with no unreported
truncation. The result means only that the recorded method reported no
alignment under its exact settings against those exact searched snapshots.
It is not novelty, absence from nature, or a negative biological result.

Keep failure and suitability states distinct:

| Condition | Required outcome |
| --- | --- |
| Missing, unusable, or unapproved BLAST+ dependency | `DEPENDENCY_UNAVAILABLE` |
| Invalid query or candidate handoff | `INPUT_INVALID` |
| Invalid manifest, hashes, role, or database index | `REFERENCE_PANEL_INVALID` |
| Incomplete declared snapshot/build | `REFERENCE_PANEL_INCOMPLETE` |
| The query/method cannot provide informative evidence under an approved technical rule | `INSUFFICIENT_INFORMATION` |
| Non-zero process exit, invalid output, or parser failure | `SEARCH_FAILED` |
| Timeout, cancellation, or partial work | `SEARCH_INTERRUPTED` |
| Completed branch with one or more reported alignments | `SEARCH_COMPLETED_MATCHES_REPORTED` |
| Fully accounted valid branch with no reported alignments | `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` |

An aggregate with any required unavailable, invalid, incomplete, interrupted,
or truncated branch is partial/unresolved, never a successful overall no-hit.
A short query with a real reported alignment keeps that evidence even if a
separate method-applicability warning is recorded.

For the frozen profile, the applicability check is software-only: select the
task first, then compare query length with that task's explicit word size. If
the query is shorter, record `QUERY_SHORTER_THAN_WORD_SIZE` and do not serialize
that branch as a completed no-hit. This preserves the valid candidate and its
provenance without inventing a biological threshold; queries at or above the
word size proceed through the ordinary search and accounting path.

## 7. Provenance and deterministic reuse

Bind each run to at least:

- candidate ID, exact sequence hash/length, normalization rule, and upstream
  M6/M7 evidence identities and statuses;
- panel role, immutable snapshot/manifest hashes, record membership, source
  metadata, and generated index/database hashes;
- BLAST+ release, platform archive SHA-256, executable identities and version
  probe outputs, database-builder version, exact argument vector, output
  schema, masking/task branches, caps, and truncation state;
- operating system, architecture, Python version, thread/resource settings,
  expected/completed/unaccounted query counts, process outcome, and raw
  stdout/stderr/output hashes.

Hash exact FASTA and manifest bytes separately from normalized sequence
records. Hash raw tabular output and any normalized artifact separately.
Timestamps and temporary absolute paths may be logged as run metadata but must
not replace semantic inputs in the cache identity. Reuse requires all semantic
inputs, tool digests, effective parameters, and implementation/parser identity
to match.

For deterministic software fixtures, run with an explicit single-thread
setting, fixed synthetic inputs, fixed tool release, fixed database-builder
release, and fixed arguments. Compare both raw output hashes and normalized
evidence across repeated executions. If the pinned tool does not produce
byte-identical raw output on a supported platform, preserve that finding and
define a narrowly scoped normalized determinism contract; do not silently
weaken the test or discard ties.

## 8. Synthetic fixture validation

Map the existing [`M8_BENCHMARK_FIXTURE_DESIGN.md`](M8_BENCHMARK_FIXTURE_DESIGN.md)
fixtures to a future real-BLAST integration suite using only tiny, artificial
local panels:

| Case | Configuration question and expected safety property |
| --- | --- |
| Exact and competing-panel sequences | Report all role-specific hits with snapshot provenance; never choose a biological winner. |
| Reverse complement | `-strand both` reports orientation and original coordinates. |
| Partial fragment | Preserve HSP coordinates, aligned bases, and both coverage denominators; do not infer complete identity. |
| Short query and selector boundary | Exercise the 16-nt case and 49/50/51-nt boundary. Retain the candidate and any raw hit; keep the fixture-only 32-nt warning out of production rules. |
| Low complexity | Run explicit masked and unmasked branches; preserve branch identity and available filtering diagnostics. |
| Complete synthetic no-match | Reach the canonical scoped no-hit only after all expected queries, snapshots, and branches complete. |
| Corrupt panel/index and missing executable | Return invalid/unavailable states, never an empty successful result. |
| Interruption and output limit | Preserve completed work and accounting; mark interrupted/partial or truncated, not no-hit. |
| Deterministic reuse | Repeated identical runs have matching semantic identity and the agreed raw/normalized determinism behavior. |
| Weak or unresolved upstream evidence | Preserve M6/M7 state; BLASTN evidence never upgrades it. |

Fixtures test parser, parameter, provenance, completeness, and failure
behavior. They do not measure biological sensitivity/specificity or validate
taxonomy, identity, origin, novelty, or a classifier. Do not run the future
blinded biological benchmark as part of this configuration design.

## 9. Cross-platform CI and local use

Keep dependency-free tests runnable in the existing Python 3.11/3.12 matrix on
Ubuntu and Windows. They should exercise configuration validation, parsing,
accounting, missing-dependency behavior, and fake-adapter failure paths without
requiring BLAST+.

Extend the future optional-tools/runtime validation to acquire the pinned
platform archive from the versioned NCBI HTTPS URL, verify the reviewed digest
before extraction, run both version probes, build only the synthetic fixture
databases, and execute the integration fixtures. Exercise Linux and Windows
path handling; include Python 3.11 and 3.12 in the adapter tests. Cache only the
verified executable package outside the checkout. Never download production
reference databases or commit binaries or generated indexes.

Use argv lists with `shell=False`; test executable paths containing spaces,
Windows `.exe` resolution and cleanup, Linux execute permissions, timeouts,
cancellation, bounded stdout/stderr, and paths in temporary directories. A
missing tool must produce `DEPENDENCY_UNAVAILABLE`; optional-tool setup failure
must not turn the offline test suite into a passing empty-search result.

Local use should require an explicitly installed, version-verified NCBI BLAST+
release. The application must not install or upgrade BLAST+ automatically.
Document the resolved executable and version in each run manifest.

## 10. Gate decisions and remaining scope

The implementation gate records these technical decisions:

1. Linux x86-64 only, pinned to the verified NCBI `2.17.0+` archive and
   executable hashes; unsupported platforms map to `DEPENDENCY_UNAVAILABLE`.
2. A tested 50-nt task selector, explicit scoring and reporting settings, both
   DUST branches, one thread, and conservative target/HSP cap truncation.
3. A technical word-size applicability predicate; candidate eligibility still
   has no minimum length.
4. A validated BLASTDB v5 builder/index recipe and accession-pinned external
   14-record snapshot with sequence, source-response, and index hashes.
5. Same-host repeated raw-output byte determinism and normalized evidence
   checks; no cross-platform byte-order guarantee is claimed.

This gate does not establish biological sensitivity/specificity or authorize
parameter tuning against candidate labels. It does not authorize redistribution
of reference payloads, implement production M8 search behavior, or start M9.

## 11. Authoritative references

NCBI sources checked 2026-09-26:

- [BLAST+ version-specific release directory](https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/)
  and [mutable latest-release directory](https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/).
- [NCBI BLAST+ executable download guidance](https://blast.ncbi.nlm.nih.gov/doc/blast-help/downloadblastdata.html)
  and [versioning policy](https://blast.ncbi.nlm.nih.gov/doc/blast-help/versioningblast.html).
- [BLAST+ release notes](https://www.ncbi.nlm.nih.gov/books/NBK131777/).
- [BLAST+ task descriptions](https://www.ncbi.nlm.nih.gov/books/NBK569839/),
  [BLASTN option table](https://www.ncbi.nlm.nih.gov/books/NBK279684/table/appendices.T.blastn_application_options/),
  and [common output-format options](https://www.ncbi.nlm.nih.gov/books/NBK279684/table/appendices.T.options_common_to_all_blast/).
- Project constraints: [M8 implementation architecture](M8_IMPLEMENTATION_ARCHITECTURE.md),
  [reference-panel policy](M8_REFERENCE_PANEL_APPROVAL.md),
  [M8 reference and homology specification](M8_REFERENCE_AND_HOMOLOGY_SPEC.md),
  and [M8 benchmark fixture design](M8_BENCHMARK_FIXTURE_DESIGN.md).