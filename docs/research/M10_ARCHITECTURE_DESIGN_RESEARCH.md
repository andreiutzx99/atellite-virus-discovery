# M10 architecture and topology evidence: design research

**Status: focused design research only.** M10 remains planned and is not
implemented. This report reconciles current project contracts with literature
on sequence repeats, genome termini, and circular-compatible assemblies. It
proposes a conservative, sequence-first evidence layer; it does not create a
released interface, biological classification, or claim of circularity,
completeness, replication, or function.

At the time this research was prepared, the roadmap described M1–M8 as
implemented and M9–M16 as planned. The current [roadmap](../ROADMAP.md) is
authoritative for present milestone ownership and status. The older [combined
M10/M11 report](M10_M11_DESIGN_RESEARCH.md) preserves an earlier numbering
conflict and is historical research, not the current M10 contract. The
[post-M7 reconciliation](../POST_M7_ROADMAP_RECONCILIATION.md) records the
later adopted milestone ownership but is also proposed design material, not a
released interface.

This report distinguishes:

- **EMPIRICAL/LITERATURE SUPPORT** — findings, methods, and limits reported by
  cited sources or already established project contracts.
- **PROPOSED M10 DESIGN** — a conservative design recommendation, not an
  implementation or approval.
- **UNRESOLVED DECISION** — a choice requiring later project review before
  production implementation or interpretation.

## 1. Scope and current project boundary

### EMPIRICAL/LITERATURE SUPPORT — current contracts

- M10's current roadmap purpose is to describe genome architecture, termini,
  completeness limits, and carefully scoped topology signals. It must not
  convert sequence or assembly patterns into confirmed molecule topology.
- The present M6-to-M8 handoff is a checksum-bound
  `m8_candidate_sequence_set` plus paired FASTA when sequence bytes are
  available. The artifact contract and
  [candidate handoff validator](../../satellite_discovery/m8_candidate_handoff.py)
  bind producer-declared candidate and sequence identities to exact sequence
  letters, lengths, source artifacts, M6 state, and completeness metadata.
  FASTA line wrapping is excluded from the sequence digest; different
  producer-declared candidates are not merged merely because their sequences
  match. The handoff imposes no positive minimum sequence length.
- This is an M6-produced artifact used by the M8 design and contract. Its name
  does **not** mean that M8 search is a prerequisite or that an M10 stage
  interface already exists.
- M6 reconstruction and read-support statuses are technical, run-scoped
  evidence. An assembled sequence remains available even if it did not pass
  M6's read-support promotion criteria. M6 read-back uses reads associated
  with assembly and is not independent validation; see
  [M6 residual support](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md) and
  [M8 contract validation](../M8_CONTRACT_AND_BLASTN_VALIDATION.md).
- M7 exact-recurrence records and provenance are separate, optional context.
  M7 retains declared observation metadata and does not establish biological
  identity or independence beyond those declarations; see
  [M7 recurrence](../M7_INDEPENDENT_RECURRENCE.md).
- M8 query status, nucleotide alignments, summaries, snapshots, commands, and
  raw-output provenance can be optional, separately typed context. M8 is
  implemented as a scoped software milestone, but candidate homology does not
  establish topology or biological identity.
- The [M9 contract freeze](../M9_CONTRACT_FREEZE.md) authorizes a synthetic,
  offline software baseline only; M9 remains planned/not implemented. M9
  predictions and results, if supplied later, are optional M10 context. An ORF
  is not required for M10 eligibility.
- The [module interface inventory](../MODULE_INTERFACES.md) explicitly warns
  that placeholder interfaces are not callable production stages. The
  combined M10/M11 research and roadmap reconciliation are proposals; neither
  creates M10 artifact contracts.

### PROPOSED M10 DESIGN — input and eligibility

1. Make one valid candidate sequence and its provenance the fundamental unit
   of M10 assessment. Consume the exact sequence bytes and stable
   producer-declared IDs; keep sequence hash, length, source-artifact identity,
   declared molecule type, completeness state, and available M6 reconstruction
   and support states alongside every result.
2. Keep candidates independent even when their sequence strings are identical.
   An implementation may reuse a computation internally only if it links the
   result separately to each candidate and preserves the original identities.
3. Preserve supplied M6/M7/M8/M9 context with artifact IDs, hashes, and original
   status values. These are contextual evidence, not M10 eligibility gates.
   Missing context means “not supplied,” not a negative finding.
4. A valid sequence remains eligible regardless of M6 support category, M7
   recurrence, M8 result, M9 ORF count, or M9 availability. A missing sequence,
   invalid handoff, or complete empty set must remain a distinct input state;
   none may be represented as an evaluated no-repeat result.
5. Do not alter the source sequence, repair ambiguous letters, silently convert
   T/U, join contig ends, or replace the source with a circularized view. Any
   derived comparison view must have its own named policy and digest.
6. Keep the first baseline sequence-only. Raw-read junction analysis, paired
   mapping, long-read review, assembly modification, and experimental assays
   are not required inputs. A future read-based branch would require separate
   approval, authorized source data, library provenance, and a clear handoff to
   M12.

## 2. Terminology and evidence boundaries

### EMPIRICAL/LITERATURE SUPPORT

These architecture terms describe different observations and should not be
treated as synonyms:

