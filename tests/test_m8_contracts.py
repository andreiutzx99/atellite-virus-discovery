import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery import artifact_contracts
from satellite_discovery.artifact_workflow import build_default_registry, _stage_cache_key
from satellite_discovery.m8_candidate_handoff import validate_candidate_sequence_set
from satellite_discovery.m8_contracts import (
    AGGREGATE_STATUSES,
    PANEL_ROLES,
    SEARCH_STATUSES,
    aggregate_search_status,
    completed_search_status,
    map_fixture_status,
    normalize_panel_role,
)


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _write(path, content, root):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)
    return {"path": str(Path(path).relative_to(Path(root))),
            "sha256": _sha256(content)}


class M8ContractTests(unittest.TestCase):
    def test_normative_roles_and_contextual_fixture_aliases(self):
        self.assertEqual(PANEL_ROLES, {
            "satellite_subviral", "virus_helper", "host_nuclear",
            "host_organelle", "microbial", "vector", "plasmid", "adapter",
            "technical_contaminant", "mobile_element", "related_non_satellite",
        })
        self.assertEqual(
            normalize_panel_role("delta-related-subviral"),
            {"role": "related_non_satellite", "subrole": "deltavirus_context"},
        )
        self.assertEqual(
            normalize_panel_role("viroid"),
            {"role": "related_non_satellite", "subrole": "viroid_context"},
        )
        self.assertEqual(
            normalize_panel_role("polinton_related"),
            {"role": "related_non_satellite", "subrole": "polinton_like_context"},
        )
        self.assertEqual(
            normalize_panel_role(
                "related_non_satellite", "polinton_like_virus_context"),
            {"role": "related_non_satellite", "subrole": "polinton_like_context"},
        )
        self.assertEqual(
            normalize_panel_role("satellite_subviral", "plant_satellite_dna"),
            {"role": "satellite_subviral", "subrole": "satellite_dna"},
        )
        self.assertEqual(
            normalize_panel_role("satellite_subviral", "plant_satellite_rna"),
            {"role": "satellite_subviral", "subrole": "satellite_rna"},
        )
        self.assertEqual(
            normalize_panel_role("satellite_subviral", "plant_satellite_virus"),
            {"role": "satellite_subviral", "subrole": "satellite_virus"},
        )
        self.assertEqual(
            normalize_panel_role("virus_helper", "documented_helper_context"),
            {"role": "virus_helper", "subrole": "declared_potential_helper"},
        )
        self.assertEqual(
            normalize_panel_role("virus_helper", "segmented_helper_genome"),
            {"role": "virus_helper", "subrole": "segmented_helper_genome"},
        )
        self.assertEqual(
            normalize_panel_role("host", "mitochondrial"),
            {"role": "host_organelle", "subrole": "mitochondrial"},
        )
        self.assertEqual(
            normalize_panel_role("host", "nuclear"),
            {"role": "host_nuclear", "subrole": None},
        )
        self.assertEqual(
            normalize_panel_role("vector_plasmid", "plasmid"),
            {"role": "plasmid", "subrole": None},
        )
        self.assertEqual(
            normalize_panel_role("reagent"),
            {"role": "technical_contaminant", "subrole": "reagent"},
        )
        with self.assertRaisesRegex(ValueError, "requires a nuclear or organelle"):
            normalize_panel_role("host")
        with self.assertRaisesRegex(ValueError, "requires vector or plasmid"):
            normalize_panel_role("vector_plasmid")
        with self.assertRaises(ValueError):
            normalize_panel_role("satellite_subviral", "deltavirus_context")
        with self.assertRaisesRegex(ValueError, "must be split"):
            normalize_panel_role(
                "related_non_satellite",
                "polinton_related_and_virophage_label_conflict",
            )
        with self.assertRaisesRegex(ValueError, "conflates"):
            normalize_panel_role(
                "related_non_satellite", "virophage_and_proviral_context")
        self.assertEqual(
            normalize_panel_role(
                "related_non_satellite", "virophage_and_proviral_context",
                accession_version="KU052222.1"),
            {"role": "related_non_satellite", "subrole": "proviral_context"},
        )
        with self.assertRaisesRegex(ValueError, "only the reviewed"):
            normalize_panel_role(
                "related_non_satellite", "virophage_and_proviral_context",
                accession_version="other-record.1")

    def test_status_serialization_keeps_no_hit_distinct_from_failure(self):
        self.assertEqual(
            completed_search_status(hit_count=0, accounting_complete=True),
            "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
        )
        self.assertEqual(
            completed_search_status(hit_count=2, accounting_complete=True),
            "SEARCH_COMPLETED_MATCHES_REPORTED",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=False, execution_state="COMPLETED"),
            "SEARCH_FAILED",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True, dependency_available=False),
            "DEPENDENCY_UNAVAILABLE",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True, panel_state="INVALID"),
            "REFERENCE_PANEL_INVALID",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True, panel_state="INCOMPLETE"),
            "REFERENCE_PANEL_INCOMPLETE",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=1, accounting_complete=True, output_truncated=True),
            "SEARCH_TRUNCATED",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True, execution_state="INTERRUPTED"),
            "SEARCH_INTERRUPTED",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True, method_informative=False),
            "INSUFFICIENT_INFORMATION",
        )
        self.assertEqual(
            completed_search_status(
                hit_count=1, accounting_complete=True, method_informative=False),
            "SEARCH_COMPLETED_MATCHES_REPORTED",
        )
        self.assertEqual(
            completed_search_status(hit_count=0, accounting_complete=True,
                                    candidate_valid=False),
            "INPUT_INVALID",
        )
        self.assertEqual(
            aggregate_search_status([
                "SEARCH_COMPLETED_MATCHES_REPORTED",
                "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
            ]),
            "COMPLETE",
        )
        self.assertEqual(
            aggregate_search_status([
                "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
                "SEARCH_TRUNCATED",
            ]),
            "PARTIAL",
        )
        self.assertEqual(
            aggregate_search_status(
                ["SEARCH_COMPLETED_MATCHES_REPORTED"],
                required_branch_count=2,
            ),
            "PARTIAL",
        )
        with self.assertRaises(ValueError):
            aggregate_search_status(["AMBIGUOUS"])
        self.assertEqual(
            map_fixture_status(
                "COMPLETE", hit_count=0, accounting_complete=True),
            "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
        )
        self.assertEqual(
            map_fixture_status(
                "COMPLETE", hit_count=1, accounting_complete=True),
            "SEARCH_COMPLETED_MATCHES_REPORTED",
        )
        self.assertEqual(map_fixture_status("PARTIAL"), "PARTIAL")
        self.assertEqual(
            map_fixture_status("UNAVAILABLE", cause="dependency"),
            "DEPENDENCY_UNAVAILABLE",
        )
        self.assertEqual(
            map_fixture_status("FAILED", cause="interrupted"),
            "SEARCH_INTERRUPTED",
        )
        for fixture_label in ("AMBIGUOUS", "KNOWN", "SIMILAR"):
            self.assertEqual(
                map_fixture_status(
                    fixture_label, hit_count=1, accounting_complete=True),
                "SEARCH_COMPLETED_MATCHES_REPORTED",
            )
            with self.assertRaises(ValueError):
                map_fixture_status(fixture_label)
        with self.assertRaisesRegex(ValueError, "specific software cause"):
            map_fixture_status("UNAVAILABLE")
        with self.assertRaises(ValueError):
            map_fixture_status("FAILED")
        self.assertIn("SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
                      SEARCH_STATUSES)
        self.assertIn("SEARCH_TRUNCATED", SEARCH_STATUSES)
        self.assertEqual(AGGREGATE_STATUSES, {"COMPLETE", "PARTIAL"})
        self.assertFalse({"AMBIGUOUS", "KNOWN", "SIMILAR"} & SEARCH_STATUSES)

    def _candidate_set(self, root, *, state="AVAILABLE", with_records=True):
        root = Path(root)
        assembly = root / "assembly" / "contigs.fasta"
        assembly_bytes = b">source-a description\nA\n>source-b\nA\n"
        source_ref = _write(assembly, assembly_bytes, root) if with_records else None
        assembly_manifest = root / "assembly" / "assembly_manifest.json"
        assembly_manifest_bytes = json.dumps({
            "schema": "assembly-manifest-v1",
            "workflow_status": "complete",
            "contig_count": 2,
            "assembler": "synthetic",
            "external_tool_version": "test",
        }, sort_keys=True).encode()
        assembly_manifest_ref = (
            _write(assembly_manifest, assembly_manifest_bytes, root)
            if with_records else None
        )
        evidence_path = root / "reconstruction_evidence.json"
        evidence = {
            "schema": "m6-reconstruction-evidence-v1",
            "status": "NO_SUPPORTED_ASSEMBLY" if with_records else "ASSEMBLY_NOT_ATTEMPTED",
            "contigs": [],
            "configuration": {},
            "provenance": {},
        }
        evidence_bytes = json.dumps(evidence, sort_keys=True).encode()
        evidence_path.write_bytes(evidence_bytes)
        records = []
        fasta_ref = None
        if with_records:
            fasta = root / "candidate_sequences.fasta"
            fasta_bytes = b">source-a description\nA\n>source-b\nA\n"
            fasta_ref = _write(fasta, fasta_bytes, root)
            for candidate, seq, record_id, support in (
                ("candidate-1", "sequence-1", "source-a", "LOW_SUPPORT_ASSEMBLY"),
                ("candidate-2", "sequence-2", "source-b", "UNSUPPORTED_ASSEMBLY"),
            ):
                records.append({
                    "candidate_id": candidate,
                    "sequence_id": seq,
                    "fasta_record_id": record_id,
                    "sequence_sha256": _sha256(b"A"),
                    "sequence_length": 1,
                    "sequence_bytes_available": True,
                    "sequence_unavailable_reason": None,
                    "molecule_type": None,
                    "sequence_alphabet": "IUPAC_NUCLEOTIDE",
                    "completeness_state": "UNKNOWN",
                    "source_artifact_id": source_ref["path"],
                    "source_artifact_sha256": source_ref["sha256"],
                    "m6_support_status": support,
                    "m7_context": None,
                })
        document = {
            "schema": "m8-candidate-sequence-set-v1",
            "producer": {
                "stage_kind": "residual_evidence",
                "stage_id": "m6-test",
                "adapter_name": "minimap2-residual-evidence",
                "adapter_version": "1.1",
            },
            "source_artifact": source_ref,
            "assembly_manifest": assembly_manifest_ref,
            "m6_evidence": {
                "reconstruction_status": (
                    "NO_SUPPORTED_ASSEMBLY" if with_records else "ASSEMBLY_NOT_ATTEMPTED"
                ),
                "support_status": (
                    "NO_SUPPORTED_ASSEMBLY" if with_records else "NOT_EVALUATED"
                ),
                "artifact": {
                    "path": "reconstruction_evidence.json",
                    "sha256": _sha256(evidence_bytes),
                },
            },
            "m7_context": None,
            "availability": {
                "state": state,
                "reason": None if with_records else "ASSEMBLY_DISABLED",
                "fasta_artifact": fasta_ref,
                "record_count": len(records),
            },
            "records": records,
        }
        manifest_path = root / "candidate_sequence_set.json"
        manifest_path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        return manifest_path, document

    def test_candidate_handoff_preserves_distinct_observations_and_one_nt_sequences(self):
        with tempfile.TemporaryDirectory() as folder:
            path, document = self._candidate_set(folder)
            result = validate_candidate_sequence_set(path)
            self.assertEqual(result["availability_state"], "AVAILABLE")
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["available_sequence_count"], 2)
            self.assertNotEqual(
                document["records"][0]["candidate_id"],
                document["records"][1]["candidate_id"],
            )
            self.assertEqual(
                document["records"][0]["sequence_sha256"],
                document["records"][1]["sequence_sha256"],
            )
            self.assertEqual(
                artifact_contracts.validate_artifact(
                    path, "m8_candidate_sequence_set")["availability_state"],
                "AVAILABLE",
            )

    def test_unavailable_upstream_bytes_are_explicit_not_a_completed_empty_search(self):
        with tempfile.TemporaryDirectory() as folder:
            path, document = self._candidate_set(
                folder, state="UPSTREAM_UNAVAILABLE", with_records=False)
            self.assertEqual(
                validate_candidate_sequence_set(path)["availability_state"],
                "UPSTREAM_UNAVAILABLE",
            )
            self.assertEqual(document["availability"]["reason"], "ASSEMBLY_DISABLED")
            self.assertIsNone(document["availability"]["fasta_artifact"])
            self.assertEqual(document["records"], [])
            self.assertNotIn(
                document["availability"]["state"], SEARCH_STATUSES)

    def test_candidate_handoff_detects_bound_artifact_tampering(self):
        for artifact_path in (
            "candidate_sequences.fasta",
            "assembly/contigs.fasta",
            "reconstruction_evidence.json",
        ):
            with self.subTest(artifact=artifact_path), tempfile.TemporaryDirectory() as folder:
                path, _document = self._candidate_set(folder)
                target = Path(folder) / artifact_path
                target.write_bytes(target.read_bytes() + b"\n")
                with self.assertRaises(ValueError):
                    validate_candidate_sequence_set(path)

    def test_available_candidate_requires_a_valid_declared_alphabet(self):
        for alphabet in (None, "PROTEIN", "DNA"):
            with self.subTest(alphabet=alphabet), tempfile.TemporaryDirectory() as folder:
                path, document = self._candidate_set(folder)
                document["records"][0]["sequence_alphabet"] = alphabet
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "sequence_alphabet"):
                    validate_candidate_sequence_set(path)

    def test_assembly_manifest_is_typed_and_matches_candidate_count(self):
        with tempfile.TemporaryDirectory() as folder:
            path, document = self._candidate_set(folder)
            assembly_path = Path(folder) / document["assembly_manifest"]["path"]
            malformed = b'{"status":"complete"}'
            assembly_path.write_bytes(malformed)
            document["assembly_manifest"]["sha256"] = _sha256(malformed)
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Assembly manifest"):
                validate_candidate_sequence_set(path)

        with tempfile.TemporaryDirectory() as folder:
            path, document = self._candidate_set(folder)
            assembly_path = Path(folder) / document["assembly_manifest"]["path"]
            mismatched = json.dumps({
                "schema": "assembly-manifest-v1",
                "workflow_status": "complete",
                "contig_count": 1,
                "assembler": "synthetic",
                "external_tool_version": "test",
            }, sort_keys=True).encode()
            assembly_path.write_bytes(mismatched)
            document["assembly_manifest"]["sha256"] = _sha256(mismatched)
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validate_candidate_sequence_set(path)

    def test_m7_context_is_a_separate_typed_optional_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path, document = self._candidate_set(folder)
            row = document["records"][0]
            document["m7_context"] = {
                "links": [{
                    "candidate_id": row["candidate_id"],
                    "sequence_id": row["sequence_id"],
                    "sequence_sha256": row["sequence_sha256"],
                    "observation_id": "observation-1",
                }],
            }
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "separately as typed"):
                validate_candidate_sequence_set(path)

    def test_m8_only_package_source_change_does_not_invalidate_m6_or_m7_keys(self):
        registry = build_default_registry()
        for stage_id, kind in (
            ("m6", "residual_evidence"),
            ("m7", "independent_recurrence"),
        ):
            definition = registry.get(kind)
            stage = {"id": stage_id, "kind": kind}
            scoped_files = definition.handler.cache_implementation_identity()[
                "implementation_sha256"]
            self.assertNotIn("m8_contracts.py", scoped_files)
            self.assertNotIn("m8_blastn_profile.py", scoped_files)
            first = _stage_cache_key(
                stage, definition, {}, {}, {"source_sha256": "m8-before"}, None)
            second = _stage_cache_key(
                stage, definition, {}, {}, {"source_sha256": "m8-after"}, None)
            self.assertEqual(first, second, stage_id)


if __name__ == "__main__":
    unittest.main()