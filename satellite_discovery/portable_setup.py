"""Install one checksum-pinned portable BLAST release on Windows, without admin changes."""
import os
import shutil
import tarfile
from pathlib import Path
from urllib.request import urlopen
from .sequence_downloader import checksum,write_json
from .local_comparison import tools

WINDOWS=os.name=='nt'
ARCHIVE='ncbi-blast-2.17.0+-x64-win64.tar.gz'
SHA256='ccde8788641e8f4137536aaadedfeac2f3599dbbc6166e701b5d89d19fa79038'
URL='https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/'+ARCHIVE

def install(root,offline=False):
    if not WINDOWS:raise RuntimeError('Portable installer targets Windows. On other systems use a supported package manager and configure PATH.')
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    lock=root/'.blast-install.lock'
    try:lock.open('x').close()
    except FileExistsError:raise ValueError('BLAST installation is locked')
    try:
        archive=root/ARCHIVE
        if not archive.exists():
            if offline:raise RuntimeError('Pinned archive is unavailable offline')
            if shutil.disk_usage(root).free<1_500_000_000:raise RuntimeError('Need 1.5 GB free disk space')
            temporary=root/(ARCHIVE+'.part')
            with urlopen(URL,timeout=30) as response,temporary.open('wb') as target:
                size=0
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>500_000_000:raise ValueError('Archive exceeds download cap')
                    target.write(chunk)
            if checksum(temporary)!=SHA256:raise ValueError('Downloaded BLAST checksum mismatch')
            temporary.replace(archive)
        if checksum(archive)!=SHA256:raise ValueError('Cached BLAST checksum mismatch')
        destination=root/'blast-2.17.0';destination.mkdir(exist_ok=True)
        with tarfile.open(archive,'r:gz') as source:
            members=source.getmembers()
            if sum(m.size for m in members)>1_000_000_000:raise ValueError('Archive exceeds extraction cap')
            for member in members:
                path=(destination/member.name).resolve()
                if not path.is_relative_to(destination) or not(member.isdir() or member.isfile()):raise ValueError('Unsafe archive member')
            # Verify all existing files before writing any missing files. Never overwrite edits.
            import hashlib
            for member in members:
                path=destination/member.name
                if member.isfile() and path.exists():
                    with source.extractfile(member) as content:
                        expected=hashlib.file_digest(content,'sha256').hexdigest()
                    if checksum(path)!=expected:raise ValueError('Existing runtime differs from pinned archive: '+member.name)
            for member in members:
                path=destination/member.name
                if member.isdir():path.mkdir(parents=True,exist_ok=True)
                elif not path.exists():
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with source.extractfile(member) as content,path.open('xb') as target:shutil.copyfileobj(content,target)
        result=tools(destination/'ncbi-blast-2.17.0+'/ 'bin')
        write_json(root/'portable-blast-installation.json',{'source':URL,'archive_sha256':SHA256,'tools':result})
        return result
    finally:lock.unlink()
