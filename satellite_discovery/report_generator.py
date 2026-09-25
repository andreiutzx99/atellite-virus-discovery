import csv
import html
import json
import hashlib
from pathlib import Path
from . import __version__


def write_reports(directory, rows):
    directory = Path(directory)
    (directory / "datasets.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    columns = list(rows[0]) if rows else ["run_accession", "selection", "warnings"]
    with (directory / "datasets.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            values = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            # Prevent metadata from becoming executable spreadsheet formulas.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v
                             for k, v in values.items()})
    display = ["run_accession", "proposed_helper", "study_accession", "library_strategy", "total_spots", "selection", "exclusion_reasons", "warnings"]
    if any('scope' in row for row in rows):
        display.insert(6, 'scope')
    table = "".join("<tr>" + "".join("<td>" + html.escape(str(r.get(k) or "unknown")) + "</td>" for k in display) + "</tr>" for r in rows)
    phase3 = directory / "phase3" / "manifest.json"
    stage_content = '<h2>Progress: metadata search completed</h2><p>Reads have not been downloaded or processed in this output folder. To continue, choose stage 2 in the launcher or use <code>--stage qc</code>.</p>'
    if phase3.exists():
        manifest = json.loads(phase3.read_text(encoding="utf-8"))
        def esc(value):
            return html.escape(str(value))
        stage_content = '<h2>Download and QC: ' + esc(manifest['status']) + '</h2>'
        stage_content += '<p>This is read preparation, not satellite detection or known-positive biological validation. Mapping, assembly and candidate analysis have not run.</p>'
        stage_content += '<table><tr><th>Run</th><th>Status</th><th>Provider</th><th>Input reads</th><th>Retained reads</th><th>Warnings</th></tr>'
        for item in manifest['runs']:
            stage_content += '<tr>' + ''.join(
                '<td>' + esc(item.get(key, 'not measured')) + '</td>'
                for key in ['accession', 'status', 'provider', 'input_reads', 'retained_reads', 'warnings']
            ) + '</tr>'
        stage_content += '</table>'
        providers = manifest.get('provider_registry', [])
        if providers:
            stage_content += '<h3>Registered acquisition providers</h3><ul>'
            for provider in providers:
                stage_content += (
                    '<li><strong>' + esc(provider.get('name', 'unknown')) + '</strong>: '
                    + esc(provider.get('mechanism', '')) + ' — '
                    + '<a href="' + html.escape(str(provider.get('documentation', '')), quote=True)
                    + '">documentation</a></li>'
                )
            stage_content += '</ul>'
        for item in manifest['runs']:
            attempts = item.get('acquisition_attempts', [])
            if attempts:
                stage_content += (
                    '<details><summary>Acquisition attempts for ' + esc(item.get('accession', 'unknown'))
                    + '</summary><pre>' + esc(json.dumps(attempts, indent=2)) + '</pre></details>'
                )
        for item in manifest['runs']:
            accession = item.get('accession', '')
            # Reports are generated only for validated archive accessions.
            import re
            if not re.fullmatch(r'[SED]RR\d+', accession):
                continue
            qc_path = directory / 'phase3' / accession / 'qc' / 'qc.json'
            if item.get('status') != 'complete' or not qc_path.exists():
                continue
            qc = json.loads(qc_path.read_text(encoding='utf-8'))
            stage_content += '<h3>QC metrics: ' + esc(accession) + '</h3><table><tr><th>Metric</th><th>Before</th><th>After</th></tr>'
            for key, label, percent in [('reads', 'Reads', False), ('bases', 'Bases', False), ('mean_phred', 'Mean Phred', False), ('q20_fraction', 'Q20 bases', True), ('q30_fraction', 'Q30 bases', True), ('gc_fraction_all_bases', 'GC among all bases', True)]:
                values = []
                for side in ['before', 'after']:
                    value = qc[side].get(key)
                    values.append('not measured' if value is None else f'{value:.1%}' if percent else f'{value:,.2f}' if isinstance(value, float) else f'{value:,}')
                stage_content += '<tr><td>' + label + '</td>' + ''.join('<td>' + esc(value) + '</td>' for value in values) + '</tr>'
            stage_content += '</table><p>After metrics include surviving paired, orphan and single reads. Filtering reasons: ' + esc(qc['rejection_reasons']) + '</p>'
        if manifest.get('errors'):
            stage_content += '<h3>Errors</h3><pre>' + esc(json.dumps(manifest['errors'], indent=2)) + '</pre>'
        plan_path = directory / 'phase3' / 'download_plan.json'
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding='utf-8'))
            stage_content += '<h3>Download selection</h3><p>Eligible runs are selected whole, without splitting read pairs. ENA FASTQ checksums are preferred; eligible SRR runs can use the documented NCBI SRA Toolkit fallback when its tools are installed. The default pilot budget is one run and 1,000 MB.</p>'
            stage_content += '<p>Planned input reservation: ' + esc(round(plan['planned_bytes'] / 1_000_000, 1)) + ' MB. Budget: ' + esc(round(plan['max_bytes'] / 1_000_000, 1)) + ' MB.</p>'
            if plan.get('unknown_size_accessions'):
                stage_content += '<p>Size is not listed by the primary provider for: ' + esc(', '.join(plan['unknown_size_accessions'])) + '. Each selected run reserves the full remaining byte budget; this is a cap, not an estimated download size.</p>'
            stage_content += '<details><summary>Why other runs were skipped</summary><ul>' + ''.join('<li>' + esc(r['accession']) + ': ' + esc(r['reason']) + '</li>' for r in plan['skipped']) + '</ul></details>'
        if manifest['status'] == 'no_suitable_downloads':
            stage_content += '<p><strong>No files were downloaded.</strong> Review the skipped-run reasons. If all runs exceed the budget, choose a larger budget in a new output folder. NCBI fallback is limited to eligible SRR runs and requires the SRA Toolkit.</p>'
        if manifest['status'] == 'dependency_missing':
            stage_content += '<p><strong>Acquisition stopped because a registered provider dependency is missing.</strong> The failed provider and required tools are listed in the attempt details.</p>'
        stage_content += '<p>QC uses an explicit portable baseline: exact common Illumina adapter matching, end-quality trimming and read filtering. This is not fastp. Original, rejected and orphan reads are preserved. Detailed metrics and checksums are in <code>phase3/&lt;accession&gt;/qc/qc.json</code>.</p>'
    (directory / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Dataset discovery report</title>'
        '<style>body{font:16px system-ui;margin:3rem;background:#f5f8fb;color:#172b42}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd5df;text-align:left}td{max-width:360px;overflow-wrap:anywhere}</style>'
        '<h1>Public sequencing preparation report</h1><p>Software version ' + __version__ + '</p>' + stage_content + '<h2>Dataset shortlist</h2><p>No satellite candidates or infection calls have been generated.</p>'
        f'<p>{len(rows)} runs; {sum(r["selection"] != "excluded" for r in rows)} eligible for review. Spots are archive sequencing units, not mapped read depth.</p>'
        '<table><thead><tr>' + ''.join('<th>' + k + '</th>' for k in display) + '</tr></thead><tbody>' + table + '</tbody></table></html>', encoding="utf-8")
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists():
        metadata_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        metadata_manifest['output_sha256'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                            for name in ('datasets.json', 'datasets.csv', 'report.html')}
        from .sequence_downloader import write_json
        write_json(manifest_path, metadata_manifest)
