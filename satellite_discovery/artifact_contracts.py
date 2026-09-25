"""Typed, content-checked artifact contracts for workflow handoffs.

Contracts describe file formats and provenance only. They do not imply
biological identity, function, absence, novelty, or reference completeness.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat

from .sequence_downloader import checksum


SCHEMA = 'artifact-contract-v1'
CONTRACT_VERSION = '1'

# The names are stable identifiers used by the trusted workflow registry.
_CONTRACTS = {
    'raw_read': 'A supplied FASTQ file before workflow validation.',
    'validated_fastq': 'A structurally validated FASTQ file.',
    'fastq_manifest': 'A validated FASTQ handoff manifest with checksum-bound files.',
    'sra_archive': 'A local SRA archive supplied for explicit conversion.',
    'raw_fasta': 'A supplied nucleotide FASTA file.',
    'assembly_manifest': 'A completed registered assembly manifest.',
    'canonical_contig_fasta': 'Catalogue-safe FASTA emitted by assembly.',
    'catalogue_fasta': 'FASTA exported by a sequence catalogue.',
    'sequence_catalogue': 'A validated sequence catalogue SQLite database.',
    'sequence_catalogue_records': 'Structured records from a sequence catalogue.',
    'sequence_catalogue_summary': 'Structured summary from a sequence catalogue.',
    'reference_snapshot_config': 'A declared supplied-reference snapshot manifest.',
    'reference_catalogue': 'The file-level catalogue from a reference snapshot.',
    'reference_snapshot_summary': 'A structured reference snapshot summary.',
    'reference_record_catalogue': 'Per-record metadata from an imported reference snapshot.',
    'reference_records_fasta': 'FASTA records from an immutable imported reference snapshot.',
    'reference_record_database': 'A validated imported reference-record database.',
    'reference_snapshot_manifest': 'A per-record immutable reference snapshot manifest.',
    'reference_roles': 'Declared role and provenance rows for supplied references.',
    'blast_hit_table': 'Raw configured-comparison rows; an empty table is allowed.',
    'sequence_comparison_evidence': 'Descriptive supplied-reference comparison evidence.',
    'comparison_summary': 'Structured descriptive comparison output.',
    'comparison_parameters': 'The declared executable identities and parameters for a comparison.',
    'sample_table': 'Declared sample metadata for supplied observations.',
    'observation_table': 'Declared present/absent/unknown sequence observations.',
    'occurrence_table': 'Catalogue-linked sequence occurrences with provenance.',
    'occurrence_summary': 'Descriptive occurrence and control summaries.',
    'catalogue_imports': 'Declared sequence catalogue imports and sample metadata.',
    'report': 'A human-readable HTML report.',
    'workflow_report_json': 'Machine-readable consolidated workflow report.',
}


def known_contract(name):
    return isinstance(name, str) and name in _CONTRACTS


def contract_names():
    return tuple(sorted(_CONTRACTS))


def contract_description(name):
    if not known_contract(name):
        raise ValueError(f'Unknown artifact contract: {name!r}')
    return _CONTRACTS[name]


def _read_json(path):
    if path.stat().st_size > 32_000_000:
        raise ValueError('JSON artifact exceeds the 32 MB contract limit')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('JSON artifact must be an object')
    return value


def _csv_rows(path, required):
    if path.stat().st_size > 64_000_000:
        raise ValueError('CSV artifact exceeds the 64 MB contract limit')
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not set(required) <= set(fields):
            raise ValueError('CSV artifact does not satisfy its declared columns')
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('CSV artifact contains a malformed row')
            rows.append(row)
            if len(rows) > 200_000:
                raise ValueError('CSV artifact exceeds the 200,000-row contract limit')
    return rows


def _validate_catalogue_database(path):
    uri = path.as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        records = db.execute(
            'SELECT records.record_id, records.sha256, sequences.sequence '
            'FROM records JOIN sequences ON records.sha256=sequences.sha256'
        ).fetchmany(10_001)
        total = db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
        if total != len(records) or len(records) > 10_000:
            raise ValueError('Sequence catalogue has invalid or excessive records')
        for record_id, digest, sequence in records:
            if (not isinstance(record_id, str) or not isinstance(sequence, str)
                    or not re.fullmatch(r'[a-f0-9]{64}', str(digest))
                    or hashlib.sha256(sequence.encode('ascii')).hexdigest() != digest):
                raise ValueError('Sequence catalogue contains invalid sequence provenance')
    return {'record_count': total}


def validate_artifact(path, artifact_type):
    """Validate one declared artifact and return safe descriptive metadata."""
    if not known_contract(artifact_type):
        raise ValueError(f'Unknown artifact contract: {artifact_type!r}')
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError(f'Artifact is missing or unreadable: {path}') from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError('Artifacts must be regular files, not links or directories')
    path = path.resolve(strict=True)
    info = path.stat()
    if info.st_size <= 0 and artifact_type != 'blast_hit_table':
        raise ValueError('Artifact is empty')

    details = {}
    if artifact_type in {'raw_read', 'validated_fastq'}:
        if not path.name.lower().endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
            raise ValueError('FASTQ contract requires a .fastq, .fq or gzip FASTQ file')
        from .assembly_adapters import _read_fastq
        details['record_count'] = sum(1 for _ in _read_fastq(path))
    elif artifact_type == 'sra_archive':
        if path.suffix.lower() != '.sra' or info.st_size > 100_000_000:
            raise ValueError('SRA archive contract requires a local .sra file no larger than 100 MB')
        details['record_count'] = None
    elif artifact_type == 'fastq_manifest':
        value = _read_json(path)
        if value.get('schema') != 'validated-fastq-v1' or value.get('status') != 'valid':
            raise ValueError('FASTQ handoff manifest is not validated')
        files = value.get('files')
        if not isinstance(files, dict) or set(files) != (
            {'read1'} if value.get('layout') == 'single-end' else {'read1', 'read2'}
        ):
            raise ValueError('FASTQ handoff manifest has inconsistent layout and file roles')
        counts = {}
        for role, record in files.items():
            name = record.get('path') if isinstance(record, dict) else None
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError('FASTQ handoff file path is invalid')
            source = path.parent / name
            if checksum(source) != record.get('sha256') or source.stat().st_size != record.get('bytes'):
                raise ValueError('FASTQ handoff file integrity check failed')
            from .assembly_adapters import _read_fastq
            counts[role] = sum(1 for _ in _read_fastq(source))
            if counts[role] != record.get('record_count'):
                raise ValueError('FASTQ handoff read count changed')
        if len(set(counts.values())) != 1:
            raise ValueError('FASTQ handoff mates contain different record counts')
        details['record_count'] = counts['read1']
        details['layout'] = value['layout']
    elif artifact_type == 'raw_fasta':
        from .sequence_catalogue import read_fasta
        records = read_fasta(path)
        details['record_count'] = len(records)
        details['total_bases'] = sum(len(row[2]) for row in records)
    elif artifact_type in {
        'canonical_contig_fasta', 'catalogue_fasta', 'reference_records_fasta',
    }:
        from .sequence_catalogue import read_fasta
        records = read_fasta(path)
        details['record_count'] = len(records)
        details['total_bases'] = sum(len(row[2]) for row in records)
    elif artifact_type == 'assembly_manifest':
        value = _read_json(path)
        if value.get('schema') != 'assembly-manifest-v1' or value.get('workflow_status') != 'complete':
            raise ValueError('Assembly manifest is not a completed registered assembly')
        details.update(record_count=value.get('contig_count'), assembler=value.get('assembler'),
                       tool_version=value.get('external_tool_version'))
    elif artifact_type == 'sequence_catalogue':
        details.update(_validate_catalogue_database(path))
    elif artifact_type == 'sequence_catalogue_records':
        rows = _csv_rows(path, ('record_id', 'sequence_sha256', 'length'))
        details['record_count'] = len(rows)
    elif artifact_type == 'sequence_catalogue_summary':
        value = _read_json(path)
        if not isinstance(value.get('records'), int) or not isinstance(value.get('exact_sequence_groups'), int):
            raise ValueError('Sequence catalogue summary is missing its declared counts')
        details.update(record_count=value['records'], exact_sequence_groups=value['exact_sequence_groups'])
    elif artifact_type == 'reference_snapshot_config':
        value = _read_json(path)
        if not isinstance(value.get('files'), list) or not value['files']:
            raise ValueError('Reference snapshot configuration requires a non-empty files list')
        details['record_count'] = len(value['files'])
    elif artifact_type == 'reference_catalogue':
        rows = _csv_rows(path, ('name', 'bytes', 'sha256', 'source', 'version', 'role', 'reference_id'))
        details['record_count'] = len(rows)
    elif artifact_type == 'reference_snapshot_summary':
        value = _read_json(path)
        if not isinstance(value.get('title'), str) or not isinstance(value.get('tables'), dict):
            raise ValueError('Reference snapshot summary is malformed')
        details['record_count'] = len(value['tables'].get('references', []))
    elif artifact_type == 'reference_record_catalogue':
        rows = _csv_rows(path, ('record_id', 'sequence_sha256', 'reference_id', 'source', 'category'))
        details['record_count'] = len(rows)
    elif artifact_type == 'reference_records_fasta':
        from .sequence_catalogue import read_fasta
        records = read_fasta(path)
        details['record_count'] = len(records)
    elif artifact_type == 'reference_record_database':
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'records', 'sequences'} <= names:
                raise ValueError('Reference-record database schema is incomplete')
            details['record_count'] = db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    elif artifact_type == 'reference_snapshot_manifest':
        value = _read_json(path)
        if (not isinstance(value.get('snapshot_id'), str)
                or not isinstance(value.get('records'), list)
                or value.get('validation_status') not in {'valid', 'review_required'}):
            raise ValueError('Reference-record snapshot manifest is malformed or invalid')
        details.update(record_count=value.get('record_count'), snapshot_id=value['snapshot_id'],
                       parent_snapshot_id=value.get('parent_snapshot_id'),
                       validation_status=value['validation_status'])
    elif artifact_type == 'reference_roles':
        rows = _csv_rows(path, ('reference_id', 'reference_role', 'reference_source', 'reference_version'))
        from .contamination_review import ROLES
        if any(row['reference_role'] not in ROLES for row in rows):
            raise ValueError('Reference roles contain an unsupported role')
        details['record_count'] = len(rows)
    elif artifact_type == 'blast_hit_table':
        if path.stat().st_size > 64_000_000:
            raise ValueError('BLAST hit table exceeds the 64 MB contract limit')
        with path.open(encoding='utf-8') as source:
            count = sum(1 for line in source if line.strip())
        details['record_count'] = count
    elif artifact_type == 'sequence_comparison_evidence':
        rows = _csv_rows(path, ('feature_id', 'reference_id', 'reference_role'))
        details['record_count'] = len(rows)
        details['no_reported_hit'] = len(rows) == 0
    elif artifact_type == 'comparison_summary':
        value = _read_json(path)
        if not isinstance(value.get('title'), str) or not isinstance(value.get('tables'), dict):
            raise ValueError('Comparison summary is malformed')
        details['record_count'] = len(value['tables'].get('matches', []))
        details['result_scope'] = 'configured comparison only'
    elif artifact_type == 'comparison_parameters':
        value = _read_json(path)
        tools = value.get('tools')
        commands = value.get('commands')
        mapping = value.get('identifier_mapping')
        thresholds = value.get('configured_thresholds')
        if (not isinstance(tools, dict) or not {'blastn', 'makeblastdb'} <= set(tools)
                or not isinstance(commands, list) or len(commands) != 2
                or value.get('schema') != 'comparison-parameters-v1'
                or not isinstance(mapping, dict)
                or not isinstance(mapping.get('queries'), dict)
                or not isinstance(mapping.get('references'), dict)
                or not isinstance(thresholds, dict)
                or not isinstance(value.get('threshold_policy'), str)
                or not value['threshold_policy'].strip()
                or not isinstance(value.get('parameters'), str)
                or not value['parameters'].strip()):
            raise ValueError('Comparison parameter record is incomplete')
        for name in ('blastn', 'makeblastdb'):
            item = tools[name]
            if (not isinstance(item, dict) or not isinstance(item.get('version'), str)
                    or not isinstance(item.get('sha256'), str)
                    or len(item['sha256']) != 64
                    or any(char not in '0123456789abcdef' for char in item['sha256'])):
                raise ValueError('Comparison parameter record lacks executable provenance')
        details.update(tool_versions={
            name: tools[name]['version'] for name in ('blastn', 'makeblastdb')
        }, parameters=value['parameters'], configured_thresholds=thresholds,
           threshold_policy=value['threshold_policy'])
    elif artifact_type == 'sample_table':
        rows = _csv_rows(path, ('sample_id', 'study_id', 'condition', 'sample_type', 'library_molecule'))
        details['record_count'] = len(rows)
    elif artifact_type == 'observation_table':
        rows = _csv_rows(path, ('sample_id', 'feature_id', 'detection'))
        details['record_count'] = len(rows)
    elif artifact_type == 'occurrence_table':
        with path.open(encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            fields = set(reader.fieldnames or ())
            allowed = (
                {'sample_id', 'contig_id', 'sequence_sha256'},
                {'feature_id', 'present_biological_samples'},
                {'feature_id', 'study_id', 'library_molecule', 'sample_type',
                 'condition', 'present', 'absent', 'unknown'},
            )
            if not any(required <= fields for required in allowed):
                raise ValueError('Occurrence table does not satisfy a declared descriptive schema')
            rows = list(reader)
            if len(rows) > 200_000 or any(None in row or any(value is None for value in row.values())
                                          for row in rows):
                raise ValueError('Occurrence table contains malformed or excessive rows')
        details['record_count'] = len(rows)
    elif artifact_type in {'occurrence_summary', 'workflow_report_json'}:
        value = _read_json(path)
        details['record_count'] = value.get('feature_count', value.get('record_count'))
        details['schema'] = value.get('schema')
    elif artifact_type == 'catalogue_imports':
        rows = _csv_rows(path, ('catalogue_dir', 'sample_id', 'study_id', 'condition',
                                'sample_type', 'library_molecule'))
        details['record_count'] = len(rows)
    elif artifact_type == 'report':
        if path.stat().st_size > 32_000_000:
            raise ValueError('HTML report exceeds the 32 MB contract limit')
        text = path.read_text(encoding='utf-8')
        if '<' not in text or '\x00' in text:
            raise ValueError('HTML report is not readable text')
    return details


def describe_artifact(path, artifact_type, *, display_path=None, producer_stage=None,
                      input_provenance=None):
    """Return a checksum-bound, validated contract envelope."""
    path = Path(path)
    details = validate_artifact(path, artifact_type)
    path = path.resolve(strict=True)
    descriptor = {
        'schema': SCHEMA,
        'artifact_type': artifact_type,
        'contract_version': CONTRACT_VERSION,
        'producer_stage': producer_stage,
        'path': str(display_path if display_path is not None else path),
        'sha256': checksum(path),
        'size_bytes': path.stat().st_size,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'input_provenance': input_provenance or {},
        'record_count': details.pop('record_count', None),
        'validation_state': 'valid',
        'metadata': details,
    }
    return descriptor


def verify_descriptor(path, descriptor, artifact_type=None):
    """Verify a stored envelope against the current artifact bytes and contract."""
    if not isinstance(descriptor, dict) or descriptor.get('schema') != SCHEMA:
        raise ValueError('Artifact contract descriptor is missing or malformed')
    selected = artifact_type or descriptor.get('artifact_type')
    if descriptor.get('artifact_type') != selected:
        raise ValueError('Artifact contract type changed during handoff')
    fresh = describe_artifact(path, selected)
    if (fresh['sha256'] != descriptor.get('sha256')
            or fresh['size_bytes'] != descriptor.get('size_bytes')
            or descriptor.get('validation_state') != 'valid'):
        raise ValueError('Artifact contract integrity check failed')
    return fresh