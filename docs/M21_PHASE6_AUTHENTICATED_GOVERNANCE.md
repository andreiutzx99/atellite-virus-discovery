# M21 Phase 6 — authenticated synthetic benchmark governance

Phase 6 adds a synthetic-only evaluation boundary around the Phase 4 Ed25519
trust store, Phase 5 eligibility rules, reference-exclusion verifier, and
deterministic scoring policy. It does not authorize a biological benchmark.

## Approval and evidence flow

1. `verify_signed_control_qualification` verifies the Phase 4 record, exact
   qualification/evidence digests, two distinct reviewers, role/scope, key
   identity, validity, revocation, and approval-ID uniqueness. It derives the
   Phase 5 reviewer and eligibility fields instead of trusting caller-supplied
   `independently_reviewed` metadata. Eligible positives require independently
   reviewed HIGH or MODERATE evidence; eligible screen negatives require
   ADEQUATE sensitivity. Conflicting Phase 4 and Phase 5 classifications fail
   before normalized scoring records are constructed. Phase 5 validation
   remains an additional defensive check. Pending and unevaluable controls
   remain excluded.
2. `verify_reference_governance` independently checks reference bytes and the
   signed panel snapshot, recomputes the exact exclusion-policy digest, checks
   the actual exclusion result, binds policy and panel evidence, and verifies
   separate exclusion-policy and scientific-review signatures. The review
   binds exact thresholds, policy version, panel digest, evidence, expiry, and
   limitations. A signature authenticates a decision; it does not prove
   scientific appropriateness.
3. `evaluate_synthetic_bundle` is the evaluation-only entry point. It receives
   the complete reference evidence and recomputes its verification, rechecks
   signed control qualifications, verifies the blinded analysis digest, and
   derives the scoring-policy digest. It verifies two independent unblinding
   signatures bound to those exact digests before it opens the truth-bundle
   path. The context also binds the panel-manifest digest, exclusion-policy
   digest, recomputed exclusion-evidence digest, signed scientific-review
   digest, and exact authenticated approval-set digests for both scientific
   review and reference policy. Replacing an approval set changes the context;
   expired or modified approvals fail verification. The truth bytes must then
   match the approved digest and analysis.
4. Only after these checks does the entry point call the existing Phase 5
   scorer. Existing Phase 5 definitions, denominator rules, and truth/control
   consistency checks remain authoritative.

All approval signatures reuse Phase 4's canonical Ed25519 payload and
`_check_approval` verifier. The Phase 6 trust-store loader only extends the
permitted scope vocabulary; Phase 4's default scopes are unchanged. Tests
generate temporary synthetic keys and never persist or use production keys.

## Audit custody and states

Audit events are canonical JSON hash-chain records with a previous-event
digest. Verification rejects altered, removed, reordered, duplicated, or
malformed events. Appending validates the existing prefix first. A checkpoint
can be verified only when its count and head match and its signature is valid
under the custody-checkpoint scope. Without such a checkpoint the chain is
explicitly `UNANCHORED`.

A local hash chain cannot prevent deletion of the entire log, rollback to an
older copy, or replacement by a newly generated valid chain. Phase 6 does not
claim operationally secure custody unless an independently retained signed
checkpoint is available and verified. No trusted external anchor is configured
by this change.

Permitted stages are:

`PREPARED → QUALIFIED → REFERENCE_APPROVED → BLINDED_ANALYSIS_VERIFIED → UNBLINDING_AUTHORISED → SYNTHETIC_SCORING_COMPLETE`

`verify_governance_transitions` validates a complete chain of signed receipts.
Each receipt binds its current and requested states, target-specific evidence
category, verified artifact digests, passing verification result, and previous
transition digest; two trusted transition reviewers authenticate it. Receipts
cannot be replayed or reordered. The older `advance_governance_state` function
is a non-authoritative sequence helper only; a plain `PASS` argument never
authorizes progress. The state machine has no biological-execution state.
Regardless of synthetic results, the reported overall state remains
`BLOCKED_FOR_BENCHMARK_EXECUTION`.

## Readiness categories

Reports keep cryptographic approval, control qualification, reference
integrity, scientific-review evidence, blinding integrity, unblinding,
audit-chain verification, and synthetic scoring eligibility separate.
Software correctness is not scientific validity; neither constitutes dataset
qualification or biological authorization.

The initial readiness report is
[M21 Phase 6 governance readiness](M21_PHASE6_GOVERNANCE_READINESS.md).
Schemas for signed qualifications, scientific review, unblinding context,
authenticated transition receipts, audit events, and readiness reports ship
with the Python package.

## Scope and limitations

All implementation and tests use synthetic fixtures. This change does not
retrieve data, search biological databases, run M4–M15, alter Px31, create
production credentials or truth keys, or authorize biological execution.
The reference-exclusion handoff currently accepts one signed FASTA artifact
per exclusion result. Scientific review still depends on qualified human
assessment of the exact policy and its limitations. Operational custody needs
an external retained anchor not supplied here.

Run focused and regression tests with:

```sh
python -m unittest tests.test_m21_phase6_governance
python -m unittest tests.test_m21_benchmark_readiness tests.test_m21_phase5
```
