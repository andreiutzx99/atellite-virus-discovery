# Unified review interface

Double-click **Run-reviews.cmd** in this checkout. Choose one of the numbered stages, enter the requested file paths, and select a new output folder. Completed outputs can be verified and reused by selecting the same stage, inputs and output folder. The menu returns after each operation; `0` exits.

The launcher calls existing library-review, observational-report and sequence-inventory modules directly. It does not recreate those stages or automatically run earlier analysis. Added options are supplied alignment coverage, descriptive contamination evidence, cross-import catalogue linking and a dashboard of existing reports. No stage starts a download, mapping or assembly job.

The dashboard examines manifests in the selected folder and its immediate child folders, with a 2,000-folder limit. Reported completion is explicitly distinguished from verified integrity. Its dependency check searches PATH only; portable tools may exist elsewhere. Links open existing reports. It does not execute commands saved in manifests.

## Supplied alignment coverage

Inputs are three CSV files:

| File | Required columns |
|---|---|
| Reference lengths | reference_id, length |
| Assessed sample panel | sample_id |
| Alignment blocks | sample_id, reference_id, alignment_id, start, end |

Coordinates are **zero-based, half-open**: start 0, end 5 covers five reference positions. Provide aligned blocks, excluding gaps, rather than the outer span of a gapped alignment. Multiple overlapping blocks sharing one alignment ID within a sample/reference are unioned. Different alignment IDs contribute independently. Counts are alignment counts, not unique molecules or paired-end fragments.

Every sample/reference combination in the supplied panel is treated as assessed. A missing block produces zero coverage, so do not include an unassessed sample/reference combination. Separate jobs are needed for different assessed panels. Input quality/secondary-alignment/duplicate policies must be resolved upstream. Menu option 4 imports tables. Option 8 additionally imports bounded plain-text SAM, as described below.

Outputs include covered bases, breadth fraction, mean block depth, depth standard deviation and maximum depth. Zero-depth reference positions are included. Reference lengths do not determine memory allocation; the calculation uses interval endpoints rather than one array per base.

The artificial example under `examples/reviews/` has two alignments covering eight of ten positions, mean depth 1, maximum depth 2 and standard deviation sqrt(0.4). The second declared sample has zero coverage.

## Plain-text SAM coverage

Menu option 8 reads an existing uncompressed SAM file. It requires reference lengths in `@SQ` headers and converts 1-based SAM positions into the same half-open block representation. M, = and X contribute coverage; D and N advance the reference without adding coverage; clipping and insertions do not cover reference positions. Invalid coordinates, lengths, CIGAR clipping positions and duplicate reference headers are rejected. The parser is intentionally not a complete SAM validator.

Unmapped, secondary, supplementary, QC-failed and duplicate-flagged records are excluded, with counts in the report. Mates contribute separately, and no MAPQ cutoff is applied. Thus reported depth is descriptive alignment depth, not a calibrated measure of reliable biological support. `sam_sample` labels one input file, not an independently verified biological sample.

Limits are 256 MB, two million text lines and 200,000 aligned blocks. BAM, CRAM and compressed SAM are unsupported. This adapter does not launch mapping or extract/reconstruct sequences. Coordinate and CIGAR conventions follow the [SAM specification](https://samtools.github.io/hts-specs/SAMv1.pdf).

## Descriptive contamination evidence

Inputs:

| File | Required columns |
|---|---|
| Feature lengths | feature_id, length |
| Supplied matches | feature_id, reference_id, reference_role, query_start, query_end, percent_identity, reference_source, reference_version |
| Technical controls | sample_id, feature_id, detection |

Match coordinates also use zero-based, half-open intervals. Reference roles are `host`, `microbial`, `vector`, `adapter`, `technical_reference` or `known_virus`. Reference source/version are mandatory provenance labels, not verified source authenticity. Control detection is `present`, `absent` or `unknown`. The control file must contain technical controls; biological condition comparisons use the completed observation-report module instead.

Coverage is the union of supplied matches within a reference role. Several partial matches can contribute; this does not establish one complete matching reference. Reports preserve the reference IDs/source versions and maximum reported identity. Missing matches or controls produce **insufficient evidence**, never a clean result. Technical-control detections flag review without declaring contamination mechanism, index hopping, probability or automatic rejection. No sequences are discarded.

## Cross-import catalogue linking

Provide an imports CSV containing `catalogue_dir,sample_id,study_id,condition,sample_type,library_molecule`. The final five fields use the existing observation-report schema. Catalogue paths may be absolute or relative to the imports CSV. Each directory must be a completed sequence-inventory snapshot with its manifest and all five exported artifacts.

The linker verifies every artifact against its manifest, reads the SQLite catalogue in read-only mode, rechecks sequence hashes and links exact normalized sequences. It preserves each original record's import ID, sample, input FASTA hash and catalogue manifest hash. Input file hashes detect copied exports assigned to different samples; they cannot prove biological independence or catch every mislabeled duplicate. Metadata conflicts for one sample are rejected. Duplicate imports of the same directory are rejected.

Repeated records/imports from one biological sample contribute only one presence observation per exact sequence. Missing sequences remain **unknown**, never negative. No similarity clustering or consensus is performed. Outputs include a linked SQLite database, provenance CSV, sample CSV and positive-observation CSV. The latter two can be passed directly to the already implemented observation-report module. No FASTA or catalogue input is changed.

Limits: 100 imports, 100,000 linked source records, 40 million distinct sequence bases, and 100,000 sample/sequence comparison cells. Input tables are capped at 64 MB and 200,000 rows.

## Recovery and resource failures

New stages share a manifest lifecycle. It records input hashes, implementation hashes, source paths, Python version, timestamps and output hashes. Changed inputs or stage code require a new output directory. Completed results are reused only after all registered artifact hashes match. Ordinary failures record `failed`; repeating the same job rebuilds only that small review stage. SQLite replacement is atomic, preventing appended duplicate imports after an interrupted attempt.

An exclusive `.review.lock` prevents concurrent writers. After a forced termination, confirm that no review process is active before removing only that lock and resuming. Stale locks are not automatically removed. Existing folders without a matching manifest are refused. Failed jobs, invalid coordinates, malformed metadata, disk-write failures and altered outputs must never be represented as successful empty results.

## Remaining unsupported work

BAM/CRAM or compressed-SAM import, automatic reference searches, approximate clustering, ORF reporting and functional inference are not implemented by these review tools. The existing assembly/mapping runtime prototypes remain separate. The new infrastructure operates on supplied evidence, not an end-to-end biological discovery workflow.
