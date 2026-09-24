"""Conditional local SRA archive conversion; no archive search or download."""
import json
import gzip
import re
import shutil
import subprocess
from itertools import zip_longest
from pathlib import Path
from .bounded_process import run as process
from .quality_control import records, pair_id, check_mate
from .review_stage import execute,report
from .sequence_downloader import checksum,write_json


def preserve_failed_outputs(directory,stem):
    names=[stem+suffix for suffix in ('.fastq','_1.fastq','_2.fastq','.fastq.gz','_1.fastq.gz','_2.fastq.gz')]+['command.json','conversion.log']
    existing=[directory/name for name in names if (directory/name).exists()]
    if not existing:return
    archive=directory/'previous_attempts'
    if not archive.resolve().is_relative_to(directory):raise ValueError('Retry archive redirects outside output')
    archive.mkdir(exist_ok=True)
    index=1
    while (archive/str(index)).exists():index+=1
    target=archive/str(index);target.mkdir()
    for path in existing:
        if path.is_symlink() or not path.resolve().is_relative_to(directory) or not path.is_file():
            raise ValueError('Unsafe previous conversion output')
        path.replace(target/path.name)

def convert(archive,output):
    path=Path(archive).resolve(strict=True)
    if path.suffix.lower()!='.sra' or not re.fullmatch('[A-Za-z0-9_-]+',path.stem):raise ValueError('Use a local .sra archive with a simple filename')
    if path.stat().st_size>100_000_000:raise ValueError('Local SRA conversion pilot is limited to 100 MB input')
    binary=shutil.which('fasterq-dump')
    if not binary:raise RuntimeError('Install NCBI SRA Toolkit with fasterq-dump on PATH for local archive conversion')
    version=subprocess.run([binary,'--version'],capture_output=True,text=True,check=True,timeout=15).stdout.strip()
    tool={'path':str(Path(binary).resolve()),'sha256':checksum(binary),'version':version}
    inputs={'archive':path,'process_engine':Path(__file__).with_name('bounded_process.py'),'fastq_parser':Path(__file__).with_name('quality_control.py')}
    def produce(paths,directory):
        if shutil.disk_usage(directory).free<2_000_000_000:raise RuntimeError('Need 2 GB free space for bounded local conversion')
        preserve_failed_outputs(directory,path.stem)
        command=[tool['path'],str(paths['archive']),'--split-3','--threads','1','--outdir',str(directory),'--temp',str(directory/'temporary'),'--force']
        write_json(directory/'command.json',{'command':command,'tool':tool,'input_sha256':checksum(paths['archive'])})
        process(command,directory,'conversion.log',timeout=300,max_bytes=1_000_000_000)
        outputs=sorted(directory.glob('*.fastq'))
        allowed={path.stem+'.fastq',path.stem+'_1.fastq',path.stem+'_2.fastq'}
        if not outputs or any(p.name not in allowed for p in outputs):raise ValueError('Unexpected or missing converted FASTQ filenames')
        compressed=[]
        for plain in outputs:
            gz=plain.with_suffix(plain.suffix+'.gz')
            with plain.open('rb') as source,gz.open('wb') as dest:
                with gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0) as target:shutil.copyfileobj(source,target)
            compressed.append(gz)
        rows=[{'filename':p.name,'reads':sum(1 for _ in records(p)),'sha256':checksum(p)} for p in compressed]
        counts={r['filename']:r['reads'] for r in rows}
        if (path.stem+'_1.fastq.gz' in counts)!=(path.stem+'_2.fastq.gz' in counts):raise ValueError('Converted paired FASTQ mate is missing')
        if counts.get(path.stem+'_1.fastq.gz')!=counts.get(path.stem+'_2.fastq.gz'):raise ValueError('Converted paired FASTQ counts disagree')
        if not sum(counts.values()):raise ValueError('Conversion produced no reads; not a valid negative result')
        if path.stem+'_1.fastq.gz' in counts:
            for first,second in zip_longest(records(directory/(path.stem+'_1.fastq.gz')),records(directory/(path.stem+'_2.fastq.gz'))):
                if first is None or second is None or pair_id(first[0])!=pair_id(second[0]):raise ValueError('Converted paired FASTQ identifiers disagree')
                check_mate(first[0],'1');check_mate(second[0],'2')
        temporary=directory/'temporary'
        if temporary.exists():
            if temporary.is_symlink() or temporary.resolve().parent!=directory or any(p.is_symlink() or not p.resolve().is_relative_to(temporary) for p in temporary.rglob('*')):
                raise ValueError('Temporary conversion path redirects outside owned scratch space')
            shutil.rmtree(temporary)
        return report(directory,'Local SRA conversion',{'fastq_files':rows},['Conversion only, using supplied local archive; no reads downloaded or biological conclusions generated.','FASTQ syntax, counts, paired identifiers and mate orientation are checked.','The bounded pilot supports standard single/paired split-3 output. Empty or unsupported layouts fail explicitly.','Successful scratch space is cleaned; raw FASTQ and compressed outputs remain. Failed outputs are preserved under previous_attempts on retry.'])+['command.json','conversion.log']+[p.name for p in outputs+compressed]
    return execute('local-sra-conversion-v1:'+json.dumps(tool,sort_keys=True),inputs,output,__file__,produce)
