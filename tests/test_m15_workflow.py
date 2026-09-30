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
            "artifact_contract_version": artifact_contracts.semantic_identity(
                artifact_type
            )["contracts"][artifact_type],
            "relative_path": relative_path,
            "sha256": digest,
        }, artifact_path

    def _run(self, refs, artifact_paths, *, optional_states=None):
        optional_states = optional_states or {
            "M12": "NOT_SUPPLIED",
            "M13": "NOT_SUPPLIED",
            "M14": "PRESENT" if refs else "NOT_SUPPLIED",
        }
        input_manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
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
        output = self.root / "m15-output"
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

    def test_m14_reference_is_preserved_but_semantics_remain_unknown(self):
        ref, path = self._producer_ref(
            "observations",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        result = self._run([ref], [path])
        record = result["envelope"]["records"][0]
        self.assertEqual(record["producer_status_raw"], "complete")
        self.assertEqual(record["producer_schema_raw"], "m14-observation-table-v1")
        self.assertEqual(record["semantic_axes"]["artifact_validity"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["execution"], "complete")
        self.assertEqual(record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(
            result["summary"]["result_completeness"],
            "PARTIAL",
        )
        self.assertIn(
            "UPSTREAM_CONTRACT_VALIDATOR_UNAVAILABLE",
            result["envelope"]["compatibility_warnings"],
        )

    def test_digest_mismatch_is_retained_as_invalid_without_ingesting_payload(self):
        valid_ref, valid_path = self._producer_ref(
            "observations",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        bad_ref, bad_path = self._producer_ref(
            "summary",
            "m14_descriptive_summary",
            {"schema": "m14-summary-v1", "counts": {}},
        )
        bad_ref = dict(bad_ref)
        bad_ref["sha256"] = "0" * 64
        result = self._run([valid_ref, bad_ref], [valid_path, bad_path])
        self.assertEqual(
            sorted(row["validation_state"] for row in result["envelope"]["records"]),
            ["ACCEPTED", "INVALID"],
        )
        invalid = next(
            row for row in result["envelope"]["records"]
            if row["validation_state"] == "INVALID"
        )
        self.assertEqual(invalid["reason_code"], "ARTIFACT_NOT_BOUND_BY_PRODUCER_MANIFEST")
        self.assertEqual(invalid["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_duplicate_reference_is_preserved_once_and_marked_invalid(self):
        ref, path = self._producer_ref(
            "duplicate",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        result = self._run([ref, dict(ref)], [path, path])
        self.assertEqual(
            sorted(row["validation_state"] for row in result["envelope"]["records"]),
            ["ACCEPTED", "INVALID"],
        )
        duplicate = next(
            row for row in result["envelope"]["records"]
            if row["reason_code"] == "DUPLICATE_REFERENCE"
        )
        self.assertEqual(duplicate["semantic_axes"]["observation"], "UNKNOWN")
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

    def test_unavailable_reference_is_unknown_not_invalid_or_negative(self):
        ref, available_path = self._producer_ref(
            "unavailable",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
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
        result = self._run([ref], [path])
        record = result["envelope"]["records"][0]
        self.assertEqual(record["producer_status_raw"], "future-status")
        self.assertEqual(record["semantic_axes"]["execution"], "UNKNOWN")
        self.assertEqual(record["semantic_axes"]["observation"], "UNKNOWN")
        self.assertIn(
            "UNRECOGNIZED_PRODUCER_STATUS",
            result["envelope"]["compatibility_warnings"],
        )
        self.assertEqual(result["summary"]["result_completeness"], "PARTIAL")

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

    def test_cache_identity_uses_exact_manifest_bytes_not_absolute_location(self):
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
        self.assertNotEqual(
            first_context["input_manifest_sha256"],
            line_ending_context["input_manifest_sha256"],
        )
        self.assertNotEqual(
            first_context["cache_identity"],
            line_ending_context["cache_identity"],
        )

    def test_cache_identity_tracks_resolved_artifact_bytes(self):
        ref, path = self._producer_ref(
            "cache-input",
            "m14_observation_table",
            {"schema": "m14-observation-table-v1", "rows": []},
        )
        manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
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

    def test_m5_completed_zero_is_scoped_no_detection_not_candidate_negative(self):
        ref = {
            "producer_milestone": "M5",
            "producer_stage_id": "m5-caller",
            "producer_run_manifest_sha256": "a" * 64,
            "producer_status": "complete",
            "artifact_type": "dvg_evidence_summary",
            "artifact_contract_version": artifact_contracts.semantic_identity(
                "dvg_evidence_summary"
            )["contracts"]["dvg_evidence_summary"],
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
        producer_root.mkdir()
        triage_path = producer_root / "triage.csv"
        triage_path.write_text(
            "query_id,mate,outcome,residual,length,ambiguous_fraction,entropy,"
            "mean_phred,sequence_hash,exact_duplicate_count,reason_codes\n"
            "fragment-a,1,ELIGIBLE_FOR_ASSEMBLY,True,100,0.0,1.0,30.0,"
            "a,1,\n"
            "fragment-a,2,ELIGIBLE_FOR_ASSEMBLY,True,100,0.0,1.0,30.0,"
            "b,1,\n",
            encoding="utf-8",
        )
        support_path = producer_root / "support.json"
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
        output_hashes = {
            "triage.csv": m15_contracts.sha256_file(triage_path),
            "support.json": m15_contracts.sha256_file(support_path),
        }
        producer_manifest = producer_root / "manifest.json"
        m15_contracts.write_json(producer_manifest, {
            "schema": "m6-stage-manifest-v1",
            "status": "complete",
            "output_sha256": output_hashes,
        })
        run_digest = m15_contracts.sha256_file(producer_manifest)
        refs = []
        for artifact_type, name, path in (
            ("read_triage_table", "triage.csv", triage_path),
            ("read_support_evidence", "support.json", support_path),
        ):
            refs.append({
                "producer_milestone": "M6",
                "producer_stage_id": "m6-residual-support",
                "producer_run_manifest_sha256": run_digest,
                "producer_status": "complete",
                "artifact_type": artifact_type,
                "artifact_contract_version": artifact_contracts.semantic_identity(
                    artifact_type
                )["contracts"][artifact_type],
                "relative_path": name,
                "sha256": m15_contracts.sha256_file(path),
            })
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
        m5_root.mkdir()
        m13_root.mkdir()
        event = {
            "reference_id": "donor",
            "acceptor_reference_id": "acceptor",
            "breakpoint_1": 1,
            "breakpoint_2": 1,
            "orientation": {"donor": "+", "acceptor": "+"},
            "supporting_read_count": 1,
            "evidence_id": "event-a",
        }
        evidence_path = m5_root / "evidence.json"
        m15_contracts.write_json(evidence_path, {
            "schema": "dvg-evidence-v1",
            "caller": "synthetic-caller",
            "status": "DVG_EVIDENCE_DETECTED",
            "events": [event],
        })
        evidence_digest = m15_contracts.sha256_file(evidence_path)
        m5_manifest = m5_root / "manifest.json"
        m15_contracts.write_json(m5_manifest, {
            "schema": "external-tool-stage-v1",
            "status": "complete",
            "output_sha256": {"evidence.json": evidence_digest},
        })
        m5_manifest_digest = m15_contracts.sha256_file(m5_manifest)
        stage_id = "m5-synthetic-caller"
        event_index_path = m13_root / "event_index.json"
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
        event_index_digest = m15_contracts.sha256_file(event_index_path)
        m13_manifest = m13_root / "manifest.json"
        m15_contracts.write_json(m13_manifest, {
            "schema": "m13-stage-manifest-v1",
            "status": "complete",
            "output_sha256": {"event_index.json": event_index_digest},
        })
        refs = []
        for milestone, producer_stage, artifact_type, root, path, digest in (
            ("M5", stage_id, "dvg_evidence", m5_root, evidence_path, evidence_digest),
            (
                "M13", "m13_m5_evidence_matrix", "m13_event_index",
                m13_root, event_index_path, event_index_digest,
            ),
        ):
            manifest_path = root / "manifest.json"
            refs.append({
                "producer_milestone": milestone,
                "producer_stage_id": producer_stage,
                "producer_run_manifest_sha256": m15_contracts.sha256_file(
                    manifest_path
                ),
                "producer_status": "complete",
                "artifact_type": artifact_type,
                "artifact_contract_version": artifact_contracts.semantic_identity(
                    artifact_type
                )["contracts"][artifact_type],
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": digest,
            })
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