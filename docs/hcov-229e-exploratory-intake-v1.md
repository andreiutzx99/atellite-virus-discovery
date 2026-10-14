# HCoV-229E exploratory intake v1

**Status: INACTIVE — NOT APPROVED.** This is a non-authorizing, offline review pathway for exactly one proposed technical pilot: SRR12424250.

## Scope and policy boundary

The additional policy identifier is `public-virus-exploratory-229e-gse155986-v1`. It is not a replacement for `public-virus-v1` and applies only to:

| Field | Required value |
|---|---|
| Virus | HCoV-229E |
| GEO / BioProject / SRA study | GSE155986 / PRJNA656274 / SRP276927 |
| Run / Experiment / BioSample / GEO sample | SRR12424250 / SRX8920123 / SAMN15776099 / GSM4718636 |
| Reported exposure | HCoV-229E, 24 hours |
| Library / limit | single-end RNA-seq; at most 1,000,000,000 compressed bytes |
| Complete FASTQ manifest SHA256 | `8af1155a0ff3d65d2d32bb62560b2db37c22fb5f37c6b38a684a72747e4e9fe0` |

No other run, including the other 11 reported exposure samples and the three unresolved 0-hour samples, can pass this rule. The 0-hour entries are not treated as controls. Current strict identity remains `HELD`; an exploratory result never changes eligibility or claims archive-declared or sequence-confirmed virus identity.

## Checks and evidence

The evaluator is an offline function over supplied documents. It:

1. Verifies local record and source-snapshot consistency with the existing public-virus verifier; requires archive-client retrieval metadata with no archive errors and all read/QC flags false.
2. Recomputes the strict `public-virus-v1` identity result and requires the existing insufficient-identity hold to remain present.
3. Reuses the existing metadata technical-suitability assessment and FASTQ parser, and requires Illumina, transcriptomic RNA-Seq, cDNA selection, single-end layout, a complete one-file manifest, the 1 GB cap, and the pinned canonical manifest SHA256.
4. Evaluates sample-level treatment and explicit run→experiment→BioSample→GEO relationships with the existing exposure-evidence validator. It requires current, non-conflicted metadata; valid archive references; and the primary publication.
5. Binds the pending scientific approval template to the canonical policy JSON digest, canonical evidence-document digest, and FASTQ manifest digest.

Evidence and approval examples are in `hcov-229e-exploratory-intake-evidence-v1.json` and `hcov-229e-exploratory-scientific-approval-v1.json`. The status is `NOT_APPROVED`; no person, approval rationale, date, or signature is supplied. A JSON claim of `APPROVED` or `REJECTED` is blocked because this offline pathway cannot authenticate an approver.

Possible results are `candidate_for_scientific_review`, `held_pending_approval`, or `blocked`. A candidate result means only that the exact inputs satisfy the evidence checks and may be considered by humans. It is not eligibility, authorization, biological validation, or permission to acquire reads. Every result explicitly retains the original strict-policy identity and HELD state, separate exploratory evidence status, approval status, sequence-confirmation status, exact scope, and reasons.

## Approval and acquisition

The machine-readable approval record has separate owner and independent-reviewer decision fields, identifiers, rationale, date, policy/evidence/manifest digests, purpose, and unresolved limitations. Both decisions currently remain `NOT_RECORDED`, with overall status `NOT_APPROVED`. This pathway does not trust editable JSON as an authorization source.

Acquisition remains disabled. No environment variable, command-line option, callback, fixture, or hardcoded approval in this module can activate the existing downloader. The active acquisition API remains unchanged and fail-closed. No FASTQ was downloaded; no QC, alignment, assembly, or discovery processing was run.

## Failure conditions and limitations

Wrong or missing accession relationships, wrong study/BioProject/run scope, wrong virus or treatment, unresolved/changed/withdrawn metadata, missing or conflicting source evidence, incomplete or changed FASTQ manifests, a digest mismatch, a file over the cap, an unsuitable library, a changed strict-policy result, or any approval/authorization claim fails closed.

SHA256 values bind local document bytes or canonical representations; they do not authenticate the originating archive, prove source freshness, or establish who reviewed a record. Source URLs and retrieval dates remain recorded evidence, not signed attestations. Reported infection exposure is not viral sequence confirmation. The paper's qPCR time course does not predict viral-read yield in this run. Biological independence, library enrichment chemistry, read quality, and viral content remain unverified.

## Future PR #67 integration contract

PR #67 must remain separate and must not activate this pathway by consuming a local JSON approval alone. It should:

1. Define a trusted, auditable mechanism for recording the owner's and independent reviewer's decisions; require both decisions to approve the exact run, policy version/digest, evidence digest, and FASTQ manifest digest.
2. Re-fetch archive metadata and repeat exact run/experiment/BioSample/study/BioProject relationships, sample treatment, conflict/withdrawal checks, strict identity assessment, technical suitability, complete manifest, digest, and 1 GB checks immediately before any review decision is consumed.
3. Preserve the original strict identity result as `HELD`; report study exposure separately; never infer sequence-confirmed presence.
4. Keep this exception restricted to SRR12424250, leave other datasets on strict `public-virus-v1`, and preserve the existing production acquisition API's fail-closed behavior.
5. Require a separate explicit operator authorization and fresh acquisition preflight. Any authorization feature needs its own review and must not be bundled into this inactive intake change.

Do not expand virus or dataset scope or create a general policy framework.
