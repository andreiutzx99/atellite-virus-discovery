# M9 empirical method validation

**Status: software-method review; M9 remains planned and unimplemented.**

**Validation scope:** synthetic sequences and artificial profiles only. No biological candidate dataset or biological reference database was searched or downloaded. No production M9 code, contract, or test was added.

## Executive summary

The tests support the architecture’s conservative direction, but they do not select biological thresholds or validate biological sensitivity:

- A small deterministic six-frame enumerator retained plus- and reverse-strand ORFs, nested starts, two-residue products, boundary partials, ambiguous codons, and changed start/code hypotheses. These are distinct outputs of declared policies, not gene calls.
- BLASTP, BLASTP-short, BLASTX, DIAMOND, and HMMER returned materially different output as query length, task, masking, composition handling, and reporting limits changed. Exact synthetic matches were easy; short random alignments and composition-sensitive results were also observable.
- HMMER’s default bias filter, `--nobias`, `--nonull2`, and `--max` produced different hit sets and scores on the same artificial profiles. HMMER’s machine tables list reported matches, not a complete no-hit row for every query.
- Single-threaded normalized BLASTP and HMMER tabular rows were repeatable for fixed fixtures. A target cap hid a tied reference without a native “truncated” marker in the result table. A profile searched before `hmmpress` failed rather than producing a no-hit.
- No experiment establishes an ORF minimum, peptide cutoff, E-value threshold, profile threshold, biological sensitivity, or a candidate identity. MMseqs2 was not available in the local package catalog and was not tested.

**Recommended baseline:** keep deterministic ORF enumeration separate from reference searches; record each declared start/code/partial policy; retain all ORF hypotheses without a biological minimum; translate ambiguous codons explicitly (for example `X`); use local BLASTP and HMMER only against approved, immutable, caller-supplied snapshots; preserve a separate optional BLASTX branch; expose masking/composition settings and competing hits; and keep no-ORF, no-hit, insufficient-information, invalid, unavailable, failed, interrupted, and truncated states distinct. Defer DIAMOND/MMseqs2 routine use, remote profile comparison, CDD, biological cutoffs, and all biological classification pending review and approval.

## 1. Evidence baseline and scope

The current [roadmap](ROADMAP.md) assigns M8 to nucleotide homology and M9 to translated/protein evidence. The M9 architecture proposal, preserved outside current main, is design context rather than implementation authorization; it specifies the validated M6 candidate-sequence set as the identity/byte source, with M7/M8 as optional context rather than eligibility gates. It also keeps ORF derivation separate from reference-dependent searches and disallows biological identity, novelty, expression, function, and helper-dependence conclusions from M9 alone.

The historical [M8/M9 design research](research/M8_M9_DESIGN_RESEARCH.md) contains protein-method proposals but records an obsolete milestone-label discrepancy. The current roadmap governs milestone status; the M9 architecture proposal is preserved design context, not a document on current main. No separate M9 protein-evidence research document was present when this validation began. The inspected M8 candidate handoff binds exact sequence bytes and hashes without imposing a length minimum; at the time of this validation, M8 search states and scientific behavior were unchanged. The later pre-M9 work changed identity/cache scoping, not those scientific semantics (see the [pre-M9 stage identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md)). Current M8 uses its own `REFERENCE_PANEL_INVALID` and `REFERENCE_PANEL_INCOMPLETE` vocabulary. This report proposes M9 snapshot vocabulary separately and does not edit or generalize M8 contracts.

All experiments below use artificial input sequences and toy reference sets generated locally in temporary directories. No Pfam, CDD, RefSeq, UniProt, viral, host, or other biological database/profile payload was downloaded, bundled, or searched. Tool/version observations are local runtime facts, not claims about what is supported in production.

## 2. Test environment and reproducibility

Observed environment: Linux x86-64 NixOS container, Python 3.12.12, 4 available CPUs and about 7.8 GiB visible memory. Runs used one search thread. Temporary databases, HMMs, and outputs were not retained in the project.

| Tool | Observed version and use | Software terms checked | Test and CI implications |
| --- | --- | --- | --- |
| NCBI BLAST+ | 2.16.0; `makeblastdb`, `blastp`, `blastx` | NCBI source/toolkit publishes a public-domain notice; verify the exact packaged binary and included components before distribution. | Local Linux executable; TSV output. Fixed-input, one-thread normalized BLASTP output repeated byte-identically. Suitable for offline CI with tiny artificial FASTA fixtures and a pinned executable identity. |
| HMMER | 3.4 (Aug 2023); `hmmbuild`, `hmmpress`, `hmmscan` | Upstream source is BSD 3-Clause; Easel and included third-party components have their own terms. | Local Linux executable; `--tblout` and `--domtblout` rows repeated identically after normalization. Artificial profile build plus `hmmpress` is a small offline CI fixture. Missing pressed index returned an error. |
| DIAMOND | 2.1.11; `makedb`, `blastp --sensitive/--very-sensitive` | Upstream repository identifies GPL-3.0. | Local Linux executable; TSV output; fixed one-thread cap fixture repeated identically. Tiny-database wall times are dominated by startup and are not a performance comparison. |
| MMseqs2 | Not installed or tested; the Replit system-package catalog rejected `mmseqs` as unavailable. | Current upstream repository lists MIT; the exact pinned release and its dependencies must still be checked. This differs from older project research text describing MMseqs2 as GPL-licensed. | No runtime, sensitivity, determinism, or CI behavior measured. Reconsider only after an exact release can be installed and tested against the same frozen artificial fixtures. |
| NCBI ORFfinder | Web documentation checked; no local executable/version was pinned or run. The web page offers a standalone Linux x64 executable and limits the web query region to 50 kb. | Exact standalone release and redistribution terms were not established in this test. | A changing web service is not a reproducible M9 dependency. A local binary would need version/hash pinning and offline synthetic tests. |
| Prodigal | Upstream README identifies version 2.6.3 (February 2016); not installed or tested here. | Upstream repository identifies GPL-3.0. Verify the pinned release and dependencies before packaging. | Upstream describes Linux, macOS, and Windows binaries; no local platform behavior was tested. A context-specific prokaryotic caller is not a neutral replacement for six-frame enumeration on short/unfamiliar candidates. No M9 result depends on Prodigal. |

