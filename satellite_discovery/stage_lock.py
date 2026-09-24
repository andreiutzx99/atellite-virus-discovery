"""Exclusive stage lock diagnostics; never infer stale ownership from age alone."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import uuid
import warnings


def acquire(path):
    path = Path(path)
    token = json.dumps({'pid': os.getpid(), 'host': socket.gethostname(),
                        'created_utc': datetime.now(timezone.utc).isoformat(),
                        'owner_token': uuid.uuid4().hex}, sort_keys=True).encode('utf-8')
    try:
        handle = path.open('xb')
    except FileExistsError:
        owner = 'owner unavailable (legacy, malformed or inaccessible lock)'
        try:
            if not path.is_symlink() and path.stat().st_size <= 4096:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    owner = 'recorded PID '+str(data.get('pid','unknown'))+' on '+str(data.get('host','unknown'))+' since '+str(data.get('created_utc','unknown'))
        except (OSError, ValueError):
            pass
        raise ValueError('Stage is locked: '+owner+'. Verify the owning process has stopped before manually recovering this lock; no automatic stale-lock deletion.') from None
    with handle:
        handle.write(token)
    return token


def release(path, token):
    path = Path(path)
    try:
        if path.is_symlink() or path.stat().st_size > 4096 or path.read_bytes() != token:
            warnings.warn('Lock ownership changed; replacement lock preserved', RuntimeWarning)
            return
        path.unlink()
    except FileNotFoundError:
        warnings.warn('Owned lock disappeared before release', RuntimeWarning)
