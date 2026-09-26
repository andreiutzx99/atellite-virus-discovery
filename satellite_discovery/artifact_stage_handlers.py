"""Trusted handlers that bridge existing generic artifact components."""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import html
import json
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing

from . import assembly_adapters, observation_report, quality_control
from .review_stage import execute, table, unique
from .sequence_downloader import checksum, write_json


SAMPLE_FIELDS = ('sample_id', 'study_id', 'condition', 'sample_type', 'library_molecule')


def validate_fastq_config(config):
    if not isinstance(config, dict) or set(config) != {'layout'}:
        raise ValueError('FASTQ validation config requires only layout')
    if config['layout'] not in {'single-end', 'paired-end'}:
        raise ValueError('FASTQ layout must be declared as single-end or paired-end')
    return {'layout': config['layout']}


def validate_qc_config(config):
    """Validate a bounded declarative configuration for the existing QC engine."""
    if not isinstance(config, dict):
        raise ValueError('FASTQ QC config must be an object')
    allowed = {
        'min_length', 'end_quality', 'min_mean_quality', 'max_n_fraction',
        'adapters', 'min_adapter_overlap',
    }
    if set(config) - allowed:
        raise ValueError('FASTQ QC config contains unsupported fields')
    values = dict(config)
    if 'adapters' in values:
        if (not isinstance(values['adapters'], (list, tuple))
                or any(not isinstance(item, str) for item in values['adapters'])):
            raise ValueError('QC adapters must be a list of literal sequence strings')
        values['adapters'] = tuple(values['adapters'])
    qc_config = quality_control.QCConfig(**values)
    qc_config.validate()
    return {
        'min_length': qc_config.min_length,
        'end_quality': qc_config.end_quality,
        'min_mean_quality': qc_config.min_mean_quality,
        'max_n_fraction': qc_config.max_n_fraction,
        'adapters': list(qc_config.adapters),
        'min_adapter_overlap': qc_config.min_adapter_overlap,
    }


def quality_control_fastq(inputs, output, config):
    """Run the existing QC engine as a typed stage and retain its full outputs."""
    config = validate_qc_config(config)
    if set(inputs) not in ({'read1'}, {'read1', 'read2'}):
        raise ValueError('FASTQ QC requires read1 and optionally read2')

    def produce(paths, directory):
        qc_inputs = ({'single': paths['read1']} if 'read2' not in paths else
                     {'R1': paths['read1'], 'R2': paths['read2']})
        qc_config = quality_control.QCConfig(
            min_length=config['min_length'],
            end_quality=config['end_quality'],
            min_mean_quality=config['min_mean_quality'],
            max_n_fraction=config['max_n_fraction'],
            adapters=tuple(config['adapters']),
            min_adapter_overlap=config['min_adapter_overlap'],
        )
        result = quality_control.run_qc(
            qc_inputs, directory, qc_config, progress=lambda _message: None,
        )
        return sorted(result['output_sha256']) + ['qc.json']

    return execute('typed-fastq-qc-v1', inputs, output, __file__, produce)


def validate_observation_config(config):
    if not isinstance(config, dict) or set(config) != {'samples'} or not isinstance(config['samples'], dict):
        raise ValueError('Catalogue observation config requires declared samples keyed by catalogue input name')
    if not 1 <= len(config['samples']) <= 100:
        raise ValueError('Declare between one and 100 catalogue samples')
    normalized_samples = {}
    for input_name, sample in config['samples'].items():
        if (not isinstance(input_name, str) or not input_name
                or len(input_name) > 64 or not input_name[0].isalpha()
                or any(not (char.isalnum() or char in '_-') for char in input_name)):
            raise ValueError('Sample configuration keys must match safe catalogue input names')
        if not isinstance(sample, dict) or set(sample) != set(SAMPLE_FIELDS):
            raise ValueError('Each sample requires sample_id, study_id, condition, sample_type and library_molecule')
        if any(not isinstance(sample[name], str) or not sample[name].strip()
               or len(sample[name]) > 1000 or '\x00' in sample[name] for name in SAMPLE_FIELDS):
            raise ValueError('Sample fields must be explicit bounded strings; use unknown where appropriate')
        normalized = {name: sample[name].strip() for name in SAMPLE_FIELDS}
        if normalized['condition'] not in {'positive', 'negative', 'unknown'}:
            raise ValueError('condition must be positive, negative or unknown')
        if normalized['sample_type'] not in {'biological', 'technical_control', 'unknown'}:
            raise ValueError('sample_type must be biological, technical_control or unknown')
        if normalized['library_molecule'] not in {'RNA', 'DNA', 'mixed', 'unknown'}:
            raise ValueError('library_molecule must be RNA, DNA, mixed or unknown')
        normalized_samples[input_name] = normalized
    return {'samples': normalized_samples}


