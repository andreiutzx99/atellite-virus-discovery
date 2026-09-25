"""Pinned, bounded ViReMa adapter for caller-generated DVG evidence."""
import csv
import hashlib
import html
import inspect
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys

from . import dvg_evidence, sequence_catalogue
from .assembly_adapters import _read_fastq
from .dependency_review import inspect_executable
from .external_tool import ExternalToolAdapter
from .sequence_downloader import checksum, write_json


ADAPTER_VERSION = '1.0'
UPSTREAM_COMMIT = '481defd7c340bb52fa80748a89d478be9c265f64'
CALLER_NAME = 'ViReMa'
CALLER_VERSION = '0.25'
SOURCE_HASHES = {
    'ViReMa.py': 'c4c7cb46db9ac8a0427ef073db918cced451ef8bfb9e81bf906a784396c20486',
    'ConfigViReMa.py': '27bc2f61bae94c754ca80bcff22fa030676629eaddadc49cc24638868876da0e',
    'Compiler_Module.py': '6cfd3687639775fab6592aab4dec90c611b4752e5efc61b4f1964ed2c879c272',
}
BOWTIE_SHA256 = {
    'bowtie': '95d87272268ec455f2bea7e9c03bdde7e03da8af87c1eb33dee000dace10f682',
    'bowtie-build': 'b5bbc660d29afd372eb2929c8ee14fe98c01763126f41470a69a786c135e7cf7',
    'bowtie-inspect': '91aba905857d56b9d3350f107ae616b8371f8e769bfccfab7e6ea8c5505c6504',
}
_SAFE_SAMPLE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
_BOWTIE_VERSION = re.compile(r'\b0\.12\.9\b')
_OUTPUTS = (
    'raw/Virus_Recombination_Results.txt',
    'evidence.json',
    'summary.json',
    'parameters.json',
    'report.html',
)


def _sha(path):
    return checksum(path)


def _regular_file(path, label):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError(f'{label} is missing or unreadable') from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(f'{label} must be a regular non-symlink file')
    return path


def _reference_records(path):
    records = sequence_catalogue.read_fasta(path)
    return {
        identifier: {
            'length': len(sequence),
            'sha256': hashlib.sha256(sequence.encode('ascii')).hexdigest(),
        }
        for identifier, _header, sequence in records
    }


def _catalogue_rows(path):
    if path is None:
        return {}
    rows = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if not {'record_id', 'sequence_sha256', 'length'} <= set(reader.fieldnames or ()):
            raise ValueError('Catalogue records lack required identity columns')
        count = 0
        for row in reader:
            record_id, digest = row.get('record_id'), row.get('sequence_sha256')
            length = row.get('length')
            if (not record_id or not re.fullmatch(r'[a-f0-9]{64}', digest or '')
                    or not isinstance(length, str) or not length.isdigit()):
                raise ValueError('Catalogue records contain invalid identity data')
            rows.setdefault((record_id, digest), []).append(row)
            count += 1
            if count > 200_000:
                raise ValueError('Catalogue records exceed the 200,000-row limit')
    return rows


