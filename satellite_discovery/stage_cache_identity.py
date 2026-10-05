"""Stage-owned source identity for resumable workflow cache entries.

The workflow runner and the artifact contract registry are shared, but their
entire source files are not dependencies of every stage.  This module hashes
the selected stage's imported source closure, selected contract semantics, and
small shared cache/registry interfaces instead of the whole package.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path


IDENTITY_ALGORITHM_VERSION = "stage-source-identity-v2"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_NAME = "satellite_discovery"
_SPECIAL_MODULES = {
    f"{_PACKAGE_NAME}.artifact_contracts",
    f"{_PACKAGE_NAME}.artifact_workflow",
    f"{_PACKAGE_NAME}.stage_cache_identity",
}
_RESOURCE_SUFFIXES = {".json", ".txt", ".py"}


def _canonical_digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_bytes(content):
    return content.replace(b"\r\n", b"\n")


def _newline_kind(content):
    if b"\r\n" in content:
        remainder = content.replace(b"\r\n", b"")
        if b"\n" in remainder:
            return "mixed"
        return "crlf"
    return "lf" if b"\n" in content else "lf"


def _profile(kinds):
    kinds = set(kinds)
    if not kinds:
        return "lf"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _source_file_for_module(module_name):
    module = sys.modules.get(module_name)
    filename = getattr(module, "__file__", None) if module else None
    if filename:
        path = Path(filename)
        if path.suffix in {".py", ".pyw"} and path.is_file():
            return path
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ModuleNotFoundError, ValueError):
        spec = None
    origin = getattr(spec, "origin", None) if spec else None
    if origin and origin not in {"built-in", "frozen"}:
        path = Path(origin)
        if path.suffix in {".py", ".pyw"} and path.is_file():
            return path
    return None


def _resolve_imports(module_name, tree):
    """Find literal first-party imports, including imports nested in functions."""
    resolved = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_PACKAGE_NAME + "."):
                    resolved.add(alias.name)
                elif alias.name == _PACKAGE_NAME:
                    resolved.add(_PACKAGE_NAME)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = module_name.rpartition(".")[0]
                relative = "." * node.level + (node.module or "")
                try:
                    base = importlib.util.resolve_name(relative, package)
                except (ImportError, ValueError):
                    continue
            else:
                base = node.module or ""
            if base.startswith(_PACKAGE_NAME + "."):
                resolved.add(base)
            elif base == _PACKAGE_NAME:
                for alias in node.names:
                    if alias.name != "*":
                        candidate = f"{base}.{alias.name}"
                        if _source_file_for_module(candidate):
                            resolved.add(candidate)
    return resolved


def _literal_resources(module_name, tree, module_path):
    """Capture adjacent files explicitly named by stage source code."""
    if not module_name.startswith(_PACKAGE_NAME + "."):
        return ()
    try:
        package_root = Path(importlib.import_module(_PACKAGE_NAME).__file__).parent
        module_dir = module_path.parent
    except (ImportError, TypeError):
        return ()
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"with_name", "joinpath"} or not node.args:
            continue
        argument = node.args[0]
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            continue
        name = argument.value
        if Path(name).suffix not in _RESOURCE_SUFFIXES:
            continue
        candidate = module_dir / name
        if not candidate.is_file():
            continue
        try:
            logical_name = candidate.resolve().relative_to(package_root.resolve()).as_posix()
        except ValueError:
            logical_name = f"{module_name}/{candidate.name}"
        names.add((logical_name, candidate))
    return tuple(sorted(names, key=lambda row: row[0]))


def _module_inventory(root_modules):
    pending = sorted(set(root_modules))
    visited = set()
    module_hashes = {}
    resource_hashes = {}
    newline_kinds = []

    while pending:
        module_name = pending.pop(0)
        if not isinstance(module_name, str) or not module_name:
            raise ValueError("Cache identity contains an invalid source module")
        if module_name in visited or module_name in _SPECIAL_MODULES:
            continue
        visited.add(module_name)
        source = _source_file_for_module(module_name)
        if source is None:
            if module_name.startswith(_PACKAGE_NAME + "."):
                raise ValueError(
                    f"Cache identity cannot locate trusted source module {module_name!r}"
                )
            module_hashes[module_name] = "unavailable"
            continue

        raw = source.read_bytes()
        normalized = _normalized_bytes(raw)
        newline_kinds.append(_newline_kind(raw))
        module_hashes[module_name] = hashlib.sha256(normalized).hexdigest()
        if source.suffix not in {".py", ".pyw"}:
            continue
        try:
            tree = ast.parse(normalized.decode("utf-8"), filename=module_name)
        except (UnicodeDecodeError, SyntaxError) as error:
            raise ValueError(
                f"Cache identity cannot parse trusted source module {module_name!r}"
            ) from error
        for logical_name, resource in _literal_resources(module_name, tree, source):
            resource_bytes = resource.read_bytes()
            newline_kinds.append(_newline_kind(resource_bytes))
            resource_hashes[logical_name] = hashlib.sha256(
                _normalized_bytes(resource_bytes)
            ).hexdigest()
        pending.extend(
            sorted(_resolve_imports(module_name, tree) - visited - _SPECIAL_MODULES)
        )

    return (
        [{"module": name, "sha256": digest}
         for name, digest in sorted(module_hashes.items())],
        [{"resource": name, "sha256": digest}
         for name, digest in sorted(resource_hashes.items())],
        newline_kinds,
    )


def _callable_source(callable_value):
    if inspect.ismethod(callable_value):
        callable_value = callable_value.__func__
    try:
        lines, first_line = inspect.getsourcelines(callable_value)
        source = "".join(lines)
    except (OSError, TypeError) as error:
        raise ValueError("Cache identity requires inspectable trusted callables") from error
    path = inspect.getsourcefile(callable_value)
    if not path:
        raise ValueError("Cache identity requires a source path for trusted callables")
    try:
        raw_lines = Path(path).read_bytes().splitlines(keepends=True)
        selected = b"".join(raw_lines[first_line - 1:first_line - 1 + len(lines)])
    except OSError as error:
        raise ValueError("Cache identity cannot read trusted callable source") from error
    return (
        hashlib.sha256(_normalized_bytes(source.encode("utf-8"))).hexdigest(),
        _newline_kind(selected),
    )


def _stable_capture(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError("Cache identity cannot serialize a non-finite closure value")
        return value
    if isinstance(value, types.ModuleType):
        return {"module": value.__name__}
    if inspect.isfunction(value) or inspect.ismethod(value):
        return {
            "callable": f"{value.__module__}.{value.__qualname__}",
        }
    if isinstance(value, (tuple, list)):
        return [_stable_capture(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Cache identity closure dictionaries require string keys")
        return {key: _stable_capture(value[key]) for key in sorted(value)}
    raise ValueError("Cache identity found an unsupported trusted closure value")


def _immutable_capture(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        try:
            return True, _stable_capture(value)
        except ValueError:
            return False, None
    if isinstance(value, types.ModuleType):
        return True, {"module": value.__name__}
    if inspect.isfunction(value) or inspect.ismethod(value):
        return True, {
            "callable": f"{value.__module__}.{value.__qualname__}",
        }
    if isinstance(value, tuple):
        rows = [_immutable_capture(item) for item in value]
        if all(stable for stable, _ in rows):
            return True, [captured for _, captured in rows]
    if isinstance(value, frozenset):
        rows = [_immutable_capture(item) for item in value]
        if all(stable for stable, _ in rows):
            return True, sorted(
                (captured for _, captured in rows),
                key=lambda item: json.dumps(item, sort_keys=True),
            )
    return False, None


def _callable_identity(value):
    if value is None:
        return None, ()
    source_sha, newline_kind = _callable_source(value)
    if inspect.ismethod(value):
        value = value.__func__
    closure = {}
    for name, cell in zip(value.__code__.co_freevars, value.__closure__ or ()):
        stable, captured = _immutable_capture(cell.cell_contents)
        if stable:
            closure[name] = captured
    stable_defaults, defaults = _immutable_capture(value.__defaults__ or ())
    stable_kwdefaults, kwdefaults = _immutable_capture(value.__kwdefaults__ or {})
    return {
        "module": value.__module__,
        "qualname": value.__qualname__,
        "source_sha256": source_sha,
        "defaults": defaults if stable_defaults else None,
        "kwdefaults": kwdefaults if stable_kwdefaults else None,
        "closure": closure,
    }, (newline_kind,)


def _contract_types(definition):
    types_used = set()
    for mapping in (
        getattr(definition, "input_contracts", None) or {},
        getattr(definition, "output_contracts", None) or {},
    ):
        for value in mapping.values():
            values = (value,) if isinstance(value, str) else value
            types_used.update(values)
    return tuple(sorted(types_used))


def _shared_semantics(contract_types):
    from . import artifact_contracts, artifact_workflow, stage_registry

    workflow_functions = (
        artifact_workflow._cache_contract_mapping,
        artifact_workflow._stage_cache_registration_identity,
        artifact_workflow._stage_cache_key,
    )
    workflow_sources = []
    newline_kinds = []
    for function in workflow_functions:
        source_sha, newline_kind = _callable_source(function)
        workflow_sources.append({
            "name": function.__name__,
            "sha256": source_sha,
        })
        newline_kinds.append(newline_kind)

    registry_path = Path(stage_registry.__file__)
    registry_bytes = registry_path.read_bytes()
    newline_kinds.append(_newline_kind(registry_bytes))
    registry_sha = hashlib.sha256(_normalized_bytes(registry_bytes)).hexdigest()

    contract_identity_source_sha, contract_newline = _callable_source(
        artifact_contracts.semantic_identity
    )
    newline_kinds.append(contract_newline)
    if contract_types:
        contract_identity = artifact_contracts.semantic_identity(contract_types)
    else:
        contract_identity = None
    return {
        "workflow_cache_semantics_version":
            artifact_workflow.WORKFLOW_CACHE_SEMANTICS_VERSION,
        "workflow_cache_functions": workflow_sources,
        "stage_registry_source_sha256": registry_sha,
        "contract_identity_function_sha256": contract_identity_source_sha,
        "artifact_contract_semantics": contract_identity,
    }, newline_kinds


def _handler_roots(definition):
    handler = getattr(definition, "handler", None)
    roots = set()
    explicit_roots = getattr(handler, "_cache_source_modules", ())
    roots.update(explicit_roots)
    if not explicit_roots and handler is not None:
        target = handler if inspect.isfunction(handler) or inspect.ismethod(handler) else type(handler)
        module_name = getattr(target, "__module__", None)
        if module_name:
            roots.add(module_name)
    if handler is None and getattr(definition, "module_name", None):
        roots.add(definition.module_name)
    for hook_name in ("config_validator", "dependency_inspector"):
        hook = getattr(definition, hook_name, None)
        if hook is not None:
            target = hook if inspect.isfunction(hook) or inspect.ismethod(hook) else type(hook)
            module_name = getattr(target, "__module__", None)
            if module_name:
                roots.add(module_name)
    return tuple(sorted(roots))


def _handler_descriptor(definition):
    handler = getattr(definition, "handler", None)
    if handler is None:
        return {"kind": "no-handler"}
    if inspect.isfunction(handler) or inspect.ismethod(handler):
        descriptor, _ = _callable_identity(handler)
        legacy_target = getattr(handler, "_cache_source_descriptor", None)
        if legacy_target is not None:
            descriptor["legacy_target"] = _stable_capture(legacy_target)
            from . import artifact_workflow
            factory_sha, _ = _callable_source(artifact_workflow._legacy_handler)
            descriptor["legacy_factory_source_sha256"] = factory_sha
        return {"kind": "callable", **descriptor}
    return {
        "kind": "callable-object",
        "class": f"{type(handler).__module__}.{type(handler).__qualname__}",
        "adapter_version": getattr(handler, "adapter_version", None),
    }


def identity_payload(
    stage_kind,
    source_modules,
    contract_types=(),
    *,
    semantic_version=None,
    output_schema_version=None,
    registration=None,
    handler_descriptor=None,
):
    module_rows, resource_rows, newline_kinds = _module_inventory(source_modules)
    contracts = tuple(sorted(set(contract_types)))
    shared, shared_newlines = _shared_semantics(contracts)
    newline_kinds.extend(shared_newlines)
    from . import artifact_contracts
    if contracts and any(not artifact_contracts.known_contract(name) for name in contracts):
        raise ValueError("Cache identity references an unknown artifact contract")
    payload = {
        "identity_algorithm_version": IDENTITY_ALGORITHM_VERSION,
        "stage": stage_kind,
        "semantic_version": semantic_version,
        "output_schema_version": output_schema_version,
        "registration": registration,
        "handler": handler_descriptor,
        "source_modules": module_rows,
        "source_resources": resource_rows,
        "artifact_contract_semantics": (
            artifact_contracts.semantic_identity(contracts) if contracts else None
        ),
        "shared_semantics": shared,
    }
    return payload, _profile(newline_kinds)


def stage_implementation_identity(definition, registration):
    payload, line_profile = identity_payload(
        definition.kind,
        _handler_roots(definition),
        _contract_types(definition),
        semantic_version=definition.version,
        registration=registration,
        handler_descriptor=_handler_descriptor(definition),
    )
    return _canonical_digest(payload), line_profile


def stage_source_identity(
    stage_kind,
    source_modules,
    contract_types,
    *,
    semantic_version,
    output_schema_version,
):
    payload, line_profile = identity_payload(
        stage_kind,
        source_modules,
        contract_types,
        semantic_version=semantic_version,
        output_schema_version=output_schema_version,
    )
    return _canonical_digest(payload), line_profile


def _read_identity_compatibility():
    path = Path(__file__).with_name("stage_cache_identity_compatibility.txt")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            return {}
        key, value = line.split("=", 1)
        if not key or key in values:
            return {}
        values[key] = value
    if values.get("schema") != "stage-cache-identity-compat-v1":
        return {}
    return values


def _matching_digest(values, key):
    value = values.get(key)
    return value if isinstance(value, str) and _DIGEST.fullmatch(value) else None


def legacy_package_cache_alias(stage_kind, identity_sha256, line_profile):
    """Return an exact prior package-cache digest only for a pinned baseline."""
    if not _DIGEST.fullmatch(identity_sha256) or line_profile not in {"lf", "crlf"}:
        return None
    values = _read_identity_compatibility()
    if values.get(f"stage.{stage_kind}") != identity_sha256:
        return None
    try:
        legacy_values = {}
        path = Path(__file__).with_name("m12_legacy_cache_compatibility.txt")
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in legacy_values:
                    return None
                legacy_values[key] = value
    except OSError:
        return None
    if legacy_values.get("schema") != "m12-legacy-cache-compat-v1":
        return None
    suffix = "" if line_profile == "lf" else "_crlf"
    return _matching_digest(legacy_values, f"legacy_source_sha256{suffix}")


def legacy_stage_source_identity(stage_kind, identity_sha256, line_profile):
    """Map only an exact audited M12/M13 baseline back to its public identity."""
    if not _DIGEST.fullmatch(identity_sha256) or line_profile not in {"lf", "crlf"}:
        return None
    values = _read_identity_compatibility()
    if values.get(f"source.{stage_kind}.identity_sha256") != identity_sha256:
        return None
    return _matching_digest(values, f"source.{stage_kind}.legacy_sha256_{line_profile}")
