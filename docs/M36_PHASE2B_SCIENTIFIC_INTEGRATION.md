# M36 Phase 2B Scientific Integration Readiness

## Decision

The 520-assignment matrix remains **NO-GO**. This note records what the frozen
design currently says, the exact reproducibility gaps, and a proposed private
manifest preparation method. It does not supply missing scientific values,
amend the preregistration, or authorize any registered attempt.

## Current frozen baseline

The preregistration names the existing M25 synthetic read generator, a 900-nt
target, nominal coverage 48, 100-nt reads, substitution rate 0.02, insertion
and deletion rates 0.01, uniform read starts, and synthetic-background
coverage. Those are the values stated in
`M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json`; they do not fully define
family-sequence construction, random-number derivation, technical-reference
construction, or realized coverage accounting.

There is also an implementation discrepancy to resolve: the preregistration
names `read_start_mode: uniform`, while the M36 M25 audit fixture currently
uses `random`. Do not select one silently. Confirm which matches the approved
design and record a preregistration amendment if the approved source does not
already settle it.

## Unresolved scientific specifications

| Topic | What is specified | Required decision before a condition is READY | Amendment status |
|---|---|---|---|
| Target/background 1:9 | **BLOCKED.** The condition label says `target_background_abundance_1_to_9`; current audit code counts target-derived and synthetic-background reads and excludes technical-reference reads. | Confirm whether abundance means read count, sequenced bases, or another measure; define eligible read roles, treatment of indel-altered lengths, integer rounding, measurement point, and tolerance. The exact-count read-ratio rule in the audit is an implementation proposal, not an adopted frozen rule. | Required unless the approved preregistration source explicitly supplies the same denominator and zero-tolerance rule. |
| Low-complexity sequence | **BLOCKED.** The label says `low_complexity_stress_sequence`. | Freeze the recipe, motif/composition constraints, length, seed derivation, and acceptance metrics; verify deterministic bytes across supported runtimes. Existing M19/M32 patterns are examples only and are not substitutes for an M36 decision. | Required if the chosen recipe or metrics are not already in the approved source. |
| Alternate error positions | **BLOCKED.** The condition says “same rates,” and the M25 baseline samples distinct positions uniformly. | Specify the alternative position distribution, sampling/replacement rule, how the same realized rates are enforced, and the validation statistic/tolerance. No alternative distribution is selected here. | Required unless the approved preregistration fully defines it. |
| Other baseline details | **BLOCKED where unspecified.** The preregistration lists target length, nominal coverage, read length, error rates, read-start mode, and background coverage. | Confirm target/background sequence generation, technical-reference source, seed-to-RNG mapping, coverage denominator, insertion/deletion semantics, and the `uniform` versus `random` read-start discrepancy. | Required for any changed frozen value; clarifications require documented source evidence and independent review. |

### Proposed resolution process (not a parameter decision)

The design owner should provide the authoritative source text or an explicitly
approved amendment for each unresolved item. Record the exact source, version
or digest, decision, measurement procedure, and amendment requirement. Keep
proposed alternatives separate from the frozen catalog; do not mark a row
`READY` until the catalog and its digest reflect an approved decision.

## Restricted evaluator manifest preparation

The existing runner expands the 520 registered assignments and validates the
design digest, condition-catalog digest, 12 family seeds, 4/4/4 family split,
alternative-assembler 4/0/4 split, distinct family/read seed roles, independent
repeat read seeds, and shared paired-assembler inputs. Use that validator as
the acceptance gate rather than implementing a second set of rules.

`satellite_discovery.m36_manifest_builder` implements the join and
post-write validation. It consumes an approved restricted source map with this
shape:

```json
{
  "schema": "m36-approved-evaluator-source-map-v1",
  "provenance": {
    "source_id": "approved-source",
    "source_version": "v1",
    "approval_reference": "review record"
  },
  "families": [
    {"family_id": "f01", "family_seed": 123, "split": "development"}
  ],
  "read_seeds": [
    {
      "block_id": "positive_recovery",
      "family_id": "f01",
      "condition_id": "c01",
      "repeat_id": "r01",
      "read_seed": 456
    }
  ]
}
```

