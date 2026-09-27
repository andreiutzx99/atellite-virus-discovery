"""Same-workflow, artifact-bounded M12 review of typed M5/M6 outputs."""

import hashlib
import os
from pathlib import Path
import tempfile

from . import artifact_contracts, m12_contracts


STAGE_KIND = "m12_artifact_review"
STAGE_VERSION = "1"
OUTPUT_CONTRACTS = {
    "artifact_review_table.json": "m12_artifact_review_table",
    "summary.json": "m12_summary",
    "result_bundle.json": "m12_result_bundle",
}
OUTPUT_SCHEMA_VERSION = "m12-output-schema-v1"
CACHE_INPUT_SEMANTICS_VERSION = "m12-input-and-producer-contracts-v1"
WORKFLOW_BINDING_SEMANTICS_VERSION = "m12-exact-same-workflow-handoff-v1"
M5_STAGE_KIND = "dvg_virema"
M6_STAGE_KIND = "residual_evidence"
M12_JSON_INPUT_TYPES = frozenset({
    "dvg_evidence",
    "dvg_evidence_summary",
    "dvg_parameters",
    "residual_read_manifest",
    "read_support_evidence",
    "reconstruction_evidence",
})
REVIEW_FAILURE_STATES = frozenset({
    "UNAVAILABLE",
    "INVALID",
    "INCOMPLETE",
    "FAILED",
    "INTERRUPTED",
    "NOT_EVALUATED",
})
COMMON_LIMITATION = (
    "This artifact review does not establish biological identity, source or "
    "read origin, contamination, classification, function, helper dependence, "
    "or candidate rejection."
)
UNASSESSED_DIMENSIONS = [
    "Source and read origin were not assessed.",
    "Matched-control adequacy was not assessed.",
    "Sample-metadata interpretation was not assessed.",
    "Independent evidence was not consumed.",
    "Biological identity, contamination, classification, helper dependence, "
    "function, and candidate rejection were not assessed.",
]


def validate_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError("M12 artifact review does not accept stage configuration")
    return {}


def _source_identity():
    sources = (
        Path(__file__).resolve(),
        Path(m12_contracts.__file__).resolve(),
        Path(__file__).with_name("artifact_workflow.py").resolve(),
    )
    content = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.name):
        content.update(source.name.encode("utf-8"))
        content.update(b"\0")
        content.update(source.read_bytes())
        content.update(b"\0")
    return {
        "schema": "m12-stage-implementation-v1",
        "semantic_version": m12_contracts.SEMANTIC_VERSION,
        "source_sha256": content.hexdigest(),
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
    }


def register_stage(registry):
    input_types = sorted({
        "m12_input_manifest",
        *m12_contracts.TYPE_MILESTONE,
    })
    return registry.register(
        STAGE_KIND,
        None,
        run_stage,
        version=STAGE_VERSION,
        dynamic_inputs=True,
        config_validator=validate_config,
        input_contracts={"*": tuple(input_types)},
        output_contracts=OUTPUT_CONTRACTS,
        description=(
            "Reviews exact same-workflow M5/M6 artifact handoffs without "
            "re-running producer analysis or consuming external evidence."
        ),
    )


def _ref_key(ref):
    return (
        ref["producer_run_manifest_sha256"],
        ref["artifact_type"],
        ref["sha256"],
    )


def _sort_ref(ref):
    return (
        ref["producer_milestone"],
        ref["producer_stage_id"],
        ref["artifact_type"],
        ref["sha256"],
    )


def _stage_kind_for_milestone(kind):
    if kind == M5_STAGE_KIND:
        return "M5"
    if kind == M6_STAGE_KIND:
        return "M6"
    return None


def validate_handoff_declarations(input_manifest_path, stage, stages, definitions):
    """Require exact one-to-one typed references to earlier M5/M6 handoffs."""
    if stage.get("kind") != STAGE_KIND:
        raise ValueError("M12 handoff validation was requested for another stage")
    inputs = stage.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("M12 stage inputs are malformed")
    manifest_input = inputs.get("manifest")
    if (not isinstance(manifest_input, dict)
            or set(manifest_input) != {"path", "artifact_type"}
            or manifest_input.get("artifact_type") != "m12_input_manifest"):
        raise ValueError("M12 requires a direct typed m12_input_manifest input")
    if Path(input_manifest_path).is_symlink():
        raise ValueError("M12 input manifest must not be a symbolic link")
    manifest_value = m12_contracts.load_input_manifest(input_manifest_path)

    stage_positions = {item["id"]: index for index, item in enumerate(stages)}
    handoffs = []
    for input_name, value in inputs.items():
        if input_name == "manifest":
            continue
        if not (isinstance(value, dict) and set(value) == {"stage", "artifact"}):
            raise ValueError("M12 accepts only the direct manifest and typed stage handoffs")
        producer_id = value["stage"]
        producer_stage = next((item for item in stages if item["id"] == producer_id), None)
        definition = definitions.get(producer_id)
        if (producer_stage is None or definition is None
                or stage_positions.get(producer_id, len(stages))
                >= stage_positions[stage["id"]]):
            raise ValueError("M12 producer handoffs must reference an earlier workflow stage")
        produced = definition.output_contracts.get(value["artifact"], ())
        if isinstance(produced, str):
            produced = (produced,)
        if len(produced) != 1:
            raise ValueError("M12 producer handoff must have one exact artifact type")
        artifact_type = produced[0]
        milestone = _stage_kind_for_milestone(definition.kind)
        if (milestone is None
                or m12_contracts.TYPE_MILESTONE.get(artifact_type) != milestone):
            raise ValueError("M12 handoff is not an allowlisted M5/M6 artifact")
        handoffs.append({
            "input_name": input_name,
            "producer_stage_id": producer_id,
            "relative_path": value["artifact"],
            "artifact_type": artifact_type,
            "producer_milestone": milestone,
        })

    references = manifest_value["producer_artifacts"]
    if len(handoffs) != len(references):
        raise ValueError("M12 references and declared typed handoffs are not one-to-one")
    unused_handoffs = list(handoffs)
    bindings = []
    for ref in references:
        matches = [
            item for item in unused_handoffs
            if item["producer_stage_id"] == ref["producer_stage_id"]
            and item["relative_path"] == ref["relative_path"]
            and item["artifact_type"] == ref["artifact_type"]
            and item["producer_milestone"] == ref["producer_milestone"]
        ]
        if len(matches) != 1:
            raise ValueError(
                "Each M12 ArtifactRef must match exactly one same-workflow typed handoff"
            )
        match = matches[0]
        unused_handoffs.remove(match)
        bindings.append({**match, "artifact_ref": ref})
    if unused_handoffs:
        raise ValueError("M12 workflow declares an unlisted or extra producer handoff")
    return sorted(bindings, key=lambda item: _sort_ref(item["artifact_ref"]))


