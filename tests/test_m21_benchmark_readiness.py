import base64
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    serialization = Ed25519PrivateKey = None

from satellite_discovery import m21_benchmark_readiness as m21


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
DATASET_ID = "DS-SYNTH00001"
SAMPLE_ID = "BLD-0123456789ABCDEF01234567"
REVIEWER_ID = "REV-TEST0001"


@unittest.skipUnless(Ed25519PrivateKey is not None, "cryptography is unavailable")
class M21BenchmarkReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        self.analysis.mkdir()
        self.operator = self.root / "operator"
        self.operator.mkdir()
        self.reference_root = self.root / "reference-bytes"
        self.reference_root.mkdir()
        self.reference_bytes = b">synthetic-reference\nACGTACGT\n"
        (self.reference_root / "panel.fa").write_bytes(self.reference_bytes)
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.trust = {REVIEWER_ID: base64.b64encode(public).decode("ascii")}
        self.r1 = b"@read-a/1\nACGT\n+\nIIII\n@read-b/1\nTGCA\n+\nHHHH\n"
        self.r2 = b"@read-a/2\nTGCA\n+\nIIII\n@read-b/2\nACGT\n+\nHHHH\n"
        (self.analysis / "r1.fastq").write_bytes(self.r1)
        (self.analysis / "r2.fastq").write_bytes(self.r2)

    def tearDown(self):
        self.temp.cleanup()

    def approval(self, gate, status="APPROVED", expires="2027-01-01T00:00:00Z", manifest_digest=None):
        record = {
            "status": status,
            "approval_id": "APR-TEST00000001",
            "reviewer_id": REVIEWER_ID,
            "approved_at": "2026-10-01T00:00:00Z",
            "expires_at": expires,
            "evidence_sha256": hashlib.sha256((gate + "-evidence").encode()).hexdigest(),
            "manifest_sha256": manifest_digest or "0" * 64,
        }
        record["signature_ed25519"] = base64.b64encode(
            self.private.sign(m21._approval_payload(DATASET_ID, SAMPLE_ID, gate, record))
        ).decode("ascii")
        return record

    def reference_panel(self):
        panel = {
            "schema_version": m21.REFERENCE_SCHEMA_VERSION,
            "snapshot_id": "REF-SYNTH00001",
            "references": [{"source": "synthetic", "accession_version": "SYNTH.1",
                            "path": "panel.fa", "bytes": len(self.reference_bytes),
                            "sha256": hashlib.sha256(self.reference_bytes).hexdigest()}],
            "target_exclusion_policy_id": "POL-SYNTH00001",
        }
        digest = m21._reference_panel_binding_digest(panel)
        approval = self.approval("reference_panel", manifest_digest=digest)
        approval["signature_ed25519"] = base64.b64encode(
            self.private.sign(m21._approval_payload(
                "REF-SYNTH00001", "REF-SYNTH00001", "reference_panel", approval
            ))
        ).decode("ascii")
        panel["approval"] = approval
        return panel

    def manifest(self):
        document = {
            "schema_version": m21.SCHEMA_VERSION,
            "dataset_id": DATASET_ID,
            "sample_id": SAMPLE_ID,
            "provenance": {
                "source_catalog": "synthetic-fixture",
                "custodian_record_ref": "SRC-SYNTH00001",
                "accession_refs": ["ACCREF-SYNTH00001"],
            },
            "reference_panel_sha256": m21._reference_panel_binding_digest(self.reference_panel()),
            "read_input": {
                "layout": "PAIRED",
                "format": "FASTQ",
                "files": [
                    {"role": "R1", "path": "r1.fastq", "bytes": len(self.r1),
                     "sha256": hashlib.sha256(self.r1).hexdigest(), "integrity_status": "VERIFIED"},
                    {"role": "R2", "path": "r2.fastq", "bytes": len(self.r2),
                     "sha256": hashlib.sha256(self.r2).hexdigest(), "integrity_status": "VERIFIED"},
                ],
            },
            "ground_truth_review": {
                "assayed_region_evidence": "REVIEWED",
                "full_length_reconstruction": "NOT_ASSESSED",
                "negative_control_assessment": "NOT_CLAIMED",
            },
        }
        digest = m21._manifest_binding_digest(document)
        document["gates"] = {gate: self.approval(gate, manifest_digest=digest) for gate in m21.GATES}
        return document

    def validate(self, document, **kwargs):
        return m21.validate_manifest(
            document, self.analysis, self.trust, NOW, scan_root=self.operator,
            reference_manifest=self.reference_panel(), reference_root=self.reference_root, **kwargs
        )

    def test_valid_signed_synthetic_manifest_can_reach_ready_state(self):
        result = self.validate(self.manifest())
        self.assertEqual(result["decision"], "READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK")
        self.assertEqual(result["issues"], [])

    def test_manifest_content_tampering_invalidates_every_gate_signature(self):
        document = self.manifest()
        document["provenance"]["source_catalog"] = "changed-synthetic-source"
        result = self.validate(document)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertTrue(any("not bound to the current manifest" in issue for issue in result["issues"]))

    def test_missing_crypto_and_missing_disclosure_scan_fail_closed(self):
        document = self.manifest()
        with patch.object(m21, "Ed25519PublicKey", None):
            result = self.validate(document)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertTrue(any("cryptography dependency unavailable" in issue for issue in result["issues"]))
        result = m21.validate_manifest(
            self.manifest(), self.analysis, self.trust, NOW,
            reference_manifest=self.reference_panel(), reference_root=self.reference_root,
        )
        self.assertTrue(any("disclosure scan root" in issue for issue in result["issues"]))

    def test_default_missing_gate_and_pending_approval_block(self):
        doc = self.manifest()
        del doc["gates"]["data_use"]
        result = self.validate(doc)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertTrue(any("mandatory approval gates" in item for item in result["issues"]))
        doc = self.manifest()
        doc["gates"]["data_use"] = {"status": "PENDING"}
        self.assertEqual(self.validate(doc)["decision"], "BLOCKED")

    def test_expired_or_untrusted_approval_blocks(self):
        doc = self.manifest()
        doc["gates"]["data_use"] = self.approval("data_use", expires="2026-10-19T00:00:00Z")
        result = self.validate(doc)
        self.assertTrue(any("expired" in item for item in result["issues"]))
        doc["gates"]["data_use"] = self.approval("data_use")
        result = m21.validate_manifest(doc, self.analysis, {}, NOW, scan_root=self.operator,
                                       reference_manifest=self.reference_panel(), reference_root=self.reference_root)
        self.assertTrue(any("external trust store" in item for item in result["issues"]))

    def test_metadata_only_and_bad_checksum_never_count_as_byte_verified(self):
        doc = self.manifest()
        doc["read_input"]["files"][0]["integrity_status"] = "METADATA_ONLY"
        self.assertEqual(self.validate(doc)["decision"], "BLOCKED")
        doc = self.manifest()
        doc["read_input"]["files"][0]["sha256"] = "0" * 64
        self.assertTrue(any("checksum mismatch" in x for x in self.validate(doc)["issues"]))

    def test_unapproved_negative_control_assessment_stays_blocked(self):
        doc = self.manifest()
        doc["ground_truth_review"]["negative_control_assessment"] = "REVIEWED"
        doc["gates"]["negative_control_review"] = {"status": "PENDING"}
        result = self.validate(doc)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertTrue(any("negative_control_review" in issue for issue in result["issues"]))

    def test_negative_control_not_applicable_still_requires_signed_evidence(self):
        doc = self.manifest()
        doc["gates"]["negative_control_review"] = {"status": "NOT_APPLICABLE"}
        result = self.validate(doc)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertTrue(any("approval_id" in issue for issue in result["issues"]))

    def test_accession_leakage_in_manifest_is_blocked(self):
        doc = self.manifest()
        doc["provenance"]["source_catalog"] = "SRA SRR123456"
        self.assertTrue(any("accession-like" in issue for issue in self.validate(doc)["issues"]))

    def test_format_mismatch_and_malformed_manifest_types_fail_closed(self):
        doc = self.manifest()
        doc["read_input"]["files"][0]["path"] = "r1.fq.gz"
        result = self.validate(doc)
        self.assertTrue(any("extension does not match" in issue for issue in result["issues"]))
        doc = self.manifest()
        doc["read_input"]["layout"] = []
        result = self.validate(doc)
        self.assertEqual(result["decision"], "BLOCKED")

    def test_malformed_identifiers_and_duplicate_opaque_ids(self):
        self.assertTrue(m21.validate_opaque_ids(["not-opaque"]))
        self.assertTrue(m21.validate_opaque_ids([SAMPLE_ID, SAMPLE_ID]))
        doc = self.manifest()
        doc["sample_id"] = "Px15"
        self.assertTrue(any("opaque sample" in x for x in self.validate(doc)["issues"]))

    def test_paired_fastq_stats_and_pair_mismatch(self):
        result = m21.validate_fastq(self.analysis / "r1.fastq", self.analysis / "r2.fastq")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["statistics"]["read_pairs"], 2)
        self.assertTrue(result["statistics"]["phred33_histogram"])
        bad = self.analysis / "bad.fastq"
        bad.write_bytes(b"@other/2\nACGT\n+\nIIII\n")
        result = m21.validate_fastq(self.analysis / "r1.fastq", bad)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("inconsistent" in x for x in result["issues"]))

    def test_malformed_duplicate_and_truncated_fastq(self):
        malformed = self.analysis / "malformed.fastq"
        malformed.write_text("@r\nACGT\n+\nIII\n", encoding="ascii")
        self.assertEqual(m21.validate_fastq(malformed)["status"], "FAIL")
        duplicate = self.analysis / "duplicate.fastq"
        duplicate.write_text("@x\nAC\n+\nII\n@x\nTG\n+\nII\n", encoding="ascii")
        self.assertTrue(any("Duplicate" in x for x in m21.validate_fastq(duplicate)["issues"]))
        truncated = self.analysis / "truncated.fastq"
        truncated.write_text("@x\nAC\n+\n", encoding="ascii")
        self.assertTrue(any("Truncated" in x for x in m21.validate_fastq(truncated)["issues"]))

    def test_gzip_fastq_and_configurable_thresholds(self):
        path = self.analysis / "reads.fastq.gz"
        with gzip.open(path, "wt", encoding="ascii") as handle:
            handle.write("@one\nACGT\n+\nIIII\n")
        self.assertEqual(m21.validate_fastq(path)["status"], "PASS")
        result = m21.validate_fastq(path, thresholds={"min_reads": 2})
        self.assertEqual(result["status"], "FAIL")

    def test_reference_panel_requires_provenance_and_signed_independent_approval(self):
        panel = self.reference_panel()
        self.assertEqual(m21.validate_reference_panel(panel, self.trust, NOW, self.reference_root), [])
        (self.reference_root / "panel.fa").write_bytes(b">altered\nTTTT\n")
        self.assertTrue(any("integrity mismatch" in issue for issue in
                            m21.validate_reference_panel(panel, self.trust, NOW, self.reference_root)))
        panel["approval"] = {"status": "PENDING"}
        self.assertTrue(m21.validate_reference_panel(panel, self.trust, NOW, self.reference_root))

    def test_disclosure_scan_rejects_identifiers_labels_private_keys(self):
        root = self.root / "operator"
        root.mkdir(exist_ok=True)
        (root / "settings.json").write_text(
            json.dumps({"truth_label": "positive", "private_key": "-----BEGIN PRIVATE KEY-----"}),
            encoding="utf-8",
        )
        (root / "SRR123456.fastq").write_text("fixture", encoding="ascii")
        found = m21.scan_operator_artifacts(root, ["positive"])
        self.assertTrue(any("Private-key" in x for x in found))
        self.assertTrue(any("accession-like" in x for x in found))
        self.assertTrue(any("truth/identity" in x for x in found))
        self.assertTrue(any("disclosure token" in x for x in found))

    def test_truth_key_is_private_and_rejected_inside_analysis_tree(self):
        outside = self.root / "custodian"
        outside.mkdir()
        target = outside / "sealed-key.json"
        m21.write_sealed_truth_key({"synthetic-case": SAMPLE_ID}, target, self.analysis)
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            m21.write_sealed_truth_key({"synthetic-case": SAMPLE_ID}, target, self.analysis)
        with self.assertRaises(ValueError):
            m21.write_sealed_truth_key({"synthetic-case": SAMPLE_ID}, self.analysis / "leak.json", self.analysis)

    def test_readiness_command_has_no_network_or_stage_side_effects(self):
        manifest_path = self.analysis / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest()), encoding="utf-8")
        (self.analysis / "reference.json").write_text(json.dumps(self.reference_panel()), encoding="utf-8")
        trust_path = self.analysis / "trust.json"
        trust_path.write_text(json.dumps(self.trust), encoding="utf-8")
        with patch("socket.create_connection", side_effect=AssertionError("network attempted")) as network:
            with patch("subprocess.Popen", side_effect=AssertionError("stage launched")) as process:
                code = m21.main([
                    "validate", "--manifest", str(manifest_path), "--analysis-root", str(self.analysis),
                "--trust-store", str(trust_path), "--scan-root", str(self.operator),
                "--reference-manifest", str(self.analysis / "reference.json"),
                "--reference-root", str(self.reference_root),
                ])
        self.assertEqual(code, 0)
        network.assert_not_called()
        process.assert_not_called()

    def test_readiness_command_returns_nonzero_when_blocked(self):
        doc = self.manifest()
        doc["gates"]["execution_authorization"] = {"status": "PENDING"}
        path = self.analysis / "blocked.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        trust = self.analysis / "trust.json"
        trust.write_text(json.dumps(self.trust), encoding="utf-8")
        (self.analysis / "reference.json").write_text(json.dumps(self.reference_panel()), encoding="utf-8")
        with patch("sys.stdout"):
            code = m21.main([
                "validate", "--manifest", str(path), "--analysis-root", str(self.analysis),
                "--trust-store", str(trust), "--scan-root", str(self.operator),
                "--reference-manifest", str(self.analysis / "reference.json"),
                "--reference-root", str(self.reference_root),
            ])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
