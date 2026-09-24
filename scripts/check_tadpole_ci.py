"""Optional pinned Tadpole diagnostic on a clean CI checkout (artificial data only)."""
from pathlib import Path
from urllib.request import urlopen
import zipfile
from test_tadpole_runtime import PROJECT, COMMIT, ARCHIVE_SHA256, digest, run

root = PROJECT / '.tools'
root.mkdir(exist_ok=True)
archive = root / 'BBTools-40.01.zip'
if not archive.exists():
    with urlopen('https://codeload.github.com/bbushnell/BBTools/zip/'+COMMIT, timeout=60) as source:
        payload = source.read(40_000_001)
    if len(payload) > 40_000_000:
        raise ValueError('Pinned runtime download exceeded byte budget')
    with archive.open('xb') as dest:
        dest.write(payload)
if digest(archive) != ARCHIVE_SHA256:
    raise ValueError('Pinned archive integrity failure')
target = (root/'bbtools-40.01').resolve()
if not target.exists():
    with zipfile.ZipFile(archive) as bundle:
        if sum(m.file_size for m in bundle.infolist()) > 200_000_000 or any(
                not (target/m.filename).resolve().is_relative_to(target) for m in bundle.infolist()):
            raise ValueError('Archive extraction violates resource/path contract')
        bundle.extractall(target)
for paired, name in ((False,'single'),(True,'paired')):
    output=root/('ci-diagnostic-'+name)
    if not run(output,paired):raise RuntimeError('Artificial diagnostic failed')
    if not run(output,paired):raise RuntimeError('Verified reuse failed')
