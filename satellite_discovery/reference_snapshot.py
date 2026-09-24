"""Checksum-pinned, user-specified reference snapshots; no automatic reference selection."""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from .review_stage import execute,report
from .sequence_downloader import checksum
from .portable_paths import portable_name

MAX_TOTAL=100_000_000

def snapshot(manifest,output,offline=False):
    if Path(manifest).stat().st_size>1_000_000:raise ValueError('Snapshot specification exceeds 1 MB')
    spec=json.loads(Path(manifest).read_text(encoding='utf-8'))
    if not isinstance(spec,dict):raise ValueError('Snapshot specification must be an object')
    entries=spec.get('files',[])
    if not isinstance(entries,list) or not entries or len(entries)>100:raise ValueError('Provide 1..100 reference files')
    inputs={'specification':manifest};seen=set();total=0
    for i,row in enumerate(entries):
        if not isinstance(row,dict):raise ValueError('Snapshot file entries must be objects')
        name=row.get('name','')
        if not portable_name(name) or not re.fullmatch(r'[A-Za-z0-9_-]+\.(fa|fasta|fna|csv|tsv|json)',name) or name.casefold() in seen or name.casefold() in {'summary.json','manifest.json','references.csv'}:raise ValueError('Unsafe or duplicate snapshot filename')
        seen.add(name.casefold())
        if not isinstance(row.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',row.get('sha256','')) or type(row.get('bytes')) is not int or row['bytes']<0:raise ValueError('Each file needs an exact SHA256 and byte size')
        total+=row['bytes']
        if total>MAX_TOTAL:raise ValueError('Reference snapshot exceeds 100 MB')
        if any(not isinstance(row.get(key),str) or not row[key].strip() or len(row[key])>2000 for key in ('source','version','role')):raise ValueError('Source, version and role are required')
        for key in ('accession','database_version'):
            if key in row and (not isinstance(row[key],str) or not row[key].strip() or len(row[key])>2000):
                raise ValueError('Optional accession/database_version must be nonempty text')
        if ('path' in row)==('url' in row):raise ValueError('Specify exactly one local path or HTTPS URL')
        if not isinstance(row.get('path',row.get('url')),str):raise ValueError('Reference path or URL must be text')
        if 'path' in row:
            inputs['file_'+str(i)]=(Path(manifest).resolve().parent/row['path']).resolve()
            if inputs['file_'+str(i)].stat().st_size != row['bytes']:
                raise ValueError('Reference size or checksum mismatch: '+row['name'])
        else:
            url=urlsplit(row['url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password:raise ValueError('Use a credential-free HTTPS URL')
    def produce(paths,directory):
        retrieved_utc=datetime.now(timezone.utc).isoformat()
        for i,row in enumerate(entries):
            target=directory/row['name']
            if 'path' in row:shutil.copyfile(paths['file_'+str(i)],target)
            else:
                if offline:raise RuntimeError('Reference URL unavailable in offline mode')
                with urlopen(row['url'],timeout=30) as source,target.open('wb') as dest:
                    if urlsplit(source.url).scheme!='https':raise ValueError('Reference download redirected away from HTTPS')
                    received=0
                    while chunk:=source.read(1024*1024):
                        received+=len(chunk)
                        if received>row['bytes']:raise ValueError('Reference exceeds declared size')
                        dest.write(chunk)
            if target.stat().st_size!=row['bytes'] or checksum(target)!=row['sha256']:raise ValueError('Reference size or checksum mismatch: '+row['name'])
        rows=[{**{k:r[k] for k in ('name','bytes','sha256','source','version','role')},
               'accession':r.get('accession','unknown'),'database_version':r.get('database_version','unknown'),
               'retrieved_utc':retrieved_utc} for r in entries]
        return report(directory,'Pinned supplied-reference snapshot',{'references':rows},['An immutable snapshot of explicitly supplied sources; no database completeness or biological suitability is inferred.','Updates require a new manifest and output folder. No reference is silently replaced.'])+[r['name'] for r in entries]
    return execute('reference-snapshot-v1',inputs,output,__file__,produce)
