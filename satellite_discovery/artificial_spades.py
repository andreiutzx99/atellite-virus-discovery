"""Standalone fixed artificial SPAdes diagnostic. Accepts no user read/reference data."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import shutil
import time

from . import bounded_process, quality_control, sequence_catalogue
from .acquisition_fallback import classify
from .review_stage import execute, report
from .sequence_downloader import checksum, write_json


def fixture(directory, paired):
    rng = random.Random(17292026)
    truth = ''.join(rng.choice('ACGT') for _ in range(2000))
    (directory/'truth.fasta').write_text('>artificial_random_fixture\n'+truth+'\n', encoding='ascii')
    reads = [[], []]
    for repeat in range(4):
        for start in range(0, 1801 if paired else 1901, 5):
            first = truth[start:start+100]
            second = truth[start+100:start+200].translate(str.maketrans('ACGT','TGCA'))[::-1]
            for mate, sequence in enumerate((first, second) if paired else (first,)):
                reads[mate].append(f'@fixture_{repeat}_{start}/{mate+1}\n{sequence}\n+\n'+('I'*100)+'\n')
    names = ['reads_1.fastq.gz', 'reads_2.fastq.gz'] if paired else ['reads_1.fastq.gz']
    for i, name in enumerate(names):
        with (directory/name).open('wb') as dest:
            with gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as encoded:
                encoded.write(''.join(reads[i]).encode('ascii'))
    return truth, names


def validate_fixture(directory, names):
    records = [list(quality_control.records(directory/name)) for name in names]
    if not records[0] or (len(records)==2 and len(records[0])!=len(records[1])):
        raise ValueError('Artificial read fixture is empty or has unequal mates')
    if len(records)==2:
        for a,b in zip(*records):
            quality_control.check_mate(a[0],'1');quality_control.check_mate(b[0],'2')
            if quality_control.pair_id(a[0])!=quality_control.pair_id(b[0]):
                raise ValueError('Artificial fixture mate IDs differ')
    return sum(map(len,records))


def run(output, paired=False):
    if type(paired) is not bool:raise ValueError('paired must be boolean')
    tool = shutil.which('spades.py') or shutil.which('spades')
    inputs = {'diagnostic': __file__, 'runner': bounded_process.__file__,
              'fastq_parser': quality_control.__file__, 'fasta_parser': sequence_catalogue.__file__}
    if tool:inputs['executable']=Path(tool).resolve(strict=True)
    kind='artificial-spades-v1:'+('paired' if paired else 'single')

    def produce(paths, directory):
        started=time.monotonic()
        details={'status':'running','paired':paired,'fixture_seed':17292026,
                 'started_utc':datetime.now(timezone.utc).isoformat(),
                 'scientific_validation':False,'discovery_integration':False,
                 'limits':{'timeout_seconds':180,'stage_bytes':400_000_000,'tool_memory_gb':2,'threads':2},
                 'command':[],'exit_status':None}
        try:
            if not tool:raise FileNotFoundError('SPAdes unavailable: install a compatible external runtime providing spades.py or spades on PATH')
            details['executable']={'path':str(paths['executable']),'sha256':checksum(paths['executable'])}
            # Version probing uses the same bounded runner, not an unbounded PIPE.
            bounded_process.run([tool,'--version'],directory,'version.log',timeout=15,max_bytes=100_000)
            version=(directory/'version.log').read_text(encoding='utf-8',errors='replace').strip()
            if 'SPAdes' not in version:raise ValueError('Executable did not identify itself as SPAdes')
            details['version']=version
            truth,names=fixture(directory,paired)
            details['input_reads']=validate_fixture(directory,names)
            details['input_sha256']={n:checksum(directory/n) for n in names}
            command=[tool,'--only-assembler','-t','2','-m','2','-k','21,33,55','-o',str(directory/'assembly')]
            command += ['-1',str(directory/names[0]),'-2',str(directory/names[1])] if paired else ['-s',str(directory/names[0])]
            details['command']=command
            write_json(directory/'diagnostic.json',details)
            bounded_process.run(command,directory,'assembly.log',timeout=180,max_bytes=400_000_000)
            details['exit_status']=0
            source=directory/'assembly/contigs.fasta'
            if not source.resolve(strict=True).is_relative_to(directory):raise ValueError('Contig output escaped diagnostic folder')
            contigs=sequence_catalogue.read_fasta(source)
            reverse=truth.translate(str.maketrans('ACGT','TGCA'))[::-1]
            if len(contigs)!=1 or contigs[0][2] not in (truth,reverse):
                raise ValueError('Output did not exactly reconstruct the fixed artificial fixture')
            shutil.copyfile(source,directory/'contigs.fasta')
            details.update(status='passed',contig_count=1,contig_length=len(truth),exact_match_allowing_reverse_complement=True)
            # Hash every retained raw file, so reuse verifies more than the copied FASTA.
            raw={p.relative_to(directory).as_posix():checksum(p) for p in sorted((directory/'assembly').rglob('*')) if p.is_file()}
            details['raw_output_sha256']=raw
        except BaseException as exc:
            details.update(status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed',
                           failure_class=classify(exc),error=str(exc) or type(exc).__name__)
            raise
        finally:
            details.update(finished_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-started)
            write_json(directory/'diagnostic.json',details)
            files=report(directory,'Artificial SPAdes runtime diagnostic',{'diagnostic':[{
                'status':details['status'],'paired':paired,'version':details.get('version','unavailable'),
                'error':details.get('error',''),'scientific_validation':False}]},[
                'Fixed generated random data only. No user reads/references or discovery workflow integration.',
                'Passing this fixture does not show biological sensitivity or equivalence to Tadpole.',
                'Raw upstream files are retained under assembly/. Failed attempts require a fresh output folder.',
                'Resource limits are polling/tool limits, not hard OS containment. Executable checksum does not cover the entire installed distribution.'])
        return files+['diagnostic.json','version.log','assembly.log','truth.fasta','contigs.fasta']+names

    directory=Path(output).resolve()
    marker=directory/'manifest.json'
    if marker.exists():
        previous=json.loads(marker.read_text(encoding='utf-8'))
        if previous.get('status')!='complete':raise ValueError('Failed/interrupted diagnostic preserved; use a new output folder')
        # execute verifies top-level diagnostic.json before returning a cache hit;
        # validate its raw-output index only after that verification below.
    result=execute(kind,inputs,output,__file__,produce)
    if bounded_process.stage_bytes(directory)>400_000_000:raise ValueError('Diagnostic exceeds byte budget')
    details=json.loads((directory/'diagnostic.json').read_text(encoding='utf-8'))
    actual={p.relative_to(directory).as_posix() for p in (directory/'assembly').rglob('*') if p.is_file()}
    if actual!=set(details['raw_output_sha256']):raise ValueError('Raw SPAdes output inventory changed')
    for name,digest in details['raw_output_sha256'].items():
        target=directory/name
        if not name.startswith('assembly/') or not target.resolve(strict=True).is_relative_to(directory) or checksum(target)!=digest:
            raise ValueError('Raw SPAdes output integrity failure')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--paired',action='store_true')
    args=parser.parse_args()
    try:run(args.output,args.paired)
    except (OSError,ValueError,RuntimeError,KeyboardInterrupt) as exc:parser.exit(1,str(exc)+'\n')
    print('PASSED: '+str(Path(args.output).resolve()/'report.html'))


if __name__=='__main__':main()
