"""Resumable allowlisted workflow over existing artifacts; no discovery or shell steps."""
import argparse
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import re
from .sequence_downloader import checksum,write_json

FIELDS={
 'sra_conversion':{'archive'},'inventory':{'fasta'},'sequence_quality':{'fasta'},'library':{'metadata'},
 'observations':{'samples','observations'},'context':{'samples','observations'},
 'quantitative':{'measurements'},'alignment':{'alignment'},'cram':{'alignment','reference'},
 'blast_import':{'features','references','hits'},'blast_compare':{'query','reference','roles'},
 'contamination':{'features','matches','controls'},'catalogue_links':{'imports'},'reference_snapshot':{'manifest'}}

def dispatch(kind,inputs,output):
    if kind=='sra_conversion':
        from .sra_conversion import convert
        return convert(inputs['archive'],output)
    if kind=='inventory':
        from .sequence_catalogue import run
        return run(inputs['fasta'],output)
    if kind=='sequence_quality':
        from .sequence_quality import run
        return run(inputs['fasta'],output)
    if kind=='library':
        from .library_review import review
        return review(inputs['metadata'],output)
    if kind=='observations':
        from .observation_report import run
        return run(inputs['samples'],inputs['observations'],output)
    if kind=='context':
        from .context_review import run_context
        return run_context(inputs['samples'],inputs['observations'],output)
    if kind=='quantitative':
        from .context_review import run_quantitative
        return run_quantitative(inputs['measurements'],output)
    if kind in {'alignment','cram'}:
        from .alignment_adapter import run
        return run(inputs['alignment'],output,inputs.get('reference'))
    if kind=='blast_import':
        from .blast_import import run
        return run(inputs['features'],inputs['references'],inputs['hits'],output)
    if kind=='blast_compare':
        from .local_comparison import compare
        return compare(inputs['query'],inputs['reference'],inputs['roles'],output)
    if kind=='contamination':
        from .contamination_review import run
        return run(inputs['features'],inputs['matches'],inputs['controls'],output)
    if kind=='catalogue_links':
        from .catalogue_linker import run
        return run(inputs['imports'],output)
    if kind=='reference_snapshot':
        from .reference_snapshot import snapshot
        return snapshot(inputs['manifest'],output)
    raise ValueError('Unsupported workflow stage')

def validate(spec):
    stages=spec.get('stages',[]);seen=set()
    if spec.get('schema')!='artifact-workflow-v1' or not stages or len(stages)>30:raise ValueError('Provide schema artifact-workflow-v1 and 1..30 stages')
    for stage in stages:
        sid=stage.get('id','');kind=stage.get('kind')
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',sid) or sid in seen:raise ValueError('Invalid/duplicate stage ID')
        if kind not in FIELDS or set(stage.get('inputs',{}))!=FIELDS[kind]:raise ValueError('Unknown stage or incorrect input fields')
        for value in stage['inputs'].values():
            if isinstance(value,str) and value:continue
            if not isinstance(value,dict) or set(value)!={'stage','artifact'} or value['stage'] not in seen or not re.fullmatch('[A-Za-z0-9_.-]+',value['artifact']) or value['artifact'] in {'.','..','manifest.json'}:raise ValueError('Use an existing file or an earlier stage output artifact')
        seen.add(sid)
    return stages

def run(manifest,output):
    manifest=Path(manifest).resolve(strict=True);output=Path(output).resolve()
    if manifest.is_relative_to(output):raise ValueError('Keep workflow specification outside output folder')
    if manifest.stat().st_size>1_000_000:raise ValueError('Workflow specification exceeds 1 MB')
    digest=checksum(manifest);stages=validate(json.loads(manifest.read_text(encoding='utf-8')))
    output.mkdir(parents=True,exist_ok=True);lock=output/'.workflow.lock'
    try:lock.open('x').close()
    except FileExistsError:raise ValueError('Workflow is locked; do not start concurrent writers')
    marker=output/'workflow.json';result=None
    try:
        identity={'specification_sha256':digest,'engine_sha256':checksum(__file__)}
        if marker.exists():
            previous=json.loads(marker.read_text())
            if previous.get('identity')!=identity:raise ValueError('Workflow specification/engine changed; choose a new output folder')
        elif any(p!=lock for p in output.iterdir()):raise ValueError('Nonempty output has no workflow manifest')
        result={'identity':identity,'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),'stages':[]}
        write_json(marker,result)
        for stage in stages:
            inputs={}
            for key,value in stage['inputs'].items():
                if isinstance(value,str):path=(manifest.parent/value).resolve(strict=True)
                else:
                    base=output/value['stage'];prior=json.loads((base/'manifest.json').read_text())
                    artifact=value['artifact']
                    digests=prior.get('output_sha256',{})
                    if prior.get('status')!='complete' or artifact not in digests:raise ValueError('Requested artifact is not a verified completed-stage output')
                    path=(base/artifact).resolve(strict=True)
                    if not path.is_relative_to(base) or checksum(path)!=digests[artifact]:raise ValueError('Workflow artifact failed integrity check')
                inputs[key]=path
            stage_output=(output/stage['id']).resolve()
            if not stage_output.is_relative_to(output):raise ValueError('Stage output redirects outside the workflow folder')
            dispatch(stage['kind'],inputs,stage_output)
            result['stages'].append({'id':stage['id'],'kind':stage['kind'],'status':'complete'})
            write_json(marker,result)
        if checksum(manifest)!=digest:raise ValueError('Workflow specification changed during execution')
        body='<!doctype html><meta charset="utf-8"><h1>Artifact workflow</h1><p>Descriptive supplied-artifact stages only. No autonomous biological discovery.</p><ul>'
        for stage in stages:
            report_path=output/stage['id']/'report.html'
            body+='<li><a href="'+html.escape(report_path.as_uri(),quote=True)+'">'+html.escape(stage['id'])+'</a></li>'
        (output/'report.html').write_text(body+'</ul>',encoding='utf-8')
        result.update(status='complete',finished_utc=datetime.now(timezone.utc).isoformat(),report_sha256=checksum(output/'report.html'))
        write_json(marker,result);return output/'report.html'
    except BaseException as exc:
        if result is not None:result.update(status='failed',error=str(exc));write_json(marker,result)
        raise
    finally:lock.unlink()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(run(args.manifest,args.output))
