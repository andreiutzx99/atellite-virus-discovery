"""Frozen local contracts for the synthetic M16 benchmark harness.

These schemas describe generated software fixtures and custody mechanics only.
They do not encode biological classes, truth, or performance claims.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


PUBLIC_MANIFEST_SCHEMA = "m16-public-manifest-v1"
SYNTHETIC_KEY_SCHEMA = "m16-synthetic-key-v1"
TARGET_REF_SCHEMA = "m16-m15-target-ref-v1"
QUERY_SCHEMA = "m16-m15-state-query-v1"
FIXTURE_PROVENANCE_SCHEMA = "m16-fixture-provenance-v1"
PREDICTION_SCHEMA = "m16-prediction-table-v1"
LEAKAGE_SCHEMA = "m16-leakage-report-v1"
CUSTODY_SCHEMA = "m16-custody-log-v1"
METRIC_SCHEMA = "m16-metric-summary-v1"
RESULT_BUNDLE_SCHEMA = "m16-result-bundle-v1"
PROJECTION_SCHEMA = "m16-m15-dossier-state-projection-v1"

SEMANTIC_VERSION = "1"
OUTPUT_SCHEMA_VERSION = "m16-output-schema-v1"
SCORING_VERSION = "1"
OUTCOME_SCHEMA_VERSION = PROJECTION_SCHEMA
JSON_LIMIT = 1_000_000
RATE_PRECISION = 6

OUTPUT_CONTRACTS = {
    "predictions.json": "m16_prediction_table",
    "leakage_report.json": "m16_leakage_report",
    "custody_log.json": "m16_custody_log",
    "metric_summary.json": "m16_metric_summary",
    "result_bundle.json": "m16_result_bundle",
}
SIDE_CAR_CONTRACTS = {
    name: artifact_type
    for name, artifact_type in OUTPUT_CONTRACTS.items()
    if name != "result_bundle.json"
}

TARGET_TYPES = {
    "M12": "m12_result_bundle",
    "M13": "m13_result_bundle",
    "M14": "m14_result_bundle",
    "M15": "m15_result_bundle",
}
SPLIT_ROLES = frozenset({
    "DEVELOPMENT", "TUNING", "SYNTHETIC_HOLDOUT", "UNASSIGNED",
})
LABEL_STATES = frozenset({
    "SEALED_SYNTHETIC_EXPECTATION", "UNKNOWN", "NOT_APPLICABLE",
})
EXECUTION_STATES = frozenset({
    "COMPLETED", "NOT_EVALUATED", "DEPENDENCY_UNAVAILABLE", "FAILED",
    "INTERRUPTED", "INCOMPLETE", "TRUNCATED", "INVALID_INPUT",
})
OUTCOME_STATES = frozenset({
    "EMITTED", "ABSTAINED", "NOT_APPLICABLE", "UNKNOWN",
})
PREDICTION_CATEGORIES = (
    "PREDICTION_EMITTED", "ABSTAINED", "OUTCOME_UNKNOWN",
    "NOT_EVALUATED", "DEPENDENCY_UNAVAILABLE", "FAILED", "INTERRUPTED",
    "INCOMPLETE", "TRUNCATED", "INVALID_INPUT",
    "PREDICTION_NOT_APPLICABLE",
)
CUSTODY_STATES = (
    "SEALED", "PREDICTIONS_COMMITTED", "BLINDED_CHECKED", "SCORED",
    "INTEGRITY_FAILED",
)

_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")
_EXECUTION_REF_FIELDS = frozenset({
    "schema", "producer_workflow_ref", "producer_stage_id",
    "producer_stage_kind", "producer_stage_manifest_sha256",
})


class M16OutOfScopeError(ValueError):
    """An empirical or biological claim was supplied to the synthetic harness."""


class M16IntegrityError(ValueError):
    """A terminal M16 custody or target-integrity condition was detected."""


class M16PathSecurityError(ValueError):
    """A filesystem input changed or traversed a link while being opened."""


@dataclass(frozen=True)
class FixedRate:
    """A JSON number serialized with exactly six fractional digits."""

    value: Decimal


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number is forbidden: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def parse_json_bytes(raw, *, label="M16 JSON", maximum=JSON_LIMIT):
    if not isinstance(raw, bytes):
        raise ValueError(f"{label} must be read as bytes")
    if len(raw) > maximum:
        raise ValueError(f"{label} exceeds the size limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{label} must not contain a UTF-8 BOM")
    if b"\r" in raw:
        raise ValueError(f"{label} must use LF line endings")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_int=int,
            parse_float=Decimal,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from error
    _validate_json_value(value, label)
    return value


def read_json(path, *, label="M16 JSON", maximum=JSON_LIMIT):
    path = Path(path)
    raw = path.read_bytes()
    return parse_json_bytes(raw, label=label, maximum=maximum)


def _validate_json_value(value, label="JSON"):
    if value is None or isinstance(value, (str, bool, int, Decimal, FixedRate)):
        if isinstance(value, FixedRate) and not value.value.is_finite():
            raise ValueError(f"{label} contains a non-finite rate")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError(f"{label} contains a non-finite number")
        return
    if isinstance(value, float):
        raise ValueError(f"{label} must not contain binary floating-point values")
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, label)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{label} object keys must be strings")
        for item in value.values():
            _validate_json_value(item, label)
        return
    raise ValueError(f"{label} contains a non-JSON value")


def _decimal_token(value):
    if not value.is_finite():
        raise ValueError("Non-finite decimal values cannot be serialized")
    sign, digits, exponent = value.as_tuple()
    if not any(digits):
        return ("-" if sign else "") + "0.0e+0"
    digits = list(digits)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    adjusted = len(digits) + exponent - 1
    mantissa = str(digits[0]) + "." + (
        "".join(str(digit) for digit in digits[1:]) or "0"
    )
    exponent_token = f"+{adjusted}" if adjusted >= 0 else str(adjusted)
    return ("-" if sign else "") + mantissa + "e" + exponent_token


def _encode_json(value):
    if isinstance(value, FixedRate):
        quantized = value.value.quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        return format(quantized, ".6f")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _decimal_token(value)
    if isinstance(value, float):
        raise ValueError("Binary floating-point output is forbidden")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(_encode_json(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        entries = (
            json.dumps(key, ensure_ascii=False) + ":" + _encode_json(value[key])
            for key in sorted(value)
        )
        return "{" + ",".join(entries) + "}"
    raise ValueError(f"Cannot serialize non-JSON value {type(value).__name__}")


def _encode_json_pretty(value, level=0):
    indent = "  " * level
    child_indent = "  " * (level + 1)
    if isinstance(value, (dict, list)) and not value:
        return "{}" if isinstance(value, dict) else "[]"
    if isinstance(value, dict):
        rows = [
            child_indent + json.dumps(key, ensure_ascii=False) + ": "
            + _encode_json_pretty(value[key], level + 1)
            for key in sorted(value)
        ]
        return "{\n" + ",\n".join(rows) + "\n" + indent + "}"
    if isinstance(value, list):
        rows = [
            child_indent + _encode_json_pretty(item, level + 1)
            for item in value
        ]
        return "[\n" + ",\n".join(rows) + "\n" + indent + "]"
    if isinstance(value, FixedRate):
        quantized = value.value.quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        return format(quantized, ".6f")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _decimal_token(value)
    if isinstance(value, float):
        raise ValueError("Binary floating-point output is forbidden")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ValueError(f"Cannot serialize non-JSON value {type(value).__name__}")


def canonical_json_bytes(value):
    _validate_json_value(value, "M16 semantic JSON")
    return _encode_json(value).encode("utf-8")


def semantic_sha256(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_json(path, value):
    _validate_json_value(value, "M16 output JSON")
    raw = (_encode_json_pretty(value) + "\n").encode("utf-8")
    path = Path(path)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value):
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def safe_relative_path(value, label):
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or _DRIVE_RE.match(value)
    ):
        raise ValueError(f"{label} must be a normalized relative path")
    path = PurePosixPath(value)
    if (
        str(path) != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"{label} must be a normalized relative path")
    return value


def resolve_relative_path(root, value, label, *, require_file=False):
    safe_relative_path(value, label)
    root = Path(root).resolve(strict=True)
    candidate = root
    for part in PurePosixPath(value).parts:
        candidate = candidate / part
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if require_file:
                raise
            return candidate
        reparse_point = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if candidate.is_symlink() or getattr(info, "st_file_attributes", 0) & reparse_point:
            raise ValueError(f"{label} must not traverse links")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"{label} escapes its declared root")
    if require_file and (not candidate.is_file() or candidate.is_symlink()):
        raise ValueError(f"{label} must name a regular file")
    return candidate


def _is_reparse_point(info):
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(getattr(info, "st_file_attributes", 0) & reparse_point)
    )


def _stat_identity(info, label):
    device = getattr(info, "st_dev", None)
    inode = getattr(info, "st_ino", None)
    if not isinstance(inode, int) or inode == 0:
        raise M16PathSecurityError(
            f"{label} filesystem does not provide a stable file identity"
        )
    return device, inode


def _check_path_component(info, label, *, directory):
    if _is_reparse_point(info):
        raise M16PathSecurityError(
            f"{label} must not traverse a symbolic link or reparse point"
        )
    if directory and not stat.S_ISDIR(info.st_mode):
        raise M16PathSecurityError(
            f"{label} contains a non-directory path component"
        )
    if not directory and not stat.S_ISREG(info.st_mode):
        raise M16PathSecurityError(f"{label} must name a regular file")


def _open_posix_regular_file(path, label):
    """Open every path component relative to pinned, no-follow directory fds."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    parts = absolute.parts
    if len(parts) < 2 or not absolute.anchor:
        raise M16PathSecurityError(f"{label} must name an absolute regular file")
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in getattr(os, "supports_dir_fd", set())
    ):
        raise M16PathSecurityError(
            f"{label} cannot be opened with race-resistant no-follow semantics"
        )

    common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags = common_flags | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = None
    file_fd = None
    try:
        current_fd = os.open(absolute.anchor, directory_flags)
        _check_path_component(os.fstat(current_fd), label, directory=True)
        for part in parts[1:-1]:
            next_fd = None
            try:
                next_fd = os.open(
                    part, directory_flags, dir_fd=current_fd
                )
                _check_path_component(
                    os.fstat(next_fd), label, directory=True
                )
            except Exception:
                if next_fd is not None:
                    os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(
            parts[-1],
            common_flags | os.O_NOFOLLOW,
            dir_fd=current_fd,
        )
        _check_path_component(os.fstat(file_fd), label, directory=False)
        return file_fd
    except OSError as error:
        if file_fd is not None:
            os.close(file_fd)
            file_fd = None
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise M16PathSecurityError(
                f"{label} must not traverse a symbolic link or non-directory"
            ) from error
        raise
    except Exception:
        if file_fd is not None:
            os.close(file_fd)
        raise
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _windows_path_snapshot(path, label):
    absolute = Path(os.path.abspath(os.fspath(path)))
    if not absolute.anchor:
        raise M16PathSecurityError(f"{label} must name an absolute regular file")
    parts = absolute.parts
    if len(parts) < 2:
        raise M16PathSecurityError(f"{label} must name a regular file")

    current = Path(absolute.anchor)
    root_info = current.lstat()
    _check_path_component(root_info, label, directory=True)
    snapshots = [(current, _stat_identity(root_info, label), True)]
    remaining = parts[1:]
    for index, part in enumerate(remaining):
        current = current / part
        info = current.lstat()
        is_directory = index < len(remaining) - 1
        _check_path_component(info, label, directory=is_directory)
        snapshots.append((current, _stat_identity(info, label), is_directory))
    return absolute, snapshots


