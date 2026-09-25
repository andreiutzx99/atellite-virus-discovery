# External tool adapters and workflow stages

This document describes the implemented, domain-neutral adapter foundation in
`artifact-workflow-v1`. It does not define or implement a biological analysis
module. The registry is populated by trusted Python application code; workflow
JSON selects registered names and supplies data only.

## Stage registry

`WorkflowStageRegistry` is the single dispatcher for fixed built-in stages,
trusted external-tool adapters and declarative external-module requirements.
The default registry retains the existing stage kinds and adds
`example_text_transform` plus the generic `external_module` placeholder.

Each registration has a unique stage kind, required and optional input fields,
a version, and a trusted handler. An adapter may also register a module name so
that a workflow can require it without hard-coding that module's stage kind.
Duplicate stage or module names fail immediately. Registry entries can be
inspected with `describe()` and are included in workflow manifests and reports.

For application code, register an adapter explicitly:

```python
from satellite_discovery.artifact_workflow import DEFAULT_STAGE_REGISTRY
from satellite_discovery.example_transform_adapter import ExampleTextTransformAdapter

DEFAULT_STAGE_REGISTRY.register_external_adapter(ExampleTextTransformAdapter())
```

The default application already registers this harmless example. A deployed
application should construct its registry once at trusted startup, before
validating or running workflow files. Registration is not performed by workflow
configuration.

## Adapter contract

Subclass `ExternalToolAdapter` and provide:

* **Identity:** stage kind, trusted module name, adapter name/version, and
  external tool name.
* **Dependencies:** one or more executable declarations, each with a stable
  dependency name, executable name/path, and version arguments. The shared
  dependency-review code resolves the executable, captures version output and
  hashes the executable when possible.
* **Inputs:** `input_fields` for required files and
  `optional_input_fields` for optional files. Workflow input values are paths
  to supplied files or verified artifacts from earlier completed stages.
  `validate_inputs()` resolves and checks regular files and prevents an input
  from being inside the stage output directory.
* **Configuration:** override `validate_config()` to accept a narrow JSON
  object, reject unknown keys and return normalized configuration. Do not put
  credentials in workflow configuration or command arguments.
* **Command construction:** implement
  `build_command(executables, inputs, output, config)` and return a non-empty
  list of strings. The first argument must be one of the declared executables.
  The adapter owns argument layout; workflow files cannot supply a command,
  executable override, Python module, or shell fragment.
* **Outputs:** declare relative output paths in `output_files`. The runner also
  retains `stdout.log` and `stderr.log`; every regular stage output is
  inventoried with byte size and SHA256. Symlinks, reparse points, special
  files, unsafe paths and budget overruns are rejected.
* **Limits:** select a finite positive timeout and positive stage byte budget.
  The shared bounded runner uses argv execution without a shell, separate
  stdout/stderr capture, timeout monitoring and process-tree cleanup.

Minimal implementation shape:

```python
class MyAdapter(ExternalToolAdapter):
    def __init__(self):
        super().__init__(
            kind="my_tool",
            module_name="vendor.my_tool",
            adapter_name="my-tool-adapter",
            adapter_version="1.0",
            tool_name="My Tool",
            dependencies=[{
                "name": "my_tool",
                "command": "my-tool",
                "version_args": ["--version"],
            }],
            input_fields={"source"},
            optional_input_fields={"metadata"},
            output_files=["result.txt"],
            timeout=120,
            max_bytes=20_000_000,
        )

    def validate_config(self, config):
        # Check exact allowed keys and value types; return normalized JSON data.
        return {}

    def build_command(self, executables, inputs, output, config):
        return [executables["my_tool"], str(inputs["source"]),
                str(output / "result.txt")]
```

Do not use `shell=True`, `os.system`, `eval`, `exec`, or imports derived from a
workflow file. The handler and executable declaration are trusted code. The
bounded runner is process/resource management, not a hostile-code sandbox; an
adapter author remains responsible for choosing a trustworthy executable and
for its behavior outside the stage directory.

