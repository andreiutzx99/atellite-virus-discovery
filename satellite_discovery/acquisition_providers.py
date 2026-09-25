"""Trusted acquisition providers for the ENA FASTQ and NCBI SRA public archives."""
from dataclasses import dataclass, field
import gzip
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

from . import __version__
from .acquisition_fallback import (
    ConversionFailureError, DependencyMissingError, DownloadBudgetExceededError,
    FileUnavailableError, MetadataUnavailableError, ProviderExecutionError,
    RecordUnavailableError, RemoteUnavailableError, UnsupportedLayoutError,
    VerificationError,
)
from .bounded_process import run as run_process, run_captured
from .metadata import enrich_ena
from .quality_control import check_mate, pair_id, records as fastq_records
from .sequence_downloader import checksum, download_file, files_for_run, write_json

ENA_FILE_REPORT_DOCS = "https://www.ebi.ac.uk/ena/portal/api/filereport"
NCBI_SRA_DOWNLOAD_DOCS = "https://www.ncbi.nlm.nih.gov/sra/docs/sradownload"
NCBI_SRA_TOOLKIT_DOCS = "https://github.com/ncbi/sra-tools/wiki/08.-prefetch-and-fasterq-dump"
MAX_NCBI_WORKSPACE_BYTES = 20 * 1024**3
NCBI_WORKSPACE_OVERHEAD_BYTES = 64 * 1024**2
NCBI_TOOL_TIMEOUT_SECONDS = 60 * 60
NCBI_TOOL_NAMES = ("prefetch", "vdb-validate", "fasterq-dump")
SRA_ACCESSION = re.compile(r"SRR\d+\Z")


@dataclass
class AcquisitionContext:
    row: dict
    directory: Path
    max_bytes: int
    offline: bool = False
    client: object = None
    progress: object = print
    transfer_attempts: list = field(default_factory=list)
    transfer_recorder: object = None
    downloader: object = None

    @property
    def accession(self):
        return self.row["run_accession"]


class ProviderRegistry:
    """Registry of trusted in-process provider implementations; config cannot import code."""

    def __init__(self):
        self._providers = {}

    def register(self, provider):
        name = getattr(provider, "name", None)
        priority = getattr(provider, "priority", None)
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", name):
            raise ValueError("Provider name must be a safe registered identifier")
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
            raise ValueError("Provider priority must be a nonnegative integer")
        if name in self._providers:
            raise ValueError("Duplicate acquisition provider: " + name)
        if any(existing.priority == priority for existing in self._providers.values()):
            raise ValueError("Acquisition provider priorities must be unique")
        for method in ("availability", "resolve", "acquire", "verify"):
            if not callable(getattr(provider, method, None)):
                raise ValueError("Provider is missing required method: " + method)
        self._providers[name] = provider

    def get(self, name):
        try:
            return self._providers[name]
        except KeyError:
            raise ValueError("Unknown acquisition provider: " + str(name)) from None

    def ordered(self, names=None):
        if names is None:
            return [self._providers[name] for name in sorted(
                self._providers, key=lambda key: (self._providers[key].priority, key))]
        if not isinstance(names, (list, tuple)) or not names:
            raise ValueError("Configure one or more registered acquisition providers")
        if any(not isinstance(name, str) for name in names):
            raise ValueError("Provider order must contain registered provider names")
        if len(set(names)) != len(names):
            raise ValueError("Duplicate acquisition provider in order")
        providers = [self.get(name) for name in names]
        if providers != sorted(providers, key=lambda item: (item.priority, item.name)):
            raise ValueError("Acquisition providers must follow registered priority order")
        return providers

    def describe(self):
        return [{
            "name": provider.name,
            "priority": provider.priority,
            "mechanism": provider.mechanism,
            "availability": provider.availability_description,
            "integrity": provider.integrity_description,
            "documentation": provider.documentation,
        } for provider in self.ordered()]

    @property
    def names(self):
        return [provider.name for provider in self.ordered()]