The example values are illustrative only. They are not M36 seed or split
assignments and must not be copied into an evaluator source map.

Preparation procedure:

1. Obtain an approved evaluator-only source map outside the checkout. It must
   provide one `family_id -> {family_seed, split}` row per registered family
   and one read seed for every unique `(block_id, family_id, condition_id,
   repeat_id)` tuple. Paired assemblers intentionally share that tuple's read
   seed. Preserve the source's provenance and approval record.
2. Expand assignments from the frozen design, join only those approved values,
   and derive condition parameters from the frozen design/catalog. Never
   synthesize missing seeds, splits, or condition values.
3. Validate the complete manifest with `validate_evaluator_manifest`, then
   serialize canonical JSON and bind the design and condition-catalog digests.
4. Run `python -m satellite_discovery.m36_manifest_builder` with the frozen
   design, approved source map, checkout root, restricted root, and public root.
   The command emits only aggregate counts and digests. Store the manifest in a
   provisioned owner-only restricted volume using
   immutable, exclusive creation. Re-read the stored bytes and validate them
   again. Report only the assignment count and digests outside the restricted
   store; keep seeds, truth, family-to-split mappings, and condition decoding
   out of analyst-facing artifacts.
5. If any approved source row or scientific decision is missing, stop and
   report the missing key. Do not create a partial manifest or infer a value.

The source-map schema is an operational input format, not a change to the
scientific design. Its seed and split values are private evaluator inputs and
must never be placed in source control, PR text, logs, or public outputs.

## Adapter evidence checkpoints

Any eventual adapter must preserve these independent stage outcomes and
content digests:

1. **Generation:** M25 FASTQ bytes, generator identity, placement ledger, and
   independently re-counted role/error/coverage metrics.
2. **Assembly:** exact paired-input digests, frozen SPAdes/Tadpole identity,
   canonical contig bytes, raw logs, and resource-enforcement evidence.
3. **Read support:** support thresholds and per-read/per-contig digest-linked
   placement records. A raw contig is not thereby a read-supported contig.
4. **Detection handoff:** typed M6 candidate-sequence-set validation, then
   frozen M8/M31 processing if its required reference snapshot and complete
   inputs are explicitly available. Without those inputs report detection as
   `NOT_EVALUATED`; do not treat assembly or support as candidate acceptance.

No single aggregate “success” may erase an earlier stage failure or
unevaluable result. Raw inputs, truth, mappings, and tool logs remain restricted
until the run-wide validation and blinding gates pass.

The new unregistered fixture harness exercises M25 generation, injected
assembly/support/detection boundaries, and the M25-to-support crosswalk with
four separate digest receipts. It is deliberately not a substitute for
verified SPAdes/Tadpole execution, a measured M6 support adapter, or a complete
M8/M31 workflow. The registered adapter entry point remains explicitly
disabled; the coordinator rejects it before expanding or launching attempts.

## Host prerequisites (documentation only)

- Provision a durable volume outside the checkout and public artifact tree;
  verify owner-only permissions, durability, backup/restore behavior, and
  non-symlink paths before use.
- Install the public Ed25519 trust anchor at the configured root-controlled
  location. Keep the private key in the approved host secret-management
  facility; never place it in Git, task files, PR text, or logs.
- A future workflow must be manually dispatched, protected by environment
  approval, bind approval to the exact source/design/tool/manifest/resource
  digests, and remain disabled until separately reviewed and authorized.
- Preserve immutable, content-hashed evidence and exact executable, runtime,
  and archive identities. The current CI smoke is not proof that the production
  host or durable storage is provisioned.

## Safety state

- Registered matrix: `NOT_RUN`.
- Phase 2B authorization: `false`.
- Biological sequencing data: not used.
- Frozen M6/M8/M31 settings and M34/M35 results: unchanged.
- PR #103 remains draft and unmerged; M37 has not started.
