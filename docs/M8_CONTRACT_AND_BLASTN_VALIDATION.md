# M8 Contract Freeze and BLASTN Technical Validation

**Status: technical pre-implementation gate evidence complete for Linux x86-64.**
This records the frozen typed handoff, role/status contracts, accession-pinned
external reference snapshot, and synthetic-only validation of the approved
BLASTN profile. It does not implement or operate a production M8 search stage.

## 1. Scope and non-goals

This work covers:

- A backward-compatible M6/M7-to-M8 candidate sequence-set handoff.
- One normative M8 reference-panel role vocabulary and software execution
  statuses.
- Accession-pinned retrieval and external index construction for the approved
  14-record panel, with manifest and hashes only in the repository.
- Synthetic-only validation of NCBI BLAST+ `2.17.0+` on Linux x86-64.
- M6/M7 cache isolation from package-wide, M8-only source changes.

No production M8 search stage was added. The approved 14 reference records
were fetched from NCBI only to verify accession-pinned provenance/terms and
construct an external index; no candidate sequence or biological candidate
dataset was searched. Sequence payloads and index files remain outside the
repository. The curator catalogue and review files were not edited. M9 was not
started. No biological identity, novelty, or eligibility thresholds were
introduced.

The 50-nt task selector is a frozen software-method choice, not a minimum query
length. A valid query shorter than the BLAST seed word remains in the evidence
record but its branch is `INSUFFICIENT_INFORMATION`; all other valid queries,
including the 16-nt fixture, are searchable, and any reported alignment
remains evidence.

## 2. Candidate sequence-set handoff

M6 now emits the typed `m8_candidate_sequence_set` artifact
(`candidate_sequence_set.json`) and, when sequence bytes are available,
`candidate_sequences.fasta`. The handoff is produced from the assembler output
before read-support promotion. It therefore exposes the complete valid
assembled-contig set without changing the existing `supported_contigs.fasta`
gate or M7's supported-only input behavior.

Each record binds the producer-declared candidate and sequence IDs to the
FASTA record ID, exact sequence SHA-256 and length, source artifact identity,
alphabet, completeness state, and M6 read-support status. Identical sequence
bytes remain distinct records when their producer/FASTA identifiers differ;
they are not deduplicated by sequence equality. An optional M7-context link is
accepted only when candidate ID, sequence ID, and sequence hash agree.

The artifact validator enforces the declared IUPAC nucleotide alphabet and
checks the candidate FASTA against the manifest. It binds the source assembly,
completed assembly manifest, and M6 reconstruction evidence by path and
SHA-256; assembly contig count must match the complete candidate set. Tampering
with any bound artifact fails validation. M6 candidate artifacts cannot embed
M7 data: M7 artifacts are separate typed optional M8 inputs. Missing upstream
bytes are explicit (`UPSTREAM_UNAVAILABLE` with a reason and no FASTA
reference); malformed bytes are `INVALID_OUTPUT`. Neither state is an empty or
successful search. If valid assembly bytes exist but read support fails, the
candidate FASTA remains available and its support status is preserved rather
than suppressing the sequence.

M6 adapter version is `1.1` to account for the new output contract. This causes
the expected one-time M6 cache refresh. The existing supported-contig handoff
to M7 remains unchanged.

## 3. Normative roles and fixture terminology

The canonical panel roles are:

`satellite_subviral`, `virus_helper`, `host_nuclear`, `host_organelle`,
`microbial`, `vector`, `plasmid`, `adapter`, `technical_contaminant`,
`mobile_element`, and `related_non_satellite`.

Fixture labels are aliases or subroles, not a second normative role enum:

