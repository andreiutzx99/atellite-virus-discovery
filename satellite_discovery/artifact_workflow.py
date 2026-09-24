"""Resumable allowlisted workflow over existing artifacts; no discovery or shell steps."""
import argparse
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import re
from .sequence_downloader import checksum,write_json
from .portable_paths import portable_name

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
    if not isinstance(spec,dict):raise ValueError('Workflow specification must be an object')
    stages=spec.get('stages',[]);seen=set();portable_seen=set()
    if spec.get('schema')!='artifact-workflow-v1' or not isinstance(stages,list) or not stages or len(stages)>30:raise ValueError('Provide schema artifact-workflow-v1 and 1..30 stages')
    for stage in stages:
        if not isinstance(stage,dict) or not isinstance(stage.get('inputs'),dict):raise ValueError('Every stage and inputs must be objects')
        sid=stage.get('id','');kind=stage.get('kind')
        if not portable_name(sid) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',sid) or sid.casefold() in portable_seen:raise ValueError('Invalid/duplicate portable stage ID')
        if not isinstance(kind,str) or kind not in FIELDS or set(stage.get('inputs',{}))!=FIELDS[kind]:raise ValueError('Unknown stage or incorrect input fields')
        for value in stage['inputs'].values():
            if isinstance(value,str) and value:continue
            if not isinstance(value,dict) or set(value)!={'stage','artifact'} or not isinstance(value['stage'],str) or value['stage'] not in seen or not portable_name(value['artifact']) or value['artifact'].casefold()=='manifest.json':raise ValueError('Use an existing file or an earlier stage output artifact')
        seen.add(sid)
        portable_seen.add(sid.casefold())
    return stages


def write_status(output, result):
    """Write a useful report even when a stage cannot start or is interrupted."""
    body = '<!doctype html><meta charset="utf-8"><title>Artifact workflow</title><h1>Artifact workflow</h1>'
    body += '<p>Status: ' + html.escape(result['status']) + '</p>'
    body += '<p>Descriptive supplied-artifact stages only. No autonomous biological discovery.</p><ul>'
    for stage in result['stages']:
        label = html.escape(stage['id'] + ': ' + stage['status'])
        if stage['status'] == 'complete':
            label = '<a href="' + stage['id'] + '/report.html">' + label + '</a>'
        body += '<li>' + label
        if 'error' in stage:
            body += '<pre>' + html.escape(stage['error']) + '</pre>'
        body += '</li>'
    if 'error' in result:
        body += '<li>' + html.escape(result['error']) + '</li>'
    (output/'report.html').write_text(body+'</ul>', encoding='utf-8')
    result['report_sha256'] = checksum(output/'report.html')
    write_json(output/'workflow.json', result)

def run(manifest,output):
    manifest=Path(manifest).resolve(strict=True);output=Path(output).resolve()
    if manifest.is_relative_to(output):raise ValueError('Keep workflow specification outside output folder')
    if manifest.stat().st_size>1_000_000:raise ValueError('Workflow specification exceeds 1 MB')
    digest=checksum(manifest);stages=validate(json.loads(manifest.read_text(encoding='utf-8')))
    output.mkdir(parents=True,exist_ok=True);lock=output/'.workflow.lock'
    try:lock.open('x').close()
    except FileExistsError:raise ValueError('Workflow is locked; do not start concurrent writers')
    marker=output/'workflow.json';result=None;active=None
    try:
        identity={'specification_sha256':digest,'engine_sha256':checksum(__file__),
                  'portable_paths_sha256':checksum(Path(__file__).with_name('portable_paths.py'))}
        if marker.exists():
            previous=json.loads(marker.read_text())
            if previous.get('identity')!=identity:raise ValueError('Workflow specification/engine changed; choose a new output folder')
        elif any(p!=lock for p in output.iterdir()):raise ValueError('Nonempty output has no workflow manifest')
        result={'identity':identity,'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
                'stages':[{'id':s['id'],'kind':s['kind'],'status':'pending'} for s in stages]}
        write_status(output,result)
        for stage,active in zip(stages,result['stages']):
            active.update(status='running',started_utc=datetime.now(timezone.utc).isoformat())
            write_status(output,result)
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
            active.update(status='complete',finished_utc=datetime.now(timezone.utc).isoformat())
            write_status(output,result)
            active=None
        if checksum(manifest)!=digest:raise ValueError('Workflow specification changed during execution')
        result.update(status='complete',finished_utc=datetime.now(timezone.utc).isoformat())
        write_status(output,result);return output/'report.html'
    except BaseException as exc:
        if result is not None:
            status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
            failure={'status':status,'error':str(exc) or type(exc).__name__,
                     'error_type':type(exc).__name__,'finished_utc':datetime.now(timezone.utc).isoformat()}
            result.update(failure)
            if active is not None:active.update(failure)
            write_status(output,result)
        raise
    finally:lock.unlink()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(run(args.manifest,args.output))
