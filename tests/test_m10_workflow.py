import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import artifact_contracts, artifact_workflow, m10_contracts
from tests.test_m8_contracts import M8ContractTests


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _candidate_set(root, sequence="ACGTACGT"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    candidate_path, document = M8ContractTests()._candidate_set(root)
    fasta_path = root / document["availability"]["fasta_artifact"]["path"]
    fasta_bytes = (
        f">source-a synthetic\n{sequence}\n"
        f">source-b synthetic\n{sequence}\n"
    ).encode("ascii")
    fasta_path.write_bytes(fasta_bytes)
    document["availability"]["fasta_artifact"]["sha256"] = _sha(fasta_bytes)

    source_ref = document["source_artifact"]
    source_path = root / source_ref["path"]
    source_bytes = fasta_bytes
    source_path.write_bytes(source_bytes)
    source_ref["sha256"] = _sha(source_bytes)
    for record in document["records"]:
        record.update(
            sequence_length=len(sequence),
            sequence_sha256=_sha(sequence.encode("ascii")),
            source_artifact_sha256=source_ref["sha256"],
            molecule_type="DNA",
            completeness_state="COMPLETE",
        )
    candidate_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return candidate_path


class M10WorkflowTests(unittest.TestCase):
    def test_source_bound_evidence_rejects_mismatches_and_nonmaximal_rows(self):
        candidate = {"source_sequence": "ACGTACGT", "molecule_type": "DNA"}
        terminal = {
            "source_intervals": [[0, 4], [4, 8]],
            "orientation": "DIRECT",
            "relationship_class": "SUFFIX_PREFIX",
        }
        self.assertTrue(m10_contracts._matches_source(candidate, terminal))
        self.assertFalse(m10_contracts._matches_source({
            **candidate, "source_sequence": "ACGTTCGT",
        }, terminal))

        nonmaximal = {
            "source_intervals": [[2, 4], [6, 8]],
            "orientation": "DIRECT",
            "relationship_class": "INTERNAL_DIRECT_REPEAT",
        }
        self.assertFalse(m10_contracts._matches_source({
            "source_sequence": "TGACTGACTTT",
            "molecule_type": "DNA",
        }, nonmaximal))

    def test_cache_key_tracks_only_supplied_context_contract_semantics(self):
        registry = artifact_workflow.build_default_registry()
        definition = registry.get("m10_exact_first")
        stage = {"id": "m10", "kind": "m10_exact_first"}
        candidate = {
            "candidate_sequence_set": {
                "sha256": "a" * 64,
                "artifact_type": "m8_candidate_sequence_set",
            },
        }

        def key(inputs):
            return artifact_workflow._stage_cache_key(
                stage, definition, {}, inputs, {}, None)

        baseline = key(candidate)
        context = {
            **candidate,
            "m9_orf_results": {
                "sha256": "b" * 64,
                "artifact_type": "m9_orf_results",
            },
        }
        context_baseline = key(context)
        with patch.dict(
                artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
                {"m9_orf_results": "test-semantic-change"}):
            self.assertEqual(key(candidate), baseline)
            self.assertNotEqual(key(context), context_baseline)
        with patch.object(
                definition.handler,
                "cache_input_contract_semantics_version",
                "test-cache-semantics-change"):
            self.assertNotEqual(key(candidate), baseline)

    def test_synthetic_workflow_emits_verified_typed_results_and_reuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path = _candidate_set(root / "candidate")
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps({
                "schema": "artifact-workflow-v1",
                "stages": [{
                    "id": "m10",
                    "kind": "m10_exact_first",
                    "inputs": {
                        "candidate_sequence_set": {
                            "path": "candidate/candidate_sequence_set.json",
                            "artifact_type": "m8_candidate_sequence_set",
                        },
                    },
                    "config": {},
                }],
            }), encoding="utf-8")
            output = root / "out"
            registry = artifact_workflow.build_default_registry()

            artifact_workflow.run(spec_path, output, registry)
            state = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            stage = state["stages"][0]
            self.assertEqual(stage["status"], "complete")
            stage_output = output / stage["output_path"]
            bundle_path = stage_output / "m10_bundle.json"
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["aggregate_status"], "COMPLETE")
            self.assertEqual(bundle["candidate_count"], 2)
            self.assertEqual(
                bundle["source_inputs"]["optional_context_state"]["m7"]["state"],
                "NOT_SUPPLIED",
            )
            evidence_count = artifact_contracts.validate_artifact(
                stage_output / "repeat_evidence.jsonl",
                "m10_repeat_evidence")["record_count"]
            self.assertEqual(
                artifact_contracts.validate_artifact(
                    bundle_path, "m10_result_bundle")["evidence_count"],
                evidence_count,
            )
            accounting = artifact_contracts.validate_artifact(
                stage_output / "candidate_accounting.jsonl",
                "m10_candidate_accounting")
            self.assertEqual(accounting["candidate_count"], 2)
            self.assertEqual(accounting["aggregate_status"], "COMPLETE")
            accounting_rows = [
                json.loads(line)
                for line in (stage_output / "candidate_accounting.jsonl")
                .read_text(encoding="utf-8").splitlines()
            ]
            candidate_record = accounting_rows[1]
            self.assertEqual(
                candidate_record["source_alphabet"]["observed_symbols"],
                ["A", "C", "G", "T"],
            )
            self.assertEqual(
                candidate_record["comparison_view"]["policy"],
                "M10-COMPARE-IUPAC-v1",
            )
            self.assertEqual(
                candidate_record["reverse_complement_view"]["coordinate_map"],
                "view interval [a,b) -> source [n-b,n-a)",
            )

            artifact_workflow.run(spec_path, output, registry)
            reused = json.loads((output / "workflow.json").read_text(
                encoding="utf-8"))["stages"][0]
            self.assertEqual(reused["execution"], "verified_reuse")
            with (stage_output / "repeat_evidence.jsonl").open("ab") as evidence:
                evidence.write(b'{"tampered":true}\n')
            with self.assertRaises(ValueError):
                artifact_contracts.validate_artifact(
                    bundle_path, "m10_result_bundle")

    def test_empty_candidate_set_is_not_a_candidate_no_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_root = root / "candidate"
            candidate_root.mkdir()
            candidate_path, document = M8ContractTests()._candidate_set(
                candidate_root, state="COMPLETE_EMPTY", with_records=False)
            document["availability"]["reason"] = None
            candidate_path.write_text(json.dumps(document), encoding="utf-8")
            result = __import__(
                "satellite_discovery.m10_stage",
                fromlist=["run_stage"],
            ).run_stage(
                {"candidate_sequence_set": candidate_path},
                root / "direct-output",
                {},
            )
            self.assertEqual(set(result), {
                "candidate_accounting.jsonl", "repeat_evidence.jsonl",
                "m10_bundle.json",
            })
            bundle = json.loads(
                (root / "direct-output" / "m10_bundle.json").read_text())
            self.assertEqual(bundle["input_status"], "COMPLETE_EMPTY_INPUT_SET")
            self.assertEqual(bundle["aggregate_status"], "PARTIAL")
            self.assertEqual(bundle["candidate_count"], 0)
            self.assertEqual(
                artifact_contracts.validate_artifact(
                    root / "direct-output" / "m10_bundle.json",
                    "m10_result_bundle")["evidence_count"],
                0,
            )

    def test_supplied_m9_context_is_retained_as_context_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path = _candidate_set(root / "candidate")
            context_path = root / "synthetic-m9-output.txt"
            context_bytes = b"Synthetic fixture only; no protein search was run.\n"
            context_path.write_bytes(context_bytes)
            from satellite_discovery.m10_stage import run_stage

            run_stage({
                "candidate_sequence_set": candidate_path,
                "m9_raw_output_fixture": context_path,
            }, root / "direct-output", {})
            bundle_path = root / "direct-output" / "m10_bundle.json"
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            m9_state = bundle["source_inputs"]["optional_context_state"]["m9"]
            self.assertEqual(m9_state["state"], "SUPPLIED")
            self.assertEqual(len(m9_state["artifacts"]), 1)
            descriptor = m9_state["artifacts"][0]
            self.assertEqual(descriptor["input_name"], "m9_raw_output_fixture")
            self.assertEqual(descriptor["sha256"], _sha(context_bytes))
            self.assertEqual(descriptor["validation_state"], "valid")
            self.assertEqual(
                artifact_contracts.validate_artifact(
                    bundle_path, "m10_result_bundle")["aggregate_status"],
                "COMPLETE",
            )