class ENAFastqProvider:
    name = "ena_fastq"
    priority = 10
    mechanism = "ENA Portal file report metadata and HTTPS FASTQ files"
    availability_description = "Public ENA file-report API and HTTPS FASTQ endpoint"
    integrity_description = "Exact declared byte count and provider MD5; local SHA256 recorded"
    documentation = ENA_FILE_REPORT_DOCS

    def availability(self, context):
        return {"available": True, "provider": self.name, "network_required": not context.offline}

    def resolve(self, context):
        row = dict(context.row)
        if not row.get("fastq_ftp") or not row.get("fastq_md5") or not row.get("fastq_bytes"):
            if context.client is None:
                raise MetadataUnavailableError("ENA file metadata is absent and no metadata client is available")
            try:
                enrich_ena(context.client, row)
            except Exception as exc:
                raise MetadataUnavailableError("ENA file metadata request failed: " + str(exc)) from exc
        try:
            files = files_for_run(row)
        except ValueError as exc:
            message = str(exc)
            if "layout" in message.lower() or "paired library" in message.lower():
                raise UnsupportedLayoutError(message) from exc
            raise MetadataUnavailableError("ENA file metadata is unusable: " + message) from exc
        return {"row": row, "files": files}

    def acquire(self, context):
        resolved = self.resolve(context)
        files = resolved["files"]
        needed = sum(item["bytes"] for item in files)
        if needed > context.max_bytes:
            raise DownloadBudgetExceededError(
                f"ENA run needs {needed} bytes but only {context.max_bytes} bytes are reserved"
            )
        directory = context.directory / "raw"
        artifacts = []
        downloader = context.downloader or download_file
        for spec in files:
            path = downloader(
                spec, directory, context.offline, context.progress,
                attempt_history=context.transfer_attempts,
                attempt_recorder=context.transfer_recorder,
            )
            artifacts.append({
                "role": spec["role"], "name": spec["name"], "path": str(path.resolve()),
                "bytes": path.stat().st_size, "expected_bytes": spec["bytes"],
                "expected_md5": spec["md5"], "observed_md5": checksum(path, "md5"),
                "sha256": checksum(path), "url": spec["url"],
            })
        return {
            "provider": self.name, "accession": context.accession, "layout": resolved["row"]["layout"],
            "files": artifacts,
            "provenance": {
                "metadata_source": "ENA Portal filereport",
                "metadata_documentation": self.documentation,
                "retrieval_method": "HTTPS FASTQ",
                "verification_method": ["declared_bytes", "provider_md5", "local_sha256"],
            },
        }

    def verify(self, artifact, context):
        if artifact.get("provider") != self.name or artifact.get("accession") != context.accession:
            raise VerificationError("ENA artifact provider or accession mismatch")
        files = artifact.get("files")
        if not isinstance(files, list) or not files or any(not isinstance(item, dict) for item in files):
            raise VerificationError("ENA provider returned no FASTQ files")
        roles = [item.get("role") for item in files]
        if any(not isinstance(role, str) for role in roles):
            raise VerificationError("ENA provider returned malformed FASTQ roles")
        if len(roles) != len(set(roles)):
            raise VerificationError("ENA provider returned duplicate FASTQ file roles")
        expected_names = {
            "single": context.accession + ".fastq.gz",
            "R1": context.accession + "_1.fastq.gz",
            "R2": context.accession + "_2.fastq.gz",
        }
        if set(roles) - set(expected_names):
            raise VerificationError("ENA provider returned an unsupported FASTQ role")
        if context.row.get("layout") == "PAIRED" and not {"R1", "R2"}.issubset(roles):
            raise VerificationError("ENA provider did not return a complete read pair")
        if context.row.get("layout") == "SINGLE" and roles != ["single"]:
            raise VerificationError("ENA provider returned files inconsistent with a single-end layout")
        verified = []
        for item in files:
            raw_path = Path(item.get("path", ""))
            if raw_path.is_symlink():
                raise VerificationError("ENA output path is a symbolic link")
            try:
                path = raw_path.resolve(strict=True)
                if (not path.is_relative_to((context.directory / "raw").resolve())
                        or not path.is_file()):
                    raise VerificationError("ENA output path is outside its provider directory")
            except OSError as exc:
                raise VerificationError("ENA FASTQ output is missing or unreadable") from exc
            if path.name != expected_names[item["role"]]:
                raise VerificationError("ENA output path is outside its provider directory")
            try:
                observed_bytes = path.stat().st_size
                observed_md5 = checksum(path, "md5")
            except OSError as exc:
                raise VerificationError("ENA FASTQ output could not be verified") from exc
            if observed_bytes != item.get("expected_bytes") or observed_md5 != item.get("expected_md5"):
                raise VerificationError("ENA FASTQ size or MD5 verification failed: " + path.name)
            sha = checksum(path)
            if sha != item.get("sha256"):
                raise VerificationError("ENA FASTQ SHA256 changed during acquisition: " + path.name)
            verified.append({"name": path.name, "role": item["role"], "bytes": observed_bytes,
                             "md5": observed_md5, "sha256": sha})
        return {
            "verified": True, "provider": self.name, "files": verified,
            "integrity_method": "declared size and MD5; local SHA256",
        }


