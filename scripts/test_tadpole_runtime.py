"""Test the installed Java assembler using generated random data only."""
import argparse
import hashlib
import html
import json
import random
import shutil
import subprocess
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
COMMIT = '7afa43b1bb3ad07493ac93a67ada4a5ec779f0c0'
ARCHIVE_SHA256 = '36b1c7be738f16185e967e33cab909e660b0f33a905b1fe06043f24a314a3725'


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'running', 'kind': 'synthetic_runtime_test',
              'backend': 'BBTools Tadpole 40.01', 'biological_validation': False,
              'application_discovery_integration': False}
    try:
        java = shutil.which('java')
        if not java:
            raise RuntimeError('Java is missing from PATH. Install Java before repeating this test.')
        archive = PROJECT / '.tools/BBTools-40.01.zip'
        if not archive.is_file() or digest(archive) != ARCHIVE_SHA256:
            raise RuntimeError('The pinned BBTools archive is missing or has a checksum mismatch.')
        base = PROJECT / '.tools/bbtools-40.01'
        prefix = 'BBTools-' + COMMIT + '/current/'
        classpath = base / ('BBTools-' + COMMIT) / 'current'
        # Verify installed runtime contents against the pinned archive before execution.
        with zipfile.ZipFile(archive) as bundle:
            members = [m for m in bundle.infolist() if m.filename.startswith(prefix) and not m.is_dir()]
            if not members:
                raise RuntimeError('Archive contains no runtime files')
            for member in members:
                installed = (base / member.filename).resolve()
                if not installed.is_relative_to(classpath.resolve()) or not installed.is_file():
                    raise RuntimeError('Installed runtime file is missing or outside the expected directory')
                if digest(installed) != hashlib.sha256(bundle.read(member)).hexdigest():
                    raise RuntimeError('Installed runtime checksum mismatch: ' + member.filename)
        version = subprocess.run([java, '-version'], capture_output=True, text=True, check=True, timeout=30)
        result.update(java_version=version.stderr.strip() or version.stdout.strip(),
                      archive_sha256=ARCHIVE_SHA256, verified_runtime_files=len(members))
        rng = random.Random(17292026)
        truth = ''.join(rng.choice('ACGT') for _ in range(1000))
        (output / 'truth.fasta').write_text('>random_software_fixture\n' + truth + '\n', encoding='ascii')
        reads = output / 'reads.fastq'
        count = 0
        with reads.open('w', encoding='ascii', newline='\n') as target:
            for repeat in range(4):
                for start in range(0, 901, 5):
                    target.write(f'@fixture_{repeat}_{start}\n{truth[start:start+100]}\n+\n' + 'I'*100 + '\n')
                    count += 1
        contigs = output / 'contigs.fasta'
        command = [java, '-ea', '-Xmx512m', '-cp', str(classpath), 'assemble.Tadpole',
                   'in=' + str(reads), 'out=' + str(contigs), 'threads=2', 'overwrite=f']
        result['command'] = command
        with (output / 'assembly.log').open('w', encoding='utf-8') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        sequences = [''.join(chunk.splitlines()[1:]).upper()
                     for chunk in contigs.read_text().split('>') if chunk.strip()]
        reverse = truth.translate(str.maketrans('ACGT', 'TGCA'))[::-1]
        if len(sequences) != 1 or sequences[0] not in (truth, reverse):
            raise RuntimeError('Assembly did not exactly reconstruct the random fixture')
        result.update(status='passed', input_reads=count, contig_count=1, contig_length=1000,
                      exact_match_allowing_reverse_complement=True,
                      sha256={name: digest(output / name) for name in
                              ('reads.fastq', 'truth.fasta', 'contigs.fasta', 'assembly.log')})
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        result.update(status='failed', error=str(exc))
    finally:
        (output / 'test_result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        (output / 'report.html').write_text(
            '<!doctype html><meta charset="utf-8"><title>Tadpole runtime test</title>'
            '<h1>Tadpole runtime test: ' + html.escape(result['status']) + '</h1>'
            '<p>Generated random software fixtures only. This checks runtime operation; '
            'it does not validate biological discovery or the full application workflow.</p><pre>'
            + html.escape(json.dumps(result, indent=2)) + '</pre>', encoding='utf-8')
    print(result['status'].upper() + ': ' + str(output / 'report.html'))
    if result.get('error'):
        print(result['error'])
    return result['status'] == 'passed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New folder for synthetic test artifacts')
    args = parser.parse_args()
    try:
        raise SystemExit(0 if run(args.output) else 1)
    except OSError as exc:
        parser.exit(1, str(exc) + '\n')
