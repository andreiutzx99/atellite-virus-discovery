"""Verify an already completed live run without network or recomputing QC.

Usage: python scripts/verify_live_replay.py runs/phase3-live-proof
Writes compact evidence under docs/, without reads or sequence content.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from satellite_discovery import __version__
from satellite_discovery.quality_control import QCConfig
from satellite_discovery.read_workflow import prepare_reads
from satellite_discovery.report_generator import write_reports
from satellite_discovery.workflow import discover


def main():
    directory = Path(sys.argv[1]).resolve()
    old = json.loads((directory / 'phase3' / 'manifest.json').read_text())
    if old['status'] != 'complete':
        raise RuntimeError('This verification requires a completed live download/QC run')
    before = {r['accession']: json.loads((directory / 'phase3' / r['qc_report']).read_text())
              for r in old['runs']}
    meta = json.loads((directory / 'parameters.json').read_text())
    params = old['parameters']
    qc_config = QCConfig(**{**params['qc'], 'adapters': tuple(params['qc']['adapters'])})
    with patch('satellite_discovery.database_query.urlopen', side_effect=AssertionError('Metadata network prohibited')), \
         patch('satellite_discovery.sequence_downloader.urlopen', side_effect=AssertionError('Read network prohibited')), \
         patch('satellite_discovery.quality_control.records', side_effect=AssertionError('QC should reuse verified outputs')):
        discover(meta['helper'], meta['experiment_limit'], meta['min_spots'], meta['include_study_context'],
                 directory, offline=True, query=meta['query'])
        after = prepare_reads(directory, params['max_runs'], params['max_bytes'], offline=True, qc_config=qc_config)
    if after['status'] != 'complete':
        raise AssertionError('Replay did not complete')
    for item in after['runs']:
        current = json.loads((directory / 'phase3' / item['qc_report']).read_text())
        if current['output_sha256'] != before[item['accession']]['output_sha256']:
            raise AssertionError('QC output checksums changed')
    rows = json.loads((directory / 'datasets.json').read_text())
    write_reports(directory, rows)
    summary = {'software_version': __version__, 'software_test_evidence': 'Separately recorded in docs/STATUS.md',
               'live_started_utc': old['started_utc'], 'live_finished_utc': old['finished_utc'],
               'live_metadata_runs': len(rows), 'offline_network_disabled': True,
               'recomputed_qc': False, 'identical_qc_output_hashes': True,
               'biological_validation': 'not_performed', 'runs': []}
    for item in old['runs']:
        qc = before[item['accession']]
        summary['runs'].append({'accession': item['accession'], 'downloads': item['downloads'],
                                'before': qc['before'], 'after': qc['after'], 'counts': qc['counts'],
                                'rejection_reasons': qc['rejection_reasons'], 'output_sha256': qc['output_sha256']})
    destination = Path(__file__).resolve().parents[1] / 'docs' / 'phase3-smoke-results.json'
    destination.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({'runs': [{k: r[k] for k in ['accession', 'status', 'input_reads', 'retained_reads']} for r in after['runs']],
                      'offline_replay': 'passed', 'evidence': str(destination)}, indent=2))


if __name__ == '__main__':
    main()
