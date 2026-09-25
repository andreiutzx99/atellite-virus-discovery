"""Registered, arbitrary-input FASTQ assembly stages.

Only trusted adapters construct executable argument vectors. Workflow JSON
selects an assembler by identifier and supplies input artifacts and safe limits.
"""
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import re
import shutil
import stat
import zipfile

from . import reproducibility
from .dependency_review import inspect_executable
from .external_tool import (
    DependencyMissingError,
    ExternalToolAdapter,
    _inventory,
)
from . import quality_control, sequence_catalogue
from .sequence_downloader import checksum, write_json


ADAPTER_VERSION = '1.0'
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_OUTPUT_BUDGET = 400_000_000
BBTOOLS_VERSION = '40.01'
BBTOOLS_COMMIT = '7afa43b1bb3ad07493ac93a67ada4a5ec779f0c0'
BBTOOLS_ARCHIVE_SHA256 = '36b1c7be738f16185e967e33cab909e660b0f33a905b1fe06043f24a314a3725'


def _assembly_config(config):
    if not isinstance(config, dict) or set(config) - {'assembler', 'layout', 'threads', 'memory_mb'}:
        raise ValueError('Assembly config accepts only assembler, layout, threads and memory_mb')
    assembler = config.get('assembler')
    if not isinstance(assembler, str) or assembler not in {'spades', 'tadpole'}:
        raise ValueError('Unknown registered assembler; choose spades or tadpole')
    layout = config.get('layout')
    if not isinstance(layout, str) or layout not in {'single-end', 'paired-end'}:
        raise ValueError('Assembly layout must be declared as single-end or paired-end')
    threads = config.get('threads', 2)
    memory_mb = config.get('memory_mb', 2048 if assembler == 'spades' else 512)
    if type(threads) is not int or not 1 <= threads <= 8:
        raise ValueError('Assembly threads must be an integer from 1 through 8')
    if type(memory_mb) is not int or not 256 <= memory_mb <= 16384:
        raise ValueError('Assembly memory_mb must be an integer from 256 through 16384')
    if assembler == 'spades' and memory_mb % 1024:
        raise ValueError('SPAdes memory_mb must be a whole number of GiB')
    return {'assembler': assembler, 'layout': layout, 'threads': threads, 'memory_mb': memory_mb}


def _read_fastq(path):
    """Stream and structurally validate FASTQ without loading a file at once."""
    path = Path(path)
    compressed = path.name.lower().endswith(('.fastq.gz', '.fq.gz'))
    opener = gzip.open if compressed else open
    count = 0
    with opener(path, 'rt', encoding='ascii', newline='') as source:
        while True:
            rows = []
            for _ in range(4):
                line = source.readline(10002)
                if len(line.rstrip('\r\n')) > 10000:
                    raise ValueError(f'FASTQ line exceeds the 10,000-character limit in {path.name}')
                rows.append(line.rstrip('\r\n'))
            if not rows[0]:
                if any(rows[1:]):
                    raise ValueError(f'Incomplete FASTQ record in {path.name}')
                break
            header, sequence, plus, quality = rows
            count += 1
            if not header.startswith('@') or len(header) < 2 or not plus.startswith('+'):
                raise ValueError(f'Malformed FASTQ record {count} in {path.name}')
            if not sequence or len(sequence) != len(quality) or len(sequence) > 10000:
                raise ValueError(f'Invalid FASTQ sequence/quality lengths at record {count} in {path.name}')
            if set(sequence.upper()) - set('ACGTN') or any(not 33 <= ord(char) <= 126 for char in quality):
                raise ValueError(f'Unsupported FASTQ base or quality encoding at record {count} in {path.name}')
            if plus[1:] and plus[1:].split()[0] != header[1:].split()[0]:
                raise ValueError(f'FASTQ separator identifier mismatch at record {count} in {path.name}')
            yield header, sequence.upper(), quality
    if count == 0:
        raise ValueError(f'FASTQ contains no records: {path.name}')


