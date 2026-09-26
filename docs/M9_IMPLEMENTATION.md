# M9 Synthetic/Offline Baseline Implementation

**Review status: implementation is prepared for review. The milestone remains
PLANNED / NOT IMPLEMENTED until it is formally accepted.**

This document describes the bounded software baseline added for M9. It does
not change milestone tracking or authorize biological reference retrieval,
biological searches, candidate classification, or later milestones. Tests use
deterministic synthetic sequences and an explicitly supplied synthetic
protein snapshot only.

## Scope and evidence boundary

M9 starts from the validated, checksum-bound M6 candidate-sequence handoff.
Candidate IDs, sequence IDs, source bytes, hashes, support state, and unresolved
upstream evidence remain separate and are carried into the derived records.
Repeated sequence bytes do not merge candidate identities.

M7 recurrence and M8 nucleotide evidence are optional context, not eligibility
gates. When supplied, M7 artifacts retain their input identities. M8 artifacts
are checked against a completed M8 stage manifest and the same M6 candidate-set
hash. Verified M8 statuses, including partial or failed branch outcomes, remain
context; they do not gate ORF translation. Invalid or unverifiable M8 context
is labeled `INVALID_OR_INCOMPLETE`, not reinterpreted as a no-hit. M6 and M7/M8
artifacts are never rewritten by M9.

The baseline performs no database discovery or retrieval. Protein searching
requires one explicitly supplied, typed snapshot consisting of a manifest and
FASTA payload. The manifest binds record IDs, accession versions, roles,
lengths, sequence hashes, payload hash, provenance, completeness, and a
canonical snapshot digest. An incomplete snapshot may retain positive rows
with incomplete-scope status, but cannot produce a scoped no-hit or a complete
aggregate.

Outputs are technical hypotheses and similarity evidence only. ORFs are not
gene calls; protein similarity does not establish expression, function,
novelty, helper dependence, satellite status, or biological reality. No M10
topology analysis, BLASTX, BLASTP-short, HMMER, or biological dataset search is
included.

## Registered stages

### `m9_orf_translation`

Required typed input:

- `candidate_sequence_set`: `m8_candidate_sequence_set`

Optional typed context:

- M7 observation, recurrence, independence, validation, and provenance
  artifacts.
- M8 query status, match evidence, summary, search commands, and raw BLAST
  outputs.

The stage enumerates all six strand/frame combinations with translation table
1, ATG-only complete starts, the first definite in-frame stop, nested starts,
and distinct 5′/3′ partial hypotheses. Ambiguous codons translate to `X`;
RNA uses a temporary U-to-T view without changing source bytes. Coordinates are
zero-based, half-open on the original sequence, including reverse-strand
mapping. No biological minimum ORF length is applied.

Outputs:

- `orf_results.json` (`m9_orf_results`): candidate- and ORF-level provenance,
  accounting, translation policy, coordinates, partial state, and hashes.
- `proteins.faa` (`m9_protein_fasta`): a separate derived-protein FASTA,
  including a valid empty file when no ORFs are predicted.
- `orf_bundle.json` (`m9_orf_bundle`): input and output checksums.

`NO_ORF_PREDICTED_WITHIN_POLICY` is not a noncoding conclusion. Candidate
identities with unavailable sequence bytes remain accounted for and do not
become an empty successful search.

### `m9_blastp`

Required typed inputs:

- `orf_results`: `m9_orf_results`
- `protein_fasta`: `m9_protein_fasta`
- `reference_manifest`: `m9_protein_reference_manifest`
- `reference_payload`: `m9_protein_reference_payload`

The stage runs ordinary local BLASTP only. The pinned runtime is NCBI BLAST+
2.16.0 on Linux x86_64:

- `blastp`: SHA-256
  `e17de0fd689f89dcb095eea2626710a206ab3d016a183f064c388f963ecbc7c4`
- `makeblastdb`: SHA-256
  `6797dd00e0dddfa0529de795ded12b41738792c9b75bf3643e1f03a782d2008f`

Executables are checked at runtime and are not bundled, downloaded, or silently
replaced. The recorded profile uses BLOSUM62, gap open/extend 11/1, SEG enabled,
composition-based statistics mode 2, E-value exposure 2000, at most 1000
targets, at most 100 HSPs per query, and one thread. The E-value and limits
describe this software profile, not a biological cutoff. Reaching a configured
row, target, HSP, byte, or output cap is truncation, not a complete no-hit.

Outputs:

- `query_status.json` (`m9_protein_search_status`): expected/observed/missing
  query IDs and candidate/query execution states.
- `matches.json` (`m9_protein_match_evidence`): all parsed HSP rows, including
  zero-based half-open coordinates, query/reference coverage and denominators,
  identity, positives, gaps, raw/bit scores, E-values, reference metadata, and
  raw-output hashes.
- `summary.json` (`m9_protein_summary`) and `commands.json`
  (`m9_search_commands`): scope, runtime, settings, accounting, exact commands,
  and provenance.
- `m9_bundle.json` (`m9_output_bundle`): checksummed local outputs.
- Raw TSV, stdout, and stderr artifacts use `m9_raw_blast_output`.

If ORF enumeration completes with zero queries, BLASTP is not run; each
candidate is accounted as `NOT_RUN_NO_ORF`, not as a no-hit. A no-hit is scoped
to an informative query, the exact complete validated snapshot, and the
recorded profile. Dependency failure, invalid input or snapshot, incomplete
snapshot, failed/interrupted execution, and truncation remain distinct states.

Configuration allows only explicit executable paths, a bounded timeout, and a
maximum output-byte limit. An executable path override does not override the
required version/hash pin.

## Cache and workflow integration

The ORF stage identity is scoped to ORF derivation, the candidate handoff, its
input/output contract semantics, and the implementation dependencies it uses.
Protein snapshot bytes, manifest, BLASTP settings, and BLASTP runtime belong to
the separate search-stage identity. A reference-only change therefore
invalidates protein search without rerunning unchanged ORF derivation. M9
contracts and outputs are also accepted by the consolidated workflow-report
stage.

The implementation adds M9 artifact contracts and registry entries without
changing M6, M7, M8, M10, `README.md`, or `ROADMAP.md`. In particular,
`scripts/post-merge.sh` is not part of this implementation.

## Validation performed

The synthetic/offline test coverage exercises:

- Six-frame ORF enumeration, coordinate mapping, partials, ambiguous codons,
  duplicate candidate sequences with distinct identities, and protein hashes.
- Snapshot digest, payload membership/hash, repeated reference roles,
  incomplete snapshots, and malformed FASTA handling.
- BLASTP tabular parsing, coordinate/coverage normalization, output caps, and
  a real run with the locally available pinned BLASTP 2.16.0 runtime.
- End-to-end M8-to-M9 context preservation where an M8 branch fails, while M9
  translation and synthetic protein searching complete.
- Query accounting for dependency failure, no-ORF, complete search, and
  incomplete reference scope.
- Cache isolation: changing the protein snapshot changes the M9 search key but
  leaves the ORF derivation key unchanged.

All biological-resource retrieval and biological-dataset search remain
outside this validation. Synthetic software tests do not establish biological
sensitivity, specificity, or classification accuracy.