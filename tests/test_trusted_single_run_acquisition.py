import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from io import BytesIO

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from satellite_discovery.public_virus_acquisition_preflight import fastq_manifest_sha256
from satellite_discovery import trusted_single_run_acquisition as gate


class TrustedAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trusted-hcov-test-")
        self.root = Path(self.temp.name)
        self.trust = self.root / "trust"
        self.trust.mkdir(mode=0o700)
        self.keys = {
            role: Ed25519PrivateKey.generate()
            for role in ("owner", "independent_reviewer", "operator")
        }
        self.key_ids = {
            "owner": "owner-test-key",
            "independent_reviewer": "reviewer-test-key",
            "operator": "operator-test-key",
        }
        public = []
        self.trust_keys = {}
        for role, private in self.keys.items():
            key_id = self.key_ids[role]
            raw = private.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            public.append({
                "key_id": key_id, "role": role,
                "public_key": base64.b64encode(raw).decode("ascii"),
            })
            self.trust_keys[key_id] = (role, private.public_key())
        config = self.trust / "trusted_keys.json"
        config.write_text(json.dumps({"schema": gate.TRUST_SCHEMA, "keys": public}), encoding="utf-8")
        if hasattr(config, "chmod"):
            config.chmod(0o600)
        self.now = datetime.now(timezone.utc)
        self.evidence = {"example": "signed evidence"}
        self.evidence_digest = hashlib.sha256(gate.canonical_json(self.evidence)).hexdigest()
        self.limits = dict(gate.LIMITS)
        self.manifest = gate.EXPECTED_MANIFEST
        self.scientific_payload = {
            "scope": gate.TARGET,
            "policy_identifier": gate.POLICY_ID,
            "policy_sha256": gate.POLICY_SHA256,
            "evidence_document_sha256": self.evidence_digest,
            "fastq_manifest_sha256": self.manifest,
            "purpose": gate.PURPOSE,
            "resource_limits": self.limits,
            "unresolved_limitations": ["No reads have been reviewed."],
            "decision_status": "APPROVED",
            "owner_identifier": self.key_ids["owner"],
            "independent_reviewer_identifier": self.key_ids["independent_reviewer"],
        }
        self.scientific = self.sign(
            gate.SCIENTIFIC_SCHEMA, self.scientific_payload,
            ("owner", "independent_reviewer"),
        )
        self.operator_payload = self.make_operator_payload()
        self.operator = self.sign(gate.OPERATOR_SCHEMA, self.operator_payload, ("operator",))

    def tearDown(self):
        self.temp.cleanup()

    def sign(self, schema, payload, roles):
        body = gate.canonical_json(payload)
        return {
            "schema": schema, "payload": payload,
            "signatures": [
                {"key_id": self.key_ids[role],
                 "signature": base64.b64encode(self.keys[role].sign(body)).decode("ascii")}
                for role in roles
            ],
        }

    def make_operator_payload(self):
        return {
            "scope": gate.TARGET, "policy_identifier": gate.POLICY_ID,
            "policy_sha256": gate.POLICY_SHA256,
            "evidence_document_sha256": self.evidence_digest,
            "fastq_manifest_sha256": self.manifest,
            "resource_limits": self.limits, "purpose": gate.PURPOSE,
            "authorization_id": "auth-test-001", "nonce": "nonce-test-001",
            "operator_identifier": self.key_ids["operator"],
            "storage_root": str(self.root.resolve()),
            "issued_at": (self.now - timedelta(seconds=10)).isoformat(),
            "expires_at": (self.now + timedelta(minutes=10)).isoformat(),
        }

    def test_independent_ed25519_roles_bind_the_exact_scientific_payload(self):
        payload, signers = gate.verify_scientific_approval(self.scientific, self.trust_keys)
        self.assertEqual(payload, self.scientific_payload)
        self.assertNotEqual(signers["owner"], signers["independent_reviewer"])
        forged = json.loads(json.dumps(self.scientific))
        forged["payload"]["scope"]["run"] = "SRR00000000"
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_scientific_approval(forged, self.trust_keys)

    def test_missing_role_invalid_signature_and_same_role_fail_closed(self):
        missing = self.sign(gate.SCIENTIFIC_SCHEMA, self.scientific_payload, ("owner",))
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_scientific_approval(missing, self.trust_keys)
        same_role = self.sign(gate.SCIENTIFIC_SCHEMA, self.scientific_payload, ("owner", "owner"))
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_scientific_approval(same_role, self.trust_keys)
        bad = json.loads(json.dumps(self.scientific))
        bad["signatures"][0]["signature"] = base64.b64encode(b"x" * 64).decode("ascii")
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_scientific_approval(bad, self.trust_keys)

    def test_scope_policy_evidence_manifest_limits_and_signer_identity_are_bound(self):
        mutations = [
            ("scope", "run", "SRR00000000"),
            ("policy_sha256", None, "0" * 64),
            ("evidence_document_sha256", None, "x" * 64),
            ("fastq_manifest_sha256", None, "0" * 64),
            ("purpose", None, "general sequencing"),
            ("resource_limits", None, {"max_runs": 2}),
            ("owner_identifier", None, "forged-owner"),
            ("independent_reviewer_identifier", None, "owner-test-key"),
        ]
        for field, nested, value in mutations:
            with self.subTest(field=field):
                payload = json.loads(json.dumps(self.scientific_payload))
                if nested:
                    payload[field][nested] = value
                else:
                    payload[field] = value
                signed = self.sign(gate.SCIENTIFIC_SCHEMA, payload, ("owner", "independent_reviewer"))
                with self.assertRaises(gate.AuthorizationError):
                    gate.verify_scientific_approval(signed, self.trust_keys)

    def test_missing_trust_store_and_duplicate_public_key_roles_block(self):
        with self.assertRaises(gate.AuthorizationError):
            gate._load_trust_store(self.root / "missing")
        duplicate = Ed25519PrivateKey.generate()
        raw = duplicate.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        config = {
            "schema": gate.TRUST_SCHEMA,
            "keys": [
                {"key_id": "owner", "role": "owner", "public_key": base64.b64encode(raw).decode()},
                {"key_id": "reviewer", "role": "independent_reviewer", "public_key": base64.b64encode(raw).decode()},
            ],
        }
        path = self.trust / "trusted_keys.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(gate.AuthorizationError):
            gate._load_trust_store(self.trust)

    def test_operator_expiry_scope_and_resource_binding(self):
        payload, _ = gate.verify_scientific_approval(self.scientific, self.trust_keys)
        result, _ = gate.verify_operator_authorization(
            self.operator, self.trust_keys, payload, storage_directory=self.root, now=self.now,
        )
        self.assertEqual(result["authorization_id"], "auth-test-001")
        expired = dict(self.operator_payload, expires_at=(self.now - timedelta(seconds=1)).isoformat())
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_operator_authorization(
                self.sign(gate.OPERATOR_SCHEMA, expired, ("operator",)),
                self.trust_keys, payload, storage_directory=self.root, now=self.now,
            )
        wrong_root = dict(self.operator_payload, storage_root=str((self.root / "elsewhere")))
        with self.assertRaises(gate.AuthorizationError):
            gate.verify_operator_authorization(
                self.sign(gate.OPERATOR_SCHEMA, wrong_root, ("operator",)),
                self.trust_keys, payload, storage_directory=self.root, now=self.now,
            )

    def test_replay_store_consumes_nonce_atomically_and_rejects_reuse(self):
        database = self.trust / "replay.sqlite3"
        gate.consume_authorization(database, self.operator_payload, now=self.now)
        with self.assertRaises(gate.AuthorizationError):
            gate.consume_authorization(database, self.operator_payload, now=self.now)

    def test_concurrent_replay_has_one_winner(self):
        import threading
        barrier = threading.Barrier(2)
        results = []
        def consume():
            barrier.wait()
            try:
                gate.consume_authorization(self.trust / "race.sqlite3", self.operator_payload, now=self.now)
                results.append("consumed")
            except gate.AuthorizationError:
                results.append("replay")
        workers = [threading.Thread(target=consume) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
        self.assertCountEqual(results, ["consumed", "replay"])

    def test_transfer_accepts_only_bounded_verified_synthetic_bytes(self):
        body = b"synthetic FASTQ bytes only"
        spec = {
            "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/SRR12424250/SRR12424250.fastq.gz",
            "name": "SRR12424250.fastq.gz", "bytes": len(body),
            "md5": hashlib.md5(body).hexdigest(),
        }
        class Opener:
            def open(self, url, timeout):
                return BytesIO(body)
        out = self.root / "out"
        out.mkdir()
        observed = gate._transfer_one(spec, out, opener=Opener())
        self.assertEqual(observed["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual((out / spec["name"]).read_bytes(), body)
        bad_url = dict(spec, url="http://attacker.invalid/file")
        with self.assertRaises(ValueError):
            gate._transfer_one(bad_url, out, opener=Opener())

    def test_transfer_rejects_short_oversized_corrupt_and_colliding_outputs(self):
        body = b"synthetic FASTQ"
        class Opener:
            def __init__(self, response):
                self.response = response
            def open(self, url, timeout):
                return BytesIO(self.response)
        spec = {
            "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/SRR12424250/SRR12424250.fastq.gz",
            "name": "SRR12424250.fastq.gz", "bytes": len(body),
            "md5": hashlib.md5(body).hexdigest(),
        }
        out = self.root / "transfer"
        out.mkdir()
        with self.assertRaises(ValueError):
            gate._transfer_one(dict(spec, bytes=len(body) + 1), out, opener=Opener(body))
        with self.assertRaises(ValueError):
            gate._transfer_one(dict(spec, bytes=len(body) - 1), out, opener=Opener(body))
        with self.assertRaises(ValueError):
            gate._transfer_one(dict(spec, md5="0" * 32), out, opener=Opener(body))
        gate._transfer_one(spec, out, opener=Opener(body))
        with self.assertRaises(FileExistsError):
            gate._transfer_one(spec, out, opener=Opener(body))

    def test_live_revalidation_blocks_without_fresh_geo_evidence_provider(self):
        with self.assertRaisesRegex(gate.AuthorizationError, "Fresh GEO"):
            gate._fresh_exploratory_record(
                self.evidence, {}, self.root / "archive-evidence",
                retriever=lambda *args, **kwargs: self.fail("retrieval must not start"),
            )

    def test_full_synthetic_orchestration_consumes_auth_and_writes_audit(self):
        body = b"synthetic FASTQ"
        spec = {
            "url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/SRR12424250/SRR12424250.fastq.gz",
            "name": "SRR12424250.fastq.gz", "bytes": len(body),
            "md5": hashlib.md5(body).hexdigest(), "role": "single",
        }
        manifest = fastq_manifest_sha256([spec])
        scientific_payload = dict(self.scientific_payload, fastq_manifest_sha256=manifest)
        scientific = self.sign(
            gate.SCIENTIFIC_SCHEMA, scientific_payload,
            ("owner", "independent_reviewer"),
        )
        operator_payload = dict(
            self.operator_payload, fastq_manifest_sha256=manifest,
            evidence_document_sha256=self.evidence_digest,
            authorization_id="auth-e2e", nonce="nonce-e2e",
        )
        operator = self.sign(gate.OPERATOR_SCHEMA, operator_payload, ("operator",))
        template = {
            "decision_status": "NOT_APPROVED", "scope": gate.TARGET,
            "policy_sha256": gate.POLICY_SHA256,
            "evidence_document_sha256": self.evidence_digest,
            "fastq_manifest_sha256": manifest,
            "unresolved_limitations": scientific_payload["unresolved_limitations"],
        }
        record = {"public_virus": {"status": "insufficient"}}
        class Opener:
            def open(self, url, timeout):
                return BytesIO(body)
        output = self.root / "approved" / "reads"
        storage = self.root
        min_storage = 3 * len(body) + 256 * 1024 * 1024
        limits = {"max_runs": 1, "max_compressed_bytes": len(body),
                  "max_storage_bytes": min_storage}
        with (
            patch.object(gate, "EXPECTED_BYTES", len(body)),
            patch.object(gate, "EXPECTED_MD5", spec["md5"]),
            patch.object(gate, "EXPECTED_MANIFEST", manifest),
            patch.object(gate, "MIN_STORAGE_BYTES", min_storage),
            patch.object(gate, "LIMITS", limits),
            patch.object(gate, "_fresh_exploratory_record", return_value={"record": record}),
            patch.object(gate, "_controlled_ena_opener", return_value=Opener()),
            patch.object(gate.sequence_downloader, "files_for_run", return_value=[spec]),
        ):
            # Bind signatures to the patched resource policy used by this synthetic transfer.
            scientific_payload["resource_limits"] = limits
            scientific = self.sign(gate.SCIENTIFIC_SCHEMA, scientific_payload,
                                   ("owner", "independent_reviewer"))
            operator_payload["resource_limits"] = limits
            operator = self.sign(gate.OPERATOR_SCHEMA, operator_payload, ("operator",))
            result = gate.acquire_exploratory_single_run(
                self.evidence, template, scientific, operator, self.trust,
                self.trust / "replay.sqlite3", output, storage, lambda prompt: True,
                now=self.now,
            )
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual((output / spec["name"]).read_bytes(), body)
        audit = json.loads((output / "acquisition.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["strict_identity_status"], "insufficient")
        self.assertEqual(audit["eligibility"], "HELD")
        self.assertEqual(audit["files"][0]["sha256"], hashlib.sha256(body).hexdigest())


if __name__ == "__main__":
    unittest.main()
