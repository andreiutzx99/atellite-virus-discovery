"""Read-only integrity audit of existing portable QC output, across versions."""
import argparse
import html
import json
import re
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

from .quality_control import records, pair_id, check_mate
from .sequence_downloader import checksum, write_json

BASE = {'clean_single.fastq.gz', 'rejected.fastq.gz'}
PAIRED = {'clean_R1.fastq.gz', 'clean_R2.fastq.gz',
          'orphan_R1.fastq.gz', 'orphan_R2.fastq.gz'}


def render_report(result):
    """Render audit evidence without implying biological validation."""
    esc = html.escape
    full = result['fastq_records_recounted']
    mode = 'Checksums, FASTQ record counts and paired identifiers' if full else 'Checksums and saved QC accounting; FASTQ records not recounted'
    rows = []
    for item in result['files']:
        count = result['observed_reads_by_file'].get(item['name'])
        reads = f'{count:,}' if count is not None else 'Not recounted'
        rows.append(f'<tr><td>{esc(item["name"])}</td><td>{reads}</td><td>{item["bytes"]:,}</td><td>Verified</td></tr>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>QC integrity audit</title><style>body{font:17px system-ui;margin:3rem;'
            'color:#172b42;background:#f5f8fb}table{border-collapse:collapse}'
            'td,th{padding:12px;border:1px solid #ccd5df;text-align:left}'
            'p{max-width:85ch;overflow-wrap:anywhere}</style><h1>QC integrity audit</h1>'
            f'<p>Status: <strong>{esc(result["status"])}</strong></p>'
            f'<p>{esc(mode)}</p><p>Source: {esc(result["qc_directory"])}</p>'
            f'<p>Retained reads: <strong>{result["retained_reads_reported"]:,}</strong>. '
            f'Rejected reads: {result["rejected_reads_reported"]:,}.</p>'
            '<table><tr><th>File</th><th>Observed reads</th><th>Compressed bytes</th><th>SHA256</th></tr>'
            + ''.join(rows) + '</table><p>' + esc(result['scope']) + '</p>'
            '<p>The audit reads source files without changing them. It does not repeat QC or download data.</p></html>')


def audit(qc_directory, full=False, progress=print):
    directory = Path(qc_directory).resolve(strict=True)
    marker = directory / 'qc.json'
    marker_hash = checksum(marker)
    qc = json.loads(marker.read_text(encoding='utf-8'))
    if qc.get('status') != 'complete' or qc.get('engine') != 'portable_baseline_phred33':
        raise ValueError('Expected completed portable QC results')
    hashes = qc.get('output_sha256', {})
    if set(hashes) not in (BASE, BASE | PAIRED):
        raise ValueError('Missing or unexpected QC output filenames')
    before, retained = qc['before']['reads'], qc['after']['reads']
    counts = qc['counts']
    rejected = counts.get('rejected_reads', 0)
    values = [before, retained, rejected, *counts.values(), *qc['rejection_reasons'].values()]
    if any(type(n) is not int or n < 0 for n in values):
        raise ValueError('QC counts must be nonnegative integers')
    if (before != retained + rejected or retained != counts.get('retained_reads', 0)
            or rejected != sum(qc['rejection_reasons'].values())
            or retained != 2 * counts.get('retained_pairs', 0)
            + counts.get('retained_orphans', 0) + counts.get('retained_single_reads', 0)):
        raise ValueError('QC read accounting is inconsistent')
    files = []
    for name, expected in sorted(hashes.items()):
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid SHA256 for ' + name)
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory or not path.is_file():
            raise ValueError('Missing or redirected QC output: ' + name)
        progress('Verifying ' + name)
        if checksum(path) != expected:
            raise ValueError('QC checksum mismatch: ' + name)
        files.append({'name': name, 'bytes': path.stat().st_size, 'sha256': expected})
    observed = {}
    if full:
        for name in sorted(set(hashes) - {'clean_R1.fastq.gz', 'clean_R2.fastq.gz'}):
            progress('Recounting ' + name)
            observed[name] = sum(1 for _ in records(directory / name))
        if PAIRED <= set(hashes):
            pairs = 0
            for a, b in zip_longest(records(directory / 'clean_R1.fastq.gz'),
                                   records(directory / 'clean_R2.fastq.gz')):
                if a is None or b is None or pair_id(a[0]) != pair_id(b[0]):
                    raise ValueError('QC pair counts or identifiers do not match')
                check_mate(a[0], '1')
                check_mate(b[0], '2')
                pairs += 1
                if pairs % 1000000 == 0:
                    progress(f'Checked {pairs:,} paired identifiers')
            observed['clean_R1.fastq.gz'] = observed['clean_R2.fastq.gz'] = pairs
        if (observed['rejected.fastq.gz'] != rejected
                or sum(n for name, n in observed.items() if name != 'rejected.fastq.gz') != retained
                or observed.get('clean_R1.fastq.gz', 0) != counts.get('retained_pairs', 0)
                or observed['clean_single.fastq.gz'] != counts.get('retained_single_reads', 0)
                or sum(observed.get(n, 0) for n in ('orphan_R1.fastq.gz', 'orphan_R2.fastq.gz')) != counts.get('retained_orphans', 0)):
            raise ValueError('Observed FASTQ counts differ from the QC record')
    if checksum(marker) != marker_hash:
        raise ValueError('QC record changed during verification')
    return {'status': 'passed', 'kind': 'qc_integrity_audit', 'qc_directory': str(directory),
            'qc_json_sha256': marker_hash, 'source_version': qc['fingerprint']['software_version'],
            'checked_utc': datetime.now(timezone.utc).isoformat(),
            'input_reads_reported': before, 'retained_reads_reported': retained,
            'rejected_reads_reported': rejected, 'files': files,
            'fastq_records_recounted': full, 'observed_reads_by_file': observed,
            'scope': 'File integrity and QC accounting only; no biological analysis or suitability assessment'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qc-dir', required=True)
    parser.add_argument('--output', required=True, help='New audit JSON outside the source QC folder')
    parser.add_argument('--full', action='store_true', help='Also parse all FASTQ records and check paired identifiers')
    parser.add_argument('--html', action='store_true', help='Also save a readable HTML report beside the JSON')
    args = parser.parse_args()
    try:
        source, output = Path(args.qc_dir).resolve(), Path(args.output).resolve()
        if output == source or source in output.parents or output.exists():
            raise ValueError('Choose a new audit file outside the source QC directory')
        html_output = output.with_suffix('.html')
        if args.html and (html_output == output or html_output.exists()):
            raise ValueError('Choose an output name with no existing HTML report')
        result = audit(source, args.full)
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, result)
        if args.html:
            html_output.write_text(render_report(result), encoding='utf-8')
        print('QC integrity audit passed: ' + str(output))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, 'QC audit failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
