"""Trusted M6 residual-read evidence workflow.

This adapter deliberately records reconstruction evidence, not biological
classifications.  The only external program invoked directly is the declared
minimap2 executable; assembly is delegated to the existing trusted assembly
router.
"""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from urllib.parse import quote

from . import artifact_contracts, bounded_process, residual_reads, read_support
from .assembly_adapters import AssemblyWorkflowAdapter
from .sequence_catalogue import read_fasta
from .m8_candidate_handoff import fasta_record_metadata
from .external_tool import (
    DependencyMissingError, ExternalToolAdapter, ExternalToolExitError,
)
from .sequence_downloader import checksum, write_json


_SAFE_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_TRIAGE_DEFAULTS = {
    "min_read_length": 50, "max_ambiguous_fraction": .05,
    "min_entropy_bits": 1.2, "min_mean_phred": 20,
}
_SUPPORT_DEFAULTS = {
    "min_mapq": 20, "min_alignment_fraction": .8,
    "min_sequence_identity": .95, "min_coverage_breadth": .8,
    "min_mean_depth": 2, "min_distinct_fragments": 2,
    "coverage_window_size": 100,
}
_ROOT_OUTPUTS = (
    "reference_screen.sam", "residual_read1.fastq.gz", "residual_read2.fastq.gz",
    "eligible_read1.fastq.gz", "eligible_read2.fastq.gz",
    "retained_unassembled_read1.fastq.gz", "retained_unassembled_read2.fastq.gz",
    "unresolved_read1.fastq.gz", "unresolved_read2.fastq.gz",
    "read_triage.csv", "support_alignments.sam", "read_support.csv",
    "read_support.json", "residual_manifest.json", "reconstruction_evidence.json",
    "candidate_sequence_set.json",
)


def _digest_file(path):
    return checksum(path)


def _empty_gzip(path):
    with Path(path).open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0):
            pass


def _copy_selected_fastq(source, destination, selected, paired=False, mate=None):
    """Copy exact original FASTQ records selected by stable m6r IDs."""
    wanted = set(selected)
    with Path(destination).open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as out:
            for index, row in enumerate(residual_reads._records(source), 1):
                if residual_reads._qname(index) in wanted:
                    out.write(row[4].encode("ascii"))


def _write_support_csv(path, rows):
    fields = (
        "query_id", "mate", "contig_id", "mapq", "query_aligned_bases",
        "reference_aligned_bases", "aligned_query_fraction",
        "sequence_identity", "qualifying",
    )
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