def _safe_output_root(output_root):
    root = Path(output_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Workflow output root is not a directory")
    return root


def _resolve_binding(binding, input_paths, producer_records, output_root):
    ref = binding["artifact_ref"]
    record = producer_records.get(binding["producer_stage_id"])
    if not isinstance(record, dict):
        raise ValueError("M12 producer stage record is unavailable")
    resolved = {
        "producer_stage_id": record.get("id"),
        "producer_run_manifest_sha256": None,
        "producer_status_raw": None,
        "artifact_type": binding["artifact_type"],
        "artifact_contract_version": None,
        "sha256": None,
        "available": False,
        "identity_matches": False,
        "identity_errors": [],
    }
    errors = set()
    marker = None
    stage_root = None
    try:
        relative_root = record.get("output_path")
        if not isinstance(relative_root, str) or not relative_root:
            raise OSError("Producer output path is missing")
        candidate_root = output_root / relative_root
        if candidate_root.is_symlink():
            errors.add("producer_output_path_is_symlink")
            raise OSError("Producer output path is unsafe")
        stage_root = candidate_root.resolve(strict=True)
        if not stage_root.is_relative_to(output_root):
            errors.add("producer_output_path_escapes_workflow")
            raise OSError("Producer output path escapes workflow output")
        marker = stage_root / "manifest.json"
        if marker.is_symlink() or not marker.is_file():
            raise OSError("Producer run manifest is unavailable")
        manifest_bytes = marker.read_bytes()
        actual_run_digest = hashlib.sha256(manifest_bytes).hexdigest()
        resolved["producer_run_manifest_sha256"] = actual_run_digest
        producer_manifest = m12_contracts.read_json(marker)
        raw_status = producer_manifest.get("status")
        if isinstance(raw_status, str):
            resolved["producer_status_raw"] = raw_status
        if raw_status != record.get("status"):
            errors.add("workflow_and_producer_status_mismatch")
        if raw_status != "complete":
            errors.add("producer_manifest_not_complete")
    except (OSError, ValueError, KeyError, TypeError):
        errors.add("producer_manifest_unavailable")

    artifact_path = input_paths.get(binding["input_name"])
    if stage_root is not None and artifact_path is not None:
        try:
            artifact_path = Path(artifact_path)
            if artifact_path.is_symlink():
                errors.add("artifact_is_symlink")
                raise OSError("Artifact handoff is a symbolic link")
            resolved_path = artifact_path.resolve(strict=True)
            expected_path = (stage_root / binding["relative_path"]).resolve(strict=True)
            if not resolved_path.is_relative_to(stage_root) or resolved_path != expected_path:
                errors.add("resolved_handoff_path_mismatch")
            if not resolved_path.is_file():
                raise OSError("Artifact handoff is not a regular file")
            artifact_digest = _sha256_file(resolved_path)
            resolved["sha256"] = artifact_digest
            resolved["available"] = True
            producer_manifest = m12_contracts.read_json(marker)
            output_digests = producer_manifest.get("output_sha256", {})
            if output_digests.get(binding["relative_path"]) != artifact_digest:
                errors.add("producer_output_digest_mismatch")
        except (OSError, ValueError, KeyError, TypeError):
            errors.add("artifact_unavailable")

    try:
        contract_version = artifact_contracts.semantic_identity(
            binding["artifact_type"]
        )["contracts"][binding["artifact_type"]]
        resolved["artifact_contract_version"] = contract_version
    except (ValueError, KeyError, TypeError):
        errors.add("artifact_contract_identity_unavailable")

    if resolved["producer_stage_id"] != ref["producer_stage_id"]:
        errors.add("producer_stage_id_mismatch")
    if resolved["producer_run_manifest_sha256"] != ref["producer_run_manifest_sha256"]:
        errors.add("producer_run_manifest_digest_mismatch")
    if resolved["producer_status_raw"] != ref["producer_status"]:
        errors.add("producer_status_mismatch")
    if resolved["artifact_type"] != ref["artifact_type"]:
        errors.add("artifact_type_mismatch")
    if binding["relative_path"] != ref["relative_path"]:
        errors.add("relative_path_mismatch")
    if resolved["artifact_contract_version"] != ref["artifact_contract_version"]:
        errors.add("artifact_contract_version_mismatch")
    if resolved["sha256"] != ref["sha256"]:
        errors.add("artifact_digest_mismatch")

    resolved["identity_errors"] = sorted(errors)
    resolved["identity_matches"] = not errors and resolved["available"]
    return {
        "input_name": binding["input_name"],
        "artifact_ref": ref,
        "resolved": resolved,
    }


def build_stage_context(input_paths, bindings, producer_records, output_root):
    """Build path-free cache material from exact resolved workflow records."""
    root = _safe_output_root(output_root) if bindings else None
    try:
        manifest_path = Path(input_paths["manifest"])
        manifest_path = manifest_path.resolve(strict=True)
        manifest = m12_contracts.load_input_manifest(manifest_path)
        manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError("M12 input manifest could not be verified") from error

    resolved_handoffs = (
        [
            _resolve_binding(binding, input_paths, producer_records, root)
            for binding in bindings
        ]
        if bindings else []
    )
    resolved_handoffs.sort(key=lambda item: _sort_ref(item["artifact_ref"]))
    contract_types = {"m12_input_manifest"}
    contract_types.update(ref["artifact_type"] for ref in manifest["producer_artifacts"])
    contract_semantics = artifact_contracts.semantic_identity(contract_types)
    output_contract_semantics = artifact_contracts.semantic_identity(
        OUTPUT_CONTRACTS.values()
    )
    implementation = _source_identity()
    cache_identity = {
        "schema": "m12-stage-cache-context-v1",
        "input_schema": m12_contracts.INPUT_SCHEMA,
        "semantic_version": m12_contracts.SEMANTIC_VERSION,
        "candidate_id": manifest["candidate_id"],
        "input_manifest_sha256": manifest_digest,
        "external_evidence": manifest["external_evidence"],
        "resolved_handoffs": resolved_handoffs,
        "workflow_binding_semantics_version": WORKFLOW_BINDING_SEMANTICS_VERSION,
        "contract_semantics": contract_semantics,
        "output_contract_semantics": output_contract_semantics,
        "implementation": implementation,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
    }
    return {
        "input_manifest": manifest,
        "input_manifest_sha256": manifest_digest,
        "bindings": resolved_handoffs,
        "cache_identity": cache_identity,
        "implementation": implementation,
    }


def _empty_axes(review_state="VERIFIED", execution="UNKNOWN",
                accounting="UNKNOWN", observation="UNKNOWN"):
    return {
        "review_state": review_state,
        "analysis_execution_status": execution,
        "accounting_status": accounting,
        "observation_status": observation,
    }


def _identity_failure(prepared, state="INVALID"):
    prepared["axes"] = _empty_axes(
        review_state=state,
        execution="UNKNOWN",
        accounting="UNKNOWN",
        observation="NO_OBSERVATION",
    )


def _prepare_artifacts(inputs, context):
    binding_by_key = {
        _ref_key(binding["artifact_ref"]): binding
        for binding in context["bindings"]
    }
    prepared = []
    for ref in context["input_manifest"]["producer_artifacts"]:
        binding = binding_by_key.get(_ref_key(ref))
        if binding is None:
            raise ValueError("M12 resolved handoff does not match its input reference")
        item = {
            "ref": ref,
            "binding": binding,
            "payload": None,
            "axes": _empty_axes(),
            "invalid_reason": None,
        }
        resolved = binding["resolved"]
        if not resolved["available"]:
            _identity_failure(item, "UNAVAILABLE")
            item["invalid_reason"] = "The declared artifact handoff is unavailable."
            prepared.append(item)
            continue
        if not resolved["identity_matches"]:
            _identity_failure(item)
            item["invalid_reason"] = "The declared artifact identity does not match the resolved handoff."
            prepared.append(item)
            continue
        path = inputs[binding["input_name"]]
        try:
            artifact_contracts.validate_artifact(path, ref["artifact_type"])
            if ref["artifact_type"] in M12_JSON_INPUT_TYPES:
                item["payload"] = m12_contracts.read_json(path)
        except OSError:
            _identity_failure(item, "UNAVAILABLE")
            item["invalid_reason"] = "The declared artifact could not be read."
        except (ValueError, KeyError, TypeError, UnicodeError):
            _identity_failure(item)
            item["invalid_reason"] = "The declared artifact failed its producer contract validation."
        prepared.append(item)
    _check_cross_artifact_consistency(prepared)
    return prepared


def _run_key(item):
    ref = item["ref"]
    return (
        ref["producer_milestone"],
        ref["producer_stage_id"],
        ref["producer_run_manifest_sha256"],
    )


def _group_by_run(prepared):
    groups = {}
    for item in prepared:
        groups.setdefault(_run_key(item), {}).setdefault(
            item["ref"]["artifact_type"], []
        ).append(item)
    return groups


def _invalidate_group_items(items, reason):
    for item in items:
        _identity_failure(item)
        item["invalid_reason"] = reason


def _check_cross_artifact_consistency(prepared):
    for (milestone, _, _), group in _group_by_run(prepared).items():
        if milestone == "M5":
            summaries = group.get("dvg_evidence_summary", [])
            evidence = group.get("dvg_evidence", [])
            parameters = group.get("dvg_parameters", [])
            valid_summary = [item for item in summaries if item["payload"] is not None]
            valid_evidence = [item for item in evidence if item["payload"] is not None]
            valid_parameters = [item for item in parameters if item["payload"] is not None]
            related = valid_summary + valid_evidence + valid_parameters
            if len(valid_summary) > 1 or len(valid_evidence) > 1 or len(valid_parameters) > 1:
                _invalidate_group_items(
                    related, "M5 same-run artifacts are ambiguous for consistency checks."
                )
                continue
            mismatch = False
            if valid_summary and valid_evidence:
                summary = valid_summary[0]["payload"]
                doc = valid_evidence[0]["payload"]
                mismatch = (
                    summary.get("status") != doc.get("status")
                    or summary.get("event_count") != len(doc.get("events", []))
                    or summary.get("caller") != doc.get("caller")
                )
            if valid_parameters:
                parameters_payload = valid_parameters[0]["payload"]
                reference = (
                    valid_summary[0]["payload"] if valid_summary
                    else valid_evidence[0]["payload"] if valid_evidence
                    else None
                )
                if reference is not None and parameters_payload.get("caller") != reference.get("caller"):
                    mismatch = True
            if mismatch:
                _invalidate_group_items(
                    related, "M5 summary, event, and parameter artifacts conflict."
                )

        if milestone == "M6":
            supports = group.get("read_support_evidence", [])
            reconstructions = group.get("reconstruction_evidence", [])
            valid_supports = [item for item in supports if item["payload"] is not None]
            valid_reconstructions = [
                item for item in reconstructions if item["payload"] is not None
            ]
            if len(valid_supports) > 1 or len(valid_reconstructions) > 1:
                _invalidate_group_items(
                    valid_supports + valid_reconstructions,
                    "M6 same-run read-support artifacts are ambiguous.",
                )
                continue
            if valid_supports and valid_reconstructions:
                support_status = valid_supports[0]["payload"].get("status")
                reconstruction_status = valid_reconstructions[0]["payload"].get("status")
                if (
                    reconstruction_status in {
                        "READ_SUPPORTED_ASSEMBLY",
                        "NO_SUPPORTED_ASSEMBLY",
                    }
                    and (
                        (
                            reconstruction_status == "READ_SUPPORTED_ASSEMBLY"
                            and support_status != "READ_SUPPORTED_ASSEMBLY"
                        )
                        or (
                            reconstruction_status == "NO_SUPPORTED_ASSEMBLY"
                            and support_status == "READ_SUPPORTED_ASSEMBLY"
                        )
                    )
                ):
                    _invalidate_group_items(
                        valid_supports + valid_reconstructions,
                        "M6 read-support and reconstruction statuses conflict.",
                    )


def _support_query_accounting(group, evidence):
    residual_rows = group.get("residual_read_manifest", [])
    residual_rows = [item for item in residual_rows if item["payload"] is not None]
    if len(residual_rows) != 1:
        return {"status": "UNKNOWN", "reason": "M6 input layout is not uniquely available."}
    residual = residual_rows[0]["payload"]
    source_reads = residual.get("source_reads")
    if not isinstance(source_reads, dict) or set(source_reads) not in (
        {"read1"},
        {"read1", "read2"},
    ):
        return {"status": "UNKNOWN", "reason": "M6 input layout is not established."}
    provenance = evidence.get("provenance")
    fragment_ids = (
        provenance.get("support_input_fragment_ids")
        if isinstance(provenance, dict) else None
    )
    if not isinstance(fragment_ids, list):
        return {"status": "UNKNOWN", "reason": "M6 support input identities are not retained."}
    if any(not isinstance(item, str) or not item for item in fragment_ids):
        return {"status": "INVALID", "reason": "M6 support input identities are malformed."}
    if len(fragment_ids) != len(set(fragment_ids)):
        return {"status": "INVALID", "reason": "M6 support input identities are duplicated."}
    if not fragment_ids:
        return {"status": "UNKNOWN", "reason": "No assembly-eligible support input was recorded."}
    mate_numbers = (1, 2) if "read2" in source_reads else (0,)
    expected = {(fragment_id, mate) for fragment_id in fragment_ids for mate in mate_numbers}
    records = evidence.get("read_support")
    if not isinstance(records, list):
        return {"status": "INVALID", "reason": "M6 support query records are missing."}
    observed = []
    for record in records:
        if (not isinstance(record, dict)
                or not isinstance(record.get("query_id"), str)
                or not record["query_id"]
                or isinstance(record.get("mate"), bool)
                or not isinstance(record.get("mate"), int)):
            return {"status": "INVALID", "reason": "M6 support query identity is malformed."}
        observed.append((record["query_id"], record["mate"]))
    if len(observed) != len(set(observed)):
        return {"status": "INVALID", "reason": "M6 support query identities are duplicated."}
    if set(observed) != expected:
        return {"status": "INVALID", "reason": "M6 support queries do not reconcile to declared inputs."}
    return {"status": "COMPLETE", "reason": None}


def _m5_mapping(status):
    mapping = {
        "DVG_EVIDENCE_DETECTED": ("COMPLETED", "COMPLETE", "OBSERVATION_REPORTED"),
        "NO_DVG_EVIDENCE_DETECTED": (
            "COMPLETED", "COMPLETE", "NO_SIGNAL_WITHIN_SCOPE"
        ),
        "NOT_EVALUATED": ("NOT_STARTED", "UNKNOWN", "NO_OBSERVATION"),
        "ANALYSIS_UNAVAILABLE": (
            "DEPENDENCY_UNAVAILABLE", "UNKNOWN", "NO_OBSERVATION"
        ),
        "ANALYSIS_FAILED": ("FAILED", "UNKNOWN", "NO_OBSERVATION"),
        "INVALID_RESULT": ("FAILED", "INVALID", "NO_OBSERVATION"),
    }
    return mapping.get(status, ("UNKNOWN", "UNKNOWN", "UNKNOWN"))


def _m6_support_mapping(status, accounting):
    if status == "READ_SUPPORTED_ASSEMBLY":
        if accounting == "INVALID":
            return ("UNKNOWN", "INVALID", "NO_OBSERVATION", True)
        if accounting == "COMPLETE":
            return ("COMPLETED", "COMPLETE", "OBSERVATION_REPORTED", False)
        return ("UNKNOWN", "UNKNOWN", "OBSERVATION_REPORTED", False)
    if status == "NO_SUPPORTED_ASSEMBLY":
        if accounting == "COMPLETE":
            return ("COMPLETED", "COMPLETE", "NO_SIGNAL_WITHIN_SCOPE", False)
        if accounting == "INVALID":
            return ("UNKNOWN", "INVALID", "NO_OBSERVATION", True)
        return ("UNKNOWN", "UNKNOWN", "NO_OBSERVATION", False)
    if status == "NOT_EVALUATED":
        return ("NOT_STARTED", "UNKNOWN", "NO_OBSERVATION", False)
    if status == "READ_SUPPORT_FAILED":
        return ("FAILED", "UNKNOWN", "NO_OBSERVATION", False)
    if status == "INVALID_SUPPORT_OUTPUT":
        return ("FAILED", "INVALID", "NO_OBSERVATION", False)
    return ("UNKNOWN", "UNKNOWN", "UNKNOWN", False)


def _m6_reconstruction_mapping(status, support_item, support_accounting):
    if status == "READ_SUPPORTED_ASSEMBLY":
        if (support_item is not None
                and support_item["axes"]["review_state"] == "VERIFIED"
                and support_accounting == "COMPLETE"):
            return ("COMPLETED", "COMPLETE", "OBSERVATION_REPORTED")
        return ("UNKNOWN", "UNKNOWN", "OBSERVATION_REPORTED")
    if status == "NO_SUPPORTED_ASSEMBLY":
        if support_item is None:
            return ("UNKNOWN", "UNKNOWN", "NO_OBSERVATION")
        support_status = (support_item.get("payload") or {}).get("status")
        if support_status == "NOT_EVALUATED":
            return ("NOT_STARTED", "UNKNOWN", "NO_OBSERVATION")
        if (support_status == "NO_SUPPORTED_ASSEMBLY"
                and support_accounting == "COMPLETE"
                and support_item["axes"]["review_state"] == "VERIFIED"):
            return ("COMPLETED", "COMPLETE", "NO_SIGNAL_WITHIN_SCOPE")
        return ("UNKNOWN", "UNKNOWN", "NO_OBSERVATION")
    if status == "ASSEMBLY_NOT_ATTEMPTED":
        return ("NOT_STARTED", "UNKNOWN", "NO_OBSERVATION")
    if status == "DEPENDENCY_UNAVAILABLE":
        return ("DEPENDENCY_UNAVAILABLE", "UNKNOWN", "NO_OBSERVATION")
    if status in {
        "EXECUTION_FAILED",
        "READ_SUPPORT_FAILED",
        "INVALID_OUTPUT",
        "INVALID_SUPPORT_OUTPUT",
    }:
        accounting = "INVALID" if status in {"INVALID_OUTPUT", "INVALID_SUPPORT_OUTPUT"} else "UNKNOWN"
        return ("FAILED", accounting, "NO_OBSERVATION")
    if status == "INTERRUPTED":
        return ("INTERRUPTED", "UNKNOWN", "NO_OBSERVATION")
    return ("UNKNOWN", "UNKNOWN", "UNKNOWN")


def _scope_for(item, payload):
    ref = item["ref"]
    scope = {
        "producer_milestone": ref["producer_milestone"],
        "producer_stage_id": ref["producer_stage_id"],
        "artifact_type": ref["artifact_type"],
        "relative_path": ref["relative_path"],
    }
    if ref["artifact_type"] == "dvg_evidence_summary" and isinstance(payload, dict):
        scope["method"] = "M5 configured DVG caller"
        if isinstance(payload.get("caller"), str):
            scope["caller"] = payload["caller"]
    elif ref["artifact_type"] in {"dvg_evidence", "dvg_raw_output"}:
        scope["method"] = "M5 configured DVG caller"
    elif ref["artifact_type"] == "residual_read_manifest":
        scope["method"] = "M6 configured reference screen"
        if isinstance(payload, dict):
            comparison = payload.get("comparison")
            if isinstance(comparison, dict) and isinstance(comparison.get("scope"), str):
                scope["declared_scope"] = comparison["scope"]
    elif ref["artifact_type"] in {
        "read_support_evidence",
        "read_support_table",
        "reconstruction_evidence",
    }:
        scope["method"] = "M6 read-support assessment"
    elif ref["artifact_type"] == "read_triage_table":
        scope["method"] = "M6 technical read triage"
    elif ref["artifact_type"] == "read_alignment_sam":
        scope["method"] = "M6 retained alignment output; not reinterpreted"
    elif ref["artifact_type"] == "m8_candidate_sequence_set":
        scope["method"] = "M6 candidate identity handoff"
    elif ref["artifact_type"] == "dvg_parameters":
        scope["method"] = "M5 caller configuration and provenance"
    return scope


def _limitations_for(item, axes):
    ref = item["ref"]
    limitations = [COMMON_LIMITATION]
    artifact_type = ref["artifact_type"]
    if axes["observation_status"] == "NO_SIGNAL_WITHIN_SCOPE":
        if artifact_type in {"dvg_evidence", "dvg_evidence_summary"}:
            limitations.append(
                "No DVG evidence was reported by the named M5 caller within its configured scope; "
                "this is not a biological negative."
            )
        elif artifact_type == "residual_read_manifest":
            limitations.append(
                "The residual count applies only to the declared M6 reference screen and settings."
            )
        elif artifact_type in {"read_support_evidence", "reconstruction_evidence"}:
            limitations.append(
                "No contig met the completed M6 read-support criteria for the declared eligible reads."
            )
    if artifact_type in {
        "read_support_evidence",
        "read_support_table",
        "reconstruction_evidence",
    }:
        limitations.append(
            "M6 read-back uses assembly-eligible reads and is not independent confirmation."
        )
    if artifact_type in {"read_triage_table", "read_alignment_sam", "read_support_table"}:
        limitations.append(
            "Per-read or raw alignment records were not scanned to create an aggregate observation."
        )
    return limitations


def _group_context(prepared):
    groups = _group_by_run(prepared)
    group_by_ref = {}
    for group in groups.values():
        for artifact_items in group.values():
            for item in artifact_items:
                group_by_ref[_ref_key(item["ref"])] = group
    return groups, group_by_ref


def _map_item(item, group, group_by_ref):
    ref = item["ref"]
    artifact_type = ref["artifact_type"]
    payload = item["payload"]
    if item["axes"]["review_state"] != "VERIFIED":
        return

    if artifact_type in {"dvg_evidence", "dvg_evidence_summary"}:
        status = payload.get("status") if isinstance(payload, dict) else None
        execution, accounting, observation = _m5_mapping(status)
        item["axes"].update(
            analysis_execution_status=execution,
            accounting_status=accounting,
            observation_status=observation,
        )
        return

    if artifact_type == "dvg_raw_output":
        summaries = group.get("dvg_evidence_summary", [])
        summary = next(
            (candidate for candidate in summaries
             if candidate["axes"]["review_state"] == "VERIFIED"
             and candidate.get("payload") is not None),
            None,
        )
        if summary is not None:
            execution, accounting, _ = _m5_mapping(summary["payload"].get("status"))
            item["axes"].update(
                analysis_execution_status=execution,
                accounting_status=accounting,
                observation_status="NOT_APPLICABLE",
            )
        else:
            item["axes"].update(
                analysis_execution_status="UNKNOWN",
                accounting_status="UNKNOWN",
                observation_status="NOT_APPLICABLE",
            )
        return

    if artifact_type == "dvg_parameters":
        item["axes"].update(
            analysis_execution_status="NOT_APPLICABLE",
            accounting_status="NOT_APPLICABLE",
            observation_status="NOT_APPLICABLE",
        )
        return

    if artifact_type == "residual_read_manifest":
        comparison = payload.get("comparison") if isinstance(payload, dict) else None
        counts = payload.get("counts") if isinstance(payload, dict) else None
        if not isinstance(comparison, dict) or not isinstance(counts, dict):
            _identity_failure(item)
            item["invalid_reason"] = "M6 residual comparison accounting is missing."
            return
        input_count = comparison.get("input_read_count")
        accounted_count = comparison.get("accounted_read_count")
        residual_count = counts.get("residual_fragments")
        if (comparison.get("status") != "complete"
                or isinstance(input_count, bool) or not isinstance(input_count, int)
                or input_count < 1 or isinstance(accounted_count, bool)
                or not isinstance(accounted_count, int)
                or accounted_count != input_count):
            item["axes"].update(
                analysis_execution_status="COMPLETED",
                accounting_status="INCOMPLETE",
                observation_status="NO_OBSERVATION",
            )
            item["axes"]["review_state"] = "INCOMPLETE"
            return
        if (isinstance(residual_count, bool) or not isinstance(residual_count, int)
                or residual_count < 0):
            _identity_failure(item)
            item["invalid_reason"] = "M6 residual fragment accounting is malformed."
            return
        item["axes"].update(
            analysis_execution_status="COMPLETED",
            accounting_status="COMPLETE",
            observation_status=(
                "NO_SIGNAL_WITHIN_SCOPE" if residual_count == 0
                else "OBSERVATION_REPORTED"
            ),
        )
        return

    if artifact_type == "read_support_evidence":
        accounting_result = _support_query_accounting(group, payload)
        status = payload.get("status")
        execution, accounting, observation, invalidate = _m6_support_mapping(
            status, accounting_result["status"]
        )
        if accounting_result["status"] == "INVALID":
            invalidate = True
        if invalidate:
            _identity_failure(item)
            item["invalid_reason"] = accounting_result.get("reason") or (
                "M6 read-support accounting is inconsistent."
            )
            return
        item["axes"].update(
            analysis_execution_status=execution,
            accounting_status=accounting,
            observation_status=observation,
        )
        if status == "NOT_EVALUATED" and not payload.get("read_support"):
            item["axes"]["observation_status"] = "NO_OBSERVATION"
        return

    if artifact_type == "reconstruction_evidence":
        support_items = group.get("read_support_evidence", [])
        support_item = next(
            (
                candidate for candidate in support_items
                if candidate["axes"]["review_state"] == "VERIFIED"
            ),
            None,
        )
        support_accounting = "UNKNOWN"
        if support_item is not None and support_item.get("payload") is not None:
            support_accounting = _support_query_accounting(
                group, support_item["payload"]
            )["status"]
        execution, accounting, observation = _m6_reconstruction_mapping(
            payload.get("status"), support_item, support_accounting
        )
        item["axes"].update(
            analysis_execution_status=execution,
            accounting_status=accounting,
            observation_status=observation,
        )
        return

    if artifact_type == "read_support_table":
        support_items = group.get("read_support_evidence", [])
        support_item = next(
            (
                candidate for candidate in support_items
                if candidate["axes"]["review_state"] == "VERIFIED"
            ),
            None,
        )
        if support_item is not None:
            account = _support_query_accounting(
                group, support_item["payload"]
            )["status"]
            execution, accounting, _, invalid = _m6_support_mapping(
                support_item["payload"].get("status"), account
            )
            if not invalid:
                item["axes"].update(
                    analysis_execution_status=execution,
                    accounting_status=accounting,
                    observation_status="NOT_APPLICABLE",
                )
                return
        item["axes"].update(
            analysis_execution_status="UNKNOWN",
            accounting_status="UNKNOWN",
            observation_status="NOT_APPLICABLE",
        )
        return

    if artifact_type in {"read_triage_table", "read_alignment_sam"}:
        item["axes"].update(
            analysis_execution_status="UNKNOWN",
            accounting_status="UNKNOWN",
            observation_status="NOT_APPLICABLE",
        )
        return

    if artifact_type == "m8_candidate_sequence_set":
        item["axes"].update(
            analysis_execution_status="NOT_APPLICABLE",
            accounting_status="NOT_APPLICABLE",
            observation_status="NOT_APPLICABLE",
        )
        return

    item["axes"].update(
        analysis_execution_status="UNKNOWN",
        accounting_status="UNKNOWN",
        observation_status="UNKNOWN",
    )


def _dependencies_for(ref, all_refs):
    if ref["producer_milestone"] != "M6":
        return []
    linked_types = {
        "read_support_evidence",
        "read_support_table",
        "reconstruction_evidence",
    }
    if ref["artifact_type"] not in linked_types:
        return []
    related = [
        other for other in all_refs
        if other["producer_stage_id"] == ref["producer_stage_id"]
        and other["producer_run_manifest_sha256"] == ref["producer_run_manifest_sha256"]
        and other["artifact_type"] in linked_types
        and _ref_key(other) != _ref_key(ref)
    ]
    return [
        {
            "artifact_ref": other,
            "relation": "SHARES_ASSEMBLY_ELIGIBLE_READS",
            "note": (
                "These M6 read-back outputs reuse assembly-eligible reads and "
                "are not independent confirmation."
            ),
        }
        for other in sorted(related, key=_sort_ref)
    ]


def _review_rows(prepared, candidate_id):
    _, group_by_ref = _group_context(prepared)
    refs = [item["ref"] for item in prepared]
    rows = []
    for item in prepared:
        group = group_by_ref[_ref_key(item["ref"])]
        _map_item(item, group, group_by_ref)
        ref = item["ref"]
        rows.append({
            "candidate_id": candidate_id,
            "artifact_ref": ref,
            "review_state": item["axes"]["review_state"],
            "producer_status_raw": (
                item["binding"]["resolved"]["producer_status_raw"]
                if item["binding"]["resolved"]["producer_status_raw"] is not None
                else ref["producer_status"]
            ),
            "scope": _scope_for(item, item["payload"]),
            "analysis_execution_status": item["axes"]["analysis_execution_status"],
            "accounting_status": item["axes"]["accounting_status"],
            "observation_status": item["axes"]["observation_status"],
            "limitations": _limitations_for(item, item["axes"]),
            "dependency_refs": _dependencies_for(ref, refs),
        })
    rows.sort(key=lambda row: (
        row["candidate_id"],
        row["artifact_ref"]["producer_milestone"],
        row["artifact_ref"]["producer_stage_id"],
        row["artifact_ref"]["artifact_type"],
        row["artifact_ref"]["sha256"],
    ))
    return rows


def _make_summary(manifest, rows):
    producer_counts = {"M5": 0, "M6": 0}
    review_counts = {state: 0 for state in sorted(m12_contracts.REVIEW_STATES)}
    for row in rows:
        producer_counts[row["artifact_ref"]["producer_milestone"]] += 1
        review_counts[row["review_state"]] += 1
    if not rows:
        completeness = "NOT_EVALUATED"
    elif any(row["review_state"] in REVIEW_FAILURE_STATES for row in rows):
        completeness = "PARTIAL"
    else:
        completeness = "COMPLETE_WITHIN_SUPPLIED_ARTIFACT_SCOPE"
    return {
        "schema": m12_contracts.SUMMARY_SCHEMA,
        "candidate_id": manifest["candidate_id"],
        "external_evidence": manifest["external_evidence"],
        "artifact_counts": {
            "by_producer_milestone": producer_counts,
            "by_review_state": review_counts,
        },
        "review_completeness": completeness,
        "unassessed_dimensions": list(UNASSESSED_DIMENSIONS),
        "biological_conclusion": "NONE",
    }


def _bundle_handoffs(context):
    return [
        {
            "artifact_ref": binding["artifact_ref"],
            "resolved": binding["resolved"],
        }
        for binding in context["bindings"]
    ]


def _output_identity(output, identity):
    if output.is_symlink():
        return None
    marker = output / "manifest.json"
    if marker.is_symlink() or not marker.is_file():
        return None
    try:
        value = m12_contracts.read_json(marker)
        if (value.get("schema") != "m12-stage-manifest-v1"
                or value.get("status") != "complete"
                or value.get("identity") != identity
                or not isinstance(value.get("output_sha256"), dict)):
            return None
        expected_names = set(OUTPUT_CONTRACTS)
        if set(value["output_sha256"]) != expected_names:
            return None
        actual_names = {path.name for path in output.iterdir()}
        if actual_names != expected_names | {"manifest.json"}:
            return None
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            path = output / name
            if path.is_symlink() or not path.is_file():
                return None
            if _sha256_file(path) != value["output_sha256"].get(name):
                return None
            artifact_contracts.validate_artifact(path, artifact_type)
        bundle = m12_contracts.read_json(output / "result_bundle.json")
        table = m12_contracts.read_json(output / "artifact_review_table.json")
        summary = m12_contracts.read_json(output / "summary.json")
        if any(row["candidate_id"] != identity["candidate_id"] for row in table):
            return None
        expected_handoffs = identity["resolved_handoffs"]
        if [row["artifact_ref"] for row in table] != [
            item["artifact_ref"] for item in expected_handoffs
        ]:
            return None
        for row, handoff in zip(table, expected_handoffs):
            resolved = handoff["resolved"]
            if (resolved["producer_status_raw"] is not None
                    and row["producer_status_raw"] != resolved["producer_status_raw"]):
                return None
            if (not resolved["identity_matches"]
                    and row["review_state"] not in {"INVALID", "UNAVAILABLE"}):
                return None
        expected_summary = _make_summary({
            "candidate_id": identity["candidate_id"],
            "external_evidence": identity["external_evidence"],
        }, table)
        if summary != expected_summary:
            return None
        if (
            bundle["candidate_id"] != identity["candidate_id"]
            or bundle["input_manifest_sha256"] != identity["input_manifest_sha256"]
            or bundle["implementation_source_sha256"]
            != identity["implementation"]["source_sha256"]
            or bundle["resolved_handoffs"] != identity["resolved_handoffs"]
            or bundle["external_evidence"] != identity["external_evidence"]
        ):
            return None
        for name in ("artifact_review_table.json", "summary.json"):
            if bundle["outputs"][OUTPUT_CONTRACTS[name]]["sha256"] != value["output_sha256"][name]:
                return None
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_stage(inputs, output, config, *, workflow_context=None):
    validate_config(config)
    if not isinstance(workflow_context, dict):
        raise ValueError("M12 requires resolved same-workflow producer context")
    manifest = m12_contracts.validate_input_manifest(
        workflow_context.get("input_manifest")
    )
    manifest_path = Path(inputs["manifest"])
    input_digest = _sha256_file(manifest_path)
    if input_digest != workflow_context.get("input_manifest_sha256"):
        raise ValueError("M12 input manifest changed during stage execution")

    identity = workflow_context["cache_identity"]
    existing = _output_identity(Path(output), identity)
    if existing is not None:
        return existing
    output = Path(output)
    if output.is_symlink():
        raise ValueError("M12 stage output must not be a symbolic link")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Existing M12 stage output is partial, changed, or unverified")

    prepared = _prepare_artifacts(inputs, workflow_context)
    rows = _review_rows(prepared, manifest["candidate_id"])
    summary = _make_summary(manifest, rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m12-stage-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        table_path = temporary / "artifact_review_table.json"
        summary_path = temporary / "summary.json"
        bundle_path = temporary / "result_bundle.json"
        m12_contracts.write_json(table_path, rows)
        m12_contracts.write_json(summary_path, summary)
        output_digests = {
            "artifact_review_table.json": _sha256_file(table_path),
            "summary.json": _sha256_file(summary_path),
        }
        bundle = {
            "schema": m12_contracts.RESULT_BUNDLE_SCHEMA,
            "input_schema": m12_contracts.INPUT_SCHEMA,
            "semantic_version": m12_contracts.SEMANTIC_VERSION,
            "candidate_id": manifest["candidate_id"],
            "input_manifest_sha256": input_digest,
            "implementation_source_sha256": workflow_context["implementation"]["source_sha256"],
            "resolved_handoffs": _bundle_handoffs(workflow_context),
            "external_evidence": manifest["external_evidence"],
            "outputs": {
                "m12_artifact_review_table": {
                    "artifact_type": "m12_artifact_review_table",
                    "artifact_contract_version": m12_contracts.OUTPUT_CONTRACT_VERSION,
                    "sha256": output_digests["artifact_review_table.json"],
                },
                "m12_summary": {
                    "artifact_type": "m12_summary",
                    "artifact_contract_version": m12_contracts.OUTPUT_CONTRACT_VERSION,
                    "sha256": output_digests["summary.json"],
                },
            },
            "biological_conclusion": "NONE",
        }
        m12_contracts.write_json(bundle_path, bundle)
        stage_outputs = {
            name: _sha256_file(temporary / name)
            for name in sorted(OUTPUT_CONTRACTS)
        }
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(temporary / name, artifact_type)
        stage_manifest = {
            "schema": "m12-stage-manifest-v1",
            "status": "complete",
            "identity": identity,
            "output_sha256": stage_outputs,
        }
        m12_contracts.write_json(temporary / "manifest.json", stage_manifest)
        for name in set(OUTPUT_CONTRACTS) | {"manifest.json"}:
            if (temporary / name).is_symlink() or not (temporary / name).is_file():
                raise ValueError("M12 failed to create a regular output artifact")
        if output.exists():
            if any(output.iterdir()):
                raise ValueError("M12 output directory became occupied during execution")
            output.rmdir()
        os.replace(temporary, output)
    return stage_manifest


run_stage.cache_implementation_identity = _source_identity
run_stage.cache_input_contract_semantics = True
run_stage.cache_input_contract_semantics_version = CACHE_INPUT_SEMANTICS_VERSION
