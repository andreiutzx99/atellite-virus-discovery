# Milestone 6 — residual-read evidence audit

This is a software and workflow integration audit, not a biological validation.
M6 reports only reads unaccounted for by a completed comparison to the declared
reference collection, followed by optional assembly and read-back evidence. A
residual is not evidence of novelty or satellite identity. M6 does not infer
biological identity, function, or candidate significance.
M7 is not part of this work.

| # | Check | Result and evidence |
| ---: | --- | --- |
| 1 | Existing workflow stages remain available | **PASS locally.** The default registry retains the existing stages; the M4 reuse regression passes. |
| 2 | M6 is registered in the trusted typed workflow | **PASS locally.** `residual_evidence` is registered with typed read, QC, reference-role, and optional DVG inputs. |
| 3 | QC remains a distinct typed artifact | **PASS locally.** `fastq_qc` publishes `qc.json` separately from its cleaned FASTQ outputs; M6 does not reuse the older `fastq_manifest` contract. |
| 4 | M6 consumes the exact QC output bytes | **PASS locally.** Input hashes are compared to the QC manifest's declared clean FASTQ digests before execution. |
| 5 | Layout and mate relationships are explicit | **PASS locally.** Declared single/paired layout must match supplied mates; FASTQ mate labels, identifiers, and record counts are checked. |
| 6 | Reference scope is declared and consistent | **PASS locally.** FASTA identifiers must match the supplied role table exactly; SAM sequence dictionaries, lengths, and mapped coordinate bounds are checked against that FASTA. |
| 7 | No workflow-supplied executable or shell command is accepted | **PASS locally.** Minimap2 is selected by the trusted dependency inspector and invoked with fixed argument lists through the bounded process runner. |
| 8 | User configuration is bounded | **PASS locally.** Sample identifiers, supported assemblers, numeric thresholds, threads, memory, and layout are validated; unsupported fields are rejected. |
| 9 | Query identity is tied to source reads | **PASS locally.** Stable internal query IDs are checked against the original read sequence hashes, including reverse-strand SAM records. |
| 10 | A residual requires complete comparison accounting | **PASS locally.** Every input query requires exactly one primary SAM record; unknown, duplicate, or missing primary queries fail closed. |
| 11 | Mapped SAM records stay within declared references | **PASS locally.** Reference IDs, `@SQ` lengths, CIGAR spans, and coordinates are validated; undeclared or out-of-bounds mappings cannot produce residuals. |
| 12 | Paired SAM records preserve mate identity | **PASS locally.** Paired flags and first/second mate identities are validated; if either mate maps, the full fragment is treated as accounted for. |
| 13 | Source files cannot change unnoticed during screening | **PASS locally.** Streaming passes compare record, base, byte, and FASTQ digest totals; the external-tool lifecycle rechecks input hashes before completion. |
| 14 | Residual and triage categories remain distinct | **PASS locally.** Original residuals, assembly-eligible reads, retained-unassembled reads, unresolved reads, and support outputs are separate artifacts. |
| 15 | Original unresolved records are preserved | **PASS locally.** Selected records are copied from the original FASTQ, not reconstructed from normalized mapper input; paired tests check both mates. |
| 16 | Triage remains technical and conservative | **PASS locally.** Length, ambiguity, entropy, and quality thresholds emit reason codes; no novelty or biological classification is assigned. |
| 17 | Triage-excluded residuals cannot support an assembly | **PASS locally.** Only eligible fragment IDs are sent to assembly and read-back; retained-unassembled fragments remain unresolved. |
| 18 | Assembly is optional and uses trusted adapters | **PASS locally.** Only registered SPAdes or Tadpole adapters can run; disabling assembly preserves residuals without claiming a negative result. |
| 19 | Assembly alone cannot establish a supported reconstruction | **PASS locally.** Supported contigs are emitted only after independent read-back meets configured criteria. |
| 20 | Read-back alignments are validated independently | **PASS locally.** Query sequence hashes, contig dictionary, CIGAR, NM, MAPQ, aligned fraction, sequence identity, and coordinate bounds are checked. |
| 21 | Support requires breadth, depth, and distinct fragments | **PASS locally.** Support, low-support, cross-contig ambiguity, unrelated-read, and unsupported outcomes have synthetic tests; coverage windows use bounded local coordinates. |
| 22 | Paired support requires both mates | **PASS locally.** Paired support utilities require both declared mates for a fragment to resolve; incomplete support leaves the fragment unresolved. |
| 23 | Failure outcomes remain distinguishable | **PASS locally.** Missing dependencies, execution failures, invalid assembly output, failed support mapping, invalid support output, disabled assembly, and unsupported results do not collapse into one negative status. |
| 24 | DVG status is linked without converting unavailable runs to zero evidence | **PASS locally.** DVG evidence is optional for assembly; supplied evidence and summary status/count must agree, unavailable/incomplete states are preserved, and `NO_DVG_EVIDENCE_DETECTED` is not treated as confirmed non-DVG. |
| 25 | Provenance binds outputs to inputs and tools | **PASS locally.** Residual manifests record read/QC/reference/role digests, comparison scope, tool identity, parameters, and output digests. |
| 26 | Output contracts and consolidated reporting are typed | **PASS locally.** M6 manifests, triage tables, support evidence, and reconstruction evidence have dedicated contracts and are accepted by the workflow report stage. |
| 27 | Reuse does not mutate cached evidence | **PASS locally.** Output validation is read-only; a completed synthetic run verifies reuse, while changed optional assembler identity blocks reuse. |
| 28 | Implementation changes invalidate reuse | **PASS locally.** Cache identity includes the M6 adapter, residual/support/QC, contract, assembly, and external-tool implementation digests. |
| 29 | Real minimap2 runtime behavior is exercised | **PASS locally.** `python scripts/check_minimap2_ci.py` used minimap2 2.29-r1283 on generated sequences: three reads were fully accounted, two residual reads passed read-back, and no biological conclusion was made. |
| 30 | Optional-tools CI includes the M6 runtime check | **CONFIGURED; CI REQUIRED.** The Ubuntu optional-tools job installs minimap2, runs the artificial check, and uploads its synthetic diagnostics. Its remote result must pass before merge. |
| 31 | Complete local test suite | **PASS locally.** The default suite ran 369 tests (361 passed, 8 optional-tool skips); with `RUN_OPTIONAL_TOOL_TESTS=1`, all 369 passed. Compilation, package wheel build, and `git diff --check` passed. |
| 32 | Ubuntu/Windows Python matrix | **REQUIRED GATE.** The configured matrix covers Ubuntu and Windows on Python 3.11 and 3.12; every leg must pass before merge. |
| 33 | GitHub checks, review, and merge | **REQUIRED GATE.** Merge only after all required remote checks pass; local results are not a substitute for GitHub status. |

