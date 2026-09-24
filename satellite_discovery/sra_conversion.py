"""Conditional local SRA archive conversion; no archive search or download."""
import json
import gzip
import re
import shutil
import subprocess
from pathlib import Path
from .bounded_process import run as process
from .quality_control import records
from .review_stage import execute,report
from .sequence_downloader import checksum,write_json

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
        command=[binary,str(paths['archive']),'--split-3','--threads','1','--outdir',str(directory),'--temp',str(directory/'temporary'),'--force']
        write_json(directory/'command.json',{'command':command,'tool':tool,'input_sha256':checksum(paths['archive'])})
        process(command,directory,'conversion.log',timeout=300,max_bytes=1_000_000_000)
        outputs=sorted(directory.glob(path.stem+'*.fastq'))
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
        return report(directory,'Local SRA conversion',{'fastq_files':rows},['Conversion only, using supplied local archive; no reads downloaded or biological conclusions generated.','FASTQ syntax and mate counts are checked. Full paired identifier validation remains in QC.','The bounded pilot supports standard single/paired split-3 output. Other archive layouts fail explicitly.'])+['command.json','conversion.log']+[p.name for p in outputs+compressed]
    return execute('local-sra-conversion-v1:'+json.dumps(tool,sort_keys=True),inputs,output,__file__,produce)