def _validate_fastq_inputs(inputs, output):
    if 'read2' not in inputs:
        return {'read1': sum(1 for _ in _read_fastq(inputs['read1']))}
    first, second = inputs['read1'], inputs['read2']
    if first == second or (first.stat().st_dev, first.stat().st_ino) == (second.stat().st_dev, second.stat().st_ino):
        raise ValueError('Paired FASTQ inputs must be distinct files')
    count = 0
    sentinel = object()
    for left, right in zip_longest(_read_fastq(first), _read_fastq(second), fillvalue=sentinel):
        if left is sentinel or right is sentinel:
            raise ValueError('Paired FASTQ files contain different record counts')
        quality_control.check_mate(left[0], '1')
        quality_control.check_mate(right[0], '2')
        if quality_control.pair_id(left[0]) != quality_control.pair_id(right[0]):
            raise ValueError('Paired FASTQ record identifiers do not match')
        count += 1
    return {'read1': count, 'read2': count}


def _fasta_summary(path):
    records = sequence_catalogue.read_fasta(path)
    lengths = [len(row[2]) for row in records]
    return {
        'contig_count': len(records),
        'total_bases': sum(lengths),
        'minimum_length': min(lengths),
        'maximum_length': max(lengths),
        'contig_sha256': checksum(path),
    }


def _canonicalize_contigs(source, destination):
    """Make valid, unique catalogue IDs while preserving raw FASTA separately."""
    source = Path(source)
    destination = Path(destination)
    if source.stat().st_size > 100_000_000:
        raise ValueError('Raw contig FASTA exceeds the existing catalogue 100 MB limit')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Assembler unexpectedly created the canonical contig path')
    used, header_map = set(), []
    record_count = total_bases = 0
    current_id = None
    has_bases = False
    with source.open(encoding='utf-8-sig', newline='') as raw, \
            destination.open('x', encoding='ascii', newline='\n') as canonical:
        while True:
            line = raw.readline(1_000_002)
            if not line:
                break
            if len(line) > 1_000_001 and not line.endswith('\n'):
                raise ValueError('Assembler FASTA contains an overlong line')
            line = line.rstrip('\r\n')
            if line.startswith('>'):
                if current_id is not None and not has_bases:
                    raise ValueError('Assembler FASTA contains an empty contig')
                original_header = line[1:].strip()
                if not original_header:
                    raise ValueError('Assembler FASTA contains an empty header')
                source_id = original_header.split()[0]
                base_id = source_id.split(',', 1)[0]
                safe_id = re.sub(r'[^A-Za-z0-9_.:-]', '_', base_id)[:200].strip('._:')
                if not safe_id:
                    safe_id = f'contig_{record_count + 1}'
                candidate = safe_id
                suffix = 2
                while candidate.casefold() in used:
                    candidate = f'{safe_id}_{suffix}'
                    suffix += 1
                used.add(candidate.casefold())
                record_count += 1
                if record_count > sequence_catalogue.MAX_RECORDS:
                    raise ValueError('Assembly exceeds the existing catalogue record limit')
                if candidate != source_id:
                    header_map.append({
                        'record_number': record_count,
                        'original_header_sha256': hashlib.sha256(original_header.encode('utf-8')).hexdigest(),
                        'canonical_id': candidate,
                    })
                canonical.write('>' + candidate + '\n')
                current_id = candidate
                has_bases = False
                continue
            if current_id is None:
                if line.strip():
                    raise ValueError('Assembler FASTA sequence appears before its header')
                continue
            sequence = ''.join(line.split()).upper()
            if not sequence:
                continue
            if set(sequence) - sequence_catalogue.ALPHABET:
                raise ValueError('Assembler FASTA contains an invalid nucleotide symbol')
            total_bases += len(sequence)
            if total_bases > sequence_catalogue.MAX_BASES:
                raise ValueError('Assembly exceeds the existing catalogue base limit')
            canonical.write(sequence + '\n')
            has_bases = True
            if canonical.tell() > 100_000_000:
                raise ValueError('Canonical contig FASTA exceeds the existing catalogue 100 MB limit')
    if current_id is not None and not has_bases:
        raise ValueError('Assembler FASTA contains an empty contig')
    return header_map


