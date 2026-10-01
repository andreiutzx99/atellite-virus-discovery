"""Verify versioned references from external artifacts to M1 workflow runs.

This module verifies integrity and ownership links only. It does not establish
who created a bundle, whether an artifact is scientifically correct, or what a
missing/failed producer state means biologically.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat

from .artifact_contracts import SCHEMA as ARTIFACT_CONTRACT_SCHEMA
from .workflow_states import STAGE_STATES, WORKFLOW_STATES


PRODUCER_EXECUTION_REF_SCHEMA = "producer-execution-ref-v1"
PRODUCER_ARTIFACT_BINDING_SCHEMA = "verified-producer-artifact-binding-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ARTIFACT_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_WORKFLOW_REF_FIELDS = frozenset({"path", "sha256", "workflow_id"})
_EXECUTION_REF_FIELDS = frozenset({
    "schema",
    "producer_workflow_ref",
    "producer_stage_id",
    "producer_stage_kind",
    "producer_stage_manifest_sha256",
})
_METADATA_LIMIT = 8 * 1024 * 1024
_HASH_CHUNK_SIZE = 1024 * 1024


class ProducerProvenanceError(ValueError):
    """Base error with a stable state and reason code for consumer handling."""

    state = "INVALID"

    def __init__(self, message, *, code, producer_status=None):
        super().__init__(message)
        self.code = code
        self.producer_status = producer_status


class ProducerProvenanceUnavailableError(ProducerProvenanceError):
    """The explicit reference or artifact is missing or unreadable."""

    state = "UNAVAILABLE"


class ProducerProvenanceIncompleteError(ProducerProvenanceError):
    """The selected producer stage did not complete."""

    state = "INCOMPLETE"


class ProducerProvenanceInvalidError(ProducerProvenanceError):
    """The supplied reference or its integrity chain is invalid."""

    state = "INVALID"


@dataclass(frozen=True)
class VerifiedProducerArtifact:
    """Integrity-verified producer identity and artifact metadata.

    ``binding_sha256`` excludes filesystem paths, so moving an intact bundle
    does not change its provenance/cache identity.
    """

    workflow_id: str
    workflow_sha256: str
    workflow_status_raw: str
    stage_id: str
    stage_kind: str
    stage_status_raw: str
    stage_manifest_sha256: str
    artifact_relative_path: str
    artifact_type: str
    contract_version: str
    artifact_sha256: str
    binding_sha256: str


def _invalid(message, code, *, producer_status=None):
    raise ProducerProvenanceInvalidError(
        message, code=code, producer_status=producer_status
    )


def _unavailable(message, code):
    raise ProducerProvenanceUnavailableError(message, code=code)


def _incomplete(message, code, status):
    raise ProducerProvenanceIncompleteError(
        message, code=code, producer_status=status
    )


def _require_hash(value, label):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _invalid(f"{label} must be a lowercase SHA-256 digest", "REFERENCE_INVALID")
    return value


def _safe_relative_parts(value, label):
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
    ):
        _invalid(f"{label} must be a normalized relative path", "ARTIFACT_PATH_UNSAFE")
    path = PurePosixPath(value)
    if (
        str(path) != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _invalid(f"{label} must be a normalized relative path", "ARTIFACT_PATH_UNSAFE")
    return path.parts


def _checked_path(root, relative_path, label):
    parts = _safe_relative_parts(relative_path, label)
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            _unavailable(f"{label} is missing", "REFERENCED_FILE_UNAVAILABLE")
        except OSError as error:
            _unavailable(f"{label} is unreadable", "REFERENCED_FILE_UNAVAILABLE")
        if stat.S_ISLNK(info.st_mode):
            _invalid(f"{label} must not traverse symbolic links", "ARTIFACT_PATH_UNSAFE")
        final = index == len(parts) - 1
        if final and not stat.S_ISREG(info.st_mode):
            _invalid(f"{label} must be a regular file", "ARTIFACT_PATH_UNSAFE")
        if not final and not stat.S_ISDIR(info.st_mode):
            _invalid(f"{label} parent must be a regular directory", "ARTIFACT_PATH_UNSAFE")
    return current


def _read_json_file(path, label):
    try:
        size = path.stat().st_size
        if size > _METADATA_LIMIT:
            _invalid(f"{label} exceeds the metadata size limit", "WORKFLOW_INVALID")
        raw = path.read_bytes()
    except ProducerProvenanceError:
        raise
    except OSError as error:
        _unavailable(f"{label} is unreadable", "REFERENCED_FILE_UNAVAILABLE")
    if len(raw) > _METADATA_LIMIT:
        _invalid(f"{label} exceeds the metadata size limit", "WORKFLOW_INVALID")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        _invalid(f"{label} is not valid UTF-8 JSON", "WORKFLOW_INVALID")
    if not isinstance(value, dict):
        _invalid(f"{label} must contain a JSON object", "WORKFLOW_INVALID")
    return raw, value


def _sha256_file(path, label):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(_HASH_CHUNK_SIZE)
                if not block:
                    break
                digest.update(block)
    except OSError:
        _unavailable(f"{label} is unreadable", "REFERENCED_FILE_UNAVAILABLE")
    return digest.hexdigest()


def _canonical_sha256(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_reference(reference):
    if not isinstance(reference, dict) or set(reference) != _EXECUTION_REF_FIELDS:
        _invalid("Producer execution reference has an invalid shape", "REFERENCE_INVALID")
    if reference.get("schema") != PRODUCER_EXECUTION_REF_SCHEMA:
        _invalid("Unsupported producer execution reference schema", "REFERENCE_INVALID")

    workflow_ref = reference.get("producer_workflow_ref")
    if (
        not isinstance(workflow_ref, dict)
        or set(workflow_ref) != _WORKFLOW_REF_FIELDS
    ):
        _invalid("Producer workflow reference has an invalid shape", "REFERENCE_INVALID")
    workflow_path = workflow_ref.get("path")
    _safe_relative_parts(workflow_path, "producer_workflow_ref.path")
    if PurePosixPath(workflow_path).name != "workflow.json":
        _invalid("Producer workflow reference must name workflow.json", "REFERENCE_INVALID")
    workflow_sha256 = _require_hash(
        workflow_ref.get("sha256"), "producer_workflow_ref.sha256"
    )
    workflow_id = workflow_ref.get("workflow_id")
    if not isinstance(workflow_id, str) or not workflow_id or len(workflow_id) > 256:
        _invalid("Producer workflow ID is invalid", "REFERENCE_INVALID")

    stage_id = reference.get("producer_stage_id")
    stage_kind = reference.get("producer_stage_kind")
    if not isinstance(stage_id, str) or not _TOKEN.fullmatch(stage_id):
        _invalid("Producer stage ID is invalid", "REFERENCE_INVALID")
    if not isinstance(stage_kind, str) or not _TOKEN.fullmatch(stage_kind):
        _invalid("Producer stage kind is invalid", "REFERENCE_INVALID")
    stage_manifest_sha256 = _require_hash(
        reference.get("producer_stage_manifest_sha256"),
        "producer_stage_manifest_sha256",
    )
    return (
        workflow_ref,
        workflow_sha256,
        workflow_id,
        stage_id,
        stage_kind,
        stage_manifest_sha256,
    )


def verify_producer_artifact(
    bundle_root,
    producer_execution_ref,
    artifact_path,
    *,
    artifact_relative_path,
    artifact_type,
    contract_version,
    expected_sha256,
):
    """Verify a supplied artifact against an explicit M1 workflow snapshot.

    The reference schema is intentionally independent of M5 execution
    outcomes. ``workflow.json`` and all referenced paths must be present under
    the caller-selected ``bundle_root``. The workflow file's raw SHA-256 is the
    run-snapshot identity because M1 does not expose a separate immutable run
    ID. The selected stage must be complete and the artifact bytes must match
    both M1 inventories, the typed descriptor, and the consumer's supplied
    copy.

    The returned binding hash includes exact workflow/stage-manifest/artifact
    digests and typed identities, but excludes paths so relocation is stable.
    """

    (
        workflow_ref,
        workflow_sha256,
        workflow_id,
        stage_id,
        stage_kind,
        stage_manifest_sha256,
    ) = _validate_reference(producer_execution_ref)

    if not isinstance(artifact_relative_path, str):
        _invalid("Artifact output path is invalid", "REFERENCE_INVALID")
    artifact_parts = _safe_relative_parts(
        artifact_relative_path, "artifact_relative_path"
    )
    if not isinstance(artifact_type, str) or not _ARTIFACT_TYPE.fullmatch(artifact_type):
        _invalid("Artifact type is invalid", "REFERENCE_INVALID")
    if not isinstance(contract_version, str) or not _VERSION.fullmatch(contract_version):
        _invalid("Artifact contract version is invalid", "REFERENCE_INVALID")
    expected_sha256 = _require_hash(expected_sha256, "expected_sha256")

    try:
        root = Path(bundle_root).resolve(strict=True)
        root_info = root.stat()
    except (OSError, TypeError, ValueError):
        _unavailable("Bundle root is unavailable", "REFERENCED_FILE_UNAVAILABLE")
    if not stat.S_ISDIR(root_info.st_mode):
        _invalid("Bundle root must be a directory", "ARTIFACT_PATH_UNSAFE")

    workflow_path = _checked_path(
        root, workflow_ref["path"], "producer workflow manifest"
    )
    if workflow_path.stat().st_size > _METADATA_LIMIT:
        _invalid("Producer workflow manifest exceeds the size limit", "WORKFLOW_INVALID")
    workflow_raw, workflow = _read_json_file(
        workflow_path, "producer workflow manifest"
    )
    actual_workflow_sha256 = hashlib.sha256(workflow_raw).hexdigest()
    if actual_workflow_sha256 != workflow_sha256:
        _invalid("Producer workflow manifest digest does not match", "WORKFLOW_DIGEST_MISMATCH")
    if workflow.get("schema") != "artifact-workflow-manifest-v2":
        _invalid("Unsupported producer workflow schema", "WORKFLOW_INVALID")
    if workflow.get("workflow_id") != workflow_id:
        _invalid("Producer workflow ID does not match", "PRODUCER_IDENTITY_MISMATCH")
    workflow_status = workflow.get("status")
    if not isinstance(workflow_status, str) or workflow_status not in WORKFLOW_STATES:
        _invalid("Producer workflow status is unknown", "WORKFLOW_INVALID")

    stages = workflow.get("stages")
    if not isinstance(stages, list):
        _invalid("Producer workflow stages must be a list", "WORKFLOW_INVALID")
    if any(not isinstance(row, dict) for row in stages):
        _invalid("Producer workflow stage rows must be objects", "WORKFLOW_INVALID")
    matching_stages = [
        row for row in stages
        if row.get("id") == stage_id
    ]
    if len(matching_stages) != 1:
        _invalid("Producer stage is missing or ambiguous", "PRODUCER_STAGE_NOT_FOUND")
    stage = matching_stages[0]
    if stage.get("kind") != stage_kind:
        _invalid("Producer stage kind does not match", "PRODUCER_IDENTITY_MISMATCH")
    stage_status = stage.get("status")
    if not isinstance(stage_status, str) or stage_status not in STAGE_STATES:
        _invalid("Producer stage status is unknown", "WORKFLOW_INVALID")
    if stage_status != "complete":
        _incomplete(
            f"Producer stage did not complete: {stage_status}",
            "PRODUCER_STAGE_INCOMPLETE",
            stage_status,
        )

    output_path = stage.get("output_path")
    output_parts = _safe_relative_parts(output_path, "producer stage output_path")
    stage_output_relative = PurePosixPath(*output_parts)
    stage_manifest_relative = stage_output_relative / "manifest.json"
    stage_manifest_path = _checked_path(
        workflow_path.parent,
        stage_manifest_relative.as_posix(),
        "producer stage manifest",
    )
    stage_manifest_raw, stage_manifest = _read_json_file(
        stage_manifest_path, "producer stage manifest"
    )
    actual_stage_manifest_sha256 = hashlib.sha256(stage_manifest_raw).hexdigest()
    if (
        actual_stage_manifest_sha256 != stage_manifest_sha256
        or stage.get("stage_manifest_sha256") != stage_manifest_sha256
    ):
        _invalid(
            "Producer stage manifest is not bound to the workflow row",
            "STAGE_MANIFEST_DIGEST_MISMATCH",
        )
    if stage_manifest.get("status") != stage_status:
        _invalid(
            "Producer stage and stage manifest statuses conflict",
            "STAGE_MANIFEST_INVALID",
        )
    if (
        "stage_manifest_identity" in stage
        and stage.get("stage_manifest_identity") != stage_manifest.get("identity")
    ):
        _invalid(
            "Producer stage manifest identity does not match the workflow row",
            "STAGE_MANIFEST_INVALID",
        )

    output_sha256 = stage_manifest.get("output_sha256")
    if not isinstance(output_sha256, dict):
        _invalid("Producer stage has no checksummed output inventory", "STAGE_MANIFEST_INVALID")
    if artifact_relative_path not in output_sha256:
        _unavailable(
            "Artifact is not listed in the producer stage inventory",
            "ARTIFACT_UNAVAILABLE",
        )
    inventory_sha256 = _require_hash(
        output_sha256[artifact_relative_path], "stage manifest artifact digest"
    )
    if inventory_sha256 != expected_sha256:
        _invalid(
            "Artifact digest does not match the producer stage inventory",
            "ARTIFACT_DIGEST_MISMATCH",
        )

    output_files = stage.get("output_files")
    if not isinstance(output_files, dict) or artifact_relative_path not in output_files:
        _invalid("Workflow row is missing its artifact inventory", "ARTIFACT_DESCRIPTOR_INVALID")
    output_record = output_files[artifact_relative_path]
    if (
        not isinstance(output_record, dict)
        or output_record.get("sha256") != expected_sha256
        or isinstance(output_record.get("size_bytes"), bool)
        or not isinstance(output_record.get("size_bytes"), int)
        or output_record.get("size_bytes") < 0
    ):
        _invalid("Workflow artifact inventory is invalid", "ARTIFACT_DESCRIPTOR_INVALID")

    artifacts = stage.get("artifacts")
    if not isinstance(artifacts, dict) or artifact_relative_path not in artifacts:
        _invalid("Workflow row has no typed artifact descriptor", "ARTIFACT_DESCRIPTOR_INVALID")
    descriptor = artifacts[artifact_relative_path]
    expected_producer_path = (
        stage_output_relative / PurePosixPath(*artifact_parts)
    ).as_posix()
    if (
        not isinstance(descriptor, dict)
        or descriptor.get("schema") != ARTIFACT_CONTRACT_SCHEMA
        or descriptor.get("artifact_type") != artifact_type
        or descriptor.get("contract_version") != contract_version
        or descriptor.get("producer_stage") != stage_id
        or descriptor.get("path") != expected_producer_path
        or descriptor.get("sha256") != expected_sha256
        or isinstance(descriptor.get("size_bytes"), bool)
        or not isinstance(descriptor.get("size_bytes"), int)
        or descriptor.get("size_bytes") != output_record["size_bytes"]
        or descriptor.get("validation_state") != "valid"
    ):
        _invalid("Typed workflow artifact descriptor does not match", "ARTIFACT_DESCRIPTOR_INVALID")

    producer_artifact_path = _checked_path(
        workflow_path.parent,
        expected_producer_path,
        "producer artifact",
    )
    try:
        producer_artifact_size = producer_artifact_path.stat().st_size
    except OSError:
        _unavailable("Producer artifact is unreadable", "ARTIFACT_UNAVAILABLE")
    if producer_artifact_size != output_record["size_bytes"]:
        _invalid("Producer artifact size does not match its inventory", "ARTIFACT_INTEGRITY_FAILED")
    if _sha256_file(producer_artifact_path, "producer artifact") != expected_sha256:
        _invalid("Producer artifact digest does not match", "ARTIFACT_INTEGRITY_FAILED")

    consumer_artifact_path = _checked_path(
        root, artifact_path, "consumer artifact"
    )
    try:
        consumer_artifact_size = consumer_artifact_path.stat().st_size
    except OSError:
        _unavailable("Consumer artifact is unreadable", "ARTIFACT_UNAVAILABLE")
    if consumer_artifact_size != output_record["size_bytes"]:
        _invalid("Consumer artifact size does not match", "ARTIFACT_INTEGRITY_FAILED")
    if _sha256_file(consumer_artifact_path, "consumer artifact") != expected_sha256:
        _invalid("Consumer artifact digest does not match", "ARTIFACT_INTEGRITY_FAILED")

    binding = {
        "schema": PRODUCER_ARTIFACT_BINDING_SCHEMA,
        "workflow_id": workflow_id,
        "workflow_sha256": workflow_sha256,
        "workflow_status_raw": workflow_status,
        "stage_id": stage_id,
        "stage_kind": stage_kind,
        "stage_status_raw": stage_status,
        "stage_manifest_sha256": stage_manifest_sha256,
        "artifact_relative_path": artifact_relative_path,
        "artifact_type": artifact_type,
        "contract_version": contract_version,
        "artifact_sha256": expected_sha256,
    }
    return VerifiedProducerArtifact(
        workflow_id=workflow_id,
        workflow_sha256=workflow_sha256,
        workflow_status_raw=workflow_status,
        stage_id=stage_id,
        stage_kind=stage_kind,
        stage_status_raw=stage_status,
        stage_manifest_sha256=stage_manifest_sha256,
        artifact_relative_path=artifact_relative_path,
        artifact_type=artifact_type,
        contract_version=contract_version,
        artifact_sha256=expected_sha256,
        binding_sha256=_canonical_sha256(binding),
    )