# Public-virus experimental-exposure evidence policy proposal v1

**Proposal status:** Proposed; not approved, not active, and non-authorizing.  
**Curation date:** 2026-10-14.  
**Case study:** GSE155986, using the accession-level record reviewed in PR #63.  
**Acquisition:** Disabled. No reads were downloaded or inspected; no QC, assembly, sequence confirmation, or discovery was performed.

## Executive summary

The current `public-virus-v1` gate answers whether an exact archive sample declares a viral identity in an accepted sample-level identity field. It does not encode what a publication and accession-linked treatment annotation report that researchers did to a sample. Those are different questions. Sequence-confirmed viral presence is a third, separate question that requires examination of sequence data.

This proposal defines a separate, versioned evidence vocabulary named `study_reported_experimental_exposure`. It can describe a documented, accession-linked experimental treatment without treating that report as archive identity, infection confirmation, or acquisition eligibility. The proposal includes a deterministic, local-only shadow evaluator and the 15 records already reviewed for GSE155986.

**Nothing in this PR changes or activates the identity gate, eligibility, acquisition preflight, or acquisition safeguards.** The proposed vocabulary can be adopted as descriptive evidence independently from any future decision to alter eligibility. Any eligibility use would require a separately approved policy version and independent scientific review.

## Existing contract and evidence distinctions

The existing intake in `satellite_discovery.public_virus.py` accepts virus evidence from the sample organism or the exact typed fields `virus`, `virus species`, `infecting virus`, `viral species`, and `pathogen`. A positive result means accepted for technical review, not biological confirmation. Human host taxonomy, study titles, GEO treatment labels, and publication context are not substitutes. The policy remains `public-virus-v1`; its 1,000,000,000-byte complete-run limit is unchanged.

| Evidence concept | Question it answers | Meaning in this proposal |
|---|---|---|
| A. Archive-declared viral identity | Does the exact archive sample declare the virus in a current accepted identity field? | Evaluated by the existing policy only; HCoV-229E records in this case remain `INSUFFICIENT`. |
| B. Study-reported experimental exposure | Do sample-linked source records report a specific treatment involving the virus? | A proposed evidence category based on accession links, sample condition, source support, and review. It is not detection. |
| C. Sequence-confirmed viral presence | Has sequence from that exact sample been examined and shown to contain the virus? | `NOT_ASSESSED` for every case-study record. Metadata does not establish it. |

Category B may be `SUPPORTED` while A is `INSUFFICIENT` and C is `NOT_ASSESSED`. The proposed category reports the study's account of its treatment; it does not assert that infection succeeded, that reads contain virus, or that the sample is uncontaminated.

## Proposed category and evidence contract

Category name: `study_reported_experimental_exposure`; schema: `study-reported-experimental-exposure-evidence-v1`, version 1.

Every candidate record must retain:

1. Exact run, experiment, BioSample, and GEO sample accessions.
2. Explicit, individually checked relationships between run–experiment, experiment–BioSample, and BioSample–GEO sample, each with source references. Missing or mismatched edges fail closed.
3. A sample-level treatment annotation, the reported virus, the normalized condition, and timepoint. A general study-level virus statement is supporting context only.
4. A primary publication or protocol locator, exact source URLs/identifiers, retrieval date, and the source fields used.
5. A conflict assessment and metadata freshness state. Changed or withdrawn metadata requires re-review; source digests, if kept, establish local byte integrity only and do not prove scientific truth.
6. A separate biological-independence assessment, including its evidence basis. Accession counts and `R1`–`R3` labels alone remain `UNKNOWN`.
7. A reviewer decision status. The record must not imply that an entered reviewer name is authenticated or that the proposal itself has received human approval.

Evidence strength uses `SUPPORTED`, `INSUFFICIENT`, `CONFLICTED`, and `NOT_ASSESSED`. Experimental condition uses a separate vocabulary: `REPORTED_INFECTED`, `REPORTED_MOCK`, `REPORTED_UNTREATED`, `UNRESOLVED_BASELINE`, `OTHER`, and `UNKNOWN`. An untreated record is not automatically a mock control. A zero-hour record with uncertain relation to inoculation remains `UNRESOLVED_BASELINE`.

`satellite_discovery.public_virus_exposure_proposal` is a pure offline shadow evaluator. It reads supplied JSON only, performs no network access, does not import the intake or acquisition modules, and has no CLI, environment switch, callback, or acquisition path. Missing mappings, absent sample-level treatment/source support, metadata changes, and conflicts cannot yield supported exposure. It always returns `sequence_confirmed_viral_presence: NOT_ASSESSED`, `current_eligibility: HELD`, `eligibility_effect: NONE`, `authorizing: false`, and `acquisition_enabled: false`. It is a deterministic validation aid, not an authentication service or an eligibility gate.

