# Running the supported artifact tools

Use Python 3.11 or newer. The base package has no third-party Python runtime dependencies. Optional native tools belong to the environment in which Python runs; executables from a Windows installation cannot be assumed usable inside WSL/Linux.

## Windows

Double-click `Start.cmd` (or `Run-reviews.cmd`) for the numbered review menu. If a repository `.venv` exists it is used; otherwise the launcher uses Python on PATH. One-time setup, from the checkout:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
```

Menu 11 checks optional tools, 20 previews a workflow specification, 12 runs/resumes the supported workflow, 21 opens a report, and 22 compares two verified reference snapshots. The launcher prints output locations and explains errors. Existing metadata/QC command-line entry points remain available; Start now consistently opens artifact reviews.

## Linux and WSL

Use a configured Linux distribution with Python 3.11+. Clone the same repository inside that environment, then:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
sh Run-reviews.sh
```

The shell launcher finds its own checkout even when started from another working directory and handles paths containing spaces. It uses `.venv/bin/python` when present, otherwise `${SATELLITE_PYTHON:-python3}`. Set `SATELLITE_PYTHON` to one executable path, not a shell command. An installed environment also provides `satellite-reviews` directly. No launcher downloads biological data on startup.

This session's Windows WSL command did not expose a usable distribution; no real WSL deployment is claimed. Ubuntu CI tests the Linux package and shell entry point. A user/admin must configure WSL separately; this project does not alter Windows system features.

## Generic HPC/Linux usage

Create the virtual environment on a filesystem visible to the job. Load site-approved Python and any optional-tool modules before submitting a job. Use absolute paths in the scheduler command and keep the same output folder for resume:

```sh
/path/to/checkout/.venv/bin/python -m satellite_discovery.artifact_workflow \
  --manifest /path/to/checkout/examples/artifact-workflow/workflow.json \
  --output /path/to/persistent/output
```

Choose persistent output storage: converting scratch-only output into a finished run is not automatic. Standard `TMPDIR` (Linux) or `TEMP`/`TMP` (Windows) affects Python temporary directories. Stage-native scratch remains inside the owned output folder so its bytes can be monitored. No global PATH or environment configuration is modified by the application. Set PATH in the batch job itself if modules differ from the login shell. Runtime records capture the Python/OS/package versions and the actual external commands and executable hashes.

Request scheduler CPU/memory/time/storage resources according to site policy. Existing native review stages use bounded single-thread commands; application byte/time checks are polling limits, not scheduler quotas. Calls through the common process runner use POSIX process groups or Windows PID-specific tree cleanup, with the containment limits documented in PROCESS_RELIABILITY_REPORT.md. No Slurm/PBS submission adapter or real HPC deployment was tested. Headless report opening prints the path when a browser cannot be launched; copy the complete output folder to view relative report links elsewhere.

## Recovery and provenance

Run menu 20 first to catch missing files and misspelled configuration fields. Menu 12 with the same specification and output resumes after ordinary failures. It verifies completed outputs; changed source code/configuration/input requires a new folder. A process killed forcibly may leave a lock: confirm the owning process has stopped before manual removal. There is no unsafe automatic stale-lock deletion.

Each started artifact workflow writes `workflow.json`, `report.html`, and `reproducibility.json`, including failed/interrupted runs. If the output directory itself is inaccessible, the launcher reports that error directly; it cannot create a manifest in an unwritable directory. The reproducibility manifest contains configuration, package source hashes, Git revision/dirty status when available, OS/Python, installed optional-package versions, resolved input paths/hashes/sizes, stage manifests, executed external commands, reference version metadata, timestamps, output locations and verified reuse status. Git is optional for installed distributions; source hashes remain available. Unused tools are not represented as functionally validated. Input sequence contents, arbitrary environment variables and credentials are not embedded.

Reproducibility files can contain local paths and supplied reference-source descriptions; review them before sharing. They describe the latest attempt and retain links/hashes for earlier verified stage artifacts. Failed SRA outputs are preserved under `previous_attempts` before a retry so stale mates cannot masquerade as new outputs. Successful SRA scratch is removed; raw/compressed FASTQ outputs remain. Preserved failed files count toward byte budgets; move to a fresh output folder if accumulated artifacts exceed the cap.

## Acquisition fallback contract

The existing ENA/QC path records a failure class, failed stage, error type and explicit `automatic_alternative: not_configured`. It never substitutes another transport silently. `acquisition_fallback.run(methods, providers, verify, record)` is a tested application-code API: ordered configured provider names, transient-failure classification, explicit verification before acceptance, and persisted attempt transitions. Unknown providers/configuration are rejected before execution; integrity, permissions and disk failures do not trigger fallback. Interruptions propagate after recording.

Providers are trusted callables registered by application code, not arbitrary commands or import strings in a user configuration. No remote SRA provider is registered in production acquisition. Adding one requires a separately validated transport and explicit routing policy; the current API supports that without replacing the downloader or hiding verification failures. The local SRA conversion action remains explicit in menu 19.
