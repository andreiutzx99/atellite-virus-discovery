# M8 Benchmark and Reference Fixture Design

**Status: design only.** This document plans deterministic software fixtures
and a future blinded benchmark. It does not implement M8, select biological
decision thresholds, or claim discovery.

## Scope and project boundaries

M8 is planned for nucleotide/reference comparisons only. M9 owns translated
and protein-level evidence, while M12 owns read-origin and technical-artifact
review. This document preserves earlier design history without treating its
former numbering discrepancy as the current architecture; see the
[current roadmap](ROADMAP.md).

The fixtures use synthetic sequences and miniature local panels only. A
fixture role identifies which panel a test record was placed in; it is not a
biological label for an unknown candidate. A match means similarity to a
declared reference under a named method, not confirmed identity, function,
origin, helper dependence, contamination, or novelty.

No full databases, proprietary or copyrighted reference datasets, search
tools, or database dependencies are downloaded or installed for this design.
No M8 production code, M9 work, or M1–M7 behavior is changed.

## 1. Fixture classes and expected outcomes

Use fixed literal FASTA records in a later test implementation; do not
generate random sequence at test runtime. Give every record a stable
`art-`-prefixed ID. Compute query and reference hashes from the exact
documented normalization rule below. The fixture-set version and all search
parameters must be fixed. For construction-based cases, define sequences
relative to a named reference literal (copy, reverse complement, or a stated
1-based interval) so that the relationship is reproducible.

The proposed `COMPLETE`, `PARTIAL`, `UNAVAILABLE`, `FAILED`, `INTERRUPTED`,
`AMBIGUOUS`, and `NO_MATCH_WITHIN_SEARCHED_REFERENCES` labels describe
software states. The final specification may choose different enum strings,
but it must preserve the distinctions and expected behavior in this table.

| Fixture | Construction | Expected software outcome |
| --- | --- | --- |
| `art-satellite-exact` | Query is identical to one synthetic record in the `satellite_subviral` panel. | Search completes; emit a match row linked to that panel, record, hashes, coordinates, strand, and scores. Describe similarity only; do not label the query a satellite. |
| `art-helper-exact` | Query is identical to one synthetic record in the `virus_helper` panel. | Search completes; preserve the helper-panel hit as similarity evidence. Do not infer helper dependence or classify the query as a helper. |
| `art-host-exact` | Query is identical to one synthetic record in the `host` panel. | Search completes; report host-panel similarity and coordinates. Do not infer that the sequence originated from the host or is contamination. |
| `art-organelle-exact` | Query is identical to one synthetic record in the `organelle` panel. | When the declared panel set includes organelles, report the organelle-panel match. If the sample configuration excludes that panel, report it as not searched; do not silently count it as a no-match. |
| `art-microbial-exact` | Query is identical to one synthetic record in the `microbial` panel. | Search completes and reports the declared microbial-panel match. Do not infer contamination or sample origin. |
| `art-vector-exact` | Query is identical to one synthetic record in the `vector_plasmid` panel. | Search completes and reports the declared vector/plasmid-panel match with span and coverage; a match alone does not establish laboratory source. |
| `art-mobile-exact` | Query is identical to one synthetic record in the `mobile_element` panel. | Search completes and reports the mobile-element-panel match. Do not infer integration, viral identity, or satellite status. |
| `art-competing-panels` | Place identical synthetic sequence bytes under two different panel roles, then query those bytes. | Retain both hits and their panel provenance. Summarize as competing/ambiguous evidence; do not choose a winner by comparing scores across panels with different search spaces. |
| `art-reverse-complement` | Query is the reverse complement of a fixed panel reference. | With both-strand searching enabled, report the negative-strand alignment and coordinates. Preserve the searched orientation and parameters; do not silently canonicalize away strand evidence. |
| `art-partial-fragment` | Query is a fixed internal slice of a longer reference, with its 1-based source interval recorded in the fixture definition. | Report the local hit, query/subject spans, and both coverage values. Treat it as partial evidence, not whole-sequence identity; any summary interpretation remains subject to the approved coverage rule. |
| `art-weak-upstream-candidate` | Supply a valid typed candidate sequence with explicit incomplete, unsupported, or unresolved upstream evidence and no `READ_SUPPORTED_ASSEMBLY` state. | Run the declared nucleotide comparison and retain the upstream state unchanged. M8 does not promote support, infer biological reality, or treat the candidate as absent. |
| `art-short-query` | Query is a 16-nt exact slice of a synthetic reference. For this branch test only, exercise a fixture-only 32-nt method-applicability warning. | Keep the candidate eligible and preserve any raw hit. Report the method limitation without converting it to a biological minimum, role assignment, or no-match. The 32-nt value is a test parameter, not a production or biological threshold. |
| `art-low-complexity` | Query and one panel record share a fixed repetitive sequence such as `ACAC` repeated 16 times; run with the declared low-complexity handling enabled. | Preserve raw tool output or filtered-hit counts and masking settings. Flag low-complexity evidence and keep the summary ambiguous/unresolved; do not promote a role-specific result from the repeat alone. |
| `art-complete-no-match` | Use a fixed artificial query that has no qualifying alignment to the complete miniature panel set under the pinned test engine and parameters. | Only after every configured panel and query completes with exact accounting may the result be `NO_MATCH_WITHIN_SEARCHED_REFERENCES`. It is not a novelty, absence, or biological-negative claim. |
| `art-corrupt-reference` | Change one byte in a panel FASTA after writing its manifest, leaving the recorded file and sequence hashes stale. | Reject the affected panel as invalid before interpreting its search results. The aggregate cannot become a no-match; other completed panels, if any, remain separately visible. |
| `art-corrupt-manifest` | Change one manifest metadata value without regenerating its checksum sidecar. | Reject the manifest/snapshot as invalid. Do not search with it or report a complete no-match. |
| `art-missing-search-dependency` | The configured dependency inspector reports the required search executable unavailable. | Mark that search unavailable/not run. Do not substitute an empty hit table or report a no-match. |
| `art-interrupted-search` | A bounded test process stops after a recorded subset of the query/panel work. | Mark execution interrupted or partial, preserve completed panel results and completed/expected counts, and do not report a complete no-match. |