def validate_workflow_report_config(config):
    if not isinstance(config, dict) or set(config) - {'title'}:
        raise ValueError('Workflow report config accepts only title')
    title = config.get('title', 'Generic artifact workflow')
    if not isinstance(title, str) or not title.strip() or len(title) > 300 or '\x00' in title:
        raise ValueError('Workflow report title must be a bounded non-empty string')
    return {'title': title.strip()}


def _copy_as_deterministic_gzip(source, destination):
    compressed = source.name.lower().endswith(('.fastq.gz', '.fq.gz'))
    opener = gzip.open if compressed else open
    with opener(source, 'rb') as reader, destination.open('wb') as raw_target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw_target, mtime=0) as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)


def validate_fastq(inputs, output, config):
    """Validate and snapshot declared FASTQ inputs without running QC."""
    config = validate_fastq_config(config)
    if set(inputs) not in ({'read1'}, {'read1', 'read2'}):
        raise ValueError('FASTQ validation requires read1 and optionally read2')
    if (config['layout'] == 'paired-end') != ('read2' in inputs):
        raise ValueError('Declared FASTQ layout does not match the supplied read mates')
    if 'read2' in inputs:
        first, second = Path(inputs['read1']).resolve(strict=True), Path(inputs['read2']).resolve(strict=True)
        if first == second or (first.stat().st_dev, first.stat().st_ino) == (second.stat().st_dev, second.stat().st_ino):
            raise ValueError('Paired FASTQ inputs must be distinct files')

    def produce(paths, directory):
        source_hashes = {name: checksum(path) for name, path in paths.items()}
        output_paths = {}
        for role in ('read1', 'read2'):
            if role not in paths:
                continue
            target = directory / f'{role}.fastq.gz'
            _copy_as_deterministic_gzip(paths[role], target)
            output_paths[role] = target
        counts = assembly_adapters._validate_fastq_inputs(output_paths, directory)
        if any(checksum(paths[name]) != digest for name, digest in source_hashes.items()):
            raise ValueError('FASTQ input changed during validation')
        files = {
            role: {
                'path': path.name,
                'sha256': checksum(path),
                'bytes': path.stat().st_size,
                'record_count': counts[role],
            }
            for role, path in output_paths.items()
        }
        write_json(directory / 'fastq.json', {
            'schema': 'validated-fastq-v1',
            'contract_version': '1',
            'layout': config['layout'],
            'status': 'valid',
            'source_sha256': source_hashes,
            'files': files,
            'validated_utc': datetime.now(timezone.utc).isoformat(),
            'validation': 'FASTQ structure, sequence/quality lengths, read-pair counts and mate IDs checked.',
            'scope': 'Validation only; no quality filtering or biological interpretation.',
        })
        return [path.name for path in output_paths.values()] + ['fastq.json']

    return execute('validated-fastq-v1', inputs, output, __file__, produce)


