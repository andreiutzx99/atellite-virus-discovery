import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.external_tool import DependencyMissingError
from satellite_discovery.artifact_workflow import (
    build_default_registry, run as run_artifact_workflow,
    validate as validate_artifact_workflow,
)
from satellite_discovery.residual_evidence_adapter import ResidualEvidenceAdapter
from satellite_discovery.artifact_stage_handlers import workflow_report
from satellite_discovery.sequence_downloader import checksum
from satellite_discovery.bounded_process import ProcessResult


def _gzip(path, text=""):
    with Path(path).open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as out:
            out.write(text.encode("ascii"))


class FakeAssembly:
    def __init__(self, sequence="ACGT"):
        self.sequence = sequence

    def validate_config(self, value):
        return dict(value)

    def inspect_dependency_for_config(self, value):
        return {"status": "available", "dependencies": []}

    def execute(self, inputs, output, config, context=None):
        output.mkdir(parents=True, exist_ok=True)
        (output / "contigs.fasta").write_text(f">c\n{self.sequence}\n", encoding="ascii")
        (output / "assembly_manifest.json").write_text(json.dumps({
            "status": "complete", "external_tool_version": "fake-1",
            "parameters": config,
        }), encoding="utf-8")


class ResidualEvidenceAdapterTests(unittest.TestCase):
    def test_default_workflow_registry_exposes_typed_m6_stages(self):
        registry = build_default_registry()
        residual = registry.get("residual_evidence")
        qc = registry.get("fastq_qc")
        self.assertEqual(residual.input_contracts["qc_manifest"], ("qc_manifest",))
        self.assertEqual(residual.input_contracts["read1"], ("qc_fastq",))
        self.assertEqual(residual.output_contracts["residual_manifest.json"],
                         ("residual_read_manifest",))
        self.assertEqual(residual.output_contracts["read_support.json"],
                         ("read_support_evidence",))
        self.assertEqual(qc.output_contracts["qc.json"], ("qc_manifest",))

    def test_config_is_strict_and_uses_registered_assembly_validation(self):
        adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
        config = adapter.validate_config({"sample_id": "sample-1"})
        self.assertEqual(config["layout"], "single-end")
        self.assertEqual(config["assembler"], "tadpole")
        with self.assertRaises(ValueError):
            adapter.validate_config({"sample_id": "bad/id"})
        with self.assertRaises(ValueError):
            adapter.validate_config({"sample_id": "ok", "threads": True})
        with self.assertRaises(ValueError):
            adapter.validate_config({"sample_id": "ok", "unknown": 1})

    def test_minimap_command_is_allowlisted_and_bounded(self):
        adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
        config = adapter.validate_config({"sample_id": "s"})
        command = adapter.build_command(
            {"minimap2": "/usr/bin/minimap2"},
            {"read1": Path("/tmp/read.fastq.gz"),
             "reference": Path("/tmp/ref.fasta"),
             "roles": Path("/tmp/roles.csv"),
             "qc_manifest": Path("/tmp/qc.json")},
            Path("/tmp/out"), config,
        )
        self.assertEqual(command[0], "/usr/bin/minimap2")
        self.assertIn("--secondary=no", command)
        self.assertEqual(command[command.index("-x") + 1], "sr")
        self.assertNotIn("shell", command)

    def _inputs(self, root):
        return self._inputs_for_sequences(root, ["ACGT"])

    def _inputs_for_sequences(self, root, sequences):
        read = root / "clean_single.fastq.gz"
        reads = "".join(
            f"@r{index}\n{sequence}\n+\n{'I' * len(sequence)}\n"
            for index, sequence in enumerate(sequences, 1)
        )
        _gzip(read, reads)
        rejected = root / "rejected.fastq.gz"
        _gzip(rejected)
        qc = root / "qc.json"
        source = {
            "status": "complete", "engine": "test",
            "fingerprint": {
                "software_version": "test", "config": {},
                "inputs": {"single": {"sha256": "a" * 64, "bytes": 1}},
            },
            "before": {}, "after": {}, "counts": {},
            "output_sha256": {
                "clean_single.fastq.gz": checksum(read),
                "rejected.fastq.gz": checksum(rejected),
            },
        }
        qc.write_text(json.dumps(source), encoding="utf-8")
        reference = root / "reference.fasta"
        reference.write_text(">ref\n" + ("G" * 300) + "\n", encoding="ascii")
        roles = root / "roles.csv"
        roles.write_text(
            "reference_id,reference_role,reference_source,reference_version\n"
            "ref,technical_reference,test,1\n",
            encoding="utf-8",
        )
        return read, reference, roles, qc

    def _paired_inputs(self, root, read1_sequences, read2_sequences):
        self.assertEqual(len(read1_sequences), len(read2_sequences))
        read1 = root / "clean_R1.fastq.gz"
        read2 = root / "clean_R2.fastq.gz"
        _gzip(read1, "".join(
            f"@r{index}/1\n{sequence}\n+\n{'I' * len(sequence)}\n"
            for index, sequence in enumerate(read1_sequences, 1)
        ))
        _gzip(read2, "".join(
            f"@r{index}/2\n{sequence}\n+\n{'I' * len(sequence)}\n"
            for index, sequence in enumerate(read2_sequences, 1)
        ))
        artifacts = {
            "clean_R1.fastq.gz": read1,
            "clean_R2.fastq.gz": read2,
        }
        for name in (
                "clean_single.fastq.gz", "orphan_R1.fastq.gz",
                "orphan_R2.fastq.gz", "rejected.fastq.gz"):
            path = root / name
            _gzip(path)
            artifacts[name] = path
        qc = root / "qc.json"
        qc.write_text(json.dumps({
            "status": "complete", "engine": "test",
            "fingerprint": {
                "software_version": "test", "config": {},
                "inputs": {
                    "R1": {"sha256": "a" * 64, "bytes": 1},
                    "R2": {"sha256": "b" * 64, "bytes": 1},
                },
            },
            "before": {}, "after": {}, "counts": {},
            "output_sha256": {name: checksum(path) for name, path in artifacts.items()},
        }), encoding="utf-8")
        reference = root / "reference.fasta"
        reference.write_text(">ref\n" + ("G" * 300) + "\n", encoding="ascii")
        roles = root / "roles.csv"
        roles.write_text(
            "reference_id,reference_role,reference_source,reference_version\n"
            "ref,technical_reference,test,1\n",
            encoding="utf-8",
        )
        return read1, read2, reference, roles, qc

    @staticmethod
    def _primary_sam(path, sequences):
        with Path(path).open("w", encoding="ascii") as output:
            output.write("@HD\tVN:1.6\n@SQ\tSN:ref\tLN:300\n")
            for index, sequence in enumerate(sequences, 1):
                output.write(
                    f"m6r{index:012d}\t4\t*\t0\t0\t*\t*\t0\t0\t"
                    f"{sequence}\t{'I' * len(sequence)}\n"
                )

    @staticmethod
    def _mock_primary_process(sequences):
        def run(command, directory, stdout_name, stderr_name, *, timeout, max_bytes):
            sam_path = command[command.index("-o") + 1]
            ResidualEvidenceAdapterTests._primary_sam(sam_path, sequences)
            return ProcessResult(0, 0.0, stdout_name, stderr_name)
        return run

    @staticmethod
    def _mock_paired_primary_process(read1_sequences, read2_sequences):
        def run(command, directory, stdout_name, stderr_name, *, timeout, max_bytes):
            sam_path = command[command.index("-o") + 1]
            with Path(sam_path).open("w", encoding="ascii") as output:
                output.write("@HD\tVN:1.6\n@SQ\tSN:ref\tLN:300\n")
                for index, (first, second) in enumerate(
                        zip(read1_sequences, read2_sequences), 1):
                    qname = f"m6r{index:012d}"
                    output.write(
                        f"{qname}\t77\t*\t0\t0\t*\t*\t0\t0\t{first}\t"
                        f"{'I' * len(first)}\n"
                    )
                    output.write(
                        f"{qname}\t141\t*\t0\t0\t*\t*\t0\t0\t{second}\t"
                        f"{'I' * len(second)}\n"
                    )
            return ProcessResult(0, 0.0, stdout_name, stderr_name)
        return run

    def test_qc_mismatch_fails_closed_before_screening(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read, reference, roles, qc = self._inputs(root)
            changed = root / "changed.fastq.gz"
            _gzip(changed, "@r\nTGCA\n+\nIIII\n")
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            with self.assertRaisesRegex(ValueError, "exact QC output"):
                adapter.validate_configured_inputs(
                    {"read1": changed, "reference": reference, "roles": roles,
                     "qc_manifest": qc}, root / "out",
                     adapter.validate_config({"sample_id": "s"}),
                )

    def test_supported_reconstruction_is_never_created_from_assembler_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read, reference, roles, qc = self._inputs(root)
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            config = adapter.validate_config({"sample_id": "s"})
            triage = {
                "counts": {"input_fragments": 1, "residual_fragments": 1,
                           "eligible_fragments": 1, "retained_unassembled_fragments": 0},
                "residual_fragment_ids": ["m6r000000000001"],
                "eligible_fragment_ids": ["m6r000000000001"],
                "retained_unassembled_fragment_ids": [],
                "read_metadata": {
                    ("m6r000000000001", 0): {
                        "query_length": 4,
                        "sequence_sha256": hashlib.sha256(b"ACGT").hexdigest(),
                    },
                },
            }
            with patch.object(adapter, "inspect_dependency_for_config",
                              return_value={"status": "available", "dependencies": [
                                  {"tool": "minimap2", "path": "/bin/minimap2"}]}), \
                 patch("satellite_discovery.residual_evidence_adapter.residual_reads.prepare_normalized_fastqs",
                       return_value={"read1": root / "normalized.fastq.gz", "read2": None}), \
                 patch("satellite_discovery.residual_evidence_adapter.residual_reads.screen_and_triage",
                       return_value=triage), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=lambda command, directory, stdout, stderr, timeout, max_bytes:
                       (Path(command[command.index("-o") + 1]).write_text(
                           "@HD\tVN:1.6\n", encoding="ascii")
                        and ProcessResult(0, 0.0, stdout, stderr))), \
                 patch.object(adapter, "_run_mapper"), \
                 patch("satellite_discovery.residual_evidence_adapter.read_support.assess_read_support",
                       side_effect=ValueError("bad support")):
                result = adapter.execute(
                    {"read1": read, "reference": reference, "roles": roles,
                     "qc_manifest": qc}, root / "out", config,
                )
            evidence = json.loads((root / "out" / "reconstruction_evidence.json").read_text())
            self.assertEqual(evidence["status"], "INVALID_SUPPORT_OUTPUT")
            self.assertFalse((root / "out" / "supported_contigs.fasta").exists())

    def test_disabled_assembly_preserves_unresolved_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequence = "ACGT" * 25
            read, reference, roles, qc = self._inputs_for_sequences(root, [sequence])
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            config = adapter.validate_config({
                "sample_id": "s", "assembly_enabled": False,
                "triage": {"min_read_length": 50},
            })
            dependency = {
                "status": "available",
                "dependencies": [{"tool": "minimap2", "path": "/bin/minimap2",
                                  "version": "fake", "sha256": "a" * 64}],
            }
            with patch.object(adapter, "inspect_dependency_for_config", return_value=dependency), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=self._mock_primary_process([sequence])), \
                 patch.object(adapter, "_run_mapper") as support_mapper:
                adapter.execute(
                    {"read1": read, "reference": reference, "roles": roles,
                     "qc_manifest": qc}, root / "out", config,
                )
            support_mapper.assert_not_called()
            evidence = json.loads((root / "out" / "reconstruction_evidence.json").read_text())
            self.assertEqual(evidence["status"], "ASSEMBLY_NOT_ATTEMPTED")
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read1.fastq.gz").read_bytes()),
                gzip.decompress(read.read_bytes()),
            )
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read2.fastq.gz").read_bytes()),
                b"",
            )

    def test_paired_unresolved_reads_preserve_both_original_mates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = "ACGT" * 25, "TGCA" * 25
            read1, read2, reference, roles, qc = self._paired_inputs(
                root, [first], [second])
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            config = adapter.validate_config({
                "sample_id": "paired-unresolved", "layout": "paired-end",
                "assembly_enabled": False,
                "triage": {"min_read_length": 50},
            })
            dependency = {
                "status": "available",
                "dependencies": [{"tool": "minimap2", "path": "/bin/minimap2",
                                  "version": "fake", "sha256": "a" * 64}],
            }
            with patch.object(adapter, "inspect_dependency_for_config", return_value=dependency), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=self._mock_paired_primary_process([first], [second])), \
                 patch.object(adapter, "_run_mapper") as support_mapper:
                adapter.execute(
                    {"read1": read1, "read2": read2, "reference": reference,
                     "roles": roles, "qc_manifest": qc}, root / "out", config,
                )
            support_mapper.assert_not_called()
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read1.fastq.gz").read_bytes()),
                gzip.decompress(read1.read_bytes()),
            )
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read2.fastq.gz").read_bytes()),
                gzip.decompress(read2.read_bytes()),
            )
            residual = json.loads(
                (root / "out" / "residual_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(residual["comparison"]["input_read_count"], 2)
            self.assertEqual(residual["comparison"]["accounted_read_count"], 2)

    def test_completed_screen_and_read_back_support_reuse_through_base(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = "ACGT" * 25
            second = first[:-1] + "A"
            short = first[:40]
            sequences = [first, second, short]
            read, reference, roles, qc = self._inputs_for_sequences(root, sequences)
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly(first))
            config = adapter.validate_config({
                "sample_id": "supported",
                "triage": {"min_read_length": 50},
                "support": {"min_mean_depth": 2, "min_distinct_fragments": 2},
            })
            dependency = {
                "status": "available",
                "dependencies": [{"tool": "minimap2", "path": "/bin/minimap2",
                                  "version": "fake", "sha256": "a" * 64}],
                "assembly": {"status": "available", "dependencies": [
                    {"tool": "fake-assembler", "path": "/bin/assembler",
                     "version": "fake-1", "sha256": "b" * 64}]},
            }
            changed_dependency = {
                **dependency,
                "assembly": {"status": "available", "dependencies": [
                    {"tool": "fake-assembler", "path": "/bin/assembler",
                     "version": "fake-2", "sha256": "c" * 64}]},
            }

            def support_mapper(_executable, _reference, reads, output, _config):
                rows = gzip.decompress(Path(reads[0]).read_bytes()).decode("ascii").splitlines()
                support_records = [
                    (rows[index][1:].split()[0], rows[index + 1])
                    for index in range(0, len(rows), 4)
                ]
                self.assertEqual(len(support_records), 2)
                with Path(output).open("w", encoding="ascii") as sam:
                    sam.write("@HD\tVN:1.6\n@SQ\tSN:c\tLN:100\n")
                    for query_id, sequence in support_records:
                        nm = sum(a != b for a, b in zip(sequence, first))
                        sam.write(
                            f"{query_id}\t0\tc\t1\t60\t{len(sequence)}M\t*\t0\t0\t"
                            f"{sequence}\t{'I' * len(sequence)}\tNM:i:{nm}\n"
                        )

            args = {
                "read1": read, "reference": reference,
                "roles": roles, "qc_manifest": qc,
            }
            with patch.object(
                    adapter, "inspect_dependency_for_config",
                    side_effect=[dependency, dependency, changed_dependency]), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=self._mock_primary_process(sequences)), \
                 patch.object(adapter, "_run_mapper", side_effect=support_mapper):
                execution = adapter.execute(args, root / "out", config)
                reused = adapter.execute(args, root / "out", config)
                with self.assertRaisesRegex(ValueError, "executable changed"):
                    adapter.execute(args, root / "out", config)
            self.assertEqual(execution.execution, "executed")
            self.assertEqual(reused.execution, "verified_reuse")
            support = json.loads((root / "out" / "read_support.json").read_text())
            self.assertEqual(support["status"], "READ_SUPPORTED_ASSEMBLY")
            self.assertEqual(len(support["resolved_fragment_ids"]), 2)
            self.assertEqual(
                support["provenance"]["support_input_fragment_ids"],
                ["m6r000000000001", "m6r000000000002"],
            )
            self.assertTrue((root / "out" / "supported_contigs.fasta").is_file())
            residual = json.loads((root / "out" / "residual_manifest.json").read_text())
            self.assertEqual(residual["comparison"]["input_read_count"], 3)
            self.assertEqual(residual["comparison"]["accounted_read_count"], 3)
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read1.fastq.gz").read_bytes()),
                f"@r3\n{short}\n+\n{'I' * len(short)}\n".encode("ascii"),
            )
            workflow_report({
                "residual_manifest": root / "out" / "residual_manifest.json",
                "read_support": root / "out" / "read_support.json",
                "reconstruction": root / "out" / "reconstruction_evidence.json",
            }, root / "workflow-report", {"title": "M6 artificial workflow"})
            report = json.loads(
                (root / "workflow-report" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                report["artifacts"]["reconstruction"]["summary"]["status"],
                "READ_SUPPORTED_ASSEMBLY",
            )
            self.assertEqual(
                report["artifacts"]["residual_manifest"]["summary"]["comparison"]["status"],
                "complete",
            )

    def test_assembler_dependency_failure_is_not_no_supported_assembly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequence = "ACGT" * 25
            read, reference, roles, qc = self._inputs_for_sequences(root, [sequence])
            assembly = FakeAssembly()
            adapter = ResidualEvidenceAdapter(assembly_adapter=assembly)
            config = adapter.validate_config({
                "sample_id": "missing-tool",
                "triage": {"min_read_length": 50},
            })
            dependency = {
                "status": "available",
                "dependencies": [{"tool": "minimap2", "path": "/bin/minimap2",
                                  "version": "fake", "sha256": "a" * 64}],
                "assembly": {"status": "dependency_missing", "dependencies": []},
            }
            with patch.object(adapter, "inspect_dependency_for_config", return_value=dependency), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=self._mock_primary_process([sequence])), \
                 patch.object(assembly, "execute",
                              side_effect=DependencyMissingError("missing", dependency)):
                adapter.execute(
                    {"read1": read, "reference": reference, "roles": roles,
                     "qc_manifest": qc}, root / "out", config,
                )
            evidence = json.loads((root / "out" / "reconstruction_evidence.json").read_text())
            support = json.loads((root / "out" / "read_support.json").read_text())
            self.assertEqual(evidence["status"], "DEPENDENCY_UNAVAILABLE")
            self.assertEqual(support["status"], "NOT_EVALUATED")
            self.assertEqual(
                gzip.decompress((root / "out" / "unresolved_read1.fastq.gz").read_bytes()),
                gzip.decompress(read.read_bytes()),
            )

    def test_dvg_unavailable_status_is_preserved_and_summary_is_linked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequence = "ACGT" * 25
            read, reference, roles, qc = self._inputs_for_sequences(root, [sequence])
            dvg = root / "dvg.json"
            dvg.write_text(json.dumps({
                "schema": "dvg-evidence-v1", "caller": "fixture",
                "status": "ANALYSIS_UNAVAILABLE", "events": [],
            }), encoding="utf-8")
            summary = root / "dvg-summary.json"
            summary.write_text(json.dumps({
                "schema": "dvg-summary-v1", "caller": "fixture",
                "status": "ANALYSIS_UNAVAILABLE", "event_count": 0,
            }), encoding="utf-8")
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            config = adapter.validate_config({
                "sample_id": "dvg-link", "assembly_enabled": False,
                "triage": {"min_read_length": 50},
            })
            dependency = {
                "status": "available",
                "dependencies": [{"tool": "minimap2", "path": "/bin/minimap2",
                                  "version": "fake", "sha256": "a" * 64}],
            }
            with patch.object(adapter, "inspect_dependency_for_config", return_value=dependency), \
                 patch("satellite_discovery.external_tool.bounded_process.run_captured",
                       side_effect=self._mock_primary_process([sequence])):
                adapter.execute(
                    {"read1": read, "reference": reference, "roles": roles,
                     "qc_manifest": qc, "dvg_evidence": dvg, "dvg_summary": summary},
                    root / "out", config,
                )
            evidence = json.loads(
                (root / "out" / "reconstruction_evidence.json").read_text())
            self.assertEqual(evidence["dvg_status"]["status"], "ANALYSIS_UNAVAILABLE")
            self.assertEqual(
                evidence["dvg_status"]["dvg_evidence"]["status"],
                evidence["dvg_status"]["dvg_summary"]["status"],
            )

    def test_conflicting_dvg_evidence_and_summary_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read, reference, roles, qc = self._inputs_for_sequences(root, ["ACGT"])
            dvg = root / "dvg.json"
            dvg.write_text(json.dumps({
                "schema": "dvg-evidence-v1", "caller": "fixture",
                "status": "ANALYSIS_UNAVAILABLE", "events": [],
            }), encoding="utf-8")
            summary = root / "dvg-summary.json"
            summary.write_text(json.dumps({
                "schema": "dvg-summary-v1", "caller": "fixture",
                "status": "NO_DVG_EVIDENCE_DETECTED", "event_count": 0,
            }), encoding="utf-8")
            adapter = ResidualEvidenceAdapter(assembly_adapter=FakeAssembly())
            config = adapter.validate_config({"sample_id": "dvg-conflict"})
            with self.assertRaisesRegex(ValueError, "status/count do not agree"):
                adapter.validate_configured_inputs(
                    {"read1": read, "reference": reference, "roles": roles,
                     "qc_manifest": qc, "dvg_evidence": dvg, "dvg_summary": summary},
                    root / "out", config,
                )

    def test_complete_m6_bundles_handoff_to_m7_through_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequence = "ACGT" * 25
            near_match = sequence[:-1] + "A"
            support_sequences = [sequence, near_match]
            specification = {"schema": "artifact-workflow-v1", "stages": []}
            observations = []
            m7_inputs = {}

            for index, sample_id in enumerate(
                    ("sample-1", "sample-2", "sample-unsupported"), start=1):
                input_dir = root / f"input-{index}"
                input_dir.mkdir()
                read, reference, roles, qc = self._inputs_for_sequences(
                    input_dir, support_sequences,
                )
                read_records = "".join(
                    f"@sample{index}_r{number}\n{read_sequence}\n+\n"
                    f"{'I' * len(read_sequence)}\n"
                    for number, read_sequence in enumerate(support_sequences, start=1)
                )
                _gzip(read, read_records)
                qc_record = json.loads(qc.read_text(encoding="utf-8"))
                qc_record["output_sha256"]["clean_single.fastq.gz"] = checksum(read)
                qc.write_text(json.dumps(qc_record), encoding="utf-8")

                stage_id = f"m6_{index}"
                specification["stages"].append({
                    "id": stage_id,
                    "kind": "residual_evidence",
                    "inputs": {
                        "read1": {
                            "path": str(read),
                            "artifact_type": "qc_fastq",
                        },
                        "reference": {
                            "path": str(reference),
                            "artifact_type": "raw_fasta",
                        },
                        "roles": {
                            "path": str(roles),
                            "artifact_type": "reference_roles",
                        },
                        "qc_manifest": {
                            "path": str(qc),
                            "artifact_type": "qc_manifest",
                        },
                    },
                    "config": {
                        "sample_id": sample_id,
                        "layout": "single-end",
                        "triage": {"min_read_length": 50},
                        "assembly_enabled": index < 3,
                    },
                })

                evidence_input = f"evidence{index}"
                residual_input = f"residual{index}"
                observation = {
                    "observation_id": f"obs{index}",
                    "candidate_id": f"candidate{index}",
                    "sample_id": sample_id,
                    "sequencing_run_id": f"run-{index}" if index == 1 else None,
                    "study_id": "study-1" if index == 1 else None,
                    "source_artifact_id": f"source-{index}",
                    "m6_state": "available",
                    "molecule_type": "DNA",
                    "evidence_input": evidence_input,
                    "residual_manifest_input": residual_input,
                }
                m7_inputs[evidence_input] = {
                    "stage": stage_id,
                    "artifact": "reconstruction_evidence.json",
                }
                m7_inputs[residual_input] = {
                    "stage": stage_id,
                    "artifact": "residual_manifest.json",
                }
                if index < 3:
                    contigs_input = f"contigs{index}"
                    observation["contigs_input"] = contigs_input
                    m7_inputs[contigs_input] = {
                        "stage": stage_id,
                        "artifact": "supported_contigs.fasta",
                    }
                observations.append(observation)

            specification["stages"].append({
                "id": "m7",
                "kind": "independent_recurrence",
                "inputs": m7_inputs,
                "config": {
                    "orientation_policy": "forward_only",
                    "observations": observations,
                },
            })
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(specification), encoding="utf-8")

            dependency = {
                "status": "available",
                "dependencies": [{
                    "tool": "minimap2",
                    "path": "/bin/minimap2",
                    "version": "artificial",
                    "sha256": "a" * 64,
                }],
                "assembly": {
                    "status": "available",
                    "dependencies": [{
                        "tool": "artificial-assembler",
                        "path": "/bin/assembler",
                        "version": "1",
                        "sha256": "b" * 64,
                    }],
                },
            }

            def support_mapper(_executable, _reference, reads, output, _config):
                lines = gzip.decompress(Path(reads[0]).read_bytes()).decode(
                    "ascii"
                ).splitlines()
                support_records = [
                    (lines[offset][1:].split()[0], lines[offset + 1])
                    for offset in range(0, len(lines), 4)
                ]
                self.assertEqual(len(support_records), 2)
                with Path(output).open("w", encoding="ascii") as sam:
                    sam.write("@HD\tVN:1.6\n@SQ\tSN:c\tLN:100\n")
                    for query_id, read_sequence in support_records:
                        mismatches = sum(
                            left != right
                            for left, right in zip(read_sequence, sequence)
                        )
                        sam.write(
                            f"{query_id}\t0\tc\t1\t60\t100M\t*\t0\t0\t"
                            f"{read_sequence}\t{'I' * len(read_sequence)}"
                            f"\tNM:i:{mismatches}\n"
                        )

            with patch.object(
                    ResidualEvidenceAdapter,
                    "inspect_dependency_for_config",
                    return_value=dependency,
            ), patch(
                    "satellite_discovery.external_tool.bounded_process.run_captured",
                    side_effect=self._mock_primary_process(support_sequences),
            ) as primary_mapper:
                registry = build_default_registry()
                residual_definition = registry.get("residual_evidence")
                adapter = residual_definition.handler
                assembly = FakeAssembly(sequence)
                adapter.assembly_adapter = assembly

                invalid = json.loads(json.dumps(specification))
                invalid["stages"][-1]["inputs"]["contigs1"]["artifact"] = (
                    "assembly/contigs.fasta"
                )
                with self.assertRaises(ValueError):
                    validate_artifact_workflow(invalid, registry)
                validate_artifact_workflow(specification, registry)

                workflow_output = root / "workflow-output"
                with patch.object(
                        assembly, "execute", wraps=assembly.execute,
                ) as assembly_calls, patch.object(
                        adapter, "_run_mapper", side_effect=support_mapper,
                ) as support_calls:
                    run_artifact_workflow(spec_path, workflow_output, registry)
                    first_report = json.loads(
                        (workflow_output / "workflow.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(first_report["status"], "complete")
                    first_stages = {
                        row["id"]: row for row in first_report["stages"]
                    }
                    self.assertEqual(
                        [first_stages[f"m6_{index}"]["status"]
                         for index in (1, 2, 3)],
                        ["complete", "complete", "complete"],
                    )
                    self.assertEqual(first_stages["m7"]["status"], "complete")
                    self.assertEqual(primary_mapper.call_count, 3)
                    self.assertEqual(support_calls.call_count, 2)
                    self.assertEqual(assembly_calls.call_count, 2)

                    m6_outputs = {}
                    for index in (1, 2, 3):
                        stage = first_stages[f"m6_{index}"]
                        stage_dir = workflow_output / stage["output_path"]
                        m6_outputs[index] = stage_dir
                        m6_manifest = json.loads(
                            (stage_dir / "manifest.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        self.assertEqual(m6_manifest["status"], "complete")
                        for name, digest in m6_manifest["output_sha256"].items():
                            artifact = stage_dir / name
                            self.assertTrue(artifact.is_file(), name)
                            self.assertEqual(checksum(artifact), digest, name)
                        self.assertTrue(
                            (stage_dir / "reconstruction_evidence.json").is_file()
                        )
                        self.assertTrue(
                            (stage_dir / "residual_manifest.json").is_file()
                        )
                        if index < 3:
                            self.assertTrue(
                                (stage_dir / "supported_contigs.fasta").is_file()
                            )
                        else:
                            self.assertFalse(
                                (stage_dir / "supported_contigs.fasta").exists()
                            )

                    m7_dir = workflow_output / first_stages["m7"]["output_path"]
                    m7_input_types = {
                        item["artifact_type"]
                        for item in first_stages["m7"]["inputs"].values()
                    }
                    self.assertEqual(m7_input_types, {
                        "canonical_contig_fasta",
                        "reconstruction_evidence",
                        "residual_read_manifest",
                    })
                    observation_data = json.loads(
                        (m7_dir / "observations.json").read_text(encoding="utf-8")
                    )
                    observation_rows = {
                        row["observation_id"]: row
                        for row in observation_data["observations"]
                    }
                    first = observation_rows["obs1"]
                    second = observation_rows["obs2"]
                    unsupported = observation_rows["obs3"]

                    self.assertEqual(first["m6_status"], "READ_SUPPORTED_ASSEMBLY")
                    self.assertEqual(first["sample_id"], "sample-1")
                    self.assertEqual(first["sequencing_run_id"], "run-1")
                    self.assertEqual(first["study_id"], "study-1")
                    self.assertEqual(
                        first["contigs"][0]["sequence_sha256"],
                        hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                    )
                    first_manifest = m6_outputs[1] / "manifest.json"
                    first_residual = json.loads(
                        (m6_outputs[1] / "residual_manifest.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(
                        first["upstream_manifest_sha256"], checksum(first_manifest)
                    )
                    self.assertEqual(
                        first["source_read_sha256"],
                        {
                            role: item["sha256"]
                            for role, item in first_residual["source_reads"].items()
                        },
                    )
                    for input_name, filename in (
                            ("evidence1", "reconstruction_evidence.json"),
                            ("residual1", "residual_manifest.json"),
                            ("contigs1", "supported_contigs.fasta")):
                        self.assertEqual(
                            first["source_artifacts"][input_name]["sha256"],
                            checksum(m6_outputs[1] / filename),
                        )

                    self.assertEqual(second["sample_id"], "sample-2")
                    self.assertIsNone(second["sequencing_run_id"])
                    self.assertIsNone(second["study_id"])
                    self.assertIn("sequencing_run_id", second["metadata_missing"])
                    self.assertIn("study_id", second["metadata_missing"])
                    self.assertNotEqual(
                        first["source_dataset_fingerprint"],
                        second["source_dataset_fingerprint"],
                    )
                    self.assertNotEqual(
                        first["source_read_sha256"]["read1"],
                        second["source_read_sha256"]["read1"],
                    )

                    self.assertEqual(
                        unsupported["m6_status"], "ASSEMBLY_NOT_ATTEMPTED"
                    )
                    self.assertEqual(unsupported["contigs"], [])
                    self.assertIn("study_id", unsupported["metadata_missing"])
                    recurrence = json.loads(
                        (m7_dir / "exact_recurrence.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(observation_data["sequence_observation_count"], 2)
                    self.assertEqual(len(recurrence["groups"]), 1)
                    group = recurrence["groups"][0]
                    self.assertEqual(group["sequence_observation_count"], 2)
                    self.assertEqual(group["source_dataset_count"], 2)
                    self.assertEqual(
                        group["recurrence_categories"],
                        ["RECURRENT_ACROSS_SAMPLES"],
                    )
                    recurrence_before_reuse = (
                        m7_dir / "exact_recurrence.json"
                    ).read_bytes()
                    m7_manifest_before_reuse = json.loads(
                        (m7_dir / "manifest.json").read_text(encoding="utf-8")
                    )

                    run_artifact_workflow(spec_path, workflow_output, registry)
                    reused_report = json.loads(
                        (workflow_output / "workflow.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    reused_stages = {
                        row["id"]: row for row in reused_report["stages"]
                    }
                    self.assertTrue(all(
                        reused_stages[f"m6_{index}"]["execution"]
                        == "verified_reuse"
                        for index in (1, 2, 3)
                    ))
                    self.assertEqual(
                        reused_stages["m7"]["execution"], "verified_reuse"
                    )
                    self.assertEqual(
                        (m7_dir / "exact_recurrence.json").read_bytes(),
                        recurrence_before_reuse,
                    )
                    self.assertEqual(
                        json.loads(
                            (m7_dir / "manifest.json").read_text(encoding="utf-8")
                        )["output_sha256"],
                        m7_manifest_before_reuse["output_sha256"],
                    )
                    self.assertEqual(primary_mapper.call_count, 3)
                    self.assertEqual(support_calls.call_count, 2)
                    self.assertEqual(assembly_calls.call_count, 2)

                corrupted = m6_outputs[1] / "supported_contigs.fasta"
                original_fasta = corrupted.read_bytes()
                tampered_sequence = sequence[:-1] + (
                    "A" if sequence[-1] != "A" else "C"
                )
                corrupted.write_text(
                    f">c\n{tampered_sequence}\n", encoding="ascii"
                )
                direct_inputs = {
                    "evidence1": {
                        "path": str(m6_outputs[1] / "reconstruction_evidence.json"),
                        "artifact_type": "reconstruction_evidence",
                    },
                    "residual1": {
                        "path": str(m6_outputs[1] / "residual_manifest.json"),
                        "artifact_type": "residual_read_manifest",
                    },
                    "contigs1": {
                        "path": str(corrupted),
                        "artifact_type": "canonical_contig_fasta",
                    },
                }
                corruption_spec = {
                    "schema": "artifact-workflow-v1",
                    "stages": [{
                        "id": "m7_corruption_check",
                        "kind": "independent_recurrence",
                        "inputs": direct_inputs,
                        "config": {
                            "orientation_policy": "forward_only",
                            "observations": [observations[0]],
                        },
                    }],
                }
                corruption_path = root / "corruption-workflow.json"
                corruption_path.write_text(
                    json.dumps(corruption_spec), encoding="utf-8"
                )
                corruption_output = root / "corruption-output"
                try:
                    with self.assertRaisesRegex(
                            ValueError,
                            "not bound to its adjacent stage manifest",
                    ):
                        run_artifact_workflow(
                            corruption_path, corruption_output, registry
                        )
                finally:
                    corrupted.write_bytes(original_fasta)
                corruption_report = json.loads(
                    (corruption_output / "workflow.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(corruption_report["status"], "failed")
                self.assertIn(
                    "not bound to its adjacent stage manifest",
                    corruption_report["failure"]["error"],
                )


if __name__ == "__main__":
    unittest.main()