## Independent-review procedure

Before any future eligibility-policy decision:

1. Two scientific reviewers independently inspect every accession edge and the exact sample-level condition against GEO, SRA, BioSample, ENA, and a primary publication or protocol. Each records their own decision, evidence locators, rationale, and unresolved concerns.
2. The reviewers separately classify evidence strength, condition, timepoint, and biological independence. Study context cannot fill a missing sample-level link.
3. Agreement, disagreement, rejection, and not-yet-reviewed states are retained. Disagreement or contradictory sources keep the affected interpretation held for resolution; reviewers do not overwrite the original source statements.
4. Recheck source availability and content before a decision. Changed, corrected, or withdrawn records invalidate the prior interpretation and trigger re-review.
5. Preserve unresolved terms, especially inoculation timing, control status, and replicate independence. Never infer mock status from `Untreated`, or independence from replicate labels.
6. Record the outcome separately from acquisition authorization. A decision about reported exposure is not approval to download, analyze, or claim infection.

This framework requires no external identity-management service. It improves traceability but cannot authenticate reviewers; authentication and any actual eligibility change would need separate governance and policy work.

## GSE155986 case study

The machine-readable companion carries the 15 per-run accession mappings, evidence locators, source fields, treatment, timepoint, review status, current-policy comparison, FASTQ size/MD5 metadata, and evaluator inputs. The evidence source set is the metadata-only PR #63 review, dated 2026-10-14. The exact values below are not newly inferred by this proposal.

| Run | GEO sample | Treatment / time | Proposed condition | Reported exposure | Current identity / eligibility | Sequence presence | Independence |
|---|---|---|---|---|---|---|---|
| SRR12424243 | GSM4718629 | Untreated / 0 h | UNRESOLVED_BASELINE | INSUFFICIENT | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424244 | GSM4718630 | Untreated / 0 h | UNRESOLVED_BASELINE | INSUFFICIENT | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424245 | GSM4718631 | Untreated / 0 h | UNRESOLVED_BASELINE | INSUFFICIENT | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424246 | GSM4718632 | HCoV-229E / 6 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424247 | GSM4718633 | HCoV-229E / 6 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424248 | GSM4718634 | HCoV-229E / 6 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424249 | GSM4718635 | HCoV-229E / 24 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424250 | GSM4718636 | HCoV-229E / 24 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424251 | GSM4718637 | HCoV-229E / 24 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424252 | GSM4718638 | HCoV-229E / 48 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424253 | GSM4718639 | HCoV-229E / 48 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424254 | GSM4718640 | HCoV-229E / 48 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424255 | GSM4718641 | HCoV-229E / 72 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424256 | GSM4718642 | HCoV-229E / 72 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |
| SRR12424257 | GSM4718643 | HCoV-229E / 72 h | REPORTED_INFECTED | SUPPORTED | INSUFFICIENT / HELD | NOT_ASSESSED | UNKNOWN |

The 12 6–72-hour conditions are reported in accession-linked GEO/BioSample treatment fields and consistent with the described study time course. For the three 0-hour records, the archive says “Untreated,” while the paper describes collection at 0 hours post-infection. The available evidence does not establish whether inoculum had been applied before collection. Their reported condition is therefore unresolved baseline, not mock and not supported exposure.

**Case-study totals:** 15/15 relationships verified; 12 supported reported exposures; 3 unresolved untreated zero-hour baselines; 0 confirmed mock controls; 0 sequence-confirmed samples; biological independence unknown; 15/15 remain HELD. All complete per-run FASTQ manifests in PR #63 were within the existing 1,000,000,000-byte cap. Passing that metadata check does not authorize retrieval.

## Decision matrix: vocabulary versus eligibility

| Decision | Evidence vocabulary adoption | Eligibility-policy adoption |
|---|---|---|
| Purpose | Describe an accession-linked study-reported condition as a distinct evidence category. | Permit a new evidence class to affect a technical eligibility gate. |
| Approval in this PR | Proposed only; not approved or active. | Not proposed as an implementation; no gate behavior changes. |
| Minimum evidence | Exact accession chain, explicit sample treatment, virus/condition/time, traceable primary source, conflict/freshness review, independence status, review decision status. | All vocabulary evidence plus a formal policy version, explicit decision rules, risk review, two independent scientific reviews, and regression/safety validation. |
| What it can conclude | “This source reports that this exact sample received this treatment.” | Only what a separately approved future policy explicitly allows; never sequence presence by itself. |
| What it cannot conclude | Successful infection, viral reads, biological independence, contamination status, or acquisition permission. | Sequence confirmation or acquisition authorization without their separate required processes. |

