# M21 Phase 2 — reference and blinding plan

**Status:** protocol proposal only; no reference panel, sample key, or biological search workflow was created or executed.

## Purpose

Prepare a future review-gated, blinded benchmark that keeps published truth and target sequences out of pipeline inputs until outputs are frozen. This document does not authorize FASTQ acquisition, reference searching, or biological pipeline execution.

## Target-excluded reference policy

Before any future benchmark, an independent reference curator should:

1. Define the target sequence set from the approved ground-truth dossier, including PV541158 and PV541159 and any other confirmed target sequence relevant to the cohort.
2. Predeclare a reproducible rule for excluding exact targets and close homologues from all search references available to operators. Record identity, coverage, length, sequence-family, and source rules before viewing pipeline outputs.
3. Search candidate reference sources using the frozen policy, retain a private exclusion ledger, and record public source accession/version, retrieval date, licensing/terms review, and cryptographic digest for every retained reference record.
4. Freeze the retained reference bytes and a manifest digest before creating benchmark inputs. Do not create or run a biological reference-search workflow in Phase 2.
5. Have a reviewer independent of pipeline operation verify the manifest, exclusions, and absence of expected target sequences from the operator-visible panel.

No reference FASTA or target sequence payload is included in this Phase 2 change.

## Ground-truth custody and sample grouping

- A custodian who does not operate or score the discovery workflow maintains the mapping from public sample identities and truth labels to opaque identifiers.
- The operator receives only approved read files, opaque IDs, and the frozen target-excluded references. Truth labels, PCR outcomes, expected sequences, and sample names must not appear in filenames, directories, configuration, cache keys, run manifests, or routine logs.
- Keep all libraries, lanes, technical replicates, and subsamples from the same biological plant or linked experimental unit in a single partition.
- Group by study and biological source before assigning development, validation, or held-out partitions. Do not split related units across partitions.
- Store the mapping key outside the analysis workspace and outside repository artifacts. Record who can access it, how it is protected, and when it is destroyed or archived under the approved protocol.
- Freeze and hash inputs, reference manifests, tool versions, configurations, and outputs before the custodian reveals labels to the independent scorer.

## Scoring and disclosure sequence

1. Approve read-use terms, technical adequacy, and the sample label evidence for each case.
2. Freeze the analysis plan, binary sample decision, candidate deduplication, target-matching rules, and denominators before execution.
3. Assign opaque IDs and verify that filenames/configuration/cache/logs do not disclose labels or target sequences.
4. Only after separate explicit authorization, execute the unchanged registered workflow in an isolated output root.
5. Freeze output files and hashes; then allow the independent scorer to join outputs to the sealed truth key once.
6. Mark missing, invalid, incomplete, or dependency-blocked cases unevaluable with explicit reasons. Any run after unblinding is exploratory and cannot replace the blinded result.

## Current Phase 2 state

The three public sample/run mappings are documented in the qualification report and matrix. The opaque IDs, sealed key, target-excluded reference snapshot, access-control arrangement, and input/output digests do not yet exist. Blinding readiness is therefore `PENDING` for all three samples. Phase 2 does not generate these artifacts or retrieve biological data.