| Fixture term | Canonical interpretation |
| --- | --- |
| `delta_related_subviral`, `deltavirus_context` | `related_non_satellite / deltavirus_context` |
| `viroid`, `viroid_context` | `related_non_satellite / viroid_context` |
| `virophage`, `virophage_context` | `related_non_satellite / virophage_context` |
| `polinton_related`, `polinton_like_context` | `related_non_satellite / polinton_like_context` |
| `plant_satellite_dna` | `satellite_subviral / satellite_dna` |
| `plant_satellite_rna` | `satellite_subviral / satellite_rna` |
| `plant_satellite_virus` | `satellite_subviral / satellite_virus` |
| `documented_helper_context` | `virus_helper / declared_potential_helper` |
| `segmented_helper_genome` | `virus_helper / segmented_helper_genome` |
| `polinton_like_virus_context` | `related_non_satellite / polinton_like_context` |

Ambiguous fixture labels are not guessed into one role. `host` requires a
nuclear or organelle subrole; `vector_plasmid` requires choosing `vector` or
`plasmid`. `polinton_related_and_virophage_label_conflict` must be split into
explicit reviewed records. `virophage_and_proviral_context` is rejected as a
generic alias; the exact curator-reviewed accession `KU052222.1` is mapped to
`related_non_satellite / proviral_context`, not to free-virus virophage context.
These rules keep deltavirus, viroid, virophage, and Polinton-like context out of
the satellite role by default.

## 4. Execution and aggregate status contract

Branch statuses are limited to explicit software outcomes:

- Completed: `SEARCH_COMPLETED_MATCHES_REPORTED` or
  `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`.
- Not conclusive: `INSUFFICIENT_INFORMATION`, `DEPENDENCY_UNAVAILABLE`,
  `INPUT_INVALID`, `REFERENCE_PANEL_INVALID`, `REFERENCE_PANEL_INCOMPLETE`,
  `SEARCH_FAILED`, `SEARCH_INTERRUPTED`, or `SEARCH_TRUNCATED`.
- Lifecycle-only states: `NOT_SELECTED`, `NOT_APPLICABLE`, `NOT_STARTED`, and
  `RUNNING`.

The canonical no-match status requires valid candidate and panel inputs,
available and approved software, successful execution and parsing, complete
accounting, and no truncation. It means only that the exact recorded method
reported no alignment against the exact searched references. It is not
biological absence, novelty, or a negative classification.

An aggregate is `COMPLETE` only when every required branch has a completed
matches-reported or completed-no-match status. Missing required branches,
truncation, invalid/incomplete inputs, interruption, failure, or insufficient
information makes the aggregate `PARTIAL`. Fixture labels `AMBIGUOUS`, `KNOWN`,
and `SIMILAR` are not software statuses; they map to matches-reported only
when complete hit accounting confirms at least one hit. `UNAVAILABLE` and
`FAILED` require a specific software cause. A short-query applicability note
does not erase a real reported alignment.

## 5. BLAST+ archive and executable identity

The versioned NCBI Linux x86-64 archive was freshly downloaded and verified in
temporary storage outside the repository:

- Archive: [`ncbi-blast-2.17.0+-x64-linux.tar.gz`](https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/ncbi-blast-2.17.0+-x64-linux.tar.gz)
- Size: `296006458` bytes.
- NCBI MD5 sidecar: `bdec166721de3b55f90a3badc83538e8` (verified).
- Locally computed archive SHA-256:
  `3888112d8207831aa47371d93583c601f058f88b5db22dc782438b039a3a411b`.
- `blastn -version`: `blastn: 2.17.0+`, package build dated 2025-07-01.
  Executable SHA-256:
  `33b64bc67d3149cee2459b2f7766b363323df632cf12c099546de00aea9698b5`.
- `makeblastdb -version`: `makeblastdb: 2.17.0+`, matching package build.
  Executable SHA-256:
  `c1ffdcf6f15d1d8d75377cc9f37afa42bc9fa06678903bad77c2641e60778fce`.
- Validation host: Linux x86-64, Python 3.12.12.

The archive checksum was independently recomputed from the fresh download and
matched NCBI's MD5 sidecar; the executable hashes were computed locally.
`m8_blastn_profile.py` supports only Linux x86-64 with the exact `2.17.0+`
`blastn` and `makeblastdb` pair. Windows and all other platforms are explicitly
unavailable and must produce typed `DEPENDENCY_UNAVAILABLE`, not a fallback.
The NCBI executable required `libgomp.so.1`; validation used an existing
Nix-provided OpenMP library through `LD_LIBRARY_PATH`. A future runner must
provision this runtime dependency. No BLAST+ binary, sequence payload, or
generated index was added to the repository, and the application does not
download or install BLAST+.

