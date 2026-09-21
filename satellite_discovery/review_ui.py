"""Unified local launcher for descriptive review tools and existing reports."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import sqlite3


def dashboard(root, output):
    root, output = Path(root).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new dashboard filename')
    candidates = [root / 'manifest.json'] + sorted(root.glob('*/manifest.json'))
    if len(candidates) > 2000:
        raise ValueError('More than 2,000 folders; choose a narrower report root')
    rows = []
    for path in candidates:
        if not path.is_file() or not path.resolve().is_relative_to(root):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                raise ValueError('Manifest too large')
            data = json.loads(path.read_text(encoding='utf-8'))
            status = str(data.get('status', 'unknown'))
        except (ValueError, OSError, AttributeError):
            status = 'unreadable_manifest'
        report = path.parent / 'report.html'
        link = ''
        if report.is_file() and report.resolve().is_relative_to(root):
            link = '<a href="' + html.escape(report.as_uri(), quote=True) + '">Open existing report</a>'
        rows.append('<tr><td>' + html.escape(path.parent.name) + '</td><td>' + html.escape(status) + '</td><td>' + link + '</td></tr>')
    dependencies = {name: 'found on PATH' if shutil.which(name) else 'not found on PATH' for name in ('python', 'java', 'blastn', 'spades.py')}
    body = '<!doctype html><meta charset="utf-8"><title>Review dashboard</title><style>body{font:16px system-ui;margin:2rem}td,th{padding:.5rem;border:1px solid #aaa}table{border-collapse:collapse}</style><h1>Existing review reports</h1><p>Statuses are read from manifests. This dashboard does not verify artifact hashes, run analyses or certify tool functionality.</p><table><tr><th>Folder</th><th>Reported status</th><th>Report</th></tr>' + ''.join(rows) + '</table><h2>PATH dependency discovery</h2><p>Portable project tools may exist outside PATH. Discovery is not runtime testing.</p><ul>' + ''.join('<li>' + html.escape(k + ': ' + v) + '</li>' for k,v in dependencies.items()) + '</ul>'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as target:
        target.write(body)
    return output


def ask(label):
    value = input(label + ': ').strip().strip('"')
    if not value:
        raise ValueError('A path is required')
    return value


def launch(choice):
    if choice == '1':
        from .library_review import review
        source = ask('Existing datasets.json path')
        output = ask('Review output folder')
        review(source, output)
    elif choice == '2':
        from .observation_report import run
        samples, observations = ask('Samples CSV path'), ask('Observations CSV path')
        output = ask('Comparison output folder')
        run(samples, observations, output)
    elif choice == '3':
        from .sequence_catalogue import run
        source = ask('Existing nucleotide FASTA path')
        output = ask('Inventory output folder')
        run(source, output)
    elif choice == '4':
        from .coverage_review import run
        references, samples, blocks = ask('Reference lengths CSV'), ask('Assessed samples CSV'), ask('Alignment blocks CSV')
        output = ask('Coverage output folder')
        run(references, samples, blocks, output)
    elif choice == '5':
        from .contamination_review import run
        features, matches, controls = ask('Feature lengths CSV'), ask('Reference matches CSV'), ask('Technical-control observations CSV')
        output = ask('Evidence output folder')
        run(features, matches, controls, output)
    elif choice == '6':
        from .catalogue_linker import run
        source = ask('Catalogue imports CSV')
        output = ask('Linked catalogue output folder')
        run(source, output)
    elif choice == '7':
        return dashboard(ask('Existing reports root folder'), ask('New dashboard HTML path'))
    elif choice == '8':
        from .coverage_review import run_sam
        source = ask('Existing uncompressed SAM path')
        output = ask('SAM coverage output folder')
        run_sam(source, output)
    else:
        raise ValueError('Choose a number from 0 to 8')
    return Path(output).resolve() / 'report.html'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--choice', choices=list('12345678'))
    args = parser.parse_args()
    while True:
        print('\n1 Library metadata review\n2 Observation comparisons\n3 Sequence inventory\n4 Supplied alignment blocks coverage\n5 Contamination evidence review\n6 Link catalogue imports\n7 Existing report dashboard\n8 Supplied text SAM coverage\n0 Exit')
        try:
            choice = args.choice or input('Choose a review: ').strip()
            if choice == '0':
                return
            path = launch(choice)
            print('Report: ' + str(path))
        except (OSError, ValueError, KeyError, TypeError, csv.Error, sqlite3.Error) as exc:
            print('Review did not complete: ' + str(exc))
            if args.choice:
                parser.exit(1)
        except (EOFError, KeyboardInterrupt):
            print('\nStopped. Existing stages were not restarted.')
            return
        if args.choice:
            return


if __name__ == '__main__':
    main()