For `art-complete-no-match`, first validate the fixed literal against the
selected miniature panels and pinned engine. If it produces a qualifying hit,
choose a different synthetic query; do not adjust a scientific reporting
threshold merely to force the expected result. Store engine output and
parameters with the fixture version so the expected empty result is
reproducible.

For every search fixture, retain all materially competing hits for these
small panels. If a production output cap is later adopted, test that the
truncation is explicit. Compare raw scores only within their declared search
context; E-values and scores from panels with different search spaces are not
a shared ranking scale.

## 2. Expected evidence and execution records

Each reported match should be traceable to the exact candidate hash and
length, panel role and snapshot, reference ID and sequence hash, query and
subject coordinates, strand/frame where relevant, aligned length, identity,
query and subject coverage, mismatches/gaps, score and E-value, masking
settings, tool/version, and configuration. Preserve the raw hit row or a
lossless reference to it.

Keep execution completeness separate from similarity interpretation. Record
panel-level `COMPLETE`, `PARTIAL`, `NOT_RUN`, `UNAVAILABLE`, `FAILED`, or
`INTERRUPTED` (or approved equivalents), plus expected, completed, and
unaccounted query counts. A missing panel, failed database build, invalid
snapshot, missing executable, interrupted process, or incomplete accounting
must never be converted to `NO_MATCH_WITHIN_SEARCHED_REFERENCES`.

For this fixture set, an exact record match is expected to produce
`KNOWN/SIMILAR` only if that proposed scoped label is adopted; it still means
similarity to a named record under the stated method, not biological identity.
The precise output enums and any rule for `AMBIGUOUS` require approval in the
separate M8 specification.

## 3. Deterministic reference-manifest fixture

Use one small FASTA and one manifest per role-separated panel. A miniature
manifest should support the following shape:

