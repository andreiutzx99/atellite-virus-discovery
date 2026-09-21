"""Descriptive summaries of supplied observations; no sequence discovery or scoring."""
import argparse
import csv
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import html
import json
import platform
import sqlite3
import sys
from pathlib import Path

from .sequence_downloader import checksum, write_json

SCHEMA = 'observations-v1'
SAMPLE_COLUMNS = ('sample_id', 'study_id', 'condition', 'sample_type', 'library_molecule')
OBS_COLUMNS = ('sample_id', 'feature_id', 'detection')
OUTPUTS = ('summary.json', 'recurrence.csv', 'comparisons.csv', 'observations.sqlite', 'report.html')


def read_table(path, required):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not set(required).issubset(fields):
            raise ValueError('Missing or duplicate CSV columns: ' + str(path))
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed CSV row')
            if any(not row[k].strip() for k in required):
                raise ValueError('Required fields must be explicit; use unknown where appropriate')
            if any(len(v) > 1000 or '\x00' in v for v in row.values()):
                raise ValueError('Invalid or excessively long CSV value')
            rows.append({k: v.strip() for k, v in row.items()})
    return rows


def validate(samples_path, observations_path):
    samples = read_table(samples_path, SAMPLE_COLUMNS)
    observations = read_table(observations_path, OBS_COLUMNS)
    if not samples or not observations:
        raise ValueError('Provide at least one sample and one observation')
    by_id = {}
    for row in samples:
        sid = row['sample_id']
        if sid in by_id:
            raise ValueError('Duplicate biological sample ID; reconcile repeat sequencing runs before import')
        if row['condition'] not in {'positive', 'negative', 'unknown'}:
            raise ValueError('condition must be positive, negative or unknown')
        if row['sample_type'] not in {'biological', 'technical_control', 'unknown'}:
            raise ValueError('Invalid sample_type')
        if row['library_molecule'] not in {'RNA', 'DNA', 'mixed', 'unknown'}:
            raise ValueError('library_molecule must be RNA, DNA, mixed or unknown')
        by_id[sid] = row
    pairs = set()
    for row in observations:
        key = row['sample_id'], row['feature_id']
        if key[0] not in by_id or key in pairs:
            raise ValueError('Unknown sample or duplicate sample/feature observation')
        pairs.add(key)
        if row['detection'] not in {'present', 'absent', 'unknown'}:
            raise ValueError('detection must be present, absent or unknown')
    # Bound the report matrix; this tool intentionally does not render enormous cohorts.
    if len(samples) * len({o['feature_id'] for o in observations}) > 100_000:
        raise ValueError('Report exceeds 100,000 sample/feature cells; split the cohort')
    return samples, observations


def summarize(samples, observations):
    lookup = {(r['sample_id'], r['feature_id']): r['detection'] for r in observations}
    features = sorted({r['feature_id'] for r in observations})
    summaries, comparisons = [], []
    bio = [s for s in samples if s['sample_type'] == 'biological']
    groups = defaultdict(list)
    for sample in samples:
        groups[(sample['study_id'], sample['library_molecule'], sample['sample_type'], sample['condition'])].append(sample['sample_id'])
    for feature in features:
        present = [s for s in bio if lookup.get((s['sample_id'], feature)) == 'present']
        absent = sum(lookup.get((s['sample_id'], feature)) == 'absent' for s in bio)
        studies = sorted({s['study_id'] for s in present if s['study_id'] != 'unknown'})
        summaries.append({'feature_id': feature, 'present_biological_samples': len(present),
                          'absent_biological_samples': absent,
                          'unknown_biological_samples': len(bio) - len(present) - absent,
                          'distinct_studies_with_detection': len(studies), 'study_ids': studies,
                          'detections_without_study_id': sum(s['study_id'] == 'unknown' for s in present)})
        # Strata prevent RNA and DNA assays, studies, or technical controls being pooled.
        for (study, molecule, kind, condition), identifiers in sorted(groups.items()):
            calls = [lookup.get((sid, feature), 'unknown') for sid in identifiers]
            positive, negative = calls.count('present'), calls.count('absent')
            comparisons.append({'feature_id': feature, 'study_id': study, 'library_molecule': molecule,
                                'sample_type': kind, 'condition': condition, 'present': positive,
                                'absent': negative, 'unknown': calls.count('unknown'),
                                'assessed_samples': positive + negative,
                                'observed_fraction': positive / (positive + negative) if positive + negative else None})
    return {'schema': SCHEMA, 'sample_count': len(samples), 'feature_count': len(features),
            'recurrence': summaries, 'comparisons': comparisons,
            'limitations': ['Inputs are supplied observations; detections are not independently verified.',
                           'Missing observations are unknown, not negative controls.',
                           'Distinct studies are not proof of independent biological replication.',
                           'Fractions describe assessed samples; no probability, causal claim or ranking is produced.',
                           'RNA and DNA assay types are reported separately; comparability is not assumed.']}


