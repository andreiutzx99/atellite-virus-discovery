"""Typed, content-checked artifact contracts for workflow handoffs.

Contracts describe file formats and provenance only. They do not imply
biological identity, function, absence, novelty, or reference completeness.
"""
import csv
from contextlib import closing
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
    'qc_fastq': 'A checksum-bound FASTQ emitted by the completed QC stage; it may contain zero reads.',
    'residual_fastq': 'Original FASTQ records unexplained by a completed configured reference screen.',
    'eligible_residual_fastq': 'Residual FASTQ records meeting configured technical assembly-triage criteria.',
    'retained_unassembled_fastq': 'Residual FASTQ records retained but not sent to assembly.',
    'unresolved_residual_fastq': 'Residual FASTQ records not represented by a read-supported reconstruction.',
    'fastq_manifest': 'A validated FASTQ handoff manifest with checksum-bound files.',
    'qc_manifest': 'A completed QC manifest bound to its exact inputs and output FASTQs.',
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
    'dvg_raw_output': 'Bounded UTF-8 native DVG caller output.',
    'dvg_evidence': 'Validated normalized DVG evidence events.',
    'dvg_evidence_summary': 'Validated caller-neutral DVG evaluation summary.',
    'dvg_parameters': 'Declared DVG caller configuration and source provenance.',
    'residual_read_manifest': 'Completion-accounted residual-read provenance and comparison scope.',
    'read_triage_table': 'Per-read technical triage evidence and reason codes.',
    'read_alignment_sam': 'Bounded raw SAM output from a completed read comparison.',
    'read_support_evidence': 'Caller-neutral read-back support evidence for assembled contigs.',
    'read_support_table': 'Per-read alignment support rows linked to stable read and contig identifiers.',
    'reconstruction_evidence': 'Neutral assembly and read-support outcome; not a biological classification.',
    'm7_observation_table': 'Declared M6 observations and supported sequence records with provenance.',
    'm7_exact_recurrence_table': 'Exact sequence recurrence groups with retained observation identities.',
    'm7_independence_summary': 'Descriptive recurrence and metadata-based independence summaries.',
    'm7_validation_report': 'Validation and completeness state for an M7 recurrence evaluation.',
    'm7_provenance_manifest': 'M7 input, configuration, implementation and output provenance.',
    'm8_candidate_sequence_set': 'Producer-declared M6 candidate sequences with byte availability and provenance.',
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


_HASH = re.compile(r'^[a-f0-9]{64}$')


def _validate_fastq_file(path, *, allow_empty):
    if not path.name.lower().endswith(('.fastq.gz', '.fq.gz')):
        raise ValueError('Typed QC and residual FASTQ artifacts must be gzip-compressed FASTQ files')
    from .assembly_adapters import _read_fastq
    count = sum(1 for _ in _read_fastq(path, allow_empty=allow_empty))
    return {'record_count': count}


def _validate_qc_manifest(path):
    value = _read_json(path)
    fingerprint = value.get('fingerprint')
    if (value.get('status') != 'complete'
            or not isinstance(value.get('engine'), str) or not value['engine']
            or not isinstance(fingerprint, dict)
            or not isinstance(fingerprint.get('software_version'), str)
            or not isinstance(fingerprint.get('config'), dict)
            or not isinstance(fingerprint.get('inputs'), dict)
            or not isinstance(value.get('output_sha256'), dict)
            or not isinstance(value.get('before'), dict)
            or not isinstance(value.get('after'), dict)
            or not isinstance(value.get('counts'), dict)):
        raise ValueError('QC manifest is incomplete or not marked complete')
    inputs = fingerprint['inputs']
    if set(inputs) not in ({'single'}, {'R1', 'R2'}):
        raise ValueError('QC manifest input roles are inconsistent')
    for record in inputs.values():
        if (not isinstance(record, dict) or not _HASH.fullmatch(str(record.get('sha256', '')))
                or not isinstance(record.get('bytes'), int) or record['bytes'] <= 0):
            raise ValueError('QC manifest contains invalid input provenance')
    expected_outputs = (
        {'clean_single.fastq.gz', 'rejected.fastq.gz'}
        if 'single' in inputs else
        {'clean_single.fastq.gz', 'rejected.fastq.gz', 'clean_R1.fastq.gz',
         'clean_R2.fastq.gz', 'orphan_R1.fastq.gz', 'orphan_R2.fastq.gz'}
    )
    outputs = value['output_sha256']
    if set(outputs) != expected_outputs:
        raise ValueError('QC manifest output list is inconsistent with its input layout')
    for name, digest in outputs.items():
        if Path(name).name != name or not _HASH.fullmatch(str(digest)):
            raise ValueError('QC manifest contains an invalid output name or checksum')
        output = path.parent / name
        try:
            info = output.lstat()
        except OSError as error:
            raise ValueError('QC output named by the manifest is missing') from error
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError('QC outputs must be regular files')
        if checksum(output) != digest:
            raise ValueError('QC output integrity check failed')
        _validate_fastq_file(output, allow_empty=True)
    return {'schema': 'qc-manifest-current', 'input_roles': sorted(inputs),
            'output_count': len(outputs), 'engine': value['engine']}