Local measured executable SHA-256 values:

| Binary | SHA-256 |
| --- | --- |
| `blastp` | `e17de0fd689f89dcb095eea2626710a206ab3d016a183f064c388f963ecbc7c4` |
| `blastx` | `d83fbe89f34670c623ffb60723a5c2da246e91c358b91a7f8597ad49731bc1a3` |
| `makeblastdb` | `6797dd00e0dddfa0529de795ded12b41738792c9b75bf3643e1f03a782d2008f` |
| `hmmscan` | `70e94ba0a5cb53e4d40a8c4ea279a4b30bc8279081e61d7d0c5c0b7fd411bec2` |
| `hmmbuild` | `007e01cf9d58c4dbfbe183bda3a426ee44b7399ed6e080b61587d77532d51d14` |
| `hmmpress` | `f6f4a8d62d2187781c02ae5004705ccb8ef235d990b8b9cec621cb348e4a4330` |
| `diamond` | `80981d3e9d4c705aa88af17d4918efaf99ad85baa5ac2191275018ba5753c97e` |

These hashes identify the local executables tested, not a portable binary bundle. Tool and fixture versions, command settings, reference/profile digests, and parser identity must be pinned together for production reuse. Synthetic-data generation used Python’s `random.Random` with fixed seeds; timing values below are single-run observations on this host, not benchmark claims. Peak RSS was not measured. No runtime or resource conclusion should be extrapolated to large external snapshots.

## 3. ORF and genetic-code observations

### Method used

A compact test enumerator iterated frames 0, 1, and 2 on the input and reverse complement. It reported every configured start through the first in-frame stop, plus explicitly enabled sequence-boundary partials. Coordinates were mapped to the original sequence as zero-based, half-open intervals. The test translator emitted `X` for an ambiguous codon. It did not infer expression, use a learned gene model, repair frameshifts, or circularize the sequence.

The policy was varied rather than silently chosen after seeing a search result. For the comparisons below, a complete start-to-stop ORF requires a start in the declared start set and a stop under the declared translation table. Partial-boundary records carry separate partial flags and are not recast as complete ORFs.

Reproduction outline: for each of the six strand/frame combinations, split the oriented sequence into complete codons at that frame offset; for every codon in the declared start set, translate through the first in-frame stop (excluding the stop codon), or to the last complete codon when 3′ partials are enabled. Independently emit the leading complete-codon segment through its first in-frame stop as a 5′ partial when that option is enabled and no in-frame start precedes it. Translate unresolvable codons as `X`. For a minus-strand oriented interval `[a,b)` on a sequence of length `n`, map it to original coordinates `[n-b,n-a)` and retain strand `−`. Complete start enumeration, rather than “first start only,” is what yields nested rows.

| Synthetic input | Observed result under stated policy | What this establishes |
| --- | --- | --- |
| `ATGAAATAA` | `+`, frame 0, `[0,9)`, `MK` | The expected forward-strand, stop-terminated fixture is enumerated. |
| `TTATTTCAT` (reverse complement of the above) | `−`, frame 0, `[0,9)`, `MK` | Reverse-strand translation and original-coordinate mapping work for this fixture. |
| `AATGAAATAA` and `AAATGAAATAA` | `+`, frames 1 and 2 respectively, `MK` | The offset frames are evaluated rather than only frame 0. Reverse-complemented offset fixtures likewise returned the intended `MK` in reverse frames. |
| `ATGAAAATGCCCTAA` | Nested `+` frame-0 records `[0,15)`, `MKMP`, and `[6,15)`, `MP` | Keeping every declared start preserves nested/overlapping hypotheses; longest-only selection would discard one. |
| `ATGTTTTAA` | `[0,9)`, `MF` (two amino acids) | Small ORFs are enumerable when no biological minimum length is imposed. |
| `ATGAAAC` | `[0,6)`, `MK`, partial at the 3′ boundary | A missing terminal stop can be represented as a partial hypothesis. |
| `CCCAAATAA` | `[0,9)`, `PK`, partial at the 5′ boundary | A boundary-to-stop segment can be represented separately when partial 5′ enumeration is enabled. |
| `ATGNNNTAA` | `[0,9)`, `MX` | An ambiguous internal codon can be retained without inventing a concrete residue. |
| `GTGAAATAA` | No complete ORF when only `ATG` starts are accepted; `GTG` in the declared start set yields `MK` | Start policy changes the ORF set. The alternative start is translated as initiator methionine only in that declared hypothesis. |
| `ATGATATGATAA` | Code 1: `MI`, ending at `TGA`; code 2: `MMW`, ending at `TAA` | A declared table can change both residue identities and stop boundaries. The table must be recorded; this is not evidence for which table applies to an unknown candidate. |
| `CCCCCCCC` | No complete start-to-stop ORF under the tested policy | “No ORF” means none under this enumeration policy, not a biological noncoding conclusion. |

