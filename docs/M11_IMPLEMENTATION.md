# M11 RNA MFE implementation

M11 implements the approved baseline in
[the frozen contract](M11_CONTRACT_FREEZE.md). It is an optional workflow
stage named `m11_rna_mfe`; it does not change M6–M10 artifacts and is not a
required gate for those stages.

## Input and configuration

The stage accepts exactly one validated `m8_candidate_sequence_set` input.
It consumes the immutable candidate handoff, its FASTA payload when available,
and the handoff's checksum-bound source and reconstruction artifacts. M7–M10
artifacts are not inputs to M11.

The workflow may provide these configuration values:

| Key | Default | Meaning |
| --- | ---: | --- |
| `max_fold_symbols` | `100000` | Maximum symbols in one whole-sequence or explicit region request. |
| `max_folds_per_run` | `1000` | Maximum eligible candidate/region fold requests. |
| `timeout_seconds_per_fold` | `60` | Wall-clock limit for one isolated fold. |
| `memory_bytes_per_fold` | `2147483648` | Per-fold memory limit. |
| `region_requests` | `[]` | Optional requests with `candidate_id`, `sequence_id`, and zero-based, half-open `start`/`end` coordinates. |

When a candidate has one or more explicit region requests, those regions replace
its default whole-sequence request. Each region is accounted independently.
Invalid, unavailable, inapplicable, capped, interrupted, or failed requests
remain in fold accounting and do not receive fabricated structure evidence.

## Pinned runtime

M11 uses the official ViennaRNA 2.7.2 Python package with CPython 3.11 or 3.12
on Linux or Windows x86-64. Install the project, then provision the optional
runtime with:

```sh
python -m pip install .
python scripts/install_m11_runtime.py
```

The installer force-reinstalls only binary wheels from
`requirements-m11.lock` with hash verification, then writes an environment
receipt. At runtime, M11 verifies the wheel pin, interface version, native
library hash, and installed package-file digest against that receipt. A missing,
unsupported, changed, or unverified installation is reported as
`DEPENDENCY_UNAVAILABLE`; M11 does not fall back to another engine.

The wheel is not vendored or redistributed with the application. Review the
upstream ViennaRNA license and attribution terms before distribution. The
contract calls for contacting the ViennaRNA authors before commercial-product
release; this note is project guidance, not a legal opinion.

## Outputs and validation

The stage writes:

- `candidate_accounting.jsonl` — one source/provenance row per candidate plus a
  run header;
- `fold_accounting.jsonl` — one terminal typed status for every candidate or
  region request;
- `rna_structure_evidence.jsonl` — source-bound predictions only for validated
  completed folds;
- `mfe_raw_results.jsonl` — deterministic envelopes of the Python API's
  returned structure and IEEE-754 hexadecimal energy;
- `m11_bundle.json` — the run identity, effective configuration, counts,
  implementation/runtime identity, and hashes, paths, and roles for all child
  artifacts.

Records use canonical UTF-8 JSON with sorted keys and a final LF. Bundle
validation checks request coverage, status axes, source and view identities,
model profile, runtime receipt identity, energy/structure values, links, and
all child hashes. A predicted fold is a model-dependent structure hypothesis,
not observed structure or biological function.

Run the offline suite without a ViennaRNA installation:

```sh
python -m unittest discover -s tests -v
```

After provisioning the pinned runtime, run the synthetic golden-fold and
end-to-end bundle checks:

```sh
M11_REQUIRE_RUNTIME=1 python -m unittest tests.test_m11_runtime_smoke -v
```

CI runs the offline suite and the pinned-runtime checks separately on all four
supported operating-system/Python combinations.