| Term | Narrow meaning | What sequence-only evidence cannot establish |
| --- | --- | --- |
| **Direct terminal repeat (DTR)** | Similar or identical sequence tracts at the two reported sequence ends in the same orientation. | Whether the tracts are native molecule termini, an assembly duplication, integration boundary, or another repeated architecture. |
| **Inverted terminal repeat (ITR)** | End regions align in reverse-complement orientation. | That the sequence is a transposon, a particular virus, or a closed/circular molecule. ITRs occur in mobile elements and some viral genomes. |
| **Terminal redundancy** | A molecule or assembled representation contains repeated sequence information at its ends; establishing biological redundancy can require comparison across molecule ends, isolates, or packaging evidence. | It is not synonymous with an exact DTR call on one assembled string. |
| **Terminal overlap** | A suffix and prefix of the submitted sequence align under a stated orientation and alignment policy. | Whether the overlap is duplicated sequence in the molecule or a redundant assembly representation. |
| **Terminal complementarity / cohesive-end-compatible sequence** | Opposing end tracts can form a reverse-complement relationship under the stated comparison. | Physical single-stranded overhangs, end chemistry, ligation state, or an experimentally established cohesive end. |
| **Circular permutation** | Related molecules have different sequence start points while representing permutations of shared sequence content; evidence is comparative across molecules, not a property inferable from one sequence alone. | A population-level packaging or topology mechanism from one contig. |
| **Circular-compatible sequence architecture** | A specified sequence-end relationship is compatible with a circularized representation under a declared method. | The existence of a circular molecule, covalent closure, biological genome topology, replication, or completeness. |
| **Assembly circularization** | A software/assembly representation joins or trims contig ends according to an assembly procedure. | That the input molecule was biologically circular or that the assembly boundary is correct. |
| **Biological topology** | The physical molecular state in the sampled material, under an appropriately defined assay. | It cannot be assigned from a sequence pattern or assembly label alone. |

Nayfach et al.'s CheckV method uses end-repeat signals, including an explicit
20-bp repeat rule in its closure procedure, and discusses alternative origins
including short-read assembly of circular genomes and concatemer-associated
linear genomes. The authors cross-check closure predictions with completeness
estimates and flag unsupported cases. That is a method-specific rule for its
target setting, not a universal minimum repeat length or a transferable
biological truth criterion for M10. CheckV also notes that ITRs are present in
mobile elements as well as some viral genomes.

Li et al. document diverse phage termini and packaging patterns, including
cohesive ends, DTRs, terminal redundancy with circular permutation, and
terminal host-derived sequence. Their categories make clear that the same
apparent sequence representation can arise from different packaging
architectures. PhageTerm uses next-generation sequencing read-end/coverage
patterns to infer phage termini and packaging strategy; it is not a
sequence-only circularity test and its assumptions are specific to suitable
phage sequencing libraries.

### PROPOSED M10 DESIGN — language policy

Use evidence-scoped terms such as:

- `TERMINAL_RELATIONSHIP_REPORTED`
- `DIRECT_TERMINAL_REPEAT_PATTERN_REPORTED`
- `INVERTED_TERMINAL_REPEAT_PATTERN_REPORTED`
- `TERMINAL_OVERLAP_REPORTED`
- `INTERNAL_REPEAT_REPORTED`
- `CIRCULAR_COMPATIBLE_SEQUENCE_ARCHITECTURE_REPORTED`
- `NO_MATCH_WITHIN_TESTED_ARCHITECTURE`
- `INSUFFICIENT_INFORMATION`

These are proposed examples, not approved enum values. Avoid statuses such as
`CIRCULAR_GENOME_CONFIRMED`, `COMPLETE_GENOME`, `LINEAR_GENOME_CONFIRMED`,
`SATELLITE`, or `NON_SATELLITE` from M10 sequence architecture alone.

If biological topology is a future question, the required evidence standard
must be separately approved for the molecule and assay. Appropriate physical
molecule-level or orthogonal end/topology experiments may be needed, with
positive, negative, and process controls. Read evidence for a proposed
end-to-start junction can support that a sampled library contains molecules
consistent with the adjacency, but duplicates, multimapping, chimeras,
ligation, amplification, or template switching remain alternatives. A read
observation is not itself an unconditional topology verdict.

## 3. Methods and tool comparison

### EMPIRICAL/LITERATURE SUPPORT

