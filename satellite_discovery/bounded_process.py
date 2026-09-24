"""Bounded external-tool execution within one owned stage directory."""
import subprocess
import time
import math
from pathlib import Path
from .portable_paths import portable_name

def run(command,directory,log_name,timeout=180,max_bytes=400_000_000):
    directory=Path(directory).resolve(strict=True)
    if not portable_name(log_name):raise ValueError('Use a portable log filename')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout<=0:
        raise ValueError('External-tool timeout must be finite and positive')
    if type(max_bytes) is not int or max_bytes<=0:raise ValueError('External-tool byte budget must be a positive integer')
    if sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())>max_bytes:
        raise ValueError('Existing stage files exceed stage byte budget')
    with (directory/log_name).open('wb') as log:
        process=subprocess.Popen(command,stdout=log,stderr=log,cwd=directory)
        start=time.monotonic()
        try:
            while process.poll() is None:
                total=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
                if total>max_bytes:raise ValueError('External-tool output exceeds stage byte budget')
                if time.monotonic()-start>timeout:raise TimeoutError('External-tool time budget exceeded')
                time.sleep(.05)
            if process.returncode:raise RuntimeError('External tool failed; see '+log_name)
            if sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())>max_bytes:raise ValueError('External-tool output exceeds stage byte budget')
        finally:
            if process.poll() is None:process.kill()
            process.wait()