## 6. Synthetic profile and results

The optional integration tests use only locally generated artificial FASTA
records and temporary databases built with:

```text
makeblastdb -in <synthetic.fasta> -dbtype nucl -parse_seqids -out <temporary-prefix>
```

The frozen technical profile `m8-blastn-linux-x86_64-v1` uses explicit
settings. These constrain reproducible reporting; they are not biological
cutoffs or candidate-role rules.

| Query length | Task | Word size | Reward | Penalty | Gap open/extend |
| --- | --- | ---: | ---: | ---: | --- |
| `< 50 nt` | `blastn-short` | 7 | 1 | -3 | 5 / 2 |
| `>= 50 nt` | `blastn` | 11 | 2 | -3 | 5 / 2 |

Both profiles use `-strand both`, `-soft_masking true`, `-evalue 1000`,
`-max_target_seqs 1000`, `-max_hsps 1000`, and `-num_threads 1`. Every required
panel/method branch runs separate `-dust yes` and `-dust no` searches; one is
not a fallback for the other. Reaching either per-query target cap or
per-query/reference HSP cap is conservatively `SEARCH_TRUNCATED`, including
when the capped output might happen to contain every possible hit. Output uses the explicit
tabular field order
`qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen sstrand`.
The fixture parser preserves raw output, converts 1-based inclusive
coordinates to 0-based half-open coordinates, retains subject strand, and
retains query/reference spans and their respective length denominators for
coverage calculation by a future M8 stage.

Seven pinned-tool integration tests and four pure profile tests cover:

- The 7-nt seed boundary, retained 16-nt query, and selector boundary at
  49/50/51 nt.
- Exact forward and reverse-complement matches.
- A partial local HSP and two competing exact reference records.
- Separate low-complexity masked/unmasked branches.
- A completed synthetic no-match and both target-cap and HSP-cap truncation.
- Missing executable, invalid database, execution failure, and safe
  interruption-status handling.

Two repeated exact-match runs produced byte-identical raw tabular output and
identical normalized rows on this host. Exact coordinates and plus/minus
orientation were checked. The interruption case uses a controlled synthetic
sleeping process to test cancellation-to-status mapping; it does not claim
cross-platform BLAST process cancellation has been validated. A finite target
cap is conservatively considered truncated when reached.

## 7. M6/M7 cache isolation

M6 and M7 now provide stage-scoped implementation identities. M6 hashes code
that can affect its own outputs and candidate handoff validation; M7 hashes
its recurrence implementation and dependencies. When a scoped identity is
available, `_stage_cache_key` does not incorporate the package-wide source
digest. Regression tests changed that package digest and confirmed unchanged
M6 and M7 keys. M8 role/status-only code is excluded from both scoped
identities; the M8 candidate-handoff validator is included in M6 because it
validates an M6-produced artifact.

## 8. Verification and remaining review

Verification on Python 3.12.12:

- `python -m compileall -q satellite_discovery tests` — passed.
- `python -m unittest discover -s tests -v` — 413 tests passed; 8 optional
  live-tool tests were skipped.
- All 7 pinned BLASTN synthetic integration tests and 4 pure profile tests ran
  in that suite with the executable paths explicitly set.

The external accession/version set, role mapping, typed M6/M7 handoff,
Linux-only BLASTN profile, masking policy, reporting caps, truncation behavior,
and narrow `INSUFFICIENT_INFORMATION` predicate are now recorded. The snapshot
manifest preserves exact sequence and source-response hashes, source taxonomy,
curation citations, rights state, and external index-file hashes; no payload is
committed and redistribution is not approved. The profile has no validated
Windows or non-Linux runtime. This report does not add or execute production
M8 search behavior; it closes the technical gates for a separate implementation.
M9 remains out of scope.