def export_csv(path, rows):
    with Path(path).open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            safe = {}
            for key, value in row.items():
                value = json.dumps(value) if isinstance(value, list) else value
                if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                    value = "'" + value
                safe[key] = value
            writer.writerow(safe)


def export_database(path, samples, observations):
    # Build a replacement artifact and atomically publish it; never append duplicate imports.
    temporary = path.with_suffix('.building.sqlite')
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(temporary)) as connection, connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('CREATE TABLE samples (sample_id TEXT PRIMARY KEY, study_id TEXT, condition TEXT, sample_type TEXT, library_molecule TEXT)')
        connection.execute('CREATE TABLE observations (sample_id TEXT REFERENCES samples(sample_id), feature_id TEXT, detection TEXT, PRIMARY KEY(sample_id, feature_id))')
        connection.executemany('INSERT INTO samples VALUES (?,?,?,?,?)', [tuple(s[k] for k in SAMPLE_COLUMNS) for s in samples])
        connection.executemany('INSERT INTO observations VALUES (?,?,?)', [tuple(o[k] for k in OBS_COLUMNS) for o in observations])
    temporary.replace(path)


def render_heatmap(comparisons):
    """Bounded accessible display of supplied observations, including unassessed cells."""
    features = sorted({r['feature_id'] for r in comparisons})[:40]
    keys = ('study_id', 'library_molecule', 'sample_type', 'condition')
    strata = sorted({tuple(r[k] for k in keys) for r in comparisons})[:30]
    lookup = {(r['feature_id'], tuple(r[k] for k in keys)): r for r in comparisons}
    body = '<h2>Observed-fraction heatmap</h2><p>At most 40 features and 30 strata; full values remain in CSV. Each column is study / assay / sample type / condition. Unassessed is not zero.</p><table><tr><th>Feature</th>'
    body += ''.join('<th>' + html.escape(' / '.join(k)) + '</th>' for k in strata) + '</tr>'
    for feature in features:
        body += '<tr><th>' + html.escape(feature) + '</th>'
        for group in strata:
            row = lookup.get((feature, group))
            value = row['observed_fraction'] if row else None
            if value is None:
                body += '<td style="background:#eee">not assessed</td>'
            else:
                shade = round(245 - 100 * value)
                label = str(row['present']) + '/' + str(row['assessed_samples']) + ' (' + format(value, '.1%') + ')'
                body += '<td style="background:rgb(' + str(shade) + ',' + str(shade) + ',255)">' + label + '</td>'
        body += '</tr>'
    return body + '</table>'


