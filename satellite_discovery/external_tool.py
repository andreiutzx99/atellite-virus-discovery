"""Safe, provenance-recording adapter contract for trusted external tools."""
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
import math
import os
from pathlib import Path
import stat
import time

from . import bounded_process, reproducibility, stage_lock
from .dependency_review import inspect_executable
from .portable_paths import portable_name
from .sequence_downloader import checksum, write_json


class DependencyMissingError(RuntimeError):
    def __init__(self, message, dependency_report):
        super().__init__(message)
        self.dependency_report = dependency_report


class ExternalToolExitError(RuntimeError):
    def __init__(self, returncode, stderr_name):
        super().__init__(f'External tool failed with exit status {returncode}; see {stderr_name}')
        self.returncode = returncode


@dataclass(frozen=True)
class ExternalToolExecution:
    execution: str
    adapter: dict
    tool: dict
    command: list
    output_inventory: list
    manifest_sha256: str


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        return False
    path = Path(value)
    if path.is_absolute() or any(part in {'', '.', '..'} or not portable_name(part)
                                 for part in path.parts):
        return False
    return True


def _inventory(directory):
    """Hash every regular output without following links or special files."""
    import stat

    rows = []
    for base, dirs, files in os.walk(directory, followlinks=False):
        base_path = Path(base)
        for name in list(dirs):
            path = base_path/name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('External-tool output contains a link: '+str(path))
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError('External-tool output contains a special file: '+str(path))
        for name in files:
            path = base_path/name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('External-tool output contains a link: '+str(path))
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('External-tool output contains a special file: '+str(path))
            relative = path.relative_to(directory).as_posix()
            if relative in {'manifest.json', '.external-tool.lock'}:
                continue
            if not _safe_relative_path(relative):
                raise ValueError('External-tool output has an unsafe path: '+relative)
            rows.append({'path': relative, 'bytes': info.st_size, 'sha256': checksum(path)})
    return sorted(rows, key=lambda row: row['path'])