The compact enumerator emitted incidental short partial/frame records in some fixtures when that option was enabled. That is expected from an inclusive enumeration policy, but it reinforces the need to record the policy and retain competing rows rather than choosing a favorable sequence. The experiment did not test every NCBI genetic code, RNA editing, programmed frameshifting, circular-origin traversal, or caller-specific gene prediction. Circular translation remains outside the baseline.

### Recommended ORF defaults

1. Enumerate both strands and all three frames using a declared table and start/stop policy; retain each candidate ORF and overlaps. Preserve alternative start/table interpretations as separate hypotheses.
2. Apply no universal biological ORF-length cutoff. If storage/reporting bounds are later needed, make them explicit technical limits and report excluded counts and truncation.
3. Record original sequence identity, translation table, initiator set, stop set, partial flags, ambiguity policy, and exact coordinates for every row. Preserve the original nucleotide bytes; derived normalization needs its own identity.
4. Translate unresolved ambiguous codons as `X` under the initial conservative policy and preserve the source codon. Do not choose a genetic code or start policy because it creates a desired match.
5. An empty completed enumeration is `NO_ORF_PREDICTED_WITHIN_POLICY`; it is not a negative biological call. Do not send an empty peptide FASTA into protein search and label it no-hit. A separately selected translated-nucleotide branch may still run.

## 4. Protein and translated search observations

### Artificial panel and command settings

The protein panel contained five invented records: one 80-aa random protein, its exact duplicate under a second reference ID (a competing-role tie fixture), an 80-aa variant with eight seeded substitutions, its 40-aa internal fragment, and an unrelated 80-aa random protein. The base sequence was generated from `ACDEFGHIKLMNPQRSTVWY` with seed 417, then positions `[34,39)` were replaced by `AAAAA`; its SHA-256 was `5dae6b1565959592ddeadc50756268f605d5862a6d2dd22984c9b1850c0092aa`. Query fixtures included exact prefixes of 6, 8, 12, 20, 40, and 80 aa; seeded 12-aa and 40-aa substitutions; an exact 40-aa internal partial; a random 80-aa sequence; `A` repeated 24 times; and `KRR` repeated eight times.

BLAST+ commands used local `makeblastdb`, `blastp` tasks `blastp` and `blastp-short`, E-value reporting threshold 2000, at most 20 targets and one HSP per target, one thread, and tabular output containing IDs, identity, alignment coordinates/length, E-value, bit score, and sequence lengths. `-seg yes/no` was explicitly varied. Default task scoring parameters were otherwise retained, so task-specific score values are not cross-calibrated. DIAMOND used `makedb` followed by `blastp --sensitive` or `--very-sensitive`, E-value threshold 2000, at most 20 targets, one thread, and tabular output; its normal masking defaults were left enabled. These permissive E-value reporting settings intentionally expose weak rows for inspection; they are not candidate acceptance thresholds.

To regenerate the five-record protein panel and query sequences under Python 3.12, use this deterministic recipe (FASTA headers are shown as stable fixture IDs):

```python
import random

AA = "ACDEFGHIKLMNPQRSTVWY"

def peptide(n, seed):
    rng = random.Random(seed)
    return "".join(rng.choice(AA) for _ in range(n))

def mutate(sequence, count, seed):
    rng = random.Random(seed)
    result = list(sequence)
    for index in rng.sample(range(len(result)), count):
        result[index] = rng.choice([aa for aa in AA if aa != result[index]])
    return "".join(result)

base = peptide(80, 417)
base = base[:34] + "AAAAA" + base[39:]
references = {
    "comp_A": base,
    "comp_B_duplicate": base,
    "mutant80": mutate(base, 8, 82),
    "partial40": base[20:60],
    "unrelated80": peptide(80, 908),
}
queries = {
    f"exact{length}": base[:length] for length in (6, 8, 12, 20, 40, 80)
}
queries.update({
    "sub12": mutate(base[:12], 2, 112),
    "sub40": mutate(base[:40], 4, 140),
    "partial40": base[20:60],
    "random80": peptide(80, 330),
    "low_A24": "A" * 24,
    "biased24": "KRR" * 8,
})
```

