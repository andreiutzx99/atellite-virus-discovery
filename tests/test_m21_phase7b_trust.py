import base64
import copy
import unittest
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    serialization = None
    Ed25519PrivateKey = None

from satellite_discovery import m21_phase7b_trust as trust

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


@unittest.skipIf(Ed25519PrivateKey is None, "cryptography required for trust-root signatures")
class TrustRootTests(unittest.TestCase):
    @staticmethod
    def _public(key):
        return base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )).decode()

    def _bundle(self, generation=1, *, wrong_anchor=False, expired=False):
        root_key = Ed25519PrivateKey.generate()
        admin_keys = [Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()]
        identity_keys = admin_keys + [Ed25519PrivateKey.generate()]
        records = []
        for index, key in enumerate(identity_keys):
            identity_id = f"ID-{index + 1:04d}"
            raw = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            record = {
                "identity_id": identity_id, "display_name": f"Fixture {index + 1}",
                "organization": "Synthetic Test Authority",
                "key_id": f"KEY-{index + 1:08d}",
                "public_key_ed25519": base64.b64encode(raw).decode(),
                "key_fingerprint_sha256": trust.sha256(raw),
                "identity_class": "SYNTHETIC",
                "roles": ["trust_admin"] if index < 2 else ["reviewer", "custodian", "trust_admin"],
                "scopes": [
                    "phase7_closure_approval", "phase7_checkpoint_retention",
                    "trust_registry_enrollment",
                ],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked": False,
                "identity_verification": {
                    "method": "synthetic authority fixture",
                    "evidence_sha256": f"{index + 1:064x}",
                    "authority": "synthetic-test-root",
                },
                "enrollment_approvals": [], "rotation": None,
            }
            records.append(record)
        if generation > 1:
            for target_index, target in enumerate(records):
                body = {key: target[key] for key in (
                    "identity_id", "key_id", "key_fingerprint_sha256", "roles",
                    "scopes", "valid_from", "valid_until", "identity_verification",
                )}
                for admin_index, key in enumerate(identity_keys):
                    if admin_index == target_index:
                        continue
                    target["enrollment_approvals"].append({
                        "identity_id": f"ID-{admin_index + 1:04d}",
                        "key_id": f"KEY-{admin_index + 1:08d}",
                        "signature_ed25519": base64.b64encode(key.sign(
                            trust.canonical_bytes(body),
                        )).decode(),
                    })
        registry = {
            "schema_version": trust.REGISTRY_SCHEMA, "registry_id": "REG-SYNTH-001",
            "generation": generation,
            "previous_checkpoint_sha256": None if generation == 1 else "a" * 64,
            "issued_at": "2026-10-20T00:00:00Z",
            "expires_at": "2026-10-25T00:00:00Z" if expired else "2027-01-01T00:00:00Z",
            "identities": records,
        }
        root_raw = root_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        anchor = {
            "schema_version": trust.ANCHOR_SCHEMA, "anchor_id": "ANCHOR-SYNTH",
            "key_id": "ROOT-00000001", "public_key_ed25519": base64.b64encode(root_raw).decode(),
            "key_fingerprint_sha256": trust.sha256(root_raw), "authority": "fixture-only",
        }
        checkpoint = {
            "schema_version": trust.CHECKPOINT_SCHEMA, "registry_id": registry["registry_id"],
            "generation": generation, "registry_sha256": trust.digest(registry),
            "previous_checkpoint_sha256": registry["previous_checkpoint_sha256"],
            "issued_at": "2026-10-20T00:00:00Z",
        }
        checkpoint["signature_ed25519"] = base64.b64encode(root_key.sign(
            trust.canonical_bytes(checkpoint),
        )).decode()
        bundle = {
            "registry": registry, "state_checkpoint": checkpoint,
            "anchor_signature": base64.b64encode(root_key.sign(
                trust.canonical_bytes(registry),
            )).decode(),
        }
        self.identity_keys = identity_keys
        fingerprint = "0" * 64 if wrong_anchor else anchor["key_fingerprint_sha256"]
        return bundle, anchor, fingerprint, trust.digest({
            key: value for key, value in checkpoint.items() if key != "signature_ed25519"
        }), root_key

    def test_independent_anchor_and_pinned_state_verify_registry(self):
        bundle, anchor, fingerprint, pin, _ = self._bundle()
        result = trust.verify_registry(
            bundle, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=pin, now=NOW,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence_class"], "PINNED_EXTERNAL_TRUST_ROOT")
        self.assertEqual(result["generation"], 1)

    def test_wrong_anchor_pin_checkpoint_rollback_expiry_and_tamper_fail(self):
        bundle, anchor, fingerprint, pin, _ = self._bundle()
        for wrong_fingerprint, wrong_pin, changed, expired in (
            ("0" * 64, pin, False, False),
            (fingerprint, "f" * 64, False, False),
            (fingerprint, pin, True, False),
            (fingerprint, pin, False, True),
        ):
            candidate = copy.deepcopy(bundle)
            if changed:
                candidate["registry"]["identities"][2]["roles"] = ["trust_admin"]
            if expired:
                candidate["registry"]["expires_at"] = "2026-10-25T00:00:00Z"
                candidate["anchor_signature"] = base64.b64encode(
                    Ed25519PrivateKey.generate().sign(b"not the registry")
                ).decode()
            result = trust.verify_registry(
                candidate, anchor, expected_anchor_fingerprint=wrong_fingerprint,
                expected_state_checkpoint_sha256=wrong_pin, now=NOW,
            )
            self.assertEqual(result["status"], "FAIL")

    def test_nonbootstrap_identity_requires_two_nonself_trust_admins(self):
        bundle, anchor, fingerprint, pin, root_key = self._bundle(generation=2)
        result = trust.verify_registry(
            bundle, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=pin,
            expected_previous_checkpoint_sha256="a" * 64, now=NOW,
        )
        self.assertEqual(result["status"], "PASS")
        target = bundle["registry"]["identities"][2]
        body = {key: target[key] for key in (
            "identity_id", "key_id", "key_fingerprint_sha256", "roles",
            "scopes", "valid_from", "valid_until", "identity_verification",
        )}
        subject_key = Ed25519PrivateKey.generate()
        # A valid signature from the identity itself must not authorize its own
        # trust-store enrollment.
        target["enrollment_approvals"] = [{
            "identity_id": target["identity_id"], "key_id": target["key_id"],
            "signature_ed25519": base64.b64encode(subject_key.sign(
                trust.canonical_bytes(body),
            )).decode(),
        }]
        bundle["state_checkpoint"]["registry_sha256"] = trust.digest(bundle["registry"])
        checkpoint_body = {
            key: value for key, value in bundle["state_checkpoint"].items()
            if key != "signature_ed25519"
        }
        bundle["state_checkpoint"]["signature_ed25519"] = base64.b64encode(
            root_key.sign(trust.canonical_bytes(checkpoint_body)),
        ).decode()
        bundle["anchor_signature"] = base64.b64encode(root_key.sign(
            trust.canonical_bytes(bundle["registry"]),
        )).decode()
        pin = trust.digest(checkpoint_body)
        result = trust.verify_registry(
            bundle, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=pin,
            expected_previous_checkpoint_sha256="a" * 64, now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")

    def test_authenticated_history_binds_rotation_and_rejects_conflicts(self):
        fixture = TrustRootTests()
        prior, anchor, fingerprint, prior_pin, root_key = fixture._bundle()
        records = copy.deepcopy(prior["registry"]["identities"])
        rotated_index = 2
        prior_key = fixture.identity_keys[rotated_index]
        rotated_key = Ed25519PrivateKey.generate()
        raw_new = rotated_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        old_raw = prior_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        target = records[rotated_index]
        old_fingerprint = target["key_fingerprint_sha256"]
        target.update({
            "key_id": "KEY-ROTATED-0001",
            "public_key_ed25519": base64.b64encode(raw_new).decode(),
            "key_fingerprint_sha256": trust.sha256(raw_new),
            "rotation": {
                "previous_key_fingerprint_sha256": old_fingerprint,
                "previous_public_key_ed25519": base64.b64encode(old_raw).decode(),
                "continuity_signature_ed25519": base64.b64encode(prior_key.sign(
                    trust.canonical_bytes({
                        "identity_id": target["identity_id"],
                        "new_key_fingerprint_sha256": trust.sha256(raw_new),
                        "previous_key_fingerprint_sha256": old_fingerprint,
                    }),
                )).decode(),
            },
        })
        all_keys = list(fixture.identity_keys)
        all_keys[rotated_index] = rotated_key
        for index, record in enumerate(records):
            enrollment = {key: record[key] for key in (
                "identity_id", "key_id", "key_fingerprint_sha256", "roles",
                "scopes", "valid_from", "valid_until", "identity_verification",
            )}
            record["enrollment_approvals"] = [{
                "identity_id": records[admin_index]["identity_id"],
                "key_id": records[admin_index]["key_id"],
                "signature_ed25519": base64.b64encode(key.sign(
                    trust.canonical_bytes(enrollment),
                )).decode(),
            } for admin_index, key in enumerate(all_keys) if admin_index != index]
        prior_checkpoint_body = {
            key: value for key, value in prior["state_checkpoint"].items()
            if key != "signature_ed25519"
        }
        registry = {
            **prior["registry"], "generation": 2,
            "previous_checkpoint_sha256": trust.digest(prior_checkpoint_body),
            "issued_at": "2026-10-21T00:00:00Z", "identities": records,
        }
        checkpoint_body = {
            "schema_version": trust.CHECKPOINT_SCHEMA,
            "registry_id": registry["registry_id"], "generation": 2,
            "registry_sha256": trust.digest(registry),
            "previous_checkpoint_sha256": registry["previous_checkpoint_sha256"],
            "issued_at": "2026-10-21T00:00:00Z",
        }
        current = {
            "registry": registry,
            "state_checkpoint": {
                **checkpoint_body,
                "signature_ed25519": base64.b64encode(
                    root_key.sign(trust.canonical_bytes(checkpoint_body)),
                ).decode(),
            },
            "anchor_signature": base64.b64encode(
                root_key.sign(trust.canonical_bytes(registry)),
            ).decode(),
        }
        state_pin = trust.digest(checkpoint_body)
        verified = trust.verify_registry(
            current, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=state_pin,
            expected_previous_checkpoint_sha256=trust.digest(prior_checkpoint_body),
            historical_registry_bundles=[prior], now=NOW,
        )
        self.assertEqual(verified["status"], "PASS", verified)
        missing_history = trust.verify_registry(
            current, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=state_pin,
            expected_previous_checkpoint_sha256=trust.digest(prior_checkpoint_body),
            now=NOW,
        )
        self.assertEqual(missing_history["status"], "INCOMPLETE")
        altered = copy.deepcopy(current)
        altered["registry"]["previous_checkpoint_sha256"] = "f" * 64
        self.assertEqual(trust.verify_registry(
            altered, anchor, expected_anchor_fingerprint=fingerprint,
            expected_state_checkpoint_sha256=state_pin,
            expected_previous_checkpoint_sha256="f" * 64,
            historical_registry_bundles=[prior], now=NOW,
        )["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