class ExternalToolAdapter:
    """Base contract for a trusted adapter that invokes an argv-only tool.

    Subclasses define command construction and may tighten config/input checks.
    The adapter itself, not workflow JSON, owns the executable and invocation.
    """

    def __init__(self, *, kind, module_name, adapter_name, adapter_version,
                 tool_name, dependencies, input_fields, output_files,
                 optional_input_fields=(),
                 timeout=180, max_bytes=400_000_000,
                 stdout_name='stdout.log', stderr_name='stderr.log',
                 description=''):
        self.kind = kind
        self.module_name = module_name
        self.adapter_name = adapter_name
        self.adapter_version = adapter_version
        self.tool_name = tool_name
        self.dependencies = tuple(dict(item) for item in dependencies)
        self.input_fields = frozenset(input_fields)
        self.optional_input_fields = frozenset(optional_input_fields)
        if self.input_fields & self.optional_input_fields:
            raise ValueError('An input cannot be both required and optional')
        field_names = self.input_fields | self.optional_input_fields
        if any(not isinstance(name, str) or not name.isidentifier() for name in field_names):
            raise ValueError('External adapter input names must be identifiers')
        self.output_files = tuple(output_files)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.stdout_name = stdout_name
        self.stderr_name = stderr_name
        self.description = description
        if not isinstance(adapter_name, str) or not adapter_name.strip():
            raise ValueError('Adapter name must be non-empty')
        if not isinstance(adapter_version, str) or not adapter_version.strip():
            raise ValueError('Adapter version must be non-empty')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Adapter timeout must be finite and positive')
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError('Adapter byte budget must be a positive integer')
        if not self.dependencies:
            raise ValueError('External adapter must declare at least one executable')
        if len({row.get('name') for row in self.dependencies}) != len(self.dependencies):
            raise ValueError('External adapter executable names must be unique')
        for row in self.dependencies:
            if set(row) != {'name', 'command', 'version_args'}:
                raise ValueError('Executable declarations require name, command, and version_args')
            if (not isinstance(row['name'], str) or not row['name']
                    or not isinstance(row['command'], str) or not row['command']
                    or not isinstance(row['version_args'], (list, tuple))
                    or any(not isinstance(arg, str) or '\0' in arg for arg in row['version_args'])):
                raise ValueError('Invalid external executable declaration')
        if any(not _safe_relative_path(name) for name in self.output_files):
            raise ValueError('Declared output names must be safe relative paths')
        if len(set(name.casefold() for name in self.output_files)) != len(self.output_files):
            raise ValueError('Declared output filenames must be unique')
        if not portable_name(stdout_name) or not portable_name(stderr_name) or stdout_name.casefold() == stderr_name.casefold():
            raise ValueError('External-tool log filenames must be portable and distinct')
        if any(name.casefold() in {stdout_name.casefold(), stderr_name.casefold(), 'manifest.json'}
               for name in self.output_files):
            raise ValueError('Declared outputs cannot overwrite adapter records or logs')

    def validate_config(self, config):
        if not isinstance(config, dict):
            raise ValueError('Adapter config must be an object')
        try:
            json.dumps(config, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError('Adapter config must contain JSON-safe values') from error
        return dict(config)

    def validate_inputs(self, inputs, output, config=None):
        if (not isinstance(inputs, dict)
                or not self.input_fields <= set(inputs)
                or set(inputs) - (self.input_fields | self.optional_input_fields)):
            raise ValueError('External adapter received incorrect input fields')
        paths = {}
        for name, value in inputs.items():
            path = Path(value).resolve(strict=True)
            if not path.is_file():
                raise ValueError(f'Required input is not a regular file: {name}')
            if path.is_relative_to(output):
                raise ValueError('External-tool inputs must be outside the stage output directory')
            paths[name] = path
        return paths

    def validate_configured_inputs(self, inputs, output, config):
        """Configuration-aware extension point that preserves legacy adapters."""
        return self.validate_inputs(inputs, output)

    def inspect_dependency(self, config=None):
        rows = [
            inspect_executable(item['name'], item['command'], tuple(item['version_args']))
            for item in self.dependencies
        ]
        return {
            'status': 'available' if all(row['path'] for row in rows) else 'dependency_missing',
            'dependencies': rows,
        }

    def inspect_dependency_for_config(self, config):
        """Configuration-aware extension point; old adapters need no signature change."""
        return self.inspect_dependency()

    def build_command(self, executables, inputs, output, config):
        """Return the argument list. Subclasses must not invoke a shell."""
        raise NotImplementedError

    def prepare_execution(self, output, inputs, config, manifest):
        """Stage owned input copies after recording provenance, before launch."""
        return None

    def finalize_outputs(self, output, config, process_result, manifest):
        """Create any canonical artifacts after a successful tool exit."""
        return None

    def validate_outputs(self, output, config):
        """Validate declared outputs and return a JSON-safe output contract."""
        return {}

    def record_failure(self, output, state, error):
        """Let adapters update any adapter-specific completion record."""
        return None

    def _output_bytes(self, output):
        output = Path(output)
        total = sum(row['bytes'] for row in _inventory(output))
        total += sum(
            (output / name).stat().st_size
            for name in ('manifest.json', '.external-tool.lock')
            if (output / name).is_file()
        )
        return total

    def _safe_command(self, command, inputs, output):
        safe = []
        for argument in command:
            replacement = argument
            for name, path in inputs.items():
                if argument == str(path):
                    replacement = f'<input:{name}>'
                    break
            else:
                try:
                    candidate = Path(argument)
                    if candidate.is_absolute() and candidate.is_relative_to(output):
                        replacement = '<stage-output>/' + candidate.relative_to(output).as_posix()
                except (OSError, ValueError):
                    pass
            safe.append(replacement)
        return safe

    def _identity(self, config, inputs, dependency, command, environment, context=None):
        source_path = Path(inspect.getsourcefile(type(self)) or __file__).resolve()
        adapter_source = checksum(source_path) if source_path.is_file() else None
        relevant_environment = {
            key: environment.get(key)
            for key in ('software_version', 'git_revision', 'source_sha256', 'python', 'platform')
        }
        return {
            'adapter': {
                'name': self.adapter_name,
                'version': self.adapter_version,
                'kind': self.kind,
                'source_sha256': adapter_source,
            },
            'tool': dependency['dependencies'],
            'inputs': {
                name: {'path': str(path), 'bytes': path.stat().st_size, 'sha256': checksum(path)}
                for name, path in sorted(inputs.items())
            },
            'configuration': config,
            'command': command,
            'environment': relevant_environment,
            'declared_outputs': list(self.output_files),
            'stage_id': context.get('stage_id') if isinstance(context, dict) else None,
        }

    def _verify_reuse(self, output, identity, previous):
        if previous.get('schema') != 'external-tool-stage-v1' or previous.get('status') != 'complete':
            raise ValueError('Existing external-tool stage is not a completed reusable result')
        if previous.get('identity') != identity:
            raise ValueError('External-tool inputs, configuration, adapter or executable changed; use a new output folder')
        expected = previous.get('output_inventory')
        if not isinstance(expected, list):
            raise ValueError('External-tool output inventory is malformed')
        actual = _inventory(output)
        if actual != expected:
            raise ValueError('External-tool output integrity failure; existing files preserved')
        for row in expected:
            path = (output/row['path']).resolve(strict=True)
            if not path.is_relative_to(output) or not path.is_file():
                raise ValueError('External-tool output path is invalid; existing files preserved')
        return ExternalToolExecution(
            execution='verified_reuse',
            adapter=previous['adapter'],
            tool=previous['tool'],
            command=previous['safe_command'],
            output_inventory=expected,
            manifest_sha256=checksum(output/'manifest.json'),
        )

    def execute(self, inputs, output, config, context=None):
        config = self.validate_config(config)
        output = Path(output).resolve()
        paths = self.validate_configured_inputs(inputs, output, config)
        dependency = self.inspect_dependency()
        if dependency['status'] != 'available':
            raise DependencyMissingError(
                f'Required external executable for {self.adapter_name} is unavailable',
                dependency,
            )
        executables = {row['tool']: row['path'] for row in dependency['dependencies']}
        output.mkdir(parents=True, exist_ok=True)
        lock = output/'.external-tool.lock'
        token = stage_lock.acquire(lock)
        marker = output/'manifest.json'
        manifest = None
        started = None
        try:
            if marker.exists():
                try:
                    previous = json.loads(marker.read_text(encoding='utf-8'))
                except (OSError, ValueError) as error:
                    raise ValueError('External-tool manifest is malformed; existing files preserved') from error
                environment = reproducibility.environment()
                command = self.build_command(executables, paths, output, config)
                safe_command = self._safe_command(command, paths, output)
                identity = self._identity(config, paths, dependency, safe_command, environment, context)
                contract = self.validate_outputs(output, config)
                if previous.get('output_contract') != contract:
                    raise ValueError('External-tool output contract changed; existing files preserved')
                return self._verify_reuse(output, identity, previous)
            if any(path != lock for path in output.iterdir()):
                raise ValueError('External-tool output folder is nonempty without a matching manifest')

            environment = reproducibility.environment()
            command = self.build_command(executables, paths, output, config)
            if not isinstance(command, (list, tuple)) or not command or any(
                    not isinstance(arg, str) or '\0' in arg for arg in command):
                raise ValueError('Adapter must return a non-empty argv list of strings')
            if command[0] != next(iter(executables.values())) and command[0] not in executables.values():
                raise ValueError('Adapter command must start with a declared executable')
            safe_command = self._safe_command(command, paths, output)
            identity = self._identity(config, paths, dependency, safe_command, environment, context)
            adapter_identity = identity['adapter']
            tool_identity = {
                'name': self.tool_name,
                'executables': dependency['dependencies'],
            }
            manifest = {
                'schema': 'external-tool-stage-v1',
                'status': 'running',
                'identity': identity,
                'adapter': adapter_identity,
                'tool': tool_identity,
                'inputs': {
                    name: {'path': str(path), **identity['inputs'][name]}
                    for name, path in sorted(paths.items())
                },
                'configuration': config,
                'safe_command': safe_command,
                'environment': environment,
                'dependency_report': dependency,
                'stage_id': context.get('stage_id') if isinstance(context, dict) else None,
                'started_utc': _now(),
            }
            write_json(marker, manifest)
            started = time.monotonic()
            self.prepare_execution(output, paths, config, manifest)
            process_result = bounded_process.run_captured(
                list(command), output, self.stdout_name, self.stderr_name,
                timeout=self.timeout, max_bytes=self.max_bytes,
            )
            if process_result.returncode:
                raise ExternalToolExitError(process_result.returncode, self.stderr_name)
            self.finalize_outputs(output, config, process_result, manifest)
            finalized_bytes = self._output_bytes(output)
            if finalized_bytes > self.max_bytes:
                raise ValueError(
                    f'External-tool stage byte budget exceeded after output finalization '
                    f'({finalized_bytes} > {self.max_bytes})'
                )
            for relative in self.output_files:
                artifact = (output/relative).resolve(strict=True)
                if not artifact.is_relative_to(output) or not artifact.is_file():
                    raise ValueError(f'Declared external-tool output is missing or unsafe: {relative}')
            output_contract = self.validate_outputs(output, config)
            for name, path in paths.items():
                if checksum(path) != identity['inputs'][name]['sha256']:
                    raise ValueError(f'Input changed during external-tool execution: {name}')
            inventory = _inventory(output)
            manifest.update(
                status='complete',
                exit_status=process_result.returncode,
                duration_seconds=process_result.duration_seconds,
                finished_utc=_now(),
                output_contract=output_contract,
                output_inventory=inventory,
                output_sha256={row['path']: row['sha256'] for row in inventory},
            )
            write_json(marker, manifest)
            completed_bytes = self._output_bytes(output)
            if completed_bytes > self.max_bytes:
                raise ValueError(
                    f'External-tool stage byte budget exceeded after completion manifest '
                    f'({completed_bytes} > {self.max_bytes})'
                )
            return ExternalToolExecution(
                execution='executed',
                adapter=adapter_identity,
                tool=tool_identity,
                command=safe_command,
                output_inventory=inventory,
                manifest_sha256=checksum(marker),
            )
        except BaseException as error:
            if manifest is not None:
                state = 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed'
                try:
                    self.record_failure(output, state, error)
                except Exception:
                    pass
                try:
                    inventory = _inventory(output)
                    inventory_error = None
                except (OSError, ValueError) as inventory_exception:
                    inventory = []
                    inventory_error = str(inventory_exception) or type(inventory_exception).__name__
                marker_is_regular = False
                try:
                    marker_is_regular = stat.S_ISREG(marker.lstat().st_mode)
                except OSError:
                    pass
                if marker_is_regular:
                    try:
                        manifest.update(
                            status=state,
                            error=str(error) or type(error).__name__,
                            error_type=type(error).__name__,
                            exit_status=getattr(error, 'returncode', None),
                            duration_seconds=(time.monotonic()-started) if started is not None else None,
                            finished_utc=_now(),
                            output_inventory=inventory,
                        )
                        if inventory_error:
                            manifest['output_inventory_error'] = inventory_error
                        write_json(marker, manifest)
                    except (OSError, ValueError):
                        pass
            raise
        finally:
            stage_lock.release(lock, token)