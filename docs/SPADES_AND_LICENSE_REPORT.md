# Artificial SPAdes diagnostic and licence audit

Baseline: merged PR #8, `40804a62`, 208 tests. This is a partial delivery of the follow-up request. It adds an independent artificial SPAdes diagnostic and an upstream licence audit. It does not connect reconstruction, reference withholding or DVG analysis into the viral/helper-dependent discovery chain. Existing QC and user read data were not used.

Historical PR #8 diagnostic report. Statements below that no arbitrary-input adapter existed, or that ViReMa was not integrated, describe that baseline; the current registered SPAdes/Tadpole stage is documented in the [assembly guide](ASSEMBLY.md), and the later ViReMa adapter/runtime evidence is documented in [DVG evidence](DVG_EVIDENCE.md). The licence findings remain specific to the audited sources.

| Component | Implemented | Runtime tested | Dependency | Remaining limitation |
|---|---|---|---|---|
| SPAdes fixed artificial diagnostic | Yes: single/paired fixtures, detection/version, input validation, bounded execution, raw output preservation, provenance, failure reports and verified reuse | Actual Linux SPAdes 3.15.5 passed both layouts and reuse; software fixtures locally | Externally installed `spades.py` or `spades`; CI obtains the distribution package | No native Windows installation here; only fixed generated data, no arbitrary-read adapter, no equivalence to Tadpole |
| SPAdes failures | Missing dependency, malformed generated input, empty/malformed output, timeout, interruption, byte-budget failure, changed executable/layout and corrupt reports/raw outputs | Software tests; missing dependency also exercised on this Windows host | None for mocked tests | Failure injections are wrapper tests, not proof of every real SPAdes failure mode |
| Per-record reference import | No new importer | No new runtime test | Existing file-level snapshots | Still missing; not promoted to operational |
| Production acquisition fallback | Existing contract only | Existing regression tests | No production alternative registered | Still not operational as automatic alternative acquisition |
| Independently verified withholding | No new mechanism | No | Existing supplied-digest evaluator | Withholding remains unverified |
| ViReMa licence audit | Yes, pinned repository/root and embedded-component licence inspection | Not an execution test | Official Routh Lab repository and its linked upstream source | Licence facts do not establish safety, fitness, reproducibility or blanket redistribution rights for dependencies |
| ViReMa adapter at PR #8 baseline | No | No | No installation made at that baseline | Later implemented as an optional source-pinned external adapter; see [DVG evidence](DVG_EVIDENCE.md) |

## Diagnostic usage and interpretation

With a compatible external installation on PATH, run `python -m satellite_discovery.artificial_spades --output NEW_FOLDER`, adding `--paired` for the paired fixture. The command accepts no input-read, reference, assembly-mode or arbitrary tool-argument options. It generates one seeded 2,000-base random software fixture and checks exact reconstruction allowing reverse-complement orientation. No public biological reads are downloaded for this diagnostic.

The wrapper caps execution at 180 seconds and 400 MB of stage files, requests two threads and the tool's 2 GB memory setting, and uses the existing subprocess cleanup. These are polling/tool controls rather than hard containment. The version probe is separately bounded. All upstream outputs remain under `assembly/`; copied contigs, logs, a lifecycle manifest and `diagnostic.json` support review. Diagnostics record input/output hashes, command, version, executable checksum, timestamps, duration and success exit status. On execution failure, exit status may remain unknown; the retained error/log must be inspected. A nonzero exit, missing output or invalid reconstruction cannot pass.

Completed results are reused only after input/engine, top-level artifact and raw-file inventory/hash verification. Failed/interrupted attempts require a new output folder. Reuse certifies saved artifacts, not the current health of all installed SPAdes components: the executable hash is not a fingerprint of every library/core binary. The CI package version is recorded by the runtime, but the apt repository/dependency closure is not pinned. No third-party runtime is committed or redistributed in this repository.

The implementation follows SPAdes' [official invocation documentation](https://ablab.github.io/spades/running.html). Its [installation documentation](https://ablab.github.io/spades/installation.html) describes compatible Linux/macOS distributions; this report makes no native Windows support claim.

## ViReMa audit, 2026-09-24

