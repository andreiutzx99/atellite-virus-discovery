"""Compact provenance for existing-artifact workflows; never embeds input data."""
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

from . import __version__
from .sequence_downloader import checksum, write_json


def environment():
    package = Path(__file__).resolve().parent
    source_hashes = {p.name: checksum(p) for p in sorted(package.iterdir())
                     if p.suffix in {'.py', '.json'} and p.is_file()}
    revision, dirty = None, None
    if (package.parent/'.git').exists():
        try:
            revision = subprocess.run(['git', '-C', str(package.parent), 'rev-parse', 'HEAD'],
                                      capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            dirty = bool(subprocess.run(['git', '-C', str(package.parent), 'status', '--porcelain'],
                                       capture_output=True, text=True, timeout=5, check=True).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            revision = None
    packages = {}
    for name in ('pysam', 'matplotlib'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {'software_version': __version__, 'git_revision': revision, 'git_dirty': dirty,
            'source_sha256': hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
            'source_files': source_hashes, 'python': sys.version, 'platform': platform.platform(),
            'optional_package_versions': packages, 'command': sys.argv}


def bounded_json(path, root):
    if not path.resolve().is_relative_to(root) or path.stat().st_size > 2_000_000:
        raise ValueError('Provenance file is outside the workflow or exceeds 2 MB')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Provenance file must contain an object')
    return value


def save(output, result):
    stages = []
    for item in result['stages']:
        directory = output/item['id']
        row = {**item, 'output_directory': str(directory), 'records': {}}
        for name in ('manifest.json', 'commands.json', 'command.json', 'decoder.json'):
            path = directory/name
            if path.is_file():
                try:
                    content=bounded_json(path, output)
                    row['records'][name] = {'sha256': checksum(path), 'content': content}
                except (OSError, ValueError) as exc:
                    row['records'][name] = {'status': 'unreadable', 'error': str(exc)}
        # The validated snapshot specification contains all supplied reference versions.
        stages.append(row)
    bundle = {'schema': 'artifact-reproducibility-v1', 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'status': result['status'], 'environment': result['environment'],
              'configuration': result['configuration'], 'identity': result['identity'],
              'registry': result.get('registry', []),
              'started_utc': result['started_utc'], 'finished_utc': result.get('finished_utc'),
              'output_directory': str(output), 'stages': stages,
              'notes': ['Contains paths, hashes and recorded commands, not input sequence data.',
                        'Package versions indicate installation only. External tool versions are recorded by stages that execute them.',
                        'Missing records for pending/failed stages are not successful negative results.']}
    write_json(output/'reproducibility.json', bundle)