```json
{
  "schema": "m8-reference-manifest-v1",
  "snapshot_id": "synthetic-panels-fixture-v1",
  "panel_role": "satellite_subviral",
  "source": {
    "database": "project-generated-synthetic-panel",
    "release": "fixture-v1",
    "source_url": null,
    "retrieval_date": null
  },
  "files": [
    {
      "path": "panel.fasta",
      "sha256": "<sha256-of-exact-file-bytes>"
    }
  ],
  "records": [
    {
      "reference_id": "art-sv-001",
      "sequence_file": "panel.fasta",
      "sequence_sha256": "<sha256-of-normalized-record-sequence>",
      "sequence_length": 64,
      "taxonomy": {
        "taxid": null,
        "scientific_name": null,
        "taxonomy_release": null
      },
      "metadata": {
        "fixture_only": true,
        "fixture_role": "satellite_subviral"
      },
      "licensing": {
        "license_id": "project-synthetic-test-data",
        "redistribution_status": "test-fixture-only",
        "attribution": "Artificial sequence generated for software testing",
        "terms_url": null
      }
    }
  ]
}
```

The angle-bracketed digests above are schema placeholders, not valid fixture
values. Generate real values from the fixed fixture literals when a future
implementation materializes the test data.

Manifest rules:

1. `panel_role` is explicit and uses a declared role vocabulary, initially
   `satellite_subviral`, `virus_helper`, `host`, `organelle`, `microbial`,
   `vector_plasmid`, and `mobile_element`. A configured but unsearched role
   remains visible as unsearched.
2. `snapshot_id` is stable for the frozen panel set. `source.database` and
   `source.release` identify the source and release/build recipe. Use a real
   ISO-8601 retrieval date for retrieved records. For generated fixtures,
   `retrieval_date: null` explicitly means there was no external retrieval.
3. `sequence_sha256` hashes the uppercase, unwrapped sequence symbols for
   exactly one FASTA record, encoded as UTF-8; `sequence_length` counts those
   symbols. The file-level SHA-256 hashes the exact FASTA bytes, including
   headers, line wrapping, and final newline.
4. Store taxonomy IDs, names, and taxonomy release when they are relevant.
   They are null for artificial fixtures. Preserve source metadata rather
   than silently substituting a taxonomy label.
5. Include licensing and redistribution metadata at record or panel level.
   Synthetic data must be identified as generated test data. Real datasets
   require release-specific terms, attribution, and redistribution review;
   do not infer permission from the software license.
6. Serialize `manifest.json` as UTF-8 canonical JSON: recursively sorted keys,
   compact separators, no byte-order mark, and exactly one trailing LF. Store
   the SHA-256 of the complete serialized file in `manifest.json.sha256` as
   lowercase hex plus one LF. This sidecar avoids a self-referential checksum.
   Any mismatch invalidates the snapshot before search.

## 4. Corruption and failure fixtures

Keep content-integrity failures separate from execution failures:

- **Corrupt FASTA or record digest:** the manifest still parses but its
  file/sequence hash does not match. Reject the panel and identify the
  offending file or record.
- **Corrupt manifest or checksum sidecar:** reject the snapshot before
  database construction.
- **Missing or malformed record metadata:** report an invalid/incomplete
  panel according to the approved contract; do not invent a taxonomy or
  source field.
- **Missing search dependency:** return an unavailable/not-run state before
  searching. It is not an empty successful result.
- **Interrupted search:** preserve completed panel/query results and exact
  accounting; mark unfinished work explicitly.
- **Successful empty result:** only the complete-no-match fixture may reach
  `NO_MATCH_WITHIN_SEARCHED_REFERENCES`, after all required panels and queries
  complete and pass validation.

The checks should prove that each failure cannot fall through to a successful
no-match or a role label. Do not install tools or create real database indexes
for this design task.

## 5. Short, low-complexity, and fragmented sequences

Treat length and composition as recorded evidence, not hidden filters.
`art-short-query` exercises a deliberately configured, test-only method-
applicability warning and must retain both the candidate and any raw hit. Do
not introduce a length-only biological eligibility cutoff. A method-specific
technical applicability rule, if proposed, must be explicit, justified,
validated, and must not remove a candidate from the M8 evidence record.

