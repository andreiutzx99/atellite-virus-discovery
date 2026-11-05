import json
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m28_synthetic_assembly_diagnostics import (
    FOLLOW_UP_SCIENTIFIC_LIMITATION,
    _experimental_comparison,
    _failure_class,
    _fastq_with_metadata,
    _read_support_diagnostics,
    _validate_experiment_execution,
    render_markdown,
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
            "memory_gb": 2,
            "memory_mb": 2048,
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

    def test_zero_support_distinguishes_no_alignments_from_rejected_alignments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reads = root / "reads.fastq"
            reads.write_text("@r1\nACGT\n+\nIIII\n")
            contigs = root / "contigs.fasta"
            contigs.write_text(">alt\nACGT\n")
            sam = root / "support.sam"
            sam.write_text(
                "@SQ\tSN:alt\tLN:4\n"
                "r1\t4\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n"
            )
            _, metadata = _fastq_with_metadata(reads)
            thresholds = {
                "min_mapq": 20, "min_alignment_fraction": 0.8,
                "min_sequence_identity": 0.95,
            }
            absent = assess_read_support(
                sam, contigs, metadata, paired=False, thresholds=thresholds,
            )
            absent_summary = _read_support_diagnostics(absent, thresholds)
            self.assertEqual(absent_summary["primary_reads"]["mapped"], 0)
            self.assertEqual(absent_summary["contigs"][0]["qualifying_supporting_read_count"], 0)
            self.assertEqual(
                absent_summary["contigs"][0]["zero_qualifying_support_interpretation"],
                "NO_PRIMARY_READS_ALIGNED_TO_CONTIG",
            )

            sam.write_text(
                "@SQ\tSN:alt\tLN:4\n"
                "r1\t0\talt\t1\t0\t4M\t*\t0\t0\tACGT\tIIII\tNM:i:0\n"
            )
            rejected = assess_read_support(
                sam, contigs, metadata, paired=False, thresholds=thresholds,
            )
            rejected_summary = _read_support_diagnostics(rejected, thresholds)
            self.assertEqual(rejected_summary["primary_reads"]["mapped"], 1)
            self.assertEqual(
                rejected_summary["primary_reads"]["mapped_rejected_by_one_or_more_support_criteria"],
                1,
            )
            self.assertEqual(rejected_summary["mapped_reads_rejected_by_criterion"]["mapq"], 1)
            self.assertEqual(rejected_summary["contigs"][0]["mapped_primary_read_count"], 1)
            self.assertEqual(rejected_summary["contigs"][0]["qualifying_supporting_read_count"], 0)
            self.assertEqual(
                rejected_summary["contigs"][0]["zero_qualifying_support_interpretation"],
                "MAPPED_ALIGNMENTS_REJECTED_BY_CONFIGURED_CRITERIA",
            )

    def test_spades_memory_metadata_matches_command_units(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline, experiment, reads = self._execution_fixture(Path(temp))
            manifest_path = experiment / "execution.json"
            manifest = json.loads(manifest_path.read_text())
            memory_index = manifest["command_parameters"].index("-m")
            self.assertEqual(manifest["command_parameters"][memory_index + 1], "2")
            self.assertEqual(manifest["memory_gb"], 2)
            self.assertEqual(manifest["memory_mb"], 2048)
            self.assertEqual(
                _validate_experiment_execution(experiment, reads, "a" * 64)["status"],
                "COMPLETED",
            )

            manifest["memory_mb"] = 2
            manifest_path.write_text(json.dumps(manifest))
            result = _validate_experiment_execution(experiment, reads, "a" * 64)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["manifest"]["memory_mb"], 2048)
            self.assertEqual(
                result["manifest"]["memory_metadata_correction"]["previous_memory_mb"],
                2,
            )

    def test_report_labels_historical_results_and_unavailable_measurements(self):
        report_path = Path(__file__).parents[1] / "docs" / (
            "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.json"
        )
        report = json.loads(report_path.read_text())
        status = report["follow_up_evidence_status"]
        self.assertEqual(status["original_experimental_results"], "DOCUMENTED_HISTORICAL_RESULTS")
        self.assertEqual(
            status["per_partition"]["development"]["mapped_primary_reads"],
            "NOT_SUPPLIED",
        )
        self.assertEqual(
            status["per_partition"]["development"]["total_input_reads_historically_recorded"],
            432,
        )
        self.assertEqual(status["scientific_limitation"], FOLLOW_UP_SCIENTIFIC_LIMITATION)
        markdown = render_markdown(report)
        self.assertIn(FOLLOW_UP_SCIENTIFIC_LIMITATION, markdown)
        self.assertIn("EXPERIMENTS_NOT_RERUN", status["current_verification"])
        for run in report["controlled_experiment"]["runs"]:
            execution = run["assembler_execution"]
            memory_index = execution["command_parameters"].index("-m")
            self.assertEqual(execution["command_parameters"][memory_index + 1], "2")
            self.assertEqual(execution["memory_gb"], 2)
            self.assertEqual(execution["memory_mb"], 2048)

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
            self.assertEqual(
                result["runs"][0]["experimental_configuration_B"]["read_support"]
                ["read_evidence"]["primary_reads"]["unmapped"],
                1,
            )


if __name__ == "__main__":
    unittest.main()