## Manifests, provenance and reuse

External stages write `manifest.json` with schema
`external-tool-stage-v1`. It records:

* adapter name, version, stage kind and adapter source checksum;
* external tool name and, for each executable, resolved path, version output,
  dependency status and executable checksum when available;
* each supplied input path, size and checksum;
* normalized configuration and a safe argv representation (not shell text);
* Python/platform/source/Git environment information when available;
* start/finish times, duration, exit status and stage status;
* the inventory, byte sizes and checksums of captured logs and tool outputs.

`complete` results can be reused only when adapter identity/version/source,
tool executable identity, inputs, configuration, command and relevant
environment still match, and the complete current output inventory matches the
saved checksums. A folder's existence alone is never enough. Changed or
damaged results are preserved and rejected; use a new stage output folder to
rerun a failed or changed external stage.

The workflow-level `reproducibility.json` includes the registration snapshot
and the external stage manifest. It records file paths and hashes, not input
file contents.

## Workflow states and placeholders

Stage states and permitted paths are:

```text
pending -> running -> complete
                    -> dependency_missing
                    -> external_module_required
                    -> failed
                    -> interrupted
pending -> skipped
pending -> dependency_missing
pending -> external_module_required
```

`skipped` is available through `"skip": true` on a stage. It is not `complete`.
When a required executable is unavailable, the workflow records
`dependency_missing`, lists the missing dependency and stops before invoking
the adapter. A registered adapter can also be requested by module name:

```json
{
  "schema": "artifact-workflow-v1",
  "stages": [{
    "id": "optional",
    "kind": "external_module",
    "module": "vendor.future_adapter",
    "inputs": {"source": "input.txt"}
  }]
}
```

If the trusted module name is not registered, the stage becomes
`external_module_required`; no dynamic import or execution is attempted, and
completed earlier outputs remain unchanged. If it is registered, the registry
validates its input/configuration contract and invokes its trusted handler.

`dependency_missing` and `external_module_required` describe infrastructure
readiness only. Neither, nor `skipped`, means a successful analysis, zero
observations, absence of evidence or any domain conclusion. Ordinary stage
failures still stop execution and leave later stages `pending`, preserving the
existing workflow behavior. A workflow containing both completed and skipped
stages is reported as `partial`; an all-skipped workflow is `skipped`.

The configuration schema remains `artifact-workflow-v1`. Existing workflow
files without `config` or `skip` fields continue to validate. Unknown stage
kinds and unknown stage fields are rejected.

## Harmless example and tests

`ExampleTextTransformAdapter` launches a tiny Python command that reads an
artificial text fixture, prepends a configured prefix and writes
`transformed.txt`. It demonstrates registry registration, dependency
inspection, safe argv execution, separate logs, output inventory, provenance,
failure states and verified reuse. It performs no biological analysis.

Run focused and complete tests from the repository root:

```console
python -m unittest discover -s tests -p 'test_external_tool_adapters.py' -v
python -m unittest discover -s tests -v
```

Before accepting another adapter, tests should cover its input/configuration
validation, executable present/missing behavior, successful and failing exits,
timeout/interruption cleanup, output path and checksum inventory, manifest
provenance, changed-input/configuration invalidation, verified reuse, workflow
report states, and backward compatibility. Use artificial fixtures; do not use
existing user QC/results as adapter test inputs.

## Current limitations

The adapter framework is software infrastructure, not scientific validation.
The M1 example adapter did not include ViReMa or DVG analysis; the later
optional M5 ViReMa integration is documented in
[M5 DVG evidence](M5_DVG_EVIDENCE.md). The complete project still does not
provide validated satellite-virus discovery, candidate ranking, or biological
interpretation. The process runner does not provide hard CPU/RAM quotas or a
sandbox for malicious executables. Some
operating-system process-tree cleanup remains best-effort. A failed adapter
stage is preserved and requires a new output folder for a fresh run.