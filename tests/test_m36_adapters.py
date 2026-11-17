import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m36_adapters import (
    M36Phase2BAttemptAdapter,
    run_unregistered_fixture,
    triage_m8_outputs,
)
from satellite_discovery.m36_preparation import RunnerBlocked
from satellite_discovery import m31_synthetic_evidence_screening as m31


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
            if os.name == "posix":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)

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


if __name__ == "__main__":
    unittest.main()
