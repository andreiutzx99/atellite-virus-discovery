"""Transport-neutral fallback contract; no network or biological routing here."""
import errno
import subprocess
import copy
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError


class VerificationError(ValueError):
    """A retrieved artifact failed validation; never bypass by fallback."""


class AcquisitionFailed(RuntimeError):
    def __init__(self, attempts):
        self.attempts = attempts
        super().__init__('Acquisition did not complete; inspect the recorded attempts')


def classify(error):
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return 'interrupted'
    if isinstance(error, VerificationError):
        return 'integrity_failure'
    if isinstance(error, PermissionError):
        return 'permission_denied'
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return 'insufficient_disk'
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return 'timeout'
    if isinstance(error, HTTPError):
        return 'remote_unavailable' if error.code in {408, 429} or error.code >= 500 else 'remote_rejected'
    if isinstance(error, (URLError, ConnectionError)):
        return 'remote_unavailable'
    if isinstance(error, FileNotFoundError):
        return 'missing_input_or_executable'
    if isinstance(error, ValueError):
        return 'invalid_input_or_integrity'
    return 'execution_failed'


def run(methods, providers, verify, record, *, retries=0, history=None):
    """Execute configured trusted callables, verifying every success before acceptance.

    `record` persists the full attempt list after each transition. Providers and
    verifier are supplied by application code, never imported from user config.
    No remote SRA provider is registered by the released acquisition workflow.
    """
    if not isinstance(methods, list) or not methods or len(methods) > 5 or any(not isinstance(m, str) for m in methods):
        raise ValueError('Configure one to five named acquisition methods')
    if len(set(methods)) != len(methods) or any(m not in providers for m in methods):
        raise ValueError('Unknown or duplicate acquisition backend')
    if type(retries) is not int or not 0 <= retries <= 2:
        raise ValueError('Retries must be an integer from zero to two')
    if history is not None and (not isinstance(history, list) or len(history) > 1000 or
                               any(not isinstance(item, dict) for item in history)):
        raise ValueError('Invalid prior attempt history')
    # Prior success never bypasses verification: providers must safely reacquire or
    # return an existing artifact for the verifier. Preserve prior records verbatim.
    attempts = copy.deepcopy(history or [])
    for method, attempt in ((m, n) for m in methods for n in range(1, retries + 2)):
        # Success returns; permanent errors break. A transient exhausted retry is
        # followed by the next explicitly configured provider.
        started = time.monotonic()
        item = {'method': method, 'attempt': attempt, 'status': 'running',
                'started_utc': datetime.now(timezone.utc).isoformat()}
        attempts.append(item); record(attempts)
        try:
            artifact = providers[method]()
            item['status'] = 'verifying'; record(attempts)
            try:
                provenance = verify(artifact)
            except Exception as exc:
                raise VerificationError('Artifact verification failed: '+str(exc)) from exc
            if not isinstance(provenance, dict) or provenance.get('verified') is not True:
                raise VerificationError('Verifier did not certify the artifact')
            item.update(status='complete', verification=provenance,
                        finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic()-started)
            record(attempts)
            return artifact
        except BaseException as exc:
            reason = classify(exc)
            item.update(status='interrupted' if reason == 'interrupted' else 'failed',
                        failure_class=reason, error_type=type(exc).__name__, message=str(exc),
                        finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic()-started)
            record(attempts)
            if reason == 'interrupted':
                raise
            if reason not in {'timeout', 'remote_unavailable', 'missing_input_or_executable'}:
                break
    raise AcquisitionFailed(attempts)


def diagnostic(error):
    return {'failure_class': classify(error), 'error_type': type(error).__name__,
            'primary_method': 'ena_fastq', 'automatic_alternative': 'not_configured',
            'next_step': 'Inspect the error and download plan. Local SRA conversion is a separate explicit menu action; it is not automatically substituted.'}