For example, after writing those mappings as FASTA, the ordinary BLASTP command was `makeblastdb -in references.faa -dbtype prot -out proteins`, followed by `blastp -task blastp -query queries.faa -db proteins -seg no -evalue 2000 -max_target_seqs 20 -max_hsps 1 -num_threads 1 -outfmt '6 qseqid sseqid pident length qstart qend sstart send evalue bitscore qlen slen' -out result.tsv`. Replace `-task blastp` with `-task blastp-short` and vary `-seg yes/no` for the other observed BLASTP runs. The DIAMOND comparison used `diamond makedb --in references.faa --db proteins.dmnd`, then `diamond blastp --sensitive` or `--very-sensitive` with the same query, E-value and target cap, `--threads 1`, and the equivalent tabular columns. The translated test encoded 20 residues as 60 nt and ran `blastx` against the same artificial protein database with `-seg no -evalue 2000 -max_target_seqs 100 -max_hsps 1 -num_threads 1`. These recipes identify the synthetic test, not a production profile.

### Observed output

| Case | BLASTP observation | Other observation |
| --- | --- | --- |
| Exact 6-aa query | Standard `blastp` reported local 6-aa matches (example E-value `1.0e-3`); `blastp-short` reported the same exact region under its short-query settings. | DIAMOND reported no 6-aa result in either tested mode. |
| Exact 8-aa query | BLASTP and BLASTP-short reported exact local alignments. | DIAMOND reported no 8-aa result in either tested mode. |
| Exact 12-aa query | Both BLAST tasks reported exact matches. | DIAMOND reported exact matches. |
| Exact 20–80-aa queries | Exact and duplicate-reference matches were reported; the observed exact 80-aa standard-BLASTP E-value was `3.14e-61` in the compact five-record fixture. | Both DIAMOND modes reported exact matches at 12 aa and above in this fixture. |
| 12-aa query with two substitutions | Standard BLASTP reported an 83.3%-identity, 12-aa local alignment (example E-value `6.09e-6`). | DIAMOND `--sensitive` reported none; `--very-sensitive` reported the alignment (example DIAMOND E-value `3.04e-7`). BLASTP and DIAMOND E-values are method/search-space specific and are not directly comparable. |
| 40-aa query with four substitutions | Standard BLASTP reported an alignment to the artificial 80-aa template and its duplicate at 90% identity across 40 aa. | Both DIAMOND modes reported the comparable synthetic alignment. |
| 40-aa internal fragment | Local alignments included both the 40-aa fragment record and the longer parent template, retaining competing targets and coverage differences. | Both DIAMOND modes reported the fragment and full-length targets. |
| Random 80-aa query | A standard BLASTP short local alignment of six residues was reported at E-value `1.2`; BLASTP-short reported short, weak rows at E-values around `1.7–3.7`. | DIAMOND reported no result under these settings. |
| `A`×24 low-complexity composition control | With BLASTP-short and `-seg no`, a 17-residue local alignment at 29.4% identity, score 3.6, E-value 953 was emitted against the artificial panel. With `-seg yes`, no such row was emitted. | DIAMOND’s default masking/seeding did not report this query in the tested run. |
| Duplicate exact references | Equal-scoring, equal-E-value hits to both IDs were retained when the target cap allowed it. | A top row is not a unique interpretation; preserve ties and reference roles. |

With the same small fixture, `blastp-short` settings produced stronger numerical scores/lower E-values for exact short matches than ordinary `blastp`, but also surfaced a 5-residue random local alignment. This is a concrete demonstration that task, matrix, word size, composition controls, masking, database size, and permissive reporting affect output. It is not evidence that one task or a particular short length is biologically sensitive or specific.

### Translated search

BLASTX was run on a 60-nt invented sequence encoding a 20-aa segment of the artificial target, without forcing an ORF start codon. With one thread, `-seg no`, E-value reporting threshold 2000, and a local artificial protein database, BLASTX returned an exact 20-aa alignment in frame `+1` (query coordinates 1–60; target coordinates 1–20; E-value `2.40e-14`). This shows the software can report a six-frame translated alignment without the ORF-enumerator’s canonical-start requirement. It remains a separate translated-search result, not retroactive confirmation of an ORF or a coding claim.

### Search caps, repeatability, runtime

- Repeated normalized tabular BLASTP output for the same input files, executable, one-thread settings, and parameters was byte-identical (36 rows; SHA-256 `09ce0a482100d94ba4ff7068100e5e7abce94d8fc52ac10a0886c7a01c8593bd`). Repeated one-thread BLASTP and DIAMOND cap-fixture output was also identical within each tool.
- With two exact tied target records and `max_target_seqs=1`, both BLASTP and DIAMOND returned one result and exited successfully. BLASTP’s TSV row did not state that a second tied reference was omitted. The M9 runner must record the cap and treat a reached cap as incomplete/truncated unless completeness is independently established; exit code zero is not enough.
- Single-run timings on this host were approximately 0.06–0.10 s for the 12-query BLASTP tasks, about 0.2 s for a BLASTX test that searched a somewhat larger synthetic target panel, 0.04–0.13 s for DIAMOND search modes, and 0.005–0.015 s for the tiny HMMER fixture. Startup, database preparation, warm caches, and scheduling dominate such tiny runs. No peak RSS was measured; these are not throughput estimates.

### Interpretation and default

