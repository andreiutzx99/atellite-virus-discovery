# M21 Phase 7 closure readiness

**Decision: `INCOMPLETE`.** The closure verification framework and synthetic
adversarial tests are not substitutes for independently authenticated evidence.
No real reviewer signatures, external checkpoint package, or live closure
package has been supplied.

| Requirement | Current state | Remaining evidence |
|---|---|---|
| Successful 27-case CI acceptance | Implemented; CI output is run-bound | Retrieve results, run statement and bundle for the exact closure revision |
| GitHub attestation | Offline bundle verification implemented with `gh attestation verify` | Execute against the retained bundle in a trusted environment |
| Independent reviewer approval | Ed25519 validation, expiry, scope and revocation checks implemented | Two real, distinct trusted reviewers must sign the exact package and evidence digests |
| Independent checkpoint custody | Signed receipt and audit-chain continuity verifier implemented | Obtain the package from an independently controlled source with a trusted custodian key |
| Canonical closure package | Content-addressed package contract and schema added | Assemble from verified component outputs and validate the real evidence |
| Operational closure | Not established | Keep `INCOMPLETE` until all evidence above verifies independently |

Synthetic test keys prove only that the code rejects and accepts the intended
shapes under test. They do not establish reviewer identity, external retention,
trusted timestamps, scientific validity or biological readiness.

The fixed state remains **`BLOCKED_FOR_BENCHMARK_EXECUTION`** and
`biological_execution_authorized` remains `false`, regardless of the closure
decision.

## Phase 8 prerequisites

Before considering Phase 8, independently provision reviewer and custodian
trust roots, retrieve and verify the real CI attestation and checkpoint history,
obtain unexpired reviewer approvals for the exact software revision, and record
the limitations and expiry conditions. Any separate biological execution
decision requires its own authorization and data-access review.