| Method/tool | Evidence it can produce | Strengths | Limits for M10 / short or partial candidates |
| --- | --- | --- | --- |
| **Exact end comparisons** | Exact suffix-prefix overlaps; same-orientation and reverse-complement comparisons between specified terminal windows. | Simple, deterministic, portable, easy to test with synthetic strings, no external dependency, and naturally preserves coordinates. | Misses substitutions and indels. A short exact match can be chance or low-complexity sequence. Must report tested window sizes and avoid treating every exact match as meaningful topology. |
| **Banded/semi-global end alignment** | Quantified terminal alignments allowing configured mismatches and/or gaps, with end anchoring. | Directly addresses partial, error-containing, and indel-bearing ends; reports aligned bases, identity, gaps, and coordinates. | Scores and band/window choices alter results. Short/ambiguous inputs can yield many equally plausible alignments. Must pin and report settings; no universal biological cutoff follows from the algorithm. |
| **Local self-alignment (Smith–Waterman class)** | Local matching segments within a sequence and between forward/reverse-complement views; can expose internal repeats and matches reaching termini. | General way to find partial and gapped local similarities; source algorithm is well established. | Self-comparison includes the trivial main diagonal and symmetric duplicate rows; threshold and scoring sensitivity matter. A score is not a biological significance value. Output can grow rapidly in repetitive/low-complexity strings. |
| **BLASTN self-search** | Seeded local HSPs between candidate and itself or its reverse complement. | Mature and familiar local-alignment tool; raw output and tool identity can be recorded. | External executable and database/index build add dependency burden. Seed, masking, scoring, result caps, and short-query task affect detection. E-values on a self-search are not a substitute for a calibrated repeat significance model; absence of an HSP can reflect seeding/reporting behavior. Existing M8 BLASTN settings are not an M10 profile. |
| **REPuter** | Maximal exact or approximate repeats, including direct/inverted structures, with algorithmic significance/visualization options. | Designed for repeat analysis and useful as an independent comparator for more complex repeats. | Additional executable/version/license/runtime policy and repeat parameters. Significance depends on its model and settings; it should not become a black-box biological cutoff. Not needed for the first transparent baseline. |
| **EMBOSS `einverted` / `palindrome`** | Candidate inverted repeats/palindromes with configured repeat length, gap, and mismatch behavior. | Focused, widely described utility; convenient cross-check for ITR-like patterns. | Tool settings and version must be pinned. Inverted-repeat detection only; not a general topology or direct-repeat method. Tool thresholds are not biological criteria. |
| **Tandem Repeats Finder (TRF)** | Periodic tandem units, copy structure, and approximate tandem repeats. | Established method for describing tandem arrays and periodic sequence organization. | Targets tandem periodicity, not terminal-overlap interpretation. Scoring and period bounds need explicit settings. Low-complexity or tiny candidates can produce uninformative repeat calls. |
| **minimap2 self-mapping** | Seeded mappings of a sequence to itself or a derived reference, often useful for long-read/molecule alignments. | Efficient for longer sequences and read-to-reference workflows. | Seeding/repetitive-region behavior can suppress or fragment short-candidate signals; mapping output is not a direct, exhaustive terminal-repeat inventory. Runtime/tool dependency is unjustified for short candidate-only baseline. |
| **PhageTerm** | Read-end/coverage evidence for phage termini and packaging-mode hypotheses. | A validated read-based tool for selected phage packaging contexts, using raw sequencing evidence rather than only a contig-end motif. | Requires suitable sequencing reads and library assumptions; not generic for satellites, RNA agents, or arbitrary assemblies. It does not provide universal biological circularity proof. |
| **CheckV closure procedure** | Comparative viral-genome quality context and repeat-/integration-associated closure predictions. | Published tool precedent for combining closure signals with other context. | Built for metagenome-assembled viral genomes and reference context; its repeat rule is method-specific. Not calibrated as an architecture classifier for short, divergent, noncoding, or nonviral candidates. |