BLASTP is the most reviewable initial local similarity baseline already proposed by the architecture. Use the ordinary mode as a declared main branch and evaluate short-query behavior as a separately declared branch; do not silently mix their scores or defaults. Preserve BLASTX as an optional independent branch with its own translation table, six-frame coordinates, executable identity, snapshot, and state. DIAMOND is a justified scale/sensitivity comparator but not a drop-in result-equivalent replacement; the small synthetic comparison demonstrates a mode-specific difference at 12 aa, not a general sensitivity advantage. MMseqs2 remains unmeasured. Do not choose any short-peptide cutoff, score, identity, coverage, or E-value from these artificial results.

## 5. Profile-HMM and composition observations

### Fixtures

Two artificial 48-column amino-acid alignments were constructed from invented sequences, each with six sequences. The first model’s base sequence was `MTSICPWHVYMDACEQAWGNAAAAAANQGRRKWQPFCRGPRKYIEHRS`; the second was `QIIRAQIIYYQSLQYSDFLALMLLPNRYWPTADPQRQSKDSWWLSAKH`. Aligned variants were generated from fixed seed 9031 and fixed per-sequence seeds. Query fixtures were full model-A and model-B sequences (48 aa), a 28-aa internal model-A fragment, an 8-aa model-A segment, a weakly mutated model-A sequence, an unrelated random 48-aa sequence, `A`×24, a `K/R`-biased 24-aa sequence, and `W`×12. `hmmbuild` generated the profiles and `hmmpress` prepared the local profile file.

`hmmscan` emitted `--tblout` and `--domtblout` with `--noali`, `-E 1000`, and `--domE 1000`; the permissive cutoffs were for observing weak outputs, not interpreting them as significant. Separate runs varied `--nobias`, `--nonull2`, and `--max`.

The profile fixture is reproducible with Python 3.12 using the following generator. Write each alignment as Stockholm format with the shown IDs, build each profile with `hmmbuild --amino`, concatenate the HMM files, and run `hmmpress -f profiles.hmm`. The query FASTA is the `queries` mapping:

```python
import random

AA = "ACDEFGHIKLMNPQRSTVWY"
rng = random.Random(9031)

def random_peptide(n):
    return "".join(rng.choice(AA) for _ in range(n))

def variant(sequence, seed):
    local = random.Random(seed)
    result = list(sequence)
    for index in range(len(result)):
        if (8 <= index < 20 or 26 <= index < 42) and local.random() < 0.10:
            result[index] = local.choice([aa for aa in AA if aa != result[index]])
    return "".join(result)

model_a = list(random_peptide(48))
model_a[20:26] = list("AAAAAA")
model_a = "".join(model_a)
model_b = random_peptide(48)
alignment_a = [model_a] + [variant(model_a, seed) for seed in range(1, 6)]
alignment_b = [model_b] + [variant(model_b, seed) for seed in range(21, 26)]
queries = {
    "full_A": model_a,
    "partial_A": model_a[11:39],
    "short_A": model_a[20:28],
    "weak_variant_A": variant(model_a, 88),
    "full_B": model_b,
    "random48": random_peptide(48),
    "lowcomplex24": "A" * 24,
    "biased24": "KRRKRRKRRKRRKRRKRRKRRKRR",
    "no_match": "W" * 12,
}
```

### Observed output

| Mode | Observed synthetic result |
| --- | --- |
| Default filters | Full model-A query: sequence E-value `8.7e-44`, score 134.8; 28-aa partial: `5.3e-21`, score 61.8; weak variant: `4e-42`, score 129.4; full model-B query: `5.5e-42`, score 128.7. The 8-aa query and composition controls were not reported in this default table. |
| `--nobias` | The 8-aa model-A segment appeared with E-value `0.0027`, score 5.1, bias 7.0; `A`×24 appeared at E-value 2, score −18.6, bias 37.5. These are weak outputs from an artificial profile, not domain evidence. |
| `--nonull2` | The same full model-A query changed from score 134.8/E-value `8.7e-44` to score 141.6/E-value `6.5e-46`; the partial score changed from 61.8 to 71.7. Disabling composition correction changes numeric evidence materially. |
| `--max` | Bypassing HMMER’s heuristic filters exposed additional weak cross-model and random/composition rows, including the unrelated random query against model A (score −0.6, E-value 0.17), `A`×24 (score −18.6, E-value 2), and biased `K/R` rows. The `W`×12 no-match fixture still produced no reported row at these settings. |

The same prepared profile/query inputs produced the same four non-comment default `tblout` rows on repeated runs (normalized-row SHA-256 `72a7700ad0aa19998d285803b561fd4284149dac6936ac421b1c52ff24f89ed5`). Only reported hits appear in these tables; absent query rows are not self-describing no-hit results. Maintain an expected candidate/query × method × snapshot accounting record outside the hit table.

### Failure and truncation fixtures

- Running `hmmscan` against the generated profile file before `hmmpress` exited with status 1 and reported that its binary auxiliary files were unavailable. That is profile preparation/reference failure, not no-hit.
- A post-capture truncation fixture retained 1 of 4 generated domain-table rows. The original HMMER invocation had completed successfully; truncation was injected after capture to model an output cap. It demonstrates why byte limits and row validation belong to the runner/parser contract, not to interpretation of HMMER’s exit status alone. HMMER did not emit a native “truncated” state for this fixture.

