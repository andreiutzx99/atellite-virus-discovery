# M13 DVG-versus-satellite differential evidence: design research

**Status: research and architecture proposal only.** M13 is planned, not an
implemented production stage. The current [roadmap](../ROADMAP.md) assigns M13
the DVG-versus-satellite differential; historical documents using different
milestone numbers do not supersede it. No candidate, private dataset, or
biological reference sequence was searched.

This report distinguishes **LITERATURE/EMPIRICAL SUPPORT**,
**PROJECT DESIGN PROPOSAL**, and **UNRESOLVED DECISION**.

## 1. Baseline and method scope

### LITERATURE/EMPIRICAL SUPPORT — existing project behavior

M5 implements optional, caller-specific ViReMa junction parsing with completion
and read-accounting checks. `NO_DVG_EVIDENCE_DETECTED` is scoped to a completed,
accounted run under that caller/configuration; it is not a non-DVG result
([M5 contract](../M5_DVG_EVIDENCE.md)). M6 adds reference-scoped read
accounting and optional reconstruction; M7 reports exact recurrence among
eligible supported contigs. Neither is a biological differential classifier.

DVG detection methods identify candidate non-standard viral genome junctions
from reads mapped to declared viral references. Published methods include
ViReMa, DI-tector, and VODKA/VODKA2, with different algorithms, input
assumptions, and reported event conventions [1–4]. Event types include
deletion, copy-back and snap-back structures; a junction call or coverage
pattern alone does not establish a replicating defective interfering genome.
“Defective” and “interfering” are not interchangeable: interference is a
biological effect that requires evidence beyond a computationally observed
junction.

### PROJECT DESIGN PROPOSAL

M13 should compare hypotheses rather than issue a binary `DVG = false` /
`satellite = true` decision. Keep at least these alternatives visible:

- DVG/DI or other helper-derived rearrangement;
- satellite or other subviral element;
- ordinary full-length/fragmented viral genome;
- host, microbial, mobile-element, vector or reagent source;
- mixed infection, cross-sample carryover, read chimera, amplification or
  assembly artifact;
- unresolved or insufficiently assessed.

A completed M5 zero-event outcome remains one caller-scoped observation. It
cannot be promoted into evidence for a satellite, and a DVG-like junction does
not exclude other roles without additional evidence.

## 2. Evidence matrix and ownership boundaries

The differential dossier should link, not rewrite:

| Evidence input | M13 use | Boundary |
| --- | --- | --- |
| M5 caller run/event/accounting | Preserve exact caller-specific event coordinates, run status, read denominators and settings. | Do not rerun or generalize the caller unless a separate approved branch requires it. A zero-event result is not a biological negative. |
| M6 reconstruction/read-back | Link candidate identity, read accounting, contig evidence and reuse of source reads. | Read-back of assembly-eligible reads is not independent validation. |
| M7 recurrence | Report exact recurrence and declared observation metadata as its own dimension. | It does not establish biological independence, DVG/satellite identity, or sample metadata truth. |
| M8/M9 | Use nucleotide/protein similarity, roles, intervals and protein hypotheses as context. | Similarity and no-hit are method/reference scoped, not source or class verdicts. |
| M10/M11 | Use architecture, boundary and RNA model predictions where available. | Repeat, topology-compatible, fold, or motif evidence is not function or class. |
| M12 | Link read-origin, control, batch and artifact observations. | A technical alternative is not automatic rejection; missing controls are not clean results. |
| Curated comparators | Compare only with versioned, provenance-bearing examples and explicit curation confidence. | Reference labels are not automatically ground truth; holdout examples must not leak into method/threshold design. |
| Helper-derived sequence relationship | Link candidate/helper alignment intervals, role declarations and competing reference placements from M8 or an approved comparison. | Homology can motivate a helper-derived hypothesis; it does not prove the source molecule or helper dependence. |
| Breakpoint/junction evidence | Preserve breakpoint coordinates, orientation, event structure, supporting fragments, local sequence context and alternatives. | A breakpoint signature is caller- and reference-scoped; chimeras, mapping ambiguity and assembly errors remain alternatives. |
| Coverage signature | Link per-base depth, breadth, termini, discontinuities and candidate/helper genome intervals where the underlying reads and reference are available. | Coverage depends on library, mapping, amplification and reference choice; it is not a DVG/satellite verdict. |

For each hypothesis, retain evidence supporting it, evidence conflicting with
it, completed scoped no-signal results, unassessed dimensions, execution
failures, truncation, and evidence shared with other hypotheses. Preserve
coordinates and identities linking read junctions to candidate sequence and
reference records. No uncalibrated total score or winner is proposed.

## 3. Methods, tools, and resource constraints

### LITERATURE/EMPIRICAL SUPPORT

The published ViReMa paper describes virus recombination mapping from
next-generation sequencing data [1]. DI-tector presents a junction-detection
approach for defective interfering viral genomes [2]. VODKA2 addresses
non-standard viral genomes in large RNA-seq data sets [3]. Their papers support
their own method descriptions, not project-specific sensitivity/specificity or
universal DVG detection.

DVGfinder is a published metasearch wrapper around ViReMa-a and DI-tector, so
its output must not be counted as a third independent caller vote [4]. It may
be useful as an integration comparator, but its additional dependencies and
their versions need separate review. VODKA2 is the updated VODKA method line;
the VODKA/VODKA2 focus and event coverage are not automatically interchangeable
with callers aimed at different DVG structures.

