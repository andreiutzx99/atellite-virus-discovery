"""Pinned ViennaRNA runtime identity and environment receipt for M11."""

import hashlib
import importlib
import importlib.metadata
import json
import platform
from pathlib import Path
import sys
import sysconfig

from .m11_algorithms import canonical_json


RECEIPT_NAME = "satellite-discovery-m11-runtime-v1.json"
WHEEL_LOCK = {
    ("Linux", "3.11"): (
        "viennarna-2.7.2-cp311-cp311-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl",
        "c85a09270bda4ddb4aa07d2d373e135c4efac94253b121601bb733cfda22dc79",
    ),
    ("Windows", "3.11"): (
        "viennarna-2.7.2-cp311-cp311-win_amd64.whl",
        "b66567c43c1f3b6795a1c7ab46b7315f56bfed4097827d0df80e03ff5b8f0e29",
    ),
    ("Linux", "3.12"): (
        "viennarna-2.7.2-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl",
        "1e4132cbb35dc258cc97f2e1b7b83bd11712d539c4757dfb78445c38041e439c",
    ),
    ("Windows", "3.12"): (
        "viennarna-2.7.2-cp312-cp312-win_amd64.whl",
        "68b0803568549256dadf7383e02ee98973433e6d4c59abebb6a27f278ba77c02",
    ),
}


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _target():
    system = platform.system()
    machine = platform.machine().lower()
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if platform.python_implementation() != "CPython":
        return None
    if system not in {"Linux", "Windows"} or machine not in {"x86_64", "amd64"}:
        return None
    return system, version


def _receipt_path():
    purelib = Path(sysconfig.get_paths()["purelib"])
    return purelib / RECEIPT_NAME


def _installed_tree_digest(distribution):
    entries = []
    for relative in distribution.files or ():
        path = Path(distribution.locate_file(relative))
        if path.is_file():
            entries.append((
                str(relative).replace("\\", "/"),
                _file_sha256(path),
            ))
    entries.sort()
    payload = canonical_json(entries).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def unavailable_identity(reason):
    system = platform.system()
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return {
        "status": "unavailable",
        "reason_code": reason,
        "engine": "ViennaRNA",
        "version": None,
        "wheel_filename": None,
        "wheel_sha256": None,
        "native_library_sha256": None,
        "installed_files_sha256": None,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_abi": sys.implementation.cache_tag,
        "operating_system": system,
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "target_python": version,
    }


def runtime_identity():
    target = _target()
    if target is None or target not in WHEEL_LOCK:
        return unavailable_identity("UNSUPPORTED_RUNTIME_TARGET")
    try:
        distribution = importlib.metadata.distribution("ViennaRNA")
        version = distribution.version
    except importlib.metadata.PackageNotFoundError:
        return unavailable_identity("PACKAGE_NOT_INSTALLED")
    if version != "2.7.2":
        return unavailable_identity("VERSION_MISMATCH")

    expected_filename, expected_sha256 = WHEEL_LOCK[target]
    try:
        receipt = json.loads(_receipt_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return unavailable_identity("PINNED_WHEEL_RECEIPT_MISSING_OR_INVALID")
    if not isinstance(receipt, dict):
        return unavailable_identity("PINNED_WHEEL_RECEIPT_MISSING_OR_INVALID")
    if (
        receipt.get("schema") != "satellite-discovery-m11-runtime-v1"
        or receipt.get("wheel_filename") != expected_filename
        or receipt.get("wheel_sha256") != expected_sha256
        or receipt.get("target_python") != target[1]
        or receipt.get("operating_system") != target[0]
        or receipt.get("architecture") not in {"x86_64", "AMD64"}
    ):
        return unavailable_identity("PINNED_WHEEL_RECEIPT_MISMATCH")
    try:
        module = importlib.import_module("RNA")
        native = importlib.import_module("RNA._RNA")
    except (ImportError, OSError):
        return unavailable_identity("NATIVE_INTERFACE_UNAVAILABLE")
    if getattr(module, "__version__", None) != "2.7.2":
        return unavailable_identity("INTERFACE_VERSION_MISMATCH")
    native_digest = _file_sha256(native.__file__)
    installed_digest = _installed_tree_digest(distribution)
    if (
        receipt.get("native_library_sha256") != native_digest
        or receipt.get("installed_files_sha256") != installed_digest
    ):
        return unavailable_identity("PINNED_RUNTIME_CONTENT_MISMATCH")
    return {
        "status": "available",
        "reason_code": None,
        "engine": "ViennaRNA",
        "version": version,
        "wheel_filename": expected_filename,
        "wheel_sha256": expected_sha256,
        "native_library_sha256": native_digest,
        "installed_files_sha256": installed_digest,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_abi": sys.implementation.cache_tag,
        "operating_system": target[0],
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "target_python": target[1],
    }


def write_runtime_receipt():
    """Write the receipt after a hash-verified install through the pinned lock."""
    target = _target()
    if target is None or target not in WHEEL_LOCK:
        raise RuntimeError("M11 ViennaRNA provisioning target is unsupported")
    filename, digest = WHEEL_LOCK[target]
    distribution = importlib.metadata.distribution("ViennaRNA")
    if distribution.version != "2.7.2":
        raise RuntimeError("Installed ViennaRNA version is not 2.7.2")
    native = importlib.import_module("RNA._RNA")
    receipt = {
        "schema": "satellite-discovery-m11-runtime-v1",
        "wheel_filename": filename,
        "wheel_sha256": digest,
        "target_python": target[1],
        "operating_system": target[0],
        "architecture": platform.machine(),
        "native_library_sha256": _file_sha256(native.__file__),
        "installed_files_sha256": _installed_tree_digest(distribution),
    }
    path = _receipt_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path