### Proposed policy decision rules

- **Sufficiently documented:** exact verified accession chain; explicit sample-level treatment naming HCoV-229E; source locator in a primary paper/protocol; retrieval date/provenance; no unresolved contradiction; condition/timepoint retained; reviewer state recorded.
- **Supporting but insufficient alone:** study title, abstract-wide virus claim, host taxonomy, replicate labels, FASTQ sizes, and a local content hash.
- **Hold/conflict:** mismatched accession edge, different named virus, contradictory treatment sources, changed/withdrawn source, unresolved sample-condition contradiction, or inadequate source reference.
- **Controls and replication:** mock is reported only when explicitly annotated; untreated remains distinct; zero-hour inoculation timing remains unresolved when sources do not settle it. Independence is assessed per biological dimension and remains unknown without direct support.
- **Permitted conclusions:** source-reported experimental exposure and its evidence state, with uncertainty.
- **Prohibited conclusions:** confirmed infection, viral presence in reads, biological validation, sample purity, or eligibility from this category alone.
- **Future eligibility change:** requires a new policy version and independent review; the evidence vocabulary and eligibility policy are separate decisions.

## Negative and adversarial cases

The standalone tests cover these 16 cases. Tests use synthetic evidence except the explicitly identified GSE155986 case study; they do not assert that the adversarial scenarios occurred in the data.

| Case | Expected handling |
|---|---|
| Correct accession mapping and explicit infection label | `SUPPORTED` reported exposure; sequence status remains `NOT_ASSESSED`. |
| Correct mapping but missing treatment | `INSUFFICIENT`. |
| GEO/SRA relationship conflict | `INSUFFICIENT`; mapping failure cannot support exposure. |
| Different virus in treatment | `CONFLICTED`. |
| Study-level virus statement without sample-level treatment | `INSUFFICIENT`. |
| Human host organism without viral identity | Current identity remains `INSUFFICIENT`; host does not substitute. |
| Explicit mock-infected sample | Condition may be `REPORTED_MOCK`; it is not reported viral exposure. |
| Untreated baseline | `REPORTED_UNTREATED`; not converted to mock or infection. |
| Ambiguous zero-hour sample | `UNRESOLVED_BASELINE`; exposure remains `INSUFFICIENT`. |
| Duplicate runs from one biological sample | No independence is inferred; status remains `UNKNOWN` absent direct evidence. |
| Contradictory publication and archive annotations | `CONFLICTED`. |
| Changed or withdrawn metadata | `CONFLICTED` and requires reassessment. |
| Missing source references | `INSUFFICIENT`. |
| Missing/tentative reviewer records | Not upgraded to agreement; remains `NOT_REVIEWED`. |
| Claimed sequence confirmation without sequence evidence | Output stays `NOT_ASSESSED`. |
| Attempt to promote a HELD run to ELIGIBLE | Rejected as an eligibility effect; output remains HELD and non-authorizing. |

## Risks, limitations, and next steps

False classification can arise from stale or incorrect database relations, ambiguous treatment wording, copied or study-level labels, incomplete conflict review, or mistaken assumptions about independent biological units. The evaluator checks internal consistency of supplied evidence; it cannot verify that a cited website is authentic, current, or truthful. Source references and retrieval dates improve auditability but do not authenticate claims. No reviewer has approved this proposal, and JSON reviewer identifiers are not authentication.

Next steps are independent review of the evidence schema and GSE155986 classifications; source-by-source verification, including the unresolved zero-hour semantics; and review of the two distinct decisions (evidence vocabulary and any future eligibility change). Do not select a pilot or enable acquisition based on this proposal.

## Verification boundaries and sources

The JSON companion is versioned and explicitly non-authorizing. Its GSE155986 records carry the accession links, source references, retrieval date, treatments, statuses, FASTQ manifest metadata, and proposed review fields. SHA-256 values from the earlier review are not used as proof of scientific truth. Existing identity, provenance, acquisition-review, preflight, controlled-acquisition, 1 GB cap, and M1–M16 contracts are not changed.

Primary sources are listed in [`hcov-229e-identity-evidence-review-v1.md`](hcov-229e-identity-evidence-review-v1.md) and in the versioned JSON companion. The reported exposure at 6–72 hours is drawn from the sample-linked GEO/BioSample fields and paper Methods. No new read-level evidence exists.

---

**PUBLIC-VIRUS EXPOSURE POLICY PROPOSAL V1: READY FOR INDEPENDENT REVIEW**