### PROJECT DESIGN PROPOSAL

Keep the existing M5 ViReMa path as the default imported evidence, not a
mandatory M13 dependency. DI-tector and VODKA/VODKA2 may be evaluated later as
separately named comparators on authorized synthetic and curated datasets.
Preserve raw outputs, exact tool and aligner identity, input/reference hashes,
parameters, read accounting, and parser version. Never merge event sets into a
single caller-independent “DVG call” without explicit event identity,
coordinate-normalization, and agreement/disagreement accounting.

Tool licensing and maintenance are a provisioning gate. The current project
documents ViReMa as an external dependency and does not bundle it. This review
did not find repository-root `LICENSE` files in the public top-level listings
reviewed for DVGfinder or VODKA2, and did not establish redistribution terms for
DI-tector. DVGfinder's paper is open access under CC BY 4.0, but the paper
license does not establish a software license for its repository. Their
publication and source repositories are not, by themselves, a license grant.
Do not bundle/install them until repository license files, transitive
dependencies, platform support, maintenance, and terms for any reference data
are checked. Do not download or build any biological database as part of this
research.

Evidence can be computed only when the required reads, reference identity,
caller output, and source provenance are authorized and available. Sequence
alone can support comparative architecture/homology observations, but not
per-read breakpoint support. A missing read set or unsupported caller is
`NOT_ASSESSED`/unavailable, not a no-DVG result.

## 4. Validation, claims, and unresolved decisions

**Software validation:** synthetic known junctions for deletion, copy-back and
snap-back patterns; forward/reverse orientation; indel/error and low-complexity
challenge reads; mapping ambiguity; multiple events; duplicate/chimeric reads;
reference mismatch; caller-output parsing; complete versus incomplete accounting;
and independent recomputation of coordinates/counts.

**Biological validation:** independently curated, class-stratified examples
with source evidence and family/study holdouts are needed to estimate detection
behavior. Include ordinary viral fragments, full genomes, known DVGs, putative
satellites, mobile/host alternatives, and technical decoys. Current project
performance is unknown.

**Experimental confirmation:** demonstrating interference requires measuring
an effect on helper/parent-virus replication or infection under suitable
controls, not just detecting a defective genome. Demonstrating satellite
dependence requires an appropriate helper perturbation/complementation or
equivalent biological design. Neither claim is established by M13.

Unresolved contract choices include event-identity rules across callers,
reference eligibility and completeness, minimum read/metadata prerequisites,
supported DVG structure classes, handling of segmented/ambiguous references,
and which differential statements are allowed without curated comparators.
These require method-owner and biological review.

### UNRESOLVED DECISIONS

No caller-combination policy, event threshold, helper-derived source rule,
coverage criterion, or DVG-versus-satellite decision rule is approved. Decide
whether M13 remains a linked evidence matrix or later adds a validated
prioritization interface; any such prioritization remains distinct from
classification.

An M13 cache identity should bind candidate/source read inputs, exact M5/M6
records actually consumed, selected caller outputs and versions, declared
reference snapshots, event-normalization semantics, configuration, parser,
schema and output integrity. New M13 semantics should not invalidate unchanged
M5/M6 results; shared validator/cache changes follow the
[stage identity policy](../PRE_M9_STAGE_IDENTITY_AUDIT.md).

## 5. Sources checked

1. Routh A, Johnson JE. “Discovery of functional genomic motifs in viruses with
   ViReMa—a Virus Recombination Mapper—for analysis of next-generation
   sequencing data.” *Nucleic Acids Research* 42 (2014): e11.
   [doi:10.1093/nar/gkt916](https://doi.org/10.1093/nar/gkt916).
2. Beauclair G, et al. “DI-tector: defective interfering viral genomes’ detector
   for next-generation sequencing data.” *RNA* 24 (2018): 1285–1296.
   [doi:10.1261/rna.066910.118](https://doi.org/10.1261/rna.066910.118).
3. Achouri E, et al. “VODKA2: a fast and accurate method to detect non-standard
   viral genomes from large RNA-seq data sets.” *RNA* 30 (2024): 16–25.
   [doi:10.1261/rna.079747.123](https://doi.org/10.1261/rna.079747.123).
4. Olmo-Uceda MJ, et al. “DVGfinder: A Metasearch Tool for Identifying Defective
   Viral Genomes in RNA-Seq Data.” *Viruses* 14 (2022): 1114.
   [doi:10.3390/v14051114](https://doi.org/10.3390/v14051114).
   The article is CC BY 4.0; the repository top-level listing reviewed here
   contained no `LICENSE` file, so software reuse terms remain unresolved.
5. [VODKA2 source repository](https://github.com/lopezlab-washu/VODKA2) and
   [DVGfinder source repository](https://github.com/MJmaolu/DVGfinder); top-level
   repository license files were not observed in this review.
6. [DI-tector publication record](https://pmc.ncbi.nlm.nih.gov/articles/PMC6140465/);
   its software redistribution terms were not established here.
7. [M5 caller-specific DVG evidence](../M5_DVG_EVIDENCE.md) and
   [current M13 roadmap scope](../ROADMAP.md).

M13 remains planned. DVG and satellite/subviral explanations remain open when
evidence is incomplete, conflicting, or compatible with more than one cause.
