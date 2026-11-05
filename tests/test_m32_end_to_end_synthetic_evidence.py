import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery.m32_end_to_end_synthetic_evidence import (
    _benchmark_design, _handoff, _m8_workflow_spec, preregistered_panel,
    validate_handoff, validate_success_criteria,
)
from satellite_discovery import m29_assembly_root_cause_recovery as m29


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

    def _success_fixture(self, known_outcome="REVIEW_PRIORITY"):
        report = {
            "benchmark_metrics": {"cases": [{
                "case_id": "held-out-positive", "split": "held_out",
                "positive_control": True, "experiment_type": "known_reference_positive",
                "expected_triage_outcome": "REVIEW_PRIORITY", "reference_panel_status": "PRESENT",
                "assembly_recovery": True, "exact_contig_ids": ["target"],
                "supported_exact_recovery": True, "supported_exact_contig_ids": ["target"],
                "supported_contig_ids": ["target"], "m6_to_m8_handoff": True,
                "m8_search_complete": True, "target_absent": False,
            }, {
                "case_id": "held-out-independent", "split": "held_out",
                "positive_control": True, "experiment_type": "reference_independent_challenge",
                "expected_triage_outcome": "INSUFFICIENT_EVIDENCE", "reference_panel_status": "ABSENT",
                "assembly_recovery": True, "exact_contig_ids": ["unseen"],
                "supported_exact_recovery": True, "supported_exact_contig_ids": ["unseen"],
                "supported_contig_ids": ["unseen"], "m6_to_m8_handoff": True,
                "m8_search_complete": True, "target_absent": False,
            }, {
                "case_id": "held-out-negative", "split": "held_out",
                "positive_control": False, "assembly_recovery": False,
                "experiment_type": "target_absent_no_contig",
                "expected_triage_outcome": "INSUFFICIENT_EVIDENCE",
                "reference_panel_status": "NOT_APPLICABLE",
                "supported_exact_recovery": False, "m6_to_m8_handoff": False,
                "exact_contig_ids": [], "supported_exact_contig_ids": [],
                "supported_contig_ids": [], "m8_search_complete": False, "target_absent": True,
            }, {
                "case_id": "held-out-background", "split": "held_out",
                "positive_control": False, "experiment_type": "target_absent_supported_background",
                "expected_triage_outcome": "INSUFFICIENT_EVIDENCE",
                "reference_panel_status": "NOT_APPLICABLE",
                "supported_contig_ids": [], "supported_exact_contig_ids": [],
                "m6_to_m8_handoff": False, "m8_search_complete": False,
            }]},
            "candidate_triage": [
                {"case_id": "held-out-positive",
                 "outcome": [{"candidate_id": "target", "outcome": known_outcome}], "raw_outputs": []},
                {"case_id": "held-out-independent",
                 "outcome": [{"candidate_id": "unseen", "outcome": "INSUFFICIENT_EVIDENCE"}],
                 "raw_outputs": []},
                {"case_id": "held-out-negative", "outcome": "INSUFFICIENT_EVIDENCE",
                 "reason": "M6 produced no assembled contigs; M8 was not run.",
                 "raw_outputs": []},
                {"case_id": "held-out-background", "outcome": "INSUFFICIENT_EVIDENCE",
                 "raw_outputs": []},
            ],
        }
        return report

    def test_known_reference_requires_exact_supported_contig_and_expected_triage(self):
        report = self._success_fixture()
        with tempfile.TemporaryDirectory() as temp:
            validate_success_criteria(report, temp)
            report["benchmark_metrics"]["cases"][0]["supported_exact_contig_ids"] = []
            with self.assertRaisesRegex(RuntimeError, "expected triage outcome"):
                validate_success_criteria(report, temp)

    def test_unfavourable_known_reference_triage_does_not_pass(self):
        for outcome in ("BACKGROUND_LIKE", "CONFLICTING_EVIDENCE", "INSUFFICIENT_EVIDENCE"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(RuntimeError, "expected triage outcome"):
                    validate_success_criteria(self._success_fixture(outcome), temp)

    def test_unrelated_contig_cannot_supply_known_reference_success(self):
        report = self._success_fixture("INSUFFICIENT_EVIDENCE")
        report["candidate_triage"][0]["outcome"].append(
            {"candidate_id": "unrelated", "outcome": "REVIEW_PRIORITY"})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "expected triage outcome"):
                validate_success_criteria(report, temp)

    def test_supported_absent_background_must_complete_real_m8_screening(self):
        report = self._success_fixture()
        background = report["benchmark_metrics"]["cases"][3]
        background["supported_contig_ids"] = ["background-contig"]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "supported background contigs"):
                validate_success_criteria(report, temp)

    def test_supported_absent_background_must_abstain_after_m8(self):
        report = self._success_fixture()
        background = report["benchmark_metrics"]["cases"][3]
        background.update({
            "supported_contig_ids": ["background-contig"],
            "m6_to_m8_handoff": True,
            "m8_search_complete": True,
        })
        triage = report["candidate_triage"][3]
        triage["candidate_records"] = [{
            "candidate_id": "background-contig", "triage_status": "INSUFFICIENT_EVIDENCE",
        }]
        with tempfile.TemporaryDirectory() as temp:
            validate_success_criteria(report, temp)
            triage["candidate_records"][0]["triage_status"] = "REVIEW_PRIORITY"
            with self.assertRaisesRegex(RuntimeError, "pre-registered abstention"):
                validate_success_criteria(report, temp)

    def test_panel_and_m8_inputs_are_independent_of_heldout_truth(self):
        cases, _ = _benchmark_design(m29.case_matrix())
        sequences_before, panel_before = preregistered_panel(cases)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            truth = root / "heldout_truth.json"
            truth.write_text('{"candidate_sequence":"AAAA"}')
            candidate, manifest, fasta, index = [root / name for name in
                                                  ("candidate.json", "manifest.json", "panel.fasta", "panel.nhr")]
            for path in (candidate, manifest, fasta, index):
                path.write_text(path.name)
            spec_before = _m8_workflow_spec(
                cases[3], {"path": candidate}, root, manifest, fasta, [index],
                "blastn", "makeblastdb")
            truth.write_text('{"candidate_sequence":"CCCC"}')
            sequences_after, panel_after = preregistered_panel(cases)
            spec_after = _m8_workflow_spec(
                cases[3], {"path": candidate}, root, manifest, fasta, [index],
                "blastn", "makeblastdb")
            self.assertEqual(sequences_before, sequences_after)
            self.assertEqual(panel_before, panel_after)
            self.assertEqual(spec_before, spec_after)

    def test_known_reference_and_reference_absent_experiments_are_distinct(self):
        cases, contracts = _benchmark_design(m29.case_matrix())
        _, panel = preregistered_panel(cases)
        self.assertEqual(contracts["held_out-m29-positive_control"]["experiment_type"],
                         "known_reference_positive")
        self.assertEqual(contracts["held_out-m29-sequencing_errors"]["experiment_type"],
                         "reference_independent_challenge")
        self.assertIn("held_out-m29-sequencing_errors", panel["reference_independent_case_ids"])


if __name__ == "__main__":
    unittest.main()