## Default triage and support criteria

The default technical triage retains residual reads shorter than 50 bases,
with more than 5% ambiguous bases, entropy below 1.2 bits, or mean Phred
quality below 20 as **retained-unassembled**. They remain in the residual
artifacts and cannot enter assembly or read-back. These values are configurable;
the configured minimum read length must be at least 1.

A read qualifies for support when its mean Phred quality is at least 20, its
ambiguous fraction is at most 5%, MAPQ is not 255 and is at least 20, at least
80% of its query bases align, and sequence identity is at least 95%. A contig is
read-supported only when it also has at least two distinct sequence hashes and
two distinct fragments, coverage breadth of at least 80%, and mean depth of at
least 2. Coverage windows are 100 bases for reporting. Paired fragments count
as resolved only when both mates qualify on the same supported contig.

Per-contig outcomes are `READ_SUPPORTED_ASSEMBLY` when all criteria pass,
`LOW_SUPPORT_ASSEMBLY` when qualifying reads exist but the thresholds are not
met, `AMBIGUOUS_ASSEMBLY` when qualifying mates from a fragment span multiple
contigs, and `UNSUPPORTED_ASSEMBLY` when no qualifying read evidence exists.
The aggregate is `NO_SUPPORTED_ASSEMBLY` if no contig passes; it is not a
negative reference-screen result or a biological conclusion.

M6 has no configured minimum contig-length cutoff: assembly FASTA validation
requires non-empty contigs and records the observed minimum length. The
50-base read threshold can keep shorter residual reads out of assembly, but
does not remove them from residual artifacts. Assembler-specific output
filtering is outside that M6 threshold and remains a consideration for the
separate scientific review of very small satellite/subviral sequences.

The artificial minimap2 check and all synthetic tests are software checks only.
They do not establish sensitivity, specificity, clinical validity, or biological
significance.