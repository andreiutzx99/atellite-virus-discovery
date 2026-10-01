import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from satellite_discovery.producer_provenance import (
    PRODUCER_EXECUTION_REF_SCHEMA,
    ProducerProvenanceIncompleteError,
    ProducerProvenanceInvalidError,
    ProducerProvenanceUnavailableError,
    verify_producer_artifact,
)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _json_bytes(value)
    path.write_bytes(raw)
    return raw


class ProducerProvenanceTests(unittest.TestCase):
    def _fixture(
        self,
        root,
        *,
        workflow_id="workflow-1",
        workflow_status="complete",
        stage_status="complete",
        started_utc="2026-10-01T08:00:00Z",
    ):
        root = Path(root)
        producer_root = root / "producer"
        stage_relative = "stage-runs/stage-1"
        stage_root = producer_root / stage_relative
        artifact_bytes = b'{"rows":[]}\n'
        artifact_digest = _sha(artifact_bytes)
        artifact_relative = "evidence.json"
        artifact_path = stage_root / artifact_relative
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        consumer_artifact = root / "consumer" / artifact_relative
        consumer_artifact.parent.mkdir(parents=True, exist_ok=True)
        consumer_artifact.write_bytes(artifact_bytes)

        stage_identity = {
            "schema": "stage-identity-v1",
            "stage_id": "stage-1",
            "implementation_version": "1",
        }
        stage_manifest = {
            "status": "complete",
            "identity": stage_identity,
            "output_sha256": {artifact_relative: artifact_digest},
        }
        stage_manifest_raw = _write_json(stage_root / "manifest.json", stage_manifest)
        stage_manifest_digest = _sha(stage_manifest_raw)
        descriptor = {
            "schema": "artifact-contract-v1",
            "artifact_type": "synthetic_evidence",
            "contract_version": "1",
            "producer_stage": "stage-1",
            "path": f"{stage_relative}/{artifact_relative}",
            "sha256": artifact_digest,
            "size_bytes": len(artifact_bytes),
            "validation_state": "valid",
        }
        stage_row = {
            "id": "stage-1",
            "kind": "fixture_stage",
            "status": stage_status,
            "output_path": stage_relative,
            "stage_manifest_sha256": stage_manifest_digest,
            "stage_manifest_identity": stage_identity,
            "output_files": {
                artifact_relative: {
                    "sha256": artifact_digest,
                    "size_bytes": len(artifact_bytes),
                }
            },
            "artifacts": {artifact_relative: descriptor},
        }
        workflow = {
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": workflow_id,
            "status": workflow_status,
            "started_utc": started_utc,
            # This is an historical absolute path. The verifier uses the
            # explicit bundle/reference paths so an intact bundle can move.
            "output": "/old/location/producer",
            "stages": [stage_row],
        }
        workflow_raw = _write_json(producer_root / "workflow.json", workflow)
        reference = {
            "schema": PRODUCER_EXECUTION_REF_SCHEMA,
            "producer_workflow_ref": {
                "path": "producer/workflow.json",
                "sha256": _sha(workflow_raw),
                "workflow_id": workflow_id,
            },
            "producer_stage_id": "stage-1",
            "producer_stage_kind": "fixture_stage",
            "producer_stage_manifest_sha256": stage_manifest_digest,
        }
        return {
            "root": root,
            "workflow": workflow,
            "reference": reference,
            "artifact_bytes": artifact_bytes,
            "artifact_digest": artifact_digest,
            "artifact_relative_path": artifact_relative,
            "consumer_artifact_path": "consumer/evidence.json",
            "workflow_path": producer_root / "workflow.json",
            "stage_manifest_path": stage_root / "manifest.json",
            "producer_artifact_path": artifact_path,
        }

    def _verify(self, fixture, **overrides):
        values = {
            "bundle_root": fixture["root"],
            "producer_execution_ref": fixture["reference"],
            "artifact_path": fixture["consumer_artifact_path"],
            "artifact_relative_path": fixture["artifact_relative_path"],
            "artifact_type": "synthetic_evidence",
            "contract_version": "1",
            "expected_sha256": fixture["artifact_digest"],
        }
        values.update(overrides)
        return verify_producer_artifact(**values)

    def _rewrite_workflow(self, fixture):
        raw = _write_json(fixture["workflow_path"], fixture["workflow"])
        fixture["reference"]["producer_workflow_ref"]["sha256"] = _sha(raw)

    def test_verifies_complete_workflow_stage_manifest_and_artifact_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            result = self._verify(fixture)

        self.assertEqual(result.workflow_id, "workflow-1")
        self.assertEqual(result.stage_id, "stage-1")
        self.assertEqual(result.stage_kind, "fixture_stage")
        self.assertEqual(result.workflow_status_raw, "complete")
        self.assertEqual(result.stage_status_raw, "complete")
        self.assertEqual(result.artifact_type, "synthetic_evidence")
        self.assertEqual(result.artifact_sha256, fixture["artifact_digest"])
        self.assertRegex(result.binding_sha256, r"^[0-9a-f]{64}$")

    def test_completed_stage_can_be_verified_inside_partial_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(
                Path(directory) / "bundle", workflow_status="partial"
            )
            self._rewrite_workflow(fixture)
            result = self._verify(fixture)
        self.assertEqual(result.workflow_status_raw, "partial")
        self.assertEqual(result.stage_status_raw, "complete")

    def test_unrelated_failed_workflow_status_does_not_erase_completed_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(
                Path(directory) / "bundle", workflow_status="failed"
            )
            self._rewrite_workflow(fixture)
            result = self._verify(fixture)
        self.assertEqual(result.workflow_status_raw, "failed")
        self.assertEqual(result.stage_status_raw, "complete")

    def test_noncomplete_raw_stage_states_are_incomplete_not_negative(self):
        for status in (
            "pending",
            "running",
            "skipped",
            "dependency_missing",
            "external_module_required",
            "failed",
            "interrupted",
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                fixture = self._fixture(
                    Path(directory) / "bundle", stage_status=status
                )
                self._rewrite_workflow(fixture)
                with self.assertRaises(ProducerProvenanceIncompleteError) as raised:
                    self._verify(fixture)
                self.assertEqual(raised.exception.state, "INCOMPLETE")
                self.assertEqual(raised.exception.producer_status, status)

    def test_workflow_bytes_are_the_run_snapshot_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self._fixture(
                Path(directory) / "run-a", started_utc="2026-10-01T08:00:00Z"
            )
            second = self._fixture(
                Path(directory) / "run-b", started_utc="2026-10-01T08:01:00Z"
            )
            first_result = self._verify(first)
            second_result = self._verify(second)
        self.assertEqual(first_result.workflow_id, second_result.workflow_id)
        self.assertEqual(first_result.artifact_sha256, second_result.artifact_sha256)
        self.assertNotEqual(first_result.workflow_sha256, second_result.workflow_sha256)
        self.assertNotEqual(first_result.binding_sha256, second_result.binding_sha256)

    def test_binding_is_stable_under_path_relocation_and_reference_key_order(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original = self._fixture(base / "original")
            original_result = self._verify(original)
            relocated_root = base / "moved" / "bundle"
            shutil.copytree(original["root"], relocated_root)
            relocated = {
                **original,
                "root": relocated_root,
                "workflow_path": relocated_root / "producer" / "workflow.json",
                "stage_manifest_path": (
                    relocated_root / "producer" / "stage-runs" / "stage-1"
                    / "manifest.json"
                ),
                "producer_artifact_path": (
                    relocated_root / "producer" / "stage-runs" / "stage-1"
                    / "evidence.json"
                ),
                "reference": dict(reversed(list(original["reference"].items()))),
                "consumer_artifact_path": "consumer/evidence.json",
            }
            relocated_result = self._verify(relocated)
        self.assertEqual(
            original_result.binding_sha256, relocated_result.binding_sha256
        )

    def test_reference_json_whitespace_and_line_endings_do_not_change_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            baseline = self._verify(fixture)
            text = json.dumps(fixture["reference"], indent=2, sort_keys=False) + "\n"
            parsed_lf = json.loads(text.encode("utf-8"))
            parsed_crlf = json.loads(text.replace("\n", "\r\n").encode("utf-8"))
            lf_result = self._verify(fixture, producer_execution_ref=parsed_lf)
            crlf_result = self._verify(fixture, producer_execution_ref=parsed_crlf)
        self.assertEqual(baseline.binding_sha256, lf_result.binding_sha256)
        self.assertEqual(baseline.binding_sha256, crlf_result.binding_sha256)

    def test_raw_workflow_line_endings_are_integrity_significant(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            raw_lf = (
                json.dumps(
                    fixture["workflow"], sort_keys=True, indent=2
                ).encode("utf-8")
                + b"\n"
            )
            fixture["workflow_path"].write_bytes(raw_lf)
            fixture["reference"]["producer_workflow_ref"]["sha256"] = _sha(raw_lf)
            baseline = self._verify(fixture)
            raw_crlf = raw_lf.replace(b"\n", b"\r\n")
            fixture["workflow_path"].write_bytes(raw_crlf)
            fixture["reference"]["producer_workflow_ref"]["sha256"] = _sha(raw_crlf)
            changed = self._verify(fixture)
        self.assertNotEqual(baseline.workflow_sha256, changed.workflow_sha256)
        self.assertNotEqual(baseline.binding_sha256, changed.binding_sha256)

    def test_duplicate_references_to_same_run_artifact_share_binding_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            first = self._verify(fixture)
            second = self._verify(fixture)
        self.assertEqual(first.binding_sha256, second.binding_sha256)

    def test_irrelevant_workflow_metadata_is_pinned_in_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            baseline = self._verify(fixture)
            fixture["workflow"]["unrelated_diagnostic"] = {"attempt": 1}
            self._rewrite_workflow(fixture)
            changed = self._verify(fixture)
        self.assertNotEqual(baseline.workflow_sha256, changed.workflow_sha256)
        self.assertNotEqual(baseline.binding_sha256, changed.binding_sha256)

    def test_valid_reference_remains_independent_of_an_invalid_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            valid_result = self._verify(fixture)
            invalid_reference = {
                **fixture["reference"],
                "producer_stage_id": "fabricated-stage",
            }
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture, producer_execution_ref=invalid_reference)
            valid_again = self._verify(fixture)
        self.assertEqual(valid_result.binding_sha256, valid_again.binding_sha256)

    def test_wrong_workflow_digest_or_workflow_id_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            wrong_digest = dict(fixture["reference"])
            wrong_digest["producer_workflow_ref"] = {
                **fixture["reference"]["producer_workflow_ref"],
                "sha256": "0" * 64,
            }
            with self.assertRaises(ProducerProvenanceInvalidError) as digest_error:
                self._verify(fixture, producer_execution_ref=wrong_digest)
            self.assertEqual(digest_error.exception.code, "WORKFLOW_DIGEST_MISMATCH")

            wrong_id = dict(fixture["reference"])
            wrong_id["producer_workflow_ref"] = {
                **fixture["reference"]["producer_workflow_ref"],
                "workflow_id": "another-run",
            }
            with self.assertRaises(ProducerProvenanceInvalidError) as id_error:
                self._verify(fixture, producer_execution_ref=wrong_id)
            self.assertEqual(id_error.exception.code, "PRODUCER_IDENTITY_MISMATCH")

    def test_wrong_stage_id_or_kind_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            wrong_id = {
                **fixture["reference"],
                "producer_stage_id": "different-stage",
            }
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture, producer_execution_ref=wrong_id)
            wrong_kind = {
                **fixture["reference"],
                "producer_stage_kind": "different_kind",
            }
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture, producer_execution_ref=wrong_kind)
            self.assertEqual(raised.exception.code, "PRODUCER_IDENTITY_MISMATCH")

    def test_stage_manifest_digest_must_match_workflow_row_and_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            fixture["workflow"]["stages"][0]["stage_manifest_sha256"] = "0" * 64
            self._rewrite_workflow(fixture)
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture)
        self.assertEqual(raised.exception.code, "STAGE_MANIFEST_DIGEST_MISMATCH")

    def test_manifest_from_another_real_stage_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            second_root = fixture["root"] / "producer" / "stage-runs" / "stage-2"
            second_root.mkdir(parents=True)
            (second_root / "evidence.json").write_bytes(fixture["artifact_bytes"])
            second_identity = {
                "schema": "stage-identity-v1",
                "stage_id": "stage-2",
                "implementation_version": "1",
            }
            second_manifest = {
                "status": "complete",
                "identity": second_identity,
                "output_sha256": {
                    "evidence.json": fixture["artifact_digest"],
                },
            }
            second_manifest_raw = _write_json(
                second_root / "manifest.json", second_manifest
            )
            second_digest = _sha(second_manifest_raw)
            second_row = dict(fixture["workflow"]["stages"][0])
            second_row.update({
                "id": "stage-2",
                "output_path": "stage-runs/stage-2",
                "stage_manifest_sha256": second_digest,
                "stage_manifest_identity": second_identity,
                "artifacts": {
                    "evidence.json": {
                        **fixture["workflow"]["stages"][0]["artifacts"][
                            "evidence.json"
                        ],
                        "producer_stage": "stage-2",
                        "path": "stage-runs/stage-2/evidence.json",
                    }
                },
            })
            fixture["workflow"]["stages"].append(second_row)
            fixture["reference"]["producer_stage_manifest_sha256"] = second_digest
            self._rewrite_workflow(fixture)
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture)
        self.assertEqual(raised.exception.code, "STAGE_MANIFEST_DIGEST_MISMATCH")

    def test_missing_artifact_from_stage_inventory_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            manifest = json.loads(fixture["stage_manifest_path"].read_text())
            manifest["output_sha256"] = {}
            _write_json(fixture["stage_manifest_path"], manifest)
            stage_digest = _sha(fixture["stage_manifest_path"].read_bytes())
            fixture["reference"]["producer_stage_manifest_sha256"] = stage_digest
            fixture["workflow"]["stages"][0]["stage_manifest_sha256"] = stage_digest
            fixture["workflow"]["stages"][0]["stage_manifest_identity"] = manifest["identity"]
            self._rewrite_workflow(fixture)
            with self.assertRaises(ProducerProvenanceUnavailableError) as raised:
                self._verify(fixture)
        self.assertEqual(raised.exception.state, "UNAVAILABLE")
        self.assertEqual(raised.exception.code, "ARTIFACT_UNAVAILABLE")

    def test_type_version_descriptor_and_consumer_bytes_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture, artifact_type="other_type")
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture, contract_version="2")
            consumer_path = fixture["root"] / fixture["consumer_artifact_path"]
            consumer_path.write_bytes(b"changed")
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture)
        self.assertEqual(raised.exception.code, "ARTIFACT_INTEGRITY_FAILED")

    def test_invalid_schema_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            wrong_schema = {
                **fixture["reference"],
                "schema": "producer-execution-ref-v2",
            }
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture, producer_execution_ref=wrong_schema)
            traversal = {
                **fixture["reference"],
                "producer_workflow_ref": {
                    **fixture["reference"]["producer_workflow_ref"],
                    "path": "../outside/workflow.json",
                },
            }
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture, producer_execution_ref=traversal)
        self.assertEqual(raised.exception.code, "ARTIFACT_PATH_UNSAFE")

    def test_missing_and_corrupt_producer_records_have_typed_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "missing")
            fixture["workflow_path"].unlink()
            with self.assertRaises(ProducerProvenanceUnavailableError) as missing:
                self._verify(fixture)
            self.assertEqual(missing.exception.state, "UNAVAILABLE")

        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "corrupt")
            corrupt = b"{not-json"
            fixture["workflow_path"].write_bytes(corrupt)
            fixture["reference"]["producer_workflow_ref"]["sha256"] = _sha(corrupt)
            with self.assertRaises(ProducerProvenanceInvalidError) as invalid:
                self._verify(fixture)
            self.assertEqual(invalid.exception.code, "WORKFLOW_INVALID")

    def test_symlinked_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            linked_directory = fixture["root"] / "producer" / "linked"
            linked_directory.mkdir()
            linked = linked_directory / "workflow.json"
            linked.symlink_to(fixture["workflow_path"])
            fixture["reference"]["producer_workflow_ref"]["path"] = (
                "producer/linked/workflow.json"
            )
            with self.assertRaises(ProducerProvenanceInvalidError) as raised:
                self._verify(fixture)
        self.assertEqual(raised.exception.code, "ARTIFACT_PATH_UNSAFE")

    def test_producer_and_consumer_artifact_paths_reject_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            with self.assertRaises(ProducerProvenanceInvalidError) as traversal:
                self._verify(fixture, artifact_relative_path="../evidence.json")
            self.assertEqual(traversal.exception.code, "ARTIFACT_PATH_UNSAFE")

            linked = fixture["root"] / "consumer" / "evidence-link.json"
            linked.symlink_to(fixture["root"] / fixture["consumer_artifact_path"])
            with self.assertRaises(ProducerProvenanceInvalidError) as symlink:
                self._verify(fixture, artifact_path="consumer/evidence-link.json")
            self.assertEqual(symlink.exception.code, "ARTIFACT_PATH_UNSAFE")

            fixture["producer_artifact_path"].write_bytes(b"tampered producer copy")
            with self.assertRaises(ProducerProvenanceInvalidError) as changed:
                self._verify(fixture)
            self.assertEqual(changed.exception.code, "ARTIFACT_INTEGRITY_FAILED")

    def test_duplicate_stage_ids_and_unknown_states_are_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            fixture["workflow"]["stages"].append(
                dict(fixture["workflow"]["stages"][0])
            )
            self._rewrite_workflow(fixture)
            with self.assertRaises(ProducerProvenanceInvalidError) as duplicate:
                self._verify(fixture)
            self.assertEqual(duplicate.exception.code, "PRODUCER_STAGE_NOT_FOUND")

        with tempfile.TemporaryDirectory() as directory:
            fixture = self._fixture(Path(directory) / "bundle")
            fixture["workflow"]["status"] = "unknown"
            self._rewrite_workflow(fixture)
            with self.assertRaises(ProducerProvenanceInvalidError):
                self._verify(fixture)


if __name__ == "__main__":
    unittest.main()