`art-low-complexity` verifies that masking configuration, filtered-hit
counts, and any raw alignments are visible. It should not be reported as a
confident panel identity simply because a repetitive segment aligns.

`art-partial-fragment` verifies coordinates and both coverage denominators.
A local hit to a fragment is not whole-sequence identity. Do not silently
join contig ends, circularize candidates, or infer a complete genome from a
partial match.

## 6. Competing-panel fixtures

Place one identical artificial sequence in two separate panel manifests with
different declared roles. The fixture should yield two independently
provenanced matches, and the summary should remain competing/ambiguous under
the proposed semantics. This tests that:

- all role-specific hits are retained, including ties;
- panel results are not collapsed to one top hit;
- score comparisons do not cross incompatible search spaces;
- role labels on references are not promoted to candidate identity; and
- no panel match is treated as automatic contamination or exclusion.

Add an optional shared-short-motif case only if the output contract can retain
the short competing alignments and their coverage. Keep it distinct from the
full-length duplicate case so the expected reason for ambiguity is testable.

## 7. Future blinded biological benchmark

Do not execute or score this benchmark in the present task. A later,
independently governed benchmark should include:

- independently supported known satellite/subviral positives, keeping
  satellite RNAs and satellite viruses distinguishable;
- related non-satellite controls, including plausible helper/virus-like
  alternatives;
- difficult host and mobile-element decoys, plus organelle, microbial,
  vector/plasmid, and other relevant controls;
- short and incomplete known elements;
- divergent known elements; and
- family/clade-level and study-level holdouts.

Labels need documented provenance and an independent custodian. Freeze the
candidate set, reference snapshots, search tools, configuration, and
acceptance rules before unblinding. Do not calculate sensitivity,
specificity, or an overall accuracy claim now.

### Leakage prevention

For a divergent-recovery holdout, remove close relatives of each held-out
family/clade from every searchable source, not just the named nucleotide
panel. Check duplicate accessions, versioned records, synonyms, exact and
near-identical sequences, translated/protein records, and any profile or
model trained using the held-out lineage. Where study-level holdout is used,
remove records and derivative panels from that study as well.

Maintain an exclusion ledger with held-out IDs/hashes or protected cluster
IDs, exclusion reason, panel snapshot, curator, and review status. Freeze and
hash both the search snapshot and the holdout manifest before evaluation.
Keep the truth labels hidden from the implementation and fixture author
until outputs and acceptance rules are locked. Randomly splitting accessions
from the same family across reference and holdout is not an adequate leakage
control.

## 8. What these fixtures cannot validate

Synthetic fixtures can validate parsing, hashing, snapshot binding, panel
separation, strand/coordinate reporting, query accounting, failure states,
determinism, and safe handling of ambiguous or empty results. They cannot
validate biological reference labels, taxonomy truth, candidate origin,
contamination, helper dependence, biological identity, novelty, real-world
sensitivity/specificity, threshold calibration, or generalization to
divergent sequences.

A successful `art-complete-no-match` result says only that no qualifying hit
was reported for the exact synthetic query, tool, parameters, and miniature
references searched. It says nothing about unsearched databases or nature.

## 9. Remaining design decisions before implementation

1. Approve the reference panel roles, relevant hosts/organelles, sources,
   release cadence, taxonomy mappings, and panel-completeness semantics.
2. Select nucleotide-search methods, dependencies, sensitivity modes, bounded execution,
   output caps, and reproducibility/cache identities.
3. Define the output contract and exact execution/interpretation states,
   including what makes a panel complete and a no-match reportable.
4. Do not impose an arbitrary biological minimum candidate length. Review any
   method-specific technical applicability, identity, coverage, alignment, or
   score rule independently; this design sets no production threshold.
5. Approve how reverse-complement results, low complexity, partial alignments,
   ties, and competing panel roles are summarized without hiding raw hits.
6. Review source-specific licensing and redistribution terms before using any
   external reference data.
7. Assign independent label custody and approve family/clade/study holdout
   rules before running a biological benchmark.

**Next step:** review the fixture and remaining design decisions against the
approved M8/M9/M12 boundaries before creating sequence files or implementing
search behavior.
