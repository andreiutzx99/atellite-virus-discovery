"""Isolated single-sequence ViennaRNA MFE execution for M11."""

import ctypes
import json
import math
import os
import subprocess
import sys

from .m11_algorithms import canonical_json


class ResourceEnforcementError(RuntimeError):
    pass


def _json_model_value(value):
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("ViennaRNA model details contain a non-finite value")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_model_value(item) for item in value]
    return None


def _effective_model(model):
    details = {}
    for name in sorted(dir(model)):
        if name.startswith("_") or name in {"this", "thisown", "alias"}:
            continue
        try:
            value = getattr(model, name)
        except Exception:
            continue
        if callable(value):
            continue
        normalized = _json_model_value(value)
        if normalized is not None:
            details[name] = normalized
    return details


def _worker_main():
    try:
        request = json.loads(sys.stdin.read())
        sequence = request.get("sequence")
        if not isinstance(sequence, str) or not sequence:
            raise ValueError("Worker received an empty or invalid RNA sequence")
        if os.name == "posix":
            import resource
            memory_bytes = request.get("memory_bytes")
            if type(memory_bytes) is not int or memory_bytes <= 0:
                raise ValueError("Worker received an invalid memory limit")
            resource.setrlimit(
                resource.RLIMIT_AS,
                (memory_bytes, memory_bytes),
            )
        import RNA

        if getattr(RNA, "__version__", None) != "2.7.2":
            raise RuntimeError("Worker ViennaRNA interface version is not 2.7.2")
        model = RNA.md()
        model.temperature = 37.0
        model.dangles = 2
        compound = RNA.fold_compound(sequence, model)
        structure, energy = compound.mfe()
        energy = float(energy)
        if not math.isfinite(energy):
            raise ValueError("ViennaRNA returned a non-finite energy")
        effective_details = _effective_model(model)
        effective_details["parameter_set"] = "TURNER_2004_BUILTIN"
        result = {
            "dot_bracket": str(structure),
            "energy_hex": energy.hex(),
            "effective_model_details": effective_details,
        }
        sys.stdout.write(canonical_json(result) + "\n")
        return 0
    except BaseException as error:
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        return 1


def _create_windows_job(process, memory_bytes):
    """Assign the child to a Job Object with a hard per-process memory cap."""
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ResourceEnforcementError("Unable to create a Windows M11 Job Object")
    limit = ExtendedLimitInformation()
    limit.BasicLimitInformation.LimitFlags = 0x00000100  # PROCESS_MEMORY
    limit.ProcessMemoryLimit = memory_bytes
    if not kernel.SetInformationJobObject(
        job, 9, ctypes.byref(limit), ctypes.sizeof(limit)
    ):
        kernel.CloseHandle(job)
        raise ResourceEnforcementError("Unable to set the Windows M11 memory limit")
    if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        kernel.CloseHandle(job)
        raise ResourceEnforcementError("Unable to enforce the Windows M11 memory limit")
    return kernel, job


def fold_single(sequence, timeout_seconds, memory_bytes):
    """Run one fold in a bounded child process.

    Returns ``(branch_status, result, reason)``. Only the API result envelope,
    not this worker's transport stdout, is retained by the stage.
    """
    if os.name not in {"posix", "nt"}:
        raise ResourceEnforcementError("M11 resource enforcement is unsupported")
    process = subprocess.Popen(
        [sys.executable, "-m", "satellite_discovery.m11_engine", "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    windows_job = None
    try:
        if os.name == "nt":
            windows_job = _create_windows_job(process, memory_bytes)
        try:
            stdout, stderr = process.communicate(
                input=canonical_json({
                    "sequence": sequence,
                    "memory_bytes": memory_bytes,
                }) + "\n",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            if windows_job:
                windows_job[0].TerminateJobObject(windows_job[1], 1)
            else:
                process.kill()
            process.communicate()
            return "INTERRUPTED", None, "PER_FOLD_TIMEOUT"
    except ResourceEnforcementError:
        process.kill()
        process.communicate()
        raise
    finally:
        if windows_job:
            windows_job[0].CloseHandle(windows_job[1])

    if process.returncode != 0:
        if process.returncode < 0 or process.returncode >= 0xC0000000:
            return "INTERRUPTED", None, "PROCESS_TERMINATED_OR_RESOURCE_KILLED"
        return "EXECUTION_FAILED", None, (
            stderr.strip()[:500] or "VIENNARNA_WORKER_FAILED"
        )
    try:
        result = json.loads(stdout)
        if not isinstance(result, dict):
            raise ValueError("Worker result is not an object")
    except (json.JSONDecodeError, ValueError):
        return "OUTPUT_INVALID", None, "MALFORMED_WORKER_RESULT"
    return "COMPLETED", result, None


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        raise SystemExit(_worker_main())
    raise SystemExit("This module is an internal M11 worker.")