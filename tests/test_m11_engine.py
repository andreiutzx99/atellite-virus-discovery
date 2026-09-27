import os
import subprocess
import unittest
from unittest.mock import patch

from satellite_discovery import m11_engine


class _TimedOutProcess:
    _handle = 123
    returncode = None

    def __init__(self):
        self.killed = False

    def communicate(self, input=None, timeout=None):
        if input is not None:
            raise subprocess.TimeoutExpired(["m11-worker"], timeout)
        return "", ""

    def kill(self):
        self.killed = True
        self.returncode = -9


class _FakeKernel:
    def __init__(self):
        self.terminated = False
        self.closed = False

    def TerminateJobObject(self, job, code):
        self.terminated = True
        return True

    def CloseHandle(self, job):
        self.closed = True
        return True


class M11EngineTests(unittest.TestCase):
    def test_timeout_kills_the_bounded_worker_and_returns_interrupted(self):
        process = _TimedOutProcess()
        kernel = _FakeKernel()
        patches = [
            patch.object(m11_engine.subprocess, "Popen", return_value=process),
        ]
        if os.name == "nt":
            patches.append(
                patch.object(
                    m11_engine, "_create_windows_job",
                    return_value=(kernel, 456),
                )
            )
        with patches[0]:
            if len(patches) == 2:
                with patches[1]:
                    result = m11_engine.fold_single("ACGU", 0.01, 1_000_000)
            else:
                result = m11_engine.fold_single("ACGU", 0.01, 1_000_000)
        self.assertEqual(result, ("INTERRUPTED", None, "PER_FOLD_TIMEOUT"))
        if os.name == "nt":
            self.assertTrue(kernel.terminated)
            self.assertTrue(kernel.closed)
        else:
            self.assertTrue(process.killed)

    def test_malformed_worker_transport_is_output_invalid(self):
        class _CompletedProcess:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                return "not json", ""

        process = _CompletedProcess()
        patches = [
            patch.object(m11_engine.subprocess, "Popen", return_value=process),
        ]
        if os.name == "nt":
            patches.append(
                patch.object(
                    m11_engine, "_create_windows_job",
                    return_value=(_FakeKernel(), 456),
                )
            )
        with patches[0]:
            if len(patches) == 2:
                with patches[1]:
                    result = m11_engine.fold_single("ACGU", 1, 1_000_000)
            else:
                result = m11_engine.fold_single("ACGU", 1, 1_000_000)
        self.assertEqual(result, ("OUTPUT_INVALID", None, "MALFORMED_WORKER_RESULT"))


if __name__ == "__main__":
    unittest.main()