Primary algorithm/tool sources include Smith and Waterman's local alignment
algorithm; Altschul et al.'s BLAST method; Kurtz et al.'s REPuter; Benson's
Tandem Repeats Finder; Rice et al.'s EMBOSS suite; Li et al.'s minimap2; and
the CheckV, PhageTerm, and phage-termini studies listed in
[References](#11-literature-and-tool-sources).

### PROPOSED M10 DESIGN — minimal baseline

Start with a deterministic, dependency-free **sequence-only baseline**:

1. Validate candidate identity, sequence hash/length, alphabet, availability,
   and provenance before analysis. Keep the original sequence immutable.
2. Compare terminal regions in same orientation and reverse-complement
   orientation. Enumerate exact prefix/suffix and end-to-end matches and retain
   all distinct/nested relationships, rather than returning only the longest.
   Use zero-based, half-open coordinates in normalized evidence.
3. Add a bounded end-anchored alignment path for partial terminal relationships
   only if its scoring, band/window, ambiguity, and result-cap rules are fixed
   and recorded. Keep exact and approximate methods as separate method IDs;
   do not silently fall back from one to the other.
4. Report internal exact repeat intervals and simple tandem periodicity as
   descriptive sequence patterns. Treat gapped local self-alignment, REPuter,
   EMBOSS, TRF, BLASTN, minimap2, CheckV, and PhageTerm as separately named
   optional comparators or later extensions, not silent substitutions.
5. Derive topology-compatible evidence only from explicit end-to-start
   relationships and cite the exact source alignment record(s). This is a
   compatibility statement about the submitted representation, not an
   independent signal or a conclusion about physical topology.
6. Retain all competing alignments and report method-specific quantitative
   observations. Do not reduce evidence to a single architecture score or
   biological class.

No universal minimum repeat length is proposed. If implementation requires a
reporting floor, max-hit cap, or resource bound, name it as a software/output
policy, record its value, and distinguish it from a biological threshold.
Exhaustive discovery must either complete or report truncation; a cap reached
must not be rendered as a complete no-match result.

For short sequences, directly scanning all terminal lengths is cheap and
auditable. If a simple implementation uses pairwise window comparison, bound
the window and document the expected quadratic work; exact border scans can
also use a linear-time prefix-function/Z-style method. Dynamic programming
costs scale with the compared window lengths, so a banded end alignment can
bound work. Internal all-v-all local alignment and approximate repeat
enumeration can produce many overlapping matches, especially for homopolymers;
cap and truncation semantics therefore belong in the contract, not just in
report rendering.

### UNRESOLVED DECISION — algorithm profile

Reviewers must choose whether the first implementation includes approximate
end-anchored alignments and gapped internal self-alignments, or begins with
exact comparisons only. If approximate methods are selected, approve scoring,
allowed ambiguity, terminal window size, gap model, duplicate/symmetry
canonicalization, output caps, and any method-specific reporting rule using
synthetic software tests first. No cutoff or profile is biologically calibrated
by the literature comparison in this report.

## 4. Typed evidence, quantitative fields, and states

### PROPOSED M10 DESIGN — record families

These are design-level record families, not current artifact-contract names or
released APIs. Every row should refer to the exact candidate and method run and
be deterministically ordered. Prefer separate evidence dimensions over a
composite score.

| Record family | Core content |
| --- | --- |
| **Terminal relationship** | Candidate/sequence IDs and hash; relationship geometry (`suffix_prefix`, `5prime_3prime`, `terminal_to_internal`, or equivalent); query/reference intervals; strand/orientation (`same` or `reverse_complement`); sequence length; aligned bases; identical/compatible/ambiguous bases; mismatches; gaps and gap opens; identity numerator/denominator; terminal-arm and whole-candidate coverage denominators; score where applicable; method and parameters. |
| **Repeat** | Repeat class and unit/period; each copy's coordinates; orientation; copy count; span and aligned bases; identity/mismatch/gap detail; tandem versus non-tandem; sequence-complexity annotation with method/window; source alignment ID. Keep internal repeats distinct from end-touching repeats. |
| **Self-alignment** | Query and target interval on the same candidate; forward/reverse-complement orientation; local alignment blocks; aligned length, identity, mismatches, gaps, score and denominators; explicit diagonal/symmetric-hit handling; any masking or seed policy. Do not label a tool score as a probability or biological significance. |
| **Topology-compatible relationship** | A derived, separately typed record linking the exact end-to-start alignment(s), proposed junction coordinates, orientation, overlap length/identity/gap profile, alternate terminal relationships, boundary/completeness context, method, and a narrow compatibility status. It must not claim molecular closure. |
| **Method/run accounting** | Candidate and optional context artifact descriptors and hashes; expected/completed method branches; input validity; dependency/tool identity; configuration; parser and normalizer identities; start/finish and outcome; raw/normalized output paths and hashes; output caps/truncation; warnings and limitations. |

For every comparison report enough quantitative detail to reproduce and
interpret it:

- exact input sequence hash and length; source artifact ID/hash; candidate ID
  and sequence ID; coordinate convention and orientation policy;
- both aligned intervals and their denominators, aligned bases, identity
  numerator and denominator, compatible and ambiguous columns, mismatches,
  gaps/gap opens, and method-specific score;
- terminal window sizes, repeat unit/period and copy count where applicable,
  comparison branch (direct or reverse complement), low-complexity/masking
  method and affected span, and any candidate-level completeness/boundary
  limitation;
- software, adapter, parser, normalizer and schema versions; full normalized
  configuration; exact dependency/runtime identity when applicable; and
  raw-output artifact/hash plus the normalized record's source-row/ordinal
  linkage.

The dependency-free implementation has no external raw stdout. It should still
write deterministic native result artifacts and bind every normalized row to
the method-run record, input hash, and configuration digest. An external
comparator must preserve its raw output and link parsed records to its raw row
or record ordinal. Do not invent a raw output where none exists.

### PROPOSED M10 DESIGN — scoped outcome axes

Keep input validity, method execution, result presence, boundary suitability,
and aggregate completion separate. Candidate vocabulary for later review:

| Scope | Proposed value/example | Meaning |
| --- | --- | --- |
| Input | `INPUT_VALID`, `INPUT_INVALID`, `SEQUENCE_UNAVAILABLE`, `COMPLETE_EMPTY` | Handoff and bytes state only. Invalid/unavailable input cannot become a completed no-match. |
| Method lifecycle | `NOT_SELECTED`, `NOT_APPLICABLE`, `NOT_STARTED`, `RUNNING` | Scope/lifecycle states, not results. |
| Execution | `COMPLETED`, `DEPENDENCY_UNAVAILABLE`, `EXECUTION_FAILED`, `INTERRUPTED`, `OUTPUT_INVALID`, `TRUNCATED` | Whether the declared method completed and its outputs were accounted for. |
| Evidence | `MATCHES_REPORTED`, `NO_MATCH_WITHIN_TESTED_ARCHITECTURE` | A method-scoped observation after input validation and complete execution; not biological presence or absence. |
| Applicability | `INSUFFICIENT_INFORMATION`, `BOUNDARY_LIMITATION`, `AMBIGUOUS_INPUT_LIMITATION` | A declared reason the method cannot answer a particular architecture question. It does not erase valid positive rows from another branch. |
| Aggregate | `COMPLETE` or `PARTIAL` under a declared required-method plan | Completion relative to the methods required by that run, not biological completeness. |

Status names are illustrative and need not be adopted literally. A no-match is
permitted only for the exact candidate, declared method, configured search
space, and fully accounted output. “No detectable terminal relationship
within tested method/window” is preferable to “no terminal structure.” Missing
data, failed execution, invalid/corrupt output, unsupported dependencies,
unknown boundaries, and truncation are not no-matches.

### PROPOSED M10 DESIGN — ambiguity, low complexity, and partiality

- Compare original characters under an explicit alphabet policy. Do not treat
  `N` or other ambiguous IUPAC symbols as universal wildcards. Preserve counts
  and coordinates of ambiguous comparisons, and distinguish definite identity
  from possible compatibility. A reverse-complement branch must state the
  molecule/alphabet rules; never silently convert DNA `T` and RNA `U`.
- Keep candidate-provided completeness and boundary metadata. If a candidate
  is partial, a positive repeat observation remains reportable, but a
  no-match cannot be interpreted as absence of a biological terminal feature.
  Use a per-method boundary limitation or insufficient-information state when
  the method requires an unobserved terminus.
- Retain low-complexity matches and mark their sequence composition/context;
  do not discard them silently. Low complexity can generate many exact
  matches, so a short motif must not be promoted to topology-compatible
  evidence without a separately declared rule. A masking branch, if later
  included, is a distinct configuration and result, not a hidden cleanup step.
- A candidate shorter than a requested window is still accounted for. The
  method can report whatever comparisons are possible and mark only the
  specific unavailable comparison insufficient; there is no length-only
  biological eligibility threshold.
- For multiple plausible terminal relationships, preserve every alignment,
  deterministic tie ordering, and any truncation. Do not select one “best”
  architecture as a winner.

## 5. Artifact differential and M12 boundary

### EMPIRICAL/LITERATURE SUPPORT

Published closure methods caution that repeated contig ends can arise during
assembly of circular templates or from linear genomes using concatemer
intermediates. Repeat collapse, repeated sequence, and assembly boundary choice
can therefore create or alter the apparent terminal relationship. Sequencing
errors and ambiguous calls can also affect alignments; low-complexity sequence
can produce many non-specific matches. A contig-level pattern does not reveal
which process generated it.

### PROPOSED M10 DESIGN — what M10 can and cannot flag

| Observation or alternative | M10 sequence-only treatment | Proper evidence owner / limit |
| --- | --- | --- |
| Identical/near-identical sequence at both ends | Report coordinates, orientation, quantitative match, repeated length, complexity and assembly-boundary context if supplied. | M10 flags the observed pattern; it cannot decide native DTR versus assembly duplication. |
| Low-complexity terminal match | Retain alignment and mark complexity/masking context. | M10 can flag sequence composition; biological specificity needs class-appropriate validation. |
| Ambiguous bases or short end windows | Count and locate ambiguous positions; record method limitations and tested span. | M10 input/method accounting; do not turn ambiguity into a match or negative result. |
| Candidate flagged partial/truncated upstream | Preserve the declared state and boundary limitations. | M10 reports that missing ends are unassessed; it cannot infer the unobserved sequence. |
| Adapter/vector/reagent contamination | A supplied sequence could be compared only under a separately declared reference policy; M10 itself does not identify source. | M12 source/read/control review; M8 owns candidate-to-reference nucleotide similarity. |
| PCR/RT template switching, ligation, concatemer, chimeric molecule | May be listed as alternative explanations for a pattern; no sequence-only artifact label. | M12 requires authorized reads, library protocol, controls and provenance. |
| Duplicate reads, multimapping, read-through, or read support | Not measured by sequence-only baseline. | M12 read-origin/artifact review; M6 read-back alone reuses assembly-associated reads and is not independent confirmation. |
| Assembly misjoin, repeat collapse, or terminal trimming | Report only if provenance or output boundaries were supplied; sequence-only evidence cannot validate assembly. | M12 and later assembly/read review with source data; M10 must not reassemble or rewrite input. |

The minimal baseline should not accept raw reads or library metadata. It may
emit a stable proposed end-to-start junction descriptor so a future M12 stage
can target a separately approved read-origin review. If a future M10 read
branch is approved, it must be separately identified and must not duplicate,
replace, or silently reinterpret M12's per-read accounting.

## 6. Stage-scoped cache and reuse guidance

### EMPIRICAL/LITERATURE SUPPORT — current identity semantics

The [stage identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md) documents the
current model: scoped stage keys bind stage/version and its own registration,
normalized configuration, typed input digests, dependency-inspector results,
and stage-scoped implementation identity. The complete workflow registry and
package-wide source hash are not used as a substitute when a stage supplies a
scoped identity. Reuse is limited to completed stages whose manifest and output
hashes verify.

Only named artifact-contract semantics are included in a stage's contract
identity. Changing one stage's contract should not invalidate unrelated
contracts. Changes to the shared validator semantic version or common workflow
cache/reuse semantics are intentionally broader and may invalidate every
affected stage.

### PROPOSED M10 DESIGN — identity dependencies

An eventual M10 cache key should include:

1. **Candidate and source identity:** exact candidate sequence digest and
   length; candidate/sequence/FASTA IDs; producer artifact digest and
   checksum-bound manifest; completeness/molecule metadata; any M6 evidence
   links that M10 reads or emits.
2. **Optional supplied context:** exact descriptors and content hashes for each
   M7/M8/M9 artifact actually validated, consumed, or passed through in M10
   outputs. Context remains optional. If absent, identity records absence; if
   supplied and changed, M10 changes. Do not add these inputs to M6–M9.
3. **Algorithm and configuration:** exact versus approximate method; terminal
   window sizes; direct/reverse-complement rules; ambiguous-base and
   T/U policy; end-anchoring, scoring/gap model, repeat period bounds, masking
   and complexity rules; reporting floors, result/resource caps, required
   methods, canonical ordering, and any derived topology-compatibility rule.
   Changing any behavior-affecting setting invalidates M10.
4. **Implementation and contracts:** M10-specific algorithm/runner modules,
   any M10-specific helper code, selected input/output contract semantic
   identities, parser and normalizer identity, output schema/version, and
   explicit M10 semantic-version bumps. A method/parser/semantics change must
   invalidate even if inputs are identical.
5. **External dependencies, if selected:** exact tool and builder name/version,
   executable or image digest, platform/runtime identity relevant to behavior,
   invocation settings, index/database digest, dependency inspection report,
   and any external reference snapshot. A dependency becoming unavailable or
   changing identity cannot reuse a prior completed result as if it were
   current.
6. **Output integrity:** manifest, raw-output references/hashes, normalized
   artifact hashes, and complete-work accounting. Corrupt or missing saved
   outputs fail closed; they are not reusable results.

The workflow registration should fingerprint only M10's own stage metadata.
The M10 handler should provide a scoped implementation identity rather than
falling back to package-wide source identity. Shared contract modules should
use named M10 contract semantics instead of hashing the entire module. This is
the current project's documented approach for M6–M8; a future M10 implementation
must follow it rather than assuming package-level identity automatically
provides isolation.

Expected invalidation behavior:

```text
M10 candidate or consumed context change ──────────┐
M10 algorithm / parser / contract semantics change ┤
M10 parameters / dependency / tool identity change ├──> invalidate M10
M10 stage registration / output schema change ─────┘

M10-only code/configuration/dependency change ───────> M6, M7, M8, M9 reusable
M6 input/code/contract change ───────────────────────> M6; downstream only when
                                                       their declared input digest changes
shared validator or workflow-cache semantics change ─> all affected scoped stages
```

An upstream candidate artifact changing naturally changes M10's input identity;
whether its producer stage reruns is governed by that producer's own inputs and
identity. “M10-only invalidation” means an M10 implementation, configuration,
parser, or dependency change alone must not force M6–M9 to rerun.

Required reuse regression checks should show that an M10-only code, configuration,
parser, contract-semantic, or optional external-tool identity change produces a
new M10 result while unchanged, integrity-verified M6–M9 outputs remain
reused. Separately verify that a changed candidate digest or consumed optional
context changes M10, and that a shared validator/cache-semantics version bump
has the intentionally broader effect described by the common identity policy.

## 7. Synthetic software-validation matrix

### PROPOSED M10 DESIGN

All fixtures below use artificial nucleotide strings and synthetic typed
provenance. Assert parser, coordinates, counts, statuses, hashes, determinism,
and reuse behavior only. Do **not** label fixtures satellite, non-satellite,
biologically circular, linear, complete, functional, or otherwise biologically
true.

| Fixture | Software assertion |
| --- | --- |
| Linear string with unrelated ends | All required configured terminal comparisons complete with no qualifying relation; retain the tested window/method and scoped no-match. |
| Exact direct terminal repeat | Report both arm coordinates, same orientation, exact aligned length/identity and both denominators. |
| Partial terminal repeat | Preserve the shorter/partial match, alignment coordinates, terminal-arm coverage, identity and gaps; do not suppress only because it is partial. |
| Inverted terminal repeat | Report reverse-complement orientation, both terminal intervals, aligned bases and mismatch/gap counts; do not infer a mobile element or topology. |
| Reverse-complement terminal relationship | Check the reverse-complement branch and orientation convention against a fixed synthetic pair; ensure forward and reverse evidence remain distinct and deterministic. |
| Circular-compatible end-to-start overlap pattern | Report the exact suffix-prefix alignment and linked compatibility record with its narrow wording; assert no confirmed-circularity field/status is emitted. |
| Internal repeat not involving termini | Report repeat/self-alignment coordinates and class; assert no terminal-relationship or topology-compatible record is derived from an internal-only match. |
| Low-complexity false-positive challenge | Retain and annotate the repeated low-complexity match; assert it is not silently discarded and does not become a topology conclusion solely from a short motif. |
| Very short valid candidate | Preserve candidate and sequence hash; run every applicable comparison; report an explicit method limitation where needed, not a biological length exclusion. |
| Partial candidate | Preserve completeness state. Positive observed sequence evidence remains reportable; lack of terminal evidence carries a boundary limitation/insufficient state, not a claim that termini are absent. |
| Ambiguous IUPAC bases | Preserve original letters/hash and ambiguous-position counts; assert `N` is not treated as an unrestricted wildcard and compatibility rules are deterministic. |
| Multiple competing terminal relationships | Retain every candidate alignment within configured output limits, deterministic order/ties, and truncation when a cap is reached; select no biological winner. |
| Assembly-like duplicated end | Report the duplicated end pattern and quantitative relation; preserve an assembly-artifact alternative/warning without asserting that duplication was an artifact. |
| No evidence within tested method | Complete all required scans and report only `NO_MATCH_WITHIN_TESTED_ARCHITECTURE` (or approved equivalent) scoped to the method and windows. |
| Insufficient information | Exercise unavailable sequence bytes, unsupported orientation/alphabet policy, or unobserved required boundary as separate scoped outcomes; do not emit a successful no-match. |
| Corrupted input | Alter FASTA bytes, manifest checksum, identity, alphabet, or bound source artifact; reject before accepting derived evidence and retain a typed invalid-input reason. |
| Optional-context/eligibility control | Run valid candidates with absent M7/M8/M9 context and with varied M6 support states; assert candidate eligibility is unchanged and absence is not a negative result. |
| Deterministic reuse | Repeat identical input/configuration/tool identity; verify stable normalized ordering, byte-identical deterministic outputs where promised, and reuse only after manifest and output verification. |
| M10-only invalidation | Change one M10 algorithm/config/parser/contract/dependency identity at a time; assert M10 is recomputed while unchanged M6–M9 stage keys and verified outputs remain reusable. |
| Input and shared-semantics invalidation | Change the candidate hash or consumed optional evidence and assert M10 invalidates. Separately bump shared validator/cache semantics and assert the documented broader invalidation. |

Also test interruption, dependency absence for optional methods, malformed
external-tool output, output caps, parser failures, missing provenance, and
tampered saved M10 output. Each case must preserve any independently completed
method rows, account for incomplete work, and prevent a partial/error status
from being rendered as no-match. Synthetic fixture success demonstrates
software behavior only; biological performance requires a separate M16 plan
and independently curated evaluation.

## 8. Downstream handoffs without decision transfer

### PROPOSED M10 DESIGN

| Milestone | M10 can provide | M10 must not decide |
| --- | --- | --- |
| **M11 — RNA structure and ribozyme evidence** | Exact sequence identity, orientation convention, boundaries, and any explicitly reported end relationship as optional context. | Which RNA fold is native, whether a ribozyme is active, or whether circular-compatible architecture is required for M11 eligibility. |
| **M12 — Read-origin and technical-artifact review** | Coordinates of candidate terminal relationships, overlap alternatives, assembly-boundary notes, and warnings to guide an approved source-read review. | Read origin, contamination, PCR/RT artifacts, duplicate independence, misassembly truth, or artifact attribution from sequence alone. M12 owns read/control/library evidence. |
| **M13 — DVG-versus-satellite differential evidence** | A separate, provenance-linked architecture evidence dimension and method status. | DVG/non-DVG or satellite/non-satellite classification; no M10 pattern is a universal hallmark. |
| **M14 — Helper association/dependence** | Optional descriptive architecture records linked by exact candidate identity. | Helper association, direct interaction, or biological dependence. |
| **M15 — Evidence integration/prioritization** | Typed evidence, provenance, competing relationships, missingness, and completion state for side-by-side integration. | An aggregate architecture score, uncalibrated probability, biological winner, or silent promotion of a method result. |
| **M16 — Blinded validation** | Frozen method/configuration identity, synthetic fixture expectations, and evidence fields requiring independent evaluation. | Biological truth labels or validation performance claims from software fixtures alone. |

Handoffs should reference stable candidate/sequence IDs and exact hashes, not
sequence similarity alone. Keep evidence records immutable and linkable;
downstream consumers must retain their original M10 states rather than
rewriting them as their own statuses.

## 9. Implementation risks and computational expectations

### PROPOSED M10 DESIGN

- **False interpretation from geometry:** the same sequence-end pattern can
  reflect distinct biological or technical processes. Use narrowly named
  evidence and retain alternatives at the point of display.
- **Threshold migration:** CheckV's implementation settings, BLAST's defaults,
  and an arbitrary percentage identity are not universal M10 cutoffs. Pin every
  method parameter and keep technical reporting rules separate from biological
  claims.
- **Repeat explosion:** low-complexity and tandem-repeat sequences can create
  many overlapping alignments. Use deterministic canonicalization, explicit
  resource/output limits, complete accounting, and a `TRUNCATED`-type state.
- **Boundary ambiguity:** the observed contig endpoints may be assembler
  boundaries rather than molecule termini. Preserve producer completeness and
  assembly provenance; never silently trim or circularize.
- **Alphabet ambiguity:** mixed DNA/RNA symbols and IUPAC ambiguity can alter
  reverse-complement behavior. Keep the original sequence and declare the
  comparison alphabet policy.
- **Partiality and short sequences:** limited sequence length reduces evidence
  available to a method but must not act as biological ineligibility. Scope
  insufficiency to the affected method.
- **Tool drift:** external repeat or circularity tools introduce platform,
  executable, parser, licensing, and database assumptions. Keep them optional
  until a specific M10 need and supported-input boundary are approved.
- **Cache over-invalidation:** hashing the whole package or all contracts would
  make unrelated edits invalidate M6–M9. Require an M10 scoped identity and
  regression tests for both isolated M10 changes and deliberately shared
  semantic changes.
- **Evidence duplication:** several metrics may be derived from the same
  alignment; M15 must not count the terminal match, its repeat annotation, and
  its topology-compatible derivative as independent observations.
- **Scientific validation gap:** software fixtures validate accounting and
  determinism, not sensitivity, specificity, topology, or genome completeness.
  M16 needs an independent, class-stratified benchmark and physical validation
  for biological claims.

For candidate-only strings, exact terminal scans and simple sequence summaries
should be inexpensive. A short-window pairwise dynamic program costs
approximately the product of the compared window lengths; whole-sequence
all-v-all repeat search can cost quadratically in sequence length and produce
quadratically many raw relationships in repetitive inputs. Bound windows,
memory, runtime, and output size. Streaming and stable ordering are preferable
for larger candidate sets. If read mapping is ever added, its cost scales with
read volume and it requires the separate data authorization, controls, and
accounting already noted; it is not a baseline M10 dependency.

## 10. Decisions requiring later approval

### UNRESOLVED DECISION

1. **Input availability and scope:** confirm the precise M10 stage handoff
   using the current M6-produced candidate sequence set; specify treatment of
   unavailable bytes, complete-empty sets, molecule type, boundary metadata,
   and partial sequences.
2. **Method baseline:** choose exact-only terminal/repeat scans versus adding
   approximate end alignments or gapped internal self-alignment; specify which
   external tools, if any, answer a need that the internal baseline cannot.
3. **Quantitative policy:** approve terminal window sizes, alignment scoring,
   gap behavior, low-complexity handling, repeat-period range, output floors,
   candidate caps, and truncation semantics. Do not interpret these as
   biological cutoffs without independent evidence.
4. **Alphabet policy:** define orientation and reverse-complement rules for
   DNA, RNA, mixed/unknown molecule labels, and IUPAC ambiguous symbols without
   rewriting the original input.
5. **Completeness language:** decide whether M10 reports only supplied
   completeness metadata and method-specific boundary limits, or includes any
   comparative completeness estimator. CheckV must remain explicitly
   applicability-limited if considered.
6. **Read evidence:** decide whether any M10 release may analyze raw reads at
   all. If approved, specify consent/authorization, source-read and library
   provenance, technology-specific mapping/anchor rules, duplicate/molecule
   accounting, controls, failure states, and non-duplicative M12 ownership.
7. **Typed artifacts and statuses:** approve schema versions, exact coordinate
   convention, evidence/run-status axes, raw-output retention, output limits,
   human report requirements, and downstream linking rules.
8. **Cache contract:** approve M10's explicit scoped implementation identity,
   selected contract-semantic versioning, dependency identity, and regression
   checks proving M10-only changes do not invalidate M6–M9.
9. **Validation boundary:** approve synthetic software acceptance criteria
   separately from any future M16 biological benchmark, truth-set curation,
   or topology assay.

No threshold, tool selection, or biological interpretation is approved by this
research report. A future implementation should begin only after its input,
method, output, cache, and validation choices are reviewed.

## 11. Literature and tool sources

These sources support method descriptions and limitations; they do not validate
an M10 implementation or establish the truth of any candidate architecture.

1. Nayfach S, Camargo AP, Schulz F, et al. “CheckV assesses the quality and
   completeness of metagenome-assembled viral genomes.” *Nature Biotechnology*.
   2021;39:578–585.
   [doi:10.1038/s41587-020-00774-7](https://doi.org/10.1038/s41587-020-00774-7).
   Repeat-based closure signals, scope, cross-checking, and alternative origins.
2. Li S, Fan H, An X, Fan H, Jiang H, Chen Y, Tong Y. “Scrutinizing Virus
   Genome Termini by High-Throughput Sequencing.” *PLoS ONE*. 2014;9(1):e85806.
   [doi:10.1371/journal.pone.0085806](https://doi.org/10.1371/journal.pone.0085806).
   Diverse phage terminus and packaging architectures.
3. Garneau JR, Depardieu F, Fortier LC, Bikard D, Monot M. “PhageTerm: a tool
   for fast and accurate determination of phage termini and packaging
   mechanism using next-generation sequencing data.” *Scientific Reports*.
   2017;7:8293.
   [doi:10.1038/s41598-017-07910-5](https://doi.org/10.1038/s41598-017-07910-5).
   Read-based phage-terminus inference; its input assumptions differ from
   sequence-only M10.
4. “Determining DNA Packaging Strategy by Analysis of the Termini of the
   Chromosomes in Tailed-Bacteriophage Virions.” *Methods in Molecular Biology*.
   2011. [PubMed Central chapter](https://pmc.ncbi.nlm.nih.gov/articles/PMC3082370/).
   Describes cohesive ends, DTRs, terminal redundancy, and circular permutation
   as distinct packaging patterns.
5. Smith TF, Waterman MS. “Identification of common molecular subsequences.”
   *Journal of Molecular Biology*. 1981;147(1):195–197.
   [doi:10.1016/0022-2836(81)90087-5](https://doi.org/10.1016/0022-2836(81)90087-5).
   Local alignment method foundation.
6. Altschul SF, Gish W, Miller W, Myers EW, Lipman DJ. “Basic local alignment
   search tool.” *Journal of Molecular Biology*. 1990;215(3):403–410.
   [doi:10.1016/S0022-2836(05)80360-2](https://doi.org/10.1016/S0022-2836(05)80360-2).
   Seeded local sequence search; not an M10 self-alignment configuration.
7. Kurtz S, Choudhuri JV, Ohlebusch E, Schleiermacher C, Stoye J, Giegerich R.
   “REPuter: the manifold applications of repeat analysis on a genomic scale.”
   *Nucleic Acids Research*. 2001;29(22):4633–4642.
   [doi:10.1093/nar/29.22.4633](https://doi.org/10.1093/nar/29.22.4633).
   Repeat-finding methods and analysis.
8. Benson G. “Tandem repeats finder: a program to analyze DNA sequences.”
   *Nucleic Acids Research*. 1999;27(2):573–580.
   [doi:10.1093/nar/27.2.573](https://doi.org/10.1093/nar/27.2.573).
   Tandem-repeat identification and parameterized scoring.
9. Rice P, Longden I, Bleasby A. “EMBOSS: the European Molecular Biology Open
   Software Suite.” *Trends in Genetics*. 2000;16(6):276–277.
   [doi:10.1016/S0168-9525(00)02024-2](https://doi.org/10.1016/S0168-9525(00)02024-2).
   Suite containing focused repeat/palindrome utilities.
10. Li H. “Minimap2: pairwise alignment for nucleotide sequences.”
    *Bioinformatics*. 2018;34(18):3094–3100.
    [doi:10.1093/bioinformatics/bty191](https://doi.org/10.1093/bioinformatics/bty191).
    Efficient mapping/alignment tool; not selected for the short candidate-only
    baseline.
11. Wu Q, Wang Y, Cao M, et al. “Homology-independent discovery of replicating
    pathogenic circular RNAs by deep sequencing and a new computational
    algorithm.” *Proceedings of the National Academy of Sciences*.
    2012;109(10):3938–3943.
    [doi:10.1073/pnas.1117815109](https://doi.org/10.1073/pnas.1117815109).
    Circular RNA discovery context; not a license to interpret a generic
    assembled overlap as biological circularity.

## 12. Project documents reviewed

- [Current milestone roadmap](../ROADMAP.md)
- [Post-M7 roadmap reconciliation](../POST_M7_ROADMAP_RECONCILIATION.md)
- [M6 residual assembly support](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md)
- [M7 independent recurrence](../M7_INDEPENDENT_RECURRENCE.md)
- [M8 implementation architecture](../M8_IMPLEMENTATION_ARCHITECTURE.md)
- [M8 contract and BLASTN validation](../M8_CONTRACT_AND_BLASTN_VALIDATION.md)
- [M9 contract freeze](../M9_CONTRACT_FREEZE.md)
- [Pre-M9 stage identity audit](../PRE_M9_STAGE_IDENTITY_AUDIT.md)
- [Module interface inventory](../MODULE_INTERFACES.md)
- [Historical combined M10/M11 research](M10_M11_DESIGN_RESEARCH.md)
- [M6-to-M8 candidate handoff validator](../../satellite_discovery/m8_candidate_handoff.py)
- [Artifact contracts](../../satellite_discovery/artifact_contracts.py)
- [Workflow stage identity and reuse](../../satellite_discovery/artifact_workflow.py)

This report does not create an M10 implementation or modify existing contracts,
production code, tests, README, roadmap, M9 materials, candidate data, or
`scripts/post-merge.sh`.

M10 architecture design research: READY FOR REVIEW