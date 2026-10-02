import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import artifact_contracts, m15_contracts, m15_stage
from satellite_discovery.artifact_workflow import run as run_workflow


class M15WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="m15-workflow-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _producer_ref(self, name, artifact_type, document, *, status="complete"):
        producer_root = self.root / f"producer-{name}"
        producer_root.mkdir(exist_ok=True)
        relative_path = f"{name}.json"
        artifact_path = producer_root / relative_path
        m15_contracts.write_json(artifact_path, document)
        digest = m15_contracts.sha256_file(artifact_path)
        manifest = {
            "schema": "external-tool-stage-v1",
            "status": status,
            "output_sha256": {relative_path: digest},
        }
        manifest_path = producer_root / "manifest.json"
        m15_contracts.write_json(manifest_path, manifest)
        return {
            "producer_milestone": "M14",
            "producer_stage_id": "m14_descriptive_observations",
            "producer_run_manifest_sha256": m15_contracts.sha256_file(manifest_path),
            "producer_status": status,
            "artifact_type": artifact_type,
            "artifact_contract_version": artifact_contracts.CONTRACT_VERSION,
            "relative_path": relative_path,
            "sha256": digest,
        }, artifact_path

    def _snapshot_ref(self, name, *, digest=None, status="declared"):
        path = self.root / f"{name}-snapshot.json"
        raw = b'{"schema":"synthetic-caller-snapshot-v1"}\n'
        path.write_bytes(raw)
        actual_digest = hashlib.sha256(raw).hexdigest()
        return {
            "producer_milestone": "M8",
            "producer_stage_id": "caller_snapshot",
            "producer_run_manifest_sha256": actual_digest,
            "producer_status": status,
            "artifact_type": "m8_reference_snapshot_manifest",
            "artifact_contract_version": artifact_contracts.CONTRACT_VERSION,
            "relative_path": path.name,
            "sha256": digest or actual_digest,
            "provenance_mode": m15_contracts.CALLER_SNAPSHOT_MODE,
            "producer_execution_ref": None,
            "producer_bundle_path": None,
        }, path

    def _authenticated_producer_refs(
        self, producer_root, milestone, stage_id, stage_kind, artifacts,
    ):
        producer_root = Path(producer_root)
        stage_relative = f"stage-runs/{stage_id}"
        stage_root = producer_root / stage_relative
        stage_root.mkdir(parents=True, exist_ok=True)
        output_hashes = {}
        output_files = {}
        descriptors = {}
        for relative_path, artifact_type in artifacts:
            artifact_path = stage_root / relative_path
            digest = m15_contracts.sha256_file(artifact_path)
            contract_version = artifact_contracts.CONTRACT_VERSION
            output_hashes[relative_path] = digest
            output_files[relative_path] = {
                "sha256": digest,
                "size_bytes": artifact_path.stat().st_size,
            }
            descriptors[relative_path] = {
                "schema": "artifact-contract-v1",
                "artifact_type": artifact_type,
                "contract_version": contract_version,
                "producer_stage": stage_id,
                "path": f"{stage_relative}/{relative_path}",
                "sha256": digest,
                "size_bytes": artifact_path.stat().st_size,
                "validation_state": "valid",
            }
        stage_identity = {
            "schema": "stage-identity-v1",
            "stage_id": stage_id,
            "implementation_version": "synthetic-fixture-v1",
        }
        stage_manifest = {
            "status": "complete",
            "identity": stage_identity,
            "output_sha256": output_hashes,
        }
        stage_manifest_path = stage_root / "manifest.json"
        m15_contracts.write_json(stage_manifest_path, stage_manifest)
        stage_manifest_sha256 = m15_contracts.sha256_file(stage_manifest_path)
        workflow_id = f"synthetic-workflow-{stage_id}"
        workflow = {
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": workflow_id,
            "status": "complete",
            "started_utc": "2026-10-01T08:00:00Z",
            "output": str(producer_root),
            "stages": [{
                "id": stage_id,
                "kind": stage_kind,
                "status": "complete",
                "output_path": stage_relative,
                "stage_manifest_sha256": stage_manifest_sha256,
                "stage_manifest_identity": stage_identity,
                "output_files": output_files,
                "artifacts": descriptors,
            }],
        }
        workflow_path = producer_root / "workflow.json"
        m15_contracts.write_json(workflow_path, workflow)
        workflow_sha256 = m15_contracts.sha256_file(workflow_path)
        bundle_path = producer_root.relative_to(self.root).as_posix()
        refs = []
        for relative_path, artifact_type in artifacts:
            refs.append({
                "producer_milestone": milestone,
                "producer_stage_id": stage_id,
                "producer_run_manifest_sha256": stage_manifest_sha256,
                "producer_status": "complete",
                "artifact_type": artifact_type,
                "artifact_contract_version": descriptors[relative_path][
                    "contract_version"
                ],
                "relative_path": relative_path,
                "sha256": output_hashes[relative_path],
                "provenance_mode":
                    m15_contracts.AUTHENTICATED_PRODUCER_MODE,
                "producer_execution_ref": {
                    "schema": "producer-execution-ref-v1",
                    "producer_workflow_ref": {
                        "path": "workflow.json",
                        "sha256": workflow_sha256,
                        "workflow_id": workflow_id,
                    },
                    "producer_stage_id": stage_id,
                    "producer_stage_kind": stage_kind,
                    "producer_stage_manifest_sha256": stage_manifest_sha256,
                },
                "producer_bundle_path": bundle_path,
            })
        return refs

    def _run(self, refs, artifact_paths, *, optional_states=None,
             input_schema=None, output_name="m15-output"):
        if optional_states is None:
            milestones = {ref["producer_milestone"] for ref in refs}
            optional_states = {
                milestone: (
                    "PRESENT" if milestone in milestones else "NOT_SUPPLIED"
                )
                for milestone in ("M12", "M13", "M14")
            }
        input_manifest = {
            "schema": input_schema or m15_contracts.INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "artifact_refs": refs,
            "optional_stage_states": optional_states,
        }
        input_path = self.root / "m15-input.json"
        m15_contracts.write_json(input_path, input_manifest)
        inputs = {
            "manifest": {
                "path": input_path.name,
                "artifact_type": "m15_input_manifest",
            }
        }
        for index, path in enumerate(artifact_paths):
            inputs[f"artifact_{index:04d}"] = {
                "path": Path(path).relative_to(self.root).as_posix(),
                "artifact_type": refs[index]["artifact_type"],
            }
        workflow_spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m15",
                "kind": "m15_evidence_dossier",
                "inputs": inputs,
            }],
        }
        spec_path = self.root / "m15-workflow.json"
        m15_contracts.write_json(spec_path, workflow_spec)
        output = self.root / output_name
        run_workflow(spec_path, output)
        workflow = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
        stage = next(row for row in workflow["stages"] if row["id"] == "m15")
        self.assertEqual(stage["status"], "complete", stage.get("error"))
        stage_output = output / stage["output_path"]
        return {
            "workflow": workflow,
            "stage": stage,
            "stage_output": stage_output,
            "envelope": json.loads(
                (stage_output / "evidence_envelope.json").read_text(encoding="utf-8")
            ),
            "summary": json.loads(
                (stage_output / "dossier_summary.json").read_text(encoding="utf-8")
            ),
            "edges": json.loads(
                (stage_output / "dependency_edges.json").read_text(encoding="utf-8")
            ),
            "bundle": json.loads(
                (stage_output / "result_bundle.json").read_text(encoding="utf-8")
            ),
        }

    def test_empty_manifest_is_not_evaluated_without_synthetic_records(self):
        result = self._run([], [])
        self.assertEqual(result["summary"]["result_completeness"], "NOT_EVALUATED")
        self.assertEqual(result["envelope"]["records"], [])
        self.assertEqual(result["summary"]["counts"]["supplied_artifacts"], 0)
        self.assertEqual(result["bundle"]["producer_refs"], [])

    def test_v1_m14_reference_is_retained_but_not_authenticated(self):
        ref, path = self._producer_ref(
            "observations",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        result = self._run(
            [ref], [path], input_schema=m15_contracts.LEGACY_INPUT_SCHEMA)
        record = result["envelope"]["records"][0]
        self.assertEqual(record["producer_status_raw"], "complete")
        self.assertEqual(record["producer_schema_raw"], "UNKNOWN")
        self.assertEqual(record["validation_state"], "INVALID_PROVENANCE")
        self.assertEqual(record["semantic_axes"]["artifact_validity"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["execution"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(
            result["summary"]["result_completeness"],
            "INVALID",
        )
        self.assertEqual(
            record["producer_provenance_error_code"],
            "LEGACY_UNAUTHENTICATED_REFERENCE",
        )

    def test_digest_mismatch_is_retained_as_invalid_without_ingesting_payload(self):
        valid_ref, valid_path = self._snapshot_ref("valid")
        bad_ref, bad_path = self._snapshot_ref(
            "bad", digest="0" * 64)
        result = self._run([valid_ref, bad_ref], [valid_path, bad_path])
        self.assertEqual(
            sorted(row["validation_state"] for row in result["envelope"]["records"]),
            ["INVALID", "UNVERIFIED"],
        )
        invalid = next(
            row for row in result["envelope"]["records"]
            if row["validation_state"] == "INVALID"
        )
        self.assertEqual(invalid["reason_code"], "ARTIFACT_DIGEST_MISMATCH")
        self.assertEqual(invalid["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_duplicate_reference_is_preserved_once_and_marked_invalid(self):
        ref, path = self._snapshot_ref("duplicate")
        result = self._run([ref, dict(ref)], [path, path])
        self.assertEqual(
            sorted(row["validation_state"] for row in result["envelope"]["records"]),
            ["INVALID", "UNVERIFIED"],
        )
        duplicate = next(
            row for row in result["envelope"]["records"]
            if row["reason_code"] == "DUPLICATE_REFERENCE"
        )
        self.assertEqual(duplicate["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_unavailable_reference_is_unknown_not_invalid_or_negative(self):
        ref, available_path = self._snapshot_ref("unavailable")
        missing_path = available_path.parent / "missing.json"
        result = self._run([ref], [missing_path])
        record = result["envelope"]["records"][0]
        self.assertEqual(record["validation_state"], "UNAVAILABLE")
        self.assertEqual(record["semantic_axes"]["artifact_validity"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_unknown_producer_status_is_raw_and_not_negative_evidence(self):
        ref, path = self._producer_ref(
            "observations",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
            status="future-status",
        )
        result = self._run(
            [ref], [path], input_schema=m15_contracts.LEGACY_INPUT_SCHEMA)
        record = result["envelope"]["records"][0]
        self.assertEqual(record["producer_status_raw"], "future-status")
        self.assertEqual(record["validation_state"], "INVALID_PROVENANCE")
        self.assertEqual(record["semantic_axes"]["execution"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "INVALID")

    def test_optional_present_requires_matching_reference(self):
        manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "artifact_refs": [],
            "optional_stage_states": {
                "M12": "PRESENT",
                "M13": "NOT_SUPPLIED",
                "M14": "NOT_SUPPLIED",
            },
        }
        with self.assertRaisesRegex(ValueError, "PRESENT requires"):
            m15_contracts.validate_input_manifest(manifest)

    def test_cache_identity_normalizes_manifest_location_and_line_endings(self):
        manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "artifact_refs": [],
            "optional_stage_states": {
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "NOT_SUPPLIED",
            },
        }
        first = self.root / "first" / "input.json"
        second = self.root / "second" / "input.json"
        first.parent.mkdir()
        second.parent.mkdir()
        m15_contracts.write_json(first, manifest)
        second.write_bytes(first.read_bytes())
        plan = {"bindings": []}
        first_context = m15_stage.build_stage_context(
            {"manifest": first}, plan)
        relocated_context = m15_stage.build_stage_context(
            {"manifest": second}, plan)
        self.assertEqual(
            first_context["cache_identity"],
            relocated_context["cache_identity"],
        )
        second.write_bytes(first.read_bytes().replace(b"\n", b"\r\n"))
        line_ending_context = m15_stage.build_stage_context(
            {"manifest": second}, plan)
        self.assertEqual(
            first_context["input_manifest_sha256"],
            line_ending_context["input_manifest_sha256"],
        )
        self.assertEqual(
            first_context["cache_identity"],
            line_ending_context["cache_identity"],
        )
        self.assertNotEqual(
            first_context["input_manifest_file_sha256"],
            line_ending_context["input_manifest_file_sha256"],
        )

    def test_cache_identity_normalizes_reference_order_and_unknown_metadata(self):
        first_ref, first_path = self._snapshot_ref("order-first")
        second_ref, second_path = self._snapshot_ref("order-second")
        first_manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "artifact_refs": [first_ref, second_ref],
            "optional_stage_states": {
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "NOT_SUPPLIED",
            },
        }
        second_ref_with_metadata = dict(second_ref)
        second_ref_with_metadata["display_label"] = "ignored presentation metadata"
        second_manifest = {
            **first_manifest,
            "artifact_refs": [second_ref_with_metadata, first_ref],
        }
        first_path_manifest = self.root / "cache-order-first.json"
        second_path_manifest = self.root / "cache-order-second.json"
        m15_contracts.write_json(first_path_manifest, first_manifest)
        m15_contracts.write_json(second_path_manifest, second_manifest)
        plan = {"bindings": []}
        first_context = m15_stage.build_stage_context({
            "manifest": first_path_manifest,
            "artifact_0000": first_path,
            "artifact_0001": second_path,
        }, plan)
        reordered_context = m15_stage.build_stage_context({
            "manifest": second_path_manifest,
            "artifact_0000": second_path,
            "artifact_0001": first_path,
        }, plan)
        self.assertNotEqual(
            first_context["input_manifest_file_sha256"],
            reordered_context["input_manifest_file_sha256"],
        )
        self.assertEqual(
            first_context["cache_identity"],
            reordered_context["cache_identity"],
        )

    def test_cache_identity_tracks_resolved_artifact_bytes(self):
        ref, path = self._producer_ref(
            "cache-input",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        manifest = {
            "schema": m15_contracts.LEGACY_INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "artifact_refs": [ref],
            "optional_stage_states": {
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "PRESENT",
            },
        }
        manifest_path = self.root / "cache-input-manifest.json"
        m15_contracts.write_json(manifest_path, manifest)
        input_paths = {
            "manifest": manifest_path,
            "artifact_0000": path,
        }
        plan = {"bindings": [{"artifact_ref_index": 0}]}
        before = m15_stage.build_stage_context(input_paths, plan)
        m15_contracts.write_json(path, {
            "schema": "m14-observation-table-v1",
            "rows": [{"source": "synthetic"}],
        })
        after = m15_stage.build_stage_context(input_paths, plan)
        self.assertNotEqual(before["cache_identity"], after["cache_identity"])

    def test_output_artifacts_are_byte_deterministic_for_same_inputs(self):
        ref, path = self._snapshot_ref("deterministic")
        first = self._run([ref], [path], output_name="m15-deterministic-one")
        second = self._run([ref], [path], output_name="m15-deterministic-two")
        for filename in (
            "evidence_envelope.json",
            "dependency_edges.json",
            "dossier_summary.json",
            "result_bundle.json",
        ):
            first_bytes = (first["stage_output"] / filename).read_bytes()
            second_bytes = (second["stage_output"] / filename).read_bytes()
            self.assertEqual(first_bytes, second_bytes, filename)

    def test_result_bundle_supports_frozen_m16_target_handoff(self):
        from satellite_discovery import producer_provenance

        ref, path = self._snapshot_ref("m16-target-interface")
        result = self._run([ref], [path])
        workflow_root = self.root / "m15-output"
        stage = result["stage"]
        bundle = result["bundle"]
        descriptor = stage["artifacts"]["result_bundle.json"]
        workflow_path = workflow_root / "workflow.json"
        artifact_relative_path = Path(descriptor["path"]).relative_to(
            stage["output_path"]
        ).as_posix()
        execution_ref = {
            "schema": "producer-execution-ref-v1",
            "producer_workflow_ref": {
                "workflow_id": result["workflow"]["workflow_id"],
                "path": "workflow.json",
                "sha256": m15_contracts.sha256_file(workflow_path),
            },
            "producer_stage_id": stage["id"],
            "producer_stage_kind": stage["kind"],
            "producer_stage_manifest_sha256":
                stage["stage_manifest_sha256"],
        }
        verified = producer_provenance.verify_producer_artifact(
            bundle_root=workflow_root,
            producer_execution_ref=execution_ref,
            artifact_path=descriptor["path"],
            artifact_relative_path=artifact_relative_path,
            artifact_type=descriptor["artifact_type"],
            contract_version=descriptor["contract_version"],
            expected_sha256=descriptor["sha256"],
        )
        self.assertEqual(stage["kind"], m15_stage.STAGE_KIND)
        self.assertEqual(verified.stage_kind, m15_stage.STAGE_KIND)
        self.assertEqual(verified.artifact_type, "m15_result_bundle")
        self.assertEqual(verified.artifact_sha256, descriptor["sha256"])
        self.assertEqual(
            descriptor["contract_version"], artifact_contracts.CONTRACT_VERSION)
        self.assertEqual(
            bundle["schema"], m15_contracts.RESULT_BUNDLE_SCHEMA)
        self.assertEqual(
            descriptor["metadata"]["schema"], bundle["schema"])
        self.assertEqual(
            bundle["semantic_version"], m15_contracts.SEMANTIC_VERSION)
        self.assertTrue(bundle["implementation"]["source_sha256"])
        self.assertEqual(
            stage["stage_manifest_identity"]["implementation"],
            bundle["implementation"],
        )
        self.assertRegex(stage["cache_key"], r"^[0-9a-f]{64}$")
        self.assertEqual(m15_stage.validate_config({}), {})
        self.assertNotIn("m15_result_bundle", m15_contracts.ALL_INPUT_TYPES)

    def test_m8_no_hit_and_failed_branch_are_preserved_without_negative_mapping(self):
        producer_root = self.root / "m8-partial-run"
        stage_id = "m8-synthetic-partial"
        stage_root = producer_root / "stage-runs" / stage_id
        raw_dir = stage_root / "raw"
        raw_dir.mkdir(parents=True)
        no_hit_path = raw_dir / "candidate-1_dust_masked.tsv"
        failed_path = raw_dir / "candidate-1_dust_unmasked.tsv"
        no_hit_path.write_bytes(
            b"qseqid\tsseqid\tpident\tlength\tqstart\tqend\t"
            b"sstart\tsend\tevalue\tbitscore\n"
        )
        failed_path.write_bytes(b"synthetic branch failure\n")
        no_hit_digest = m15_contracts.sha256_file(no_hit_path)
        failed_digest = m15_contracts.sha256_file(failed_path)
        query_status = {
            "schema": "m8-query-status-v1",
            "stage_version": "1",
            "aggregate_status": "PARTIAL",
            "candidate_availability_state": "AVAILABLE",
            "candidate_record_count": 1,
            "panel_state": "VALID",
            "panel_error": None,
            "scope_error": None,
            "queries": [{
                "candidate_id": "candidate-1",
                "sequence_id": "sequence-1",
                "panel_role": "satellite_subviral",
                "status": "PARTIAL",
                "aggregate_status": "PARTIAL",
                "branches": [
                    {
                        "candidate_id": "candidate-1",
                        "sequence_id": "sequence-1",
                        "panel_role": "satellite_subviral",
                        "masking_branch": "dust_masked",
                        "status":
                            "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
                        "reason": None,
                        "task": "blastn-short",
                        "error": None,
                        "raw_output_path":
                            "raw/candidate-1_dust_masked.tsv",
                        "raw_output_sha256": no_hit_digest,
                        "truncated": False,
                    },
                    {
                        "candidate_id": "candidate-1",
                        "sequence_id": "sequence-1",
                        "panel_role": "satellite_subviral",
                        "masking_branch": "dust_unmasked",
                        "status": "SEARCH_FAILED",
                        "reason": None,
                        "task": "blastn-short",
                        "error": "synthetic branch failure",
                        "raw_output_path":
                            "raw/candidate-1_dust_unmasked.tsv",
                        "raw_output_sha256": failed_digest,
                        "truncated": False,
                    },
                ],
            }],
        }
        query_status_path = stage_root / "query_status.json"
        matches_path = stage_root / "matches.json"
        m15_contracts.write_json(query_status_path, query_status)
        m15_contracts.write_json(matches_path, {
            "schema": "m8-match-evidence-v1",
            "match_count": 0,
            "matches": [],
        })
        refs = self._authenticated_producer_refs(
            producer_root,
            "M8",
            stage_id,
            "m8_homology",
            [
                ("query_status.json", "m8_query_status"),
                ("matches.json", "m8_match_evidence"),
                ("raw/candidate-1_dust_masked.tsv", "m8_raw_blast_output"),
                ("raw/candidate-1_dust_unmasked.tsv", "m8_raw_blast_output"),
            ],
        )

        result = self._run(
            refs,
            [
                query_status_path,
                matches_path,
                no_hit_path,
                failed_path,
            ],
            output_name="m15-m8-partial-branch",
        )
        query_record = next(
            record for record in result["envelope"]["records"]
            if record["producer_ref"]["artifact_type"] == "m8_query_status"
        )
        preserved = m15_contracts.read_json(query_status_path)
        branches = preserved["queries"][0]["branches"]
        self.assertEqual(
            [branch["status"] for branch in branches],
            [
                "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
                "SEARCH_FAILED",
            ],
        )
        self.assertEqual(query_record["validation_state"], "ACCEPTED")
        self.assertEqual(
            query_record["producer_schema_raw"], "m8-query-status-v1")
        self.assertEqual(
            query_record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(
            query_record["semantic_axes"]["completeness"], "UNKNOWN")
        self.assertEqual(
            query_record["producer_ref"]["sha256"],
            m15_contracts.sha256_file(query_status_path),
        )

    def test_authenticated_reference_tampering_is_rejected_by_shared_verifier(self):
        mutations = (
            (
                "workflow-digest",
                lambda ref: ref["producer_execution_ref"][
                    "producer_workflow_ref"
                ].__setitem__("sha256", "0" * 64),
                "WORKFLOW_DIGEST_MISMATCH",
            ),
            (
                "execution-stage-id",
                lambda ref: ref["producer_execution_ref"].__setitem__(
                    "producer_stage_id", "not-the-stage"),
                "PRODUCER_STAGE_NOT_FOUND",
            ),
            (
                "top-level-stage-id",
                lambda ref: ref.__setitem__(
                    "producer_stage_id", "not-the-stage"),
                "PRODUCER_STAGE_ID_MISMATCH",
            ),
            (
                "stage-kind",
                lambda ref: ref["producer_execution_ref"].__setitem__(
                    "producer_stage_kind", "unregistered-kind"),
                "PRODUCER_IDENTITY_MISMATCH",
            ),
            (
                "stage-manifest",
                lambda ref: ref.__setitem__(
                    "producer_run_manifest_sha256", "f" * 64),
                "PRODUCER_STAGE_MANIFEST_MISMATCH",
            ),
            (
                "producer-status",
                lambda ref: ref.__setitem__(
                    "producer_status", "future-status"),
                "PRODUCER_STATUS_MISMATCH",
            ),
        )
        for label, mutate, expected_error in mutations:
            with self.subTest(label=label):
                producer_root = self.root / f"tamper-{label}"
                stage_root = (
                    producer_root
                    / "stage-runs/m14-descriptive-observations"
                )
                stage_root.mkdir(parents=True)
                artifact_path = stage_root / "observations.json"
                m15_contracts.write_json(artifact_path, {
                    "schema": "deliberately-not-ingested",
                    "rows": [],
                })
                ref = self._authenticated_producer_refs(
                    producer_root,
                    "M14",
                    "m14-descriptive-observations",
                    "m14_descriptive_observations",
                    [("observations.json", "m14_observation_table")],
                )[0]
                mutate(ref)
                result = self._run(
                    [ref], [artifact_path],
                    output_name=f"m15-tamper-{label}",
                )
                record = result["envelope"]["records"][0]
                self.assertEqual(record["validation_state"], "INVALID_PROVENANCE")
                self.assertEqual(
                    record["producer_provenance_error_code"], expected_error)
                self.assertEqual(record["producer_schema_raw"], "UNKNOWN")

    def test_nonterminal_authenticated_producer_is_reported_as_incomplete(self):
        producer_root = self.root / "incomplete-producer"
        stage_root = (
            producer_root / "stage-runs/m14-descriptive-observations"
        )
        stage_root.mkdir(parents=True)
        artifact_path = stage_root / "observations.json"
        m15_contracts.write_json(artifact_path, {
            "schema": "deliberately-not-ingested",
            "rows": [],
        })
        ref = self._authenticated_producer_refs(
            producer_root,
            "M14",
            "m14-descriptive-observations",
            "m14_descriptive_observations",
            [("observations.json", "m14_observation_table")],
        )[0]
        workflow_path = producer_root / "workflow.json"
        workflow = m15_contracts.read_json(workflow_path)
        workflow["status"] = "running"
        workflow["stages"][0]["status"] = "running"
        m15_contracts.write_json(workflow_path, workflow)
        ref["producer_status"] = "running"
        ref["producer_execution_ref"]["producer_workflow_ref"]["sha256"] = (
            m15_contracts.sha256_file(workflow_path)
        )
        result = self._run(
            [ref], [artifact_path], output_name="m15-incomplete-producer")
        record = result["envelope"]["records"][0]
        self.assertEqual(record["validation_state"], "INCOMPLETE")
        self.assertEqual(record["producer_execution_state"], "running")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_m5_completed_zero_is_scoped_no_detection_not_candidate_negative(self):
        ref = {
            "producer_milestone": "M5",
            "producer_stage_id": "m5-caller",
            "producer_run_manifest_sha256": "a" * 64,
            "producer_status": "complete",
            "artifact_type": "dvg_evidence_summary",
            "artifact_contract_version": artifact_contracts.CONTRACT_VERSION,
            "relative_path": "summary.json",
            "sha256": "b" * 64,
        }
        record = m15_stage._record(
            ref,
            "synthetic-candidate",
            state="ACCEPTED",
            reason=None,
            schema="dvg-summary-v1",
            document={
                "schema": "dvg-summary-v1",
                "status": "NO_DVG_EVIDENCE_DETECTED",
                "event_count": 0,
            },
        )
        self.assertEqual(
            record["semantic_axes"]["observation"],
            "NOT_DETECTED_WITHIN_SCOPE",
        )
        self.assertEqual(record["semantic_axes"]["completeness"], "COMPLETE")
        self.assertEqual(
            record["semantic_axes"]["interpretation"], "NOT_INTERPRETED")
        ref["producer_status"] = "failed"
        failed = m15_stage._record(
            ref,
            "synthetic-candidate",
            state="ACCEPTED",
            reason=None,
            schema="dvg-summary-v1",
            document={
                "schema": "dvg-summary-v1",
                "status": "NO_DVG_EVIDENCE_DETECTED",
                "event_count": 0,
            },
        )
        self.assertEqual(failed["semantic_axes"]["observation"], "UNKNOWN")

    def test_m6_same_eligible_reads_produce_verified_dependency_edge(self):
        producer_root = self.root / "m6-producer"
        stage_root = producer_root / "stage-runs/m6-residual-support"
        stage_root.mkdir(parents=True)
        triage_path = stage_root / "triage.csv"
        triage_path.write_text(
            "query_id,mate,outcome,residual,length,ambiguous_fraction,entropy,"
            "mean_phred,sequence_hash,exact_duplicate_count,reason_codes\n"
            "fragment-a,1,ELIGIBLE_FOR_ASSEMBLY,True,100,0.0,1.0,30.0,"
            "a,1,\n"
            "fragment-a,2,ELIGIBLE_FOR_ASSEMBLY,True,100,0.0,1.0,30.0,"
            "b,1,\n",
            encoding="utf-8",
        )
        support_path = stage_root / "support.json"
        m15_contracts.write_json(support_path, {
            "schema": "m6-read-support-v1",
            "status": "READ_SUPPORTED_ASSEMBLY",
            "contigs": [],
            "configuration": {},
            "provenance": {
                "support_input_fragment_ids": ["fragment-a"],
            },
            "read_support": [],
        })
        refs = self._authenticated_producer_refs(
            producer_root,
            "M6",
            "m6-residual-support",
            "residual_evidence",
            [
                ("triage.csv", "read_triage_table"),
                ("support.json", "read_support_evidence"),
            ],
        )
        result = self._run(
            refs,
            [triage_path, support_path],
            optional_states={
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "NOT_SUPPLIED",
            },
        )
        self.assertEqual(len(result["edges"]["edges"]), 1)
        edge = result["edges"]["edges"][0]
        self.assertEqual(edge["relation"], "SAME_READ_SOURCE")
        self.assertEqual(edge["verification_state"], "VERIFIED")
        self.assertEqual(
            edge["source_provenance_ref"]["eligible_fragment_ids_sha256"],
            hashlib.sha256(
                m15_contracts.canonical_json_bytes(["fragment-a"])
            ).hexdigest(),
        )
        self.assertTrue(all(
            edge["edge_id"] in record["dependency_edge_ids"]
            for record in result["envelope"]["records"]
        ))

    def test_m13_event_index_links_only_exact_m5_source_event(self):
        m5_root = self.root / "m5-event-producer"
        m13_root = self.root / "m13-event-producer"
        m5_stage_root = m5_root / "stage-runs/m5-synthetic-caller"
        m13_stage_root = m13_root / "stage-runs/m13_m5_evidence_matrix"
        m5_stage_root.mkdir(parents=True)
        m13_stage_root.mkdir(parents=True)
        event = {
            "reference_id": "donor",
            "acceptor_reference_id": "acceptor",
            "breakpoint_1": 1,
            "breakpoint_2": 1,
            "orientation": {"donor": "+", "acceptor": "+"},
            "supporting_read_count": 1,
            "evidence_id": "event-a",
        }
        evidence_path = m5_stage_root / "evidence.json"
        m15_contracts.write_json(evidence_path, {
            "schema": "dvg-evidence-v1",
            "caller": "synthetic-caller",
            "status": "DVG_EVIDENCE_DETECTED",
            "events": [event],
        })
        stage_id = "m5-synthetic-caller"
        m5_ref = self._authenticated_producer_refs(
            m5_root, "M5", stage_id, "dvg_virema",
            [("evidence.json", "dvg_evidence")],
        )[0]
        evidence_digest = m5_ref["sha256"]
        m5_manifest_digest = m5_ref["producer_run_manifest_sha256"]
        event_index_path = m13_stage_root / "event_index.json"
        m15_contracts.write_json(event_index_path, {
            "schema": "m13-event-index-v1",
            "candidate_id": "synthetic-candidate",
            "events": [{
                "candidate_id": "synthetic-candidate",
                "m5_run_ref": {
                    "producer_stage_id": stage_id,
                    "producer_run_manifest_sha256": m5_manifest_digest,
                    "dvg_evidence_sha256": evidence_digest,
                },
                "caller": "synthetic-caller",
                "caller_version": "1",
                "reference_sha256": "c" * 64,
                "source_row_index": 0,
                "source_event": event,
                "source_event_id": "event-a",
            }],
        })
        m13_ref = self._authenticated_producer_refs(
            m13_root, "M13", "m13_m5_evidence_matrix",
            "m13_m5_evidence_matrix",
            [("event_index.json", "m13_event_index")],
        )[0]
        refs = [m5_ref, m13_ref]
        result = self._run(
            refs,
            [evidence_path, event_index_path],
            optional_states={
                "M12": "NOT_SUPPLIED",
                "M13": "PRESENT",
                "M14": "NOT_SUPPLIED",
            },
        )
        edges = result["edges"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["relation"], "DERIVED_FROM")
        self.assertEqual(edges[0]["verification_state"], "VERIFIED")
        self.assertEqual(
            edges[0]["source_provenance_ref"]["source_event_id"], "event-a")
        self.assertTrue(all(
            edges[0]["edge_id"] in record["dependency_edge_ids"]
            for record in result["envelope"]["records"]
        ))
        m13_record = next(
            row for row in result["envelope"]["records"]
            if row["producer_ref"]["artifact_type"] == "m13_event_index"
        )
        m5_record = next(
            row for row in result["envelope"]["records"]
            if row["producer_ref"]["artifact_type"] == "dvg_evidence"
        )
        mismatched_rows = [{
            "m5_run_ref": {
                "producer_stage_id": stage_id,
            "producer_run_manifest_sha256": m5_manifest_digest,
                "dvg_evidence_sha256": evidence_digest,
            },
            "source_row_index": 0,
            "source_event": {**event, "breakpoint_1": 2},
            "source_event_id": "event-a",
        }]
        self.assertEqual(
            m15_stage._m13_source_event_edges(
                [m13_record, m5_record],
                {
                    m13_record["evidence_id"]: {
                        "m13_event_rows": mismatched_rows,
                    },
                    m5_record["evidence_id"]: {"dvg_events": [event]},
                },
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()