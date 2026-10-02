import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from satellite_discovery import (
    artifact_contracts,
    artifact_workflow,
    m12_artifact_review,
    m12_contracts,
    reproducibility,
)
from satellite_discovery.stage_registry import WorkflowStageRegistry


def _sha(value):
    if isinstance(value, bytes):
        payload = value
    else:
        payload = value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )
    return path


def _stage_manifest(output, payloads):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name, value in payloads.items():
        path = _write_json(output / name, value)
        digests[name] = _sha(path.read_bytes())
    manifest = {"status": "complete", "output_sha256": digests}
    _write_json(output / "manifest.json", manifest)
    return manifest


def _external_evidence(state="NOT_SUPPLIED"):
    return {
        name: {"state": state, "note": None}
        for name in m12_contracts.EXTERNAL_EVIDENCE_KEYS
    }


def _reference(milestone, stage_id, run_manifest, artifact_type, path, digest):
    return {
        "producer_milestone": milestone,
        "producer_stage_id": stage_id,
        "producer_run_manifest_sha256": run_manifest,
        "producer_status": "complete",
        "artifact_type": artifact_type,
        "relative_path": path,
        "sha256": digest,
        "artifact_contract_version": artifact_contracts.semantic_identity(
            artifact_type
        )["contracts"][artifact_type],
    }


def _workflow_spec(include_m12=False, manifest_path="m12-input.json"):
    stages = [
        {"id": "m5", "kind": "dvg_virema", "inputs": {}, "config": {}},
        {"id": "m6", "kind": "residual_evidence", "inputs": {}, "config": {}},
    ]
    if include_m12:
        stages.append({
            "id": "m12",
            "kind": "m12_artifact_review",
            "inputs": {
                "manifest": {
                    "path": manifest_path,
                    "artifact_type": "m12_input_manifest",
                },
                "m5_summary": {"stage": "m5", "artifact": "summary.json"},
                "m5_parameters": {"stage": "m5", "artifact": "parameters.json"},
                "m6_residual": {
                    "stage": "m6",
                    "artifact": "residual-manifest.json",
                },
            },
            "config": {},
        })
    return {"schema": "artifact-workflow-v1", "stages": stages}