The profiles were trained only on tiny artificial alignments, so their E-values, filtering behavior, and scores are not transferable to Pfam, CDD, custom viral models, or any future approved collection. HMMER is a reasonable local profile-HMM engine, but production thresholds should prefer a source model’s reviewed gathering threshold when appropriate and must retain threshold provenance, coverage, coordinates, competing models, model hash, and raw tables. `hmmsearch` has the reverse query/database orientation; it must not be substituted without recording a distinct method.

## 6. Literature-supported conclusions (separate from observations)

The following are supported by the linked methods documentation/literature; they do not validate this project’s thresholds or any biological result:

- NCBI ORFfinder exposes start-policy choices (ATG-only, alternative starts under a selected code, or any sense codon) and genetic-code selection. NCBI’s genetic-code tables show that codon meaning and initiation behavior can differ across tables. A tool’s default minimum-length control is a software option, not a biological minimum for M9.
- BLASTP and BLASTP-short are distinct parameterized search tasks; NCBI describes the short-query task and documents scoring, masking, composition-based statistics, target caps, and output controls. BLASTX translates nucleotide queries for protein comparison. Results and E-values remain conditional on method settings and the searched database/search space.
- Altschul et al. introduced BLAST’s local similarity/statistical framework; Lu et al. (2024) revisit BLASTP E-value calibration, reinforcing that a reported E-value should not be read as a calibrated probability of biological homology. Neither source provides a universal M9 peptide cutoff.
- Profile HMMs encode position-specific conservation from alignments; HMMER documents `hmmscan`, its bias/acceleration filters, score reporting, and machine-readable tables. A profile hit is compatibility with a specific model and threshold, not demonstrated expression, full-protein identity, or function.
- DIAMOND and MMseqs2 are designed for scalable sequence searches. Their published speed/sensitivity claims are not measured by the tiny local fixtures here and do not establish equivalence to BLASTP for short M9 peptides.
- Software and database/profile terms are independent. A software license does not authorize retrieval or redistribution of a database built from separately licensed sources.

## 7. Proposed typed result semantics and accounting

Keep input validity, candidate availability, method applicability, reference validity, execution completeness, and evidence result as separate fields. Suggested branch outcomes:

| Outcome | Recommended meaning and guard |
| --- | --- |
| `ORF_PREDICTED` | Enumeration completed under a recorded policy and emitted one or more hypotheses. This is not expression or function. |
| `NO_ORF_PREDICTED_WITHIN_POLICY` | Enumeration completed and emitted zero ORFs under the recorded policy. Not a biological negative. Protein-reference searches are `NOT_RUN_NO_ORF`, not completed no-hit; separately selected BLASTX may still run. |
| `SEARCH_COMPLETED_MATCHES_REPORTED` | An informative query completed against a valid complete declared snapshot and one or more rows passed the declared report settings. Keep weak, short, composition-sensitive, tied, and partial rows visibly qualified. |
| `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES` | An informative query completed, the full declared snapshot and all scoped inputs were valid, every required query/role/method was accounted for, output parsed successfully, and no reportable result remained under the recorded search settings. This means only “no hit reported in this named scope.” |
| `INSUFFICIENT_INFORMATION` | The declared method/query combination cannot support an informative search under an approved technical rule. Preserve reason and diagnostics; do not call it no-hit. Do not add an arbitrary biological peptide minimum. |
| `INPUT_INVALID` / `CANDIDATE_SEQUENCE_UNAVAILABLE` | Identity/alphabet/hash/contract invalid / a valid upstream record lacks sequence bytes. |
| `REFERENCE_SNAPSHOT_INVALID` / `REFERENCE_SNAPSHOT_INCOMPLETE` | Hashes, manifest, built index, roles, or membership validation fail / the declared reference set or its required payload is absent or known incomplete. Retain any partial positive evidence with the warning; never emit scoped no-hit. |
| `DEPENDENCY_UNAVAILABLE` | A required executable, runtime, index builder, or verified tool identity is missing or unusable. |
| `SEARCH_FAILED` / `SEARCH_INTERRUPTED` | Nonzero execution/parser/output-validation failure / cancellation, timeout, or other incomplete stop. Retain safe partial raw output with its status. |
| `SEARCH_TRUNCATED` | A hit/target/output/byte/time/result limit prevented complete accounting, including an externally cut output. Preserve the limit, partial rows and raw bytes; do not report no-hit. |
| `NOT_SELECTED` / `NOT_APPLICABLE` / `NOT_STARTED` / `RUNNING` | Lifecycle/scope only; none is a successful negative search. |

For a completed protein/profile assessment, emit a candidate-level record even when the candidate has no predicted ORF and a query-level result for every applicable query, method, role, and selected snapshot. Reconcile expected ORFs/proteins, queries, selected branches, target/profile snapshots, raw-output files, parsed row counts, and output hashes. `COMPLETE` should mean complete only relative to the declared required branch plan; any missing, invalid, failed, interrupted, uninformative, or truncated required branch makes the evidence assessment `PARTIAL`. Workflow artifact creation is not equivalent to biological-search completeness.

