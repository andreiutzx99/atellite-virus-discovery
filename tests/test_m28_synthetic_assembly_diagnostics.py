import json
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m28_synthetic_assembly_diagnostics import (
    _experimental_comparison,
    _failure_class,
    _fastq_with_metadata,
    _validate_experiment_execution,
    sequence_diagnostics,
)
from satellite_discovery.read_support import assess_read_support


class M28SyntheticAssemblyDiagnosticsTests(unittest.TestCase):
    def _execution_fixture(self, root, *, status="COMPLETED", return_code=0,
                            input_sha=None, support=True):
        baseline = root / "baseline"
        stage = baseline / "development/development-m25-02/stages/m6_m2502"
        stage.mkdir(parents=True)
        reads = stage / "eligible_read1.fastq.gz"
        with gzip.open(reads, "wt") as stream:
            stream.write("@r1\nACGT\n+\nIIII\n")
        input_sha = input_sha or hashlib.sha256(reads.read_bytes()).hexdigest()
        (stage / "candidate_sequences.fasta").write_text(">default\nACGT\n")
        (stage / "assembly/assembly_manifest.json").parent.mkdir(parents=True)
        (stage / "assembly/assembly_manifest.json").write_text(
            json.dumps({"parameters": {"assembler": "spades"}})
        )
        thresholds = {"min_mapq": 20, "min_alignment_fraction": 0.8}
        (stage / "read_support.json").write_text(json.dumps({"configuration": thresholds}))
        (baseline / "m25-read-coverage.json").write_text(json.dumps({
            "cases": [{
                "case_id": "development-m25-02",
                "analysis_id": "m2502",
                "input_manifest_sha256": "a" * 64,
                "positive": True,
                "pipeline": {"exact_recovery": False},
            }]
        }))
        (baseline / "development/development-m25-02/heldout_truth.json").write_text(
            json.dumps({"cases": [{"candidate_sequence": "ACGT"}]})
        )

        experiment = root / "experiment/development"
        experiment.mkdir(parents=True)
        contigs = experiment / "contigs.fasta"
        contigs.write_text(">alt\nACGT\n")
        output_bytes = contigs.read_bytes()
        manifest = {
            "schema": "m28-experimental-assembly-execution-v1",
            "case_id": "development-m25-02",
            "split": "development",
            "status": status,
            "return_code": return_code,
            "input_manifest_sha256": "a" * 64,
            "input": {
                "artifact_name": reads.name,
                "bytes": reads.stat().st_size,
                "sha256": input_sha,
            },
            "command_parameters": ["--only-assembler", "-t", "1", "-m", "2", "-k", "21,33"],
            "output": {
                "artifact_name": contigs.name,
                "bytes": len(output_bytes),
                "sha256": hashlib.sha256(output_bytes).hexdigest(),
                "record_count": 1,
            },
        }
        (experiment / "execution.json").write_text(json.dumps(manifest))
        if support:
            sam_path = experiment / "support_alignments.sam"
            sam_path.write_text(
                "@SQ\tSN:alt\tLN:4\n"
                "r1\t4\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n"
            )
            read_ids, metadata = _fastq_with_metadata(reads)
            assessed = assess_read_support(
                sam_path, contigs, metadata, paired=False, thresholds=thresholds,
            )
            (experiment / "read_support.json").write_text(json.dumps({
                "schema": "m28-experimental-read-support-v1",
                "status": "EVALUATED",
                "aggregate_status": assessed["status"],
                "contigs": assessed["contigs"],
                "mapper_execution": {
                    "return_code": 0,
                    "input_reads_sha256": hashlib.sha256(reads.read_bytes()).hexdigest(),
                    "contigs_sha256": hashlib.sha256(output_bytes).hexdigest(),
                    "sam_sha256": hashlib.sha256(sam_path.read_bytes()).hexdigest(),
                    "query_count": len(read_ids),
                    "thresholds": thresholds,
                },
            }))
        return baseline, experiment, reads

    def test_unique_and_repeated_kmers_are_described(self):
        unique = sequence_diagnostics("ACGTTGCA", k=4)
        repeated = sequence_diagnostics("ACGTACGT", k=4)
        self.assertEqual(unique["length"], 8)
        self.assertEqual(unique["unique_kmer_fraction"], 1.0)
        self.assertLess(repeated["unique_kmer_fraction"], 1.0)
        self.assertGreater(repeated["maximum_kmer_multiplicity"], 1)

    def test_upstream_failure_is_not_called_assembler_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / "stages/m6_fixture"
            stage.mkdir(parents=True)
            (stage / "manifest.json").write_text(json.dumps({"status": "failed"}))
            self.assertEqual(
                _failure_class(root, {"analysis_id": "fixture"}),
                "UPSTREAM_STAGE_FAILURE",
            )

    def test_missing_output_is_not_inferred_as_scientific_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / "stages/m6_fixture"
            stage.mkdir(parents=True)
            (stage / "manifest.json").write_text(json.dumps({"status": "complete"}))
            self.assertEqual(
                _failure_class(root, {"analysis_id": "fixture"}),
                "OUTPUT_MISSING_OR_NOT_EVALUATED",
            )

    def test_missing_execution_evidence_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as temp:
            result = _validate_experiment_execution(
                Path(temp), Path(temp) / "reads.fastq.gz", "a" * 64
            )
            self.assertEqual(result["status"], "NOT_EVALUATED")

    def test_malformed_and_incomplete_execution_records_are_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "execution.json").write_text("{bad json")
            self.assertEqual(
                _validate_experiment_execution(root, root / "reads", "a" * 64)["status"],
                "INCOMPLETE",
            )
            (root / "execution.json").write_text(json.dumps({"status": "COMPLETED"}))
            self.assertEqual(
                _validate_experiment_execution(root, root / "reads", "a" * 64)["status"],
                "INCOMPLETE",
            )

    def test_failed_execution_cannot_be_overridden_by_stale_fasta(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline, experiment, reads = self._execution_fixture(
                Path(temp), status="FAILED", return_code=21,
            )
            result = _validate_experiment_execution(
                experiment, reads, "a" * 64,
            )
            self.assertEqual(result["status"], "FAILED")

    def test_wrong_paired_input_identity_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline, experiment, reads = self._execution_fixture(
                Path(temp), input_sha="0" * 64,
            )
            result = _validate_experiment_execution(
                experiment, reads, "a" * 64,
            )
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIn("input identity", result["reason"])

    def test_missing_read_support_prevents_complete_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline, experiment, _ = self._execution_fixture(
                Path(temp), support=False,
            )
            result = _experimental_comparison(baseline, experiment.parent)
            self.assertEqual(result["runs"][0]["status"], "INCOMPLETE")
            self.assertEqual(result["runs"][0]["read_back_support"]["status"], "NOT_EVALUATED")

    def test_successful_comparison_reports_unsupported_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline, experiment, _ = self._execution_fixture(Path(temp))
            result = _experimental_comparison(baseline, experiment.parent)
            self.assertEqual(result["runs"][0]["status"], "COMPLETE")
            self.assertEqual(
                len(result["runs"][0]["experimental_configuration_B"]["read_support"]
                     ["candidates_by_support"]["unsupported"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