The developer-owned repository inspected is [Routh-Lab/ViReMaDocker](https://github.com/Routh-Lab/ViReMaDocker), at commit `481defd7c340bb52fa80748a89d478be9c265f64`. Its README identifies the packaged release as ViReMa 0.25 and links the original distribution on SourceForge. A presumed `Routh-Lab/ViReMa` GitHub URL returned 404; it is not the verified source.

The [root licence](https://github.com/Routh-Lab/ViReMaDocker/blob/481defd7c340bb52fa80748a89d478be9c265f64/LICENSE) is MIT, copyright 2022 Routh Lab. The [embedded ViReMa 0.25 licence](https://github.com/Routh-Lab/ViReMaDocker/blob/481defd7c340bb52fa80748a89d478be9c265f64/src/ViReMa_0.25/LICENSE.txt) contains MIT permission terms and copyright 2013–2021 Andrew Laurence Routh. Those terms allow redistribution subject to retaining the copyright and permission notice, with a warranty disclaimer. Root licence SHA256: `7fbf66e076e4f91256c541eca3fdaeb5d358e69c482a8bcf527c1fc87c281458`.

The bundled Bowtie directory has its own [Artistic licence](https://github.com/Routh-Lab/ViReMaDocker/blob/481defd7c340bb52fa80748a89d478be9c265f64/src/bowtie-0.12.9/COPYING). Thus the root MIT licence must not be treated as a blanket licence for the entire container or all dependencies. No complete dependency redistribution audit was performed, and no upstream implementation or example dataset was copied into this project.

At a high level, the upstream [container recipe](https://github.com/Routh-Lab/ViReMaDocker/blob/481defd7c340bb52fa80748a89d478be9c265f64/virema) uses Python, alignment tools and NumPy. Some components are version-selected while other package installations float, so a source commit alone does not prove a reproducible container build. The README describes command-line software and structured alignment/event outputs; output schemas and invocation details had not been turned into an adapter or validated at the PR #8 baseline.

Historical PR #8 integration choice: **not integrated**. The later M5 implementation uses a separately installed, source-pinned upstream copy, avoiding vendoring. This adapter is optional and does not extend this application's viral/helper-dependent discovery chain. No container is required or used by its artificial runtime check.

## Eight requested answers

1. **Genuine SPAdes runtime validation:** yes, Linux SPAdes 3.15.5 passed single/paired fixed artificial fixtures and reuse. Local Windows validates software behavior and the unavailable state only. This does not establish arbitrary biological-data performance.
2. **Per-record reference import:** still not operational as a new reference importer.
3. **Production acquisition fallback:** no registered automatic production alternative.
4. **Independent withholding:** still not verified by the existing benchmark evaluator.
5. **Verified ViReMa licence/method:** MIT for the audited repository and embedded ViReMa source; separate dependency licences apply. The later optional adapter and bounded Linux software diagnostic are described in [DVG evidence](DVG_EVIDENCE.md).
6. **ViReMa disposition at this report's PR #8 baseline:** not integrated or installed; no vendoring or container. The current M5 adapter uses an externally sourced, hash-pinned caller and does not extend the biological discovery chain.
7. **ViReMa artificial execution at this report's baseline:** none. A later real Linux runtime execution on generated software fixtures is recorded in [DVG evidence](DVG_EVIDENCE.md); it is not biological sensitivity/specificity evidence.
8. **Remaining generic work:** fuller dependency pinning/fingerprinting, additional platform diagnostics, hard resource containment, and independent general-purpose acquisition/import/benchmark tooling remain. Viral/helper-dependent discovery integration and DVG discrimination are not supplied by this pass. Artificial success is not biological sensitivity evidence.

## Runtime and regression evidence

[Linux run 36057938938](https://github.com/andreiutzx99/atellite-virus-discovery/actions/runs/36057938938), source `9b7ceef44ab3e08efc38c9dba31e94c62723b1da`, used the Ubuntu package `3.15.5+dfsg-7`, reporting SPAdes 3.15.5. Single-end: 1,524 reads; paired-end: 2,888 reads. Each produced one exact 2,000-base artificial contig and passed verified reuse. Structured summaries are in [validation/spades-linux.json](validation/spades-linux.json). All five jobs passed; optional Linux ran 217 tests without skips. The final PR checks rerun the same diagnostics and upload their full artificial output folders as `artificial-spades-evidence`, retained for 14 days.

The first CI attempt exposed a resource-monitor race when SPAdes removed a scratch directory during traversal. The monitor now tolerates disappearance of child directories while retaining errors for a missing stage root or denied access. A dedicated regression test covers those cases. No biological assembly parameters were tuned to resolve the failure.