class ViReMaDVGAdapter(ExternalToolAdapter):
    """Invoke the externally installed, source-pinned ViReMa 0.25 caller."""

    kind = 'dvg_virema'
    module_name = 'dvg.virema'
    evidence_family = 'dvg'
    caller_name = CALLER_NAME
    caller_version = CALLER_VERSION
    input_contracts = {
        'reads': ('validated_fastq',),
        'reference': (
            'raw_fasta', 'canonical_contig_fasta', 'catalogue_fasta',
            'reference_records_fasta',
        ),
        'catalogue_records': ('sequence_catalogue_records',),
    }
    output_contracts = {
        '*Virus_Recombination_Results.txt': 'dvg_raw_output',
        'evidence.json': 'dvg_evidence',
        'summary.json': 'dvg_evidence_summary',
        'parameters.json': 'dvg_parameters',
        'report.html': 'report',
    }

    def __init__(self, *, timeout=180, max_bytes=400_000_000):
        super().__init__(
            kind=self.kind,
            module_name=self.module_name,
            adapter_name='virema-dvg-adapter',
            adapter_version=ADAPTER_VERSION,
            tool_name='ViReMa 0.25 DVG junction caller',
            dependencies=[
                {'name': 'python', 'command': sys.executable, 'version_args': ['--version']},
                *[
                    {'name': name, 'command': name, 'version_args': ['--version']}
                    for name in ('bowtie', 'bowtie-build', 'bowtie-inspect')
                ],
            ],
            input_fields={'reads', 'reference'},
            optional_input_fields={'catalogue_records'},
            output_files=_OUTPUTS,
            timeout=timeout,
            max_bytes=max_bytes,
            stdout_name='stdout.log',
            stderr_name='stderr.log',
            description='Pinned ViReMa virus-virus junction evidence; not a biological classifier.',
        )

    def execute(self, inputs, output, config, context=None):
        try:
            return super().execute(inputs, output, config, context=context)
        except ValueError as error:
            if isinstance(error, dvg_evidence.InvalidDVGResultError):
                raise
            # The shared executor also handles unrelated execution/configuration
            # errors. Only failed integrity checks of a saved result mean that
            # the DVG result itself is invalid rather than an execution failure.
            if str(error).startswith((
                'External-tool manifest is malformed;',
                'External-tool output contract changed;',
                'Existing external-tool stage is not a completed reusable result',
                'External-tool output inventory is malformed',
                'External-tool output integrity failure;',
                'External-tool output path is invalid;',
                'External-tool output contains a link:',
                'External-tool output contains a special file:',
                'External-tool output has an unsafe path:',
            )):
                raise dvg_evidence.InvalidDVGResultError(
                    'Saved ViReMa result failed integrity verification: ' + str(error)
                ) from error
            raise

    @property
    def virema_home(self):
        value = os.environ.get('VIREMA_HOME')
        return Path(value).expanduser().resolve() if value else None

    def validate_config(self, config):
        if not isinstance(config, dict) or set(config) - {
                'sample_id', 'seed', 'mismatches', 'threads'}:
            raise ValueError('ViReMa config accepts only sample_id, seed, mismatches and threads')
        sample_id = config.get('sample_id')
        if not isinstance(sample_id, str) or not _SAFE_SAMPLE.fullmatch(sample_id) or sample_id in {'.', '..'}:
            raise ValueError('sample_id must be a safe identifier of 1 through 128 characters')
        seed = config.get('seed', 25)
        mismatches = config.get('mismatches', 1)
        threads = config.get('threads', 1)
        if type(seed) is not int or not 12 <= seed <= 100:
            raise ValueError('seed must be an integer from 12 through 100')
        if type(mismatches) is not int or not 0 <= mismatches <= 3:
            raise ValueError('mismatches must be an integer from 0 through 3')
        if type(threads) is not int or not 1 <= threads <= 8:
            raise ValueError('threads must be an integer from 1 through 8')
        return {
            'sample_id': sample_id, 'seed': seed,
            'mismatches': mismatches, 'threads': threads,
        }

    def validate_inputs(self, inputs, output, config=None):
        paths = super().validate_inputs(inputs, output, config)
        reads = paths['reads']
        if not reads.name.lower().endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
            raise ValueError('ViReMa reads must have a FASTQ filename extension')
        # The reader enforces single-end FASTQ structure and a minimum of one read.
        sum(1 for _ in _read_fastq(reads))
        _reference_records(paths['reference'])
        if 'catalogue_records' in paths:
            _catalogue_rows(paths['catalogue_records'])
        return paths

    def validate_configured_inputs(self, inputs, output, config):
        return self.validate_inputs(inputs, output, config)

    def inspect_dependency(self, config=None):
        platform_supported = (
            platform.system() == 'Linux' and platform.machine().lower() == 'x86_64'
        )
        if not platform_supported:
            return {
                'status': 'dependency_missing',
                'reason': 'Pinned Bowtie binaries are supported only on Linux x86_64',
                'platform': {'system': platform.system(), 'machine': platform.machine()},
                'dependencies': [],
            }
        home = self.virema_home
        if home is None or not home.is_dir():
            return {'status': 'dependency_missing', 'reason': 'VIREMA_HOME must name the pinned ViReMa source directory',
                    'dependencies': []}
        source_rows = {}
        for name, expected in SOURCE_HASHES.items():
            path = home / name
            try:
                if not path.is_file() or path.is_symlink() or _sha(path) != expected:
                    raise ValueError
            except (OSError, ValueError):
                return {'status': 'dependency_missing',
                        'reason': f'Pinned ViReMa source verification failed: {name}',
                        'source': str(home), 'dependencies': []}
            source_rows[name] = {'path': str(path.resolve()), 'sha256': expected}
        executable_rows = []
        python_row = inspect_executable('python', sys.executable, ('--version',))
        numpy_ok = False
        try:
            result = subprocess.run(
                [sys.executable, '-c', 'import numpy'],
                capture_output=True, text=True, errors='replace', timeout=15, check=False,
            )
            numpy_ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        python_row['numpy_available'] = numpy_ok
        executable_rows.append(python_row)

        bowtie_paths = []
        bin_dir = None
        for name in ('bowtie', 'bowtie-build', 'bowtie-inspect'):
            command = name + ('.exe' if os.name == 'nt' else '')
            path = shutil.which(command)
            row = inspect_executable(name, path or command, ('--version',))
            row['pinned_sha256_match'] = row.get('sha256') == BOWTIE_SHA256[name]
            executable_rows.append(row)
            if (not path or row['status'] != 'version_check_passed'
                    or not _BOWTIE_VERSION.search(row['version_output'])
                    or not row['pinned_sha256_match']):
                continue
            absolute = Path(path).resolve()
            bowtie_paths.append(absolute)
            if bin_dir is None:
                bin_dir = absolute.parent
        same_directory = len(bowtie_paths) == 3 and len({path.parent for path in bowtie_paths}) == 1
        valid_versions = all(
            row['status'] == 'version_check_passed' and _BOWTIE_VERSION.search(row['version_output'])
            for row in executable_rows[1:]
        )
        valid_hashes = all(row.get('pinned_sha256_match') for row in executable_rows[1:])
        available = (
            python_row['status'] == 'version_check_passed' and numpy_ok
            and valid_versions and valid_hashes and same_directory
        )
        return {
            'status': 'available' if available else 'dependency_missing',
            'reason': '' if available else
            'Python with NumPy and the pinned Bowtie 0.12.9 binaries in one directory are required',
            'platform': {'system': platform.system(), 'machine': platform.machine()},
            'source': str(home),
            'source_commit': UPSTREAM_COMMIT,
            'source_sha256': dict(SOURCE_HASHES),
            'source_files': source_rows,
            'bowtie_directory': str(bin_dir) if same_directory else '',
            'dependencies': executable_rows,
        }

    def inspect_dependency_for_config(self, config):
        return self.inspect_dependency(config)

    def build_command(self, executables, inputs, output, config):
        home = self.virema_home
        reads_name = Path(inputs['reads']).name
        local_name = 'reads.fastq.gz' if reads_name.lower().endswith(('.fastq.gz', '.fq.gz')) else 'reads.fastq'
        bowtie_dir = str(Path(executables['bowtie']).resolve().parent)
        command = [
            executables['python'], str((home / 'ViReMa.py').resolve()),
            str((Path(output) / 'reference.fasta').resolve()),
            local_name, 'alignments.sam',
            '--Output_Dir', str((Path(output) / 'raw').resolve()),
            '-Overwrite', '--Aligner_Directory', bowtie_dir,
            '--Seed', str(config['seed']), '--N', str(config['mismatches']),
            '--p', str(config['threads']),
        ]
        if platform.system() == 'Windows':
            command.append('-Windows')
        return command

    def prepare_execution(self, output, inputs, config, manifest):
        output = Path(output)
        raw = output / 'raw'
        raw.mkdir()
        reference = output / 'reference.fasta'
        reads = raw / (
            'reads.fastq.gz'
            if inputs['reads'].name.lower().endswith(('.fastq.gz', '.fq.gz'))
            else 'reads.fastq'
        )
        cwd_reads = output / reads.name
        shutil.copyfile(inputs['reference'], reference)
        shutil.copyfile(inputs['reads'], reads)
        # ViReMa 0.25's MainArgs opens the basename relative to cwd before its
        # later MakeReadDict path is resolved beneath Output_Dir.
        shutil.copyfile(inputs['reads'], cwd_reads)
        if _sha(reference) != manifest['inputs']['reference']['sha256']:
            raise ValueError('Staged reference checksum differs from its declared input')
        if (_sha(reads) != manifest['inputs']['reads']['sha256']
                or _sha(cwd_reads) != manifest['inputs']['reads']['sha256']):
            raise ValueError('Staged reads checksum differs from their declared input')

    def _catalogue_link(self, event, ref_hashes, catalogue):
        matches = catalogue.get((event['reference_id'], ref_hashes[event['reference_id']]['sha256']), [])
        if len(matches) == 1:
            return {'status': 'resolved', 'record_id': matches[0]['record_id'],
                    'sequence_sha256': matches[0]['sequence_sha256']}
        return {'status': 'unresolved', 'reason': 'no exact unique record ID and sequence SHA256 match'}

    def _normalized_events(self, parsed, output, config, manifest, ref_hashes, catalogue):
        raw_path = Path(output) / 'raw/Virus_Recombination_Results.txt'
        raw_hash = _sha(raw_path)
        read_meta = manifest['inputs']['reads']
        reference_meta = manifest['inputs']['reference']
        events = []
        for item in parsed:
            identity = {
                'caller': self.caller_name, 'caller_version': CALLER_VERSION,
                'sample_id': config['sample_id'], 'read_sha256': read_meta['sha256'],
                'reference_sha256': reference_meta['sha256'],
                'library': item['raw_library'], 'entry': item['raw_entry'],
                'line': item['raw_line_number'],
            }
            event_id = 'virema-' + hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
            ).hexdigest()
            events.append({
                'evidence_id': event_id,
                'caller': self.caller_name,
                'caller_version': CALLER_VERSION,
                'sample_id': config['sample_id'],
                'read_artifact_id': Path(read_meta['path']).name,
                'read_artifact_sha256': read_meta['sha256'],
                'reference_id': item['reference_id'],
                'acceptor_reference_id': item['acceptor_reference_id'],
                'reference_sequence_sha256': ref_hashes[item['reference_id']]['sha256'],
                'acceptor_reference_sequence_sha256': ref_hashes[item['acceptor_reference_id']]['sha256'],
                'breakpoint_1': item['breakpoint_1'],
                'breakpoint_2': item['breakpoint_2'],
                'orientation': item['orientation'],
                'supporting_read_count': item['supporting_read_count'],
                'score': None,
                'junction_sequence': None,
                'event_type': item['event_type'],
                'caller_metadata': {
                    'raw_library': item['raw_library'], 'raw_entry': item['raw_entry'],
                },
                'raw_entry': item['raw_entry'],
                'raw_library': item['raw_library'],
                'raw_output_reference': {
                    'path': 'raw/Virus_Recombination_Results.txt',
                    'sha256': raw_hash,
                    'line': item['raw_line_number'],
                    'entry': item['raw_entry'],
                },
                'catalogue_linkage': self._catalogue_link(item, ref_hashes, catalogue),
            })
        return events

    def finalize_outputs(self, output, config, process_result, manifest):
        output = Path(output)
        reads_copy = output / (
            'raw/reads.fastq.gz'
            if (output / 'raw/reads.fastq.gz').is_file()
            else 'raw/reads.fastq'
        )
        read_count = sum(1 for _ in _read_fastq(reads_copy))
        if read_count < 1:
            raise ValueError('ViReMa evaluation requires at least one FASTQ read')
        reference_rows = _reference_records(output / 'reference.fasta')
        native_path = output / 'raw/Virus_Recombination_Results.txt'
        parsed = dvg_evidence.parse_virema_results(native_path, {
            name: row['length'] for name, row in reference_rows.items()
        }, output / self.stdout_name, expected_read_count=read_count)
        catalogue = _catalogue_rows(manifest['inputs']['catalogue_records']['path']) \
            if 'catalogue_records' in manifest['inputs'] else {}
        events = self._normalized_events(parsed, output, config, manifest, reference_rows, catalogue)
        status = dvg_evidence.DVG_EVIDENCE_DETECTED if events else dvg_evidence.NO_DVG_EVIDENCE_DETECTED
        evidence = {
            'schema': 'dvg-evidence-v1',
            'caller': self.caller_name,
            'caller_version': CALLER_VERSION,
            'parser_version': dvg_evidence.PARSER_VERSION,
            'status': status,
            'sample_id': config['sample_id'],
            'read_artifact_id': Path(manifest['inputs']['reads']['path']).name,
            'read_artifact_sha256': manifest['inputs']['reads']['sha256'],
            'reference_lengths': {name: row['length'] for name, row in reference_rows.items()},
            'references': {
                name: {'length': row['length'], 'sha256': row['sha256']}
                for name, row in reference_rows.items()
            },
            'events': events,
        }
        dvg_evidence.validate_evidence_document(evidence)
        write_json(output / 'evidence.json', evidence)
        raw_hash = _sha(native_path)
        summary = {
            'schema': 'dvg-summary-v1',
            'status': status,
            'event_count': len(events),
            'caller': self.caller_name,
            'caller_version': CALLER_VERSION,
            'sample_id': config['sample_id'],
            'raw_output': {'path': 'raw/Virus_Recombination_Results.txt', 'sha256': raw_hash},
            'evidence_file': 'evidence.json',
            'event_references': [event['evidence_id'] for event in events],
            'limitations': [
                'This is evidence reported by ViReMa under the configured run settings, not a biological classification.',
                'No reported junctions do not establish absence of a defective viral genome.',
                'Only ViReMa virus-virus junction output is interpreted.',
            ],
            'parser_version': dvg_evidence.PARSER_VERSION,
        }
        dvg_evidence.validate_summary(summary)
        write_json(output / 'summary.json', summary)
        dependency = manifest.get('dependency_report', {})
        source_hashes = {
            name: row.get('sha256') if isinstance(row, dict) else row
            for name, row in dependency.get('source_sha256', {}).items()
        }
        command = list(manifest['safe_command'])
        parameters = {
            'schema': 'dvg-parameters-v1',
            'caller': self.caller_name,
            'caller_version': CALLER_VERSION,
            'upstream_commit': UPSTREAM_COMMIT,
            'source_sha256': source_hashes,
            'configuration': config,
            'input_sha256': {
                name: value['sha256'] for name, value in sorted(manifest['inputs'].items())
            },
            'command': command,
        }
        write_json(output / 'parameters.json', parameters)
        report = self._report(config, status, events, raw_hash)
        (output / 'report.html').write_text(report, encoding='utf-8')
        # Keep the raw/ copy used by ViReMa's Output_Dir handling, but avoid
        # retaining the second working-directory copy in successful artifacts.
        cwd_reads = output / reads_copy.name
        info = cwd_reads.lstat()
        if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
            cwd_reads.unlink()

    def _report(self, config, status, events, raw_hash):
        event_count = len(events)
        result = ('ViReMa reported supported virus-virus junction event evidence.'
                  if event_count else
                  'ViReMa reported no supported virus-virus junctions under these run settings.')
        event_limit = 50
        event_links = ''.join(
            '<li><a href="evidence.json">'
            + html.escape(event['evidence_id']) + '</a></li>'
            for event in events[:event_limit]
        )
        remaining = max(0, event_count - event_limit)
        event_list = (
            '<h2>Event references</h2><ul>' + event_links + '</ul>'
            + (f'<p>{remaining} additional event references are in evidence.json.</p>'
               if remaining else '')
            if event_count else ''
        )
        limitations = (
            '<h2>Limitations</h2><ul>'
            '<li>Supporting caller evidence only; this is not a biological classification.</li>'
            '<li>No reported junctions do not establish that a sequence is not a DVG.</li>'
            '<li>Only ViReMa virus-virus junction output is interpreted.</li>'
            '</ul>'
        )
        return (
            '<!doctype html><html><head><meta charset="utf-8"><title>ViReMa DVG evidence</title>'
            '</head><body><h1>ViReMa DVG evidence evaluation</h1>'
            f'<p>Sample: {html.escape(config["sample_id"])}</p>'
            f'<p>Caller: {html.escape(self.caller_name)} {html.escape(CALLER_VERSION)}</p>'
            f'<p>Status: {html.escape(status)}</p><p>{result}</p>'
            f'<p>Event count: {event_count}</p>'
            + event_list + limitations
            + '<p>Native result: <a href="raw/Virus_Recombination_Results.txt">'
            'raw/Virus_Recombination_Results.txt</a></p>'
            + f'<p>Native result SHA256: {raw_hash}</p></body></html>\n'
        )

    def validate_outputs(self, output, config):
        try:
            return self._validate_outputs(output, config)
        except dvg_evidence.InvalidDVGResultError:
            raise
        except (ValueError, OSError, TypeError, KeyError) as error:
            raise dvg_evidence.InvalidDVGResultError(
                'ViReMa output validation failed: ' + (str(error) or type(error).__name__)
            ) from error

    def _validate_outputs(self, output, config):
        output = Path(output)
        native = _regular_file(output / 'raw/Virus_Recombination_Results.txt', 'Native ViReMa output')
        evidence_path = _regular_file(output / 'evidence.json', 'Normalized evidence')
        summary_path = _regular_file(output / 'summary.json', 'Evidence summary')
        parameters_path = _regular_file(output / 'parameters.json', 'Parameter record')
        report_path = _regular_file(output / 'report.html', 'HTML report')
        try:
            evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
            summary = json.loads(summary_path.read_text(encoding='utf-8'))
            parameters = json.loads(parameters_path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ValueError('ViReMa normalized output JSON is missing or malformed') from error
        dvg_evidence.validate_evidence_document(evidence)
        dvg_evidence.validate_summary(summary)
        from .artifact_contracts import validate_artifact
        validate_artifact(parameters_path, 'dvg_parameters')
        validate_artifact(native, 'dvg_raw_output')
        validate_artifact(report_path, 'report')
        native_hash = _sha(native)
        if (summary.get('raw_output') != {
                'path': 'raw/Virus_Recombination_Results.txt', 'sha256': native_hash}
                or summary.get('evidence_file') != 'evidence.json'
                or summary.get('event_count') != len(evidence['events'])
                or summary.get('status') != evidence['status']
                or summary.get('event_references') != [
                    event.get('evidence_id') for event in evidence['events']
                ]
                or evidence.get('caller') != self.caller_name
                or evidence.get('sample_id') != config['sample_id']
                or summary.get('sample_id') != config['sample_id']
                or summary.get('parser_version') != dvg_evidence.PARSER_VERSION):
            raise ValueError('ViReMa summary and evidence provenance do not match native output')
        if (parameters.get('schema') != 'dvg-parameters-v1'
                or parameters.get('caller') != self.caller_name
                or parameters.get('caller_version') != CALLER_VERSION
                or parameters.get('upstream_commit') != UPSTREAM_COMMIT
                or parameters.get('configuration') != config
                or not isinstance(parameters.get('source_sha256'), dict)
                or not isinstance(parameters.get('input_sha256'), dict)
                or not isinstance(parameters.get('command'), list)
                or not parameters['command']):
            raise ValueError('ViReMa parameter provenance is incomplete')
        # Reparse the raw caller output on reuse; a valid-looking JSON file cannot
        # turn malformed, truncated, or changed native text into a valid result.
        reference_path = _regular_file(output / 'reference.fasta', 'Staged reference')
        refs = _reference_records(reference_path)
        reads_path = _regular_file(
            output / ('raw/reads.fastq.gz' if (output / 'raw/reads.fastq.gz').is_file()
                      else 'raw/reads.fastq'),
            'Staged reads',
        )
        expected_read_count = sum(1 for _ in _read_fastq(reads_path))
        parsed = dvg_evidence.parse_virema_results(
            native, {name: row['length'] for name, row in refs.items()},
            _regular_file(output / self.stdout_name, 'ViReMa stdout'),
            expected_read_count=expected_read_count,
        )
        if len(parsed) != len(evidence['events']):
            raise ValueError('Normalized event count does not match reparsed ViReMa output')
        for native_event, event in zip(parsed, evidence['events']):
            if (event.get('reference_id') != native_event['reference_id']
                    or event.get('acceptor_reference_id') != native_event['acceptor_reference_id']
                    or event.get('breakpoint_1') != native_event['breakpoint_1']
                    or event.get('breakpoint_2') != native_event['breakpoint_2']
                    or event.get('orientation') != native_event['orientation']
                    or event.get('supporting_read_count') != native_event['supporting_read_count']
                    or event.get('raw_entry') != native_event['raw_entry']
                    or event.get('raw_library') != native_event['raw_library']
                    or event.get('raw_output_reference', {}).get('sha256') != native_hash
                    or event.get('raw_output_reference', {}).get('line') != native_event['raw_line_number']):
                raise ValueError('Normalized event does not match reparsed native ViReMa output')
        return {
            'status': evidence['status'],
            'event_count': len(evidence['events']),
            'raw_output_sha256': native_hash,
            'evidence_sha256': _sha(evidence_path),
            'summary_sha256': _sha(summary_path),
            'parameters_sha256': _sha(parameters_path),
            'report_sha256': _sha(report_path),
        }

    def cache_implementation_identity(self):
        source = Path(__file__).resolve()
        parser_source = Path(dvg_evidence.__file__).resolve()
        executor_source = Path(inspect.getsourcefile(ExternalToolAdapter)).resolve()
        return {
            'adapter_source_sha256': _sha(source),
            'executor_source_sha256': _sha(executor_source),
            'caller': self.caller_name,
            'caller_version': CALLER_VERSION,
            'upstream_commit': UPSTREAM_COMMIT,
            'source_sha256': dict(SOURCE_HASHES),
            'parser_version': dvg_evidence.PARSER_VERSION,
            'parser_source_sha256': _sha(parser_source),
        }

    def _identity(self, config, inputs, dependency, command, environment, context=None):
        identity = super()._identity(config, inputs, dependency, command, environment, context)
        # Global package/git metadata and report-only presentation are not part of
        # the caller implementation identity; pinned caller/parser source is.
        # Stage inputs can be materialized in a new path after a report-only
        # code change while retaining the same verified bytes.
        identity['inputs'] = {
            name: {'bytes': row['bytes'], 'sha256': row['sha256']}
            for name, row in identity['inputs'].items()
        }
        identity['environment'] = {
            key: environment.get(key) for key in ('python', 'platform')
        }
        identity['implementation'] = self.cache_implementation_identity()
        identity['caller_source'] = dependency.get('source_sha256', {})
        return identity


__all__ = ['ViReMaDVGAdapter']