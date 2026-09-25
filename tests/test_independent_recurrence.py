import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import unittest

from satellite_discovery import artifact_contracts, artifact_workflow
from satellite_discovery.independent_recurrence import (
    OUTPUT_CONTRACTS,
    expected_input_types,
    run_stage,
)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


class IndependentRecurrenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_observation(
        self, name, sequence="ACGTACGT", *, sample_id="sample1",
        run_id="run1", study_id="PRJ1", source_key=None,
        m6_status="READ_SUPPORTED_ASSEMBLY", molecule_type="DNA",
        contig_status=None,
    ):
        folder = self.root / "inputs" / name
        folder.mkdir(parents=True, exist_ok=True)
        source_key = source_key or name
        sample_id = sample_id if sample_id is not None else "unknown"
        qc_hash = _sha("qc:" + source_key)
        reference_hash = _sha("reference")
        read_hash = _sha("reads:" + source_key)
        residual = {
            "schema": "m6-residual-manifest-v1",
            "status": "complete",
            "sample_id": sample_id,
            "source_reads": {
                "read1": {"path": "clean.fastq.gz", "sha256": read_hash},
            },
            "qc_artifact": {"path": "qc.json", "sha256": qc_hash},
            "comparison": {
                "status": "complete",
                "input_read_count": 4,
                "accounted_read_count": 4,
                "reference_sha256": reference_hash,
            },
            "counts": {
                "input_fragments": 4,
                "residual_fragments": 2,
                "eligible_fragments": 1,
                "retained_unassembled_fragments": 1,
            },
            "artifact_sha256": {},
        }
        if contig_status is None:
            contig_status = (
                "READ_SUPPORTED_ASSEMBLY"
                if m6_status == "READ_SUPPORTED_ASSEMBLY"
                else "LOW_SUPPORT_ASSEMBLY"
            )
        contigs = []
        fasta_path = None
        if m6_status in {"READ_SUPPORTED_ASSEMBLY", "NO_SUPPORTED_ASSEMBLY"}:
            contigs = [{
                "contig_id": "contig_1",
                "contig_length": len(sequence),
                "status": contig_status,
            }]
        if m6_status == "READ_SUPPORTED_ASSEMBLY":
            fasta_path = folder / "supported_contigs.fasta"
            fasta_path.write_text(
                ">contig_1 supported\n" + sequence + "\n", encoding="utf-8",
            )
        evidence = {
            "schema": "m6-reconstruction-evidence-v1",
            "status": m6_status,
            "sample_id": sample_id,
            "contigs": contigs,
            "configuration": {},
            "provenance": {
                "qc_sha256": qc_hash,
                "residual_manifest": "residual_manifest.json",
            },
            "reference_sha256": reference_hash,
        }
        evidence_path = _write_json(folder / "reconstruction_evidence.json", evidence)
        residual_path = _write_json(folder / "residual_manifest.json", residual)
        index = name.removeprefix("obs")
        evidence_input = "evidence" + index
        residual_input = "residual" + index
        contigs_input = "contigs" + index if fasta_path is not None else None
        row = {
            "observation_id": name,
            "candidate_id": "candidate-" + index,
            "sample_id": sample_id,
            "sequencing_run_id": run_id,
            "study_id": study_id,
            "source_artifact_id": "source-" + index,
            "m6_state": "available",
            "molecule_type": molecule_type,
            "evidence_input": evidence_input,
            "residual_manifest_input": residual_input,
        }
        inputs = {
            evidence_input: evidence_path,
            residual_input: residual_path,
        }
        if fasta_path is not None:
            inputs[contigs_input] = fasta_path
            row["contigs_input"] = contigs_input
        return row, inputs

    def evaluate(self, observations, *, orientation="forward_only", output_name="out"):
        config = {
            "observations": [row for row, _inputs in observations],
            "orientation_policy": orientation,
        }
        inputs = {}
        for _row, row_inputs in observations:
            inputs.update(row_inputs)
        output = self.root / output_name
        run_stage(inputs, output, config)
        values = {
            name: json.loads((output / name).read_text(encoding="utf-8"))
            for name in (
                "observations.json", "exact_recurrence.json",
                "recurrence_summary.json", "validation_report.json",
                "recurrence_provenance.json",
            )
        }
        return output, values

    def test_single_supported_observation_is_not_recurrence(self):
        observation = self.make_observation("obs1")
        _output, values = self.evaluate([observation])
        group = values["exact_recurrence.json"]["groups"][0]
        self.assertEqual(group["recurrence_categories"], ["SINGLE_OBSERVATION"])
        self.assertEqual(group["source_dataset_count"], 1)
        self.assertEqual(
            values["recurrence_summary.json"]["result_status"],
            "NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS",
        )

    def test_same_sample_recurrence_does_not_imply_different_runs(self):
        first = self.make_observation("obs1", run_id="run1")
        second = self.make_observation("obs2", run_id="run1")
        _output, values = self.evaluate([first, second])
        categories = values["exact_recurrence.json"]["groups"][0]["recurrence_categories"]
        self.assertIn("REPEATED_SAME_SAMPLE", categories)
        self.assertNotIn("RECURRENT_ACROSS_RUNS", categories)

    def test_different_runs_of_same_sample_are_reported_separately(self):
        first = self.make_observation("obs1", run_id="run1")
        second = self.make_observation("obs2", run_id="run2")
        _output, values = self.evaluate([first, second])
        categories = values["exact_recurrence.json"]["groups"][0]["recurrence_categories"]
        self.assertIn("REPEATED_SAME_SAMPLE", categories)
        self.assertIn("RECURRENT_ACROSS_RUNS", categories)

    def test_different_samples_are_reported_as_sample_recurrence(self):
        first = self.make_observation("obs1", sample_id="sample1")
        second = self.make_observation(
            "obs2", sample_id="sample2", run_id="run2",
        )
        _output, values = self.evaluate([first, second])
        categories = values["exact_recurrence.json"]["groups"][0]["recurrence_categories"]
        self.assertIn("RECURRENT_ACROSS_SAMPLES", categories)
        self.assertNotIn("RECURRENT_ACROSS_STUDIES", categories)

    def test_different_studies_are_reported_as_study_recurrence(self):
        first = self.make_observation(
            "obs1", sample_id="sample1", study_id="PRJ1",
        )
        second = self.make_observation(
            "obs2", sample_id="sample2", study_id="PRJ2", run_id="run2",
        )
        _output, values = self.evaluate([first, second])
        categories = values["exact_recurrence.json"]["groups"][0]["recurrence_categories"]
        self.assertIn("RECURRENT_ACROSS_STUDIES", categories)

    def test_reverse_complement_matching_is_explicit_and_dna_aware(self):
        forward = "ACGTTGCA"
        reverse = forward.translate(str.maketrans("ACGT", "TGCA"))[::-1]
        first = self.make_observation("obs1", sequence=forward)
        second = self.make_observation(
            "obs2", sequence=reverse, sample_id="sample2", run_id="run2",
        )
        _output, forward_values = self.evaluate(
            [first, second], output_name="forward",
        )
        self.assertEqual(len(forward_values["exact_recurrence.json"]["groups"]), 2)
        _output, normalized_values = self.evaluate(
            [first, second], orientation="reverse_complement_invariant",
            output_name="normalized",
        )
        groups = normalized_values["exact_recurrence.json"]["groups"]
        self.assertEqual(len(groups), 1)
        self.assertIn("RECURRENT_ACROSS_SAMPLES", groups[0]["recurrence_categories"])
        self.assertEqual(
            {member["orientation_to_canonical"] for member in groups[0]["members"]},
            {"forward", "reverse_complement"},
        )

    def test_reverse_complement_requires_explicit_molecule_type(self):
        row, inputs = self.make_observation("obs1", molecule_type="unknown")
        with self.assertRaisesRegex(ValueError, "explicit DNA or RNA"):
            run_stage(
                inputs, self.root / "unknown-orientation",
                {"observations": [row],
                 "orientation_policy": "reverse_complement_invariant"},
            )

    def test_similar_but_nonidentical_and_unrelated_sequences_stay_separate(self):
        first = self.make_observation("obs1", sequence="ACGTACGT")
        similar = self.make_observation(
            "obs2", sequence="ACGTACGA", sample_id="sample2", run_id="run2",
        )
        unrelated = self.make_observation(
            "obs3", sequence="CCCCCCCC", sample_id="sample3", run_id="run3",
        )
        _output, values = self.evaluate([first, similar, unrelated])
        groups = values["exact_recurrence.json"]["groups"]
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(group["source_dataset_count"] == 1 for group in groups))

    def test_missing_and_unknown_metadata_remain_unresolved(self):
        first = self.make_observation(
            "obs1", sample_id=None, run_id=None, study_id=None,
        )
        second = self.make_observation(
            "obs2", sample_id=None, run_id=None, study_id=None,
        )
        _output, values = self.evaluate([first, second])
        group = values["exact_recurrence.json"]["groups"][0]
        self.assertEqual(
            group["recurrence_categories"], ["RECURRENT_INDEPENDENCE_UNRESOLVED"],
        )
        obs = values["observations.json"]["observations"][0]
        self.assertIsNone(obs["sample_id"])
        self.assertEqual(obs["m6_sample_id"], "unknown")
        self.assertIn("sample_id", obs["metadata_missing"])
        self.assertIn("study_id", obs["metadata_missing"])

    def test_unsupported_m6_contig_is_never_promoted_by_recurrence(self):
        supported = self.make_observation("obs1", sequence="ACGTACGT")
        unsupported = self.make_observation(
            "obs2", sequence="ACGTACGT", sample_id="sample2",
            run_id="run2", m6_status="NO_SUPPORTED_ASSEMBLY",
            contig_status="LOW_SUPPORT_ASSEMBLY",
        )
        _output, values = self.evaluate([supported, unsupported])
        groups = values["exact_recurrence.json"]["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["source_dataset_count"], 1)
        self.assertEqual(groups[0]["observation_count"], 1)
        unsupported_row = next(
            row for row in values["observations.json"]["observations"]
            if row["observation_id"] == "obs2"
        )
        self.assertEqual(unsupported_row["evidence_class"], "UNSUPPORTED_RECONSTRUCTION")
        self.assertFalse(unsupported_row["contigs"][0]["evaluated_for_recurrence"])
        self.assertIsNone(unsupported_row["contigs"][0]["sequence_sha256"])

    def test_upstream_unavailable_and_failed_states_are_not_zero_recurrence(self):
        config = {
            "observations": [
                {
                    "observation_id": "obs-failed",
                    "m6_state": "failed",
                    "upstream_status": "execution_failed",
                    "upstream_reason": "M6 did not complete",
                    "sample_id": "unknown",
                    "study_id": None,
                },
                {
                    "observation_id": "obs-unavailable",
                    "m6_state": "unavailable",
                    "upstream_status": "dependency_missing",
                    "sample_id": None,
                    "study_id": None,
                },
            ],
        }
        output = self.root / "upstream-state"
        run_stage({}, output, config)
        summary = json.loads(
            (output / "recurrence_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["result_status"], "UPSTREAM_UNAVAILABLE_OR_FAILED")
        self.assertEqual(summary["exact_group_count"], 0)
        validation = json.loads(
            (output / "validation_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validation["failed_count"], 1)
        self.assertEqual(validation["unavailable_count"], 1)

    def test_available_m6_dependency_failure_remains_unavailable(self):
        row, inputs = self.make_observation(
            "obs1", m6_status="DEPENDENCY_UNAVAILABLE",
        )
        output, values = self.evaluate([(row, inputs)])
        self.assertEqual(
            values["observations.json"]["observations"][0]["evidence_class"],
            "UPSTREAM_UNAVAILABLE",
        )
        self.assertEqual(
            values["recurrence_summary.json"]["result_status"],
            "UPSTREAM_UNAVAILABLE_OR_FAILED",
        )

    def test_corrupted_supported_contig_artifact_fails_closed(self):
        row, inputs = self.make_observation("obs1")
        inputs[row["contigs_input"]].write_text(">contig_1\nACGT*\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            run_stage(inputs, self.root / "corrupted", {"observations": [row]})

    def test_changed_sequence_invalidates_reuse(self):
        row, inputs = self.make_observation("obs1")
        output, _values = self.evaluate([(row, inputs)], output_name="reuse")
        before = (output / "exact_recurrence.json").read_bytes()
        inputs[row["contigs_input"]].write_text(
            ">contig_1\nACGTACGA\n", encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "configuration or implementation changed"):
            run_stage(inputs, output, {"observations": [row]})
        self.assertEqual((output / "exact_recurrence.json").read_bytes(), before)

    def test_changed_independence_metadata_invalidates_reuse(self):
        first = self.make_observation("obs1", study_id="PRJ1")
        second = self.make_observation(
            "obs2", sample_id="sample2", study_id="PRJ2", run_id="run2",
        )
        output, _values = self.evaluate([first, second], output_name="metadata-reuse")
        config = {
            "observations": [first[0], second[0]],
        }
        config["observations"][1] = {
            **config["observations"][1], "study_id": "PRJ1",
        }
        with self.assertRaisesRegex(ValueError, "configuration or implementation changed"):
            run_stage(
                {**first[1], **second[1]}, output, config,
            )
        _other_output, values = self.evaluate(
            [first, (config["observations"][1], second[1])],
            output_name="metadata-changed",
        )
        categories = values["exact_recurrence.json"]["groups"][0]["recurrence_categories"]
        self.assertNotIn("RECURRENT_ACROSS_STUDIES", categories)

    def test_same_read_artifacts_do_not_create_independent_observations(self):
        first = self.make_observation("obs1", source_key="same-dataset")
        second = self.make_observation(
            "obs2", source_key="same-dataset", sample_id="sample1",
        )
        _output, values = self.evaluate([first, second])
        group = values["exact_recurrence.json"]["groups"][0]
        self.assertEqual(group["observation_count"], 2)
        self.assertEqual(group["source_dataset_count"], 1)
        self.assertEqual(group["recurrence_categories"], ["SINGLE_OBSERVATION"])

    def test_output_order_is_deterministic_and_inputs_are_not_modified(self):
        first = self.make_observation("obs1", sequence="ACGTACGT")
        second = self.make_observation(
            "obs2", sequence="ACGTACGT", sample_id="sample2", run_id="run2",
        )
        input_bytes = {
            str(path): path.read_bytes()
            for _row, paths in (first, second) for path in paths.values()
        }
        _out_a, values_a = self.evaluate(
            [first, second], output_name="ordered-a",
        )
        _out_b, values_b = self.evaluate(
            [second, first], output_name="ordered-b",
        )
        self.assertEqual(
            [row["observation_id"] for row in values_a["observations.json"]["observations"]],
            ["obs1", "obs2"],
        )
        self.assertEqual(
            values_a["exact_recurrence.json"]["groups"],
            values_b["exact_recurrence.json"]["groups"],
        )
        for name, before in input_bytes.items():
            self.assertEqual(Path(name).read_bytes(), before)

    def test_paths_and_input_names_are_portable(self):
        row, inputs = self.make_observation("obs1")
        bad = {**row, "evidence_input": "../evidence"}
        with self.assertRaises(ValueError):
            expected_input_types({"observations": [bad]})
        self.assertTrue(all(contract in artifact_contracts.contract_names()
                            for contract in OUTPUT_CONTRACTS.values()))
        output, _values = self.evaluate([(row, inputs)], output_name="folder with spaces")
        self.assertTrue((output / "report.html").is_file())

    def test_workflow_registry_requires_role_correct_typed_inputs(self):
        row, inputs = self.make_observation("obs1")
        config = {"observations": [row]}
        workflow_inputs = {
            row["evidence_input"]: {
                "path": str(inputs[row["evidence_input"]]),
                "artifact_type": "reconstruction_evidence",
            },
            row["residual_manifest_input"]: {
                "path": str(inputs[row["residual_manifest_input"]]),
                "artifact_type": "residual_read_manifest",
            },
            row["contigs_input"]: {
                "path": str(inputs[row["contigs_input"]]),
                "artifact_type": "canonical_contig_fasta",
            },
        }
        spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "recurrence",
                "kind": "independent_recurrence",
                "inputs": workflow_inputs,
                "config": config,
            }],
        }
        artifact_workflow.validate(spec)
        for root in (
            PurePosixPath("/tmp/M7 inputs with spaces"),
            PureWindowsPath(r"C:\M7 inputs with spaces"),
        ):
            portable_spec = json.loads(json.dumps(spec))
            for name, value in portable_spec["stages"][0]["inputs"].items():
                value["path"] = str(root / (name + ".json"))
            artifact_workflow.validate(portable_spec)
        invalid = json.loads(json.dumps(spec))
        invalid["stages"][0]["inputs"][row["evidence_input"]]["artifact_type"] = "raw_read"
        with self.assertRaises(ValueError):
            artifact_workflow.validate(invalid)

    def test_workflow_runs_m7_and_verifies_declared_outputs(self):
        row, inputs = self.make_observation("obs1")
        config = {"observations": [row]}
        typed_inputs = {
            name: {
                "path": str(inputs[name]),
                "artifact_type": artifact_type,
            }
            for name, artifact_type in expected_input_types(config).items()
        }
        spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "recurrence",
                "kind": "independent_recurrence",
                "inputs": typed_inputs,
                "config": config,
            }],
        }
        spec_path = _write_json(self.root / "workflow.json", spec)
        output = self.root / "workflow-output"
        artifact_workflow.run(spec_path, output)

        workflow_report = json.loads(
            (output / "workflow.json").read_text(encoding="utf-8")
        )
        self.assertEqual(workflow_report["status"], "complete")
        stage = next(
            item for item in workflow_report["stages"]
            if item["id"] == "recurrence"
        )
        self.assertEqual(stage["status"], "complete")

        stage_output = output / "recurrence"
        stage_manifest = json.loads(
            (stage_output / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(stage_manifest["status"], "complete")
        for name in OUTPUT_CONTRACTS:
            artifact = stage_output / name
            self.assertTrue(artifact.is_file(), name)
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(stage_manifest["output_sha256"][name], digest)
        recurrence = json.loads(
            (stage_output / "exact_recurrence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(recurrence["groups"]), 1)

    def test_m7_accepts_only_m6_artifacts_not_raw_reads(self):
        allowed = set(artifact_workflow.DEFAULT_STAGE_REGISTRY.get(
            "independent_recurrence"
        ).input_contracts["*"])
        self.assertEqual(
            allowed,
            {"canonical_contig_fasta", "reconstruction_evidence",
             "residual_read_manifest"},
        )
        self.assertNotIn("raw_read", allowed)
        self.assertEqual(
            set(OUTPUT_CONTRACTS),
            {
                "observations.json", "exact_recurrence.json",
                "recurrence_summary.json", "validation_report.json",
                "recurrence_provenance.json", "report.html",
            },
        )


if __name__ == "__main__":
    unittest.main()