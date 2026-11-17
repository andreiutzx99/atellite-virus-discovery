"""Restricted evidence custody and externally anchored M36 approval checks."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .m36_preparation import CASE_ID, RunnerBlocked, SHA256, TERMINAL_STATUSES


TRUST_ANCHOR_PATH = Path("/etc/m36-phase2b/approval_signer_ed25519.pem")
AUTHORIZATION_SCHEMA = "m36-scoped-authorization-v1"
MAX_AUTHORIZATION_BYTES = 64 * 1024


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def strict_json_loads(content: bytes) -> Any:
    def no_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"non-finite JSON value is forbidden: {value}")

    return json.loads(
        content.decode("utf-8"),
        object_pairs_hook=no_duplicate_keys,
        parse_constant=reject_constant,
    )


def _secure_regular_file(path: Path, *, owner_uid: int) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise RunnerBlocked(f"required restricted file is unavailable: {path.name}") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != owner_uid
        or info.st_mode & 0o077
    ):
        raise RunnerBlocked("restricted file ownership or permissions are invalid")
    return info


def _load_external_public_key() -> Ed25519PublicKey:
    """Load the host-administered trust anchor; never accept a caller-supplied key."""
    if os.name != "posix" or not TRUST_ANCHOR_PATH.is_absolute():
        raise RunnerBlocked("host-provisioned authorization trust anchor is required")
    parent = TRUST_ANCHOR_PATH.parent
    while parent != Path("/"):
        try:
            info = parent.lstat()
        except OSError as error:
            raise RunnerBlocked("host authorization trust directory is unavailable") from error
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
        ):
            raise RunnerBlocked("host authorization trust directory is not root-controlled")
        parent = parent.parent
    _secure_regular_file(TRUST_ANCHOR_PATH, owner_uid=0)
    try:
        key = serialization.load_pem_public_key(TRUST_ANCHOR_PATH.read_bytes())
    except (OSError, TypeError, ValueError) as error:
        raise RunnerBlocked("authorization trust anchor cannot be read") from error
    if not isinstance(key, Ed25519PublicKey):
        raise RunnerBlocked("authorization trust anchor must be Ed25519")
    return key


def verify_scoped_authorization(
    authorization: dict,
    *,
    expected_payload: dict,
) -> None:
    """Verify a canonical Ed25519-signed envelope against the host trust anchor."""
    if not isinstance(authorization, dict) or set(authorization) != {
        "schema", "payload", "signature_ed25519",
    }:
        raise RunnerBlocked("authorization envelope is malformed")
    if authorization.get("schema") != AUTHORIZATION_SCHEMA:
        raise RunnerBlocked("authorization schema is unsupported")
    payload = authorization.get("payload")
    if not isinstance(payload, dict) or payload != expected_payload:
        raise RunnerBlocked("authorization is not bound to the exact run scope and budget")
    encoded = authorization.get("signature_ed25519")
    if not isinstance(encoded, str) or len(encoded) > MAX_AUTHORIZATION_BYTES:
        raise RunnerBlocked("authorization signature is missing or oversized")
    try:
        signature = base64.b64decode(encoded, validate=True)
        if len(signature) != 64:
            raise ValueError("Ed25519 signatures must be 64 bytes")
        _load_external_public_key().verify(signature, canonical_json_bytes(payload))
    except (ValueError, InvalidSignature) as error:
        raise RunnerBlocked("authorization signature is invalid") from error


class RestrictedEvidenceStore:
    """Durable owner-only directory store, provided by the execution host."""

    def __init__(
        self,
        root: str | Path,
        *,
        source_root: str | Path,
        public_root: str | Path,
    ) -> None:
        if os.name != "posix" or not hasattr(os, "geteuid"):
            raise RunnerBlocked(
                "owner-only restricted storage requires a verifiable POSIX owner and mode"
            )
        raw = Path(root)
        if not raw.is_absolute() or raw.is_symlink():
            raise RunnerBlocked("restricted evidence root must be an absolute non-symlink path")
        self.root = raw.resolve(strict=True)
        self.source_root = Path(source_root).resolve(strict=True)
        self.public_root = Path(public_root).resolve(strict=True)
        for candidate in (self.source_root, self.public_root):
            if (
                self.root == candidate
                or self.root.is_relative_to(candidate)
                or candidate.is_relative_to(self.root)
            ):
                raise RunnerBlocked("restricted evidence store overlaps source or public outputs")
        if not self.root.is_dir():
            raise RunnerBlocked("restricted evidence root is not a directory")
        self._assert_private_directory(self.root)

    @staticmethod
    def _assert_private_directory(path: Path) -> None:
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise RunnerBlocked("restricted evidence directory must be owner-only")

    def _target(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if (
            not relative_path
            or relative.is_absolute()
            or any(part in ("", ".", "..") for part in relative.parts)
            or "\\" in relative_path
        ):
            raise RunnerBlocked("restricted evidence path is unsafe")
        target = self.root / relative
        if not target.resolve().is_relative_to(self.root):
            raise RunnerBlocked("restricted evidence path escaped its store")
        return target

    def write_bytes(self, relative_path: str, content: bytes) -> str:
        """Create one immutable file, fsync it and its parent, then verify its bytes."""
        if not isinstance(content, bytes):
            raise TypeError("restricted evidence must be bytes")
        target = self._target(relative_path)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        current = target.parent
        while current != self.root:
            self._assert_private_directory(current)
            current = current.parent
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        temporary = target.with_name(
            f".{target.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, target, follow_symlinks=False)
            temporary.unlink()
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            stored = target.read_bytes()
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
        if stored != content or target.stat().st_mode & 0o077:
            raise RunnerBlocked("restricted evidence failed byte or permission verification")
        return hashlib.sha256(stored).hexdigest()

    def write_manifest(
        self, relative_path: str, content: bytes, *, expected_sha256: str,
    ) -> dict:
        if not SHA256.fullmatch(expected_sha256):
            raise RunnerBlocked("restricted manifest digest is malformed")
        observed = hashlib.sha256(content).hexdigest()
        if observed != expected_sha256:
            raise RunnerBlocked("restricted manifest bytes do not match the frozen digest")
        return {
            "path": relative_path,
            "sha256": self.write_bytes(relative_path, content),
        }

    def load_manifest(self, path: str | Path) -> tuple[dict, str]:
        """Read the evaluator manifest only from this private store."""
        manifest_path = Path(path)
        if manifest_path.is_symlink():
            raise RunnerBlocked("restricted manifest cannot be a symlink")
        manifest_path = manifest_path.resolve(strict=True)
        if not manifest_path.is_relative_to(self.root):
            raise RunnerBlocked("evaluator manifest is outside restricted storage")
        parent = manifest_path.parent
        while parent != self.root:
            self._assert_private_directory(parent)
            parent = parent.parent
        info = _secure_regular_file(manifest_path, owner_uid=os.geteuid())
        if info.st_size > 10 * 1024 * 1024:
            raise RunnerBlocked("evaluator manifest exceeds the size limit")
        content = manifest_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        try:
            manifest = strict_json_loads(content)
        except (
            UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError,
        ) as error:
            raise RunnerBlocked("restricted evaluator manifest is malformed") from error
        if not isinstance(manifest, dict):
            raise RunnerBlocked("restricted evaluator manifest must be an object")
        return manifest, digest

    def write_terminal_record(self, assignment_id: str, record: dict) -> str:
        if not CASE_ID.fullmatch(assignment_id):
            raise RunnerBlocked("opaque assignment identifier is malformed")
        if (
            not isinstance(record, dict)
            or record.get("status") not in TERMINAL_STATUSES
        ):
            raise RunnerBlocked("terminal record must contain exactly one status")
        return self.write_bytes(
            f"attempts/{assignment_id}/terminal.json",
            canonical_json_bytes(record) + b"\n",
        )

    def inventory_directory(self, relative_dir: str) -> dict[str, str]:
        directory = self._target(relative_dir)
        if directory.is_symlink() or not directory.is_dir():
            raise RunnerBlocked("restricted attempt evidence directory is missing")
        self._assert_private_directory(directory)
        result = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise RunnerBlocked("restricted evidence contains a symlink")
            if path.is_dir():
                self._assert_private_directory(path)
                continue
            info = _secure_regular_file(path, owner_uid=os.geteuid())
            if info.st_mode & 0o077:
                raise RunnerBlocked("restricted evidence file is not owner-only")
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        return result
