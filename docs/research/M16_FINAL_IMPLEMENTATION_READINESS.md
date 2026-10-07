# M16 final implementation-readiness audit

**Initial audit date:** 2026-10-05
**Post-prerequisite reconciliation:** 2026-10-05
**Current verdict:** **READY FOR IMPLEMENTATION** for the frozen synthetic harness and clarified M15 adapter profile.

> The detailed findings in §§3–9 below record the earlier pre-clarification, pre-PR-#51 assessment. Section 10 is the current post-merge disposition and supersedes any conflicting blocker status in those sections.

This narrow amendment changes M16 documentation only. It updates the frozen
contract and aligns this readiness report and the implementation plan. It does
not change M16 implementation, tests, CI, README, ROADMAP, or M1–M15 code.
No biological data, sequence, read, or external biological inference was used.

## 1. Authoritative baseline and milestone status

The authoritative post-merge state is live GitHub `main`, local `main`,
`origin/main`, and the clean validation worktree at commit
[`c620834c78c51b33989880ce78f5bcb36f0e9845`](https://github.com/andreiutzx99/atellite-virus-discovery/commit/c620834c78c51b33989880ce78f5bcb36f0e9845),
tree `b4ebcb31ca412ac01e1f3a54d700099f3e5c7eea`. This normal merge has parents
`06738d8ff91792f7e66acc13603353586e9748a1` and
`0d47016b1f13c0b66efa0e605d1a46011215ea49`; the latter was PR #51's reviewed
head. The active task workspace is a divergent feature branch and is not used
as implementation authority.

The [ROADMAP](../ROADMAP.md#L14-L36) marks M1–M15 implemented, within their
stated scopes, and M16 **PLANNED / NOT IMPLEMENTED**. Relevant first-parent
merges on authoritative `main` are:

| Change | Main merge | Audit significance |
| --- | --- | --- |
| M14 synthetic/offline implementation, PR [#45](https://github.com/andreiutzx99/atellite-virus-discovery/pull/45) | `0255359aac335a1224107d25e3d490212246277e` | M14 is a registered, typed producer. |
| Shared producer-execution references, PR [#48](https://github.com/andreiutzx99/atellite-virus-discovery/pull/48) | `07274f79668f2f3d974584451a493fff6046071f` | The shared verifier used by M15 is present. |
| M15 synthetic evidence dossier, PR [#46](https://github.com/andreiutzx99/atellite-virus-discovery/pull/46) | `94e70be946f011786baacd86f3624b69f3d383c0` | M15 contracts, producer, and workflow tests are present. |
| M15 implemented / M16 planned status, PR [#49](https://github.com/andreiutzx99/atellite-virus-discovery/pull/49) | `06738d8ff91792f7e66acc13603353586e9748a1` | Status before the cache prerequisite. |
| Cache/source-identity prerequisite, PR [#51](https://github.com/andreiutzx99/atellite-virus-discovery/pull/51) | `c620834c78c51b33989880ce78f5bcb36f0e9845` | Stage-owned identities and downstream-only registration isolation are merged. |

Post-merge focused and full offline validation passed: 650 tests passed, 16
skipped; compileall, `pip check`, `git diff --check`, wheel/resource checks,
and installed CLI smoke checks also passed. The authoritative tree contains no
M16 stage, production modules, artifact registrations, or M16 tests, consistent
with the frozen contract and roadmap status.

## 2. Source hierarchy

| Source | Weight in this audit |
| --- | --- |
| [M16 contract freeze](../M16_CONTRACT_FREEZE.md) | Normative for the generic synthetic mechanics, accepted target types, states, metric formulas, custody, deterministic serialization, and claim limits. It expressly excludes empirical evaluation and biological interpretation. |
| [M15 contract freeze](../M15_CONTRACT_FREEZE.md) | Normative for the actual M15 input/output schemas, states, dependency semantics, provenance, and cache identity. It fixes M15 as a descriptive dossier with no score, class, or winner. |
| [ROADMAP](../ROADMAP.md) and merged source/tests on `main` | Status and actual implementation evidence. Where they differ from pre-implementation documents, current `main` wins. |
| Existing M16 contract clarification (`docs/research/M16_CONTRACT_CLARIFICATION.md`, commit `e617d511716b0896daa33b17114449cfe4da316f` on local `feature/m14-offline-baseline`) | The document labels itself a normative M16 supplement and supplies the M15 target-reference, state-projection, and determinism profile used in §10. It is absent from authoritative commit `c620834`; this report does not claim it is in `main`. Its M15 field assumptions were checked against the merged `main` implementation, and it is used here because this reconciliation explicitly names the existing clarification. |
| M16 [implementation plan](M16_IMPLEMENTATION_EXECUTION_PLAN.md) and [pre-contract readiness](M16_PRECONTRACT_READINESS.md) | Planning only. The prior cache gate is satisfied; the real-M15 integration test is a mandatory implementation-acceptance gate. Neither document changes the frozen contract. |
| M16 [benchmark research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md); M12–M16 [cross-check](M12_M16_CONTRACT_CROSSCHECK.md), [decision register](M12_M16_DECISION_REGISTER.md), [fixture matrix](M12_M16_FIXTURE_MATRIX.md), [implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), [independent audit](M12_M16_INDEPENDENT_CONTRACT_AUDIT.md), [parallelization plan](M12_M16_PARALLELIZATION_PLAN.md), and [validation logistics](M12_M16_VALIDATION_LOGISTICS.md) | Historical/research proposals. They do not amend frozen contracts. Several retain earlier “planned” milestone-status snapshots; current ROADMAP and merged code supersede those status statements. |
| M15 [pre-contract readiness](M15_PRECONTRACT_READINESS.md), [implementation plan](M15_IMPLEMENTATION_EXECUTION_PLAN.md), and [evidence-integration research](M15_EVIDENCE_INTEGRATION_DESIGN_RESEARCH.md) | Historical planning/research from before the M15 merge. For example, their “M15 planned” statements are superseded by current `main`; use the M15 freeze and implementation instead. |
| [M16 cache-decoupling note](M16_REGISTRATION_CACHE_DECOUPLING.md) | Pre-merge implementation/validation snapshot. Its “not merged” status is historical and superseded by commit `c620834`; do not use it as current status. |

In particular, the M16 pre-contract proposal’s richer empirical truth tiers,
confidence/uncertainty fields, and claim-specific metrics are not part of the
frozen synthetic contract. Conversely, the frozen contract’s opaque
`expected_software_outcome` is not permission to infer a biological class.

## 3. M16 contract versus the merged M15 handoff

### What is present and compatible

The M16 freeze allows only `m12_result_bundle`, `m13_result_bundle`,
`m14_result_bundle`, and `m15_result_bundle` as targets; each target reference
must bind producer/stage, a run-manifest digest, artifact type/version, relative
path, output digest, and target implementation/configuration identity
([M16 §2](../M16_CONTRACT_FREEZE.md#2-runner-and-accepted-target-artifacts)).

The merged M15 stage produces the typed `m15_result_bundle` artifact. Its
content schema is `m15-result-bundle-v2`; its `semantic_version` is `"2"`.
The bundle records candidate ID, result completeness, semantic input-manifest
digest and digest kind, input/axis-mapping semantic versions, optional-stage
states, producer refs, dependency edges, consumed contract semantics,
implementation identity, hashes/paths for the other three M15 outputs, and
source-access provenance. The exact field allowlist is enforced by
[`validate_result_bundle`](../../satellite_discovery/m15_contracts.py#L610-L686).
The outer M1/M4 stage manifest and workflow row bind the result bundle’s own
digest and typed descriptor; the bundle does not self-hash.

M15 is descriptive only. It does not generate a candidate class, ranking,
priority, or prediction; it retains source records and their states. It accepts
M12–M14 as upstream input types, but it deliberately excludes M11 and its own
outputs. These boundaries are frozen in
[M15 §1–4](../M15_CONTRACT_FREEZE.md#1-scope-and-non-goals) and reflected by
the actual allowlist and output writer
([M15 contract code](../../satellite_discovery/m15_contracts.py#L13-L24),
[bundle writer](../../satellite_discovery/m15_stage.py#L1090-L1145)).

### Handoff mismatches recorded by the initial audit (superseded by §10)

1. **No frozen target-execution transform.** M16 defines `target_input_ref`,
   an adapter ID/version, and adapter-defined opaque expected outcomes, but it
   does not define how an M12–M15 result bundle produces one prediction for
   each fixture item. M15’s bundle has no per-fixture prediction/outcome field
   or callable predictor; it is a dossier of already-produced evidence.
   There is no frozen crosswalk from M15 `candidate_id`/`evidence_id` to M16
   `item_id`, nor a rule for deriving `EMITTED`, abstention, or an opaque
   outcome from the bundle. Re-running M15 per fixture or turning dossier
   fields into outcomes would add semantics not specified by either freeze.
   A mechanics-only adapter may generate opaque test outputs, but that does
   not establish that M16 evaluated M15. The M15-integration gate must either
   define a software-only adapter contract for this exact handoff or limit the
   test to provenance/consumption mechanics without claiming predictive
   evaluation.

2. **“Artifact semantic version” is ambiguous across the real M15 layers.**
   For an M15 target, the outer descriptor is `artifact-contract-v1` with
   `contract_version = "1"`; the M15 JSON document says
    `schema = "m15-result-bundle-v2"` and `semantic_version = "2"`; its
    `contract_semantics` records `m15_result_bundle` contract semantics `"2"`,
    shared validator semantics `"1"`, and contract schema version `"1"`. The
    stage manifest separately records stage version `"2"`; the bundle's
    implementation identity records output schema version
    `"m15-output-schema-v2"`. The M16 freeze’s single “artifact semantic
    version” field does not say which value it means or whether it must bind
    all of them. M15’s own input contract explicitly distinguishes descriptor
    `artifact_contract_version` from validator semantics
    ([M15 §3](../M15_CONTRACT_FREEZE.md#3-input-manifest); actual versions:
    [artifact contract constants](../../satellite_discovery/artifact_contracts.py#L19-L22),
    [M15 schema versions](../../satellite_discovery/m15_contracts.py#L18-L21),
    [contract semantic map](../../satellite_discovery/artifact_contracts.py#L123-L165),
    [stage version](../../satellite_discovery/m15_stage.py#L100-L101)).
    Freeze a mapping for M12–M15 rather than guessing from one field.

3. **“Run-manifest SHA-256” does not identify one current M1 digest.**
   M15 records `producer_run_manifest_sha256` on each consumed upstream ref;
   it is not a self-run digest for the M15 result bundle. Those source refs
   include caller-snapshot, external-manifest, and authenticated M1 forms. In
   an authenticated M1 ref, the field is the selected stage-manifest digest,
   while `producer-execution-ref-v1` separately carries the raw workflow-file
   SHA-256 and stage-manifest SHA-256. The verifier checks both layers and the
   workflow row’s stage-manifest digest
   ([producer reference schema](../../satellite_discovery/producer_provenance.py#L19-L34),
   [verification](../../satellite_discovery/producer_provenance.py#L256-L278),
   [M15 input-ref fixtures](../../tests/test_m15_workflow.py#L19-L61),
   [authenticated ref fixture](../../tests/test_m15_workflow.py#L97-L153)).
   M16 must state whether its target ref binds the M15 workflow snapshot,
   stage manifest, or both, and how these map to the single “run-manifest”
   label.

4. **Target implementation/configuration is split across artifacts.** The M15
   bundle’s `implementation` contains its stage implementation identity; its
   enclosing M1 stage manifest and workflow row carry the selected stage
   identity and execution record. M15 rejects non-empty configuration, but
   the M16 contract does not identify which outer or inner identity fields
   supply its exact target implementation/configuration identity. Bind the
   bundle’s implementation and the authenticated producer execution identity
   explicitly; do not reconstruct configuration identity from the bundle
   alone.

5. **A valid M15 bundle can still be partial.** M15 permits
   `COMPLETE_WITHIN_SUPPLIED_SCOPE`, `PARTIAL`, `NOT_EVALUATED`, and `INVALID`.
   It preserves unavailable, failed, incomplete, invalid-provenance, and
   caller-snapshot-unverified records; a completed M1 stage does not imply a
   complete or fully verified evidence dossier. M16 accepts the target type but
   does not specify target eligibility or map M15 `result_completeness` and
   per-source states to M16 item `execution_state`. Do not map M15 partial,
   unavailable, invalid, or no-observation states to an emitted negative.

The shared verifier is suitable for integrity and provenance-chain consistency:
it checks the selected workflow snapshot, completed stage, stage manifest,
typed descriptor, inventory, path containment, and exact file digests
([checks](../../satellite_discovery/producer_provenance.py#L327-L462)).
Its own module explicitly says this does **not** establish who created the
bundle or whether it is scientifically correct
([verifier boundary](../../satellite_discovery/producer_provenance.py#L1-L5)).
It is therefore not cryptographic signer authentication. A tampered artifact
under an unchanged manifest must fail; a wholly fabricated but internally
self-consistent workflow/inventory/artifact cannot be distinguished from a
trusted one without an external trust anchor, which the frozen contracts do
not define.

The existing test
[`test_result_bundle_supports_frozen_m16_target_handoff`](../../tests/test_m15_workflow.py#L452-L505)
executes M15 in the workflow runner and verifies its output with the shared
verifier. It does not run M16 or prove the full authenticated producer-to-M15-
to-M16 chain; its M15 input uses the caller-snapshot fixture. The integration
gate remains unmet.

## 4. Initial field-by-field input → transformation → output matrix

This pre-clarification matrix is retained as audit history. Section 10 records
the current M15-specific mappings and supersedes its “unresolved” statuses.

The transformations marked **frozen** below are stated by the M16 contract.
“Unresolved” means the implementation must not choose an interpretation on its
own.

| Input/source | Frozen validation and permitted values | Deterministic transformation / output | Missing or invalid behavior | Provenance and cache |
| --- | --- | --- | --- | --- |
| Public manifest: `schema`, `dataset_kind`, `fixture_set_id`, `sealed_key_commitment` | `m16-public-manifest-v1`; `SYNTHETIC_FIXTURE` only; `EMPIRICAL` is `OUT_OF_SCOPE`. The commitment is an opaque custodian-supplied identifier; M16 does not define its generation. | Validate before target execution; bind fixture-set identity and commitment into M16 result and target-execution identity. | Invalid manifest rejected before execution; empirical input rejected without retrieving payload. | Public-manifest digest and opaque commitment are required in target-execution identity. Raw-byte versus canonical semantic digest is not specified. |
| `target_ref` | Exactly one of the four frozen result-bundle types; producer/stage, run digest, artifact type/version, relative path, output digest, implementation/config identity required. | Authenticate and validate the exact target, then record target provenance on each prediction and in the result bundle. | Missing dependency maps to M1 `dependency_missing` or `external_module_required`; target identity mismatch/tampering blocks scoring with `INTEGRITY_FAILED`. Exact handling of a malformed target before execution is not fully stated. | **Unresolved:** the M1 digest/version/implementation mapping above and whether an M15 partial bundle is an eligible target. |
| `adapter_id`, `adapter_version` | Registered immutable adapter; version bound in identity. Adapter outcomes are opaque software-contract values, not biological labels. | Adapter executes only on public manifest, target artifact, and synthetic input fixtures; returns one prediction row per item. | Missing/unknown adapter must fail preflight; exact adapter-failure state mapping is not specified beyond the available execution states. | Adapter implementation/schema identity and its mapping from a result bundle to an item outcome are not defined by the freeze. |
| Public item: `item_id`, `target_input_ref` | Unique stable ID; input reference is hash-bound and synthetic. | Execute target path; exactly one sorted prediction row per public item, with target provenance and execution/outcome states. | Duplicate IDs or invalid refs rejected; a non-completed item keeps a null/unknown outcome and remains counted. | `item_id` is not defined as M15 `candidate_id` or `evidence_id`; no crosswalk or automatic candidate deduplication is frozen. |
| `group_ids`, `split_role` | Group IDs sorted; split role is `DEVELOPMENT`, `TUNING`, `SYNTHETIC_HOLDOUT`, or `UNASSIGNED`. | Group checks are deterministic; any shared non-empty group across roles gives `LEAKAGE_DETECTED` and blocks scoring. | Malformed group or invalid/duplicate item identity is rejected; leakage is not a negative prediction. | Bind group graph and split roles. Group membership tests leakage only; it does not establish biological relatedness. |
| `label_state`, `fixture_provenance` | Label state is `SEALED_SYNTHETIC_EXPECTATION`, `UNKNOWN`, or `NOT_APPLICABLE`; generated software fixture only. | Keep label accounting separate from prediction accounting. Unknown/N/A labels are separately counted and excluded from `n_labelled`. | Missing/invalid fixture provenance rejected; unknown/N/A are never imputed as negative. | Bind label-state summary and key commitment; public execution may receive the opaque commitment, but not key content, expected outcomes, or the sealed-key path. |
| Sealed key: `fixture_set_id`, `sealed_key_commitment`, `item_id`, `expected_software_outcome`, `label_scope` | Matching fixture set; the opaque custodian-supplied commitment must exactly match the public manifest value. M16 does not derive it from key contents; equality is not cryptographic verification. One outcome per labelled public item; `label_scope = SOFTWARE_CONTRACT`; outcome value is adapter-defined string/object. Unknown/N/A items have no expected outcome. | Open only after prediction bytes are committed and leakage/blinding checks pass; verify exact commitment equality before scoring; exact outcome equality drives `n_exact_match`. | Corrupt key, commitment mismatch, or premature access causes terminal `INTEGRITY_FAILED`, no metrics. | Target identity binds the opaque commitment; scoring identity binds the canonical key digest plus committed prediction digest. Exact JSON object equality/canonical outcome ordering belongs to the adapter schema. |
| Prediction `execution_state`, `outcome_state`, emitted value | Execution: `COMPLETED`, `NOT_EVALUATED`, `DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, `TRUNCATED`, `INVALID_INPUT`. Completed outcomes: `EMITTED`, `ABSTAINED`, `NOT_APPLICABLE`, `UNKNOWN`. | One row/item. Completed row follows outcome state; non-completed row has no emitted value and an unknown/null outcome. | Preserve every state and denominator; do not silently drop rows or promote failure/missingness to a negative. | Bind prediction digest and scoring implementation/version. Mapping of M15 dossier states to these item states is unresolved. |
| Group checks and custody events | Same-group split consistency; custody order `SEALED → PREDICTIONS_COMMITTED → BLINDED_CHECKED → SCORED`; integrity failure is terminal. | Emit deterministic leakage report and sequence-numbered append-only custody log. | Leakage, blinding, target/key/prediction integrity failure blocks score and metric artifact. | Bind event actor/tool identity and relevant digests; timestamp-independent sequence numbers. |
| Metrics | `n_items` partition and three label-state counts each sum to item count; `n_emitted`, `n_exact_match`, coverage, agreement, and match-over-labelled use the frozen formulas. Rates are null at zero denominator; no threshold. | Exact denominator accounting and fixed declared decimal precision. | Zero denominators yield null, not zero; integrity/leakage failure emits no metrics. | Bind scoring version, contract semantic version, key and prediction digests, and output hashes. These are software-fixture metrics only. |
| Result bundle/cache | Bind public digest, target/run/output and implementation/config identity, adapter, groups/splits, labels, key commitment, predictions, scoring, contract, and output hashes. | Canonical UTF-8 JSON, no BOM, LF, one final newline; sorted keys, items/predictions by ID, groups by group/split, custody by sequence. | Cache reuse only when exact identities and output hashes verify; tampering must miss/reject reuse. | Commitment and canonical sealed-key digest are distinct: execution identity binds the opaque commitment; scoring identity additionally binds the canonical key digest and committed prediction digest. Input digest kind and cache identity composition are not fully frozen; see §5. M16 changes must not invalidate or rewrite M12–M15 outputs. |

The only frozen comparison semantics are exact equality of adapter-defined
synthetic outcomes and the denominator-aware fixture metrics. No candidate
ranking, score, prioritization, classification, confidence, promotion rule,
threshold, or biological performance interpretation is defined. Adding any of
those would require separate decisions; none is inferred here.
The formulas are frozen, but the contract does not provide the decimal precision
or rounding rule behind “fixed declared precision.” Those values must be
declared and tested before metric bytes can be uniquely reproduced.

## 5. State, identity, ordering, and cache audit

### State preservation and candidate identity

M15 has its own four-valued `result_completeness`, plus per-record validation,
provenance, producer execution, and six semantic axes. The actual resolver
sorts records by `evidence_id`, preserves unknown raw status/schema, and reports
unavailable/incomplete/invalid provenance separately
([state construction](../../satellite_discovery/m15_stage.py#L346-L420),
[completion and ordering](../../satellite_discovery/m15_stage.py#L790-L833)).
M16’s prediction/label partitions are separate; unknown and not-applicable
labels are excluded from `n_labelled`, and upstream non-success is not a
biological negative. What is not frozen is whether an M15 `PARTIAL` or
`NOT_EVALUATED` bundle blocks target execution, yields per-item dependency
states, or can be consumed as an opaque artifact. That policy must be decided
without collapsing M15’s finer states.

M15 `candidate_id` is an opaque dossier identifier; M15 evidence IDs are
derived from producer binding, artifact digest, and source-row identity.
M16 separately requires unique `item_id` and uses `group_ids` only for leakage
checks. The contracts do not define equality or deduplication between those
identities, biological-similarity deduplication, or one-candidate-to-many-item
mapping. Preserve IDs as distinct namespaces; only exact fixture item
duplicates are rejected by the M16 rules.

### Producer authentication, fabrication, and tampering

M15 `m15-input-v2` authenticates producer references through
`producer-execution-ref-v1`; legacy v1 refs are `INVALID_PROVENANCE`, and
caller-supplied snapshots are `UNVERIFIED`. The verifier checks completed
status, matching workflow/stage identity and digests, typed descriptor,
inventory, contained regular paths, and bytes. M15 tests cover changed workflow
digest, stage ID/kind, run-manifest digest, and raw status, and preserve
nonterminal producers as `INCOMPLETE`
([tamper and incomplete tests](../../tests/test_m15_workflow.py#L626-L729)).

These checks reject a changed/tampered file or inconsistent provenance chain.
They do not prove creator identity: a fabricated but internally consistent
workflow plus its own stage manifest, descriptor, inventory, and artifact is
self-consistent under the local trust model. Acceptance tests must state that
boundary instead of claiming signer authentication. M16’s frozen contract
requires integrity checks but does not add a signer or external trust anchor.

### Deterministic order, permutation, relocation, and line endings

- **Ordering:** M16 explicitly sorts public items and predictions by
  `item_id`, group checks by group/split, custody by sequence, and metric rows
  by adapter-defined outcome. M15 already canonicalizes output and sorts
  evidence IDs and edges. The adapter must define a stable canonical
  representation/comparator for object outcomes; “adapter-defined” does not
  supply one by itself.
- **Permutation:** Item/key input array reordering must not reorder output
  rows; IDs define output order. However, M16 also binds a public-manifest
  digest and does not state whether it is raw-byte or canonical-semantic.
  Therefore permutation can preserve prediction ordering while changing the
  result/cache identity if the raw digest is used. Freeze the digest kind
  before asserting that the complete result bundle is permutation-invariant.
- **Relocation:** Target refs use relative paths. The shared verifier's binding
  omits the bundle-root and workflow-file location, but it includes the
  artifact-relative output path. Copying an unchanged bundle while preserving
  relative references should therefore preserve its binding; changing the
  artifact-relative path changes it. Rewriting a hashed workflow manifest
  (including any embedded path value) changes its raw workflow digest and must
  produce a new producer binding/cache identity. Test these separately; do not
  normalize away changed manifest bytes.
- **LF/CRLF:** M16 output bytes are frozen to LF with one trailing newline.
  The freeze does not say whether CRLF input JSON is rejected or parsed and
  normalized. A branch-local plan proposes rejecting CRLF, but that is not a
  normative contract rule. Decide input policy and digest semantics; do not
  report CRLF rejection as already frozen.
- **Stale/tampered cache:** the freeze requires exact identity plus verified
  output hashes. A changed target digest/identity, adapter, fixture, key,
  scoring implementation, contract, or output hash must cause an M16 cache
  miss/rejection; post-commit target/key/prediction tampering must yield
  `INTEGRITY_FAILED` and no metrics. M16-only source/registration changes
  must leave M1–M15 cache identities and outputs unchanged.

### Initial shared-infrastructure blocker (resolved after PR #51; see §10)

The live M1/M4 runner uses a package-wide source digest for handlers without a
stage-specific `cache_implementation_identity`
([cache-key composition](../../satellite_discovery/artifact_workflow.py#L818-L850)).
Adding M16 code and registrations to shared package/registry files can
therefore invalidate unscoped upstream stage keys. The stage-specific source
identities on `main` also couple earlier stages to those shared files: M12
hashes all of `artifact_workflow.py`; M13 hashes all of
`artifact_contracts.py` and `artifact_workflow.py`; and M15 hashes both files
([M12 source list](../../satellite_discovery/m12_artifact_review.py#L60-L77),
[M13 source list](../../satellite_discovery/m13_stage.py#L54-L78),
[M15 source list](../../satellite_discovery/m15_stage.py#L130-L148)).
The additive M16 changes proposed for those files would consequently change
M12/M13/M15 implementation identities unless their source dependencies are
isolated. M15 calls `verify_producer_artifact()` from
`producer_provenance.py`, but that verifier is absent from M15’s explicit
source list. M15’s cache context and emitted bundle both reuse this identity
([cache context](../../satellite_discovery/m15_stage.py#L1010-L1029),
[bundle identity](../../satellite_discovery/m15_stage.py#L1121-L1129)).
M14 uses a narrower identity: its implementation digest is its own stage file,
the registration identity is for the M14 stage, and contract semantics are
selected by consumed types. Do not unnecessarily invalidate M14 while
decoupling the other affected identities
([M14 cache identity](../../satellite_discovery/m14_descriptive_observations.py#L1361-L1391)).
Thus a producer-verifier change can leave M15’s declared implementation
identity unchanged, while an unrelated M16 registration can change M12/M13/M15
source identities. Both violate the M16-only cache boundary unless stage-owned
source closure and selected contract semantics are available and
regression-tested.

`stage_cache_identity.py` is absent from authoritative `main`. The unmerged
cache prerequisite must pass its M1–M15 identity/reuse regression and CI before
M16 registration or implementation. The exact intended gate is also recorded
as planning in [M16 implementation steps](M16_IMPLEMENTATION_EXECUTION_PLAN.md#1-frozen-implementation-boundary)
and [M16 cache requirements](M16_IMPLEMENTATION_EXECUTION_PLAN.md#5-cache-and-provenance-identity).

## 6. Initial acceptance-fixture matrix (current status in §10)

| Fixture | Expected result from frozen behavior | Current evidence / unresolved gate |
| --- | --- | --- |
| Real synthetic M15 run → authenticated `m15_result_bundle` → M16 consumes that exact file | Build a fully synthetic M1 producer workflow and typed artifact; run actual M15 through the workflow runner; authenticate M15’s output against its own M1 workflow/stage manifest; pass that exact output to M16. M16 must record the same bytes/digest and target identity. No mock/re-serialization. | M15’s existing handoff test verifies an actual M15 output but does not invoke M16 and uses a caller-snapshot input. Required end-to-end test is absent. |
| M15 complete / partial / not evaluated / invalid, including unavailable, failed, interrupted, incomplete, invalid-provenance, and unverified input records | Preserve exact M15 completeness and producer state; never map any to a biological negative or scoped no-signal. | M15 defines these states; M16 target eligibility and item-state mapping are not frozen. Block target scoring until this is decided. |
| Valid authenticated M15 output, then mutate result bytes, workflow digest, stage-manifest digest, stage ID/kind, descriptor type/version, or inventory | Reject target integrity/provenance; `INTEGRITY_FAILED`; no metric artifact. | The shared verifier and M15 tamper tests establish behavior for the producer chain; M16-specific coverage is absent. |
| Fabricated but internally consistent workflow, stage manifest, typed descriptor, inventory, and artifact | Accepted only as internally consistent under the current local trust model, unless a separate trust anchor is specified. Never label this signer-authenticated. | Shared verifier explicitly does not identify the creator. A cryptographic authenticity requirement would need a new frozen mechanism. |
| Reorder public items and key items | Output item/prediction rows remain sorted by `item_id`; counts and leakage result are unchanged. | Full result/cache identity is unresolved until raw-versus-canonical manifest digest is fixed. |
| Relocate an intact target bundle without changing its internal bytes or relative references | Resolve and verify; preserve content binding. | Test relative relocation separately from rewriting hashed workflow-manifest contents, which must change its digest and identity. |
| LF versus CRLF JSON and output serialization | Outputs always use the frozen LF canonical form. | Input CRLF accept/reject and digest behavior are not frozen; the plan’s rejection proposal is not normative. |
| Stale or tampered M16 cache; changed target, adapter, fixture, key, scoring code, or output | Do not reuse; recompute or fail closed. Tampered post-commit artifacts produce `INTEGRITY_FAILED` and no metrics. | No M16 implementation/cache tests exist; shared cache-isolation prerequisite is not merged. |
| Synthetic missing/unknown/N/A, failed/unavailable/incomplete item, zero labelled/emitted items, leakage, hidden key | Preserve each axis; unknown/N/A excluded from labelled denominator; non-success items retained; zero denominator rates null; leakage/blinding blocks scoring. | Formulas and main behavior are frozen in M16 §§3–8; implement exact fixture checks without upgrading states. |

## 7. Shared infrastructure, regression, and resource boundaries

### Initial shared-infrastructure gate (satisfied after PR #51; see §10)

Before M16 changes shared registration or cache code:

1. Merge the stage-scoped source/contract identity prerequisite and pass its
   configured CI and complete M1–M15 regression boundary.
2. Verify exact baseline cache identity preservation for unaffected stages,
   with only explicitly reviewed M14/M15 refreshes if the prerequisite changes
   their real dependencies.
3. Verify that a M15 verifier-source change changes M15 identity, while a
   downstream-only M16 module/contract/registration change changes only M16.
4. Verify relocation, line-ending handling, packaged-resource identity, and
   rejection of unknown legacy aliases.

This was the gate recorded against the pre-PR-#51 baseline. PR #51 is now
merged into authoritative `main`; the current implementation and regression
evidence are summarized in §10. No cache prerequisite was implemented or
modified in this task.

### M1–M15 regression boundary

M16 must be strictly additive. Keep all existing M1–M15 contracts,
implementations, behavior, tests, and CI unchanged. Run the full existing
offline suite after the infrastructure prerequisite and again after M16
integration. Assert no upstream artifact is rewritten; no unrelated
M1–M15 identity/key changes; no M5 completed-zero promotion; no M6 same-read
independence inflation; no M7 declared-independence upgrade; no M8/M9
failure/no-hit coercion; no M10 pattern-to-topology promotion; no M11 fold
prediction promotion; and no change to M12–M15 descriptive or scoped
semantics. The implementation plan enumerates the relevant regression surfaces
([M16 plan §8](M16_IMPLEMENTATION_EXECUTION_PLAN.md#8-test-modules-and-regression-gates)).

### Offline/resource and scientific-claim boundary

Use generated synthetic fixtures, the existing manifest runner, and local
validators only. Do not retrieve biological sequences, reads, databases, or
benchmark labels; run external biological callers; provision optional
biological tools; choose empirical splits or truth tiers; or infer experimental
validation. `SYNTHETIC_HOLDOUT` is a mechanics fixture role only. Report any
agreement/coverage solely as `SOFTWARE_CONTRACT` fixture metrics. No synthetic
result establishes identity, source, DVG/satellite status, helper dependence,
function, sensitivity, specificity, accuracy, calibration, or a biological
winner.

## 8. Likely implementation files and explicit no-change list

For a subsequent M16 implementation, the planning-only file list remains a
reasonable starting point:

- New `satellite_discovery/m16_contracts.py` and
  `satellite_discovery/m16_stage.py`.
- New focused tests for contracts, leakage, custody, metrics, serialization,
  and workflow integration; the integration test must execute the real
  synthetic M15 producer path described above.
- Additive M16 output contracts in `satellite_discovery/artifact_contracts.py`
  and one allowlisted registration in
  `satellite_discovery/artifact_workflow.py`.
- Focused cache-isolation coverage, after the shared prerequisite is merged.

This is a likely file set, not approval to start implementation. Do **not**
change the M16 or M15 frozen contracts, M1–M15 production code or tests,
existing CI, README, ROADMAP, data/tool configuration, or biological inputs
as part of this audit. No implementation PR is opened.

## 9. Initial pre-clarification disposition (superseded by §10)

**BLOCKED for integrated M16 implementation on the authoritative post-M15
`main` tree.** The following are concrete blockers, not empirical-data
decisions:

1. The shared stage-scoped cache/source-identity prerequisite is not merged;
   current fallback and M15 source identity do not isolate M16 additions or
   bind the producer verifier correctly.
2. M16’s accepted `m15_result_bundle` has no frozen per-item prediction
   transform. M15 is descriptive and emits no prediction/class/rank. An
   adapter can provide mechanics-only opaque outputs, but no M15 evaluation
   claim may be made without a software-only mapping contract.
3. M16 does not disambiguate M15’s descriptor contract version, bundle
   semantic version, validator semantic version, workflow-manifest digest,
   stage-manifest digest, and implementation/configuration identity.
4. M16 does not specify how to treat a structurally valid but partial or
   not-evaluated M15 result bundle as a target, or how its states relate to
   M16 item execution states.
5. Public-manifest digest-kind and CRLF input behavior remain unspecified,
   affecting permutation, byte determinism, and cache expectations.
6. The output decimal precision and rounding rule for rates are not given,
   although the contract requires a fixed declared precision.
7. Existing M15 handoff coverage does not satisfy the required real synthetic
   M15 → authenticated bundle → M16 exact-artifact integration test.

The generic synthetic split, custody, state-accounting, and exact-match
denominator mechanics are **conditionally ready** once implemented with a
registered test adapter whose schema and ordering are deterministic. They do
not authorize ranking, classification, prioritization, confidence, threshold,
promotion, or biological performance semantics.

**Validation performed for this report:** the M15 workflow tests
(`python -m unittest discover -s tests -p 'test_m15_workflow.py' -v`) passed all
18 tests on the isolated authoritative-main worktree. The Markdown check
examined 55 links, and every local linked file and anchor resolved.
`git diff --check` passed after the final report edit. GitHub PR #51 status and
its changed-file list were rechecked; no M16 or biological execution was
attempted.

## 10. Post-prerequisite reconciliation

This section is the current disposition, based on authoritative `main` at
`c620834c78c51b33989880ce78f5bcb36f0e9845` (tree
`b4ebcb31ca412ac01e1f3a54d700099f3e5c7eea`) and the existing M16 clarification
identified in §2. The clarification is available in local Git history at
`e617d511716b0896daa33b17114449cfe4da316f`, but its file is not in the
authoritative main tree. This report uses that pre-existing, normatively
labelled supplement because this reconciliation explicitly names it; it does
not misstate it as a file merged to `main`. M15 and shared-verifier facts below
were independently checked against the merged implementation.

### Previous status → current status

| Area | Previous readiness report | Current status | Evidence / consequence |
| --- | --- | --- | --- |
| Cache/registration isolation | **BLOCKED**: shared source/cache identity could change M12–M15 when downstream registration was added. | **RESOLVED** for additive M16 registration/module/contract additions. | PR #51 is merged. `test_downstream_contract_registration_and_module_leave_all_existing_keys_stable` verifies all 36 existing stage keys and M12/M13/M15 source identities remain stable when a downstream contract, registration, and module are added; the added stage produces key 37. PR #51's intentional M14/M15 identity refreshes are already part of the c620 baseline, not an M16 side effect. M16 must add only a stage-scoped normalized input projection and test that the current c620 M1–M15 identities remain unchanged. |
| M15 target/prediction mapping | **UNRESOLVED**: no frozen per-item mapping from an M15 dossier to M16 output. | **RESOLVED** for the clarified `m15_dossier_state_projection` adapter v1. | The existing supplement defines one M15 result-bundle target plus all three verified companions, a strict `m16-m15-state-query-v1` input selecting sorted unique `evidence_id`s, and one opaque state-projection outcome per public item. It does not assign biological meaning. |
| State projection | **UNRESOLVED**: partial and non-success M15 states had no M16 mapping. | **RESOLVED**: preserve literal M15 state values inside the emitted projection. | `COMPLETED/EMITTED` means only that the adapter emitted the projection. M15 completeness, validation, provenance, producer-execution state, raw status/schema, six semantic axes, reasons, bindings, and edge IDs are copied without voting, ranking, collapsing, or conversion to a biological negative. |
| Provenance/version binding | **UNRESOLVED**: M15 workflow, stage-manifest, descriptor, schema, and implementation versions were conflated. | **RESOLVED** through the shared verifier plus the clarified target-ref schema. | Use `producer_workflow_ref.sha256` for raw `workflow.json` identity and `producer_stage_manifest_sha256` separately. Bind workflow/stage IDs and raw statuses, M15 bundle digest, typed descriptor type/version, payload schema/semantic version, exact implementation/contract-semantics objects, empty M15 configuration, and all three companion type/version/schema/digests. |
| Determinism/cache identity | **UNRESOLVED**: canonical input digest, CRLF, ordering, decimal precision, and cache composition were unspecified. | **RESOLVED** by the existing M16 supplement; implementation still required. | It defines `m16-semantic-json-v1`, field-specific set ordering, path-free semantic M16 input digests, raw M15 artifact/companion digests, six-place `ROUND_HALF_EVEN` rates, and versioned M16 execution/scoring/cache projections. Add the M16-specific projection without changing M1–M15 identities; do not normalize M15 producer-chain bytes. |
| Real M15 → M16 integration test | **MISSING**, previously described among prerequisite gates. | **MANDATORY M16 implementation acceptance**, not a prerequisite to start. | It cannot exercise the production M16 path before that path exists. Before M16 is accepted, the test must execute a synthetic producer, run actual M15 with authenticated `m15-input-v2`, verify the result bundle and three companions, construct the exact target ref, and run M16 on those exact artifacts. A handcrafted M15-shaped JSON fixture is insufficient. |

### M15 target-reference and projection contract

The clarified M15 profile is exact and matches the merged M15 output interface.
The bundle payload schema is `m15-result-bundle-v2`, its semantic version is
`"2"`, and its `input_schema` is `m15-input-v1` or `m15-input-v2`:

| Input | Deterministic rule and output | Missing/invalid behavior |
| --- | --- | --- |
| M15 target | Accept one `m15_result_bundle` (`contract_version: "1"`, `m15-result-bundle-v2`, `semantic_version: "2"`, producer stage `m15_evidence_dossier`, stage version `"2"`), plus its verified evidence envelope, dependency edges, and dossier summary. Require the selected M15 producer stage to be complete. Bind the bundle implementation to `stage_manifest.identity.implementation`; require configuration `{}`. | Missing producer dependency preserves M1 `dependency_missing`. A non-complete selected producer stage preserves the shared verifier's `PRODUCER_STAGE_INCOMPLETE` and stops before scoring. Malformed target-ref shape is rejected before execution; a well-formed but inconsistent or tampered producer chain is terminal `INTEGRITY_FAILED`, with no metrics. |
| Workflow/stage identity | Map M16's run-manifest field to the raw `producer_workflow_ref.sha256` and retain `workflow_id`. Bind the selected stage ID/kind, raw `producer_stage_manifest_sha256`, stage version/status, descriptor type/version, and artifact digest separately. M15's input `producer_run_manifest_sha256` is an upstream input identity and is not the M15 target run identity. | Do not infer or substitute one digest for another. Digest, identity, descriptor, path-containment, or companion mismatch prevents scoring. |
| Verifier binding and companions | Use `verify_producer_artifact` and its returned `binding_sha256` for the result bundle. The shared binding covers workflow ID/hash/status, stage ID/kind/status and manifest digest, the declared stage-output-relative artifact path, artifact type, descriptor contract version, and artifact digest. Verify every companion's raw bytes, typed descriptor, schema, and inventory digest. Filesystem root and fixture locator paths do not enter M16 semantic identity; the authenticated relative artifact path remains unchanged by relocating an intact tree. | Hash-chain verification is integrity/consistency, not signer authentication. A changed or inconsistent chain fails. A fully self-consistent fabricated chain cannot be distinguished without an external trust anchor; do not claim otherwise. |
| Public item and query | Each `item_id` has a hash-bound query reference with a normalized relative path and schema `m16-m15-state-query-v1`. Its digest is over canonical semantic JSON after sorting unique lowercase SHA-256 `evidence_ids`, not raw file bytes. Resolve each ID to exactly one envelope record. Empty selection is a valid empty projection, not absence/no-signal. | Missing query file is `DEPENDENCY_UNAVAILABLE`; bad digest/schema or unknown/duplicate evidence IDs is `INVALID_INPUT`; retain the item with `UNKNOWN` outcome and no emitted value. |
| Projection value | Emit exactly one row per item. For a valid target/query it is `COMPLETED/EMITTED`, with `m16-m15-dossier-state-projection-v1`: copy bundle `input_schema`, `semantic_version`, `candidate_id`, `result_completeness`, and `optional_stage_states`; copy envelope `compatibility_warnings`; copy selected-record `evidence_id`, `validation_state`, `reason_code`, `producer_status_raw`, `producer_schema_raw`, `producer_provenance_state`, `producer_provenance_error_code`, `producer_binding_sha256`, `producer_execution_state`, `semantic_axes`, and `dependency_edge_ids`. Sort records by `evidence_id`; do not copy local paths or reinterpret evidence. | A valid M15 bundle may itself say `PARTIAL`, `NOT_EVALUATED`, or `INVALID`; project it with that exact value. This is distinct from an invalid outer producer chain. |
| Identity and duplicates | The target is the complete bound M15 artifact instance, not `candidate_id`, an evidence row, array position, or similarity cluster. `candidate_id` is not globally unique. Repeated items may select the same evidence and remain separate item rows; M15 duplicate-reference records remain visible as invalid records, not new targets. | M16 v1 rejects multiple target refs. Do not deduplicate across distinct item IDs or map candidate IDs to item IDs. |

The exact target-ref schema is `m16-m15-target-ref-v1`, with
`producer_milestone: "M15"` and a nested `producer-execution-ref-v1`; its
remaining fields are `bundle_root_ref`, `producer_execution_ref`, `artifact_type`,
`contract_version`, `semantic_version`, `artifact_path`,
`artifact_relative_path`, `artifact_sha256`, `implementation`,
`contract_semantics`, and `configuration`. `bundle_root_ref` is a normalized
relative locator; `artifact_path` must match the selected workflow-row
descriptor, and `artifact_relative_path` must match the M15 output-inventory
key. Validate both paths under the workflow root and reject traversal,
symlinks, and mismatch. Require the selected M15 stage kind/version/status,
the exact implementation equality with `stage_manifest.identity.implementation`,
and configuration `{}`. M15 bundle `producer_refs` describe M15's inputs, not
the identity of the M15 bundle itself. Its companion inventory must contain
exactly `evidence_envelope.json` (`m15-evidence-envelope-v2`),
`dependency_edges.json` (`m15-dependency-edges-v2`), and
`dossier_summary.json` (`m15-dossier-summary-v2`); each companion descriptor
uses typed artifact contract version `"1"`.

The projection's state-domain mapping is literal, not an aggregation rule:

| M15 source field | Permitted values | M16 transformation |
| --- | --- | --- |
| `result_completeness` | `COMPLETE_WITHIN_SUPPLIED_SCOPE`, `PARTIAL`, `NOT_EVALUATED`, `INVALID` | Copy as bundle-level output. None changes M16 row execution state or becomes an expected outcome. |
| `optional_stage_states` | `PRESENT`, `NOT_SUPPLIED`, `NOT_AUTHORIZED`, `UNAVAILABLE`, `NOT_APPLICABLE`, `UNKNOWN`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, `INVALID` | Copy exact object; missing/unavailable/failed branches are not negatives. |
| Record `validation_state` | `ACCEPTED`, `INVALID`, `UNAVAILABLE`, `INCOMPLETE`, `INVALID_PROVENANCE`, `UNVERIFIED` | Copy exact value; a valid projection remains `COMPLETED/EMITTED`. |
| Record `producer_provenance_state` | `VERIFIED`, `INVALID_PROVENANCE`, `UNAVAILABLE`, `INCOMPLETE`, `DECLARED_UNVERIFIED`, `INVALID` | Copy exact value and its error/binding fields; outer-chain verification does not upgrade it. |
| `semantic_axes.artifact_validity` | `VALID`, `INVALID`, `UNKNOWN` | Copy exact value. |
| `semantic_axes.applicability` | `APPLICABLE`, `NOT_APPLICABLE`, `UNKNOWN` | Copy exact value. |
| `semantic_axes.execution` | `pending`, `running`, `complete`, `skipped`, `dependency_missing`, `external_module_required`, `failed`, `interrupted`, `UNKNOWN` | Copy exact value; do not replace with the M16 adapter execution state. |
| `semantic_axes.completeness` | `COMPLETE`, `INCOMPLETE`, `TRUNCATED`, `UNKNOWN` | Copy exact value. |
| `semantic_axes.observation` | `OBSERVED`, `NOT_DETECTED_WITHIN_SCOPE`, `NO_OBSERVATION`, `UNKNOWN` | Copy exact value; scoped zero is not biological absence and no observation is not zero. |
| `semantic_axes.interpretation` | `SUPPORTS`, `CONFLICTS`, `UNRESOLVED`, `NOT_INTERPRETED` | Copy exact value; conflicts remain distinct records, with no vote or resolution. |
| `producer_status_raw`, `producer_schema_raw`, `producer_execution_state`, reasons, binding digest, edge IDs | Exact schema-valid source values; nullable values remain null | Copy exactly; sort selected records by `evidence_id`, and retain M15's canonical dependency-edge order. |

M15 requires each envelope record's `candidate_id` to equal its bundle-level
candidate ID and `source_row_ref` to be null for these whole-artifact records;
M16 validates but does not infer outcomes from either field. It also validates
and binds M15 `dependency_edges`, `contract_semantics`, `implementation`,
`outputs`, and `source_access_provenance` without reinterpreting them as item
outcomes. The full raw envelope, including `producer_ref`, is covered by its
verified companion digest; local producer paths are not recopied into projected
values.

M15 `m15-input-v1` references remain `INVALID_PROVENANCE` and their payload is
not promoted. The outer M15 bundle's producer authentication does not upgrade
that nested state. Valid/evaluable, scoped-zero, not-assessed, unavailable,
not-run, failed, interrupted, incomplete, invalid, invalid-provenance,
unverified, conflicting, and partial evidence retain their exact M15 values.
`NOT_DETECTED_WITHIN_SCOPE` is not biological absence; `NO_OBSERVATION` is not
a zero result; `CONFLICTS` is not a false prediction; dependency edges are not
votes or weights. The projection is a software fixture outcome only. No
ranking, scoring, prioritization, classification, confidence, promotion rule,
threshold, or biological claim is introduced.

### Determinism, cache, and acceptance boundary

The existing clarification versions public/key/query/projection schemas,
semantic JSON, target-execution identity, scoring identity, and stage-cache
identity. M16 JSON is parsed and semantically canonicalized: strict UTF-8
without BOM or duplicate keys/non-finite values, recursively sorted object
keys, exact numeric canonicalization, two-space JSON output and one final LF,
field-specific normalization of set-like arrays, and fixed six-decimal rates
rounded `ROUND_HALF_EVEN`. Only items/key rows, group IDs, query evidence IDs,
and selected evidence records are sorted as sets; M15 edge ordering remains
the M15 contract's responsibility. Equivalent M16 JSON object formatting,
LF/CRLF, relocation of intact workflow/fixture trees, and declared input
permutations preserve semantic M16 identity. M15 producer-chain raw bytes
remain verifier inputs: changing their line endings without regenerating all
digests fails; a newly generated chain receives a new binding.

The numeric rule is also explicit: parse integers as arbitrary-precision
integers and fractional/exponent tokens as exact finite decimals; canonicalize
decimals in normalized scientific form with one leading significant digit,
one following fractional digit or more, `e`, and an explicitly signed
base-ten exponent without leading zeros. Preserve decimal negative zero;
`1.0`, `1.00`, and `1e0` normalize to `1.0e+0`, while integer `1` stays `1`.
Metric rates use a schema-aware writer with exactly six fractional digits.
Strings compare by exact Unicode code points without normalization. Do not
substitute binary floating point or a generic JSON canonicalizer.

The exact `m16-target-execution-cache-v1` projection includes normalized
public-manifest/query semantics, fixture-set ID, item IDs and group/split/
label/provenance fields, target `binding_sha256`, and a target-artifact object
with the raw bundle/companion digests and type/version/schema plus exact M15
implementation, configuration, and contract-semantics objects. It includes
adapter/outcome-schema versions and the opaque sealed-key commitment. It
excludes locator paths, raw M16 JSON-file digests, key contents, and expected
outcomes. The separate `m16-scoring-identity-v1` adds the canonical sealed-key
and committed prediction digests, scorer identity/version, and raw hashes of
the four prediction/leakage/custody/metric sidecars. The `m16-stage-cache-key-v1`
binds the execution-identity
digest, canonical sealed-key digest, scorer implementation, and scoring
version `"1"`. The sealed-key commitment is an opaque custodian-supplied value;
the same value appears in the public manifest and sealed key and is checked for
exact equality after the key is opened. This profile does not define its
generation scheme; M16 must not derive it from key contents, and equality is
not cryptographic verification. The commitment is distinct from the canonical
sealed-key digest, which is added with the committed prediction digest to
scoring identity. For custody, `SEALED` requires `sealed_key_commitment` as a
structured field and MUST NOT read, open, or hash the sealed key;
`sealed_key_digest` is absent or null in `SEALED`, `PREDICTIONS_COMMITTED`, and
`BLINDED_CHECKED`. The scorer may open the key only after the latter two checks
pass; after opening, the canonical digest is recorded in scoring/custody state
and is required in `SCORED`. The M16 result bundle must not contain a
self-hash: its bytes are bound by the enclosing M1 descriptor and stage
manifest, while its siblings' raw hashes are in the bundle. Every cache hit
must revalidate the producer chain and output schemas/digests; stale or
tampered M16 outputs are misses and must be recomputed or rejected. The cache
projection is M16-only; raw M15 producer digests are never normalized. See the
[frozen custody rules](../M16_CONTRACT_FREEZE.md#5-groupleakage-and-custody-rules).

| Acceptance fixture | Expected result |
| --- | --- |
| Valid record; mixed valid/unavailable/failed/incomplete/invalid/conflicting records; partial or not-evaluated dossier; scoped zero; invalid-provenance or v1-unverified record | Emit the exact state projection, sorted by evidence ID; preserve every M15 value; no conversion to negative, vote, or winner. |
| Structurally valid bundle with `result_completeness: "INVALID"`; one target ref versus a target array; same-shaped independent M15 runs | Project the literal invalid completeness when the outer producer stage verifies; reject a target array; keep separate run bindings distinct even when candidate ID/content match. |
| Missing bundle, incomplete selected stage, bad workflow/stage/version/path/digest, or tampered companion | Preserve dependency/incomplete lifecycle where applicable; reject inconsistent/tampered chain as `INTEGRITY_FAILED`; no score or metrics. |
| Fully self-consistent fabricated workflow chain | Hash verifier can establish only internal consistency; do not claim creator authentication. |
| Duplicate/unknown query evidence ID, empty query, repeated evidence across distinct items | Reject only invalid ID references; empty is an empty projection; distinct public items remain separate rows. |
| Permute item/key/query set arrays; reorder JSON object keys; relocate intact workflow/fixture trees | Same normalized M16 identity and deterministic outputs; preserve exact M15 order where the M15 contract requires it. |
| M16 JSON LF/CRLF versus M15 producer-chain LF/CRLF | Equivalent M16 JSON has the same semantic identity and canonical LF output. Altered M15 raw chain bytes fail verification unless the producer chain is regenerated, in which case it has a new binding. |
| Change M15 workflow/stage/artifact bytes or M16 cache output; reuse a stale cache | M15-chain changes fail verification or create a new target binding; tampered/stale M16 outputs are rejected and recomputed, never returned as valid. |
| Real synthetic M15 production → authenticated result bundle + all companions → M16 production path | Required end-to-end acceptance; assert exact target binding and state projection using actual M15 outputs, not hand-authored lookalikes. |
| Add M16 registration/module/cache projection | Current c620 M1–M15 keys and implementation identities stay stable; run the full existing offline M1–M15 regression suite. |

PR #51 closes the broad cache/registration prerequisite, not the M16-specific
normalization implementation itself. The latter is an explicit M16 deliverable:
add the versioned input projection in the shared runner as an opt-in M16-only
path and prove that the current c620 M1–M15 identities are unchanged. Do not
edit the M1–M15 source-identity algorithm, widen legacy aliases, or change
upstream output bytes.

The implementation boundary remains offline and synthetic. No biological
sequence, read, dataset, benchmark label, external caller, or empirical
holdout is required or authorized. Existing M1–M15 tests and behavior remain
the regression boundary; the post-PR-#51 baseline includes its reviewed
M14/M15 identity migrations. M12–M14 content-to-outcome adapters are not
defined by the M15 supplement and must remain disabled until each has its own
frozen deterministic profile; that scoped limitation does not block the M15
profile and generic M16 mechanics.

Likely implementation files remain those in §8: new M16 contracts/stage/tests
and additive M16 artifact registration. The M15 adapter belongs in M16. Do not
change the M16/M15 freezes, any M1–M15 production code or tests, CI, README,
ROADMAP, data/tool configuration, or biological inputs. This task made no
implementation changes and opened no implementation PR.

**M16 POST-PREREQUISITE RECONCILIATION: READY FOR IMPLEMENTATION**
