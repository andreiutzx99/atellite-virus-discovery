import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from satellite_discovery import m12_artifact_review, m12_contracts, m20_phase4


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _producer(root, *, artifact=b'{"synthetic":true}\n', symlink=False):
    root.mkdir(parents=True)
    stage = root / "stages" / "m6_case"
    stage.mkdir(parents=True)
    artifact_path = stage / "residual.json"
    if symlink:
        target = root / "outside.json"
        target.write_bytes(artifact)
        artifact_path.symlink_to(target)
        digest = _sha(artifact)
    else:
        artifact_path.write_bytes(artifact)
        digest = _sha(artifact)
    stage_manifest = {
        "identity": {"stage_id": "m6_case", "run": "synthetic-run"},
        "status": "complete",
        "output_sha256": {"residual.json": digest},
    }
    raw_manifest = json.dumps(stage_manifest, sort_keys=True).encode()
    (stage / "manifest.json").write_bytes(raw_manifest)
    row = {
        "id": "m6_case",
        "kind": "residual_evidence",
        "status": "complete",
        "output_path": "stages/m6_case",
        "stage_manifest_sha256": _sha(raw_manifest),
        "stage_manifest_identity": stage_manifest["identity"],
        "artifacts": {
            "residual.json": {
                "artifact_type": "residual_read_manifest",
                "sha256": digest,
                "contract_version": "1",
            },
        },
    }
    workflow = {
        "schema": "artifact-workflow-manifest-v2",
        "workflow_id": "synthetic-workflow",
        "stages": [row],
    }
    (root / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
    return row, stage, artifact_path


class M20Phase4ProvenanceTests(unittest.TestCase):
    def test_semantic_outcome_digest_ignores_run_specific_lineage_ids(self):
        base = {
            "sample_id": "case",
            "phase3_upstream_outcome": {"candidate_availability": "AVAILABLE"},
            "m12": {"status": "complete", "review_state_counts": {"VERIFIED": 1}},
            "m15": {"status": "complete", "summary": {
                "result_completeness": "PARTIAL",
                "counts": {"accepted_records": 1, "invalid_records": 0},
            }},
            "phase2b_m6_replay_comparison": {
                "identical_outputs": False,
                "changed_artifacts": [{"artifact_path": "reconstruction.json"}],
            },
            "rejected_or_missing_artifacts": [],
            "source_workflow_id": "run-a",
        }
        other_run = {**base, "source_workflow_id": "run-b"}
        frozen = {"phase1_manifest_sha256": "a" * 64}
        first = m20_phase4._semantic_result_digest([base], frozen, "b" * 64)
        second = m20_phase4._semantic_result_digest([other_run], frozen, "b" * 64)
        self.assertEqual(first, second)

    def test_path_traversal_and_windows_paths_are_rejected(self):
        for value in ("../outside.json", "stages/../../outside", r"stages\artifact"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m20_phase4._safe_relative(value)

    def test_changed_artifact_bytes_do_not_pass_the_producer_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "producer"
            row, _, artifact = _producer(root)
            artifact.write_bytes(b'{"synthetic":false}\n')
            with patch("satellite_discovery.artifact_contracts.validate_artifact"):
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    m20_phase4._artifact_records(
                        root, row, {"residual_read_manifest"},
                    )

    def test_forged_stage_digest_and_stale_workflow_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "producer"
            row, _, _ = _producer(root)
            forged = dict(row, stage_manifest_sha256="0" * 64)
            with self.assertRaisesRegex(ValueError, "disagree"):
                m20_phase4._validated_stage(root, forged)
            stale = dict(row, stage_manifest_identity={"stage_id": "m6_case", "run": "old"})
            with self.assertRaisesRegex(ValueError, "disagree"):
                m20_phase4._validated_stage(root, stale)

    def test_symlinked_artifact_is_not_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "producer"
            row, _, _ = _producer(root, symlink=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m20_phase4._artifact_records(
                    root, row, {"residual_read_manifest"},
                )

    def test_m12_rejects_a_typed_handoff_that_does_not_match_its_manifest(self):
        ref = {
            "producer_milestone": "M6",
            "producer_stage_id": "m6_case",
            "producer_run_manifest_sha256": "a" * 64,
            "producer_status": "complete",
            "artifact_type": "residual_read_manifest",
            "relative_path": "residual.json",
            "sha256": "b" * 64,
            "artifact_contract_version": "1",
        }
        manifest = {
            "schema": m12_contracts.INPUT_SCHEMA,
            "candidate_id": "case",
            "producer_artifacts": [ref],
            "external_evidence": {
                key: {"state": "NOT_SUPPLIED", "note": None}
                for key in m12_contracts.EXTERNAL_EVIDENCE_KEYS
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            m12_contracts.write_json(path, manifest)
            producer = {
                "id": "m6_case", "kind": "residual_evidence",
            }
            stage = {
                "id": "m12_case", "kind": m12_artifact_review.STAGE_KIND,
                "inputs": {
                    "manifest": {"path": "input.json", "artifact_type": "m12_input_manifest"},
                    "m6_000": {"stage": "m6_case", "artifact": "other.json"},
                },
            }
            definition = SimpleNamespace(
                kind="residual_evidence",
                output_contracts={
                    "residual.json": ("residual_read_manifest",),
                    "other.json": ("residual_read_manifest",),
                },
            )
            with self.assertRaisesRegex(ValueError, "exactly one same-workflow"):
                m12_artifact_review.validate_handoff_declarations(
                    path, stage, [producer, stage],
                    {"m6_case": definition},
                )

    def test_m15_bundle_symlink_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "producer"
            row, _, _ = _producer(root, symlink=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                m20_phase4._copy_bundle(root, row, Path(temporary) / "bundle")


if __name__ == "__main__":
    unittest.main()
