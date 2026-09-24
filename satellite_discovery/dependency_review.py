"""Read-only version checks for optional tools; never install or run analyses."""
import hashlib
import importlib.util
from importlib import metadata
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from .review_stage import report
from .sequence_downloader import write_json

TOOLS = {
    'blastn': ('blastn', '-version', '.tools/blast-*/ncbi-blast-*/bin/blastn.exe'),
    'makeblastdb': ('makeblastdb', '-version', '.tools/blast-*/ncbi-blast-*/bin/makeblastdb.exe'),
    'bowtie2': ('bowtie2', '--version', '.tools/bowtie2-*/bowtie2-*/bowtie2-align-s.exe'),
    'java': ('java', '-version', None),
    'samtools': ('samtools', '--version', None),
    'fasterq-dump': ('fasterq-dump', '--version', None),
    'prefetch': ('prefetch', '--version', None),
    'vdb-validate': ('vdb-validate', '--version', None),
    'spades': ('spades.py', '--version', None),
    'tadpole': ('tadpole.sh', '--version', None),
}

def inspect_tools(project):
    project=Path(project).resolve()
    rows=[]
    for name,(command,flag,pattern) in TOOLS.items():
        if pattern and sys.platform!='win32':pattern=pattern.removesuffix('.exe')
        path=shutil.which(command)
        if not path and name=='spades':path=shutil.which('spades')
        candidates=sorted(project.glob(pattern)) if pattern else []
        if not path and len(candidates)==1:
            path=str(candidates[0].resolve())
        row={'tool':name,'path':str(Path(path).resolve()) if path else '', 'status':'not_found', 'version_output':'', 'sha256':'', 'capability_test':'not_performed'}
        if not path and len(candidates)>1:
            row['status']='ambiguous_portable_versions'
        if path:
            try:
                with open(path,'rb') as source:
                    row['sha256']=hashlib.file_digest(source,'sha256').hexdigest()
                result=subprocess.run([path,flag],capture_output=True,text=True,errors='replace',timeout=15,check=False)
                row['status']='version_check_passed' if result.returncode==0 else 'version_check_failed'
                row['version_output']=(result.stdout+'\n'+result.stderr).strip()[:4000]
            except (OSError,subprocess.TimeoutExpired) as error:
                row.update(status='version_check_failed',version_output=str(error)[:4000])
        rows.append(row)
    for name in ('pysam','matplotlib'):
        row={'tool':name,'path':'','status':'not_found','version_output':'','sha256':'','capability_test':'not_performed'}
        try:
            if importlib.util.find_spec(name):
                try:row['version_output']=metadata.version(name)
                except metadata.PackageNotFoundError:row['version_output']='Version metadata unavailable'
                result=subprocess.run([sys.executable,'-c','import importlib,sys; importlib.import_module(sys.argv[1])',name],capture_output=True,text=True,errors='replace',timeout=15,check=False)
                row['status']='import_check_passed' if result.returncode==0 else 'import_check_failed'
                if result.returncode:row['version_output']+='; '+result.stderr[-2000:]
        except (OSError,ValueError,ImportError,subprocess.TimeoutExpired) as error:
            row.update(status='import_check_failed',version_output=str(error)[:2000])
        rows.append(row)
    return rows

def run(project,output):
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    manifest={'status':'running','kind':'dependency-version-check','started_at':datetime.now(timezone.utc).isoformat(), 'python':sys.version,'platform':platform.platform(),'project':str(Path(project).resolve())}
    write_json(output/'manifest.json',manifest)
    try:
        rows=inspect_tools(project)
        files=report(output,'Optional dependency checks',{'tools':rows},[
            'Version checks do not validate mapping, assembly, database content or biological results.',
            'Checks use PATH first, then one unambiguous project portable tool. Missing tools do not affect the pure-Python review modules.',
            'No downloads or installations occur. Choose a new folder for a fresh environment check.',
            'Tadpole is checked separately with Test-Tadpole.cmd using an artificial fixture and a pinned local archive.'])
        manifest.update(status='complete',finished_at=datetime.now(timezone.utc).isoformat(),outputs={})
        for filename in files:
            with (output/filename).open('rb') as source:
                manifest['outputs'][filename]=hashlib.file_digest(source,'sha256').hexdigest()
        write_json(output/'manifest.json',manifest)
    except Exception as error:
        manifest.update(status='failed',error=str(error)); write_json(output/'manifest.json',manifest)
        raise
    return output/'report.html'
