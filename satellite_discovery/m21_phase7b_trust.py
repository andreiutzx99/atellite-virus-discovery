"""Independently pinned Phase 7B trust-root and identity-registry verification."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:
    InvalidSignature = Exception
    Ed25519PublicKey = None

from . import m21_benchmark_readiness as readiness

ANCHOR_SCHEMA = "m21-phase7b-trust-anchor-v1"
REGISTRY_SCHEMA = "m21-phase7b-trust-registry-v1"
CHECKPOINT_SCHEMA = "m21-phase7b-trust-state-checkpoint-v1"
REGISTRY_FIELDS = {
    "schema_version", "registry_id", "generation", "previous_checkpoint_sha256",
    "issued_at", "expires_at", "identities",
}
IDENTITY_FIELDS = {
    "identity_id", "display_name", "organization", "key_id", "public_key_ed25519",
    "key_fingerprint_sha256", "identity_class", "roles", "scopes", "valid_from", "valid_until",
    "revoked", "identity_verification", "enrollment_approvals", "rotation",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value))


def _decode(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("expected base64 string")
    return base64.b64decode(value, validate=True)


def _parse_time(value: Any) -> datetime | None:
    return readiness._parse_time(value)


def _verify_signature(public_key: bytes, signature: Any, message: bytes) -> bool:
    if Ed25519PublicKey is None:
        return False
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(_decode(signature), message)
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def verify_registry(
    bundle: Any, anchor: Any, *, expected_anchor_fingerprint: str,
    expected_state_checkpoint_sha256: str,
    expected_previous_checkpoint_sha256: str | None = None,
    historical_registry_bundles: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Authenticate a registry against an out-of-band pinned trust anchor and state digest.

    This verifies the cryptographic chain only. The operator must provision the
    anchor and current checkpoint digest independently of the evidence package.
    """
    now = now or datetime.now(timezone.utc)
    if Ed25519PublicKey is None:
        return {"status": "INCOMPLETE", "issues": ["cryptography is unavailable."]}
    if not isinstance(anchor, dict) or set(anchor) != {
        "schema_version", "anchor_id", "key_id", "public_key_ed25519",
        "key_fingerprint_sha256", "authority",
    }:
        return {"status": "FAIL", "issues": ["Trust anchor is malformed."]}
    try:
        anchor_key = _decode(anchor["public_key_ed25519"])
    except (KeyError, ValueError):
        return {"status": "FAIL", "issues": ["Trust anchor public key is malformed."]}
    fingerprint = sha256(anchor_key)
    if (anchor["schema_version"] != ANCHOR_SCHEMA or len(anchor_key) != 32
            or anchor["key_fingerprint_sha256"] != fingerprint
            or fingerprint != expected_anchor_fingerprint
            or not anchor["anchor_id"] or not anchor["key_id"]
            or not anchor["authority"]):
        return {"status": "FAIL", "issues": ["Trust anchor does not match the independently pinned fingerprint."]}
    if not isinstance(bundle, dict) or set(bundle) != {
        "registry", "state_checkpoint", "anchor_signature",
    }:
        return {"status": "FAIL", "issues": ["Trust registry bundle is malformed."]}
    registry = bundle["registry"]
    checkpoint = bundle["state_checkpoint"]
    if not isinstance(registry, dict) or set(registry) != REGISTRY_FIELDS:
        return {"status": "FAIL", "issues": ["Trust registry fields are malformed."]}
    if not isinstance(checkpoint, dict) or set(checkpoint) != {
        "schema_version", "registry_id", "generation", "registry_sha256",
        "previous_checkpoint_sha256", "issued_at", "signature_ed25519",
    }:
        return {"status": "FAIL", "issues": ["Trust-state checkpoint is malformed."]}
    body = {key: value for key, value in checkpoint.items() if key != "signature_ed25519"}
    checkpoint_digest = digest(body)
    registry_time = _parse_time(registry.get("issued_at"))
    registry_expiry = _parse_time(registry.get("expires_at"))
    checkpoint_time = _parse_time(checkpoint.get("issued_at"))
    if (registry["schema_version"] != REGISTRY_SCHEMA
            or checkpoint["schema_version"] != CHECKPOINT_SCHEMA
            or not isinstance(registry["generation"], int) or registry["generation"] < 1
            or isinstance(registry["generation"], bool)
            or checkpoint["generation"] != registry["generation"]
            or checkpoint["registry_id"] != registry["registry_id"]
            or checkpoint["registry_sha256"] != digest(registry)
            or checkpoint["previous_checkpoint_sha256"] != registry["previous_checkpoint_sha256"]
            or checkpoint_digest != expected_state_checkpoint_sha256
            or not registry_time or not registry_expiry or registry_expiry <= now
            or registry_time > now or not checkpoint_time or checkpoint_time > now):
        return {"status": "FAIL", "issues": ["Trust registry is expired, rolled back, or not bound to its pinned checkpoint."]}
    if registry["generation"] == 1:
        if registry["previous_checkpoint_sha256"] is not None or expected_previous_checkpoint_sha256 is not None:
            return {"status": "FAIL", "issues": ["Initial trust registry has an unexpected predecessor."]}
    elif expected_previous_checkpoint_sha256 is None:
        return {"status": "INCOMPLETE", "issues": ["Previous trust-state checkpoint pin is required to verify continuity."]}
    elif registry["previous_checkpoint_sha256"] != expected_previous_checkpoint_sha256:
        return {"status": "FAIL", "issues": ["Trust registry does not continue the independently pinned prior state."]}
    if not _verify_signature(anchor_key, bundle["anchor_signature"], canonical_bytes(registry)):
        return {"status": "FAIL", "issues": ["Trust registry signature verification failed."]}
    if not _verify_signature(anchor_key, checkpoint["signature_ed25519"], canonical_bytes(body)):
        return {"status": "FAIL", "issues": ["Trust-state checkpoint signature verification failed."]}
    identities = registry.get("identities")
    if not isinstance(identities, list) or not identities:
        return {"status": "FAIL", "issues": ["Trust registry has no identities."]}
    records: dict[str, dict[str, Any]] = {}
    key_ids: set[str] = set()
    key_fingerprints: set[str] = set()
    issues: list[str] = []
    for record in identities:
        if not isinstance(record, dict) or set(record) != IDENTITY_FIELDS:
            issues.append("Trust identity record is malformed.")
            continue
        identity_id = record.get("identity_id")
        if (not isinstance(identity_id, str) or not identity_id
                or identity_id in records or not isinstance(record.get("revoked"), bool)
                or not isinstance(record.get("roles"), list) or not record["roles"]
                or any(role not in {"reviewer", "custodian", "trust_admin"} for role in record["roles"])
                or record.get("identity_class") not in {"HUMAN", "SYNTHETIC"}
                or not isinstance(record.get("scopes"), list) or not record["scopes"]
                or not all(isinstance(scope, str) and scope for scope in record["scopes"])
                or not isinstance(record.get("display_name"), str) or not record["display_name"]
                or not isinstance(record.get("organization"), str) or not record["organization"]
                or not isinstance(record.get("key_id"), str) or not record["key_id"]):
            issues.append("Trust identity is duplicated, revoked, or has no authorised role/scope.")
            continue
        try:
            public_key = _decode(record["public_key_ed25519"])
        except (ValueError, TypeError):
            issues.append("Trust identity public key is malformed.")
            continue
        key_fingerprint = sha256(public_key)
        if (len(public_key) != 32 or key_fingerprint != record["key_fingerprint_sha256"]
                or record["key_id"] in key_ids
                or key_fingerprint in key_fingerprints):
            issues.append("Trust identity key is invalid, conflicting, or duplicated.")
            continue
        key_ids.add(record["key_id"])
        start, end = _parse_time(record.get("valid_from")), _parse_time(record.get("valid_until"))
        verification = record.get("identity_verification")
        if (not start or not end or start >= end or start > now or end <= now
                or not isinstance(verification, dict)
                or set(verification) != {"method", "evidence_sha256", "authority"}
                or not verification.get("method") or not verification.get("authority")
                or not re.fullmatch(r"[a-f0-9]{64}", str(verification.get("evidence_sha256", "")))):
            issues.append("Identity verification evidence or validity window is missing or expired.")
            continue
        records[identity_id] = record
        key_fingerprints.add(key_fingerprint)
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    bootstrap = registry["generation"] == 1 and registry["previous_checkpoint_sha256"] is None
    rotation_present = False
    for record in records.values():
        approvals = record["enrollment_approvals"]
        admins = [
            approval for approval in approvals if isinstance(approval, dict)
        ] if isinstance(approvals, list) else []
        authorized: set[str] = set()
        enrollment = {key: record[key] for key in (
            "identity_id", "key_id", "key_fingerprint_sha256", "roles", "scopes",
            "valid_from", "valid_until", "identity_verification",
        )}
        for approval in admins:
            admin = records.get(approval.get("identity_id"))
            if (not admin or "trust_admin" not in admin["roles"]
                    or "trust_registry_enrollment" not in admin["scopes"]
                    or admin.get("revoked") is not False
                    or admin["identity_id"] == record["identity_id"]
                    or approval.get("key_id") != admin["key_id"]
                    or not _verify_signature(
                        _decode(admin["public_key_ed25519"]),
                        approval.get("signature_ed25519"), canonical_bytes(enrollment),
                    )):
                continue
            authorized.add(admin["identity_id"])
        if len(authorized) < 2 and not bootstrap:
            return {"status": "FAIL", "issues": ["Identity enrolment lacks two distinct authorised trust-admin approvals."]}
        rotation = record.get("rotation")
        if rotation is not None:
            rotation_present = True
            if not isinstance(rotation, dict) or set(rotation) != {
                "previous_key_fingerprint_sha256", "previous_public_key_ed25519",
                "continuity_signature_ed25519",
            }:
                return {"status": "FAIL", "issues": ["Key rotation record is malformed."]}
            try:
                previous_key = _decode(rotation["previous_public_key_ed25519"])
            except (ValueError, TypeError):
                return {"status": "FAIL", "issues": ["Previous rotation key is malformed."]}
            if sha256(previous_key) != rotation["previous_key_fingerprint_sha256"]:
                return {"status": "FAIL", "issues": ["Previous rotation key fingerprint is inconsistent."]}
            if rotation["previous_key_fingerprint_sha256"] == record["key_fingerprint_sha256"]:
                return {"status": "FAIL", "issues": ["Key rotation must replace the prior public key."]}
            if not _verify_signature(
                previous_key,
                rotation["continuity_signature_ed25519"],
                canonical_bytes({
                    "identity_id": record["identity_id"],
                    "new_key_fingerprint_sha256": record["key_fingerprint_sha256"],
                    "previous_key_fingerprint_sha256": rotation["previous_key_fingerprint_sha256"],
                }),
            ):
                return {"status": "FAIL", "issues": ["Key rotation continuity signature is invalid."]}
    previous_registry: dict[str, dict[str, Any]] | None = None
    if rotation_present or registry["generation"] > 1 and historical_registry_bundles is not None:
        if not isinstance(historical_registry_bundles, list):
            return {
                "status": "INCOMPLETE",
                "issues": ["Authenticated prior-registry history is required to verify key rotation."],
            }
        if len(historical_registry_bundles) != registry["generation"] - 1:
            return {"status": "FAIL", "issues": ["Trust-registry history is incomplete or contains extra generations."]}
        prior_checkpoint_sha: str | None = None
        prior_identity_registry: dict[str, dict[str, Any]] | None = None
        for index, prior_bundle in enumerate(historical_registry_bundles, start=1):
            prior_registry = prior_bundle.get("registry") if isinstance(prior_bundle, dict) else None
            prior_checkpoint = prior_bundle.get("state_checkpoint") if isinstance(prior_bundle, dict) else None
            if (not isinstance(prior_registry, dict) or prior_registry.get("generation") != index
                    or not isinstance(prior_checkpoint, dict)):
                return {"status": "FAIL", "issues": ["Trust-registry history is reordered or malformed."]}
            prior_body = {key: value for key, value in prior_checkpoint.items()
                          if key != "signature_ed25519"}
            prior_state_sha = digest(prior_body)
            verified_prior = verify_registry(
                prior_bundle, anchor,
                expected_anchor_fingerprint=expected_anchor_fingerprint,
                expected_state_checkpoint_sha256=prior_state_sha,
                expected_previous_checkpoint_sha256=prior_checkpoint_sha,
                historical_registry_bundles=historical_registry_bundles[:index - 1],
                now=now,
            )
            if verified_prior.get("status") != "PASS":
                return {
                    "status": verified_prior.get("status", "FAIL"),
                    "issues": ["A retained prior registry failed authentication.",
                               *verified_prior.get("issues", [])],
                }
            prior_checkpoint_sha = verified_prior["state_checkpoint_sha256"]
            prior_identity_registry = verified_prior["identity_registry"]
        if prior_checkpoint_sha != registry["previous_checkpoint_sha256"]:
            return {"status": "FAIL", "issues": ["Current registry conflicts with retained history or rolls back state."]}
        previous_registry = prior_identity_registry
        if previous_registry is not None:
            for identity_id, record in records.items():
                prior = previous_registry.get(identity_id)
                if prior is None:
                    continue
                prior_fp = prior["key_fingerprint_sha256"]
                current_fp = record["key_fingerprint_sha256"]
                rotation = record.get("rotation")
                if current_fp != prior_fp and rotation is None:
                    return {"status": "FAIL", "issues": ["Reviewer key changed without an authenticated rotation record."]}
                if rotation is not None and (
                    prior.get("revoked") is not False
                    or rotation["previous_key_fingerprint_sha256"] != prior_fp
                    or rotation["previous_public_key_ed25519"] != prior["public_key_ed25519"]
                ):
                    return {"status": "FAIL", "issues": ["Rotation does not continue the prior authenticated reviewer key."]}
                if prior.get("revoked") is True and current_fp == prior_fp and record.get("revoked") is False:
                    return {"status": "FAIL", "issues": ["A revoked reviewer key was reactivated."]}
            for identity_id, prior in previous_registry.items():
                if (identity_id not in records and prior.get("revoked") is not True):
                    return {"status": "FAIL", "issues": ["An active identity disappeared without an authenticated revocation."]}
    return {
        "status": "PASS", "identity_registry": records,
        "registry_sha256": digest(registry), "state_checkpoint_sha256": checkpoint_digest,
        "anchor_fingerprint_sha256": fingerprint, "anchor_id": anchor["anchor_id"],
        "generation": registry["generation"], "verified_at": now.isoformat(),
        "evidence_class": "PINNED_EXTERNAL_TRUST_ROOT",
    }
