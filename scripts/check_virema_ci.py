"""Run bounded positive/negative ViReMa checks using the pinned upstream commit."""
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
COMMIT = '481defd7c340bb52fa80748a89d478be9c265f64'
REPOSITORY = 'https://github.com/Routh-Lab/ViReMaDocker.git'
SOURCE_PATHS = {
    'ViReMa.py': 'src/ViReMa_0.25/ViReMa.py',
    'ConfigViReMa.py': 'src/ViReMa_0.25/ConfigViReMa.py',
    'Compiler_Module.py': 'src/ViReMa_0.25/Compiler_Module.py',
}
BOWTIE_PATHS = {
    'bowtie': 'src/bowtie-0.12.9/bowtie',
    'bowtie-build': 'src/bowtie-0.12.9/bowtie-build',
    'bowtie-inspect': 'src/bowtie-0.12.9/bowtie-inspect',
}
PINNED_BOWTIE_SHA256 = {
    'bowtie': '95d87272268ec455f2bea7e9c03bdde7e03da8af87c1eb33dee000dace10f682',
    'bowtie-build': 'b5bbc660d29afd372eb2929c8ee14fe98c01763126f41470a69a786c135e7cf7',
    'bowtie-inspect': '91aba905857d56b9d3350f107ae616b8371f8e769bfccfab7e6ea8c5505c6504',
}
MAX_DIAGNOSTIC = 8000


def run_git(arguments, cwd, timeout=120, text=True):
    return subprocess.run(
        ['git', *arguments], cwd=cwd, capture_output=True, text=text,
        errors='replace' if text else None, timeout=timeout, check=True,
    )


