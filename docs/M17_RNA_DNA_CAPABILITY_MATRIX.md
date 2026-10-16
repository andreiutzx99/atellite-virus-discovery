# M17–M18 RNA/DNA capability matrix and architecture audit

## Audit method

This audit checked the current registered workflow stages and their declared
input/output contracts in `build_default_registry()`, then inspected the
owning stage runners, validators, frozen contracts, and focused tests. A README
mention alone was not counted as an implementation. A typed edge is considered
compatible only when the consumer accepts the producer's declared artifact
type; matching filenames or JSON shape is not sufficient.

| Milestone | Observed software capability | Integration and pathway | Actual gap / interpretation boundary |
|---|---|---|---|
| M1-M3 | Acquisition/QC and initial reporting are exposed through the original CLI and workflow modules. | Reads/metadata into QC/report paths; no M17 coordinator. | Acquisition flows are deliberately not invoked by this offline demo. Audit the owning workflow/tests before extending them. |
| M4 | `artifact_workflow.run` validates an allowlisted graph, typed handoffs, dependencies, cache identity, provenance, recovery and reporting. | Compatible general-purpose stage engine; M17 reuses it. | M4 is orchestration infrastructure, not a complete discovery protocol. |
| M5 | Optional ViReMa caller adapter records caller-specific junction evidence. | Registered `dvg_virema`; external caller/tool requirements. | Not run in this demo; a junction or caller label is not proof of a DVG or satellite. |
| M6 | Residual evidence stage can emit the M8 candidate handoff, support and reconstruction artifacts. | M18 executes QC→M6 on generated reads; M17 retains its synthetic M6-shaped fixture path. | Synthetic M6 mapping and read-back are technical checks, not biological observations. |
| M7 | Independent recurrence has a validated stage and dataset/source provenance model. | Independent recurrence outputs are typed, but no independent synthetic datasets are provided here. | Skipped; repeated processing of one dataset is not independence. |
| M8 | Candidate/reference comparison uses declared snapshots and a pinned BLASTN profile. | Candidate handoff is compatible; reference snapshot and external-tool gates remain. | Not run without a supplied snapshot; no-hit is reference/method scoped, not novelty. |
| M9 | Deterministic ORF hypotheses and optional protein search. | M17 and M18 run M9 ORF translation from the typed M8 candidate set; M9 results feed M10. | ORFs are hypotheses; BLASTP/reference comparison is not run. |
| M10 | Dependency-free exact-first sequence architecture/repeat analysis. | M17 and M18 consume the same typed M8 candidate set plus M9 output. | Descriptive topology/repeat evidence does not establish circularity, function, or satellite status. |
| M18 | Synthetic-only seeded read generation and end-to-end integration. | Runs registered QC→M6→M9→M10 stages via M4 on artificial reads and references. | Validates technical execution only; no biological reads, references, validation, or discovery claims. |
| M11 | Optional single-sequence RNA folding stage. | RNA-only input contract; optional ViennaRNA runtime. | Not run; predictions do not establish structure or function. DNA must not be sent to this stage. |
| M12 | Read-origin/technical-artifact review with explicit producer artifact inputs. | M5/M6 evidence can be reviewed when authentic artifacts and controls exist. | Not run: demo has no read-origin, control, or batch evidence. |
| M13 | DVG-versus-satellite evidence matrix from scoped M5 evidence. | Requires authentic caller and candidate provenance; does not itself call ViReMa. | Not run; no DVG classification is inferred from the synthetic junction-like label. |
| M14 | Validates caller-authored candidate/helper observations and emits descriptive summaries. | Uses declared units, matched pairs, evidence refs. | Not run; co-detection is not dependence and the demo supplies no experimental observations. |
| M15 | Integrates authenticated M5-M14 producer evidence into a dossier. | Typed, provenance-aware terminal integration. | Not run; no authentic producer bundle exists in this demo. |
| M16 | Blinded synthetic benchmark/custody stage with frozen M12-M15 target adapters. | Separate evaluation harness; not a discovery stage. | Not run; generator labels remain segregated and are not benchmark truth for biological methods. |

## M18 implemented path

M18 generates deterministic artificial A/C/G/T FASTQ and reference fixtures,
checks their exact bytes against a local synthetic-only provenance boundary,
and keeps scenario truth and RNA/DNA pathway labels outside the M4 graph. Its
allowlisted graph connects registered QC outputs to M6, then the typed M6
candidate sequence set to M9 and M10. Reports preserve reference accounting,
residual eligibility, assembly, read-back support, ORF, and architecture
outcomes independently. The same reads used for assembly supply read-back
support, so that evidence is not independent validation. M18 does not run M8
homology or any interpretation stage and does not claim satellite discovery.

## M17 implemented path

The synthetic coordinator generates a checksum-bound candidate set with opaque
candidate identifiers; scenario descriptions live only in the separate
`fixture_truth.json` fixture sidecar. It validates the candidate set with the
existing M8 contract validator, then runs the real M9 ORF and M10
exact-first handlers through the existing artifact workflow runner. The M9
`orf_results.json`→M10 handoff is contract-checked and recorded in the M4 graph.
M4 owns stage manifests, cache/reuse, integrity checks, status transitions and
interruption/recovery behavior; M17 does not reimplement those mechanisms.

| Capability | RNA | DNA |
|---|---|---|
| M9 ORF derivation | Executed | Executed |
| M10 exact-first architecture | Executed | Executed |
| M8 homology | Unavailable without a declared reference snapshot/tool | Same |
| M11 folding | Not evaluated in this slice; optional | Not applicable; never dispatched |
| DVG, helper, controls, recurrence | Not evaluated without their typed evidence | Not evaluated |
| Circular DNA / structural variants | Not applicable | Unavailable; no validated registered method |

The workflow's positive labels and scenario descriptions are test-fixture
metadata only. A synthetic result cannot establish a satellite, novel virus,
viral identity, DVG function, helper dependence, or biological discovery
performance.
