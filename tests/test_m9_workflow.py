"""Offline synthetic workflow tests for the integrated M9 baseline."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import artifact_workflow, m8_homology, m9_blastp_stage
from satellite_discovery.m9_search_adapters import (
    inspect_blastp_runtime,
    profile_identity,
)
from tests import test_m8_contracts as _m8_contract_fixtures
from tests import test_m8_homology as _m8_workflow_fixtures


_CODONS = {
    "A": "GCT", "C": "TGT", "D": "GAT", "E": "GAA", "F": "TTT",
    "G": "GGT", "H": "CAT", "I": "ATT", "K": "AAA", "L": "CTT",
    "M": "ATG", "N": "AAT", "P": "CCT", "Q": "CAA", "R": "CGT",
    "S": "TCT", "T": "ACT", "V": "GTT", "W": "TGG", "Y": "TAT",
}
_PROTEIN = "MRTYVKDLEQGFAWPNHCSIMVYRTEGKLDPNQISAFWV"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _coding_sequence():
    return "".join(_CODONS[amino_acid] for amino_acid in _PROTEIN) + "TAA"


def _set_candidate_sequence(candidate_path, sequence):
    candidate_path = Path(candidate_path)
    document = json.loads(candidate_path.read_text(encoding="utf-8"))
    root = candidate_path.parent
    source_ref = document["source_artifact"]
    source_bytes = (
        f">source-a synthetic\n{sequence}\n>source-b synthetic\n{sequence}\n"
    ).encode("ascii")
    (root / source_ref["path"]).write_bytes(source_bytes)
    source_ref["sha256"] = _sha(source_bytes)
    document["source_artifact"] = source_ref
    fasta_ref = document["availability"]["fasta_artifact"]
    fasta_bytes = (
        f">source-a synthetic\n{sequence}\n>source-b synthetic\n{sequence}\n"
    ).encode("ascii")
    (root / fasta_ref["path"]).write_bytes(fasta_bytes)
    fasta_ref["sha256"] = _sha(fasta_bytes)
    sequence_hash = _sha(sequence.encode("ascii"))
    for row in document["records"]:
        row["sequence_length"] = len(sequence)
        row["sequence_sha256"] = sequence_hash
        row["source_artifact_sha256"] = source_ref["sha256"]
    candidate_path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return candidate_path


def _make_snapshot(root, completeness="complete"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    decoy = "M" + _PROTEIN[1:20][::-1]
    records = []
    sequences = (("syn-ref-1", "SYNTH.1", _PROTEIN),
                 ("syn-ref-2", "SYNTH.2", decoy))
    for record_id, accession, sequence in sequences:
        records.append({
            "record_id": record_id,
            "accession_version": accession,
            "role": "synthetic_technical",
            "length": len(sequence),
            "sha256": _sha(sequence.encode("ascii")),
        })
    payload = "".join(
        f">{record_id}\n{sequence}\n"
        for record_id, _accession, sequence in sequences
    ).encode("ascii")
    payload_path = root / "proteins.faa"
    payload_path.write_bytes(payload)
    manifest = {
        "schema": "m9-protein-reference-snapshot-v1",
        "snapshot_id": "synthetic-proteins-v1",
        "payload_sha256": _sha(payload),
        "completeness": completeness,
        "records": records,
        "provenance": {
            "source": "local synthetic fixture",
            "release": "fixture-v1",
            "rights": "synthetic test material",
            "terms": "offline test only",
        },
    }
    manifest["snapshot_digest"] = _sha(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8"))
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest_path, payload_path


def _failed_m8_branch(_query_path, _database, directory, query, _references,
                      branch, **_kwargs):
    raw_path = Path(directory) / f"synthetic_{branch}.tsv"
    raw_path.write_bytes(b"")
    return {
        "status": (
            "SEARCH_FAILED"
            if query["query_id"] == "source-a" and branch == "dust_masked"
            else "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
        ),
        "rows": [],
        "task": "blastn-short",
        "raw_output": str(raw_path),
        "raw_output_sha256": _sha(b""),
        "truncated": False,
        "masking_branch": branch,
        "error": "synthetic planned branch failure",
    }


class M9WorkflowTests(unittest.TestCase):
    def _inputs(self, root):
        root = Path(root)
        candidate_dir = root / "candidate"
        candidate_dir.mkdir()
        candidate_path, _ = _m8_contract_fixtures.M8ContractTests()._candidate_set(
            candidate_dir)
        candidate_path = _set_candidate_sequence(candidate_path, _coding_sequence())
        snapshot_manifest, snapshot_payload = _make_snapshot(root / "snapshot")
        return candidate_path, snapshot_manifest, snapshot_payload

    @staticmethod
    def _plain_spec(root, candidate_path, snapshot_manifest, snapshot_payload):
        return {
            "schema": "artifact-workflow-v1",
            "stages": [
                {
                    "id": "orfs", "kind": "m9_orf_translation",
                    "inputs": {
                        "candidate_sequence_set": {
                            "path": str(candidate_path.relative_to(root)),
                            "artifact_type": "m8_candidate_sequence_set",
                        },
                    },
                    "config": {},
                },
                {
                    "id": "search", "kind": "m9_blastp",
                    "inputs": {
                        "orf_results": {"stage": "orfs", "artifact": "orf_results.json"},
                        "protein_fasta": {"stage": "orfs", "artifact": "proteins.faa"},
                        "reference_manifest": {
                            "path": str(snapshot_manifest.relative_to(root)),
                            "artifact_type": "m9_protein_reference_manifest",
                        },
                        "reference_payload": {
                            "path": str(snapshot_payload.relative_to(root)),
                            "artifact_type": "m9_protein_reference_payload",
                        },
                    },
                    "config": {"timeout_seconds": 60, "max_output_bytes": 20_000_000},
                },
            ],
        }

    @staticmethod
    def _run_simple(root, spec):
        spec_path = root / "workflow.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        report = artifact_workflow.run(
            spec_path, root / "out", artifact_workflow.build_default_registry())
        workflow = json.loads((root / "out" / "workflow.json").read_text())
        return report, workflow

    @staticmethod
    def _m8_spec_inputs(root, candidate_path, m8_manifest, m8_payloads):
        helper = _m8_workflow_fixtures.M8HomologyWorkflowTests()
        return helper._spec(root, candidate_path, m8_manifest, m8_payloads)

    def test_offline_workflow_preserves_m8_failure_and_runs_real_blastp(self):
        if inspect_blastp_runtime()["status"] != "available":
            self.skipTest("pinned local BLASTP 2.16.0 is unavailable")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m8_fixture_root = root / "m8-fixture"
            m8_fixture_root.mkdir()
            candidate_path, m8_manifest, m8_payloads = (
                _m8_workflow_fixtures.M8HomologyWorkflowTests()._fixtures(
                    m8_fixture_root))
            candidate_path = _set_candidate_sequence(
                candidate_path, _coding_sequence())
            snapshot_manifest, snapshot_payload = _make_snapshot(root / "snapshot")
            m8_spec = self._m8_spec_inputs(
                root, candidate_path, m8_manifest, m8_payloads)
            stages = m8_spec["stages"]
            stages.extend([
                {
                    "id": "m9_orfs",
                    "kind": "m9_orf_translation",
                    "inputs": {
                        "candidate_sequence_set": {
                            "path": str(candidate_path.relative_to(root)),
                            "artifact_type": "m8_candidate_sequence_set",
                        },
                        "m8_query_status": {
                            "stage": "m8", "artifact": "query_status.json",
                        },
                        "m8_match_evidence": {
                            "stage": "m8", "artifact": "matches.json",
                        },
                        "m8_summary": {
                            "stage": "m8", "artifact": "summary.json",
                        },
                        "m8_search_commands": {
                            "stage": "m8", "artifact": "commands.json",
                        },
                    },
                    "config": {},
                },
                {
                    "id": "m9_search",
                    "kind": "m9_blastp",
                    "inputs": {
                        "orf_results": {
                            "stage": "m9_orfs", "artifact": "orf_results.json",
                        },
                        "protein_fasta": {
                            "stage": "m9_orfs", "artifact": "proteins.faa",
                        },
                        "reference_manifest": {
                            "path": str(snapshot_manifest.relative_to(root)),
                            "artifact_type": "m9_protein_reference_manifest",
                        },
                        "reference_payload": {
                            "path": str(snapshot_payload.relative_to(root)),
                            "artifact_type": "m9_protein_reference_payload",
                        },
                    },
                    "config": {"timeout_seconds": 60, "max_output_bytes": 20_000_000},
                },
            ])
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(m8_spec), encoding="utf-8")

            with patch.object(
                    m8_homology, "inspect_dependency",
                    return_value={"status": "available"}), \
                 patch.object(
                    m8_homology.m8_search_adapters, "run_blast_branch",
                    side_effect=_failed_m8_branch):
                artifact_workflow.run(
                    spec_path, root / "out",
                    artifact_workflow.build_default_registry(),
                )

            workflow = json.loads((root / "out" / "workflow.json").read_text())
            by_id = {row["id"]: row for row in workflow["stages"]}
            self.assertEqual(workflow["status"], "complete")
            self.assertEqual(by_id["m9_orfs"]["status"], "complete")
            self.assertEqual(by_id["m9_search"]["status"], "complete")

            orf_dir = root / "out" / by_id["m9_orfs"]["output_path"]
            orfs = json.loads((orf_dir / "orf_results.json").read_text())
            self.assertEqual(orfs["aggregate_status"], "COMPLETE")
            self.assertEqual(orfs["m8_context"]["state"], "VERIFIED")
            self.assertEqual(orfs["m8_context"]["statuses"]["m8_summary"]["aggregate_status"],
                             "PARTIAL")
            identities = [
                (row["candidate_id"], row["sequence_id"], orf["orf_id"])
                for row in orfs["candidates"] for orf in row["orfs"]
            ]
            self.assertEqual(len({candidate for candidate, _, _ in identities}), 2)
            self.assertEqual(len({orf_id for _, _, orf_id in identities}), len(identities))

            search_dir = root / "out" / by_id["m9_search"]["output_path"]
            status = json.loads((search_dir / "query_status.json").read_text())
            evidence = json.loads((search_dir / "matches.json").read_text())
            self.assertEqual(status["aggregate_status"], "COMPLETE")
            self.assertEqual(status["expected_orf_query_count"], len(identities))
            self.assertEqual(status["observed_query_count"], len(identities))
            self.assertTrue(any(
                row["reference_id"] == "syn-ref-1"
                and row["percent_identity"] == 100.0
                for row in evidence["matches"]
            ))
            self.assertTrue(all(
                row["query_coverage_denominator"] == row["query_length"]
                and row["reference_coverage_denominator"] == row["reference_length"]
                for row in evidence["matches"]
            ))

    def test_snapshot_change_does_not_change_orf_stage_cache_identity(self):
        if inspect_blastp_runtime()["status"] != "available":
            self.skipTest("pinned local BLASTP 2.16.0 is unavailable")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path, snapshot_manifest, snapshot_payload = self._inputs(root)
            spec = {
                "schema": "artifact-workflow-v1",
                "stages": [
                    {
                        "id": "orfs", "kind": "m9_orf_translation",
                        "inputs": {
                            "candidate_sequence_set": {
                                "path": str(candidate_path.relative_to(root)),
                                "artifact_type": "m8_candidate_sequence_set",
                            },
                        },
                        "config": {},
                    },
                    {
                        "id": "search", "kind": "m9_blastp",
                        "inputs": {
                            "orf_results": {"stage": "orfs", "artifact": "orf_results.json"},
                            "protein_fasta": {"stage": "orfs", "artifact": "proteins.faa"},
                            "reference_manifest": {
                                "path": str(snapshot_manifest.relative_to(root)),
                                "artifact_type": "m9_protein_reference_manifest",
                            },
                            "reference_payload": {
                                "path": str(snapshot_payload.relative_to(root)),
                                "artifact_type": "m9_protein_reference_payload",
                            },
                        },
                        "config": {"timeout_seconds": 60, "max_output_bytes": 20_000_000},
                    },
                ],
            }
            spec_path = root / "workflow.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            registry = artifact_workflow.build_default_registry()
            artifact_workflow.run(spec_path, root / "out", registry)
            first = json.loads((root / "out" / "workflow.json").read_text())
            first_rows = {row["id"]: row for row in first["stages"]}

            changed_manifest, changed_payload = _make_snapshot(
                root / "snapshot-changed", completeness="complete")
            payload_bytes = changed_payload.read_bytes().replace(
                b"SYNTH.2", b"SYNTH.3")
            # Keep a valid snapshot whose contents and identities differ.
            changed_payload.write_bytes(payload_bytes)
            changed_doc = json.loads(changed_manifest.read_text())
            changed_doc["payload_sha256"] = _sha(payload_bytes)
            changed_doc["records"][1]["accession_version"] = "SYNTH.3"
            changed_doc["snapshot_digest"] = _sha(json.dumps(
                {k: v for k, v in changed_doc.items() if k != "snapshot_digest"},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("utf-8"))
            changed_manifest.write_text(json.dumps(changed_doc), encoding="utf-8")
            spec["stages"][1]["inputs"]["reference_manifest"]["path"] = str(
                changed_manifest.relative_to(root))
            spec["stages"][1]["inputs"]["reference_payload"]["path"] = str(
                changed_payload.relative_to(root))
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            artifact_workflow.run(spec_path, root / "out", registry)
            second = json.loads((root / "out" / "workflow.json").read_text())
            second_rows = {row["id"]: row for row in second["stages"]}

            self.assertEqual(first_rows["orfs"]["cache_key"],
                             second_rows["orfs"]["cache_key"])
            self.assertNotEqual(first_rows["search"]["cache_key"],
                                second_rows["search"]["cache_key"])

    def test_dependency_failure_is_accounted_not_reported_as_no_hit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path, snapshot_manifest, snapshot_payload = self._inputs(root)
            spec = self._plain_spec(
                root, candidate_path, snapshot_manifest, snapshot_payload)
            missing = {
                "status": "DEPENDENCY_UNAVAILABLE",
                "profile": profile_identity(),
                "blastp": {"path": None, "sha256": None, "version": None, "pinned": False},
                "makeblastdb": {"path": None, "sha256": None, "version": None, "pinned": False},
            }
            with patch.object(
                    m9_blastp_stage, "inspect_blastp_runtime",
                    return_value=missing):
                _report, workflow = self._run_simple(root, spec)
            stage = next(row for row in workflow["stages"] if row["id"] == "search")
            search_dir = root / "out" / stage["output_path"]
            status = json.loads((search_dir / "query_status.json").read_text())
            self.assertEqual(status["aggregate_status"], "PARTIAL")
            self.assertEqual(
                {row["status"] for row in status["queries"]},
                {"DEPENDENCY_UNAVAILABLE"},
            )
            self.assertEqual(
                status["expected_orf_query_count"],
                status["observed_query_count"],
            )
            self.assertEqual(status["query_accounting"]["missing_query_ids"], [])
            self.assertFalse(json.loads(
                (search_dir / "matches.json").read_text())["matches"])

    def test_no_orf_candidates_are_accounted_without_searching(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path, snapshot_manifest, snapshot_payload = self._inputs(root)
            candidate_path = _set_candidate_sequence(candidate_path, "CCCCCCCC")
            spec = self._plain_spec(
                root, candidate_path, snapshot_manifest, snapshot_payload)
            missing = {
                "status": "DEPENDENCY_UNAVAILABLE",
                "profile": profile_identity(),
                "blastp": {"path": None, "sha256": None, "version": None, "pinned": False},
                "makeblastdb": {"path": None, "sha256": None, "version": None, "pinned": False},
            }
            with patch.object(
                    m9_blastp_stage, "inspect_blastp_runtime",
                    return_value=missing):
                _report, workflow = self._run_simple(root, spec)
            stage = next(row for row in workflow["stages"] if row["id"] == "search")
            search_dir = root / "out" / stage["output_path"]
            status = json.loads((search_dir / "query_status.json").read_text())
            self.assertEqual(status["aggregate_status"], "COMPLETE")
            self.assertEqual(status["expected_orf_query_count"], 0)
            self.assertEqual(status["observed_query_count"], 0)
            self.assertEqual(status["queries"], [])
            self.assertTrue(all(
                row["status"] == "NOT_RUN_NO_ORF"
                for row in status["candidate_statuses"]
            ))

    def test_incomplete_snapshot_never_becomes_a_no_hit(self):
        if inspect_blastp_runtime()["status"] != "available":
            self.skipTest("pinned local BLASTP 2.16.0 is unavailable")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidate_path, snapshot_manifest, snapshot_payload = self._inputs(root)
            manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
            manifest["completeness"] = "incomplete"
            manifest["snapshot_digest"] = _sha(json.dumps(
                {key: value for key, value in manifest.items()
                 if key != "snapshot_digest"},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("utf-8"))
            snapshot_manifest.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            spec = self._plain_spec(
                root, candidate_path, snapshot_manifest, snapshot_payload)
            _report, workflow = self._run_simple(root, spec)
            stage = next(row for row in workflow["stages"] if row["id"] == "search")
            search_dir = root / "out" / stage["output_path"]
            status = json.loads((search_dir / "query_status.json").read_text())
            evidence = json.loads((search_dir / "matches.json").read_text())
            self.assertEqual(status["aggregate_status"], "PARTIAL")
            self.assertTrue(status["queries"])
            self.assertEqual(
                {row["status"] for row in status["queries"]},
                {"REFERENCE_SNAPSHOT_INCOMPLETE"},
            )
            self.assertTrue(any(row["scope_state"] == "INCOMPLETE"
                                for row in evidence["matches"]))
            self.assertNotIn(
                "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
                {row["status"] for row in status["queries"]},
            )


if __name__ == "__main__":
    unittest.main()