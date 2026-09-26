import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from satellite_discovery.m9_contracts import (
    validate_bundle, validate_orf_results, validate_protein_fasta,
    validate_protein_match_evidence, validate_protein_search_status,
    validate_protein_summary, validate_raw_output, validate_reference_manifest,
    validate_search_commands,
)


def digest(value):
    return hashlib.sha256(value).hexdigest()


class M9ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_fasta_and_raw_output_allow_empty(self):
        fasta = self.root / "empty.fa"
        fasta.write_bytes(b"")
        self.assertEqual(validate_protein_fasta(fasta)["record_count"], 0)
        raw = self.root / "raw.tsv"
        raw.write_bytes(b"")
        self.assertEqual(validate_raw_output(raw)["size_bytes"], 0)

    def test_reference_manifest_canonical_digest(self):
        row = {
            "record_id": "r1", "accession_version": "x.1", "role": "technical",
            "length": 4, "sha256": "1" * 64,
        }
        value = {
            "schema": "m9-protein-reference-snapshot-v1", "snapshot_id": "s1",
            "payload_sha256": "0" * 64, "completeness": "complete", "records": [row],
            "provenance": {"source": "x", "release": "r", "rights": "y", "terms": "z"},
        }
        value["snapshot_digest"] = digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(validate_reference_manifest(self.put("m.json", value))["record_count"], 1)
        value["snapshot_digest"] = "f" * 64
        with self.assertRaises(ValueError):
            validate_reference_manifest(self.put("bad.json", value))
        value["snapshot_digest"] = digest(json.dumps(
            {k: x for k, x in value.items() if k != "snapshot_digest"},
            sort_keys=True, separators=(",", ":"),
        ).encode())
        value["records"] = []
        value["snapshot_digest"] = digest(json.dumps(
            {k: x for k, x in value.items() if k != "snapshot_digest"},
            sort_keys=True, separators=(",", ":"),
        ).encode())
        with self.assertRaises(ValueError):
            validate_reference_manifest(self.put("empty-complete.json", value))

    def test_status_requires_canonical_branch_status(self):
        value = {
            "schema": "m9-protein-search-status-v1", "aggregate_status": "COMPLETE",
            "reference_snapshot_state": "VALID", "candidate_count": 0,
            "expected_orf_query_count": 0, "observed_query_count": 0,
            "query_accounting": {"expected_query_ids": [], "observed_query_ids": [], "missing_query_ids": []},
            "queries": [], "candidate_statuses": [],
        }
        self.assertEqual(validate_protein_search_status(self.put("s.json", value))["query_count"], 0)
        value["candidate_statuses"] = [{"status": "NOPE"}]
        with self.assertRaises(ValueError):
            validate_protein_search_status(self.put("bad.json", value))

    def test_bundle_checks_local_hash(self):
        output = self.root / "out.fa"
        output.write_bytes(b">q\nM\n")
        value = {"schema": "m9-output-bundle-v1", "bundle_kind": "ORF_DERIVATION",
                 "source_inputs": {}, "outputs": {"out.fa": {
                     "artifact_type": "protein_fasta", "sha256": digest(output.read_bytes()),
                     "size_bytes": output.stat().st_size}}}
        self.assertEqual(validate_bundle(self.put("b.json", value))["output_count"], 1)
        output.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            validate_bundle(self.root / "b.json")

    def test_summary_and_commands_schema(self):
        for name, schema in (("summary", "m9-protein-summary-v1"), ("commands", "m9-search-commands-v1")):
            value = {"schema": schema, "aggregate_status": "PARTIAL",
                     "source_inputs": {}, "snapshot": {}, "tool": {}, "profile": {},
                     "settings": {}, "accounting": {}, "raw_output_provenance": {}}
            self.assertEqual((validate_protein_summary if name == "summary" else validate_search_commands)(
                self.put(name + ".json", value))["schema"], schema)

    def test_orf_results_rejects_bad_protein_hash(self):
        value = {"schema": "m9-orf-results-v1", "aggregate_status": "COMPLETE",
                 "candidate_set": {"sha256": "0" * 64}, "candidate_count": 1,
                 "candidates": [{
                     "candidate_id": "c", "sequence_id": "s", "sequence_bytes_available": True,
                     "sequence_sha256": "1" * 64, "sequence_length": 3, "m6_support_status": "x",
                     "completeness_state": "x", "molecule_type": "DNA", "fasta_record_id": "c",
                     "m6_evidence": {}, "orf_status": "ORF_PREDICTED", "expected_orf_count": 1,
                     "observed_orf_count": 1, "orfs": [{
                         "candidate_id": "c", "sequence_id": "s", "source_sequence_sha256": "1" * 64,
                         "source_sequence_length": 3, "orf_id": "o", "strand": "+", "frame": 0,
                         "original_span": [0, 3], "partial": False, "partial_5_prime": False,
                         "partial_3_prime": False, "translation_table": 1, "derivation_policy": "p",
                         "protein_sequence": "M", "protein_sha256": "0" * 64, "protein_length": 1,
                         "ambiguous_codon_positions": []}],
                 }]}
        with self.assertRaises(ValueError):
            validate_orf_results(self.put("o.json", value))


if __name__ == "__main__":
    unittest.main()