def _csv_count(path, required, *, max_rows=1_000_000):
    if path.stat().st_size > 256_000_000:
        raise ValueError('CSV artifact exceeds the 256 MB contract limit')
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not set(required) <= set(fields):
            raise ValueError('CSV artifact does not satisfy its declared columns')
        count = 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('CSV artifact contains a malformed row')
            count += 1
            if count > max_rows:
                raise ValueError('CSV artifact exceeds its row limit')
    return count


def _validate_sam(path):
    if path.stat().st_size > 200_000_000:
        raise ValueError('SAM artifact exceeds the 200 MB contract limit')
    count = 0
    has_header = False
    with path.open(encoding='ascii', newline='') as source:
        for line in source:
            if line.startswith('@'):
                has_header = True
                continue
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) < 11:
                raise ValueError('SAM artifact contains a malformed alignment row')
            try:
                flag, position, mapq = int(fields[1]), int(fields[3]), int(fields[4])
            except ValueError as error:
                raise ValueError('SAM artifact contains invalid numeric fields') from error
            if not 0 <= flag <= 65535 or position < 0 or not 0 <= mapq <= 255:
                raise ValueError('SAM artifact contains out-of-range fields')
            count += 1
            if count > 4_000_000:
                raise ValueError('SAM artifact exceeds its record limit')
    if not has_header:
        raise ValueError('SAM artifact is missing its header')
    return {'record_count': count}