def _read_git_revision():
    try:
        return reproducibility.environment().get('git_revision')
    except (OSError, ValueError):
        return None


def _version(row):
    value = (row.get('version_output') or '').strip()
    if not value:
        return 'unknown'
    return value


class _AssemblyToolAdapter(ExternalToolAdapter):
    assembler = ''
    tool_name = ''
    raw_contigs = 'raw/contigs.fasta'

    def __init__(self, *, timeout=DEFAULT_TIMEOUT_SECONDS, max_bytes=DEFAULT_OUTPUT_BUDGET):
        super().__init__(
            kind='assembly_' + self.assembler,
            module_name='assembly.' + self.assembler,
            adapter_name=self.assembler + '-assembly-adapter',
            adapter_version=ADAPTER_VERSION,
            tool_name=self.tool_name,
            dependencies=self._dependencies(),
            input_fields={'read1'},
            optional_input_fields={'read2'},
            output_files=[self.raw_contigs, 'contigs.fasta', 'assembly_manifest.json'],
            timeout=timeout,
            max_bytes=max_bytes,
            stdout_name='stdout.log',
            stderr_name='stderr.log',
            description='Validated arbitrary-input FASTQ assembly; no biological interpretation.',
        )

    def validate_config(self, config):
        normalized = _assembly_config(config)
        if normalized['assembler'] != self.assembler:
            raise ValueError(f'This adapter only runs the registered {self.assembler} assembler')
        return normalized

    def validate_inputs(self, inputs, output, config=None):
        if not isinstance(inputs, dict) or not {'read1'} <= set(inputs) or set(inputs) - {'read1', 'read2'}:
            raise ValueError('Assembly requires read1 and optionally read2')
        for name, value in inputs.items():
            raw = Path(value)
            try:
                if stat.S_ISLNK(raw.lstat().st_mode):
                    raise ValueError(f'FASTQ input must not be a symbolic link: {name}')
                path = raw.resolve(strict=True)
            except OSError as error:
                raise ValueError(f'FASTQ input is missing or unreadable: {name}') from error
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError(f'FASTQ input is not a regular file: {name}')
            if path.stat().st_size == 0:
                raise ValueError(f'FASTQ input is empty: {name}')
            if not path.name.lower().endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
                raise ValueError(f'Unsupported FASTQ filename extension: {path.name}')
            try:
                with path.open('rb'):
                    pass
            except OSError as error:
                raise ValueError(f'FASTQ input is unreadable: {name}') from error
        paths = super().validate_inputs(inputs, output)
        expected_paired = config['layout'] == 'paired-end'
        if expected_paired != ('read2' in paths):
            raise ValueError('Declared assembly layout does not match supplied FASTQ mates')
        if 'read2' in paths and paths['read1'] == paths['read2']:
            raise ValueError('Paired FASTQ inputs must be distinct files')
        _validate_fastq_inputs(paths, output)
        return paths

    def validate_configured_inputs(self, inputs, output, config):
        return self.validate_inputs(inputs, output, config)

    def _identity_row(self, dependency):
        return dependency['dependencies'][0]

    def _tool_version(self, dependency):
        return _version(self._identity_row(dependency))

    def _executable_identity(self, dependency):
        return [
            {key: row.get(key) for key in ('tool', 'path', 'sha256', 'status', 'version_output')}
            for row in dependency['dependencies']
        ]

    def build_command(self, executables, inputs, output, config):
        raise NotImplementedError

    def finalize_outputs(self, output, config, process_result, manifest):
        output = Path(output)
        raw = output / self.raw_contigs
        try:
            raw_info = raw.lstat()
        except OSError as error:
            raise ValueError('Assembler did not produce the expected contig FASTA') from error
        if stat.S_ISLNK(raw_info.st_mode) or not stat.S_ISREG(raw_info.st_mode):
            raise ValueError('Assembler contig output is not a regular file')
        canonical = output / 'contigs.fasta'
        header_map = _canonicalize_contigs(raw, canonical)
        summary = _fasta_summary(canonical)

        inputs = manifest['inputs']
        dependency = manifest['dependency_report']
        layout = manifest['configuration']['layout']
        inventory = _inventory(output)
        row = self._identity_row(dependency)
        assembly_manifest = {
            'schema': 'assembly-manifest-v1',
            'stage_id': manifest.get('stage_id') or manifest['identity'].get('stage_id') or 'assembly',
            'assembler': self.assembler,
            'adapter_version': self.adapter_version,
            'external_tool_version': self._tool_version(dependency),
            'executable_identity': self._executable_identity(dependency),
            'executable_path': row.get('path'),
            'executable_sha256': row.get('sha256'),
            'input_layout': layout,
            'input_filenames': {name: Path(value['path']).name for name, value in inputs.items()},
            'inputs': inputs,
            'parameters': config,
            'safe_command': manifest['safe_command'],
            'started_utc': manifest['started_utc'],
            'finished_utc': datetime.now(timezone.utc).isoformat(),
            'duration_seconds': process_result.duration_seconds,
            'exit_status': process_result.returncode,
            'workflow_status': 'complete',
            'raw_output_location': 'raw/',
            'contig_output': 'contigs.fasta',
            'contig_count': summary['contig_count'],
            'total_contig_bases': summary['total_bases'],
            'minimum_contig_length': summary['minimum_length'],
            'maximum_contig_length': summary['maximum_length'],
            'contig_sha256': summary['contig_sha256'],
            'contig_header_map': header_map,
            'output_inventory': inventory,
            'output_sha256': {row['path']: row['sha256'] for row in inventory},
            'git_revision': _read_git_revision(),
            'warnings': [],
            'errors': [],
            'resource_limits': {
                'timeout_seconds': self.timeout,
                'stage_output_bytes': self.max_bytes,
                'threads': config['threads'],
                'memory_mb': config['memory_mb'],
                'containment': 'cooperative process timeout/output budget and tool-level thread/memory options; not hard OS quotas',
            },
        }
        write_json(output / 'assembly_manifest.json', assembly_manifest)

    def validate_outputs(self, output, config):
        output = Path(output)
        canonical = output / 'contigs.fasta'
        assembly_manifest_path = output / 'assembly_manifest.json'
        for artifact in (canonical, assembly_manifest_path, output / self.raw_contigs):
            try:
                artifact_info = artifact.lstat()
            except OSError as error:
                raise ValueError(f'Required assembly output is missing: {artifact.name}') from error
            if not stat.S_ISREG(artifact_info.st_mode):
                raise ValueError(f'Assembly output is not a regular file: {artifact.name}')
        summary = _fasta_summary(canonical)
        try:
            assembly_manifest = json.loads(assembly_manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError('Assembly manifest is missing or malformed') from error
        if not isinstance(assembly_manifest, dict):
            raise ValueError('Assembly manifest must be a JSON object')
        expected = {
            'assembler': self.assembler,
            'contig_output': 'contigs.fasta',
            'contig_count': summary['contig_count'],
            'contig_sha256': summary['contig_sha256'],
        }
        if assembly_manifest.get('workflow_status') != 'complete' or any(
            assembly_manifest.get(key) != value for key, value in expected.items()
        ):
            raise ValueError('Assembly manifest does not match validated contig output')
        return {**summary, 'assembler': self.assembler}

    def record_failure(self, output, state, error):
        if state not in {'failed', 'interrupted'}:
            return
        manifest_path = Path(output) / 'assembly_manifest.json'
        try:
            if not stat.S_ISREG(manifest_path.lstat().st_mode):
                return
            record = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if not isinstance(record, dict):
            return
        record['workflow_status'] = state
        record['finished_utc'] = datetime.now(timezone.utc).isoformat()
        errors = record.get('errors')
        if not isinstance(errors, list):
            errors = []
        errors.append({
            'type': type(error).__name__,
            'message': str(error) or type(error).__name__,
        })
        record['errors'] = errors
        write_json(manifest_path, record)


class SpadesAssemblyAdapter(_AssemblyToolAdapter):
    assembler = 'spades'
    tool_name = 'SPAdes genome assembler'

    def _dependencies(self):
        return [{'name': 'spades', 'command': 'spades.py', 'version_args': ['--version']}]

    def inspect_dependency(self, config=None):
        executable = shutil.which('spades.py') or shutil.which('spades')
        row = inspect_executable('spades', executable or 'spades.py', ('--version',))
        version_ok = row['status'] == 'version_check_passed' and 'spades' in row['version_output'].lower()
        row['status'] = 'version_check_passed' if version_ok else ('not_found' if not row['path'] else 'version_check_failed')
        return {
            'status': 'available' if version_ok else 'dependency_missing',
            'assembler': self.assembler,
            'dependencies': [row],
        }

    def build_command(self, executables, inputs, output, config):
        command = [
            executables['spades'],
            '--only-assembler',
            '-t', str(config['threads']),
            '-m', str(config['memory_mb'] // 1024),
            '-o', str(output / 'raw'),
        ]
        if 'read2' in inputs:
            command += ['-1', str(inputs['read1']), '-2', str(inputs['read2'])]
        else:
            command += ['-s', str(inputs['read1'])]
        return command


class TadpoleAssemblyAdapter(_AssemblyToolAdapter):
    assembler = 'tadpole'
    tool_name = 'BBTools Tadpole assembler'

    def __init__(self, *, timeout=DEFAULT_TIMEOUT_SECONDS, max_bytes=DEFAULT_OUTPUT_BUDGET):
        self.project_root = Path(__file__).resolve().parents[1]
        super().__init__(timeout=timeout, max_bytes=max_bytes)

    @property
    def archive(self):
        return self.project_root / '.tools' / 'BBTools-40.01.zip'

    @property
    def classpath(self):
        return self.project_root / '.tools' / 'bbtools-40.01' / f'BBTools-{BBTOOLS_COMMIT}' / 'current'

    def _dependencies(self):
        return [{'name': 'java', 'command': 'java', 'version_args': ['-version']}]

    def _verify_runtime(self):
        if not self.archive.is_file() or checksum(self.archive) != BBTOOLS_ARCHIVE_SHA256:
            return {'status': 'dependency_missing', 'reason': 'Pinned BBTools archive is missing or has a checksum mismatch'}
        prefix = f'BBTools-{BBTOOLS_COMMIT}/current/'
        digest = hashlib.sha256()
        verified = 0
        try:
            with zipfile.ZipFile(self.archive) as bundle:
                members = [member for member in bundle.infolist()
                           if member.filename.startswith(prefix) and not member.is_dir()]
                if not members:
                    return {'status': 'dependency_missing', 'reason': 'Pinned BBTools archive contains no Tadpole runtime'}
                for member in members:
                    installed = (self.project_root / '.tools' / 'bbtools-40.01' / member.filename).resolve()
                    if not installed.is_relative_to(self.classpath.resolve()) or not installed.is_file():
                        return {'status': 'dependency_missing', 'reason': 'Installed BBTools runtime file is missing'}
                    expected = hashlib.sha256(bundle.read(member)).hexdigest()
                    if checksum(installed) != expected:
                        return {'status': 'dependency_missing', 'reason': 'Installed BBTools runtime checksum mismatch'}
                    digest.update(member.filename.encode('utf-8') + b'\0' + expected.encode('ascii') + b'\n')
                    verified += 1
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            return {'status': 'dependency_missing', 'reason': 'Cannot verify pinned BBTools runtime: ' + str(error)}
        if not (self.classpath / 'assemble' / 'Tadpole.class').is_file():
            return {'status': 'dependency_missing', 'reason': 'Tadpole class is missing from the verified runtime'}
        return {
            'status': 'available',
            'version': f'BBTools {BBTOOLS_VERSION}',
            'commit': BBTOOLS_COMMIT,
            'archive_sha256': BBTOOLS_ARCHIVE_SHA256,
            'installation_sha256': digest.hexdigest(),
            'verified_runtime_files': verified,
            'classpath': str(self.classpath),
        }

    def inspect_dependency(self, config=None):
        java = super().inspect_dependency(config)
        runtime = self._verify_runtime()
        available = java['status'] == 'available' and runtime['status'] == 'available'
        return {
            'status': 'available' if available else 'dependency_missing',
            'assembler': self.assembler,
            'dependencies': java['dependencies'],
            'runtime': runtime,
        }

    def _tool_version(self, dependency):
        return dependency['runtime']['version'] + ' (' + dependency['runtime']['commit'] + ')'

    def _executable_identity(self, dependency):
        return {
            'java': super()._executable_identity(dependency),
            'bbtools_runtime': dependency['runtime'],
        }

    def build_command(self, executables, inputs, output, config):
        command = [
            executables['java'],
            '-ea',
            f'-Xmx{config["memory_mb"]}m',
            '-cp', str(self.classpath),
            'assemble.Tadpole',
            'in=' + str(inputs['read1']),
            'out=' + str(output / self.raw_contigs),
            'threads=' + str(config['threads']),
            'overwrite=f',
        ]
        if 'read2' in inputs:
            command.append('in2=' + str(inputs['read2']))
        return command


class AssemblyWorkflowAdapter:
    """Workflow-facing selector for only the trusted SPAdes/Tadpole adapters."""

    kind = 'assembly'
    module_name = 'assembly.generic'
    adapter_name = 'registered-assembly-router'
    adapter_version = ADAPTER_VERSION
    input_fields = frozenset({'read1'})
    optional_input_fields = frozenset({'read2'})
    description = 'Selects a registered assembler; workflow configuration cannot provide commands.'

    def __init__(self, adapters=None):
        adapters = adapters or (SpadesAssemblyAdapter(), TadpoleAssemblyAdapter())
        self.adapters = {adapter.assembler: adapter for adapter in adapters}
        if set(self.adapters) != {'spades', 'tadpole'}:
            raise ValueError('Assembly registry must contain exactly SPAdes and Tadpole adapters')

    def validate_config(self, config):
        return _assembly_config(config)

    def _selected(self, config):
        normalized = self.validate_config(config)
        return self.adapters[normalized['assembler']], normalized

    def inspect_dependency(self, config=None):
        if config is not None:
            adapter, normalized = self._selected(config)
            report = adapter.inspect_dependency()
            report['assembler'] = normalized['assembler']
            return report
        reports = [adapter.inspect_dependency() for adapter in self.adapters.values()]
        return {
            'status': 'available' if any(row['status'] == 'available' for row in reports) else 'dependency_missing',
            'dependencies': [dependency for row in reports for dependency in row.get('dependencies', [])],
            'assemblers': {row['assembler']: row for row in reports},
        }

    def inspect_dependency_for_config(self, config):
        return self.inspect_dependency(config)

    def execute(self, inputs, output, config, context=None):
        adapter, normalized = self._selected(config)
        if set(inputs) - {'read1', 'read2'} or 'read1' not in inputs:
            raise ValueError('Assembly requires read1 and optionally read2')
        dependency = adapter.inspect_dependency()
        if dependency['status'] != 'available':
            raise DependencyMissingError(
                f'The registered {normalized["assembler"]} assembler is unavailable',
                dependency,
            )
        return adapter.execute(inputs, output, normalized, context=context)