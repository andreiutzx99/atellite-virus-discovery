import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m36_adapters import (
    M36Phase2BAttemptAdapter,
    build_m6_candidate_handoff,
    run_unregistered_fixture,
    run_frozen_m8_m31_handoff,
    triage_m8_outputs,
)
from satellite_discovery.m36_preparation import RunnerBlocked
from satellite_discovery import m31_synthetic_evidence_screening as m31
from satellite_discovery import m8_reference_panels


class M36AdapterTests(unittest.TestCase):
    def _support(self, _fastq, contigs, reads):
        supported = {
            read_id: sequence for read_id, sequence in reads.items()
            if "-ref-" not in read_id
        }
        return {
            "supported_read_ids": sorted(supported),
            "supported_contig_ids": ["target"],
            "supported_read_sha256": {
                key: hashlib.sha256(value.encode("ascii")).hexdigest()
                for key, value in supported.items()
            },
            "supported_contig_sha256": {
                "target": hashlib.sha256(contigs["target"].encode("ascii")).hexdigest()
            },
            "read_placements": [
                {"read_id": key, "contig_id": "target", "start": 0,
                 "cigar": f"{len(value)}M", "strand": "+"}
                for key, value in supported.items()
            ],
        }

    def test_unregistered_fixture_keeps_four_checkpoints_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "run"

            def assemble(_reads, _out, assembler):
                return {
                    "status": "PASS",
                    "contigs": {"target": "ACGT" * 25},
                    "evidence": f"synthetic {assembler} adapter".encode(),
                }

            result = run_unregistered_fixture(
                root,
                truth_sequence="ACGT" * 25,
                technical_reference="TGCA" * 25,
                backgrounds=("GATC" * 25,),
                seed=360003,
                read_length=50,
                coverage=2,
                error_rate=0,
                assembler="spades",
                assembly_stage=assemble,
                support_stage=self._support,
                detection_stage=lambda *_args: {
                    "status": "NOT_EVALUATED",
                    "reason": "synthetic fixture has no approved M8 panel",
                },
            )

            self.assertEqual(
                [row["stage"] for row in result["checkpoints"]],
                ["generation", "assembly", "support", "detection"],
            )
            self.assertEqual(result["support"]["support"], "READ_SUPPORTED_ASSEMBLY")
            self.assertEqual(result["detection"]["status"], "NOT_EVALUATED")
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertFalse(result["registered_matrix_executed"])
            analyst_view = json.dumps(result, sort_keys=True).lower()
            for private_value in (
                "acgt" * 25, "360003", "held_out", "family_id",
                "condition_id", "target_truth",
            ):
                self.assertNotIn(private_value, analyst_view)
            downstream = (root / "detection" / "downstream_result.json").read_text(
                encoding="utf-8",
            ).lower()
            self.assertNotIn("360003", downstream)
            self.assertNotIn("held_out", downstream)
            if os.name == "posix":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_m6_handoff_keeps_unsupported_contigs_unconfirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assembly = root / "assembly"
            assembly.mkdir()
            contigs = {"supported": "ACGT" * 25, "unsupported": "TGCA" * 25}
            (assembly / "canonical_contigs.fasta").write_text(
                "".join(f">{name}\n{sequence}\n" for name, sequence in contigs.items()),
                encoding="ascii",
            )
            (assembly / "assembly_manifest.json").write_text(json.dumps({
                "schema": "assembly-manifest-v1",
                "workflow_status": "complete",
                "contig_count": 2,
                "assembler": "synthetic",
                "external_tool_version": "test",
            }), encoding="utf-8")
            handoff = build_m6_candidate_handoff(
                assembly,
                root / "handoff",
                support_evidence={"supported_contig_ids": ["supported"]},
                support_status="READ_SUPPORTED_ASSEMBLY",
            )
            document = json.loads(handoff.read_text(encoding="utf-8"))
            by_id = {row["fasta_record_id"]: row for row in document["records"]}
            self.assertEqual(by_id["supported"]["m6_support_status"],
                             "READ_SUPPORTED_ASSEMBLY")
            self.assertEqual(by_id["unsupported"]["m6_support_status"],
                             "UNSUPPORTED_ASSEMBLY")

            with self.assertRaisesRegex(ValueError, "status and supported contig set disagree"):
                build_m6_candidate_handoff(
                    assembly,
                    root / "invalid-handoff",
                    support_evidence={"supported_contig_ids": ["supported"]},
                    support_status="NOT_EVALUATED",
                )

    def test_not_evaluated_support_never_becomes_successful_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            called = []

            def no_support(_fastq, _contigs, _reads):
                return {
                    "supported_read_ids": [],
                    "supported_contig_ids": [],
                    "supported_read_sha256": {},
                    "supported_contig_sha256": {},
                    "read_placements": [],
                }

            result = run_unregistered_fixture(
                Path(folder) / "run",
                truth_sequence="ACGT" * 25,
                technical_reference="TGCA" * 25,
                backgrounds=(),
                seed=360005,
                read_length=50,
                coverage=2,
                error_rate=0,
                assembler="spades",
                assembly_stage=lambda *_: {
                    "status": "PASS", "contigs": {"unsupported": "ACGT" * 25},
                },
                support_stage=no_support,
                detection_stage=lambda *_: called.append("detection") or {
                    "status": "PASS",
                },
            )
            self.assertEqual(result["support"]["support"], "NO_SUPPORTED_ASSEMBLY")
            self.assertEqual(result["detection"]["status"], "NOT_EVALUATED")
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(called, [])

    def test_failed_assembly_does_not_call_support_or_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            called = []
            result = run_unregistered_fixture(
                Path(folder) / "run",
                truth_sequence="ACGT" * 25,
                technical_reference="TGCA" * 25,
                backgrounds=(),
                seed=360004,
                read_length=50,
                coverage=2,
                error_rate=0,
                assembler="tadpole",
                assembly_stage=lambda *_args: {"status": "FAILED", "contigs": {}},
                support_stage=lambda *_args: called.append("support"),
                detection_stage=lambda *_args: called.append("detection"),
            )
            self.assertEqual(result["status"], "ASSEMBLY_OUTPUT_INVALID")
            self.assertEqual(called, [])

    def test_registered_adapter_is_explicitly_not_ready(self):
        self.assertFalse(M36Phase2BAttemptAdapter.REGISTERED_EXECUTION_READY)
        with self.assertRaisesRegex(RunnerBlocked, "not execution-ready"):
            M36Phase2BAttemptAdapter()()

    def test_frozen_m31_handoff_keeps_incomplete_m8_as_insufficient(self):
        queries = [
            {
                "candidate_id": "synthetic-contig",
                "panel_role": role,
                "aggregate_status": "INCOMPLETE",
            }
            for role in m31.ROLES
        ]
        result = triage_m8_outputs(
            queries, [], {"synthetic-contig": "ACGT" * 25},
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["outcome"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("incomplete", result[0]["reason"].lower())

    @unittest.skipUnless(
        os.environ.get("M8_BLASTN_EXECUTABLE")
        and os.environ.get("M8_MAKEBLASTDB_EXECUTABLE"),
        "requires the pinned optional-tools BLAST runtime",
    )
    def test_frozen_synthetic_m8_m31_handoff_validates_outputs_and_provenance(self):
        blastn = Path(os.environ["M8_BLASTN_EXECUTABLE"])
        makeblastdb = Path(os.environ["M8_MAKEBLASTDB_EXECUTABLE"])
        blastdbcmd = makeblastdb.with_name("blastdbcmd")
        if not blastdbcmd.is_file():
            self.skipTest("the pinned blastdbcmd executable is unavailable")

        fixture = m31._synthetic_sequences()
        query_rows = fixture["queries"]
        selected = [query_rows[index] for index in (0, 2, 3, 5)]
        contigs = {candidate_id: sequence
                   for candidate_id, sequence, _discarded_split in selected}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assembly = root / "assembly"
            assembly.mkdir()
            fasta = "".join(
                f">{identifier}\n{sequence}\n"
                for identifier, sequence in contigs.items()
            )
            (assembly / "canonical_contigs.fasta").write_text(fasta, encoding="ascii")
            (assembly / "assembly_manifest.json").write_text(json.dumps({
                "schema": "assembly-manifest-v1",
                "workflow_status": "complete",
                "contig_count": len(contigs),
                "assembler": "M36 synthetic-only fixture",
                "external_tool_version": "fixture",
            }), encoding="utf-8")
            candidate_path = build_m6_candidate_handoff(
                assembly,
                root / "candidate",
                support_evidence={"supported_contig_ids": []},
                support_status="NOT_EVALUATED",
            )
            candidate_doc = json.loads(candidate_path.read_text(encoding="utf-8"))

            reference_root = root / "reference"
            manifest_path, panel_path, indexes, panel_document = m31._panel(
                reference_root,
                fixture["panel"],
                str(blastn),
                str(makeblastdb),
                str(blastdbcmd),
            )
            verified_snapshot = m8_reference_panels.validate_snapshot_manifest(
                manifest_path,
            )
            payload_paths = {
                panel_path.name: panel_path,
                **{path.name: path for path in indexes},
            }
            external_identity = m8_reference_panels.validate_external_snapshot_files(
                manifest_path, payload_paths,
            )
            self.assertEqual(
                external_identity["snapshot_digest"],
                panel_document["snapshot_digest"],
            )

            complete = run_frozen_m8_m31_handoff(
                candidate_path,
                manifest_path,
                reference_root,
                root / "complete-run",
                blastn_executable=str(blastn),
                makeblastdb_executable=str(makeblastdb),
            )
            complete_file = json.loads(
                (root / "complete-run" / "m36_m8_m31_handoff.json").read_text(
                    encoding="utf-8",
                )
            )
            self.assertEqual(complete, complete_file)
            self.assertEqual(complete["m8_execution_status"], "COMPLETE")
            self.assertEqual(complete["m6_support_status"], "NOT_EVALUATED")
            self.assertEqual(complete["pipeline_detection_status"], "NOT_EVALUATED")
            self.assertFalse(complete["private_mapping_included"])
            self.assertEqual(
                complete["snapshot_provenance"]["snapshot_digest"],
                verified_snapshot["snapshot_digest"],
            )
            self.assertEqual(
                complete["snapshot_provenance"]["membership_digest"],
                verified_snapshot["membership_digest"],
            )
            self.assertEqual(
                complete["snapshot_provenance"]["reference_panel_state"], "VALID",
            )
            self.assertEqual(
                len(complete["snapshot_provenance"]["index_digests"]), len(indexes),
            )
            candidate_ids = {
                row["fasta_record_id"]: row["candidate_id"]
                for row in candidate_doc["records"]
            }
            classifications = {
                next(
                    name for name, candidate_id in candidate_ids.items()
                    if candidate_id == result["candidate_id"]
                ): result["outcome"]
                for result in complete["triage"]
            }
            self.assertEqual(classifications["q001"], "REVIEW_PRIORITY")
            self.assertEqual(classifications["q003"], "BACKGROUND_LIKE")
            self.assertEqual(classifications["q004"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(classifications["q006"], "CONFLICTING_EVIDENCE")
            serialized = json.dumps(complete, sort_keys=True).lower()
            self.assertNotIn("held_out", serialized)
            self.assertNotIn("development", serialized)
            self.assertNotIn("family_id", serialized)
            self.assertNotIn("condition_id", serialized)
            self.assertNotIn("truth", serialized)
            self.assertNotIn("split", serialized)

            # Corrupt a declared index file without changing its frozen manifest.
            indexes[0].write_bytes(indexes[0].read_bytes() + b"synthetic-corruption")
            incomplete = run_frozen_m8_m31_handoff(
                candidate_path,
                manifest_path,
                reference_root,
                root / "incomplete-run",
                blastn_executable=str(blastn),
                makeblastdb_executable=str(makeblastdb),
            )
            self.assertEqual(incomplete["m8_execution_status"], "PARTIAL")
            self.assertEqual(
                incomplete["snapshot_provenance"]["snapshot_digest"],
                verified_snapshot["snapshot_digest"],
            )
            self.assertIn(
                incomplete["snapshot_provenance"]["reference_panel_state"],
                {"INVALID", "INCOMPLETE"},
            )
            self.assertTrue(all(
                result["outcome"] == "INSUFFICIENT_EVIDENCE"
                for result in incomplete["triage"]
            ))


if __name__ == "__main__":
    unittest.main()
