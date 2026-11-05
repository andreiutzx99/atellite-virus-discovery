import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery.m32_end_to_end_synthetic_evidence import (
    _handoff, validate_handoff, validate_success_criteria,
)


class M32HandoffTests(unittest.TestCase):
    def _fixture(self, root, *, support_status="READ_SUPPORTED_ASSEMBLY",
                 evidence_status="READ_SUPPORTED_ASSEMBLY"):
        root = Path(root)
        (root / "assembly").mkdir()
        (root / "assembly" / "contigs.fasta").write_text(">contig-A\nACGTACGT\n")
        (root / "read_support.json").write_text("{}\n")
        (root / "reconstruction_evidence.json").write_text(
            json.dumps({"status": evidence_status}) + "\n")
        (root / "candidate_sequence_set.json").write_text(json.dumps({
            "records": [{"candidate_id": "contig-A",
                         "sequence_sha256": hashlib.sha256(b"ACGTACGT").hexdigest(),
                         "m6_support_status": support_status}]
        }))
        return {
            "contig-A": {"fasta_record_id": "contig-A", "sequence_length": 8,
                         "sequence_sha256": hashlib.sha256(b"ACGTACGT").hexdigest()}
        }, [{"contig_id": "contig-A", "status": support_status}]

    def test_sequence_digest_mismatch_blocks_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            expected, support = self._fixture(temp)
            expected["contig-A"]["sequence_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "IDs or sequence digests mismatch"):
                validate_handoff(temp, expected, support)

    def test_swapped_candidate_identifier_blocks_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            expected, support = self._fixture(temp)
            expected["contig-B"] = expected.pop("contig-A")
            with self.assertRaisesRegex(ValueError, "IDs or sequence digests mismatch"):
                validate_handoff(temp, expected, support)

    def test_missing_assembly_fasta_does_not_create_a_candidate_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "m6-output"
            (source / "assembly").mkdir(parents=True)
            self.assertIsNone(_handoff(source, Path(temp) / "handoff", "missing-assembly"))

    def test_missing_measured_support_blocks_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            expected, _ = self._fixture(temp)
            with patch("satellite_discovery.m32_end_to_end_synthetic_evidence."
                       "m8_candidate_handoff.validate_candidate_sequence_set",
                       return_value={"record_count": 1}):
                with self.assertRaisesRegex(ValueError, "Measured support does not bind"):
                    validate_handoff(temp, expected, [])

    def test_unavailable_reconstruction_is_not_a_successful_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            expected, support = self._fixture(temp, evidence_status="NOT_SUPPLIED")
            with patch("satellite_discovery.m32_end_to_end_synthetic_evidence."
                       "m8_candidate_handoff.validate_candidate_sequence_set",
                       return_value={"record_count": 1}):
                with self.assertRaisesRegex(ValueError, "incomplete or failed"):
                    validate_handoff(temp, expected, support)

    def test_success_requires_held_out_support_handoff_and_completed_m8(self):
        report = {
            "benchmark_metrics": {"cases": [{
                "case_id": "held-out-positive", "split": "held_out",
                "positive_control": True, "assembly_recovery": True,
                "supported_exact_recovery": True, "m6_to_m8_handoff": True,
                "m8_search_complete": True, "target_absent": False,
            }, {
                "case_id": "held-out-negative", "split": "held_out",
                "positive_control": False, "assembly_recovery": False,
                "supported_exact_recovery": False, "m6_to_m8_handoff": False,
                "m8_search_complete": False, "target_absent": True,
            }]},
            "candidate_triage": [
                {"case_id": "held-out-positive",
                 "outcome": [{"outcome": "REVIEW_PRIORITY"}], "raw_outputs": []},
                {"case_id": "held-out-negative", "outcome": "INSUFFICIENT_EVIDENCE",
                 "raw_outputs": []},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            validate_success_criteria(report, temp)
            report["benchmark_metrics"]["cases"][0]["supported_exact_recovery"] = False
            with self.assertRaisesRegex(RuntimeError, "held-out positive"):
                validate_success_criteria(report, temp)


if __name__ == "__main__":
    unittest.main()
