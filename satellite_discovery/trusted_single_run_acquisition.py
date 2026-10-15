"""Separately trusted, single-run HCoV-229E approval and acquisition gate.

The normal entry point is readiness-only. No local approval file, environment
variable, or CLI switch is a trust anchor; keys and replay state live outside
the installed source tree.
"""
import base64
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import sequence_downloader
from .controlled_fastq_acquisition import (
    _atomic_audit_write, _check_destination_space, _controlled_ena_opener,
    _create_acquisition_lock, _safe_output_path,
    _validate_ena_redirect_target,
)
from .public_virus_exploratory_intake import (
    MAX_BYTES, POLICY_ID, POLICY_SHA256, TARGET, evaluate_exploratory_intake,
)
from .hcov_229e_source_evidence_refresh import SourceEvidenceError, refresh_source_evidence
from .public_virus_acquisition_preflight import fastq_manifest_sha256

SCIENTIFIC_SCHEMA = "hcov-229e-scientific-approval-signatures-v1"
OPERATOR_SCHEMA = "hcov-229e-operator-authorization-v1"
TRUST_SCHEMA = "hcov-229e-trust-store-v1"
MAX_AUTHORIZATION_SECONDS = 900
CHUNK_BYTES = 1024 * 1024
EXPECTED_BYTES = 680887913
EXPECTED_MD5 = "9ac379cab68b8b5e2862ec167e95d3c9"
EXPECTED_MANIFEST = "8af1155a0ff3d65d2d32bb62560b2db37c22fb5f37c6b38a684a72747e4e9fe0"
MIN_STORAGE_BYTES = 3 * EXPECTED_BYTES + 256 * 1024 * 1024
LIMITS = {
    "max_runs": 1,
    "max_compressed_bytes": MAX_BYTES,
    "max_storage_bytes": MIN_STORAGE_BYTES,
}
PURPOSE = "single-run technical pilot"


