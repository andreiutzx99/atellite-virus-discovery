"""Read-only RNA/DNA assay metadata review for existing datasets.json files."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

from .observation_report import export_csv
from .sequence_downloader import checksum, write_json

RULE_VERSION = 'library-metadata-v1'
RNA_SOURCES = {'TRANSCRIPTOMIC', 'TRANSCRIPTOMIC SINGLE CELL', 'METATRANSCRIPTOMIC', 'VIRAL RNA'}
DNA_SOURCES = {'GENOMIC', 'GENOMIC SINGLE CELL', 'SYNTHETIC'}
RNA_STRATEGIES = {'RNA-SEQ', 'SSRNA-SEQ', 'SNRNA-SEQ', 'MIRNA-SEQ', 'NCRNA-SEQ', 'FL-CDNA', 'EST', 'RIBO-SEQ', 'RIP-SEQ'}


def normalize(value):
    return ' '.join(str(value or '').strip().upper().replace('_', ' ').split())


def assess_library(row):
    if not isinstance(row, dict):
        raise ValueError('Each dataset record must be an object')
    source = normalize(row.get('library_source'))
    strategy = normalize(row.get('library_strategy'))
    selection = normalize(row.get('library_selection'))
    layout = normalize(row.get('layout'))
    evidence, warnings = [], []
    if source in RNA_SOURCES:
        evidence.append({'field': 'library_source', 'value': source, 'molecule': 'RNA'})
    elif source in DNA_SOURCES:
        evidence.append({'field': 'library_source', 'value': source, 'molecule': 'DNA'})
    if strategy in RNA_STRATEGIES:
        evidence.append({'field': 'library_strategy', 'value': strategy, 'molecule': 'RNA'})
    types = {e['molecule'] for e in evidence}
    molecule = next(iter(types)) if len(types) == 1 else 'unknown'
    if len(types) > 1:
        warnings.append('conflicting_source_and_strategy')
    if not types:
        warnings.append('assay_molecule_unresolved')
    if source == 'METAGENOMIC':
        warnings.append('metagenomic_source_alone_does_not_resolve_molecule')
    if not source:
        warnings.append('library_source_missing')
    if not strategy:
        warnings.append('library_strategy_missing')
    if strategy in {'AMPLICON', 'WXS', 'TARGETED-CAPTURE'}:
        warnings.append('targeted_assay_not_whole_sample_representation')
    if selection in {'PCR', 'RANDOM PCR', 'POLYA', 'OLIGO-DT', 'HYBRID SELECTION', 'C DNA'}:
        warnings.append('library_selection_bias_requires_review')
    if 'SINGLE CELL' in source or strategy == 'SNRNA-SEQ':
        warnings.append('cell_or_barcode_layout_requires_review')
    if layout not in {'PAIRED', 'SINGLE'}:
        warnings.append('read_layout_unresolved')
    if source == 'SYNTHETIC':
        warnings.append('synthetic_source')
    return {'rule_version': RULE_VERSION, 'assay_molecule': molecule,
            'metadata_status': 'conflicting' if len(types) > 1 else ('supported' if types else 'unknown'),
            'layout': layout if layout in {'PAIRED', 'SINGLE'} else 'unknown',
            'evidence': evidence, 'warnings': warnings,
            'strand_orientation': 'unknown', 'automatic_tool_selection': False,
            'meaning': 'Assay source inference from archive fields, not virion genome type or sequencer substrate'}


def review(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.is_relative_to(output):
        raise ValueError('Keep the source datasets file outside the output directory')
    source_hash = checksum(source)
    rows = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('Expected a JSON array of dataset records')
    records, seen = [], set()
    for row in rows:
        assessment = assess_library(row)
        accession = row.get('run_accession')
        if not isinstance(accession, str) or not accession.strip() or accession in seen:
            raise ValueError('Missing or duplicate run accession')
        seen.add(accession)
        records.append({'run_accession': accession, 'library_source': row.get('library_source'),
                        'library_strategy': row.get('library_strategy'), 'library_selection': row.get('library_selection'),
                        **assessment})
    if checksum(source) != source_hash:
        raise ValueError('Source changed during review')
    identity = {'input_sha256': source_hash, 'engine_sha256': checksum(__file__), 'rule_version': RULE_VERSION,
                'csv_exporter_sha256': checksum(Path(__file__).with_name('observation_report.py'))}
    names = ('library_review.json', 'library_review.csv', 'report.html')
    if output.exists():
        manifest = output / 'manifest.json'
        if not manifest.is_file():
            raise ValueError('Choose a new output folder')
        previous = json.loads(manifest.read_text(encoding='utf-8'))
        if previous.get('status') != 'complete' or previous.get('identity') != identity:
            raise ValueError('Incomplete or changed review; choose a new output folder')
        if set(previous.get('output_sha256', {})) != set(names) or any(checksum(output / n) != previous['output_sha256'][n] for n in names):
            raise ValueError('Output integrity mismatch; existing review preserved')
        return previous
    output.mkdir(parents=True)
    result = {'status': 'running', 'identity': identity, 'source': str(source),
              'started_utc': datetime.now(timezone.utc).isoformat(), 'records': len(records)}
    write_json(output / 'manifest.json', result)
    try:
        write_json(output / 'library_review.json', records)
        flat = [{k: r[k] for k in ('run_accession', 'library_source', 'library_strategy', 'assay_molecule', 'metadata_status', 'layout', 'warnings')} for r in records]
        if flat:
            export_csv(output / 'library_review.csv', flat)
        else:
            (output / 'library_review.csv').write_text('run_accession,assay_molecule,metadata_status\n', encoding='utf-8')
        table = '<table><tr><th>Run</th><th>Assay source</th><th>Metadata status</th><th>Warnings</th></tr>'
        table += ''.join('<tr>' + ''.join('<td>' + html.escape(str(r[k])) + '</td>' for k in ('run_accession', 'assay_molecule', 'metadata_status', 'warnings')) + '</tr>' for r in records) + '</table>'
        (output / 'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Library metadata review</title><style>body{font:16px system-ui;margin:2rem}td,th{border:1px solid #aaa;padding:.5rem}table{border-collapse:collapse}</style><h1>Library metadata review</h1><p>Read-only review of existing metadata. No library is selected for downstream processing. Assay source is not the virus genome type. Strand orientation remains unknown.</p>' + table, encoding='utf-8')
        result.update(status='complete', output_sha256={name: checksum(output / name) for name in names})
        write_json(output / 'manifest.json', result)
    except BaseException as exc:
        result.update(status='failed', error=str(exc))
        write_json(output / 'manifest.json', result)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets')
    parser.add_argument('--output')
    parser.add_argument('--wizard', action='store_true')
    args = parser.parse_args()
    if args.wizard:
        args.datasets = input('Full path to existing datasets.json: ').strip().strip('"')
        args.output = input('New output folder (same completed folder to verify reuse): ').strip().strip('"')
    if not args.datasets or not args.output:
        parser.error('Provide --datasets and --output, or --wizard')
    try:
        review(args.datasets, args.output)
        print('Verified library review: ' + str(Path(args.output).resolve() / 'report.html'))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, 'Library review failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