def _catalogue_records(path):
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        rows = db.execute(
            'SELECT records.record_id, records.sha256, sequences.sequence '
            'FROM records JOIN sequences ON records.sha256=sequences.sha256 ORDER BY records.record_id'
        ).fetchmany(10_001)
        if len(rows) > 10_000 or db.execute('SELECT COUNT(*) FROM records').fetchone()[0] != len(rows):
            raise ValueError('Catalogue has missing sequence records or exceeds its record limit')
    seen = set()
    for record_id, digest, sequence in rows:
        if (not isinstance(record_id, str) or not isinstance(sequence, str)
                or hashlib.sha256(sequence.encode('ascii')).hexdigest() != digest):
            raise ValueError('Catalogue record or sequence checksum is invalid')
        if record_id in seen:
            raise ValueError('Catalogue contains duplicate contig identifiers')
        seen.add(record_id)
    if not rows:
        raise ValueError('Cannot create observations from an empty sequence catalogue')
    return rows


def catalogue_observations(inputs, output, config):
    """Create supplied-presence observations from declared catalogues."""
    config = validate_observation_config(config)
    if set(inputs) != set(config['samples']):
        raise ValueError('Each catalogue input must have exactly one declared sample record')

    def produce(paths, directory):
        samples_by_id = {}
        input_owners = {}
        presence = set()
        occurrences = []
        for input_name, catalogue_path in sorted(paths.items()):
            sample = config['samples'][input_name]
            catalogue_dir = catalogue_path.parent
            marker = catalogue_dir / 'manifest.json'
            catalogue_manifest = json.loads(marker.read_text(encoding='utf-8'))
            digests = catalogue_manifest.get('output_sha256', {})
            if (catalogue_manifest.get('status') != 'complete'
                    or catalogue_manifest.get('identity', {}).get('schema') != 'sequence-inventory-v1'
                    or digests.get('catalogue.sqlite') != checksum(catalogue_path)):
                raise ValueError('Catalogue input lacks a completed integrity-checked inventory manifest')
            fasta_hash = catalogue_manifest.get('identity', {}).get('input_sha256')
            if not isinstance(fasta_hash, str) or len(fasta_hash) != 64:
                raise ValueError('Catalogue manifest lacks source FASTA provenance')
            previous_sample = samples_by_id.get(sample['sample_id'])
            if previous_sample is not None and previous_sample != sample:
                raise ValueError('One biological sample has conflicting declared metadata')
            samples_by_id[sample['sample_id']] = sample
            owner = input_owners.get(fasta_hash)
            if owner is not None and owner != sample['sample_id']:
                raise ValueError('Identical FASTA input bytes cannot establish two independent samples')
            input_owners[fasta_hash] = sample['sample_id']
            records = _catalogue_records(catalogue_path)
            for contig_id, digest, _sequence in records:
                presence.add((sample['sample_id'], digest))
                occurrences.append({
                    'sample_id': sample['sample_id'],
                    'contig_id': contig_id,
                    'sequence_sha256': digest,
                    'detection': 'present',
                    'catalogue_input': input_name,
                    'catalogue_manifest_sha256': checksum(marker),
                    'source_fasta_sha256': fasta_hash,
                })
        samples = sorted(samples_by_id.values(), key=lambda item: item['sample_id'])
        observations = [
            {'sample_id': sample_id, 'feature_id': digest, 'detection': 'present'}
            for sample_id, digest in sorted(presence)
        ]
        if len(samples) * len({row['feature_id'] for row in observations}) > 100_000:
            raise ValueError('Occurrence table exceeds the 100,000 sample/sequence cell limit')
        summary = observation_report.summarize(samples, observations)
        summary.update({
            'schema': 'catalogue-occurrences-v1',
            'record_count': len(occurrences),
            'unique_sequence_count': len({row['sequence_sha256'] for row in occurrences}),
            'provenance': {
                'catalogues': {
                    name: {'path': str(path), 'sha256': checksum(path)}
                    for name, path in sorted(paths.items())
                },
                'feature_identity': 'exact sequence SHA256 from the supplied catalogue',
            },
            'limitations': summary['limitations'] + [
                'Presence is derived only from records in the declared sequence catalogue.',
                'No absence, read-level detection, sample independence or biological function is inferred.',
            ],
        })
        observation_report.export_csv(directory / 'samples.csv', samples)
        observation_report.export_csv(directory / 'observations.csv', observations)
        observation_report.export_csv(directory / 'occurrences.csv', occurrences)
        observation_report.export_csv(directory / 'recurrence.csv', summary['recurrence'])
        observation_report.export_csv(directory / 'comparisons.csv', summary['comparisons'])
        observation_report.export_database(directory / 'observations.sqlite', samples, observations)
        write_json(directory / 'summary.json', summary)
        (directory / 'report.html').write_text(observation_report.render(summary), encoding='utf-8')
        return [
            'samples.csv', 'observations.csv', 'occurrences.csv', 'recurrence.csv',
            'comparisons.csv', 'observations.sqlite', 'summary.json', 'report.html',
        ]

    return execute('catalogue-observations-v1', inputs, output, __file__, produce)