def _open_windows_regular_file(path, label):
    """Use Windows file IDs to detect a path/reparse swap around CreateFile."""
    absolute, snapshots = _windows_path_snapshot(path, label)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOINHERIT", 0)
    )
    file_fd = None
    try:
        file_fd = os.open(os.fspath(absolute), flags)
        opened = os.fstat(file_fd)
        _check_path_component(opened, label, directory=False)
        if _stat_identity(opened, label) != snapshots[-1][1]:
            raise M16PathSecurityError(
                f"{label} changed while its file handle was being opened"
            )
        for component, expected_identity, is_directory in snapshots:
            observed = component.lstat()
            _check_path_component(
                observed, label, directory=is_directory
            )
            if _stat_identity(observed, label) != expected_identity:
                raise M16PathSecurityError(
                    f"{label} path changed while its file handle was being opened"
                )
        return file_fd
    except Exception:
        if file_fd is not None:
            os.close(file_fd)
        raise


def read_regular_file(path, *, label="M16 input", maximum=JSON_LIMIT):
    """Read one regular file without following links or accepting a path swap."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    if os.name == "nt":
        file_fd = _open_windows_regular_file(absolute, label)
    else:
        file_fd = _open_posix_regular_file(absolute, label)

    try:
        before = os.fstat(file_fd)
        chunks = []
        total = 0
        while True:
            request_size = 64 * 1024
            if maximum is not None:
                request_size = min(request_size, maximum + 1 - total)
                if request_size <= 0:
                    raise ValueError(f"{label} exceeds the size limit")
            block = os.read(file_fd, request_size)
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if maximum is not None and total > maximum:
                raise ValueError(f"{label} exceeds the size limit")
        after = os.fstat(file_fd)
        if (
            _stat_identity(before, label) != _stat_identity(after, label)
            or before.st_size != after.st_size
        ):
            raise M16PathSecurityError(
                f"{label} changed while its contents were being read"
            )
        return b"".join(chunks)
    finally:
        os.close(file_fd)


def read_relative_file(root, value, *, label="M16 input", maximum=JSON_LIMIT):
    """Read a normalized relative file while pinning or validating its identity."""
    safe_relative_path(value, label)
    path = Path(root).joinpath(*PurePosixPath(value).parts)
    return read_regular_file(path, label=label, maximum=maximum)


def _exact_object(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"{label} has unknown or missing fields")


def _text(value, label, *, maximum=256):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} must be non-empty printable text")
    return value


def _token(value, label):
    _text(value, label)
    if not _TOKEN_RE.fullmatch(value):
        raise ValueError(f"{label} is not a safe stable identifier")
    return value


def _hash(value, label):
    if not is_sha256(value):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _validate_execution_ref(value):
    _exact_object(value, _EXECUTION_REF_FIELDS, "M16 producer_execution_ref")
    if value.get("schema") != "producer-execution-ref-v1":
        raise ValueError("M16 producer execution reference schema is invalid")
    workflow_ref = value.get("producer_workflow_ref")
    _exact_object(
        workflow_ref, {"path", "sha256", "workflow_id"},
        "M16 producer workflow reference",
    )
    safe_relative_path(workflow_ref["path"], "producer workflow reference path")
    if PurePosixPath(workflow_ref["path"]).name != "workflow.json":
        raise ValueError("M16 producer workflow reference must name workflow.json")
    _hash(workflow_ref["sha256"], "producer workflow SHA-256")
    _text(workflow_ref["workflow_id"], "producer workflow ID")
    _token(value["producer_stage_id"], "producer stage ID")
    _token(value["producer_stage_kind"], "producer stage kind")
    _hash(value["producer_stage_manifest_sha256"], "producer stage-manifest SHA-256")
    return value


def validate_target_ref(value):
    fields = {
        "schema", "producer_milestone", "producer_execution_ref",
        "bundle_root_ref", "artifact_type", "contract_version",
        "semantic_version", "artifact_path", "artifact_relative_path",
        "artifact_sha256", "implementation", "contract_semantics",
        "configuration",
    }
    _exact_object(value, fields, "M16 target_ref")
    if value["schema"] != TARGET_REF_SCHEMA:
        raise ValueError("Unsupported M16 target reference schema")
    if value["producer_milestone"] != "M15":
        raise ValueError("M16 v1 only enables the M15 target profile")
    _validate_execution_ref(value["producer_execution_ref"])
    safe_relative_path(value["bundle_root_ref"], "M16 bundle_root_ref")
    if value["artifact_type"] != "m15_result_bundle":
        raise ValueError("M16 M15 target must be an m15_result_bundle")
    if value["contract_version"] != "1" or value["semantic_version"] != "2":
        raise ValueError("M16 M15 target contract or semantic version is unsupported")
    safe_relative_path(value["artifact_path"], "M16 artifact_path")
    safe_relative_path(value["artifact_relative_path"], "M16 artifact_relative_path")
    if value["artifact_relative_path"] != "result_bundle.json":
        raise ValueError("M16 target must select the M15 result-bundle inventory entry")
    if PurePosixPath(value["artifact_path"]).name != "result_bundle.json":
        raise ValueError("M16 artifact_path must name result_bundle.json")
    _hash(value["artifact_sha256"], "M16 target artifact SHA-256")
    if not isinstance(value["implementation"], dict):
        raise ValueError("M16 target implementation identity must be an object")
    if not isinstance(value["contract_semantics"], dict):
        raise ValueError("M16 target contract semantics must be an object")
    if value["configuration"] != {}:
        raise ValueError("M16 M15 target configuration must be empty")
    _validate_json_value(value, "M16 target_ref")
    return value


def _validate_target_input_ref(value):
    _exact_object(value, {"path", "schema", "sha256"}, "target_input_ref")
    safe_relative_path(value["path"], "target_input_ref.path")
    if value["schema"] != QUERY_SCHEMA:
        raise ValueError("target_input_ref schema is unsupported")
    _hash(value["sha256"], "target_input_ref semantic SHA-256")
    return value


def validate_public_manifest(value):
    fields = {
        "schema", "dataset_kind", "fixture_set_id",
        "sealed_key_commitment", "target_ref", "adapter_id",
        "adapter_version", "items",
    }
    _exact_object(value, fields, "M16 public manifest")
    if value["schema"] != PUBLIC_MANIFEST_SCHEMA:
        raise ValueError("M16 public-manifest schema is unsupported")
    if value["dataset_kind"] == "EMPIRICAL":
        raise M16OutOfScopeError("OUT_OF_SCOPE: empirical M16 inputs are forbidden")
    if value["dataset_kind"] != "SYNTHETIC_FIXTURE":
        raise ValueError("M16 dataset_kind must be SYNTHETIC_FIXTURE")
    fixture_set_id = _token(value["fixture_set_id"], "fixture_set_id")
    commitment = _text(
        value["sealed_key_commitment"], "sealed_key_commitment", maximum=512
    )
    validate_target_ref(value["target_ref"])
    _token(value["adapter_id"], "adapter_id")
    _text(value["adapter_version"], "adapter_version", maximum=64)
    if not isinstance(value["items"], list):
        raise ValueError("M16 public items must be an array")
    items = []
    seen = set()
    item_fields = {
        "item_id", "target_input_ref", "group_ids", "split_role",
        "label_state", "fixture_provenance",
    }
    for item in value["items"]:
        _exact_object(item, item_fields, "M16 public item")
        item_id = _token(item["item_id"], "item_id")
        if item_id in seen:
            raise ValueError("M16 public item IDs must be unique")
        seen.add(item_id)
        _validate_target_input_ref(item["target_input_ref"])
        group_ids = item["group_ids"]
        if not isinstance(group_ids, list) or any(
            not isinstance(group_id, str) for group_id in group_ids
        ):
            raise ValueError("M16 group_ids must be an array of identifiers")
        for group_id in group_ids:
            _token(group_id, "group_id")
        if group_ids != sorted(set(group_ids)):
            raise ValueError("M16 group_ids must be sorted and unique")
        if item["split_role"] not in SPLIT_ROLES:
            raise ValueError("M16 split_role is unsupported")
        if item["label_state"] not in LABEL_STATES:
            raise ValueError("M16 label_state is unsupported")
        provenance = item["fixture_provenance"]
        _exact_object(
            provenance,
            {"schema", "scope", "fixture_set_id"},
            "M16 fixture_provenance",
        )
        if (
            provenance["schema"] != FIXTURE_PROVENANCE_SCHEMA
            or provenance["scope"] != "SOFTWARE_CONTRACT"
            or provenance["fixture_set_id"] != fixture_set_id
        ):
            raise ValueError("M16 item fixture provenance is not software-contract scoped")
        items.append(dict(item))
    normalized = dict(value)
    normalized["items"] = sorted(items, key=lambda item: item["item_id"])
    _validate_json_value(normalized, "M16 public manifest")
    return normalized


def validate_synthetic_key(value, public_manifest):
    fields = {"schema", "fixture_set_id", "sealed_key_commitment", "items"}
    _exact_object(value, fields, "M16 sealed synthetic key")
    if value["schema"] != SYNTHETIC_KEY_SCHEMA:
        raise ValueError("M16 sealed-key schema is unsupported")
    if value["fixture_set_id"] != public_manifest["fixture_set_id"]:
        raise M16IntegrityError("INTEGRITY_FAILED: fixture_set_id mismatch")
    if value["sealed_key_commitment"] != public_manifest["sealed_key_commitment"]:
        raise M16IntegrityError("INTEGRITY_FAILED: sealed_key_commitment mismatch")
    if not isinstance(value["items"], list):
        raise ValueError("M16 sealed-key items must be an array")
    expected_ids = {
        item["item_id"] for item in public_manifest["items"]
        if item["label_state"] == "SEALED_SYNTHETIC_EXPECTATION"
    }
    rows = []
    seen = set()
    for row in value["items"]:
        _exact_object(
            row,
            {"item_id", "expected_software_outcome", "label_scope"},
            "M16 sealed-key item",
        )
        item_id = _token(row["item_id"], "sealed-key item_id")
        if item_id in seen:
            raise ValueError("M16 sealed-key item IDs must be unique")
        seen.add(item_id)
        if row["label_scope"] != "SOFTWARE_CONTRACT":
            raise M16OutOfScopeError("OUT_OF_SCOPE: sealed key labels must be software-contract outcomes")
        expected = row["expected_software_outcome"]
        if not isinstance(expected, (str, dict)):
            raise ValueError("M16 expected software outcomes must be strings or objects")
        _validate_json_value(expected, "M16 expected software outcome")
        rows.append(dict(row))
    if seen != expected_ids:
        raise ValueError("M16 sealed-key coverage must match labelled public items exactly")
    normalized = dict(value)
    normalized["items"] = sorted(rows, key=lambda row: row["item_id"])
    _validate_json_value(normalized, "M16 sealed synthetic key")
    return normalized


def validate_query(value):
    _exact_object(value, {"schema", "evidence_ids"}, "M16 M15 state query")
    if value["schema"] != QUERY_SCHEMA:
        raise ValueError("M16 M15 state-query schema is unsupported")
    evidence_ids = value["evidence_ids"]
    if not isinstance(evidence_ids, list):
        raise ValueError("M16 query evidence_ids must be an array")
    normalized_ids = []
    seen = set()
    for evidence_id in evidence_ids:
        _hash(evidence_id, "M16 query evidence_id")
        if evidence_id in seen:
            raise ValueError("M16 query evidence_ids must be unique")
        seen.add(evidence_id)
        normalized_ids.append(evidence_id)
    normalized = {"schema": QUERY_SCHEMA, "evidence_ids": sorted(normalized_ids)}
    return normalized


def semantic_public_projection(manifest, query_semantics):
    """Return the path-free public semantics used for target cache identity."""
    target = dict(manifest["target_ref"])
    target.pop("bundle_root_ref", None)
    target.pop("artifact_path", None)
    execution_ref = dict(target["producer_execution_ref"])
    workflow_ref = dict(execution_ref["producer_workflow_ref"])
    workflow_ref.pop("path", None)
    execution_ref["producer_workflow_ref"] = workflow_ref
    target["producer_execution_ref"] = execution_ref
    items = []
    for item in manifest["items"]:
        ref = item["target_input_ref"]
        items.append({
            "item_id": item["item_id"],
            "target_input_ref": {
                "schema": ref["schema"],
                "semantic_sha256": query_semantics[item["item_id"]]["semantic_sha256"],
            },
            "group_ids": list(item["group_ids"]),
            "split_role": item["split_role"],
            "label_state": item["label_state"],
            "fixture_provenance": item["fixture_provenance"],
        })
    return {
        "schema": manifest["schema"],
        "dataset_kind": manifest["dataset_kind"],
        "fixture_set_id": manifest["fixture_set_id"],
        "sealed_key_commitment": manifest["sealed_key_commitment"],
        "target_ref": target,
        "adapter_id": manifest["adapter_id"],
        "adapter_version": manifest["adapter_version"],
        "items": items,
    }


def validate_projection(value):
    fields = {
        "schema", "input_schema", "semantic_version", "candidate_id",
        "result_completeness", "optional_stage_states",
        "compatibility_warnings", "records",
    }
    _exact_object(value, fields, "M16 M15 dossier-state projection")
    if value["schema"] != PROJECTION_SCHEMA:
        raise ValueError("M16 M15 projection schema is invalid")
    if value["input_schema"] not in {"m15-input-v1", "m15-input-v2"}:
        raise ValueError("M16 M15 projection input_schema is invalid")
    if value["semantic_version"] != "2":
        raise ValueError("M16 M15 projection semantic_version is unsupported")
    _text(value["candidate_id"], "M16 projection candidate_id")
    if value["result_completeness"] not in {
        "COMPLETE_WITHIN_SUPPLIED_SCOPE", "PARTIAL", "NOT_EVALUATED", "INVALID",
    }:
        raise ValueError("M16 M15 projection completeness is invalid")
    if not isinstance(value["optional_stage_states"], dict):
        raise ValueError("M16 M15 projection optional_stage_states must be an object")
    if not isinstance(value["compatibility_warnings"], list) or any(
        not isinstance(item, str) for item in value["compatibility_warnings"]
    ):
        raise ValueError("M16 M15 projection compatibility_warnings are invalid")
    if not isinstance(value["records"], list):
        raise ValueError("M16 M15 projection records must be an array")
    required_record_fields = {
        "evidence_id", "validation_state", "reason_code",
        "producer_status_raw", "producer_schema_raw",
        "producer_provenance_state", "producer_provenance_error_code",
        "producer_binding_sha256", "producer_execution_state",
        "semantic_axes", "dependency_edge_ids",
    }
    evidence_ids = []
    for row in value["records"]:
        _exact_object(row, required_record_fields, "M16 projected M15 record")
        _hash(row["evidence_id"], "M16 projected evidence_id")
        if not isinstance(row["semantic_axes"], dict):
            raise ValueError("M16 projected semantic_axes must be an object")
        if not isinstance(row["dependency_edge_ids"], list):
            raise ValueError("M16 projected dependency_edge_ids must be an array")
        for edge_id in row["dependency_edge_ids"]:
            _hash(edge_id, "M16 projected dependency_edge_id")
        for name in (
            "reason_code", "producer_status_raw", "producer_schema_raw",
            "producer_provenance_error_code", "producer_execution_state",
        ):
            if row[name] is not None and not isinstance(row[name], str):
                raise ValueError(f"M16 projected {name} must be a string or null")
        if row["producer_binding_sha256"] is not None:
            _hash(row["producer_binding_sha256"], "M16 projected binding SHA-256")
        evidence_ids.append(row["evidence_id"])
    if evidence_ids != sorted(set(evidence_ids)):
        raise ValueError("M16 projected records must be uniquely sorted by evidence_id")
    _validate_json_value(value, "M16 M15 projection")
    return value


def _validate_target_provenance(value):
    fields = {
        "producer_milestone", "producer_workflow_sha256",
        "producer_stage_manifest_sha256", "producer_stage_id",
        "producer_stage_kind", "artifact_type", "contract_version",
        "semantic_version", "artifact_sha256", "binding_sha256",
    }
    _exact_object(value, fields, "M16 prediction target provenance")
    if (
        value["producer_milestone"] != "M15"
        or value["producer_stage_kind"] != "m15_evidence_dossier"
        or value["artifact_type"] != "m15_result_bundle"
        or value["contract_version"] != "1"
        or value["semantic_version"] != "2"
    ):
        raise ValueError("M16 prediction target provenance is unsupported")
    _token(value["producer_stage_id"], "M16 target producer stage ID")
    for name in (
        "producer_workflow_sha256", "producer_stage_manifest_sha256",
        "artifact_sha256", "binding_sha256",
    ):
        _hash(value[name], f"M16 target provenance {name}")


def validate_prediction_table(value):
    _exact_object(
        value,
        {"schema", "fixture_set_id", "adapter_id", "adapter_version",
         "target_provenance", "rows"},
        "M16 prediction table",
    )
    if value["schema"] != PREDICTION_SCHEMA:
        raise ValueError("M16 prediction-table schema is invalid")
    _token(value["fixture_set_id"], "M16 prediction fixture_set_id")
    _token(value["adapter_id"], "M16 prediction adapter_id")
    _text(value["adapter_version"], "M16 prediction adapter_version", maximum=64)
    _validate_target_provenance(value["target_provenance"])
    if not isinstance(value["rows"], list):
        raise ValueError("M16 prediction rows must be an array")
    item_ids = []
    for row in value["rows"]:
        _exact_object(
            row,
            {"item_id", "execution_state", "outcome_state", "emitted_value",
             "reason_code"},
            "M16 prediction row",
        )
        _token(row["item_id"], "M16 prediction item_id")
        if row["execution_state"] not in EXECUTION_STATES:
            raise ValueError("M16 prediction execution_state is invalid")
        if row["outcome_state"] not in OUTCOME_STATES:
            raise ValueError("M16 prediction outcome_state is invalid")
        if row["execution_state"] != "COMPLETED":
            if row["outcome_state"] != "UNKNOWN" or row["emitted_value"] is not None:
                raise ValueError("Non-completed M16 predictions must have null/unknown outcomes")
        elif row["outcome_state"] == "EMITTED":
            if row["emitted_value"] is None:
                raise ValueError("An emitted M16 prediction requires an emitted value")
        elif row["emitted_value"] is not None:
            raise ValueError("A non-emitted M16 outcome cannot carry an emitted value")
        if row["reason_code"] is not None and not isinstance(row["reason_code"], str):
            raise ValueError("M16 prediction reason_code must be a string or null")
        _validate_json_value(row["emitted_value"], "M16 emitted value")
        item_ids.append(row["item_id"])
    if item_ids != sorted(set(item_ids)):
        raise ValueError("M16 prediction rows must be uniquely sorted by item_id")
    _validate_json_value(value, "M16 prediction table")
    return {"record_count": len(item_ids)}


def validate_leakage_report(value):
    _exact_object(
        value,
        {"schema", "status", "group_checks", "transitive_components",
         "offending_group_ids", "offending_item_ids", "scoring_blocked",
         "blocking_reason"},
        "M16 leakage report",
    )
    if value["schema"] != LEAKAGE_SCHEMA:
        raise ValueError("M16 leakage-report schema is invalid")
    if value["status"] not in {"CLEAR", "LEAKAGE_DETECTED"}:
        raise ValueError("M16 leakage status is invalid")
    if type(value["scoring_blocked"]) is not bool:
        raise ValueError("M16 scoring_blocked must be boolean")
    if value["scoring_blocked"] != (value["status"] == "LEAKAGE_DETECTED"):
        raise ValueError("M16 leakage status and scoring_blocked disagree")
    if value["blocking_reason"] is not None and not isinstance(value["blocking_reason"], str):
        raise ValueError("M16 leakage blocking_reason must be a string or null")
    if value["scoring_blocked"] != (value["blocking_reason"] is not None):
        raise ValueError("M16 leakage blocking reason is inconsistent")
    if not isinstance(value["group_checks"], list):
        raise ValueError("M16 leakage group_checks must be an array")
    group_ids = []
    for row in value["group_checks"]:
        _exact_object(row, {"group_id", "item_ids", "split_roles", "leaking"},
                      "M16 leakage group check")
        _token(row["group_id"], "M16 group check group_id")
        if row["item_ids"] != sorted(set(row["item_ids"])):
            raise ValueError("M16 leakage item IDs must be unique and sorted")
        if row["split_roles"] != sorted(set(row["split_roles"])):
            raise ValueError("M16 leakage split roles must be unique and sorted")
        if any(role not in SPLIT_ROLES for role in row["split_roles"]):
            raise ValueError("M16 leakage report contains an unsupported split")
        if type(row["leaking"]) is not bool:
            raise ValueError("M16 leakage group leaking flag must be boolean")
        if row["leaking"] != (len(row["split_roles"]) > 1):
            raise ValueError("M16 leakage group check is inconsistent")
        group_ids.append(row["group_id"])
    if group_ids != sorted(set(group_ids)):
        raise ValueError("M16 leakage group checks must be uniquely sorted")
    if not isinstance(value["transitive_components"], list):
        raise ValueError("M16 transitive components must be an array")
    previous = None
    for row in value["transitive_components"]:
        _exact_object(row, {"item_ids", "group_ids", "split_roles", "leaking"},
                      "M16 leakage component")
        for key in ("item_ids", "group_ids", "split_roles"):
            if row[key] != sorted(set(row[key])):
                raise ValueError(f"M16 leakage component {key} must be unique and sorted")
        if type(row["leaking"]) is not bool:
            raise ValueError("M16 leakage component leaking flag must be boolean")
        if row["leaking"] != (len(row["split_roles"]) > 1):
            raise ValueError("M16 leakage component is inconsistent")
        key = tuple(row["item_ids"])
        if previous is not None and key <= previous:
            raise ValueError("M16 leakage components must be deterministically sorted")
        previous = key
    for field in ("offending_group_ids", "offending_item_ids"):
        if value[field] != sorted(set(value[field])):
            raise ValueError(f"M16 {field} must be unique and sorted")
    if value["status"] == "CLEAR" and (
        value["offending_group_ids"] or value["offending_item_ids"]
    ):
        raise ValueError("Clear M16 leakage report cannot contain offending IDs")
    _validate_json_value(value, "M16 leakage report")
    return {"group_count": len(group_ids)}


def validate_custody_log(value):
    _exact_object(value, {"schema", "events", "terminal_state"}, "M16 custody log")
    if value["schema"] != CUSTODY_SCHEMA:
        raise ValueError("M16 custody-log schema is invalid")
    if not isinstance(value["events"], list) or not value["events"]:
        raise ValueError("M16 custody log must contain events")
    current = None
    terminal = None
    sealed_key_commitment = None
    target_binding_sha256 = None
    prediction_sha256 = None
    for sequence, event in enumerate(value["events"], start=1):
        _exact_object(
            event,
            {"sequence", "from_state", "to_state", "actor", "tool_identity",
             "sealed_key_commitment", "sealed_key_digest", "digests", "reason"},
            "M16 custody event",
        )
        if event["sequence"] != sequence:
            raise ValueError("M16 custody sequence numbers must be contiguous")
        if event["from_state"] != current:
            raise ValueError("M16 custody transition order is invalid")
        destination = event["to_state"]
        if destination not in CUSTODY_STATES:
            raise ValueError("M16 custody state is unsupported")
        allowed = (
            (current is None and destination == "SEALED")
            or (current == "SEALED" and destination in {
                "PREDICTIONS_COMMITTED", "INTEGRITY_FAILED",
            })
            or (current == "PREDICTIONS_COMMITTED" and destination in {
                "BLINDED_CHECKED", "INTEGRITY_FAILED",
            })
            or (current == "BLINDED_CHECKED" and destination in {
                "SCORED", "INTEGRITY_FAILED",
            })
        )
        if not allowed:
            raise ValueError("M16 custody transition is not permitted")
        _text(event["actor"], "M16 custody actor")
        _text(event["tool_identity"], "M16 custody tool identity")
        _text(
            event["sealed_key_commitment"],
            "M16 custody sealed_key_commitment",
            maximum=512,
        )
        if sealed_key_commitment is None:
            if destination != "SEALED":
                raise ValueError("M16 custody log must begin with SEALED")
            sealed_key_commitment = event["sealed_key_commitment"]
        elif event["sealed_key_commitment"] != sealed_key_commitment:
            raise ValueError(
                "M16 custody sealed_key_commitment is inconsistent across events"
            )

        sealed_key_digest = event["sealed_key_digest"]
        if destination in {
            "SEALED", "PREDICTIONS_COMMITTED", "BLINDED_CHECKED",
        }:
            if sealed_key_digest is not None:
                raise ValueError(
                    "M16 sealed_key_digest is unavailable before scorer access"
                )
        elif destination == "SCORED":
            _hash(sealed_key_digest, "M16 custody sealed_key_digest")
        elif destination == "INTEGRITY_FAILED" and sealed_key_digest is not None:
            if current != "BLINDED_CHECKED":
                raise ValueError(
                    "M16 sealed_key_digest is unavailable before scorer access"
                )
            _hash(sealed_key_digest, "M16 custody sealed_key_digest")

        _exact_object(
            event["digests"],
            {"target_binding_sha256", "prediction_sha256"},
            "M16 custody artifact digests",
        )
        for name, digest in event["digests"].items():
            if digest is not None:
                _hash(digest, f"M16 custody digest {name}")
        target_digest = event["digests"]["target_binding_sha256"]
        prediction_digest = event["digests"]["prediction_sha256"]
        if (
            target_digest is not None
            and target_binding_sha256 is not None
            and target_digest != target_binding_sha256
        ):
            raise ValueError("M16 custody target identity changed between events")
        if (
            prediction_digest is not None
            and prediction_sha256 is not None
            and prediction_digest != prediction_sha256
        ):
            raise ValueError(
                "M16 custody committed prediction identity changed between events"
            )
        if target_digest is not None:
            target_binding_sha256 = target_digest
        if prediction_digest is not None:
            prediction_sha256 = prediction_digest
        if destination in {
            "PREDICTIONS_COMMITTED", "BLINDED_CHECKED", "SCORED",
        }:
            if target_digest is None or prediction_digest is None:
                raise ValueError(
                    f"M16 {destination} custody event requires target and prediction digests"
                )
        if destination in {"BLINDED_CHECKED", "SCORED"} and (
            target_digest != target_binding_sha256
            or prediction_digest != prediction_sha256
        ):
            raise ValueError(
                f"M16 {destination} custody event changed a committed identity"
            )
        if destination == "INTEGRITY_FAILED" and prediction_sha256 is not None and (
            target_digest != target_binding_sha256
            or prediction_digest != prediction_sha256
        ):
            raise ValueError(
                "M16 integrity-failure event changed a committed identity"
            )
        _text(event["reason"], "M16 custody reason")
        current = destination
        if destination in {"SCORED", "INTEGRITY_FAILED"}:
            terminal = destination
    if terminal != value["terminal_state"]:
        raise ValueError("M16 custody terminal state does not match its event log")
    if terminal is None:
        raise ValueError("M16 custody log has no terminal state")
    if value["events"][-1]["to_state"] != terminal:
        raise ValueError("M16 custody log cannot continue after a terminal state")
    return {"event_count": len(value["events"]), "terminal_state": terminal}


def _count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _rate(value, numerator, denominator, label):
    if denominator == 0:
        if value is not None:
            raise ValueError(f"{label} must be null when its denominator is zero")
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite decimal")
    if value.as_tuple().exponent != -RATE_PRECISION:
        raise ValueError(f"{label} must have exactly six fractional digits")
    expected = (
        Decimal(numerator) / Decimal(denominator)
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    if value != expected:
        raise ValueError(f"{label} does not match its declared numerator and denominator")


def validate_metric_summary(value):
    fields = {
        "schema", "scope", "rate_precision", "n_items",
        "prediction_counts", "n_labelled", "n_unknown_label",
        "n_not_applicable_label", "n_emitted", "n_exact_match",
        "coverage", "fixture_agreement_rate", "fixture_match_over_labelled",
        "outcome_rows",
    }
    _exact_object(value, fields, "M16 metric summary")
    if value["schema"] != METRIC_SCHEMA or value["scope"] != "SOFTWARE_CONTRACT":
        raise ValueError("M16 metric summary schema or scope is invalid")
    if value["rate_precision"] != RATE_PRECISION:
        raise ValueError("M16 rate precision is unsupported")
    n_items = _count(value["n_items"], "M16 n_items")
    counts = value["prediction_counts"]
    if not isinstance(counts, dict) or set(counts) != set(PREDICTION_CATEGORIES):
        raise ValueError("M16 prediction category counts are incomplete")
    if sum(_count(counts[name], f"M16 prediction count {name}")
           for name in PREDICTION_CATEGORIES) != n_items:
        raise ValueError("M16 prediction categories do not sum to n_items")
    labelled = _count(value["n_labelled"], "M16 n_labelled")
    unknown = _count(value["n_unknown_label"], "M16 n_unknown_label")
    not_applicable = _count(
        value["n_not_applicable_label"], "M16 n_not_applicable_label"
    )
    if labelled + unknown + not_applicable != n_items:
        raise ValueError("M16 label-state counts do not sum to n_items")
    emitted = _count(value["n_emitted"], "M16 n_emitted")
    exact = _count(value["n_exact_match"], "M16 n_exact_match")
    if emitted > labelled or exact > emitted:
        raise ValueError("M16 emitted or exact-match count exceeds its denominator")
    _rate(value["coverage"], emitted, labelled, "M16 coverage")
    _rate(
        value["fixture_agreement_rate"], exact, emitted,
        "M16 fixture_agreement_rate",
    )
    _rate(
        value["fixture_match_over_labelled"], exact, labelled,
        "M16 fixture_match_over_labelled",
    )
    rows = value["outcome_rows"]
    if not isinstance(rows, list):
        raise ValueError("M16 outcome_rows must be an array")
    ids = []
    row_totals = {"n_labelled": 0, "n_emitted": 0, "n_exact_match": 0}
    for row in rows:
        _exact_object(
            row,
            {"outcome_id", "n_labelled", "n_emitted", "n_exact_match"},
            "M16 outcome row",
        )
        _hash(row["outcome_id"], "M16 outcome_id")
        ids.append(row["outcome_id"])
        for key in row_totals:
            row_totals[key] += _count(row[key], f"M16 outcome row {key}")
    if ids != sorted(set(ids)):
        raise ValueError("M16 outcome rows must be uniquely sorted by outcome_id")
    if row_totals != {
        "n_labelled": labelled, "n_emitted": emitted, "n_exact_match": exact,
    }:
        raise ValueError("M16 outcome rows do not reconcile with summary counts")
    return {"record_count": n_items, "n_labelled": labelled}


def validate_result_bundle(value):
    fields = {
        "schema", "scope", "fixture_set_id", "public_manifest_semantic_sha256",
        "sealed_key_commitment", "canonical_sealed_key_sha256",
        "target_identity", "adapter_id",
        "adapter_version", "outcome_schema_version", "prediction_sha256",
        "execution_identity_sha256", "scoring_identity",
        "stage_cache_identity", "outputs",
    }
    _exact_object(value, fields, "M16 result bundle")
    if value["schema"] != RESULT_BUNDLE_SCHEMA or value["scope"] != "SOFTWARE_CONTRACT":
        raise ValueError("M16 result-bundle schema or scope is invalid")
    _token(value["fixture_set_id"], "M16 result fixture_set_id")
    _text(value["sealed_key_commitment"], "M16 result sealed_key_commitment", maximum=512)
    for name in (
        "public_manifest_semantic_sha256", "canonical_sealed_key_sha256",
        "prediction_sha256",
        "execution_identity_sha256",
    ):
        _hash(value[name], f"M16 result {name}")
    if not isinstance(value["target_identity"], dict):
        raise ValueError("M16 result target_identity must be an object")
    _token(value["adapter_id"], "M16 result adapter_id")
    _text(value["adapter_version"], "M16 result adapter_version", maximum=64)
    _text(value["outcome_schema_version"], "M16 outcome schema version", maximum=128)
    if not isinstance(value["scoring_identity"], dict):
        raise ValueError("M16 scoring identity must be an object")
    if not isinstance(value["stage_cache_identity"], dict):
        raise ValueError("M16 stage cache identity must be an object")
    outputs = value["outputs"]
    if not isinstance(outputs, dict) or set(outputs) != set(SIDE_CAR_CONTRACTS):
        raise ValueError("M16 result bundle sidecar inventory is incomplete")
    for name, artifact_type in SIDE_CAR_CONTRACTS.items():
        row = outputs[name]
        _exact_object(
            row, {"artifact_type", "contract_version", "schema", "sha256"},
            f"M16 result sidecar {name}",
        )
        if (
            row["artifact_type"] != artifact_type
            or row["contract_version"] != "1"
            or not isinstance(row["schema"], str)
        ):
            raise ValueError(f"M16 result sidecar {name} has an invalid type/version")
        _hash(row["sha256"], f"M16 result sidecar {name} SHA-256")
    _validate_json_value(value, "M16 result bundle")
    return {"sidecar_count": len(outputs)}


def validate_output_document(artifact_type, value):
    validators = {
        "m16_prediction_table": validate_prediction_table,
        "m16_leakage_report": validate_leakage_report,
        "m16_custody_log": validate_custody_log,
        "m16_metric_summary": validate_metric_summary,
        "m16_result_bundle": validate_result_bundle,
    }
    try:
        validator = validators[artifact_type]
    except KeyError:
        raise ValueError(f"Unknown M16 output artifact type: {artifact_type!r}") from None
    return validator(value)


def validate_output_file(path, artifact_type):
    value = read_json(path, label=f"M16 {artifact_type}")
    details = validate_output_document(artifact_type, value)
    if artifact_type == "m16_result_bundle":
        root = Path(path).parent
        for name, descriptor in value["outputs"].items():
            sidecar = root / name
            if sidecar.is_symlink() or not sidecar.is_file():
                raise ValueError(f"M16 result sidecar is missing or unsafe: {name}")
            if sha256_file(sidecar) != descriptor["sha256"]:
                raise ValueError(f"M16 result sidecar digest mismatch: {name}")
            contract = SIDE_CAR_CONTRACTS[name]
            sidecar_value = read_json(sidecar, label=f"M16 sidecar {name}")
            validate_output_document(contract, sidecar_value)
            if sidecar_value.get("schema") != descriptor["schema"]:
                raise ValueError(f"M16 result sidecar schema mismatch: {name}")
        prediction = read_json(root / "predictions.json", label="M16 predictions")
        if prediction["target_provenance"]["binding_sha256"] != (
            value["target_identity"].get("binding_sha256")
        ):
            raise ValueError("M16 result bundle target identity differs from predictions")
    return details