def render(summary):
    def table(rows):
        keys = list(rows[0])
        return '<table><tr>' + ''.join('<th>' + html.escape(k) + '</th>' for k in keys) + '</tr>' + ''.join(
            '<tr>' + ''.join('<td>' + html.escape('not assessed' if r[k] is None else str(r[k])) + '</td>' for k in keys) + '</tr>' for r in rows) + '</table>'
    bars = ''.join('<p>' + html.escape(r['feature_id']) + ': ' + str(r['present_biological_samples']) +
                   ' biological samples <meter min="0" max="' + str(summary['sample_count']) +
                   '" value="' + str(r['present_biological_samples']) + '"></meter></p>' for r in summary['recurrence'])
    return '<!doctype html><meta charset="utf-8"><title>Observed sequence associations</title><style>body{font:16px system-ui;margin:2rem}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.5rem}th{background:#eef}meter{width:180px}</style><h1>Observed sequence associations</h1><p>Descriptive observations only; no discovery score or dependency inference.</p>' + bars + render_heatmap(summary['comparisons']) + '<h2>Recurrence</h2>' + table(summary['recurrence']) + '<h2>Study and control comparisons</h2>' + table(summary['comparisons']) + '<h2>Interpretation</h2><ul>' + ''.join('<li>' + html.escape(x) + '</li>' for x in summary['limitations']) + '</ul>'


def run(samples_path, observations_path, directory):
    samples_path, observations_path = Path(samples_path).resolve(), Path(observations_path).resolve()
    directory = Path(directory).resolve()
    if any(p.is_relative_to(directory) for p in (samples_path, observations_path)):
        raise ValueError('Keep input CSV files outside the output directory')
    identity = {'schema': SCHEMA, 'engine_sha256': checksum(__file__),
                'samples_sha256': checksum(samples_path), 'observations_sha256': checksum(observations_path)}
    samples, observations = validate(samples_path, observations_path)
    summary = summarize(samples, observations)
    if checksum(samples_path) != identity['samples_sha256'] or checksum(observations_path) != identity['observations_sha256']:
        raise ValueError('Input changed while reading')
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / '.observations.lock'
    try:
        handle = lock.open('x')
    except FileExistsError:
        raise ValueError('Output is locked by another or interrupted process; see the recovery guide')
    handle.close()
    manifest = directory / 'manifest.json'
    result = None
    try:
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            if previous['identity'] != identity:
                raise ValueError('Inputs or engine changed; choose a new output directory')
            if previous['status'] == 'complete':
                if set(previous['output_sha256']) != set(OUTPUTS) or any(checksum(directory / n) != previous['output_sha256'][n] for n in OUTPUTS):
                    raise ValueError('Output integrity failure; completed results were not overwritten')
                return previous
        elif any(p.name != lock.name for p in directory.iterdir()):
            raise ValueError('Output directory is not empty and has no matching manifest')
        result = {'status': 'running', 'identity': identity, 'started_utc': datetime.now(timezone.utc).isoformat(),
                  'python': platform.python_version(), 'command': sys.argv,
                  'inputs': {'samples': str(samples_path), 'observations': str(observations_path)}}
        write_json(manifest, result)
        write_json(directory / 'summary.json', summary)
        export_csv(directory / 'recurrence.csv', summary['recurrence'])
        export_csv(directory / 'comparisons.csv', summary['comparisons'])
        export_database(directory / 'observations.sqlite', samples, observations)
        (directory / 'report.html').write_text(render(summary), encoding='utf-8')
        result.update(status='complete', finished_utc=datetime.now(timezone.utc).isoformat(),
                      output_sha256={name: checksum(directory / name) for name in OUTPUTS})
        write_json(manifest, result)
        return result
    except BaseException as exc:
        if result is not None:
            result.update(status='failed', error=str(exc))
            write_json(manifest, result)
        raise
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples')
    parser.add_argument('--observations')
    parser.add_argument('--output')
    parser.add_argument('--wizard', action='store_true')
    args = parser.parse_args()
    if args.wizard:
        args.samples = input('Full path to samples CSV: ').strip().strip('"')
        args.observations = input('Full path to observations CSV: ').strip().strip('"')
        args.output = input('Output folder (new, or same folder to resume): ').strip().strip('"')
    if not all((args.samples, args.observations, args.output)):
        parser.error('Provide --samples, --observations and --output, or --wizard')
    try:
        run(args.samples, args.observations, args.output)
        print('Verified report: ' + str(Path(args.output).resolve() / 'report.html'))
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, 'Observation report failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
