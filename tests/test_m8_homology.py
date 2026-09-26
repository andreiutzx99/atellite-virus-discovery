"""Synthetic workflow regression tests for the integrated M8 stage."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import artifact_contracts, artifact_stage_handlers
from satellite_discovery import artifact_workflow, m8_homology
from satellite_discovery.m8_contracts import PANEL_ROLES
from tests.test_m8_contracts import M8ContractTests
from tests.test_m8_reference_panels import ReferencePanelTests


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _upgrade_candidate_sequences(candidate_path):
    """Give the one-base handoff fixture an informative synthetic sequence."""
    candidate_path = Path(candidate_path)
    document = json.loads(candidate_path.read_text())
    root = candidate_path.parent
    sequence = "ACGTACGTACGTACGT"
    source_ref = document["source_artifact"]
    source_path = root / source_ref["path"]
    source_bytes = (
        f">source-a description\n{sequence}\n>source-b\n{sequence}\n"
    ).encode()
    source_path.write_bytes(source_bytes)
    source_ref["sha256"] = hashlib.sha256(source_bytes).hexdigest()
    document["source_artifact"] = source_ref

    fasta_ref = document["availability"]["fasta_artifact"]
    fasta_path = root / fasta_ref["path"]
    fasta_bytes = (
        f">source-a description\n{sequence}\n>source-b\n{sequence}\n"
    ).encode()
    fasta_path.write_bytes(fasta_bytes)
    fasta_ref["sha256"] = hashlib.sha256(fasta_bytes).hexdigest()
    sequence_hash = hashlib.sha256(sequence.encode()).hexdigest()
    for record in document["records"]:
        record["sequence_length"] = len(sequence)
        record["sequence_sha256"] = sequence_hash
        record["source_artifact_sha256"] = source_ref["sha256"]
    candidate_path.write_text(json.dumps(document, sort_keys=True))


def _role_plan(selected=("satellite_subviral", "virus_helper")):
    return {
        role: (
            {"status": "SELECTED"} if role in selected else
            {"status": "NOT_SELECTED", "reason": "outside synthetic test scope"}
        )
        for role in sorted(PANEL_ROLES)
    }


class M8HomologyWorkflowTests(unittest.TestCase):
    def _fixtures(self, root):
        candidate_root = Path(root) / "candidate"
        candidate_root.mkdir()
        candidate, _ = M8ContractTests()._candidate_set(candidate_root)
        _upgrade_candidate_sequences(candidate)
        panel_root = Path(root) / "panel"
        panel_root.mkdir()
        manifest, _fasta, indexes, _ = ReferencePanelTests().make_fixture(panel_root)
        payloads = {
            "reference_payload_panel_fasta": _fasta,
            **{
                m8_homology.payload_input_name(name): path
                for name, path in indexes.items()
            },
        }
        return candidate, manifest, payloads

    def _config(self):
        return {"role_plan": _role_plan()}

    def _spec(self, root, candidate, manifest, payloads):
        inputs = {
            "candidate_sequence_set": {
                "path": str(Path(candidate).relative_to(root)),
                "artifact_type": "m8_candidate_sequence_set",
            },
            "reference_snapshot_manifest": {
                "path": str(Path(manifest).relative_to(root)),
                "artifact_type": "m8_reference_snapshot_manifest",
            },
        }
        inputs.update({
            name: {
                "path": str(Path(path).relative_to(root)),
                "artifact_type": "m8_reference_payload",
            }
            for name, path in payloads.items()
        })
        return {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m8",
                "kind": "m8_homology",
                "inputs": inputs,
                "config": self._config(),
            }],
        }

    @staticmethod
    def _fake_branch(query_path, _database, directory, query, references,
                     branch, **_kwargs):
        # Preserve both candidate identities even though their sequence bytes match.
        hit = query["query_id"] == "source-a" and branch == "dust_masked"
        reference = references["ACC001.1"]
        rows = []
        if hit:
            rows = [{
                "query_id": query["query_id"], "reference_id": "ACC001.1",
                "raw_row_ordinal": 1, "percent_identity": 100.0,
                "alignment_length": 5, "mismatches": 0, "gap_openings": 0,
                "query_start": 1, "query_end": 5, "reference_start": 1,
                "reference_end": 5, "evalue": 1e-5, "bitscore": 10.0,
                "query_length": 16, "reference_length": 5, "strand": "+",
                "query_coverage_bases": 5, "query_coverage": 5 / 16,
                "reference_coverage_bases": 5, "reference_coverage": 1.0,
                "raw_output_sha256": "a" * 64, "reference": reference,
            }]
        raw_path = Path(directory) / f"blastn_{branch}.tsv"
        raw_bytes = b""
        if hit:
            raw_bytes = (
                f"{query['query_id']}\tACC001.1\t100\t5\t0\t0\t1\t5\t1\t5"
                "\t1e-5\t10\t16\t5\tplus\n"
            ).encode()
        raw_path.write_bytes(raw_bytes)
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        for row in rows:
            row["raw_output_sha256"] = raw_hash
        return {
            "status": (
                "SEARCH_COMPLETED_MATCHES_REPORTED" if rows
                else "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
            ),
            "rows": rows, "task": "blastn-short",
            "raw_output": str(raw_path), "raw_output_sha256": raw_hash,
            "truncated": False, "masking_branch": branch,
        }

    def test_workflow_keeps_duplicate_candidates_and_aggregates_branches(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate, manifest, payloads = self._fixtures(root)
            spec = self._spec(root, candidate, manifest, payloads)
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(spec))
            with patch.object(m8_homology, "inspect_dependency",
                              return_value={"status": "available"}), \
                 patch.object(m8_homology.m8_search_adapters,
                              "run_blast_branch", side_effect=self._fake_branch):
                registry = artifact_workflow.build_default_registry()
                result = artifact_workflow.run(spec_path, root / "out", registry)
            self.assertEqual(result, root / "out" / "report.html")
            manifest = json.loads((root / "out" / "workflow.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            stage_output = root / "out" / manifest["stages"][0]["output_path"]
            stage = json.loads(
                (stage_output / "query_status.json").read_text()
            )
            selected = [
                row for row in stage["queries"]
                if row["panel_role"] == "satellite_subviral"
            ]
            self.assertEqual({row["candidate_id"] for row in selected},
                             {"candidate-1", "candidate-2"})
            self.assertTrue(all(row["aggregate_status"] == "COMPLETE"
                                for row in selected))
            self.assertEqual(
                [row["status"] for row in selected],
                ["SEARCH_COMPLETED_MATCHES_REPORTED",
                 "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"],
            )
            evidence = json.loads(
                (stage_output / "matches.json").read_text()
            )
            self.assertEqual(
                [row["candidate_id"] for row in evidence["matches"]],
                ["candidate-1"],
            )

    def test_tampered_payload_is_invalid_not_no_hit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate, manifest, payloads = self._fixtures(root)
            payloads["reference_payload_panel_fasta"].write_bytes(b">tampered\nA\n")
            spec = self._spec(root, candidate, manifest, payloads)
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(spec))
            with patch.object(m8_homology, "inspect_dependency",
                              return_value={"status": "available"}), \
                 patch.object(m8_homology.m8_search_adapters,
                              "run_blast_branch") as run:
                artifact_workflow.run(spec_path, root / "out")
            status = json.loads(
                (root / "out" / "m8" / "query_status.json").read_text()
            )
            branches = [
                branch for query in status["queries"]
                for branch in query.get("branches", [])
                if query["panel_role"] == "satellite_subviral"
            ]
            self.assertTrue(branches)
            self.assertTrue(all(branch["status"] == "REFERENCE_PANEL_INVALID"
                                for branch in branches))
            run.assert_not_called()
            self.assertNotEqual(
                status["aggregate_status"],
                "COMPLETE",
            )

    def test_missing_declared_payload_is_incomplete_and_keeps_snapshot_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate, manifest, payloads = self._fixtures(root)
            payloads.pop("reference_payload_panel_fasta")
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(
                self._spec(root, candidate, manifest, payloads)
            ))
            with patch.object(m8_homology, "inspect_dependency",
                              return_value={"status": "available"}), \
                 patch.object(m8_homology.m8_search_adapters,
                              "run_blast_branch") as run:
                registry = artifact_workflow.build_default_registry()
                artifact_workflow.run(spec_path, root / "out", registry)
            workflow = json.loads((root / "out" / "workflow.json").read_text())
            stage_output = root / "out" / workflow["stages"][0]["output_path"]
            status = json.loads((stage_output / "query_status.json").read_text())
            summary = json.loads((stage_output / "summary.json").read_text())
            branches = [
                branch for query in status["queries"]
                if query["panel_role"] == "satellite_subviral"
                for branch in query.get("branches", [])
            ]
            self.assertEqual(status["panel_state"], "INCOMPLETE")
            self.assertTrue(branches)
            self.assertTrue(all(
                branch["status"] == "REFERENCE_PANEL_INCOMPLETE"
                for branch in branches
            ))
            self.assertEqual(
                summary["reference_panel"]["snapshot_id"], "synthetic-v1"
            )
            run.assert_not_called()

    def test_exact_contracts_and_payload_change_cache_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate, manifest, payloads = self._fixtures(root)
            spec = self._spec(root, candidate, manifest, payloads)
            artifact_workflow.validate(spec)
            bad = json.loads(json.dumps(spec))
            bad["stages"][0]["inputs"]["candidate_sequence_set"]["artifact_type"] = (
                "raw_fasta"
            )
            with self.assertRaises(ValueError):
                artifact_workflow.validate(bad)
            definition = artifact_workflow.build_default_registry().get("m8_homology")
            config = m8_homology.validate_config(self._config())
            descriptors = {
                "candidate_sequence_set": artifact_contracts.describe_artifact(
                    candidate, "m8_candidate_sequence_set"),
                "reference_snapshot_manifest": artifact_contracts.describe_artifact(
                    manifest, "m8_reference_snapshot_manifest"),
            }
            payload_name, payload_path = next(iter(payloads.items()))
            descriptors[payload_name] = artifact_contracts.describe_artifact(
                payload_path, "m8_reference_payload")
            stage = {"id": "m8", "kind": "m8_homology"}
            first = artifact_workflow._stage_cache_key(
                stage, definition, config, descriptors, {}, None)
            payload_path.write_bytes(payload_path.read_bytes() + b"x")
            descriptors[payload_name] = artifact_contracts.describe_artifact(
                payload_path, "m8_reference_payload")
            second = artifact_workflow._stage_cache_key(
                stage, definition, config, descriptors, {}, None)
            self.assertNotEqual(first, second)

    def test_report_links_typed_m8_summary_and_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = root / "summary.json"
            evidence = root / "matches.json"
            summary.write_text(json.dumps({
                "schema": "m8-homology-summary-v1",
                "aggregate_status": "PARTIAL",
                "panel_role_results": [],
            }))
            evidence.write_text(json.dumps({
                "schema": "m8-match-evidence-v1", "match_count": 0, "matches": [],
            }))
            output = root / "report"
            artifact_stage_handlers.workflow_report({
                "m8_summary": summary, "m8_evidence": evidence,
            }, output, {})
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["artifacts"]["m8_summary"]["schema"],
                             "m8-homology-summary-v1")
            self.assertEqual(report["artifacts"]["m8_evidence"]["schema"],
                             "m8-match-evidence-v1")
            self.assertIn("sha256", report["artifacts"]["m8_summary"])


if __name__ == "__main__":
    unittest.main()