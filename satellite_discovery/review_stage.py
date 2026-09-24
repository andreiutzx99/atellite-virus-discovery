"""Artifact lifecycle for new descriptive review stages."""
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import platform
import re
import sys

from . import __version__

from .observation_report import export_csv
from .sequence_downloader import checksum, write_json
from .portable_paths import portable_name


def table(path, columns, limit=200_000):
    path = Path(path)
    if path.stat().st_size > 64_000_000:
        raise ValueError('Input table exceeds 64 MB')
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        names = reader.fieldnames or []
        if len(names) != len(set(names)) or not set(columns) <= set(names):
            raise ValueError('Missing or duplicate columns in ' + str(path))
        rows = []
        for row in reader:
            if len(rows) >= limit or None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed or oversized input table')
            row = {k: v.strip() for k, v in row.items()}
            if any(not row[k] for k in columns) or any(len(v) > 2000 or '\x00' in v for v in row.values()):
                raise ValueError('Empty required or invalid table value')
            rows.append(row)
        return rows


def unique(rows, key):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError('Duplicate ' + key)
        result[row[key]] = row
    return result


def report(directory, title, tables, notes):
    files, body = [], '<h1>' + html.escape(title) + '</h1>'
    for name, rows in tables.items():
        if not re.fullmatch(r'[a-z_]+', name):
            raise ValueError('Invalid report table name')
        filename = name + '.csv'
        if rows:
            export_csv(directory / filename, rows)
            keys = list(rows[0])
            body += '<h2>' + html.escape(name) + '</h2><table><tr>' + ''.join('<th>' + html.escape(k) + '</th>' for k in keys) + '</tr>'
            for row in rows[:1000]:
                body += '<tr>' + ''.join('<td>' + html.escape('unknown' if row[k] is None else str(row[k])) + '</td>' for k in keys) + '</tr>'
            body += '</table>'
            if len(rows) > 1000:
                body += '<p>Showing the first 1,000 rows. The CSV contains all rows.</p>'
        else:
            (directory / filename).write_text('status\nno_records\n', encoding='utf-8')
            body += '<p>' + html.escape(name) + ': no records supplied.</p>'
        if name == 'coverage':
            body += '<h2>Coverage breadth</h2><p>Fraction of the declared reference covered by supplied alignments; first 100 rows. Not unique molecule support.</p>'
            for row in rows[:100]:
                value = float(row['breadth_fraction'])
                if not 0 <= value <= 1:
                    raise ValueError('Coverage breadth must be between zero and one')
                label = str(row['sample_id']) + ' / ' + str(row['reference_id'])
                body += '<p>' + html.escape(label) + ': ' + format(value, '.1%') + ' <meter min="0" max="1" value="' + str(value) + '"></meter></p>'
        files.append(filename)
    body += '<ul>' + ''.join('<li>' + html.escape(x) + '</li>' for x in notes) + '</ul>'
    (directory / 'report.html').write_text('<!doctype html><meta charset="utf-8"><title>' + html.escape(title) + '</title><style>body{font:16px system-ui;margin:2rem}table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.4rem}</style>' + body, encoding='utf-8')
    write_json(directory / 'summary.json', {'title': title, 'tables': tables, 'limitations': notes})
    return files + ['report.html', 'summary.json']


def execute(kind, inputs, output, engine, produce):
    output = Path(output).resolve()
    paths = {k: Path(v).resolve(strict=True) for k, v in inputs.items()}
    if any(p.is_relative_to(output) for p in paths.values()):
        raise ValueError('Inputs must be outside the output folder')
    identity = {'stage': kind, 'inputs': {k: checksum(p) for k, p in paths.items()},
                'engine_sha256': checksum(engine), 'lifecycle_sha256': checksum(__file__),
                'portable_paths_sha256': checksum(Path(__file__).with_name('portable_paths.py')),
                'csv_exporter_sha256': checksum(Path(__file__).with_name('observation_report.py'))}
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.review.lock'
    try:
        lock.open('x').close()
    except FileExistsError:
        raise ValueError('Review folder is locked; do not run concurrent writers')
    manifest = output / 'manifest.json'
    result = None
    try:
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            if previous.get('identity') != identity:
                raise ValueError('Input, stage or implementation changed; use a new output folder')
            if previous.get('status') == 'complete':
                digests = previous.get('output_sha256', {})
                if not isinstance(digests,dict) or not digests or any(not portable_name(n) or n.casefold() == 'manifest.json' for n in digests) or len({n.casefold() for n in digests}) != len(digests):
                    raise ValueError('Invalid manifest output paths')
                if any(not (output / n).resolve().is_relative_to(output) or checksum(output / n) != digest for n, digest in digests.items()):
                    raise ValueError('Output integrity failure; existing result preserved')
                return previous
        elif any(p != lock for p in output.iterdir()):
            raise ValueError('Output directory is not empty and has no matching manifest')
        result = {'status': 'running', 'identity': identity, 'source_paths': {k: str(v) for k, v in paths.items()},
                  'python': platform.python_version(), 'software_version': __version__, 'command': sys.argv,
                  'started_utc': datetime.now(timezone.utc).isoformat()}
        write_json(manifest, result)
        names = produce(paths, output)
        if not names or any(not portable_name(n) or n.casefold() == 'manifest.json' for n in names) or len({n.casefold() for n in names}) != len(names):
            raise ValueError('Invalid producer output paths')
        if any(not (output / n).resolve().is_relative_to(output) for n in names):
            raise ValueError('Producer output redirects outside the review folder')
        if any(checksum(paths[k]) != digest for k, digest in identity['inputs'].items()):
            raise ValueError('Input changed during review')
        result.update(status='complete', finished_utc=datetime.now(timezone.utc).isoformat(),
                      output_sha256={n: checksum(output / n) for n in names})
        write_json(manifest, result)
        return result
    except BaseException as exc:
        if result is not None:
            result.update(status='failed', error=str(exc))
            write_json(manifest, result)
        raise
    finally:
        lock.unlink()
