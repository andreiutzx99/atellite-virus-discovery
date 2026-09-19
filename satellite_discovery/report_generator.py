import csv
import html
import json
from pathlib import Path


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
    display = ["run_accession", "proposed_helper", "study_accession", "library_strategy", "total_spots", "selection", "warnings"]
    table = "".join("<tr>" + "".join("<td>" + html.escape(str(r.get(k) or "unknown")) + "</td>" for k in display) + "</tr>" for r in rows)
    (directory / "report.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Dataset discovery report</title>'
        '<style>body{font:16px system-ui;margin:3rem;background:#f5f8fb;color:#172b42}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ccd5df;text-align:left}td{max-width:360px;overflow-wrap:anywhere}</style>'
        '<h1>Public sequencing dataset shortlist</h1><p>Phase 2 metadata report. No reads have been analysed; no satellite candidates or infection calls have been generated.</p>'
        f'<p>{len(rows)} runs; {sum(r["selection"] != "excluded" for r in rows)} eligible for review. Spots are archive sequencing units, not mapped read depth.</p>'
        '<table><thead><tr>' + ''.join('<th>' + k + '</th>' for k in display) + '</tr></thead><tbody>' + table + '</tbody></table></html>', encoding="utf-8")
