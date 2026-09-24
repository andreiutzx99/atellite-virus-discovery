"""Optional BAM/CRAM decoding into the existing bounded SAM coverage contract."""
import argparse
import gzip
from contextlib import ExitStack
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from .coverage_review import read_sam, calculate
from .review_stage import execute, report
from .sequence_downloader import checksum, write_json

LIMIT=256_000_000

def backend():
    if importlib.util.find_spec('pysam'):
        try:
            import pysam
            return {'name':'pysam','version':pysam.__version__,'htslib_version':pysam.__samtools_version__,'python':sys.executable}
        except (ImportError,OSError):
            pass # A broken optional native import must not hide an available samtools.
    path=shutil.which('samtools')
    if path:
        result=subprocess.run([path,'--version'],capture_output=True,text=True,errors='replace',timeout=15,check=True)
        return {'name':'samtools','path':str(Path(path).resolve()),'sha256':checksum(path),'version':result.stdout.splitlines()[0]}
    raise RuntimeError('BAM/CRAM support needs pysam or samtools. SAM/gzip-SAM remains available without either dependency.')

def decode(source,destination,tool,reference=None):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source.stat().st_size > LIMIT:
        raise ValueError('Alignment input exceeds 256 MB review limit')
    if source.suffix.lower()=='.cram' and reference is None:
        raise ValueError('CRAM requires an explicit local reference FASTA; no implicit reference download')
    if tool['name']=='pysam':
        command=[sys.executable,'-m',__name__,'--decode',str(source),'--output',str(destination)]
        if reference: command += ['--reference',str(reference)]
    else:
        command=[tool['path'],'view','-h']
        if reference: command += ['-T',str(reference)]
        command += [str(source)]
    log=destination.with_suffix('.log')
    # Isolate native decoding in a child so corrupt or slow input can be terminated.
    destination.touch()
    with ExitStack() as stack:
        errors=stack.enter_context(log.open('wb'))
        output=stack.enter_context(destination.open('wb')) if tool['name']=='samtools' else subprocess.DEVNULL
        process=subprocess.Popen(command,stdout=output,stderr=errors)
        start=time.monotonic()
        try:
            while process.poll() is None:
                if destination.stat().st_size > LIMIT or log.stat().st_size > 2_000_000:
                    raise ValueError('Decoded alignment or decoder log exceeds review limit')
                if time.monotonic()-start > 180:
                    raise TimeoutError('Alignment decoding exceeded 180 seconds')
                time.sleep(.05)
            if process.returncode:
                raise ValueError('Alignment decoder failed; see decoded.log')
            if destination.stat().st_size > LIMIT:
                raise ValueError('Decoded SAM exceeds 256 MB')
            if log.stat().st_size > 2_000_000:
                raise ValueError('Decoder log exceeds review limit')
        finally:
            if process.poll() is None: process.kill()
            process.wait()
    return command

def flag_summary(path):
    """Called only after strict bounded SAM validation; counts flags, not molecules."""
    path=Path(path)
    with path.open('rb') as handle:compressed=handle.read(2)==b'\x1f\x8b'
    counts={key:0 for key in ('accepted_primary_records','paired_flag_records','first_mate_flag_records','second_mate_flag_records','proper_pair_flag_records','mate_unmapped_flag_records')}
    with (gzip.open if compressed else open)(path,'rt',encoding='utf-8') as source:
        for line in source:
            if not line.strip() or line.startswith('@'):continue
            fields=line.split('\t');flag=int(fields[1])
            if flag & (4|256|2048|512|1024):continue
            counts['accepted_primary_records']+=1
            for bit,key in ((1,'paired_flag_records'),(64,'first_mate_flag_records'),(128,'second_mate_flag_records'),(2,'proper_pair_flag_records'),(8,'mate_unmapped_flag_records')):
                if flag & bit:counts[key]+=1
    return [{'metric':key,'records':value} for key,value in counts.items()]


def run(alignment,output,reference=None):
    source=Path(alignment)
    binary=source.suffix.lower() in {'.bam','.cram'}
    tool=backend() if binary else {'name':'text-SAM','version':'bounded-parser-v1'}
    inputs={'alignment':alignment,'coverage_engine':Path(__file__).with_name('coverage_review.py')}
    if reference: inputs['reference']=reference
    def produce(paths,directory):
        local_ref=None
        if reference:
            if paths['reference'].stat().st_size > LIMIT:raise ValueError('CRAM reference exceeds 256 MB review limit')
            local_ref=directory/'reference.fasta'
            shutil.copyfile(paths['reference'],local_ref)
        command=decode(paths['alignment'],directory/'decoded.sam',tool,local_ref) if binary else []
        decoded=directory/'decoded.sam' if binary else paths['alignment']
        refs,blocks,skipped=read_sam(decoded)
        rows=calculate(refs,[{'sample_id':'sam_sample'}],blocks)
        write_json(directory/'decoder.json',{'tool':tool,'command':command})
        files=report(directory,'Supplied binary alignment coverage',{'coverage':rows,'alignment_flags':flag_summary(decoded),'excluded_records':[{'reason':k,'records':v} for k,v in sorted(skipped.items())]},[
            'Existing alignments only; no mapping, read extraction or biological inference.',
            'Uses the same primary-record, CIGAR and mate-overlap conventions as SAM coverage.',
            'Pair metrics count supplied flags on accepted records; they do not verify pair consistency, unique molecules or assembly support.',
            'CRAM requires a supplied local reference. Decoding does not establish biological sample identity.'])
        return files+['decoder.json']+(['decoded.sam','decoded.log'] if binary else [])+(['reference.fasta'] if reference else [])
    # Decoder identity is frozen in the stage identifier without changing older stage manifests.
    return execute('optional-alignment-coverage-v1:'+json.dumps(tool,sort_keys=True),inputs,output,__file__,produce)

def _worker(source,destination,reference):
    import pysam
    kwargs={'reference_filename':reference} if reference else {}
    with pysam.AlignmentFile(source,'rc' if source.lower().endswith('.cram') else 'rb',**kwargs) as src:
        with open(destination,'w',encoding='utf-8',newline='\n') as out:
            out.write(str(src.header)); size=len(str(src.header).encode())
            for index,record in enumerate(src.fetch(until_eof=True)):
                text=record.to_string()+'\n'; size+=len(text.encode())
                if index>=2_000_000 or size>LIMIT or len(text)>1_000_000:
                    raise ValueError('Decoded SAM review limits exceeded')
                out.write(text)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--decode',required=True);parser.add_argument('--output',required=True);parser.add_argument('--reference')
    args=parser.parse_args();_worker(args.decode,args.output,args.reference)