class AuthorizationError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _load_trust_store(trust_directory):
    supplied_root = Path(trust_directory).expanduser()
    if supplied_root.is_symlink():
        raise AuthorizationError("Trust directory must not be a symbolic link.")
    try:
        root = supplied_root.resolve(strict=True)
    except OSError as exc:
        raise AuthorizationError("External trust directory is missing or unavailable.") from exc
    source_root = Path(__file__).resolve().parents[1]
    if root == source_root or source_root in root.parents:
        raise AuthorizationError("Trust configuration must be outside the repository.")
    if root.is_symlink() or not root.is_dir():
        raise AuthorizationError("Trust directory is not a regular directory.")
    path = root / "trusted_keys.json"
    if path.is_symlink() or not path.is_file():
        raise AuthorizationError("External trusted_keys.json is missing or unsafe.")
    if os.name != "nt" and (path.stat().st_mode & 0o022 or root.stat().st_mode & 0o022):
        raise AuthorizationError("Trust configuration must not be group/world writable.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != TRUST_SCHEMA or not isinstance(value.get("keys"), list):
        raise AuthorizationError("External trust store schema is invalid.")
    keys = {}
    fingerprints = set()
    for item in value["keys"]:
        if (not isinstance(item, dict)
                or not isinstance(item.get("key_id"), str)
                or item.get("role") not in {"owner", "independent_reviewer", "operator"}
                or item["key_id"] in keys):
            raise AuthorizationError("External trust store key entry is invalid.")
        try:
            raw = base64.b64decode(item["public_key"], validate=True)
            fingerprint = hashlib.sha256(raw).digest()
            if fingerprint in fingerprints:
                raise AuthorizationError("One public key cannot be assigned multiple identities or roles.")
            fingerprints.add(fingerprint)
            keys[item["key_id"]] = (item["role"], Ed25519PublicKey.from_public_bytes(raw))
        except (ValueError, TypeError, KeyError) as exc:
            raise AuthorizationError("External trust store public key is invalid.") from exc
    return root, keys


def _verify_signed_payload(bundle, schema, trust_keys, roles):
    if (not isinstance(bundle, dict) or bundle.get("schema") != schema
            or not isinstance(bundle.get("payload"), dict)
            or not isinstance(bundle.get("signatures"), list)):
        raise AuthorizationError("Signed authorization document is malformed.")
    payload = bundle["payload"]
    message = canonical_json(payload)
    accepted = {}
    for entry in bundle["signatures"]:
        try:
            key_id = entry["key_id"]
            role, key = trust_keys[key_id]
            if role not in roles or role in accepted or key_id in accepted.values():
                raise AuthorizationError("Signer is untrusted, duplicated, or assigned the wrong role.")
            signature = base64.b64decode(entry["signature"], validate=True)
            key.verify(signature, message)
            accepted[role] = key_id
        except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
            raise AuthorizationError("Authorization signature is invalid.") from exc
    if set(accepted) != set(roles):
        raise AuthorizationError("All distinct trusted signer roles are required.")
    return payload, accepted


def verify_scientific_approval(bundle, trust_keys):
    payload, signers = _verify_signed_payload(
        bundle, SCIENTIFIC_SCHEMA, trust_keys, {"owner", "independent_reviewer"},
    )
    required = {
        "scope": TARGET, "policy_identifier": POLICY_ID,
        "policy_sha256": POLICY_SHA256, "fastq_manifest_sha256": EXPECTED_MANIFEST,
        "purpose": PURPOSE, "resource_limits": LIMITS,
    }
    if any(payload.get(key) != value for key, value in required.items()):
        raise AuthorizationError("Scientific approval does not bind the exact run and limits.")
    if (not isinstance(payload.get("evidence_document_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload["evidence_document_sha256"])
            or not isinstance(payload.get("unresolved_limitations"), list)
            or not payload["unresolved_limitations"]
            or payload.get("decision_status") != "APPROVED"
            or not isinstance(payload.get("owner_identifier"), str)
            or not payload["owner_identifier"].strip()
            or not isinstance(payload.get("independent_reviewer_identifier"), str)
            or not payload["independent_reviewer_identifier"].strip()
            or payload["owner_identifier"] == payload["independent_reviewer_identifier"]):
        raise AuthorizationError("Scientific approval is missing evidence or limitations.")
    if (payload["owner_identifier"] != signers["owner"]
            or payload["independent_reviewer_identifier"] != signers["independent_reviewer"]):
        raise AuthorizationError("Signed scientific identities must match distinct trusted key IDs.")
    return payload, signers


def verify_operator_authorization(
    bundle, trust_keys, scientific_payload, *, storage_directory, now=None,
):
    payload, signers = _verify_signed_payload(
        bundle, OPERATOR_SCHEMA, trust_keys, {"operator"},
    )
    if payload.get("operator_identifier") != signers["operator"]:
        raise AuthorizationError("Operator identity must match the trusted signer key ID.")
    expected = {
        "scope": TARGET, "policy_identifier": POLICY_ID,
        "policy_sha256": POLICY_SHA256,
        "evidence_document_sha256": scientific_payload["evidence_document_sha256"],
        "fastq_manifest_sha256": EXPECTED_MANIFEST,
        "resource_limits": LIMITS, "purpose": PURPOSE,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise AuthorizationError("Operator authorization does not bind the approved acquisition.")
    try:
        storage_root = str(Path(storage_directory).expanduser().resolve(strict=True))
    except OSError as exc:
        raise AuthorizationError("Approved storage root is unavailable.") from exc
    if payload.get("storage_root") != storage_root:
        raise AuthorizationError("Operator authorization does not bind this storage root.")
    if any(not isinstance(payload.get(key), str) or not payload[key]
           for key in ("authorization_id", "nonce", "operator_identifier", "issued_at", "expires_at")):
        raise AuthorizationError("Operator authorization identity or expiry is missing.")
    if (len(payload["authorization_id"]) > 128 or len(payload["nonce"]) > 128
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", payload["authorization_id"])
            or not re.fullmatch(r"[A-Za-z0-9._:-]+", payload["nonce"])):
        raise AuthorizationError("Operator authorization id or nonce is malformed.")
    try:
        issued = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationError("Operator authorization time is malformed.") from exc
    now = now or datetime.now(timezone.utc)
    if (issued.tzinfo is None or expires.tzinfo is None
            or issued > now + timedelta(seconds=30)
            or expires <= now or expires <= issued
            or (expires - issued).total_seconds() > MAX_AUTHORIZATION_SECONDS):
        raise AuthorizationError("Operator authorization is expired or outside the short lifetime.")
    return payload, signers


def consume_authorization(database, payload, *, now=None):
    """Durably reserve a signed nonce before transfer; concurrent replays lose atomically."""
    path = Path(database)
    if (path.is_symlink() or not path.parent.is_dir()
            or path.resolve().parent != path.parent.resolve()):
        raise AuthorizationError("Replay-protection database path is unsafe.")
    if path.exists():
        mode = path.lstat().st_mode
        if not path.is_file() or (os.name != "nt" and mode & 0o022):
            raise AuthorizationError("Replay-protection database is not a protected regular file.")
    now = now or datetime.now(timezone.utc)
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        if os.name != "nt":
            os.chmod(path, 0o600)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS consumed (authorization_id TEXT PRIMARY KEY, nonce TEXT UNIQUE NOT NULL, consumed_utc TEXT NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO consumed VALUES (?, ?, ?)",
            (payload["authorization_id"], payload["nonce"], now.isoformat()),
        )
        connection.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        connection.execute("ROLLBACK")
        raise AuthorizationError("Operator authorization has already been consumed.") from exc
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _fresh_exploratory_record(evidence, approval_template, evidence_directory):
    """Refresh fixed public sources, then re-run the non-authorizing exact-scope intake."""
    try:
        fresh = refresh_source_evidence(evidence, evidence_directory)
    except SourceEvidenceError as exc:
        raise AuthorizationError(f"Fresh public metadata check failed ({exc.code}): {exc}") from exc
    document = fresh["document"]
    document["manifest"]["retained_archive_evidence"] = fresh["metadata"]["snapshot_manifest"]
    evaluation = evaluate_exploratory_intake(
        document, evidence_directory, evidence, approval_template,
    )
    if evaluation.get("result") != "candidate_for_scientific_review":
        codes = [reason.get("code", "unknown") for reason in evaluation.get("reasons", [])]
        raise AuthorizationError(
            "Fresh exact-scope evidence did not pass the non-authorizing review gate: "
            + ",".join(codes)
        )
    return document


def _transfer_one(spec, destination, opener=None):
    opener = opener or _controlled_ena_opener()
    _validate_ena_redirect_target(spec["url"])
    if (not isinstance(spec.get("name"), str)
            or not re.fullmatch(r"SRR12424250\.fastq\.gz", spec["name"])):
        raise ValueError("FASTQ filename is outside the exact-run allowlist.")
    final = destination / spec["name"]
    if final.exists() or final.is_symlink():
        raise FileExistsError("Completed FASTQ output already exists.")
    temporary = destination / ("." + spec["name"] + ".partial")
    md5, sha256, count = hashlib.md5(), hashlib.sha256(), 0
    try:
        with opener.open(spec["url"], timeout=30) as response, temporary.open("xb") as out:
            while True:
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                count += len(chunk)
                if count > spec["bytes"] or count > MAX_BYTES:
                    raise ValueError("FASTQ response exceeded the approved byte limit.")
                out.write(chunk)
                md5.update(chunk)
                sha256.update(chunk)
            out.flush()
            os.fsync(out.fileno())
        if count != spec["bytes"] or md5.hexdigest() != spec["md5"]:
            raise ValueError("FASTQ size or archive MD5 verification failed.")
        os.link(temporary, final)
        temporary.unlink()
        return {"name": spec["name"], "bytes": count, "md5": md5.hexdigest(),
                "sha256": sha256.hexdigest()}
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def acquire_exploratory_single_run(
    evidence, approval_template, approval_bundle, operator_bundle, trust_directory, replay_database,
    output_directory, storage_directory, confirmation_callback, *,
    now=None,
):
    """Execute only after trusted signatures, fresh evidence, and exact confirmation."""
    lock = None
    try:
        trust_root, keys = _load_trust_store(trust_directory)
        scientific, signers = verify_scientific_approval(approval_bundle, keys)
        if hashlib.sha256(canonical_json(evidence)).hexdigest() != scientific["evidence_document_sha256"]:
            raise AuthorizationError("Evidence document differs from the signed scientific decision.")
        if (approval_template.get("decision_status") != "NOT_APPROVED"
                or approval_template.get("scope") != scientific["scope"]
                or approval_template.get("policy_sha256") != scientific["policy_sha256"]
                or approval_template.get("evidence_document_sha256") != scientific["evidence_document_sha256"]
                or approval_template.get("fastq_manifest_sha256") != scientific["fastq_manifest_sha256"]
                or approval_template.get("unresolved_limitations") != scientific["unresolved_limitations"]):
            raise AuthorizationError("Signed scientific decisions do not bind the pending approval template.")
        operator, operator_signers = verify_operator_authorization(
            operator_bundle, keys, scientific, storage_directory=storage_directory, now=now,
        )
        operator_binding = canonical_json(operator)
        output = _safe_output_path(output_directory, storage_directory)
        fresh_evidence_dir = output.parent / (output.name + "-archive-evidence")
        fresh = _fresh_exploratory_record(
            evidence, approval_template, fresh_evidence_dir,
        )
        record = fresh["record"]
        files = sequence_downloader.files_for_run(record)
        if (len(files) != 1 or files[0]["name"] != "SRR12424250.fastq.gz"
                or files[0]["bytes"] != EXPECTED_BYTES or files[0]["md5"] != EXPECTED_MD5
                or fastq_manifest_sha256(files) != EXPECTED_MANIFEST):
            raise AuthorizationError("Fresh FASTQ manifest changed or exceeded the exact-run contract.")
        output.parent.mkdir(parents=True, exist_ok=True)
        _check_destination_space(output, EXPECTED_BYTES, LIMITS["max_storage_bytes"])
        prompt = {
            "run": TARGET["run"], "file": files[0]["name"],
            "compressed_bytes": EXPECTED_BYTES, "storage_headroom_bytes": MIN_STORAGE_BYTES,
            "policy_sha256": POLICY_SHA256, "manifest_sha256": EXPECTED_MANIFEST,
        }
        if not callable(confirmation_callback) or confirmation_callback(prompt) is not True:
            raise AuthorizationError("Explicit interactive confirmation was not accepted.")
        operator_confirmed, operator_signers_confirmed = verify_operator_authorization(
            operator_bundle, keys, scientific, storage_directory=storage_directory,
        )
        if (canonical_json(operator_confirmed) != operator_binding
                or operator_signers_confirmed != operator_signers):
            raise AuthorizationError("Operator authorization changed during confirmation.")
        replay_path = Path(replay_database).expanduser()
        expected_replay_path = (Path(trust_root) / "replay.sqlite3").resolve()
        if replay_path.resolve() != expected_replay_path:
            raise AuthorizationError("Replay database must be the protected trust-store replay.sqlite3.")
        lock = _create_acquisition_lock(output)
        if output.exists() or output.is_symlink():
            raise FileExistsError("Acquisition output already exists.")
        output.mkdir()
        audit_path = output / "acquisition.json"
        audit = {
            "schema": "trusted-single-run-acquisition-audit-v1", "status": "pre_transfer_authorization_validated",
            "scope": TARGET, "scientific_signers": signers, "operator_signers": operator_signers,
            "authorization_id": operator["authorization_id"],
            "fresh_manifest_sha256": EXPECTED_MANIFEST,
            "strict_identity_status": fresh["record"]["public_virus"]["status"],
            "fresh_archive_evidence": fresh.get("manifest", {}).get("retained_archive_evidence"),
            "eligibility": "HELD", "files": [],
        }
        _atomic_audit_write(audit_path, audit)
        # Reverify at the consumption boundary and bind replay state to this exact
        # payload; confirmation callbacks cannot substitute another signed token.
        operator_now, operator_signers_now = verify_operator_authorization(
            operator_bundle, keys, scientific, storage_directory=storage_directory,
        )
        if (canonical_json(operator_now) != operator_binding
                or operator_signers_now != operator_signers):
            raise AuthorizationError("Operator authorization changed after confirmation.")
        consume_authorization(replay_path, operator_now, now=now)
        audit.update(status="authorization_consumed")
        _atomic_audit_write(audit_path, audit)
        # A short-lived token may expire while lock, audit, or directory work runs.
        operator_last, _ = verify_operator_authorization(
            operator_bundle, keys, scientific, storage_directory=storage_directory,
        )
        if canonical_json(operator_last) != operator_binding:
            raise AuthorizationError("Operator authorization changed before transfer.")
        _check_destination_space(output, EXPECTED_BYTES, LIMITS["max_storage_bytes"])
        observed = _transfer_one(files[0], output)
        audit.update(status="complete", files=[observed])
        _atomic_audit_write(audit_path, audit)
        return {"status": "complete", "audit": str(audit_path), "file": observed}
    except Exception as exc:
        audit_path = locals().get("audit_path")
        audit = locals().get("audit")
        if audit_path is not None and isinstance(audit, dict):
            try:
                audit.update(status="failed", failure_type=type(exc).__name__)
                _atomic_audit_write(audit_path, audit)
            except OSError:
                pass
        return {"status": "blocked", "reasons": [{"code": "trusted_acquisition_blocked",
                "detail": f"{type(exc).__name__}: {exc}"}]}
    finally:
        if lock is not None:
            Path(lock).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Readiness-only by default; optionally perform one signed, interactive acquisition."
    )
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--approval-template", required=True)
    parser.add_argument("--scientific-approval")
    parser.add_argument("--operator-authorization")
    parser.add_argument("--trust-directory")
    parser.add_argument("--storage", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Requires trusted signatures, fresh metadata, and an interactive terminal.")
    args = parser.parse_args()

    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    result = {"status": "blocked", "reasons": []}
    try:
        if not args.trust_directory or not args.scientific_approval or not args.operator_authorization:
            raise AuthorizationError(
                "External trust store, two scientific signatures, and operator authorization are required."
            )
        trust_root, keys = _load_trust_store(args.trust_directory)
        evidence, template = load(args.evidence), load(args.approval_template)
        approval, _ = verify_scientific_approval(load(args.scientific_approval), keys)
        operator, _ = verify_operator_authorization(
            load(args.operator_authorization), keys, approval,
            storage_directory=args.storage,
        )
        if hashlib.sha256(canonical_json(evidence)).hexdigest() != approval["evidence_document_sha256"]:
            raise AuthorizationError("Evidence document differs from signed scientific approval.")
        if not args.execute:
            result = {
            "status": "signatures_valid_fresh_revalidation_required",
                "scope": TARGET,
                "operator": operator["operator_identifier"],
            "can_execute": False,
            "note": "Signatures are valid, but production-owned fresh treatment evidence is unavailable; no transfer was performed.",
            }
        elif not sys.stdin.isatty():
            raise AuthorizationError("Live execution requires an interactive terminal.")
        else:
            def confirm(prompt):
                print(json.dumps(prompt, indent=2))
                return (
                    input("Type SRR12424250 to confirm: ").strip() == TARGET["run"]
                    and input("Type 1000000000 to confirm the compressed-byte cap: ").strip() == str(MAX_BYTES)
                    and input(f"Type {MIN_STORAGE_BYTES} to confirm storage headroom: ").strip()
                    == str(MIN_STORAGE_BYTES)
                )
            result = acquire_exploratory_single_run(
                evidence, template, load(args.scientific_approval),
                load(args.operator_authorization), trust_root,
                trust_root / "replay.sqlite3", args.output, args.storage, confirm,
            )
    except Exception as exc:
        result = {"status": "blocked", "reasons": [{
            "code": "readiness_check_failed", "detail": f"{type(exc).__name__}: {exc}",
        }]}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {
        "signatures_valid_fresh_revalidation_required", "complete",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())