class NCBISraToolkitProvider:
    name = "ncbi_sra_toolkit"
    priority = 20
    mechanism = "NCBI SRA Toolkit prefetch, vdb-validate and fasterq-dump"
    availability_description = "Public SRR run accession and NCBI SRA Toolkit on PATH"
    integrity_description = "SRA VDB validation, FASTQ parsing/pair checks, output SHA256"
    documentation = NCBI_SRA_DOWNLOAD_DOCS

    def _tools(self):
        found = {name: shutil.which(name) for name in NCBI_TOOL_NAMES}
        missing = [name for name, path in found.items() if not path]
        if missing:
            raise DependencyMissingError(
                "NCBI SRA Toolkit dependency missing: " + ", ".join(missing)
            )
        return {name: str(Path(path).resolve()) for name, path in found.items()}

    def availability(self, context):
        if context.offline:
            raise RemoteUnavailableError("NCBI SRA acquisition is unavailable in offline mode")
        if not SRA_ACCESSION.fullmatch(context.accession):
            raise RecordUnavailableError(
                "The NCBI SRA fallback supports SRR run accessions only"
            )
        tools = self._tools()
        return {"available": True, "provider": self.name, "tools": sorted(tools)}

    def resolve(self, context):
        if not SRA_ACCESSION.fullmatch(context.accession):
            raise RecordUnavailableError(
                "The NCBI SRA fallback supports SRR run accessions only"
            )
        if context.row.get("layout") not in {"SINGLE", "PAIRED"}:
            raise UnsupportedLayoutError("NCBI conversion supports SINGLE or PAIRED layout only")
        if context.max_bytes <= 0:
            raise DownloadBudgetExceededError("NCBI provider byte budget must be positive")
        return {"accession": context.accession, "layout": context.row["layout"],
                "tools": self._tools()}

    @staticmethod
    def _tool_versions(tools, directory):
        probe = directory / "tool_probe"
        probe.mkdir()
        result = {}
        for name, binary in tools.items():
            completed = run_captured(
                [binary, "--version"], probe, name + "_version.stdout",
                name + "_version.stderr", timeout=15, max_bytes=1_000_000,
            )
            if completed.returncode:
                raise ProviderExecutionError("Unable to inspect NCBI SRA Toolkit version: " + name)
            stdout = (probe / completed.stdout_name).read_text(encoding="utf-8", errors="replace").strip()
            stderr = (probe / completed.stderr_name).read_text(encoding="utf-8", errors="replace").strip()
            result[name] = {
                "path": binary, "sha256": checksum(binary),
                "version": stdout or stderr or "version_not_reported",
            }
        return result

    @staticmethod
    def _safe_archive(prefetch_dir, accession):
        if not prefetch_dir.exists():
            raise FileUnavailableError("NCBI prefetch produced no accession directory")
        if prefetch_dir.is_symlink() or not prefetch_dir.resolve().is_dir():
            raise VerificationError("NCBI prefetch directory is not a regular directory")
        matches = []
        for path in prefetch_dir.rglob("*.sra"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.name.casefold() == (accession + ".sra").casefold():
                if not path.resolve().is_relative_to(prefetch_dir.resolve()):
                    raise VerificationError("NCBI SRA archive escaped its provider directory")
                matches.append(path.resolve())
        if len(matches) != 1:
            raise FileUnavailableError(
                "NCBI prefetch did not produce exactly one archive for " + accession
            )
        return matches[0]

    @staticmethod
    def _process_error(log_path, exc, phase):
        if isinstance(exc, TimeoutError):
            raise exc
        if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
            raise exc
        if isinstance(exc, ValueError) and "byte budget" in str(exc).lower():
            raise DownloadBudgetExceededError(str(exc)) from exc
        if isinstance(exc, RuntimeError):
            text = ""
            if log_path.exists():
                text = log_path.read_text(encoding="utf-8", errors="replace").lower()
            if any(token in text for token in ("size limit", "max-size", "maximum size",
                                                "download limit", "maximum file size")):
                raise DownloadBudgetExceededError(
                    "NCBI SRA transfer reached the configured archive size limit"
                ) from exc
            if any(token in text for token in ("failed to resolve accession", "accession not found",
                                                "cannot resolve accession", "not found in the database")):
                raise RecordUnavailableError("NCBI could not resolve the requested SRA accession") from exc
            if any(token in text for token in ("connection failed", "network", "timed out",
                                                "failed to connect", "http 5")):
                raise RemoteUnavailableError("NCBI SRA remote retrieval failed") from exc
            if phase == "conversion":
                raise ConversionFailureError("NCBI SRA FASTQ conversion failed") from exc
            raise ProviderExecutionError("NCBI SRA " + phase + " command failed") from exc
        raise exc

    @staticmethod
    def _plain_fastq_records(path):
        with Path(path).open("rt", encoding="ascii", newline="") as handle:
            index = 0
            while True:
                header = handle.readline()
                if not header:
                    return
                sequence, plus, quality = (handle.readline() for _ in range(3))
                index += 1
                header, sequence, plus, quality = (
                    line.rstrip("\r\n") for line in (header, sequence, plus, quality)
                )
                if not header.startswith("@") or len(header) < 2 or not plus.startswith("+"):
                    raise ValueError(f"Malformed FASTQ record {index} in {Path(path).name}")
                sequence = sequence.upper()
                if not sequence or len(sequence) != len(quality) or len(sequence) > 10_000:
                    raise ValueError(f"Invalid FASTQ lengths at record {index} in {Path(path).name}")
                if set(sequence) - set("ACGTN") or any(not 33 <= ord(char) <= 126 for char in quality):
                    raise ValueError(f"Unsupported base or Phred+33 encoding at record {index}")
                if plus[1:] and plus[1:].split()[0] != header[1:].split()[0]:
                    raise ValueError(f"FASTQ separator identifier mismatch at record {index}")
                yield header, sequence, quality

    @staticmethod
    def _fastq_outputs(fastq_dir, accession, layout):
        allowed = {
            accession + ".fastq": "single",
            accession + "_1.fastq": "R1",
            accession + "_2.fastq": "R2",
        }
        outputs = []
        for path in sorted(fastq_dir.iterdir()):
            if path.name not in allowed or path.is_symlink() or not path.is_file():
                raise UnsupportedLayoutError("NCBI fasterq-dump produced an unsupported FASTQ filename")
            if not path.resolve().is_relative_to(fastq_dir.resolve()):
                raise VerificationError("NCBI FASTQ output escaped its provider directory")
            try:
                count = sum(1 for _ in NCBISraToolkitProvider._plain_fastq_records(path))
            except (OSError, ValueError) as exc:
                raise ConversionFailureError("NCBI FASTQ output failed syntax validation") from exc
            if count == 0:
                raise ConversionFailureError("NCBI fasterq-dump produced an empty FASTQ file")
            outputs.append({"role": allowed[path.name], "plain_path": path, "reads": count})
        roles = {row["role"] for row in outputs}
        if layout == "SINGLE" and roles != {"single"}:
            raise UnsupportedLayoutError("NCBI output files do not match the declared SINGLE layout")
        if layout == "PAIRED" and not {"R1", "R2"}.issubset(roles):
            raise UnsupportedLayoutError("NCBI output has no complete R1/R2 pair")
        if not outputs:
            raise ConversionFailureError("NCBI fasterq-dump produced no FASTQ records")
        by_role = {row["role"]: row for row in outputs}
        if {"R1", "R2"}.issubset(by_role):
            if by_role["R1"]["reads"] != by_role["R2"]["reads"]:
                raise VerificationError("NCBI paired FASTQ record counts disagree")
            from itertools import zip_longest
            try:
                for first, second in zip_longest(
                    NCBISraToolkitProvider._plain_fastq_records(by_role["R1"]["plain_path"]),
                    NCBISraToolkitProvider._plain_fastq_records(by_role["R2"]["plain_path"]),
                ):
                    if first is None or second is None or pair_id(first[0]) != pair_id(second[0]):
                        raise VerificationError("NCBI paired FASTQ identifiers disagree")
                    check_mate(first[0], "1")
                    check_mate(second[0], "2")
            except (OSError, ValueError, EOFError) as exc:
                if isinstance(exc, VerificationError):
                    raise
                raise ConversionFailureError("NCBI paired FASTQ validation failed") from exc
        return outputs

    def _load_reusable(self, root, context):
        engine_sha = checksum(Path(__file__))
        for attempt_dir in sorted(root.glob("attempt_*"), reverse=True):
            state_path = attempt_dir / "ncbi_acquisition.json"
            if not state_path.exists():
                continue
            if state_path.is_symlink() or not state_path.is_file():
                raise VerificationError("Cached NCBI acquisition manifest is not a regular file")
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    raise VerificationError("Cached NCBI acquisition metadata is malformed")
                if state.get("status") != "complete":
                    continue
                if state.get("accession") != context.accession:
                    raise VerificationError("Cached NCBI acquisition belongs to another accession")
                if state.get("engine_sha256") != engine_sha:
                    continue
                archive = attempt_dir / state["archive"]["path"]
                files = [{
                    **item,
                    "path": str(attempt_dir / item["path"]),
                } for item in state["files"]]
                artifact = {
                    "provider": self.name, "accession": context.accession,
                    "layout": state["layout"], "attempt_directory": str(attempt_dir),
                    "archive_path": str(archive),
                    "archive_bytes": state["archive"]["bytes"],
                    "archive_sha256": state["archive"]["sha256"],
                    "vdb_validate_exit_code": state["archive"]["vdb_validate_exit_code"],
                    "tool_versions": state["tool_versions"], "files": files,
                    "provenance": state["provenance"],
                }
                self.verify(artifact, context)
                return artifact
            except VerificationError:
                raise
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise VerificationError("Cached NCBI acquisition metadata is invalid") from exc
        return None

    def acquire(self, context):
        resolved = self.resolve(context)
        root = context.directory / "raw" / self.name
        root.mkdir(parents=True, exist_ok=True)
        reused = self._load_reusable(root, context)
        if reused:
            return reused
        existing = [int(match.group(1)) for path in root.iterdir()
                    if path.is_dir() and (match := re.fullmatch(r"attempt_(\d{3,})", path.name))]
        attempt_dir = root / f"attempt_{max(existing, default=0) + 1:03d}"
        attempt_dir.mkdir()
        tool_versions = self._tool_versions(resolved["tools"], attempt_dir)
        prefetch_dir = attempt_dir / "prefetch"
        prefetch_dir.mkdir()
        max_kilobytes = context.max_bytes // 1024
        if max_kilobytes < 1:
            raise DownloadBudgetExceededError("NCBI archive budget is below 1 KiB")
        prefetch_cap = context.max_bytes + NCBI_WORKSPACE_OVERHEAD_BYTES
        prefetch_command = [
            resolved["tools"]["prefetch"], context.accession,
            "--max-size", f"{max_kilobytes}k",
        ]
        try:
            run_process(prefetch_command, prefetch_dir, "prefetch.log",
                        timeout=NCBI_TOOL_TIMEOUT_SECONDS, max_bytes=prefetch_cap)
        except BaseException as exc:
            self._process_error(prefetch_dir / "prefetch.log", exc, "prefetch")
        archive = self._safe_archive(prefetch_dir, context.accession)
        archive_bytes = archive.stat().st_size
        if archive_bytes <= 0 or archive_bytes > context.max_bytes:
            raise DownloadBudgetExceededError(
                f"NCBI SRA archive size {archive_bytes} exceeds the {context.max_bytes}-byte run budget"
            )
        workspace_bytes = archive_bytes * 20 + NCBI_WORKSPACE_OVERHEAD_BYTES
        if workspace_bytes > MAX_NCBI_WORKSPACE_BYTES:
            raise DownloadBudgetExceededError(
                "NCBI conversion workspace exceeds the fixed 20 GiB provider cap"
            )
        if shutil.disk_usage(attempt_dir).free < workspace_bytes:
            raise OSError(28, f"NCBI conversion needs {workspace_bytes:,} bytes of free disk space")
        validate_command = [resolved["tools"]["vdb-validate"], str(archive)]
        try:
            run_process(validate_command, attempt_dir, "vdb-validate.log",
                        timeout=300, max_bytes=workspace_bytes)
        except BaseException as exc:
            if isinstance(exc, (TimeoutError, OSError)) and getattr(exc, "errno", None) == 28:
                raise
            if isinstance(exc, ValueError) and "byte budget" in str(exc).lower():
                raise DownloadBudgetExceededError(str(exc)) from exc
            raise VerificationError("NCBI SRA archive failed vdb-validate") from exc

        fastq_dir = attempt_dir / "fastq"
        temp_dir = attempt_dir / "temporary"
        fastq_dir.mkdir()
        temp_dir.mkdir()
        command = [
            resolved["tools"]["fasterq-dump"], str(archive), "--split-3",
            "--threads", "1", "--outdir", str(fastq_dir), "--temp", str(temp_dir),
            "--force",
        ]
        write_json(attempt_dir / "commands.json", {
            "prefetch": prefetch_command,
            "vdb_validate": validate_command,
            "fasterq_dump": command,
            "tool_versions": tool_versions,
            "archive_sha256": checksum(archive),
            "archive_bytes": archive_bytes,
            "max_fastq_bytes": context.max_bytes,
            "workspace_cap_bytes": workspace_bytes,
        })
        try:
            run_process(command, attempt_dir, "fasterq-dump.log",
                        timeout=NCBI_TOOL_TIMEOUT_SECONDS, max_bytes=workspace_bytes)
        except BaseException as exc:
            self._process_error(attempt_dir / "fasterq-dump.log", exc, "conversion")
        for name, info in tool_versions.items():
            if checksum(info["path"]) != info["sha256"]:
                raise VerificationError("NCBI SRA Toolkit executable changed during acquisition: " + name)
        outputs = self._fastq_outputs(fastq_dir, context.accession, resolved["layout"])
        files = []
        total_compressed = 0
        for item in outputs:
            plain = item["plain_path"]
            compressed = plain.with_suffix(plain.suffix + ".gz")
            with plain.open("rb") as source, compressed.open("wb") as raw_dest:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw_dest, mtime=0) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            size = compressed.stat().st_size
            total_compressed += size
            files.append({
                "role": item["role"], "name": compressed.name,
                "path": str(compressed.resolve()), "bytes": size,
                "sha256": checksum(compressed), "reads": item["reads"],
                "expected_md5": None,
            })
        if total_compressed > context.max_bytes:
            raise DownloadBudgetExceededError(
                f"NCBI FASTQ output needs {total_compressed} bytes but the run budget is "
                f"{context.max_bytes} bytes"
            )
        for item in outputs:
            item["plain_path"].unlink()
        if temp_dir.exists():
            if (temp_dir.is_symlink() or not temp_dir.resolve().is_relative_to(attempt_dir.resolve())
                    or any(path.is_symlink() or not path.resolve().is_relative_to(temp_dir.resolve())
                           for path in temp_dir.rglob("*"))):
                raise VerificationError("NCBI temporary conversion directory redirects outside its stage")
            shutil.rmtree(temp_dir)
        archive_relative = archive.relative_to(attempt_dir).as_posix()
        file_state = [{
            **{key: item[key] for key in ("role", "name", "bytes", "sha256", "reads", "expected_md5")},
            "path": (Path("fastq") / item["name"]).as_posix(),
        } for item in files]
        provenance = {
            "source": "NCBI Sequence Read Archive",
            "accession": context.accession,
            "retrieval_method": "SRA Toolkit prefetch, vdb-validate, fasterq-dump --split-3",
            "documentation": [self.documentation, NCBI_SRA_TOOLKIT_DOCS],
            "verification_method": [
                "vdb-validate returned success",
                "FASTQ syntax and nonempty records",
                "paired read counts, identifiers and mate orientation where paired",
                "local SHA256 of each converted FASTQ",
            ],
            "provider_supplied_fastq_checksum": None,
        }
        state = {
            "status": "complete", "provider": self.name, "accession": context.accession,
            "layout": resolved["layout"], "engine_sha256": checksum(Path(__file__)),
            "tool_versions": tool_versions,
            "archive": {"path": archive_relative, "bytes": archive_bytes,
                        "sha256": checksum(archive), "vdb_validate_exit_code": 0},
            "files": file_state, "provenance": provenance,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
        }
        write_json(attempt_dir / "ncbi_acquisition.json", state)
        artifact = {
            "provider": self.name, "accession": context.accession,
            "layout": resolved["layout"], "attempt_directory": str(attempt_dir.resolve()),
            "archive_path": str(archive.resolve()), "archive_bytes": archive_bytes,
            "archive_sha256": state["archive"]["sha256"], "vdb_validate_exit_code": 0,
            "tool_versions": tool_versions, "files": files, "provenance": provenance,
        }
        return artifact

    def verify(self, artifact, context):
        if artifact.get("provider") != self.name or artifact.get("accession") != context.accession:
            raise VerificationError("NCBI artifact provider or accession mismatch")
        if artifact.get("layout") != context.row.get("layout"):
            raise VerificationError("NCBI artifact layout differs from NCBI run metadata")
        if artifact.get("vdb_validate_exit_code") != 0:
            raise VerificationError("NCBI SRA archive has not passed vdb-validate")
        raw_directory = Path(artifact.get("attempt_directory", ""))
        raw_archive = Path(artifact.get("archive_path", ""))
        if raw_directory.is_symlink() or raw_archive.is_symlink():
            raise VerificationError("NCBI acquisition path contains a symbolic link")
        try:
            directory = raw_directory.resolve(strict=True)
            archive = raw_archive.resolve(strict=True)
        except OSError as exc:
            raise VerificationError("NCBI SRA archive or acquisition directory is missing") from exc
        try:
            archive_matches = (
                archive.is_relative_to(directory) and archive.is_file()
                and archive.stat().st_size == artifact.get("archive_bytes")
                and checksum(archive) == artifact.get("archive_sha256")
            )
        except OSError as exc:
            raise VerificationError("NCBI SRA archive could not be verified") from exc
        if not archive_matches:
            raise VerificationError("NCBI SRA archive changed after validation")
        tool_versions = artifact.get("tool_versions")
        if (not isinstance(tool_versions, dict) or set(tool_versions) != set(NCBI_TOOL_NAMES)
                or any(not isinstance(value, dict)
                       or not isinstance(value.get("path"), str)
                       or not isinstance(value.get("sha256"), str)
                       or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                       or not isinstance(value.get("version"), str)
                       for value in tool_versions.values())):
            raise VerificationError("NCBI Toolkit provenance is incomplete")
        files = artifact.get("files")
        if not isinstance(files, list) or not files:
            raise VerificationError("NCBI provider returned no FASTQ files")
        if any(not isinstance(item, dict) for item in files):
            raise VerificationError("NCBI provider returned malformed FASTQ metadata")
        roles = [item.get("role") for item in files]
        if any(not isinstance(role, str) for role in roles):
            raise VerificationError("NCBI provider returned malformed FASTQ roles")
        if len(roles) != len(set(roles)):
            raise VerificationError("NCBI provider returned duplicate FASTQ roles")
        expected_names = {
            "single": context.accession + ".fastq.gz",
            "R1": context.accession + "_1.fastq.gz",
            "R2": context.accession + "_2.fastq.gz",
        }
        if set(roles) - set(expected_names):
            raise VerificationError("NCBI provider returned an unsupported FASTQ role")
        if context.row.get("layout") == "SINGLE" and roles != ["single"]:
            raise VerificationError("NCBI single-end result has unexpected FASTQ roles")
        if context.row.get("layout") == "PAIRED" and not {"R1", "R2"}.issubset(roles):
            raise VerificationError("NCBI paired result is missing a mate")
        total_bytes = 0
        verified_files = []
        by_role = {}
        for item in files:
            raw_path = Path(item.get("path", ""))
            if raw_path.is_symlink():
                raise VerificationError("NCBI FASTQ output is a symbolic link")
            try:
                path = raw_path.resolve(strict=True)
                if not path.is_relative_to(directory) or not path.is_file():
                    raise VerificationError("NCBI FASTQ output path is invalid")
                if path.name != expected_names.get(item.get("role")) or path.name != item.get("name"):
                    raise VerificationError("NCBI FASTQ output filename does not match its role")
            except OSError as exc:
                raise VerificationError("NCBI FASTQ output is missing or unreadable") from exc
            if path.name != item.get("name"):
                raise VerificationError("NCBI FASTQ output path is invalid")
            try:
                size = path.stat().st_size
                digest = checksum(path)
                reads = sum(1 for _ in fastq_records(path))
            except (OSError, ValueError, EOFError) as exc:
                raise VerificationError("NCBI FASTQ output failed integrity or syntax validation") from exc
            if size != item.get("bytes") or digest != item.get("sha256"):
                raise VerificationError("NCBI FASTQ output failed size or SHA256 verification")
            if reads != item.get("reads") or reads == 0:
                raise VerificationError("NCBI FASTQ output changed or contains no reads")
            total_bytes += size
            by_role[item["role"]] = (path, reads)
            verified_files.append({"role": item["role"], "name": path.name,
                                   "bytes": size, "sha256": item["sha256"],
                                   "reads": reads, "provider_md5": None})
        if total_bytes > context.max_bytes:
            raise DownloadBudgetExceededError("NCBI FASTQ output exceeds its reserved byte budget")
        if {"R1", "R2"}.issubset(by_role):
            if by_role["R1"][1] != by_role["R2"][1]:
                raise VerificationError("NCBI paired FASTQ record counts disagree")
            from itertools import zip_longest
            try:
                for first, second in zip_longest(
                    fastq_records(by_role["R1"][0]), fastq_records(by_role["R2"][0])
                ):
                    if (first is None or second is None
                            or pair_id(first[0]) != pair_id(second[0])):
                        raise VerificationError("NCBI paired FASTQ identifiers disagree")
                    check_mate(first[0], "1")
                    check_mate(second[0], "2")
            except (OSError, ValueError, EOFError) as exc:
                if isinstance(exc, VerificationError):
                    raise
                raise VerificationError("NCBI paired FASTQ validation failed") from exc
        return {
            "verified": True, "provider": self.name, "files": verified_files,
            "archive_sha256": artifact["archive_sha256"],
            "integrity_method": "vdb-validate plus FASTQ syntax/pair checks and local SHA256",
        }


def default_provider_registry():
    registry = ProviderRegistry()
    registry.register(ENAFastqProvider())
    registry.register(NCBISraToolkitProvider())
    return registry