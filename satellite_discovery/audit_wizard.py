"""Interactive front end for read-only audits of existing QC results."""
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .qc_audit import audit, render_report
from .sequence_downloader import write_json


def find_qc_folders(folder):
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Paste a folder path, not a report filename')
    if (folder / 'qc.json').is_file():
        return [folder]
    return sorted(p.parent for p in folder.glob('phase3/*/qc/qc.json'))


def main():
    print('Audit an existing QC run. No downloads or repeat filtering.\n', flush=True)
    try:
        folder = input('Paste the full run-folder path, then press Enter: ').strip().strip('"')
        if not folder:
            raise ValueError('A run-folder path is required')
        choices = find_qc_folders(folder)
        if not choices:
            raise ValueError('No QC results found. Choose the folder containing report.html, or the qc folder containing qc.json')
        selected = 0
        if len(choices) > 1:
            for index, path in enumerate(choices, 1):
                print(f'{index}. {path.parent.name}')
            selected = int(input('Enter the run number to audit: ')) - 1
            if not 0 <= selected < len(choices):
                raise ValueError('The selected run number is outside the list')
        print('1. Verify checksums and saved counts (usually seconds)')
        print('2. Also recount all reads and check pairs (can take several minutes)')
        mode = input('Enter 1 or 2 [1]: ').strip() or '1'
        if mode not in {'1', '2'}:
            raise ValueError('Choose 1 or 2')
        result = audit(choices[selected], full=mode == '2', progress=lambda text: print(text, flush=True))
        name = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]
        destination = Path(__file__).resolve().parents[1] / 'audits' / name
        destination.mkdir(parents=True, exist_ok=False)
        write_json(destination / 'audit.json', result)
        report = destination / 'report.html'
        report.write_text(render_report(result), encoding='utf-8')
        print('PASS: ' + str(report), flush=True)
        try:
            webbrowser.open(report.as_uri())
        except OSError:
            print('Open the report path above in your browser.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        print('Audit failed: ' + str(exc), flush=True)
        return 1
    except KeyboardInterrupt:
        print('\nAudit cancelled. Existing QC files are unchanged.', flush=True)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
