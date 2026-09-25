"""Bounded external-tool execution within one owned stage directory."""
import subprocess
import time
import math
import os
import signal
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from .portable_paths import portable_name


def stage_bytes(directory):
    """Count regular files without following links or special files."""
    import stat
    total = 0
    def scan_error(error):
        if isinstance(error, FileNotFoundError) and Path(error.filename) != Path(directory):
            # A discovered scratch directory can vanish before os.walk enters it.
            # Missing stage roots and permission/IO failures must still fail.
            return
        raise error
    for base, directories, files in os.walk(directory, followlinks=False, onerror=scan_error):
        for name in directories + files:
            path = Path(base) / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                # Tools may unlink scratch files while a budget scan is running.
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Stage contains a link or reparse point: ' + str(path))
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
            elif not stat.S_ISDIR(info.st_mode):
                raise ValueError('Stage contains a special file: ' + str(path))
    return total


def stop_tree(process):
    """Terminate this runner's group/tree; never target a process by image name.

    POSIX descendants must remain in the new session's process group. Windows
    taskkill is best effort and requires the original parent to remain alive.
    This is trusted-tool cleanup, not hostile-process containment.
    """
    error = None
    try:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            # Use the system executable, not a PATH entry or shell command.
            system = Path(os.environ.get('SystemRoot', r'C:\Windows'))
            result = subprocess.run([str(system/'System32/taskkill.exe'), '/PID', str(process.pid), '/T', '/F'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError('Windows process-tree termination failed; descendants may remain')
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        error = exc
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
    if error is not None:
        raise RuntimeError('Process-tree cleanup failed: '+str(error)) from error


@dataclass(frozen=True)
class ProcessResult:
    """Structured result for a bounded process with separate output streams."""

    returncode: int
    duration_seconds: float
    stdout_name: str
    stderr_name: str


def _run_process(command, directory, stdout_name, stderr_name, timeout, max_bytes):
    directory=Path(directory).resolve(strict=True)
    if not portable_name(stdout_name) or not portable_name(stderr_name):
        raise ValueError('Use portable log filenames')
    if not isinstance(command, (list, tuple)) or not command or any(
            not isinstance(arg, str) or '\0' in arg for arg in command):
        raise ValueError('External-tool command must be a non-empty argument list')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0:
        raise ValueError('External-tool timeout must be finite and positive')
    if type(max_bytes) is not int or max_bytes<=0:raise ValueError('External-tool byte budget must be a positive integer')
    if stage_bytes(directory)>max_bytes:
        raise ValueError('Existing stage files exceed stage byte budget')
    stdout_path = directory/stdout_name
    stderr_path = directory/stderr_name
    with ExitStack() as stack:
        stdout_log = stack.enter_context(stdout_path.open('wb'))
        stderr_log = stdout_log if stdout_path == stderr_path else stack.enter_context(stderr_path.open('wb'))
        start=time.monotonic()
        process=subprocess.Popen(command,stdout=stdout_log,stderr=stderr_log,cwd=directory,
                                 start_new_session=os.name=='posix',
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            while process.poll() is None:
                total=stage_bytes(directory)
                if total>max_bytes:raise ValueError('External-tool output exceeds stage byte budget')
                if time.monotonic()-start>timeout:raise TimeoutError('External-tool time budget exceeded')
                time.sleep(.05)
            if time.monotonic()-start>timeout:raise TimeoutError('External-tool time budget exceeded')
        finally:
            active_error=sys.exception()
            try:
                stop_tree(process)
            except (OSError,RuntimeError,subprocess.SubprocessError) as exc:
                if active_error is None:raise
                active_error.add_note(str(exc))
                stderr_log.write(('\nCleanup warning: '+str(exc)+'\n').encode('utf-8'))
        # Inspect final outputs after cleanup, including fast processes that
        # terminate between polls. Retain logs and scratch files on failure.
        if stage_bytes(directory)>max_bytes:raise ValueError('External-tool output exceeds stage byte budget')
        return ProcessResult(
            returncode=process.returncode,
            duration_seconds=time.monotonic()-start,
            stdout_name=stdout_name,
            stderr_name=stderr_name,
        )


def run(command,directory,log_name,timeout=180,max_bytes=400_000_000):
    """Run a bounded process, combining stdout and stderr in one log."""
    if not portable_name(log_name):
        raise ValueError('Use a portable log filename')
    result = _run_process(command, directory, log_name, log_name, timeout, max_bytes)
    if result.returncode:
        raise RuntimeError('External tool failed (exit '+str(result.returncode)+'); see '+log_name)


def run_captured(command, directory, stdout_name, stderr_name, timeout=180,
                 max_bytes=400_000_000):
    """Run argv without a shell, retaining stdout/stderr separately.

    Nonzero exits are returned to the adapter so it can record the exit status
    and failure details in its stage manifest.
    """
    return _run_process(command, directory, stdout_name, stderr_name, timeout, max_bytes)
