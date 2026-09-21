"""Inventory supplied nucleotide FASTA records without assembly or functional inference."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sqlite3

from .observation_report import export_csv
from .sequence_downloader import checksum, write_json

ALPHABET = set('ACGTURYSWKMBDHVN')
MAX_BASES = 20_000_000
MAX_RECORDS = 10_000
OUTPUTS = ('records.csv', 'summary.json', 'catalogue.sqlite', 'sequences.fasta', 'report.html')


def read_fasta(path):
    if Path(path).stat().st_size > 100_000_000:
        raise ValueError('FASTA file exceeds the 100 MB input cap')
    records, seen = [], set()
    header, chunks = None, []
    total = 0

    def finish():
        if header is None:
            return
        identifier = header.split()[0]
        if identifier in seen:
            raise ValueError('Duplicate FASTA record ID: ' + identifier)
        sequence = ''.join(chunks)
        if not sequence:
            raise ValueError('Empty FASTA sequence: ' + identifier)
        if len(records) >= MAX_RECORDS:
            raise ValueError('FASTA exceeds the 10,000-record limit')
        seen.add(identifier)
        records.append((identifier, header, sequence))

    with Path(path).open(encoding='utf-8-sig') as source:
        for line in source:
            line = line.strip()
            if not line:
                continue
            if line.startswith('>'):
                finish()
                header, chunks = line[1:].strip(), []
                if not header or len(header) > 1000 or any(ord(c) < 32 for c in header):
                    raise ValueError('Invalid FASTA header')
                if not re.fullmatch(r'[A-Za-z0-9_.:-]+', header.split()[0]):
                    raise ValueError('Use FASTA IDs containing letters, digits, underscore, dot, colon or hyphen')
            else:
                if header is None:
                    raise ValueError('Sequence appears before its FASTA header')
                sequence = ''.join(line.split()).upper()
                if not set(sequence) <= ALPHABET:
                    raise ValueError('Invalid nucleotide symbol; gaps and protein sequences are not accepted')
                total += len(sequence)
                if total > MAX_BASES:
                    raise ValueError('FASTA exceeds the 20-million-base limit')
                chunks.append(sequence)
        finish()
    if not records:
        raise ValueError('FASTA contains no sequence records')
    return records


def measurements(records):
    rows = []
    counts = Counter(sequence for _, _, sequence in records)
    for identifier, header, sequence in records:
        bases = Counter(sequence)
        called = sum(bases[b] for b in 'ACGTU')
        fractions = [bases[b] / called for b in 'ACGTU' if bases[b]] if called else []
        warnings = []
        if not called:
            warnings.append('no_unambiguous_bases')
        if bases['T'] and bases['U']:
            warnings.append('both_T_and_U_present')
        rows.append({'record_id': identifier, 'description': header,
                     'sequence_sha256': hashlib.sha256(sequence.encode('ascii')).hexdigest(),
                     'length': len(sequence), 'gc_fraction_called_bases': (bases['G'] + bases['C']) / called if called else None,
                     'ambiguous_fraction': (len(sequence) - called) / len(sequence),
                     'single_symbol_entropy_bits': -sum(p * math.log2(p) for p in fractions) if called else None,
                     'exact_duplicate_group_size': counts[sequence], 'warnings': warnings})
    return rows


def create_database(path, records, rows):
    temporary = path.with_suffix('.building.sqlite')
    if temporary.exists():
        temporary.unlink()
    with closing(sqlite3.connect(temporary)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE sequences (sha256 TEXT PRIMARY KEY, sequence TEXT NOT NULL)')
        db.execute('CREATE TABLE records (record_id TEXT PRIMARY KEY, header TEXT NOT NULL, sha256 TEXT REFERENCES sequences(sha256), metrics_json TEXT NOT NULL)')
        for (identifier, header, sequence), row in zip(records, rows):
            db.execute('INSERT OR IGNORE INTO sequences VALUES (?,?)', (row['sequence_sha256'], sequence))
            db.execute('INSERT INTO records VALUES (?,?,?,?)', (identifier, header, row['sequence_sha256'], json.dumps(row)))
    temporary.replace(path)


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.is_relative_to(output):
        raise ValueError('Keep the input FASTA outside the output folder')
    identity = {'schema': 'sequence-inventory-v1', 'input_sha256': checksum(source),
                'engine_sha256': checksum(__file__),
                'csv_exporter_sha256': checksum(Path(__file__).with_name('observation_report.py'))}
    records = read_fasta(source)
    rows = measurements(records)
    if checksum(source) != identity['input_sha256']:
        raise ValueError('FASTA changed while reading')
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.catalogue.lock'
    try:
        lock.open('x').close()
    except FileExistsError:
        raise ValueError('Catalogue output is locked; confirm no active process before recovery')
    manifest = output / 'manifest.json'
    result = None
    try:
        if manifest.exists():
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            if previous.get('identity') != identity:
                raise ValueError('Inputs or implementation changed; use a new output folder')
            if previous.get('status') == 'complete':
                if set(previous.get('output_sha256', {})) != set(OUTPUTS) or any(checksum(output / n) != previous['output_sha256'][n] for n in OUTPUTS):
                    raise ValueError('Output integrity failure; existing outputs preserved')
                return previous
        elif any(p.name != lock.name for p in output.iterdir()):
            raise ValueError('Output folder is not empty and has no matching manifest')
        result = {'status': 'running', 'identity': identity, 'source': str(source),
                  'started_utc': datetime.now(timezone.utc).isoformat()}
        write_json(manifest, result)
        export_csv(output / 'records.csv', rows)
        create_database(output / 'catalogue.sqlite', records, rows)
        with (output / 'sequences.fasta').open('w', encoding='utf-8', newline='\n') as target:
            for _, header, sequence in records:
                target.write('>' + header + '\n')
                for offset in range(0, len(sequence), 80):
                    target.write(sequence[offset:offset+80] + '\n')
        summary = {'records': len(records), 'exact_sequence_groups': len({r['sequence_sha256'] for r in rows}),
                   'total_bases': sum(r['length'] for r in rows),
                   'limitations': ['Composition only; entropy is not a sequencing-artefact diagnosis.',
                                   'Groups use exact uppercase sequence identity, preserving strand and T/U differences.',
                                   'No similarity clustering, consensus, reconstruction or functional inference.',
                                   'No sequence is rejected based on these measurements.']}
        write_json(output / 'summary.json', summary)
        keys = ('record_id', 'length', 'gc_fraction_called_bases', 'ambiguous_fraction', 'exact_duplicate_group_size', 'warnings')
        table = '<table><tr>' + ''.join('<th>' + html.escape(k) + '</th>' for k in keys) + '</tr>'
        table += ''.join('<tr>' + ''.join('<td>' + html.escape('unknown' if r[k] is None else str(r[k])) + '</td>' for k in keys) + '</tr>' for r in rows) + '</table>'
        (output / 'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Sequence inventory</title><style>body{font:16px system-ui;margin:2rem}td,th{border:1px solid #aaa;padding:.4rem}table{border-collapse:collapse}</style><h1>Sequence inventory</h1><p>Supplied sequences only; no biological classification or ranking.</p>' + table + '<ul>' + ''.join('<li>' + html.escape(x) + '</li>' for x in summary['limitations']) + '</ul>', encoding='utf-8')
        result.update(status='complete', finished_utc=datetime.now(timezone.utc).isoformat(),
                      output_sha256={name: checksum(output / name) for name in OUTPUTS})
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
    parser.add_argument('--fasta')
    parser.add_argument('--output')
    parser.add_argument('--wizard', action='store_true')
    args = parser.parse_args()
    if args.wizard:
        args.fasta = input('Full path to an existing nucleotide FASTA: ').strip().strip('"')
        args.output = input('New output folder, or same folder to resume: ').strip().strip('"')
    if not args.fasta or not args.output:
        parser.error('Provide --fasta and --output, or --wizard')
    try:
        run(args.fasta, args.output)
        print('Verified sequence inventory: ' + str(Path(args.output).resolve() / 'report.html'))
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, 'Sequence inventory failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