class M12ArtifactReviewTests(unittest.TestCase):
    def test_external_provenance_addition_preserves_legacy_cache_lf_and_crlf(self):
        compatibility_path = (
            Path(artifact_workflow.__file__).with_name(
                "m12_legacy_cache_compatibility.txt"
            )
        )
        compatibility = dict(
            line.split("=", 1)
            for line in compatibility_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        package = Path(artifact_workflow.__file__).parent

        for suffix, use_crlf in (("", False), ("_crlf", True)):
            with self.subTest(line_endings="CRLF" if use_crlf else "LF"):
                source_files = {}
                for path in sorted(package.iterdir()):
                    if path.suffix not in {".py", ".json"} or not path.is_file():
                        continue
                    # Git checkouts may use CRLF on Windows. Canonicalize first
                    # so each subtest exercises the named line-ending variant.
                    content = path.read_bytes().replace(b"\r\n", b"\n")
                    if use_crlf:
                        content = content.replace(b"\n", b"\r\n")
                    source_files[path.name] = _sha(content)
                source_digest = _sha(
                    json.dumps(source_files, sort_keys=True).encode("utf-8")
                )
                runtime = {
                    "source_sha256": source_digest,
                    "source_files": source_files,
                }
                self.assertEqual(
                    artifact_workflow._legacy_package_cache_digest(runtime),
                    compatibility[f"legacy_source_sha256{suffix}"],
                )

    def test_m12_package_additions_preserve_legacy_unscoped_cache_keys(self):
        runtime = reproducibility.environment()
        stage = {"id": "legacy", "kind": "legacy_stage"}
        definition = SimpleNamespace(handler=lambda *_args: None, version="1")
        actual_key = artifact_workflow._stage_cache_key(
            stage, definition, {}, {}, runtime, None
        )
        legacy_digest = artifact_workflow._legacy_package_cache_digest(runtime)
        self.assertIn(
            legacy_digest,
            {
                "9242e7b8cbba0c0e912ad6317241628541dafcde2815c7f2786f2ce06f0770ed",
                "4a7da5c1d54b22cf610bda933bcb9ca340a4a8d69fed031d52254a7f63c57312",
            },
        )
        legacy_runtime = {
            **runtime,
            "source_sha256": legacy_digest,
        }
        expected_legacy_key = artifact_workflow._stage_cache_key(
            stage, definition, {}, {}, legacy_runtime, None
        )
        self.assertEqual(actual_key, expected_legacy_key)
        changed_runtime = {**runtime, "source_sha256": "0" * 64}
        self.assertEqual(
            artifact_workflow._legacy_package_cache_digest(changed_runtime),
            "0" * 64,
        )
        compatibility_path = (
            Path(artifact_workflow.__file__).with_name(
                "m12_legacy_cache_compatibility.txt"
            )
        )
        compatibility = dict(
            line.split("=", 1)
            for line in compatibility_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        crlf_runtime = {
            **runtime,
            "source_sha256": compatibility["accepted_source_sha256_crlf"],
        }
        self.assertEqual(
            artifact_workflow._legacy_package_cache_digest(crlf_runtime),
            compatibility["legacy_source_sha256_crlf"],
        )

    @staticmethod
    def _registry(calls):
        registry = WorkflowStageRegistry()

        def produce_m5(inputs, output, config):
            marker = Path(output) / "manifest.json"
            if marker.is_file():
                return json.loads(marker.read_text(encoding="utf-8"))
            calls["m5"] += 1
            summary = {
                "schema": "dvg-summary-v1",
                "caller": "synthetic-virema",
                "status": "NO_DVG_EVIDENCE_DETECTED",
                "event_count": 0,
            }
            parameters = {
                "schema": "dvg-parameters-v1",
                "caller": "synthetic-virema",
                "caller_version": "synthetic-1",
                "upstream_commit": "synthetic-commit",
                "source_sha256": {"caller.py": _sha(b"synthetic caller")},
                "configuration": {"mode": "offline-fixture"},
                "input_sha256": {"reads": _sha(b"synthetic reads")},
                "command": ["synthetic-virema", "--offline"],
            }
            return _stage_manifest(output, {
                "summary.json": summary,
                "parameters.json": parameters,
            })

        def produce_m6(inputs, output, config):
            marker = Path(output) / "manifest.json"
            if marker.is_file():
                return json.loads(marker.read_text(encoding="utf-8"))
            calls["m6"] += 1
            residual = {
                "schema": "m6-residual-manifest-v1",
                "status": "complete",
                "sample_id": "synthetic-sample-1",
                "comparison": {
                    "status": "complete",
                    "scope": "synthetic-reference-screen",
                    "input_read_count": 4,
                    "accounted_read_count": 4,
                },
                "counts": {"residual_fragments": 0},
                "source_reads": {"read1": {"sha256": _sha(b"read input")}},
                "qc_artifact": {"sha256": _sha(b"qc input")},
                "artifact_sha256": {"reference": _sha(b"synthetic reference")},
            }
            return _stage_manifest(output, {"residual-manifest.json": residual})

        registry.register(
            "dvg_virema",
            (),
            produce_m5,
            version="synthetic-1",
            output_contracts={
                "summary.json": "dvg_evidence_summary",
                "parameters.json": "dvg_parameters",
            },
        )
        registry.register(
            "residual_evidence",
            (),
            produce_m6,
            version="synthetic-1",
            output_contracts={
                "residual-manifest.json": "residual_read_manifest",
            },
        )
        m12_artifact_review.register_stage(registry)
        return registry

    @staticmethod
    def _write_manifest(root, output, state="NOT_SUPPLIED"):
        workflow = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
        rows = {row["id"]: row for row in workflow["stages"]}
        refs = []
        for stage_id, artifact_type, path, milestone in (
            ("m5", "dvg_evidence_summary", "summary.json", "M5"),
            ("m5", "dvg_parameters", "parameters.json", "M5"),
            ("m6", "residual_read_manifest", "residual-manifest.json", "M6"),
        ):
            stage_root = output / rows[stage_id]["output_path"]
            marker = stage_root / "manifest.json"
            artifact = stage_root / path
            refs.append(_reference(
                milestone,
                stage_id,
                _sha(marker.read_bytes()),
                artifact_type,
                path,
                _sha(artifact.read_bytes()),
            ))
        refs.sort(key=lambda ref: (
            ref["producer_milestone"],
            ref["producer_stage_id"],
            ref["artifact_type"],
            ref["sha256"],
        ))
        manifest = {
            "schema": "m12-input-v1",
            "candidate_id": "synthetic-candidate-1",
            "producer_artifacts": refs,
            "external_evidence": _external_evidence(state),
        }
        path = root / "m12-input.json"
        _write_json(path, manifest)
        return path

    def test_contract_rejects_duplicate_and_unsafe_artifact_references(self):
        ref = _reference("M6", "m6", "a" * 64, "residual_read_manifest",
                         "residual-manifest.json", "b" * 64)
        value = {
            "schema": "m12-input-v1",
            "candidate_id": "synthetic-candidate",
            "producer_artifacts": [ref],
            "external_evidence": _external_evidence(),
        }
        with self.assertRaises(ValueError):
            m12_contracts.validate_input_manifest({
                **value,
                "producer_artifacts": [ref, dict(ref)],
            })
        unsafe = {**ref, "relative_path": "../residual-manifest.json"}
        with self.assertRaises(ValueError):
            m12_contracts.validate_input_manifest({
                **value,
                "producer_artifacts": [unsafe],
            })

    def test_m6_no_signal_requires_exact_nonempty_query_accounting(self):
        evidence = {
            "status": "NO_SUPPORTED_ASSEMBLY",
            "provenance": {"support_input_fragment_ids": ["fragment-a", "fragment-b"]},
            "read_support": [
                {"query_id": "fragment-a", "mate": 0},
                {"query_id": "fragment-b", "mate": 0},
            ],
        }
        group = {
            "residual_read_manifest": [{
                "payload": {"source_reads": {"read1": {"sha256": "c" * 64}}},
            }],
        }
        self.assertEqual(
            m12_artifact_review._support_query_accounting(group, evidence)["status"],
            "COMPLETE",
        )
        evidence["read_support"].pop()
        self.assertEqual(
            m12_artifact_review._support_query_accounting(group, evidence)["status"],
            "INVALID",
        )
        evidence["provenance"]["support_input_fragment_ids"] = []
        evidence["read_support"] = []
        self.assertEqual(
            m12_artifact_review._support_query_accounting(group, evidence)["status"],
            "UNKNOWN",
        )

    def test_m5_failure_and_unknown_statuses_do_not_become_negative_results(self):
        self.assertEqual(
            m12_artifact_review._m5_mapping("ANALYSIS_FAILED"),
            ("FAILED", "UNKNOWN", "NO_OBSERVATION"),
        )
        self.assertEqual(
            m12_artifact_review._m5_mapping("UNRECOGNIZED"),
            ("UNKNOWN", "UNKNOWN", "UNKNOWN"),
        )
        self.assertEqual(
            m12_artifact_review._m6_support_mapping("NO_SUPPORTED_ASSEMBLY", "UNKNOWN")[:3],
            ("UNKNOWN", "UNKNOWN", "NO_OBSERVATION"),
        )
        verified_no_support = {
            "axes": {"review_state": "VERIFIED"},
            "payload": {"status": "NO_SUPPORTED_ASSEMBLY"},
        }
        self.assertEqual(
            m12_artifact_review._m6_reconstruction_mapping(
                "NO_SUPPORTED_ASSEMBLY", None, "COMPLETE"
            ),
            ("UNKNOWN", "UNKNOWN", "NO_OBSERVATION"),
        )
        self.assertEqual(
            m12_artifact_review._m6_reconstruction_mapping(
                "NO_SUPPORTED_ASSEMBLY", verified_no_support, "COMPLETE"
            ),
            ("COMPLETED", "COMPLETE", "NO_SIGNAL_WITHIN_SCOPE"),
        )

    def test_conflicting_m5_summary_and_event_artifacts_are_invalidated_together(self):
        reference = _reference(
            "M5", "m5", "a" * 64, "dvg_evidence_summary",
            "summary.json", "b" * 64,
        )
        evidence_ref = _reference(
            "M5", "m5", "a" * 64, "dvg_evidence",
            "evidence.json", "c" * 64,
        )
        parameters_ref = _reference(
            "M5", "m5", "a" * 64, "dvg_parameters",
            "parameters.json", "d" * 64,
        )
        prepared = [
            {
                "ref": reference,
                "payload": {
                    "status": "NO_DVG_EVIDENCE_DETECTED",
                    "event_count": 0,
                    "caller": "synthetic",
                },
                "axes": {"review_state": "VERIFIED"},
                "invalid_reason": None,
            },
            {
                "ref": evidence_ref,
                "payload": {
                    "status": "DVG_EVIDENCE_DETECTED",
                    "events": [{"event_id": "synthetic-event"}],
                    "caller": "synthetic",
                },
                "axes": {"review_state": "VERIFIED"},
                "invalid_reason": None,
            },
            {
                "ref": parameters_ref,
                "payload": {"caller": "synthetic"},
                "axes": {"review_state": "VERIFIED"},
                "invalid_reason": None,
            },
        ]
        m12_artifact_review._check_cross_artifact_consistency(prepared)
        self.assertTrue(all(
            item["axes"]["review_state"] == "INVALID" for item in prepared
        ))

        support_ref = _reference(
            "M6", "m6", "e" * 64, "read_support_evidence",
            "read_support.json", "f" * 64,
        )
        reconstruction_ref = _reference(
            "M6", "m6", "e" * 64, "reconstruction_evidence",
            "reconstruction.json", "a" * 64,
        )
        m6_rows = [
            {
                "ref": support_ref,
                "payload": {"status": "NOT_EVALUATED"},
                "axes": {"review_state": "VERIFIED"},
                "invalid_reason": None,
            },
            {
                "ref": reconstruction_ref,
                "payload": {"status": "READ_SUPPORTED_ASSEMBLY"},
                "axes": {"review_state": "VERIFIED"},
                "invalid_reason": None,
            },
        ]
        m12_artifact_review._check_cross_artifact_consistency(m6_rows)
        self.assertTrue(all(
            item["axes"]["review_state"] == "INVALID" for item in m6_rows
        ))

    def test_workflow_binds_exact_handoffs_and_isolates_m12_manifest_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "out"
            spec_path = root / "workflow.json"
            calls = {"m5": 0, "m6": 0}
            registry = self._registry(calls)

            _write_json(spec_path, _workflow_spec())
            artifact_workflow.run(spec_path, output, registry)
            self.assertEqual(calls, {"m5": 1, "m6": 1})

            self._write_manifest(root, output)
            _write_json(spec_path, _workflow_spec(include_m12=True))

            declared_stages = _workflow_spec(include_m12=True)["stages"]
            definitions = {
                stage["id"]: artifact_workflow._producer_definition(stage, registry)
                for stage in declared_stages
            }
            review_stage = declared_stages[-1]
            input_manifest = root / "m12-input.json"
            self.assertEqual(
                len(m12_artifact_review.validate_handoff_declarations(
                    input_manifest, review_stage, declared_stages, definitions
                )),
                3,
            )
            for changed_inputs in (
                {
                    **review_stage["inputs"],
                    "m5_summary": {"stage": "m5", "artifact": "parameters.json"},
                },
                {
                    **review_stage["inputs"],
                    "extra": {"stage": "m6", "artifact": "residual-manifest.json"},
                },
                {
                    key: value for key, value in review_stage["inputs"].items()
                    if key != "m6_residual"
                },
                {
                    **review_stage["inputs"],
                    "m5_summary": {
                        "stage": "m6", "artifact": "residual-manifest.json",
                    },
                },
            ):
                with self.subTest(inputs=changed_inputs), self.assertRaises(ValueError):
                    m12_artifact_review.validate_handoff_declarations(
                        input_manifest,
                        {**review_stage, "inputs": changed_inputs},
                        declared_stages,
                        definitions,
                    )

            artifact_workflow.run(spec_path, output, registry)
            first = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            rows = {row["id"]: row for row in first["stages"]}
            self.assertEqual(rows["m5"]["execution"], "verified_reuse")
            self.assertEqual(rows["m6"]["execution"], "verified_reuse")
            self.assertEqual(rows["m12"]["status"], "complete")
            self.assertEqual(calls, {"m5": 1, "m6": 1})

            m12_root = output / rows["m12"]["output_path"]
            table = json.loads(
                (m12_root / "artifact_review_table.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(table), 3)
            observations = {
                row["artifact_ref"]["artifact_type"]: row["observation_status"]
                for row in table
            }
            self.assertEqual(
                observations["dvg_evidence_summary"], "NO_SIGNAL_WITHIN_SCOPE"
            )
            self.assertEqual(
                observations["residual_read_manifest"], "NO_SIGNAL_WITHIN_SCOPE"
            )
            artifact_contracts.validate_artifact(
                m12_root / "artifact_review_table.json",
                "m12_artifact_review_table",
            )
            artifact_contracts.validate_artifact(
                m12_root / "summary.json", "m12_summary"
            )
            artifact_contracts.validate_artifact(
                m12_root / "result_bundle.json", "m12_result_bundle"
            )
            first_m12_key = rows["m12"]["cache_key"]

            self._write_manifest(root, output, state="UNKNOWN")
            artifact_workflow.run(spec_path, output, registry)
            second = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            second_rows = {row["id"]: row for row in second["stages"]}
            self.assertEqual(second_rows["m5"]["execution"], "verified_reuse")
            self.assertEqual(second_rows["m6"]["execution"], "verified_reuse")
            self.assertNotEqual(second_rows["m12"]["cache_key"], first_m12_key)
            self.assertEqual(calls, {"m5": 1, "m6": 1})

            altered = json.loads(
                (root / "m12-input.json").read_text(encoding="utf-8")
            )
            altered["producer_artifacts"][0]["sha256"] = "f" * 64
            _write_json(root / "m12-input.json", altered)
            artifact_workflow.run(spec_path, output, registry)
            third = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            third_rows = {row["id"]: row for row in third["stages"]}
            self.assertEqual(third_rows["m5"]["execution"], "verified_reuse")
            self.assertEqual(third_rows["m6"]["execution"], "verified_reuse")
            self.assertEqual(third_rows["m12"]["status"], "complete")
            third_table = json.loads(
                (output / third_rows["m12"]["output_path"]
                 / "artifact_review_table.json").read_text(encoding="utf-8")
            )
            self.assertIn("INVALID", [row["review_state"] for row in third_table])
            self.assertEqual(calls, {"m5": 1, "m6": 1})

            altered["producer_artifacts"][0]["producer_status"] = "finished"
            _write_json(root / "m12-input.json", altered)
            artifact_workflow.run(spec_path, output, registry)
            fourth = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            fourth_rows = {row["id"]: row for row in fourth["stages"]}
            self.assertEqual(fourth_rows["m12"]["status"], "complete")
            fourth_table = json.loads(
                (output / fourth_rows["m12"]["output_path"]
                 / "artifact_review_table.json").read_text(encoding="utf-8")
            )
            mismatched = next(
                row for row in fourth_table
                if row["artifact_ref"]["artifact_type"] == "dvg_evidence_summary"
            )
            self.assertEqual(mismatched["review_state"], "INVALID")
            self.assertEqual(mismatched["producer_status_raw"], "complete")
            self.assertEqual(calls, {"m5": 1, "m6": 1})

    def test_partial_or_tampered_m12_outputs_are_never_reused_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "out"
            spec_path = root / "workflow.json"
            registry = self._registry({"m5": 0, "m6": 0})
            _write_json(spec_path, _workflow_spec())
            artifact_workflow.run(spec_path, output, registry)
            self._write_manifest(root, output)
            _write_json(spec_path, _workflow_spec(include_m12=True))
            artifact_workflow.run(spec_path, output, registry)

            workflow = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
            rows = {row["id"]: row for row in workflow["stages"]}
            producer_records = {row["id"]: row for row in workflow["stages"]}
            stages = _workflow_spec(include_m12=True)["stages"]
            definitions = {
                stage["id"]: artifact_workflow._producer_definition(stage, registry)
                for stage in stages
            }
            bindings = m12_artifact_review.validate_handoff_declarations(
                root / "m12-input.json",
                stages[-1],
                stages,
                definitions,
            )
            inputs = {
                "manifest": root / "m12-input.json",
                "m5_summary": output / rows["m5"]["output_path"] / "summary.json",
                "m5_parameters": output / rows["m5"]["output_path"] / "parameters.json",
                "m6_residual": output / rows["m6"]["output_path"] / "residual-manifest.json",
            }
            context = m12_artifact_review.build_stage_context(
                inputs, bindings, producer_records, output
            )
            stage_output = output / rows["m12"]["output_path"]
            table_path = stage_output / "artifact_review_table.json"
            table_path.write_bytes(table_path.read_bytes() + b" ")
            self.assertIsNone(
                m12_artifact_review._output_identity(
                    stage_output, context["cache_identity"]
                )
            )

            coordinated = root / "coordinated-tamper"
            m12_artifact_review.run_stage(
                inputs, coordinated, {}, workflow_context=context
            )
            coordinated_table_path = coordinated / "artifact_review_table.json"
            coordinated_table = m12_contracts.read_json(coordinated_table_path)
            coordinated_table.pop(0)
            table_digest = m12_contracts.write_json(
                coordinated_table_path, coordinated_table
            )
            summary_digest = m12_contracts.write_json(
                coordinated / "summary.json",
                m12_artifact_review._make_summary(
                    context["input_manifest"], coordinated_table
                ),
            )
            bundle_path = coordinated / "result_bundle.json"
            bundle = m12_contracts.read_json(bundle_path)
            bundle["outputs"]["m12_artifact_review_table"]["sha256"] = table_digest
            bundle["outputs"]["m12_summary"]["sha256"] = summary_digest
            m12_contracts.write_json(bundle_path, bundle)
            marker_path = coordinated / "manifest.json"
            marker = m12_contracts.read_json(marker_path)
            marker["output_sha256"] = {
                name: m12_artifact_review._sha256_file(coordinated / name)
                for name in m12_artifact_review.OUTPUT_CONTRACTS
            }
            m12_contracts.write_json(marker_path, marker)
            self.assertIsNone(
                m12_artifact_review._output_identity(
                    coordinated, context["cache_identity"]
                )
            )

            partial = root / "partial-m12"
            partial.mkdir()
            (partial / "partial.json").write_text("partial", encoding="utf-8")
            with self.assertRaises(ValueError):
                m12_artifact_review.run_stage(
                    inputs,
                    partial,
                    {},
                    workflow_context=context,
                )
            self.assertFalse((partial / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()