def reference_roles_from_records(inputs, output, config):
    """Use only explicitly supplied reference categories as comparison roles."""
    if config:
        raise ValueError('Reference role handoff does not accept configuration')
    if set(inputs) != {'records'}:
        raise ValueError('Reference role handoff requires imported reference records')

    def produce(paths, directory):
        rows = table(paths['records'], ('record_id', 'source', 'category', 'reference_version'),
                     limit=10_000)
        if not rows:
            raise ValueError('Imported reference snapshot contains no records')
        from .contamination_review import ROLES
        result = []
        for row in rows:
            role = row['category']
            if role not in ROLES:
                raise ValueError(
                    'Reference category must be an explicitly supplied supported comparison role'
                )
            result.append({
                'reference_id': row['record_id'],
                'reference_role': role,
                'reference_source': row['source'],
                'reference_version': row['reference_version'] or 'unknown',
            })
        if len({row['reference_id'] for row in result}) != len(result):
            raise ValueError('Imported reference record identifiers are duplicated')
        observation_report.export_csv(directory / 'roles.csv', result)
        write_json(directory / 'summary.json', {
            'schema': 'declared-reference-roles-v1',
            'record_count': len(result),
            'source_artifact_sha256': checksum(paths['records']),
            'policy': 'Reference roles are copied from declared snapshot categories, not inferred.',
        })
        report_body = '<!doctype html><meta charset="utf-8"><title>Declared reference roles</title>' \
            '<h1>Declared reference roles</h1><p>Roles are copied from the supplied reference snapshot metadata; ' \
            'no automatic reference curation or classification is performed.</p><p>Records: ' + str(len(result)) + '</p>'
        (directory / 'report.html').write_text(report_body, encoding='utf-8')
        return ['roles.csv', 'summary.json', 'report.html']

    return execute('reference-roles-v1', inputs, output, __file__, produce)


