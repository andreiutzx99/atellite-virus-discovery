"""Unified local launcher for descriptive review tools and existing reports."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import subprocess
import sqlite3
import webbrowser


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


def open_report(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower()!='.html':
        raise ValueError('Choose an existing HTML report file')
    opened=webbrowser.open(path.as_uri())
    print(('Opened report: ' if opened else 'No browser available; open this report on your desktop: ')+str(path))
    return path


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
        from .alignment_adapter import run as run_sam
        source = ask('Existing SAM, gzip-SAM, BAM or CRAM path')
        output = ask('SAM coverage output folder')
        reference = ask('Local CRAM reference FASTA') if Path(source).suffix.lower() == '.cram' else None
        run_sam(source, output, reference)
    elif choice == '9':
        from .blast_import import run
        features, references, hits = ask('Feature lengths CSV'), ask('Reference provenance CSV'), ask('Existing BLAST outfmt 6 table')
        output = ask('BLAST import output folder')
        run(features, references, hits, output)
    elif choice == '10':
        from .audit_wizard import main as audit_main
        if audit_main():
            raise ValueError('QC integrity audit did not complete')
        return 'QC audit report path printed above'
    elif choice == '11':
        from .dependency_review import run
        return run(Path(__file__).resolve().parents[1], ask('New dependency report folder'))
    elif choice == '12':
        from .artifact_workflow import run
        return run(ask('Workflow JSON specification'), ask('Workflow output folder'))
    elif choice == '13':
        from .local_comparison import compare
        query, reference, roles = ask('Supplied query FASTA'), ask('Supplied reference FASTA'), ask('Reference roles/provenance CSV')
        output = ask('BLAST comparison output folder')
        compare(query, reference, roles, output)
    elif choice == '14':
        from .context_review import run_context
        samples, observations = ask('Context samples CSV'), ask('Observations CSV')
        output = ask('Context report folder')
        run_context(samples, observations, output)
    elif choice == '15':
        from .context_review import run_quantitative
        source = ask('Paired quantitative measurements CSV')
        output = ask('Quantitative report folder')
        run_quantitative(source, output)
    elif choice == '16':
        from .sequence_quality import run
        source = ask('Supplied FASTA')
        output = ask('Sequence quality descriptor folder')
        run(source, output)
    elif choice == '17':
        from .reference_snapshot import snapshot
        source = ask('Pinned reference snapshot JSON')
        output = ask('New reference snapshot folder')
        snapshot(source, output)
    elif choice == '18':
        from .portable_setup import install
        install(Path(__file__).resolve().parents[1] / '.tools')
        return 'Portable BLAST installation verified; use menu 11 for a version report'
    elif choice == '19':
        from .sra_conversion import convert
        source = ask('Existing local SRA archive')
        output = ask('New conversion output folder')
        convert(source, output)
    elif choice == '20':
        from .artifact_workflow import inspect_configuration
        result=inspect_configuration(ask('Workflow JSON specification to inspect'))
        print(json.dumps(result,indent=2))
        return 'Configuration inspected; no stages executed or output folders created'
    elif choice == '21':
        return open_report(ask('Existing HTML report path'))
    elif choice == '22':
        from .reference_snapshot import compare_snapshots
        previous,current=ask('Previous snapshot folder'),ask('Current snapshot folder')
        output=ask('New snapshot comparison output folder')
        compare_snapshots(previous,current,output)
    elif choice == '23':
        from .artifact_benchmark import run
        datasets,expectations,artifacts=ask('Dataset status CSV'),ask('Expected file digests CSV'),ask('Observed artifact CSV')
        output=ask('Benchmark report folder')
        run(datasets,expectations,artifacts,output)
    else:
        raise ValueError('Choose a number from 0 to 23')
    return Path(output).resolve() / 'report.html'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--choice', choices=[str(n) for n in range(1,24)])
    args = parser.parse_args()
    while True:
        print('\n1 Library metadata review\n2 Observation comparisons\n3 Sequence inventory\n4 Supplied alignment blocks coverage\n5 Contamination evidence review\n6 Link catalogue imports\n7 Existing report dashboard\n8 Supplied alignment coverage (SAM/BAM/CRAM)\n9 Import existing BLAST table\n10 Audit existing QC integrity\n11 Check optional dependency versions\n12 Run artifact workflow\n13 Local supplied-reference BLAST comparison\n14 Supplied study context\n15 Supplied quantitative associations\n16 Sequence quality descriptors\n17 Pinned reference snapshot\n18 Set up portable Windows BLAST\n19 Convert local SRA archive (optional Toolkit)\n0 Exit')
        try:
            print('20 Inspect workflow configuration\n21 Open an existing report\n22 Compare reference snapshots\nUse 12 with the same specification/output folder to resume. Outputs remain at the folder you select.')
            print('23 Evaluate supplied artifact digests and control counts')
            choice = args.choice or input('Choose a review: ').strip()
            if choice == '0':
                return
            path = launch(choice)
            print('Report: ' + str(path))
        except (OSError, ValueError, KeyError, TypeError, csv.Error, sqlite3.Error, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
            print('Review did not complete: ' + str(exc))
            print('Check the named input, output-folder permissions, disk space and menu 11 dependencies. For a workflow failure, open report.html in its output folder; failed results are not valid negative results.')
            if args.choice:
                parser.exit(1)
        except (EOFError, KeyboardInterrupt):
            print('\nStopped. Existing stages were not restarted.')
            return
        if args.choice:
            return


if __name__ == '__main__':
    main()
