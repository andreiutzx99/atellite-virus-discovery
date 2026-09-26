import hashlib
import json
import unittest

from satellite_discovery.m9_reference_snapshot import (
    ReferenceSnapshotIncomplete, ReferenceSnapshotInvalid, validate_snapshot,
)


class ReferenceSnapshotTests(unittest.TestCase):
    def manifest(self, payload, completeness="complete"):
        row = {"record_id": "r1", "accession_version": "x.1", "role": "technical",
               "length": 4, "sha256": hashlib.sha256(b"ACDE").hexdigest()}
        m = {"schema": "m9-protein-reference-snapshot-v1", "snapshot_id": "s1",
             "payload_sha256": hashlib.sha256(payload).hexdigest(),
             "completeness": completeness, "records": [row],
             "provenance": {"source": "fixture", "release": "1", "rights": "none",
                            "terms": "offline"}}
        m["snapshot_digest"] = hashlib.sha256(json.dumps(m, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return m

    def test_valid_and_hashes(self):
        payload = b">r1\nACDE\n"
        result = validate_snapshot(self.manifest(payload), payload)
        self.assertEqual(result["reference_map"]["r1"]["sequence"], "ACDE")

    def test_repeated_role_and_case_sensitive_hash(self):
        payload = b">r1\nACDE\n>r2\nFGHI\n"
        m = self.manifest(payload)
        m["records"].append({
            "record_id": "r2", "accession_version": "x.2",
            "role": "technical", "length": 4,
            "sha256": hashlib.sha256(b"FGHI").hexdigest(),
        })
        m.pop("snapshot_digest")
        m["snapshot_digest"] = hashlib.sha256(json.dumps(
            m, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(len(validate_snapshot(m, payload)["reference_map"]), 2)

        payload = b">r1\nacde\n>r2\nFGHI\n"
        m["payload_sha256"] = hashlib.sha256(payload).hexdigest()
        m.pop("snapshot_digest")
        m["snapshot_digest"] = hashlib.sha256(json.dumps(
            m, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.assertRaises(ReferenceSnapshotInvalid):
            validate_snapshot(m, payload)

    def test_invalid_and_incomplete_are_distinct(self):
        payload = b">r1\nACDE\n"
        bad = self.manifest(payload)
        bad["payload_sha256"] = "0" * 64
        with self.assertRaises(ReferenceSnapshotInvalid):
            validate_snapshot(bad, payload)
        with self.assertRaises(ReferenceSnapshotIncomplete):
            validate_snapshot(self.manifest(payload, "incomplete"), payload)
        incomplete = validate_snapshot(
            self.manifest(payload, "incomplete"), payload,
            require_complete=False)
        self.assertEqual(incomplete["completeness"], "incomplete")

    def test_empty_or_malformed_fasta_header_is_typed_invalid(self):
        payload = b">\nACDE\n"
        with self.assertRaises(ReferenceSnapshotInvalid):
            validate_snapshot(self.manifest(payload), payload)


if __name__ == "__main__":
    unittest.main()