Two invariants are mandatory:

1. **No ORF is not a negative biological call.**
2. **No protein/profile match is not novelty.** A completed no-hit is limited to the named valid snapshot, tool, parameters, query, masking, reporting rules, and date-independent content digest actually searched.

The following state table is a contract truth-table proposal, not behavior implemented or exercised by an M9 stage:

| Synthetic condition | ORF/query outcome | Search outcome |
| --- | --- | --- |
| Valid candidate, completed enumeration with zero ORFs | `NO_ORF_PREDICTED_WITHIN_POLICY` | Protein-search branch `NOT_RUN_NO_ORF`; not a no-hit. |
| Valid peptide and complete informative search with zero reportable rows | ORF status remains independent | `SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES`. |
| Query/method ruled technically uninformative or no defensible profile query | ORF status remains independent | `INSUFFICIENT_INFORMATION`; not a no-hit. |
| Invalid candidate identity/alphabet/hash | No derived ORF result accepted | `INPUT_INVALID`. |
| Required snapshot payload absent / a snapshot or index digest fails validation | No valid search result accepted | `REFERENCE_SNAPSHOT_INCOMPLETE` / `REFERENCE_SNAPSHOT_INVALID`, respectively. |
| Required executable/runtime unavailable | Candidate may remain valid | `DEPENDENCY_UNAVAILABLE`. |
| Nonzero execution or malformed/contradictory parsed output | Preserve any safe partial raw bytes | `SEARCH_FAILED`. |
| Timeout or cancellation before accounting finishes | Preserve any safe partial raw bytes | `SEARCH_INTERRUPTED`. |
| Hit, output, or byte cap reached before complete accounting | Preserve partial rows and the cap | `SEARCH_TRUNCATED`; never no-hit. |
| Only some required method/role branches completed | Retain branch-level evidence and reasons | Aggregate `PARTIAL`, even if one completed branch had no hits. |

## 8. Candidate tools and operational recommendation

| Method | Decision from this validation |
| --- | --- |
| Transparent six-frame enumeration | Retain as the M9 ORF baseline because assumptions and coordinates are inspectable. Freeze its exact start, stop, partial, ambiguity, and translation-table rules before implementation. |
| NCBI ORFfinder | Useful independent comparator because start policies and translation tables are explicit. Its web service is not the reproducible production path; evaluate a version-pinned local executable before adopting it. |
| Prodigal | Do not use as the general M9 baseline. Its published target is prokaryotic gene recognition/initiation-site prediction; evaluate only for a separately approved context and labeled benchmark. |
| BLASTP / BLASTP-short | Keep BLASTP as the initial local similarity method family. Treat short-query settings as a distinct empirical branch; synthetic short exact matches and weak random alignments do not select a production threshold. |
| BLASTX | Keep as a separately declared optional nucleotide-to-protein translated search, useful for evidence missed by ORF start assumptions. It never turns a BLASTX row into an ORF call. |
| HMMER `hmmscan` | Keep as the initial profile-HMM method family after profile source, model thresholds, release, rights, and indexed payload are approved. Synthetic models validate runner mechanics only. |
| DIAMOND | Retain as an optional comparator for scale/sensitivity evaluation. Do not silently substitute its hit set/statistics for BLASTP; its tested short-query result differed at 12 aa. |
| MMseqs2 | Not empirically compared in this environment; do not select it based on upstream speed claims. Current upstream license is MIT, but tool version, platform build, exact command, output determinism, and CI/runtime behavior remain untested. |
| CDD / RPS-BLAST; HH-suite; InterProScan | Not exercised. CDD PSSMs are distinct from HMMER HMMs; HH-suite/profile-profile and integrated signature resources need separate method, database, runtime, privacy, and license decisions. Keep HH-suite deferred as the architecture recommends. |

For any future production search, use caller-supplied immutable protein/profile snapshots rather than downloading or bundling biological databases. Bind provider, exact release/accessions, retrieval date, normalized membership, record/model hashes, build/index command and identity, output/search limits, rights/attribution, and excluded/withheld records in each snapshot manifest. A checksum proves bytes, not annotation accuracy or completeness. Establish a no-network CI suite using the artificial fixtures and pinned executables; validate exact stdout/stderr handling, deterministic normalized rows, malformed/corrupt snapshot rejection, timeouts, caps, resume/cache identity, and empty-input accounting. Run a separate resource benchmark before selecting operational budgets.

## 9. Human approvals and unresolved decisions

Before production M9 implementation or biological reference retrieval, human reviewers must approve:

1. Which genetic-code tables/start policies may be used, what evidence justifies an alternative, and whether partial-boundary enumeration is in or out of the first contract.
2. Exact protein-reference and profile roles, source releases, curation owner, taxonomic annotation policy, source terms, attribution/redistribution or local-build policy, and benchmark holdouts. No reference resource is approved by this report.
3. BLASTP task and short-query policy, BLASTX applicability, HMMER filter/threshold policy, any DIAMOND/MMseqs2 comparator, and role-specific method coverage. These fixtures do not justify a hit threshold, minimum length, or ranking rule.
4. Per-stage execution/resource limits, cancellation semantics, output/target caps, resume policy, and which selected branches are required for aggregate `COMPLETE`.
5. **Historical finding — CLOSED:** At the time of this validation, M8's implementation identity hashed the shared `artifact_contracts.py` and `artifact_workflow.py`, creating a compatibility blocker for M9 registration. The merged pre-M9 stage-scoped cache-identity work subsequently resolved it: current main uses stage-scoped implementation, contract, and registration identities (see the [pre-M9 stage identity audit](PRE_M9_STAGE_IDENTITY_AUDIT.md)). This is not a current M9 implementation gate.
6. Whether any later blinded biological benchmark is authorized, its labels and custodians, length/composition strata, family/study holdouts and leakage controls, decoys, predeclared metrics, and acceptable error costs. It is outside this synthetic validation.

## 10. Concise M9 baseline proposed for review

1. Consume only the validated, hash-bound M6 candidate-sequence handoff. Preserve optional M7/M8 provenance without making it an eligibility gate or changing M6–M8 outputs.
2. Produce deterministic, six-frame ORF hypotheses under an explicit code/start/partial policy; retain overlaps, small and partial hypotheses, ambiguous residues, exact source coordinates, and completed no-ORF outcomes. No circular branch or biological length cutoff by default.
3. Produce exact derived-protein bytes/hashes separately. Search selected proteins with local BLASTP and approved HMMER `hmmscan` snapshots; leave BLASTX optional and separate. Defer DIAMOND/MMseqs2 as production dependencies and HH-suite, CDD, and broad integrated-profile passes.
4. Emit query/method/role/snapshot rows for every planned branch, retain raw outputs and quantitative alignments, preserve competing/tied hits, explicitly expose masking/composition choices and technical truncation, and aggregate only against a frozen required-branch plan.
5. Use typed statuses from §7. A valid completed no-hit is scoped to its exact method and complete snapshot; no ORF and no protein/profile hit never become a negative biological or novelty claim.

## 11. References checked

Official documentation and upstream licensing pages checked on 2026-09-26:

- NCBI [ORFfinder](https://www.ncbi.nlm.nih.gov/orffinder/) and [NCBI genetic-code tables](https://www.ncbi.nlm.nih.gov/Taxonomy/taxonomyhome.html/index.cgi?chapter=cgencodes).
- NCBI [BLASTP application options](https://www.ncbi.nlm.nih.gov/books/NBK279684/table/appendices.T.blastp_application_options/), [BLASTX application options](https://www.ncbi.nlm.nih.gov/sites/books/NBK279684/table/appendices.T.blastx_application_options/), [BLAST+ release notes](https://www.ncbi.nlm.nih.gov/books/NBK131777/), and [BLAST+ user manual](https://www.ncbi.nlm.nih.gov/books/NBK279691/).
- NCBI [C++ Toolkit public-domain notice](https://github.com/ncbi/ncbi-cxx-toolkit-public/blob/main/LICENSE) and [BLAST+ documentation/source repository](https://github.com/ncbi/blast_plus_docs).
- Eddy SR. 2011. [Accelerated Profile HMM Searches](https://doi.org/10.1371/journal.pcbi.1002195). *PLoS Computational Biology* 7(10):e1002195.
- HMMER [User’s Guide](https://eddylab.org/software/hmmer/Userguide.pdf) and [upstream license](https://github.com/EddyRivasLab/hmmer/blob/master/LICENSE).
- Altschul SF, et al. 1990. [Basic local alignment search tool](https://doi.org/10.1016/S0022-2836(05)80360-2). *Journal of Molecular Biology* 215:403–410.
- Lu YY, et al. 2024. [A BLAST from the past: revisiting blastp’s E-value](https://doi.org/10.1093/bioinformatics/btae729). *Bioinformatics* 40(12):btae729.
- Buchfink B, Reuter K, Drost H-G. 2021. [Sensitive protein alignments at tree-of-life scale using DIAMOND](https://doi.org/10.1038/s41592-021-01101-x). *Nature Methods* 18:366–368. DIAMOND [upstream GPL-3.0 license](https://github.com/bbuchfink/diamond/blob/master/LICENSE).
- Steinegger M, Söding J. 2017. [MMseqs2 enables sensitive protein sequence searching for the analysis of massive data sets](https://doi.org/10.1038/nbt.3988). *Nature Biotechnology* 35:1026–1028. MMseqs2 [current upstream license](https://github.com/soedinglab/MMseqs2/blob/master/LICENSE.md).
- Hyatt D, et al. 2010. [Prodigal: prokaryotic gene recognition and translation initiation site identification](https://doi.org/10.1186/1471-2105-11-119). *BMC Bioinformatics* 11:119. Upstream [version and platform README](https://github.com/hyattpd/Prodigal/blob/GoogleImport/README.md) and [GPL-3.0 repository](https://github.com/hyattpd/Prodigal).
- Pfam [documentation and license](https://pfam-docs.readthedocs.io/en/latest/index.html). Pfam documentation identifies CC0 for Pfam; no Pfam data were acquired.

These references support method descriptions and software/data-term checks only. They do not validate the synthetic thresholds, select a biological panel, establish discovery performance, or support any biological classification.

M9 empirical method validation: READY FOR REVIEW