def _validate_catalogue_database(path):
    uri = path.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
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
    if info.st_size <= 0 and artifact_type not in {'blast_hit_table', 'dvg_raw_output'}:
        raise ValueError('Artifact is empty')

    details = {}
    if artifact_type in {'raw_read', 'validated_fastq'}:
        if not path.name.lower().endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
            raise ValueError('FASTQ contract requires a .fastq, .fq or gzip FASTQ file')
        from .assembly_adapters import _read_fastq
        details['record_count'] = sum(1 for _ in _read_fastq(path))
    elif artifact_type in {
        'qc_fastq', 'residual_fastq', 'eligible_residual_fastq',
        'retained_unassembled_fastq', 'unresolved_residual_fastq',
    }:
        details.update(_validate_fastq_file(path, allow_empty=True))
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
    elif artifact_type == 'qc_manifest':
        details.update(_validate_qc_manifest(path))
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
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
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
    elif artifact_type == 'read_triage_table':
        count = _csv_count(path, (
            'query_id', 'mate', 'outcome', 'residual', 'length',
            'ambiguous_fraction', 'entropy', 'mean_phred',
            'sequence_hash', 'exact_duplicate_count', 'reason_codes',
        ))
        details['record_count'] = count
        details['evidence_scope'] = 'technical read triage only'
    elif artifact_type == 'read_support_table':
        count = _csv_count(path, (
            'query_id', 'mate', 'contig_id', 'mapq', 'query_aligned_bases',
            'reference_aligned_bases', 'aligned_query_fraction',
            'sequence_identity', 'qualifying',
        ))
        details['record_count'] = count
    elif artifact_type == 'read_alignment_sam':
        details.update(_validate_sam(path))
    elif artifact_type == 'residual_read_manifest':
        value = _read_json(path)
        comparison = value.get('comparison')
        if (value.get('schema') != 'm6-residual-manifest-v1'
                or value.get('status') != 'complete'
                or not isinstance(value.get('sample_id'), str)
                or not isinstance(value.get('source_reads'), dict)
                or not isinstance(value.get('qc_artifact'), dict)
                or not isinstance(comparison, dict)
                or comparison.get('status') != 'complete'
                or not isinstance(comparison.get('input_read_count'), int)
                or comparison['input_read_count'] < 1
                or comparison.get('accounted_read_count') != comparison.get('input_read_count')
                or not isinstance(value.get('counts'), dict)
                or not isinstance(value.get('artifact_sha256'), dict)):
            raise ValueError('Residual read manifest is incomplete or comparison accounting is not complete')
        for digest in value['artifact_sha256'].values():
            if not isinstance(digest, str) or not _HASH.fullmatch(digest):
                raise ValueError('Residual read manifest contains an invalid artifact checksum')
        details.update(schema=value['schema'], sample_id=value['sample_id'],
                       comparison_scope=comparison.get('scope'))
    elif artifact_type in {'read_support_evidence', 'reconstruction_evidence'}:
        value = _read_json(path)
        allowed_support = {
            'READ_SUPPORTED_ASSEMBLY', 'NO_SUPPORTED_ASSEMBLY',
            'NOT_EVALUATED', 'READ_SUPPORT_FAILED', 'INVALID_SUPPORT_OUTPUT',
        }
        allowed_reconstruction = {
            'READ_SUPPORTED_ASSEMBLY', 'NO_SUPPORTED_ASSEMBLY',
            'DEPENDENCY_UNAVAILABLE', 'EXECUTION_FAILED', 'INTERRUPTED',
            'INVALID_OUTPUT', 'READ_SUPPORT_FAILED', 'INVALID_SUPPORT_OUTPUT',
            'ASSEMBLY_NOT_ATTEMPTED',
        }
        schema = ('m6-read-support-v1' if artifact_type == 'read_support_evidence'
                  else 'm6-reconstruction-evidence-v1')
        allowed_status = allowed_support if artifact_type == 'read_support_evidence' else allowed_reconstruction
        if (value.get('schema') != schema or value.get('status') not in allowed_status
                or not isinstance(value.get('contigs'), list)
                or not isinstance(value.get('configuration'), dict)
                or not isinstance(value.get('provenance'), dict)):
            raise ValueError(f'{artifact_type} document is malformed')
        if artifact_type == 'read_support_evidence' and not isinstance(value.get('read_support'), list):
            raise ValueError('Read-support evidence is missing its per-read records')
        details.update(schema=schema, status=value['status'], record_count=len(value['contigs']))
    elif artifact_type in {'occurrence_summary', 'workflow_report_json'}:
        value = _read_json(path)
        details['record_count'] = value.get('feature_count', value.get('record_count'))
        details['schema'] = value.get('schema')
    elif artifact_type == 'm7_observation_table':
        value = _read_json(path)
        observations = value.get('observations')
        sequence_rows = value.get('sequence_observations')
        if (value.get('schema') != 'm7-observations-v1'
                or not isinstance(observations, list)
                or not isinstance(sequence_rows, list)
                or value.get('record_count') != len(observations)
                or value.get('sequence_observation_count') != len(sequence_rows)):
            raise ValueError('M7 observation table is malformed')
        observation_ids = set()
        for row in observations:
            if (not isinstance(row, dict)
                    or not isinstance(row.get('observation_id'), str)
                    or row['observation_id'] in observation_ids
                    or row.get('m6_state') not in {'available', 'unavailable', 'failed'}
                    or not isinstance(row.get('contigs'), list)
                    or not isinstance(row.get('metadata_missing'), list)
                    or not isinstance(row.get('source_artifacts'), dict)):
                raise ValueError('M7 observation record is malformed')
            observation_ids.add(row['observation_id'])
            fingerprint = row.get('source_dataset_fingerprint')
            if fingerprint is not None and (
                    not isinstance(fingerprint, str) or not _HASH.fullmatch(fingerprint)):
                raise ValueError('M7 observation has an invalid source-dataset fingerprint')
        for row in sequence_rows:
            if (not isinstance(row, dict)
                    or row.get('observation_id') not in observation_ids
                    or not isinstance(row.get('sequence_id'), str)
                    or not isinstance(row.get('sequence_length'), int)
                    or isinstance(row.get('sequence_length'), bool)
                    or row['sequence_length'] < 1
                    or not isinstance(row.get('sequence_sha256'), str)
                    or not _HASH.fullmatch(row['sequence_sha256'])
                    or not isinstance(row.get('match_sha256'), str)
                    or not _HASH.fullmatch(row['match_sha256'])):
                raise ValueError('M7 sequence observation is malformed')
        details.update(schema=value['schema'], record_count=len(observations),
                       sequence_observation_count=len(sequence_rows))
    elif artifact_type == 'm7_exact_recurrence_table':
        value = _read_json(path)
        groups = value.get('groups')
        if (value.get('schema') != 'm7-exact-recurrence-v1'
                or value.get('orientation_policy') not in {
                    'forward_only', 'reverse_complement_invariant',
                }
                or not isinstance(groups, list)
                or value.get('record_count') != len(groups)):
            raise ValueError('M7 exact recurrence table is malformed')
        for group in groups:
            if (not isinstance(group, dict)
                    or not isinstance(group.get('match_sha256'), str)
                    or not _HASH.fullmatch(group['match_sha256'])
                    or group.get('group_id') != 'exact-' + group['match_sha256']
                    or not isinstance(group.get('sequence_length'), int)
                    or isinstance(group.get('sequence_length'), bool)
                    or group['sequence_length'] < 1
                    or not isinstance(group.get('members'), list)
                    or not isinstance(group.get('recurrence_categories'), list)
                    or not isinstance(group.get('independence'), dict)):
                raise ValueError('M7 exact recurrence group is malformed')
            for member in group['members']:
                if (not isinstance(member, dict)
                        or not isinstance(member.get('observation_id'), str)
                        or not isinstance(member.get('sequence_id'), str)
                        or not isinstance(member.get('sequence_sha256'), str)
                        or not _HASH.fullmatch(member['sequence_sha256'])):
                    raise ValueError('M7 exact recurrence member is malformed')
        details.update(schema=value['schema'], record_count=len(groups))
    elif artifact_type == 'm7_independence_summary':
        value = _read_json(path)
        count_fields = (
            'observation_count', 'supported_sequence_observation_count',
            'exact_group_count', 'recurrent_group_count',
        )
        if (value.get('schema') != 'm7-independence-summary-v1'
                or value.get('analysis_completeness') not in {'COMPLETE', 'PARTIAL'}
                or value.get('result_status') not in {
                    'RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS',
                    'NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS',
                    'NO_ELIGIBLE_SUPPORTED_SEQUENCES',
                    'UPSTREAM_UNAVAILABLE_OR_FAILED',
                }
                or any(not isinstance(value.get(key), int)
                       or isinstance(value.get(key), bool) or value[key] < 0
                       for key in count_fields)
                or not isinstance(value.get('limitations'), list)
                or not isinstance(value.get('m6_evidence_class_counts'), dict)):
            raise ValueError('M7 independence summary is malformed')
        details.update(schema=value['schema'],
                       record_count=value['exact_group_count'])
    elif artifact_type == 'm7_validation_report':
        value = _read_json(path)
        count_fields = (
            'observation_count', 'available_m6_count', 'unavailable_count',
            'failed_count', 'unsupported_count', 'unresolved_count',
            'supported_sequence_observation_count',
        )
        if (value.get('schema') != 'm7-validation-report-v1'
                or value.get('status') not in {'complete', 'partial'}
                or any(not isinstance(value.get(key), int)
                       or isinstance(value.get(key), bool) or value[key] < 0
                       for key in count_fields)
                or not isinstance(value.get('warnings'), list)):
            raise ValueError('M7 validation report is malformed')
        details.update(schema=value['schema'],
                       record_count=value['observation_count'])
    elif artifact_type == 'm7_provenance_manifest':
        value = _read_json(path)
        input_artifacts = value.get('input_artifacts')
        output_hashes = value.get('output_sha256')
        implementation = value.get('implementation')
        if (value.get('schema') != 'm7-recurrence-provenance-v1'
                or value.get('status') != 'complete'
                or not isinstance(value.get('configuration'), dict)
                or not isinstance(value.get('configuration_sha256'), str)
                or not _HASH.fullmatch(value['configuration_sha256'])
                or not isinstance(input_artifacts, dict)
                or not isinstance(output_hashes, dict)
                or not isinstance(implementation, dict)
                or not isinstance(value.get('observation_source_datasets'), list)
                or any(not isinstance(row, dict)
                       or not isinstance(row.get('sha256'), str)
                       or not _HASH.fullmatch(row['sha256'])
                       for row in input_artifacts.values())
                or any(not isinstance(digest, str) or not _HASH.fullmatch(digest)
                       for digest in output_hashes.values())):
            raise ValueError('M7 provenance manifest is malformed')
        details.update(schema=value['schema'],
                       record_count=len(value['observation_source_datasets']))
    elif artifact_type == 'dvg_raw_output':
        from .dvg_evidence import _MAX_NATIVE_BYTES
        if path.name != 'Virus_Recombination_Results.txt':
            raise ValueError('DVG native output must be named Virus_Recombination_Results.txt')
        if info.st_size > _MAX_NATIVE_BYTES:
            raise ValueError('DVG native output exceeds the 32 MB contract limit')
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError('DVG native output must be readable UTF-8 text') from error
        if '\x00' in text:
            raise ValueError('DVG native output contains a NUL byte')
        details['record_count'] = None
    elif artifact_type in {'dvg_evidence', 'dvg_evidence_summary'}:
        value = _read_json(path)
        from . import dvg_evidence
        if artifact_type == 'dvg_evidence':
            dvg_evidence.validate_evidence_document(value)
            details['record_count'] = len(value['events'])
            details['schema'] = value['schema']
        else:
            dvg_evidence.validate_summary(value)
            details['record_count'] = value['event_count']
            details['schema'] = value['schema']
    elif artifact_type == 'dvg_parameters':
        value = _read_json(path)
        required = {
            'caller', 'caller_version', 'upstream_commit', 'source_sha256',
            'configuration', 'input_sha256', 'command',
        }
        if (value.get('schema') != 'dvg-parameters-v1'
                or not required <= set(value)
                or any(not isinstance(value.get(key), str) or not value[key].strip()
                       for key in ('caller', 'caller_version', 'upstream_commit'))
                or not isinstance(value.get('configuration'), dict)
                or not isinstance(value.get('command'), list)
                or not value['command']
                or any(not isinstance(arg, str) or not arg or '\x00' in arg
                       for arg in value['command'])):
            raise ValueError('DVG parameter record is incomplete')
        hash_pattern = re.compile(r'^[a-f0-9]{64}$')
        for field in ('source_sha256', 'input_sha256'):
            mapping = value[field]
            if (not isinstance(mapping, dict) or not mapping
                    or any(not isinstance(name, str) or not name.strip()
                           or not isinstance(digest, str) or not hash_pattern.fullmatch(digest)
                           for name, digest in mapping.items())):
                raise ValueError(f'DVG parameter record has an invalid {field} mapping')
        details.update(
            schema=value['schema'],
            caller=value['caller'],
            caller_version=value['caller_version'],
            source_count=len(value['source_sha256']),
            input_count=len(value['input_sha256']),
        )
    elif artifact_type == 'catalogue_imports':
        rows = _csv_rows(path, ('catalogue_dir', 'sample_id', 'study_id', 'condition',
                                'sample_type', 'library_molecule'))
        details['record_count'] = len(rows)
    elif artifact_type == 'm8_candidate_sequence_set':
        from .m8_candidate_handoff import validate_candidate_sequence_set
        details.update(validate_candidate_sequence_set(path))
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