"""Versioned, non-scientific terminal outcomes for M5 DVG workflow stages."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from . import dvg_evidence
from .workflow_states import WORKFLOW_TRANSITIONS


SCHEMA = 'm5-execution-outcome-v1'
OUTCOME_CODES = frozenset({
    'COMPLETED_EVENTS',
    'COMPLETED_ZERO',
    'NOT_STARTED',
    'UNAVAILABLE',
    'FAILED',
    'INTERRUPTED',
    'INCOMPLETE_OUTPUT',
    'INVALID_OUTPUT',
})
INCOMPLETE_FAILURE_CODES = frozenset({
    dvg_evidence.TRUNCATED_OUTPUT,
    dvg_evidence.INCOMPLETE_ACCOUNTING,
})
_HASH = re.compile(r'^[0-9a-f]{64}$')
_STAGE_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
_TERMINAL_WORKFLOW_STATES = frozenset(
    state for state, transitions in WORKFLOW_TRANSITIONS.items() if not transitions
)
_RECORD_FIELDS = frozenset({
    'schema',
    'workflow_id',
    'workflow_configuration_sha256',
    'producer_stage_id',
    'producer_stage_kind',
    'workflow_manifest_sha256',
    'producer_execution_status_raw',
    'producer_status_raw',
    'outcome_code',
})
_WORKFLOW_REF_FIELDS = frozenset({'path', 'sha256', 'workflow_id'})
_OUTCOME_REF_FIELDS = frozenset({'path', 'sha256', 'schema'})


class ExecutionOutcomeUnavailableError(OSError):
    """An explicitly referenced workflow or outcome record cannot be read."""


class ExecutionOutcomeIncompleteError(ValueError):
    """The referenced workflow is not terminal, so it has no final outcome."""

    def __init__(self, message, *, workflow=None):
        super().__init__(message)
        # A digest- and schema-verified workflow snapshot can still establish
        # its exact raw stage state even though no terminal outcome exists.
        self.workflow = workflow


class ExecutionOutcomeInvalidError(ValueError):
    """A readable outcome handoff has invalid structure, identity, or integrity."""


def _valid_hash(value):
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


def _raw_m5_status(workflow, stage):
    row = stage.get('dvg_evidence')
    if isinstance(row, dict) and isinstance(row.get('status'), str):
        return row['status']
    evaluations = workflow.get('dvg_evaluations')
    if isinstance(evaluations, dict):
        row = evaluations.get(stage.get('id'))
        if isinstance(row, dict) and isinstance(row.get('status'), str):
            return row['status']

    state = stage.get('status')
    if state in {'pending', 'skipped'}:
        return dvg_evidence.NOT_EVALUATED
    if state in {'dependency_missing', 'external_module_required'}:
        return dvg_evidence.ANALYSIS_UNAVAILABLE
    if state in {'failed', 'interrupted'}:
        if stage.get('error_type') == 'InvalidDVGResultError':
            return dvg_evidence.INVALID_RESULT
        return dvg_evidence.ANALYSIS_FAILED
    if state == 'complete':
        # A completed DVG stage without a valid evidence projection is not a
        # completed zero or event result.
        return dvg_evidence.INVALID_RESULT
    raise ExecutionOutcomeInvalidError(
        f"Unsupported producer stage state: {state!r}"
    )


def classify_outcome(stage_status, m5_status, failure_code=None):
    """Map unchanged M1/M5 raw statuses to the frozen outcome vocabulary."""
    if stage_status in {'pending', 'skipped'}:
        if m5_status != dvg_evidence.NOT_EVALUATED:
            raise ExecutionOutcomeInvalidError(
                'A pending or skipped M5 stage must remain NOT_EVALUATED'
            )
        return 'NOT_STARTED'
    if stage_status in {'dependency_missing', 'external_module_required'}:
        if m5_status != dvg_evidence.ANALYSIS_UNAVAILABLE:
            raise ExecutionOutcomeInvalidError(
                'An unavailable M5 stage must remain ANALYSIS_UNAVAILABLE'
            )
        return 'UNAVAILABLE'
    if stage_status == 'interrupted':
        if m5_status not in {
            dvg_evidence.ANALYSIS_FAILED,
            dvg_evidence.INVALID_RESULT,
        }:
            raise ExecutionOutcomeInvalidError(
                'An interrupted M5 stage has an inconsistent evidence status'
            )
        return 'INTERRUPTED'
    if stage_status == 'failed':
        if m5_status == dvg_evidence.ANALYSIS_FAILED:
            return 'FAILED'
        if m5_status != dvg_evidence.INVALID_RESULT:
            raise ExecutionOutcomeInvalidError(
                'A failed M5 stage has an inconsistent evidence status'
            )
    elif stage_status == 'complete':
        if m5_status == dvg_evidence.DVG_EVIDENCE_DETECTED:
            return 'COMPLETED_EVENTS'
        if m5_status == dvg_evidence.NO_DVG_EVIDENCE_DETECTED:
            return 'COMPLETED_ZERO'
        if m5_status != dvg_evidence.INVALID_RESULT:
            raise ExecutionOutcomeInvalidError(
                'A completed M5 stage has no valid completed evidence status'
            )
    else:
        raise ExecutionOutcomeInvalidError(
            f"Unsupported terminal producer stage state: {stage_status!r}"
        )

    if failure_code is None:
        failure_code = dvg_evidence.UNCLASSIFIED_INVALID_RESULT
    if failure_code not in dvg_evidence.M5_FAILURE_CODES:
        raise ExecutionOutcomeInvalidError(
            f"Unsupported M5 failure code: {failure_code!r}"
        )
    if failure_code in INCOMPLETE_FAILURE_CODES:
        return 'INCOMPLETE_OUTPUT'
    return 'INVALID_OUTPUT'


def validate_record(record):
    """Validate a v1 record and its raw-status/outcome consistency."""
    if not isinstance(record, dict):
        raise ExecutionOutcomeInvalidError('Execution outcome must be an object')
    allowed = _RECORD_FIELDS | {'failure_code'}
    if set(record) - allowed or not _RECORD_FIELDS <= set(record):
        raise ExecutionOutcomeInvalidError('Execution outcome fields are invalid')
    if record.get('schema') != SCHEMA:
        raise ExecutionOutcomeInvalidError('Execution outcome schema is invalid')
    if not isinstance(record.get('workflow_id'), str) or not record['workflow_id']:
        raise ExecutionOutcomeInvalidError('Execution outcome requires a workflow ID')
    if not _valid_hash(record.get('workflow_configuration_sha256')):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome configuration digest is invalid'
        )
    if not _valid_hash(record.get('workflow_manifest_sha256')):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome workflow-manifest digest is invalid'
        )
    if not isinstance(record.get('producer_stage_id'), str) or not _STAGE_ID.fullmatch(
        record['producer_stage_id']
    ):
        raise ExecutionOutcomeInvalidError('Execution outcome stage ID is invalid')
    if not isinstance(record.get('producer_stage_kind'), str) or not record[
        'producer_stage_kind'
    ]:
        raise ExecutionOutcomeInvalidError('Execution outcome stage kind is invalid')
    stage_status = record.get('producer_execution_status_raw')
    m5_status = record.get('producer_status_raw')
    if not isinstance(stage_status, str) or stage_status not in {
        'pending', 'running', 'complete', 'skipped', 'dependency_missing',
        'external_module_required', 'failed', 'interrupted',
    }:
        raise ExecutionOutcomeInvalidError('Execution outcome M1 status is invalid')
    if not isinstance(m5_status, str) or m5_status not in dvg_evidence._STATUSES:
        raise ExecutionOutcomeInvalidError('Execution outcome M5 status is invalid')
    failure_code = record.get('failure_code')
    if m5_status == dvg_evidence.INVALID_RESULT:
        if failure_code not in dvg_evidence.M5_FAILURE_CODES:
            raise ExecutionOutcomeInvalidError(
                'INVALID_RESULT requires a stable M5 failure code'
            )
    elif 'failure_code' in record:
        raise ExecutionOutcomeInvalidError(
            'failure_code is only valid for an INVALID_RESULT'
        )
    expected = classify_outcome(stage_status, m5_status, failure_code)
    if record.get('outcome_code') not in OUTCOME_CODES:
        raise ExecutionOutcomeInvalidError('Execution outcome code is invalid')
    if record['outcome_code'] != expected:
        raise ExecutionOutcomeInvalidError(
            'Execution outcome code does not match the raw producer statuses'
        )
    return record


def build_record(workflow, stage, workflow_manifest_sha256, failure_code=None):
    """Create a record from final workflow data without changing that manifest."""
    if not isinstance(workflow, dict) or not isinstance(stage, dict):
        raise ExecutionOutcomeInvalidError('Workflow and stage must be objects')
    workflow_id = workflow.get('workflow_id')
    configuration_sha256 = workflow.get('configuration_sha256')
    stage_id = stage.get('id')
    stage_kind = stage.get('kind')
    stage_status = stage.get('status')
    if not isinstance(workflow_id, str) or not workflow_id:
        raise ExecutionOutcomeInvalidError('Workflow manifest has no workflow ID')
    if not _valid_hash(configuration_sha256):
        raise ExecutionOutcomeInvalidError(
            'Workflow manifest has no valid configuration digest'
        )
    if not _valid_hash(workflow_manifest_sha256):
        raise ExecutionOutcomeInvalidError('Workflow manifest digest is invalid')
    m5_status = _raw_m5_status(workflow, stage)
    if m5_status == dvg_evidence.INVALID_RESULT and failure_code is None:
        failure_code = dvg_evidence.UNCLASSIFIED_INVALID_RESULT
    record = {
        'schema': SCHEMA,
        'workflow_id': workflow_id,
        'workflow_configuration_sha256': configuration_sha256,
        'producer_stage_id': stage_id,
        'producer_stage_kind': stage_kind,
        'workflow_manifest_sha256': workflow_manifest_sha256,
        'producer_execution_status_raw': stage_status,
        'producer_status_raw': m5_status,
        'outcome_code': classify_outcome(stage_status, m5_status, failure_code),
    }
    if m5_status == dvg_evidence.INVALID_RESULT:
        record['failure_code'] = failure_code
    return validate_record(record)


def serialize_record(record):
    """Return stable UTF-8 JSON bytes independent of host newline conventions."""
    validate_record(record)
    return (
        json.dumps(
            record,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
            allow_nan=False,
        )
        + '\n'
    ).encode('utf-8')


def _read_internal_manifest(path):
    try:
        info = path.lstat()
    except OSError as error:
        raise ExecutionOutcomeUnavailableError(
            'Final workflow.json is missing or unreadable'
        ) from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ExecutionOutcomeInvalidError(
            'Final workflow.json must be a regular non-symlink file'
        )
    try:
        contents = path.read_bytes()
        value = json.loads(contents.decode('utf-8'))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ExecutionOutcomeInvalidError(
            'Final workflow.json is unreadable or malformed'
        ) from error
    if not isinstance(value, dict):
        raise ExecutionOutcomeInvalidError('Final workflow.json must be an object')
    return contents, value


def _write_record(path, record):
    parent = path.parent
    try:
        parent_info = parent.lstat()
    except FileNotFoundError:
        parent.mkdir()
        parent_info = parent.lstat()
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome directory must be a regular directory'
        )
    try:
        target_info = path.lstat()
    except FileNotFoundError:
        target_info = None
    if target_info is not None and (
        stat.S_ISLNK(target_info.st_mode) or not stat.S_ISREG(target_info.st_mode)
    ):
        raise ExecutionOutcomeInvalidError(
            'Existing execution outcome must be a regular non-symlink file'
        )

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', dir=parent, prefix=f'.{path.stem}.', suffix='.tmp',
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(serialize_record(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def write_final_outcomes(output, dvg_module_names=(), failure_codes=None):
    """Write one sidecar per known M5 DVG stage after a terminal manifest write."""
    output = Path(output)
    manifest_path = output / 'workflow.json'
    manifest_bytes, workflow = _read_internal_manifest(manifest_path)
    workflow_status = workflow.get('status')
    if workflow_status not in WORKFLOW_TRANSITIONS:
        raise ExecutionOutcomeInvalidError('Workflow manifest status is invalid')
    if workflow_status not in _TERMINAL_WORKFLOW_STATES:
        return []

    stages = workflow.get('stages')
    if not isinstance(stages, list):
        raise ExecutionOutcomeInvalidError('Workflow manifest stages are invalid')
    ids = [stage.get('id') for stage in stages if isinstance(stage, dict)]
    if len(ids) != len(stages) or len(set(ids)) != len(ids):
        raise ExecutionOutcomeInvalidError(
            'Workflow manifest stage IDs are malformed or duplicated'
        )
    module_names = set(dvg_module_names)
    failure_codes = failure_codes or {}
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    records = []
    for stage in stages:
        is_dvg = (
            stage.get('evidence_family') == 'dvg'
            or (
                stage.get('kind') == 'external_module'
                and stage.get('module') in module_names
            )
        )
        if not is_dvg:
            continue
        stage_id = stage.get('id')
        if not isinstance(stage_id, str) or not _STAGE_ID.fullmatch(stage_id):
            raise ExecutionOutcomeInvalidError('M5 stage ID is not portable')
        record = build_record(
            workflow,
            stage,
            manifest_sha256,
            failure_code=failure_codes.get(stage_id),
        )
        records.append((stage_id, record))

    if not records:
        return []
    destination = output / 'execution-outcomes'
    try:
        directory_info = destination.lstat()
    except FileNotFoundError:
        directory_info = None
    if directory_info is not None and (
        stat.S_ISLNK(directory_info.st_mode) or not stat.S_ISDIR(directory_info.st_mode)
    ):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome path must be a regular directory'
        )
    written = []
    for stage_id, record in records:
        path = destination / f'{stage_id}.json'
        _write_record(path, record)
        written.append(path.relative_to(output).as_posix())
    return written


def _read_explicit_reference(root, relative_path):
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or '\\' in relative_path
        or relative_path.startswith('/')
        or re.match(r'^[A-Za-z]:', relative_path)
    ):
        raise ExecutionOutcomeInvalidError('Referenced path is not normalized and relative')
    posix_path = PurePosixPath(relative_path)
    if (
        str(posix_path) != relative_path
        or not posix_path.parts
        or any(part in {'', '.', '..'} for part in posix_path.parts)
    ):
        raise ExecutionOutcomeInvalidError('Referenced path is not normalized and relative')
    current = root
    for index, part in enumerate(posix_path.parts):
        current = current / part
        try:
            info = current.lstat()
        except OSError as error:
            raise ExecutionOutcomeUnavailableError(
                'Explicitly referenced file is missing or unreadable'
            ) from error
        if stat.S_ISLNK(info.st_mode):
            raise ExecutionOutcomeInvalidError(
                'Explicitly referenced files must not be symbolic links'
            )
        final = index == len(posix_path.parts) - 1
        if final and not stat.S_ISREG(info.st_mode):
            raise ExecutionOutcomeInvalidError(
                'Explicitly referenced file must be a regular file'
            )
        if not final and not stat.S_ISDIR(info.st_mode):
            raise ExecutionOutcomeInvalidError(
                'Referenced parent path must be a regular directory'
            )
    try:
        return current.read_bytes()
    except OSError as error:
        raise ExecutionOutcomeUnavailableError(
            'Explicitly referenced file is missing or unreadable'
        ) from error


def _parse_reference_json(contents, label):
    try:
        value = json.loads(contents.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as error:
        raise ExecutionOutcomeInvalidError(
            f'{label} is readable but not valid JSON'
        ) from error
    if not isinstance(value, dict):
        raise ExecutionOutcomeInvalidError(f'{label} must contain a JSON object')
    return value


def verify_execution_outcome_refs(
    input_manifest_path,
    producer_workflow_ref,
    execution_record_ref,
    *,
    expected_stage_id=None,
):
    """Verify explicit M13 handoff refs without discovering or scanning paths.

    This is a shared integrity helper only; it does not import M5 events or
    implement an M13 stage.
    """
    if (
        not isinstance(producer_workflow_ref, dict)
        or set(producer_workflow_ref) != _WORKFLOW_REF_FIELDS
        or not isinstance(execution_record_ref, dict)
        or set(execution_record_ref) != _OUTCOME_REF_FIELDS
    ):
        raise ExecutionOutcomeInvalidError('Explicit execution outcome references are invalid')
    expected_workflow_sha = producer_workflow_ref.get('sha256')
    expected_record_sha = execution_record_ref.get('sha256')
    expected_workflow_id = producer_workflow_ref.get('workflow_id')
    if (
        not _valid_hash(expected_workflow_sha)
        or not _valid_hash(expected_record_sha)
        or not isinstance(expected_workflow_id, str)
        or not expected_workflow_id
        or execution_record_ref.get('schema') != SCHEMA
    ):
        raise ExecutionOutcomeInvalidError('Explicit execution outcome identities are invalid')
    if expected_stage_id is not None and (
        not isinstance(expected_stage_id, str) or not _STAGE_ID.fullmatch(expected_stage_id)
    ):
        raise ExecutionOutcomeInvalidError('Expected producer stage ID is invalid')

    manifest_path = Path(input_manifest_path)
    try:
        manifest_info = manifest_path.lstat()
    except OSError as error:
        raise ExecutionOutcomeUnavailableError(
            'Input manifest is missing or unreadable'
        ) from error
    if stat.S_ISLNK(manifest_info.st_mode) or not stat.S_ISREG(manifest_info.st_mode):
        raise ExecutionOutcomeInvalidError(
            'Input manifest must be a regular non-symlink file'
        )
    root = manifest_path.parent.resolve(strict=True)

    workflow_bytes = _read_explicit_reference(
        root, producer_workflow_ref.get('path')
    )
    actual_workflow_sha = hashlib.sha256(workflow_bytes).hexdigest()
    if actual_workflow_sha != expected_workflow_sha:
        raise ExecutionOutcomeInvalidError('Referenced workflow digest does not match')
    workflow = _parse_reference_json(workflow_bytes, 'Referenced workflow.json')
    if workflow.get('schema') != 'artifact-workflow-manifest-v2':
        raise ExecutionOutcomeInvalidError('Referenced workflow schema is invalid')
    if workflow.get('workflow_id') != expected_workflow_id:
        raise ExecutionOutcomeInvalidError('Referenced workflow ID does not match')
    if workflow.get('status') not in WORKFLOW_TRANSITIONS:
        raise ExecutionOutcomeInvalidError('Referenced workflow status is invalid')
    if workflow.get('status') not in _TERMINAL_WORKFLOW_STATES:
        raise ExecutionOutcomeIncompleteError(
            'Referenced workflow is not terminal; no final outcome can be accepted',
            workflow=workflow,
        )

    record_bytes = _read_explicit_reference(
        root, execution_record_ref.get('path')
    )
    actual_record_sha = hashlib.sha256(record_bytes).hexdigest()
    if actual_record_sha != expected_record_sha:
        raise ExecutionOutcomeInvalidError('Referenced execution record digest does not match')
    record = _parse_reference_json(record_bytes, 'Execution outcome record')
    validate_record(record)
    if record['workflow_manifest_sha256'] != actual_workflow_sha:
        raise ExecutionOutcomeInvalidError(
            'Execution outcome is bound to a different workflow manifest'
        )
    if record['workflow_id'] != expected_workflow_id:
        raise ExecutionOutcomeInvalidError('Execution outcome workflow ID does not match')
    if record['workflow_configuration_sha256'] != workflow.get(
        'configuration_sha256'
    ):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome configuration digest does not match'
        )

    stage_id = record['producer_stage_id']
    if expected_stage_id is not None and stage_id != expected_stage_id:
        raise ExecutionOutcomeInvalidError('Execution outcome producer stage ID does not match')
    stages = workflow.get('stages')
    if not isinstance(stages, list):
        raise ExecutionOutcomeInvalidError('Referenced workflow stages are invalid')
    matches = [
        stage for stage in stages
        if isinstance(stage, dict) and stage.get('id') == stage_id
    ]
    if len(matches) != 1:
        raise ExecutionOutcomeInvalidError(
            'Execution outcome producer stage is absent or duplicated'
        )
    stage = matches[0]
    if (
        stage.get('kind') != record['producer_stage_kind']
        or stage.get('status') != record['producer_execution_status_raw']
        or _raw_m5_status(workflow, stage) != record['producer_status_raw']
    ):
        raise ExecutionOutcomeInvalidError(
            'Execution outcome producer identity or raw status does not match'
        )
    return {
        'workflow': workflow,
        'record': record,
        'workflow_sha256': actual_workflow_sha,
        'execution_record_sha256': actual_record_sha,
    }