def write_synthetic_inputs(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sequence = ''.join(
        random.Random(392 + index).choice('ACGT') for index in range(1500)
    )
    reference = folder / 'reference.fasta'
    reference.write_text('>SYNTHETIC_REF\n' + sequence + '\n', encoding='ascii')
    inputs = {}
    layouts = {
        'positive': [sequence[199:259] + sequence[749:809]] * 8,
        'negative': [sequence[199:319]] * 8,
    }
    for layout, reads in layouts.items():
        path = folder / (layout + '.fastq')
        with path.open('w', encoding='ascii', newline='\n') as target:
            for number, read in enumerate(reads, 1):
                target.write(f'@{layout}_{number}\n{read}\n+\n{"I" * 120}\n')
        inputs[layout] = path
    return reference, inputs


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    report_dir = ROOT / '.tools' / f'virema-diagnostic-{os.getpid()}'
    report_dir.mkdir(parents=True, exist_ok=False)
    report_path = report_dir / 'report.json'
    report = {
        'schema': 'virema-artificial-diagnostic-v1',
        'upstream_repository': REPOSITORY,
        'upstream_commit': COMMIT,
        'status': 'failed',
        'runs': {},
        'diagnostics': [],
    }
    report['runtime_platform'] = {
        'system': platform.system(),
        'machine': platform.machine(),
    }
    old_env = {key: os.environ.get(key) for key in ('VIREMA_HOME', 'PATH')}
    failure = None
    try:
        with tempfile.TemporaryDirectory(prefix='virema-ci-') as temporary:
            temporary = Path(temporary)
            checkout = temporary / 'checkout'
            checkout.mkdir()
            run_git(['init', '-q'], checkout)
            run_git(['fetch', '--depth=1', REPOSITORY, COMMIT], checkout)
            fetched = run_git(['rev-parse', 'FETCH_HEAD'], checkout).stdout.strip()
            if fetched != COMMIT:
                raise AssertionError(f'fetched commit mismatch: {fetched}')
            tree = set(run_git(
                ['ls-tree', '-r', '--name-only', 'FETCH_HEAD'], checkout
            ).stdout.splitlines())
            source_home = temporary / 'virema'
            source_home.mkdir()
            binary_home = temporary / 'bin'
            binary_home.mkdir()
            extracted = {}
            for name, relative in SOURCE_PATHS.items():
                if relative not in tree:
                    raise AssertionError(f'pinned source path missing: {relative}')
                destination = source_home / name
                destination.write_bytes(run_git(
                    ['show', f'FETCH_HEAD:{relative}'], checkout, text=False
                ).stdout)
                extracted[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
            for name, relative in BOWTIE_PATHS.items():
                if relative not in tree:
                    raise AssertionError(f'pinned Bowtie path missing: {relative}')
                destination = binary_home / name
                destination.write_bytes(run_git(
                    ['show', f'FETCH_HEAD:{relative}'], checkout, text=False
                ).stdout)
                destination.chmod(0o755)
                extracted[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
                report['extracted_sha256'] = dict(extracted)
                report.setdefault('bowtie_hash_verification', {})[name] = {
                    'expected_sha256': PINNED_BOWTIE_SHA256[name],
                    'extracted_sha256': extracted[name],
                    'extracted_hash_match':
                        extracted[name] == PINNED_BOWTIE_SHA256[name],
                }
                if extracted[name] != PINNED_BOWTIE_SHA256[name]:
                    raise AssertionError(
                        f'{name} binary SHA256 differs from the audited Linux x86_64 binary'
                    )

            os.environ['VIREMA_HOME'] = str(source_home)
            os.environ['PATH'] = str(binary_home) + os.pathsep + (old_env['PATH'] or '')
            sys.path.insert(0, str(ROOT))
            from satellite_discovery.virema_adapter import ViReMaDVGAdapter

            adapter = ViReMaDVGAdapter(timeout=180, max_bytes=400_000_000)
            dependency = adapter.inspect_dependency()
            report['dependency_inspection'] = dependency
            report['extracted_sha256'] = extracted
            dependency_rows = {
                row.get('tool'): row for row in dependency.get('dependencies', [])
            }
            for name, expected_hash in PINNED_BOWTIE_SHA256.items():
                report['bowtie_hash_verification'][name].update({
                    'adapter_sha256': dependency_rows.get(name, {}).get('sha256'),
                    'adapter_hash_match':
                        dependency_rows.get(name, {}).get('pinned_sha256_match'),
                    'version_output':
                        dependency_rows.get(name, {}).get('version_output', '')[:1000],
                })
            if platform.system() != 'Linux' or platform.machine().lower() not in {
                    'x86_64', 'amd64'}:
                raise RuntimeError('The pinned real-runtime diagnostic requires Linux x86_64')
            for name, expected_hash in PINNED_BOWTIE_SHA256.items():
                row = dependency_rows.get(name, {})
                if (extracted.get(name) != expected_hash
                        or row.get('sha256') != expected_hash
                        or row.get('pinned_sha256_match') is not True):
                    raise RuntimeError(
                        f'{name} did not pass the pinned executable SHA256 check'
                    )
            if dependency.get('status') != 'available':
                raise RuntimeError(
                    'Pinned ViReMa/Bowtie dependency inspection failed: '
                    + str(dependency.get('reason', 'unknown reason'))
                )
            if dependency.get('source_commit') != COMMIT:
                raise AssertionError('adapter did not identify the pinned source commit')

            version = subprocess.run(
                [sys.executable, '-c',
                 'import json,numpy,platform; print(json.dumps('
                 '{"python":platform.python_version(),"numpy":numpy.__version__}))'],
                capture_output=True, text=True, errors='replace', timeout=15,
                check=True,
            )
            report['python_numpy'] = json.loads(version.stdout)
            reference, reads = write_synthetic_inputs(report_dir / 'fixtures')
            expected = {
                'positive': {
                    'status': 'DVG_EVIDENCE_DETECTED', 'event_count': 1,
                    'breakpoints': (259, 750), 'support': 8,
                },
                'negative': {
                    'status': 'NO_DVG_EVIDENCE_DETECTED', 'event_count': 0,
                    'breakpoints': None, 'support': None,
                },
            }
            for layout in ('positive', 'negative'):
                sample = 'artificial_' + layout
                output = report_dir / layout
                outcome = adapter.execute(
                    {'reads': reads[layout], 'reference': reference},
                    output, {'sample_id': sample},
                )
                if outcome.execution != 'executed':
                    raise AssertionError(f'{layout}: expected a fresh external-tool execution')
                native = output / 'raw' / 'Virus_Recombination_Results.txt'
                evidence_path = output / 'evidence.json'
                summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
                evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
                want = expected[layout]
                if (summary.get('status') != want['status']
                        or summary.get('event_count') != want['event_count']
                        or evidence.get('status') != want['status']
                        or len(evidence.get('events', [])) != want['event_count']):
                    raise AssertionError(f'{layout}: unexpected normalized status or event count')
                if layout == 'positive':
                    event = evidence['events'][0]
                    if (event.get('breakpoint_1'), event.get('breakpoint_2'),
                            event.get('supporting_read_count')) != (259, 750, 8):
                        raise AssertionError('positive event coordinates/support differ')
                    expected_native = (
                        b'@NewLibrary: SYNTHETIC_REF_to_SYNTHETIC_REF\n'
                        b'259_to_750_#_8\t\n@EndofLibrary\n'
                    )
                    if native.read_bytes() != expected_native:
                        raise AssertionError('positive native ViReMa output differs')
                elif native.read_bytes() != b'':
                    raise AssertionError('negative native ViReMa output is not empty')

                raw_digest = sha256(native)
                evidence_digest = sha256(evidence_path)
                summary_digest = sha256(output / 'summary.json')
                validated = adapter.validate_outputs(
                    output, adapter.validate_config({'sample_id': sample})
                )
                if (validated.get('raw_output_sha256') != raw_digest
                        or validated.get('evidence_sha256') != evidence_digest):
                    raise AssertionError(f'{layout}: returned output hashes do not match files')
                reused = adapter.execute(
                    {'reads': reads[layout], 'reference': reference},
                    output, {'sample_id': sample},
                )
                if (reused.execution != 'verified_reuse'
                        or reused.output_inventory != outcome.output_inventory
                        or reused.manifest_sha256 != outcome.manifest_sha256
                        or sha256(native) != raw_digest
                        or sha256(evidence_path) != evidence_digest
                        or sha256(output / 'summary.json') != summary_digest):
                    raise AssertionError(f'{layout}: reuse changed result or raw/normalized hashes')
                report['runs'][layout] = {
                    'status': summary['status'],
                    'event_count': summary['event_count'],
                    'event': ({
                        'breakpoint_1': evidence['events'][0]['breakpoint_1'],
                        'breakpoint_2': evidence['events'][0]['breakpoint_2'],
                        'supporting_read_count':
                            evidence['events'][0]['supporting_read_count'],
                    } if evidence['events'] else None),
                    'raw_output_sha256': validated['raw_output_sha256'],
                    'evidence_sha256': validated['evidence_sha256'],
                    'summary_sha256': summary_digest,
                    'reuse_verified': True,
                }
            report['status'] = 'passed'
    except BaseException as error:
        failure = error
        report['error'] = f'{type(error).__name__}: {error}'[:MAX_DIAGNOSTIC]
        report['traceback'] = traceback.format_exc()[-MAX_DIAGNOSTIC:]
        report['diagnostics'].extend(_recent_logs(report_dir))
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8'
        )
    print(json.dumps({
        'status': report['status'],
        'report': str(report_path.relative_to(ROOT)),
        'runs': report.get('runs', {}),
        'error': report.get('error'),
    }, sort_keys=True))
    if failure:
        raise failure


def _recent_logs(directory):
    rows = []
    for path in sorted(directory.glob('**/*.log')):
        try:
            content = path.read_bytes()[-MAX_DIAGNOSTIC:].decode('utf-8', errors='replace')
            rows.append({
                'path': str(path.relative_to(directory)),
                'tail': content,
            })
        except OSError:
            continue
    return rows[:12]


if __name__ == '__main__':
    main()