class ResidualEvidenceAdapter(ExternalToolAdapter):
    """Completion-accounted residual screening, optional assembly, and support."""

    kind = "residual_evidence"
    module_name = "residual_evidence"
    adapter_name = "minimap2-residual-evidence"
    adapter_version = "1.1"
    tool_name = "minimap2 short-read residual screening"
    input_fields = frozenset({"read1", "reference", "roles", "qc_manifest"})
    optional_input_fields = frozenset({"read2", "dvg_evidence", "dvg_summary"})
    input_contracts = {
        "read1": "qc_fastq", "read2": "qc_fastq",
        "reference": "raw_fasta", "roles": "reference_roles",
        "qc_manifest": "qc_manifest", "dvg_evidence": "dvg_evidence",
        "dvg_summary": "dvg_evidence_summary",
    }
    output_contracts = {
        name: (
            "m8_candidate_sequence_set" if name == "candidate_sequence_set.json"
            else "residual_read_manifest" if name == "residual_manifest.json"
            else "reconstruction_evidence" if name == "reconstruction_evidence.json"
            else "read_alignment_sam" if name in {"reference_screen.sam", "support_alignments.sam"}
            else "residual_fastq" if name.startswith("residual_")
            else "eligible_residual_fastq" if name.startswith("eligible_")
            else "retained_unassembled_fastq" if name.startswith("retained_")
            else "unresolved_residual_fastq" if name.startswith("unresolved_")
            else "read_triage_table" if name == "read_triage.csv"
            else "read_support_table" if name == "read_support.csv"
            else "read_support_evidence" if name == "read_support.json"
            else "residual_read_manifest" if name == "residual_manifest.json"
            else "reconstruction_evidence" if name == "reconstruction_evidence.json"
            else "canonical_contig_fasta"
        )
        for name in _ROOT_OUTPUTS
    }
    output_contracts["supported_contigs.fasta"] = "canonical_contig_fasta"
    output_contracts["candidate_sequences.fasta"] = "canonical_contig_fasta"

    def __init__(self, *, assembly_adapter=None, timeout=180,
                 max_bytes=400_000_000):
        super().__init__(
            kind=self.kind, module_name=self.module_name,
            adapter_name=self.adapter_name, adapter_version=self.adapter_version,
            tool_name=self.tool_name,
            dependencies=({"name": "minimap2", "command": "minimap2",
                           "version_args": ["--version"]},),
            input_fields=self.input_fields, optional_input_fields=self.optional_input_fields,
            output_files=_ROOT_OUTPUTS, timeout=timeout, max_bytes=max_bytes,
            stdout_name="minimap2.stdout.log", stderr_name="minimap2.stderr.log",
            description="Conservative residual-read evidence generation.",
        )
        self.assembly_adapter = assembly_adapter or AssemblyWorkflowAdapter()

    def validate_config(self, config):
        if not isinstance(config, dict):
            raise ValueError("Residual evidence config must be an object")
        allowed = {"sample_id", "layout", "assembly_enabled", "assembler",
                   "threads", "memory_mb", "triage", "support", "assembly"}
        if set(config) - allowed:
            raise ValueError("Residual evidence config contains unsupported fields")
        sample_id = config.get("sample_id")
        if not isinstance(sample_id, str) or not _SAFE_TEXT.fullmatch(sample_id):
            raise ValueError("sample_id must be bounded safe text")
        layout = config.get("layout", "single-end")
        if layout not in {"single-end", "paired-end"}:
            raise ValueError("layout must be single-end or paired-end")
        enabled = config.get("assembly_enabled", True)
        if type(enabled) is not bool:
            raise ValueError("assembly_enabled must be boolean")
        assembler = config.get("assembler", "tadpole")
        if not isinstance(assembler, str) or assembler not in {"spades", "tadpole"}:
            raise ValueError("assembler must be spades or tadpole")
        threads = config.get("threads", 1)
        memory = config.get("memory_mb", 2048)
        if type(threads) is not int or not 1 <= threads <= 8:
            raise ValueError("threads must be an integer from 1 through 8")
        if type(memory) is not int or not 256 <= memory <= 16384:
            raise ValueError("memory_mb must be an integer from 256 through 16384")
        triage = self._numeric_config(config.get("triage", {}), _TRIAGE_DEFAULTS, "triage")
        support = self._numeric_config(config.get("support", {}), _SUPPORT_DEFAULTS, "support")
        # Validate through the trusted router before any execution.
        assembly = self.assembly_adapter.validate_config({
            "assembler": assembler, "layout": layout,
            "threads": threads, "memory_mb": memory,
        })
        if "assembly" in config and config["assembly"] != assembly:
            raise ValueError("Normalized assembly configuration changed")
        return {
            "sample_id": sample_id, "layout": layout,
            "assembly_enabled": enabled, "assembler": assembler,
            "threads": threads, "memory_mb": memory,
            "triage": triage, "support": support, "assembly": assembly,
        }

    @staticmethod
    def _numeric_config(value, defaults, name):
        if not isinstance(value, dict) or set(value) - set(defaults):
            raise ValueError(f"{name} configuration contains unsupported fields")
        result = dict(defaults)
        result.update(value)
        for key, item in result.items():
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError(f"{name}.{key} must be finite and numeric")
        if name == "triage" and (
            type(result["min_read_length"]) is not int or result["min_read_length"] < 1
            or not 0 <= result["max_ambiguous_fraction"] <= 1
            or result["min_entropy_bits"] < 0 or not 0 <= result["min_mean_phred"] <= 93
        ):
            raise ValueError("Invalid triage thresholds")
        if name == "support" and (
            type(result["min_mapq"]) is not int or not 0 <= result["min_mapq"] <= 255
            or not 0 <= result["min_alignment_fraction"] <= 1
            or not 0 <= result["min_sequence_identity"] <= 1
            or not 0 <= result["min_coverage_breadth"] <= 1
            or result["min_mean_depth"] < 0 or type(result["min_distinct_fragments"]) is not int
            or result["min_distinct_fragments"] < 1
            or type(result["coverage_window_size"]) is not int
            or result["coverage_window_size"] < 1
        ):
            raise ValueError("Invalid support thresholds")
        return result

    def validate_configured_inputs(self, inputs, output, config):
        paths = self.validate_inputs(inputs, output, config)
        paired = config["layout"] == "paired-end"
        if paired != ("read2" in paths):
            raise ValueError("Declared layout does not match read mates")
        artifact_contracts.validate_artifact(paths["qc_manifest"], "qc_manifest")
        artifact_contracts.validate_artifact(paths["roles"], "reference_roles")
        manifest = json.loads(Path(paths["qc_manifest"]).read_text(encoding="utf-8"))
        outputs = manifest["output_sha256"]
        roles = ("R1", "R2") if paired else ("single",)
        names = ("clean_R1.fastq.gz", "clean_R2.fastq.gz") if paired else ("clean_single.fastq.gz",)
        for role, name in zip(roles, names):
            if _digest_file(paths["read1" if role in {"R1", "single"} else "read2"]) != outputs[name]:
                raise ValueError(f"Declared {role} input is not the exact QC output")
        records = read_fasta(paths["reference"])
        if not records or len({row[0] for row in records}) != len(records):
            raise ValueError("Reference FASTA contains no records")
        role_ids = set()
        with Path(paths["roles"]).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "reference_id" not in reader.fieldnames:
                raise ValueError("Reference roles must declare reference_id")
            for row in reader:
                role_ids.add(row["reference_id"])
        fasta_ids = {row[0] for row in records}
        if role_ids != fasta_ids:
            raise ValueError("Reference FASTA IDs and roles IDs do not match exactly")
        if "dvg_evidence" in paths:
            artifact_contracts.validate_artifact(paths["dvg_evidence"], "dvg_evidence")
        if "dvg_summary" in paths:
            artifact_contracts.validate_artifact(paths["dvg_summary"], "dvg_evidence_summary")
        if "dvg_evidence" in paths and "dvg_summary" in paths:
            evidence = json.loads(Path(paths["dvg_evidence"]).read_text(encoding="utf-8"))
            summary = json.loads(Path(paths["dvg_summary"]).read_text(encoding="utf-8"))
            if (evidence["status"] != summary["status"]
                    or len(evidence["events"]) != summary["event_count"]):
                raise ValueError("DVG evidence and summary status/count do not agree")
        return paths

    def inspect_dependency_for_config(self, config):
        report = self.inspect_dependency()
        if config.get("assembly_enabled", True):
            selected = self.assembly_adapter.inspect_dependency_for_config(config["assembly"])
            report["assembly"] = selected
        return report

    def build_command(self, executables, inputs, output, config):
        return [executables["minimap2"], "-a", "-x", "sr", "--secondary=no",
                "-t", str(config["threads"]), "-o",
                str(Path(output) / "reference_screen.sam"),
                str(inputs["reference"]),
                str(Path(output) / ".m6-work" / "normalized" / "screen_R1.fastq.gz")] + (
                    [str(Path(output) / ".m6-work" / "normalized" / "screen_R2.fastq.gz")]
                    if "read2" in inputs else [])

    def _identity(self, config, inputs, dependency, command, environment, context=None):
        identity = super()._identity(config, inputs, dependency, command, environment, context)
        identity["implementation_sha256"] = {
            name: checksum(Path(__file__).with_name(name))
            for name in (
                "residual_evidence_adapter.py", "residual_reads.py",
                "read_support.py", "quality_control.py", "artifact_contracts.py",
                "external_tool.py", "assembly_adapters.py",
            )
        }
        identity["assembler"] = config["assembly"]
        identity["optional_assembler_dependency"] = dependency.get("assembly")
        return identity

    def cache_implementation_identity(self):
        """Keep M6 reuse scoped to code that can change its own artifacts."""
        source_files = (
            "residual_evidence_adapter.py", "residual_reads.py",
            "read_support.py", "quality_control.py", "artifact_contracts.py",
            "sequence_catalogue.py", "external_tool.py", "bounded_process.py",
            "assembly_adapters.py",
            "m8_candidate_handoff.py",
        )
        return {
            "stage": "m6-residual-evidence",
            "adapter_version": self.adapter_version,
            "implementation_sha256": {
                name: checksum(Path(__file__).with_name(name))
                for name in source_files
            },
        }

    def _run_mapper(self, executable, reference, reads, output, config):
        command = [executable, "-a", "-x", "sr", "--secondary=no", "-t",
                   str(config["threads"]), "-o", str(output), str(reference),
                   str(reads[0])]
        if len(reads) == 2:
            command.append(str(reads[1]))
        result = bounded_process.run_captured(
            command, Path(output).parent, "mapper.stdout.log", "mapper.stderr.log",
            timeout=self.timeout, max_bytes=self.max_bytes,
        )
        if result.returncode:
            raise ExternalToolExitError(result.returncode, "mapper.stderr.log")

    def _write_placeholders(self, output):
        for name in _ROOT_OUTPUTS:
            path = Path(output) / name
            if not path.exists():
                if name.endswith(".fastq.gz"):
                    _empty_gzip(path)
                elif name.endswith(".csv"):
                    if name == "read_triage.csv":
                        path.write_text(
                            "query_id,mate,outcome,residual,length,ambiguous_fraction,"
                            "entropy,mean_phred,sequence_hash,exact_duplicate_count,reason_codes\n",
                            encoding="utf-8")
                    else:
                        _write_support_csv(path, [])
                elif name.endswith(".sam"):
                    path.write_text("@HD\tVN:1.6\n", encoding="ascii")

    def prepare_execution(self, output, inputs, config, manifest):
        work = Path(output) / ".m6-work"
        residual_reads.prepare_normalized_fastqs(
            inputs["read1"], inputs.get("read2"), work / "normalized")

    def finalize_outputs(self, output, config, process_result, manifest):
        output = Path(output)
        inputs = {name: Path(row["path"]) for name, row in manifest["inputs"].items()}
        paired = config["layout"] == "paired-end"
        work = output / ".m6-work"
        triage = residual_reads.screen_and_triage(
            inputs["read1"], inputs.get("read2"), output / "reference_screen.sam",
            work / "triage", config=config["triage"], paired=paired,
            references={row[0]: len(row[2]) for row in read_fasta(inputs["reference"])})
        for name in ("residual_read1.fastq.gz", "residual_read2.fastq.gz",
                     "eligible_read1.fastq.gz", "eligible_read2.fastq.gz",
                     "retained_unassembled_read1.fastq.gz",
                     "retained_unassembled_read2.fastq.gz"):
            source = work / "triage" / name
            if source.exists():
                shutil.copyfile(source, output / name)
        residual_ids = triage["residual_fragment_ids"]
        eligible_ids = set(triage["eligible_fragment_ids"])
        support_result = {
            "schema": "m6-read-support-v1", "status": "NOT_EVALUATED",
            "contigs": [], "read_support": [], "resolved_fragment_ids": [],
            "configuration": config["support"],
            "provenance": {"reference_sha256": _digest_file(inputs["reference"])}
        }
        status = "ASSEMBLY_NOT_ATTEMPTED"
        assembly_info = {}
        candidate_record_metadata = []
        candidate_source_path = None
        candidate_source_identity = None
        candidate_unavailable_reason = "ASSEMBLY_NOT_ATTEMPTED"
        candidate_availability_state = "UPSTREAM_UNAVAILABLE"
        if config["assembly_enabled"] and eligible_ids:
            assembly_dir = output / "assembly"
            assembly_inputs = {"read1": work / "triage" / "eligible_read1.fastq.gz"}
            if paired:
                assembly_inputs["read2"] = work / "triage" / "eligible_read2.fastq.gz"
            try:
                assembly_execution = self.assembly_adapter.execute(
                    assembly_inputs, assembly_dir, config["assembly"],
                    context={"stage_id": manifest.get("stage_id")})
            except DependencyMissingError:
                status = "DEPENDENCY_UNAVAILABLE"
                candidate_unavailable_reason = "DEPENDENCY_UNAVAILABLE"
            except ExternalToolExitError:
                status = "EXECUTION_FAILED"
                candidate_unavailable_reason = "EXECUTION_FAILED"
            except (KeyboardInterrupt, SystemExit):
                raise
            except (OSError, ValueError):
                status = "INVALID_OUTPUT"
                candidate_availability_state = "INVALID_OUTPUT"
                candidate_unavailable_reason = "INVALID_ASSEMBLY_OUTPUT"
            else:
                contigs = assembly_dir / "contigs.fasta"
                assembly_manifest = assembly_dir / "assembly_manifest.json"
                if contigs.is_file() and not contigs.is_symlink():
                    candidate_source_identity = {
                        "path": "assembly/contigs.fasta",
                        "sha256": _digest_file(contigs),
                    }
                assembly_info = {
                    "assembler": config["assembler"], "assembly_path": "assembly/",
                    "manifest_sha256": _digest_file(assembly_manifest)
                    if assembly_manifest.exists() else None,
                }
                if assembly_execution is not None:
                    assembly_info["adapter"] = getattr(assembly_execution, "adapter", None)
                    assembly_info["tool"] = getattr(assembly_execution, "tool", None)
                if assembly_manifest.exists():
                    try:
                        assembly_record = json.loads(
                            assembly_manifest.read_text(encoding="utf-8"))
                        assembly_info.update({
                            "version": assembly_record.get("external_tool_version"),
                            "configuration": assembly_record.get("parameters", config["assembly"]),
                        })
                    except (OSError, ValueError):
                        assembly_info["version"] = None
                try:
                    if contigs.is_symlink():
                        raise ValueError("assembly contig FASTA must not be a symlink")
                    artifact_contracts.validate_artifact(
                        contigs, "canonical_contig_fasta")
                    candidate_record_metadata = fasta_record_metadata(contigs)
                    shutil.copyfile(contigs, output / "candidate_sequences.fasta")
                    candidate_source_path = contigs
                    candidate_availability_state = "AVAILABLE"
                    candidate_unavailable_reason = None
                except (OSError, ValueError):
                    status = "INVALID_OUTPUT"
                    candidate_availability_state = "INVALID_OUTPUT"
                    candidate_unavailable_reason = "INVALID_ASSEMBLY_SEQUENCE_BYTES"
                    candidate_record_metadata = []
                    (output / "candidate_sequences.fasta").unlink(missing_ok=True)

                if candidate_source_path is not None:
                    normalized = residual_reads.prepare_normalized_fastqs(
                        inputs["read1"], inputs.get("read2"),
                        work / "support-normalized",
                        include_fragment_ids=triage["eligible_fragment_ids"])
                    support_reads = [normalized["read1"]]
                    if paired:
                        support_reads.append(normalized["read2"])
                    support_metadata = {
                        key: value for key, value in triage["read_metadata"].items()
                        if key[0] in eligible_ids
                    }
                    try:
                        self._run_mapper(
                            manifest["dependency_report"]["dependencies"][0]["path"],
                            contigs, support_reads,
                            output / "support_alignments.sam", config)
                        support_result.update(read_support.assess_read_support(
                            output / "support_alignments.sam", contigs,
                            support_metadata, paired=paired,
                            thresholds=config["support"]))
                        status = support_result["status"]
                        if status == "READ_SUPPORTED_ASSEMBLY":
                            shutil.copyfile(contigs, output / "supported_contigs.fasta")
                    except ExternalToolExitError:
                        status = "READ_SUPPORT_FAILED"
                        support_result["status"] = status
                    except (ValueError, OSError):
                        status = "INVALID_SUPPORT_OUTPUT"
                        support_result["status"] = status
        elif config["assembly_enabled"]:
            status = "NO_SUPPORTED_ASSEMBLY"
            candidate_unavailable_reason = "NO_ELIGIBLE_READS_FOR_ASSEMBLY"
        else:
            candidate_unavailable_reason = "ASSEMBLY_DISABLED"
        resolved = set(support_result.get("resolved_fragment_ids", []))
        unresolved = set(residual_ids) - resolved
        for mate in (1, 2):
            destination = output / f"unresolved_read{mate}.fastq.gz"
            if paired and mate == 2:
                _copy_selected_fastq(inputs["read2"], destination, unresolved)
            elif mate == 1:
                _copy_selected_fastq(inputs["read1"], destination, unresolved)
            else:
                _empty_gzip(destination)
        _write_support_csv(output / "read_support.csv", support_result["read_support"])
        support_result["provenance"].update({
            "source_residual_ids": residual_ids,
            "support_input_fragment_ids": list(triage["eligible_fragment_ids"]),
            "support_sam_sha256": _digest_file(output / "support_alignments.sam")
            if (output / "support_alignments.sam").exists() else None})
        write_json(output / "read_support.json", support_result)
        self._write_placeholders(output)
        artifact_paths = {name: output / name for name in _ROOT_OUTPUTS
                          if (output / name).exists()}
        read_records = triage["counts"]["input_fragments"] * (2 if paired else 1)
        manifest_doc = {
            "schema": "m6-residual-manifest-v1", "status": "complete",
            "sample_id": config["sample_id"],
            "source_reads": {name: {"path": str(path), "sha256": _digest_file(path)}
                             for name, path in inputs.items() if name in {"read1", "read2"}},
            "qc_artifact": {"path": str(inputs["qc_manifest"]),
                            "sha256": _digest_file(inputs["qc_manifest"])},
            "comparison": {
                "status": "complete", "input_read_count": read_records,
                "accounted_read_count": read_records, "scope": "declared reference FASTA",
                "reference_sha256": _digest_file(inputs["reference"]),
                "reference_ids": sorted(row[0] for row in read_fasta(inputs["reference"])),
                "roles_sha256": _digest_file(inputs["roles"]),
                "tool": manifest["dependency_report"]["dependencies"][0],
                "parameters": ["-a", "-x", "sr", "--secondary=no",
                               "-t", str(config["threads"])],
            },
            "counts": triage["counts"], "triage_configuration": config["triage"],
            "artifact_sha256": {name: _digest_file(path)
                               for name, path in artifact_paths.items()},
        }
        write_json(output / "residual_manifest.json", manifest_doc)
        dvg = {"status": "NOT_EVALUATED"}
        for key in ("dvg_evidence", "dvg_summary"):
            if key in inputs:
                value = json.loads(inputs[key].read_text(encoding="utf-8"))
                if key == "dvg_evidence":
                    dvg_status = value["status"]
                    event_count = len(value["events"])
                else:
                    dvg_status = value["status"]
                    event_count = value["event_count"]
                dvg["status"] = dvg_status
                dvg[key] = {
                    "status": dvg_status, "event_count": event_count,
                    "sha256": _digest_file(inputs[key]),
                }
        write_json(output / "reconstruction_evidence.json", {
            "schema": "m6-reconstruction-evidence-v1", "status": status,
            "sample_id": config["sample_id"], "contigs": support_result["contigs"],
            "assembler": {**assembly_info, "configuration": config["assembly"]},
            "qc_artifact": str(inputs["qc_manifest"]),
            "reference_sha256": _digest_file(inputs["reference"]),
            "support_method": "minimap2 SAM read-back with strict read_support validation",
            "support_criteria": config["support"],
            "configuration": config,
            "provenance": {
                "reference_sha256": _digest_file(inputs["reference"]),
                "qc_sha256": _digest_file(inputs["qc_manifest"]),
                "residual_manifest": "residual_manifest.json",
            },
            "dvg_status": dvg,
            "limitations": [
                "Read support does not establish biological identity or novelty.",
                "Only triage-eligible residual fragments can support an assembly; retained-unassembled fragments remain unresolved.",
            ],
        })
        stage_id = manifest.get("stage_id")
        if not isinstance(stage_id, str) or not stage_id:
            stage_id = (
                f"standalone-{quote(config['sample_id'], safe='')}-"
                f"{_digest_file(inputs['read1'])[:16]}"
            )
        support_by_id = {
            row["contig_id"]: row.get("status", "NOT_EVALUATED")
            for row in support_result.get("contigs", [])
            if isinstance(row, dict) and isinstance(row.get("contig_id"), str)
        }
        candidate_rows = []
        source_hash = (
            candidate_source_identity["sha256"]
            if candidate_source_identity is not None else None
        )
        for metadata in candidate_record_metadata:
            fasta_id = metadata["fasta_record_id"]
            stage_token = quote(stage_id, safe="")
            record_token = quote(fasta_id, safe="")
            candidate_rows.append({
                "candidate_id": f"m6-candidate/{stage_token}/{record_token}",
                "sequence_id": f"m6-sequence/{stage_token}/{record_token}",
                "fasta_record_id": fasta_id,
                "sequence_sha256": metadata["sequence_sha256"],
                "sequence_length": metadata["sequence_length"],
                "sequence_bytes_available": True,
                "sequence_unavailable_reason": None,
                "molecule_type": None,
                "sequence_alphabet": "IUPAC_NUCLEOTIDE",
                "completeness_state": "UNKNOWN",
                "source_artifact_id": "assembly/contigs.fasta",
                "source_artifact_sha256": source_hash,
                "m6_support_status": support_by_id.get(fasta_id, "NOT_EVALUATED"),
                "m7_context": None,
            })
        reconstruction_path = output / "reconstruction_evidence.json"
        assembly_manifest_path = output / "assembly" / "assembly_manifest.json"
        fasta_output = output / "candidate_sequences.fasta"
        fasta_artifact = None
        if candidate_rows and fasta_output.is_file():
            fasta_artifact = {
                "path": "candidate_sequences.fasta",
                "sha256": _digest_file(fasta_output),
            }
        if not candidate_rows and candidate_availability_state == "AVAILABLE":
            candidate_availability_state = "INVALID_OUTPUT"
            candidate_unavailable_reason = "ASSEMBLY_CONTAINED_NO_SEQUENCE_RECORDS"
            candidate_availability_state = "INVALID_OUTPUT"
            fasta_artifact = None
            fasta_output.unlink(missing_ok=True)
        candidate_set = {
            "schema": "m8-candidate-sequence-set-v1",
            "producer": {
                "stage_kind": "residual_evidence",
                "stage_id": stage_id,
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
            },
            "source_artifact": candidate_source_identity,
            "assembly_manifest": (
                {
                    "path": "assembly/assembly_manifest.json",
                    "sha256": _digest_file(assembly_manifest_path),
                }
                if assembly_manifest_path.is_file() else None
            ),
            "m6_evidence": {
                "reconstruction_status": status,
                "support_status": support_result.get("status", "NOT_EVALUATED"),
                "artifact": {
                    "path": "reconstruction_evidence.json",
                    "sha256": _digest_file(reconstruction_path),
                },
            },
            "m7_context": None,
            "availability": {
                "state": candidate_availability_state,
                "reason": candidate_unavailable_reason,
                "fasta_artifact": fasta_artifact,
                "record_count": len(candidate_rows),
            },
            "records": candidate_rows,
        }
        write_json(output / "candidate_sequence_set.json", candidate_set)
        shutil.rmtree(work, ignore_errors=True)

    def validate_outputs(self, output, config):
        output = Path(output)
        for name in _ROOT_OUTPUTS:
            contract = self.output_contracts[name]
            artifact_contracts.validate_artifact(output / name, contract)
        optional = output / "supported_contigs.fasta"
        if optional.exists():
            artifact_contracts.validate_artifact(optional, "canonical_contig_fasta")
        candidate_fasta = output / "candidate_sequences.fasta"
        if candidate_fasta.exists():
            artifact_contracts.validate_artifact(
                candidate_fasta, "canonical_contig_fasta")
        contracts = {name: self.output_contracts[name] for name in _ROOT_OUTPUTS}
        if optional.exists():
            contracts["supported_contigs.fasta"] = self.output_contracts["supported_contigs.fasta"]
        if candidate_fasta.exists():
            contracts["candidate_sequences.fasta"] = self.output_contracts[
                "candidate_sequences.fasta"]
        return contracts

    def record_failure(self, output, state, error):
        shutil.rmtree(Path(output) / ".m6-work", ignore_errors=True)
        for name in (
            "residual_read1.fastq.gz", "residual_read2.fastq.gz",
            "eligible_read1.fastq.gz", "eligible_read2.fastq.gz",
            "retained_unassembled_read1.fastq.gz", "retained_unassembled_read2.fastq.gz",
            "unresolved_read1.fastq.gz", "unresolved_read2.fastq.gz",
            "read_triage.csv", "read_support.csv", "read_support.json",
            "residual_manifest.json", "reconstruction_evidence.json",
            "supported_contigs.fasta", "candidate_sequence_set.json",
            "candidate_sequences.fasta",
        ):
            (Path(output) / name).unlink(missing_ok=True)