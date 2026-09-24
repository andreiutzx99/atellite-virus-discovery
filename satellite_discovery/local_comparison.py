"""Local BLAST comparison of supplied FASTA against supplied, documented references."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from .sequence_catalogue import read_fasta
from .sequence_downloader import checksum,write_json
from .review_stage import execute,table,unique,report
from .blast_import import normalize_hits
from .contamination_review import ROLES
from .bounded_process import run as process

def tools(directory=None):
    result={}
    project=Path(__file__).resolve().parents[1]
    for name in ('blastn','makeblastdb'):
        filename=name+('.exe' if os.name=='nt' else '')
        path=Path(directory)/filename if directory else None
        if path is None:
            found=shutil.which(name)
            if found: path=Path(found)
            else:
                matches=list(project.glob('.tools/blast-*/ncbi-blast-*/bin/'+filename))
                if len(matches)==1:path=matches[0]
        if path is None or not path.is_file():raise RuntimeError('Missing '+name+'; configure BLAST+ bin directory or PATH')
        version=subprocess.run([str(path.resolve()),'-version'],capture_output=True,text=True,check=True,timeout=15).stdout.strip()
        result[name]={'path':str(path.resolve()),'sha256':checksum(path),'version':version}
    return result

def compare(query,reference,roles,output,tool_directory=None):
    binaries=tools(tool_directory)
    inputs={'query':query,'reference':reference,'roles':roles,'parser':Path(__file__).with_name('blast_import.py'),'fasta_parser':Path(__file__).with_name('sequence_catalogue.py'),'process_engine':Path(__file__).with_name('bounded_process.py')}
    def produce(paths,directory):
        queries=read_fasta(paths['query']); refs=read_fasta(paths['reference'])
        roles=table(paths['roles'],('reference_id','reference_role','reference_source','reference_version'))
        if set(unique(roles,'reference_id'))!={r[0] for r in refs} or any(r['reference_role'] not in ROLES for r in roles):
            raise ValueError('Every supplied reference requires exactly one valid role and provenance record')
        # Normalization preserves nucleotide content; no reconstruction or annotation.
        for filename,records in [('queries.fasta',queries),('references.fasta',refs)]:
            (directory/filename).write_text(''.join('>'+i+'\n'+s+'\n' for i,h,s in records),encoding='ascii')
        commands=[
            [binaries['makeblastdb']['path'],'-in',str(directory/'references.fasta'),'-dbtype','nucl','-parse_seqids','-blastdb_version','4','-out',str(directory/'database')],
            [binaries['blastn']['path'],'-query',str(directory/'queries.fasta'),'-db',str(directory/'database'),'-outfmt','6','-out',str(directory/'hits.tsv'),'-num_threads','1']]
        write_json(directory/'commands.json',{'tools':binaries,'commands':commands,'parameters':'BLAST default search settings; one thread; standard nucleotide outfmt 6'})
        for index,command in enumerate(commands):
            process(command,directory,f'tool-{index}.log')
        features=[{'feature_id':i,'length':len(s)} for i,h,s in queries]
        hits,status=normalize_hits(directory/'hits.tsv',features,roles)
        files=report(directory,'Local supplied-reference BLAST comparison',{'matches':hits,'features':features,'hit_status':status},[
            'References and their roles are supplied; database completeness and sample identity are not established.',
            'BLAST defaults and executable versions are recorded. No reported hit is not evidence of novelty.',
            'No satellite, helper-dependency, DVG, functional compatibility or confidence classification is performed.'])
        if not hits:(directory/'matches.csv').write_text('feature_id,reference_id,reference_role,query_start,query_end,percent_identity,reference_source,reference_version\n')
        return files+['commands.json','queries.fasta','references.fasta','hits.tsv','tool-0.log','tool-1.log']+[p.name for p in directory.glob('database.*') if p.is_file()]
    return execute('local-blast-v1:'+json.dumps(binaries,sort_keys=True),inputs,output,__file__,produce)