def workflow_report(inputs, output, config):
    """Consolidate declared structured stage outputs without biological inference."""
    config = validate_workflow_report_config(config)
    if not inputs:
        raise ValueError('Consolidated report requires at least one declared upstream artifact')

    def produce(paths, directory):
        artifacts = {}
        for name, path in sorted(paths.items()):
            record = {
                'path': str(path),
                'sha256': checksum(path),
                'size_bytes': path.stat().st_size,
            }
            if path.suffix.lower() == '.json':
                if path.stat().st_size > 32_000_000:
                    raise ValueError('A structured report input exceeds the 32 MB limit')
                value = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(value, dict):
                    raise ValueError('Structured report inputs must be JSON objects')
                if value.get('schema') in {'dvg-summary-v1', 'dvg-evidence-v1'}:
                    from . import dvg_evidence
                    if value['schema'] == 'dvg-summary-v1':
                        dvg_evidence.validate_summary(value)
                    else:
                        dvg_evidence.validate_evidence_document(value)
                record['summary'] = value
                if value.get('schema') in {'dvg-summary-v1', 'dvg-evidence-v1'}:
                    record['schema'] = value['schema']
                if value.get('schema') in {
                    'm6-residual-manifest-v1', 'm6-read-support-v1',
                    'm6-reconstruction-evidence-v1',
                    'm7-observations-v1', 'm7-exact-recurrence-v1',
                    'm7-independence-summary-v1', 'm7-validation-report-v1',
                    'm7-recurrence-provenance-v1',
                    'm8-query-status-v1', 'm8-match-evidence-v1',
                    'm8-homology-summary-v1', 'm8-search-commands-v1',
                }:
                    record['schema'] = value['schema']
                if value.get('schema') == 'm8-match-evidence-v1':
                    rows = value.get('matches', [])
                    record['summary'] = {
                        'match_count': len(rows) if isinstance(rows, list) else 0,
                        'candidate_count': len({
                            row.get('candidate_id') for row in rows
                            if isinstance(row, dict) and row.get('candidate_id')
                        }) if isinstance(rows, list) else 0,
                        'panel_roles': sorted({
                            row.get('panel_role') for row in rows
                            if isinstance(row, dict) and row.get('panel_role')
                        }) if isinstance(rows, list) else [],
                        'evidence_is_linked_by': 'path and sha256',
                    }
                elif value.get('schema') == 'm8-query-status-v1':
                    record['summary'] = {
                        'aggregate_status': value.get('aggregate_status'),
                        'candidate_availability_state': value.get(
                            'candidate_availability_state'),
                        'candidate_record_count': value.get('candidate_record_count'),
                        'branch_status_counts': value.get('branch_status_counts', {}),
                        'query_count': len(value.get('queries', []))
                        if isinstance(value.get('queries'), list) else 0,
                    }
                elif value.get('schema') == 'm8-search-commands-v1':
                    record['summary'] = {
                        'profile_id': value.get('profile_id'),
                        'branch_count': len(value.get('branches', []))
                        if isinstance(value.get('branches'), list) else 0,
                        'runtime': value.get('runtime'),
                        'commands_are_linked_by': 'path and sha256',
                    }
                tables = value.get('tables', {})
                if isinstance(tables, dict) and 'matches' in tables and not tables['matches']:
                    record['comparison_status'] = 'no match found under the configured comparison'
            else:
                record['media_type'] = 'text/html' if path.suffix.lower() == '.html' else 'text/csv'
            artifacts[name] = record
        report = {
            'schema': 'consolidated-workflow-report-v1',
            'title': config['title'],
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'artifacts': artifacts,
            'scope': 'Descriptive processing of declared artifacts only.',
            'limitations': [
                'A no-hit comparison means no match was reported under the configured comparison; it is not a novelty result.',
                'Missing observations are not converted to absence.',
                'No biological classification, causality, replication, function or candidate ranking is performed.',
            ],
        }
        if any(record.get('schema') in {'dvg-summary-v1', 'dvg-evidence-v1'}
               for record in artifacts.values()):
            report['limitations'].append(
                'No DVG evidence detected by a configured caller means only that this run reported no supported junctions under its settings; it does not establish that the sequence is not a DVG. An unavailable, failed, interrupted or invalid run draws no biological conclusion.'
            )
        if any(record.get('schema') in {
                'm8-query-status-v1', 'm8-match-evidence-v1',
                'm8-homology-summary-v1', 'm8-search-commands-v1',
        } for record in artifacts.values()):
            report['limitations'].append(
                'M8 nucleotide alignments are descriptive homology evidence only. '
                'A no-hit is scoped to the complete declared reference snapshot and '
                'search profile and does not establish novelty, biological class, '
                'function, causality or ranking.'
            )
        write_json(directory / 'report.json', report)
        sections = [
            '<!doctype html><html><head><meta charset="utf-8"><title>' +
            html.escape(config['title']) +
            '</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}'
            'table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.4rem;text-align:left}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:1rem}'
            '</style></head><body><h1>' + html.escape(config['title']) +
            '</h1><p>Descriptive processing of declared artifacts only.</p>'
        ]
        for name, record in artifacts.items():
            sections.append('<section><h2>' + html.escape(name) + '</h2><p>SHA256: <code>' +
                            html.escape(record['sha256']) + '</code>; ' +
                            str(record['size_bytes']) + ' bytes.</p>')
            if record.get('comparison_status'):
                sections.append('<p>' + html.escape(record['comparison_status']) + '.</p>')
            if record.get('schema') == 'dvg-summary-v1':
                summary = record['summary']
                def concise(value):
                    rendered = str(value) if value is not None else 'Not provided'
                    return rendered[:500] + ('…' if len(rendered) > 500 else '')

                fields = (
                    ('Caller', summary.get('caller')),
                    ('Version', summary.get(
                        'caller_version', summary.get('version', summary.get('parser_version')))),
                    ('Status', summary.get('status')),
                    ('Event count', summary.get('event_count')),
                    ('Raw output location', summary.get(
                        'raw_output_location',
                        summary.get('raw_output_path', summary.get('raw_output')))),
                    ('Evidence references', (
                        ', '.join(str(item)[:180] for item in
                                  summary.get('event_references', [])[:20])
                        + (f" (+{len(summary['event_references']) - 20} more in the summary)"
                           if len(summary.get('event_references', [])) > 20 else '')
                    ) if summary.get('event_references') else 'None reported'),
                )
                sections.append('<dl>' + ''.join(
                    '<dt>' + html.escape(label) + '</dt><dd>' +
                    html.escape(concise(value)) +
                    '</dd>' for label, value in fields
                ) + '</dl>')
                limitations = summary.get('limitations', [])
                if isinstance(limitations, list) and limitations:
                    sections.append('<h3>DVG evaluation limitations</h3><ul>' + ''.join(
                        '<li>' + html.escape(concise(item)) + '</li>'
                        for item in limitations[:25]
                    ) + '</ul>')
            elif record.get('schema') == 'dvg-evidence-v1':
                evidence = record['summary']
                sections.append(
                    '<p>Caller: ' + html.escape(str(evidence.get('caller', 'Not provided'))[:500]) +
                    '; status: ' + html.escape(str(evidence.get('status', 'Not provided'))[:500]) +
                    '; event count: ' + str(len(evidence['events'])) + '.</p>' +
                    '<p>Hash-bound evidence reference: <code>' +
                    html.escape(record['sha256']) + '</code>; declared path: <code>' +
                    html.escape(record['path']) + '</code>.</p>'
                )
            elif record.get('schema') == 'm6-residual-manifest-v1':
                summary = record['summary']
                counts = summary.get('counts', {})
                fields = (
                    ('Configured comparison status', summary.get('comparison', {}).get('status')),
                    ('Input fragments', counts.get('input_fragments')),
                    ('Residual fragments', counts.get('residual_fragments')),
                    ('Eligible for assembly', counts.get('eligible_fragments')),
                    ('Retained unassembled', counts.get('retained_unassembled_fragments')),
                )
                sections.append('<p>Residual means unexplained by the completed configured comparison; it does not mean novel.</p><dl>' +
                                ''.join('<dt>' + html.escape(label) + '</dt><dd>' +
                                        html.escape(str(value if value is not None else 'Not reported')) +
                                        '</dd>' for label, value in fields) + '</dl>')
            elif record.get('schema') in {'m6-read-support-v1', 'm6-reconstruction-evidence-v1'}:
                summary = record['summary']
                contigs = summary.get('contigs', [])
                supported = sum(
                    1 for item in contigs
                    if item.get('status') == 'READ_SUPPORTED_ASSEMBLY'
                )
                unsupported = sum(
                    1 for item in contigs
                    if item.get('status') in {
                        'LOW_SUPPORT_ASSEMBLY', 'AMBIGUOUS_ASSEMBLY',
                        'UNSUPPORTED_ASSEMBLY',
                    }
                )
                status = summary.get('status', 'Not reported')
                sections.append(
                    '<p>Outcome: <strong>' + html.escape(str(status)) +
                    '</strong>; assembler contigs recorded: ' + str(len(contigs)) +
                    '; contigs meeting configured read-support criteria: ' + str(supported) +
                    '; unsupported or ambiguous reconstructions retained: ' + str(unsupported) +
                    '.</p><p>Assembly is reconstruction hypothesis generation. Original sequencing reads provide the underlying evidence.</p>'
                )
                if status == 'NO_SUPPORTED_ASSEMBLY':
                    sections.append('<p>No supported assembly was obtained. Residual reads remain available for review.</p>')
                dvg = summary.get('dvg_evidence', {})
                if isinstance(dvg, dict):
                    sections.append('<p>DVG evidence status: ' +
                                    html.escape(str(dvg.get('status', 'NOT_EVALUATED'))) +
                                    '; this is a separate evidence dimension.</p>')
            elif record.get('schema') == 'm7-independence-summary-v1':
                summary = record['summary']
                fields = (
                    ('Result', summary.get('result_status')),
                    ('Completeness', summary.get('analysis_completeness')),
                    ('Supported sequence observations',
                     summary.get('supported_sequence_observation_count')),
                    ('Exact sequence groups', summary.get('exact_group_count')),
                    ('Recurrent source-dataset groups',
                     summary.get('recurrent_group_count')),
                    ('Orientation policy', summary.get('orientation_policy')),
                )
                sections.append(
                    '<p>M7 reports exact recurrence only among individually supported '
                    'M6 contigs; it does not classify biological identity or function.</p><dl>' +
                    ''.join('<dt>' + html.escape(label) + '</dt><dd>' +
                            html.escape(str(value if value is not None else 'Not reported')) +
                            '</dd>' for label, value in fields) + '</dl>'
                )
            elif record.get('schema') == 'm7-observations-v1':
                summary = record['summary']
                sections.append(
                    '<p>Declared observations: ' +
                    str(summary.get('record_count', 'Not reported')) +
                    '; supported sequence observations: ' +
                    str(summary.get('sequence_observation_count', 'Not reported')) +
                    '. Missing metadata remains explicit.</p>'
                )
            elif record.get('schema') == 'm7-exact-recurrence-v1':
                summary = record['summary']
                sections.append(
                    '<p>Exact sequence groups: ' +
                    str(summary.get('record_count', 'Not reported')) +
                    '; orientation policy: ' +
                    html.escape(str(summary.get('orientation_policy', 'Not reported'))) +
                    '.</p>'
                )
            elif record.get('schema') == 'm7-validation-report-v1':
                summary = record['summary']
                sections.append(
                    '<p>Validation status: ' +
                    html.escape(str(summary.get('status', 'Not reported'))) +
                    '; observations: ' +
                    str(summary.get('observation_count', 'Not reported')) +
                    '; unavailable: ' +
                    str(summary.get('unavailable_count', 'Not reported')) +
                    '; failed: ' +
                    str(summary.get('failed_count', 'Not reported')) + '.</p>'
                )
            elif record.get('schema') == 'm7-recurrence-provenance-v1':
                summary = record['summary']
                sections.append(
                    '<p>Configuration SHA256: <code>' +
                    html.escape(str(summary.get('configuration_sha256', 'Not reported'))) +
                    '</code>; declared input artifacts: ' +
                    str(len(summary.get('input_artifacts', {}))) + '.</p>'
                )
            elif record.get('schema') in {
                    'm8-query-status-v1', 'm8-match-evidence-v1',
                    'm8-homology-summary-v1', 'm8-search-commands-v1'}:
                sections.append(
                    '<p>M8 output is linked by the artifact path and SHA-256 above; '
                    'it is not a biological classification.</p><pre>' +
                    html.escape(json.dumps(record.get('summary', {}), indent=2, sort_keys=True)) +
                    '</pre>'
                )
            elif 'summary' in record:
                sections.append('<pre>' + html.escape(json.dumps(record['summary'], indent=2, sort_keys=True)) + '</pre>')
            else:
                sections.append('<p>Declared artifact path: <code>' + html.escape(record['path']) + '</code>.</p>')
            sections.append('</section>')
        sections.append('<h2>Limitations</h2><ul>' + ''.join(
            '<li>' + html.escape(item) + '</li>' for item in report['limitations']
        ) + '</ul></body></html>')
        (directory / 'report.html').write_text(''.join(sections), encoding='utf-8')
        return ['report.json', 'report.html']

    return execute('consolidated-workflow-report-v1', inputs, output, __file__, produce)