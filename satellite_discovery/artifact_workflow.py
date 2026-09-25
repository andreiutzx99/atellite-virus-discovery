"""Resumable allowlisted workflow over existing artifacts; no discovery or shell steps."""
import argparse
from datetime import datetime,timezone
import html
from importlib import import_module
import json
from pathlib import Path
import re
from .sequence_downloader import checksum,write_json
from .portable_paths import portable_name
from . import reproducibility
from . import stage_lock
from .external_tool import DependencyMissingError, ExternalToolExecution
from .example_transform_adapter import ExampleTextTransformAdapter
from .assembly_adapters import AssemblyWorkflowAdapter
from .stage_registry import WorkflowStageRegistry, valid_module_name
from .workflow_states import (
    STAGE_TRANSITIONS, WORKFLOW_TRANSITIONS, aggregate_stage_status, transition,
)


def _legacy_handler(module_name, function_name, input_names, alignment=False):
    """Create a trusted wrapper for an existing built-in stage."""
    def invoke(inputs, output, config):
        if config:
            raise ValueError('Built-in stages do not accept configuration')
        module = import_module('.'+module_name, package=__package__)
        function = getattr(module, function_name)
        args = [inputs[name] for name in input_names]
        if alignment:
            return function(args[0], output, inputs.get('reference'))
        return function(*args, output)
    return invoke


def build_default_registry():
    registry = WorkflowStageRegistry()
    builtins = {
        'artifact_benchmark': ('artifact_benchmark', 'run', ('datasets','expectations','artifacts'), False),
        'sra_conversion': ('sra_conversion', 'convert', ('archive',), False),
        'inventory': ('sequence_catalogue', 'run', ('fasta',), False),
        'sequence_quality': ('sequence_quality', 'run', ('fasta',), False),
        'library': ('library_review', 'review', ('metadata',), False),
        'observations': ('observation_report', 'run', ('samples','observations'), False),
        'context': ('context_review', 'run_context', ('samples','observations'), False),
        'quantitative': ('context_review', 'run_quantitative', ('measurements',), False),
        'alignment': ('alignment_adapter', 'run', ('alignment',), True),
        'cram': ('alignment_adapter', 'run', ('alignment','reference'), True),
        'blast_import': ('blast_import', 'run', ('features','references','hits'), False),
        'blast_compare': ('local_comparison', 'compare', ('query','reference','roles'), False),
        'contamination': ('contamination_review', 'run', ('features','matches','controls'), False),
        'catalogue_links': ('catalogue_linker', 'run', ('imports',), False),
        'reference_snapshot': ('reference_snapshot', 'snapshot', ('manifest',), False),
        'reference_record_import': ('reference_record_import', 'import_from_snapshot', ('references_table',), False),
    }
    for kind, (module, function, fields, alignment) in builtins.items():
        registry.register(
            kind, fields, _legacy_handler(module, function, fields, alignment),
            version='1', description='Existing trusted built-in workflow stage.',
        )
    registry.register(
        'external_module', None, None, version='1', dynamic_inputs=True,
        description='Declarative requirement resolved only from trusted registrations.',
    )
    registry.register_external_adapter(ExampleTextTransformAdapter())
    registry.register_external_adapter(AssemblyWorkflowAdapter())
    return registry


DEFAULT_STAGE_REGISTRY = build_default_registry()
FIELDS = DEFAULT_STAGE_REGISTRY.fields


def dispatch(kind,inputs,output,config=None,registry=None):
    registry = registry or DEFAULT_STAGE_REGISTRY
    definition = registry.get(kind)
    if kind == 'external_module':
        raise ValueError('External module requirements must be resolved by the workflow runner')
    normalized = registry.validate_config(kind, {} if config is None else config)
    if definition.external_tool:
        return definition.handler.execute(inputs, output, normalized)
    return definition.handler(inputs, output, normalized)


def _validate_input_mapping(inputs, seen, dynamic=False):
    if not isinstance(inputs, dict):
        raise ValueError('Every stage inputs value must be an object')
    for name, value in inputs.items():
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}', name):
            raise ValueError('Invalid stage input name')
        if isinstance(value, str) and value:
            continue
        if (not isinstance(value, dict) or set(value) != {'stage','artifact'}
                or not isinstance(value['stage'], str) or value['stage'] not in seen
                or not portable_name(value['artifact'])
                or value['artifact'].casefold() == 'manifest.json'):
            raise ValueError('Use an existing file or an earlier stage output artifact')


def validate(spec,registry=None):
    registry = registry or DEFAULT_STAGE_REGISTRY
    if not isinstance(spec,dict):raise ValueError('Workflow specification must be an object')
    if set(spec)!={'schema','stages'}:raise ValueError('Unknown or missing workflow configuration fields')
    stages=spec.get('stages',[]);seen=set();portable_seen=set()
    if spec.get('schema')!='artifact-workflow-v1' or not isinstance(stages,list) or not stages or len(stages)>30:raise ValueError('Provide schema artifact-workflow-v1 and 1..30 stages')
    for stage in stages:
        if not isinstance(stage,dict) or not isinstance(stage.get('inputs'),dict):raise ValueError('Every stage and inputs must be objects')
        sid=stage.get('id','');kind=stage.get('kind')
        if not portable_name(sid) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',sid) or sid.casefold() in portable_seen:raise ValueError('Invalid/duplicate portable stage ID')
        if not isinstance(kind,str):
            raise ValueError('Unknown workflow stage')
        definition=registry.get(kind)
        if kind == 'external_module':
            allowed={'id','kind','module','inputs','config','skip'}
            if set(stage) - allowed or not {'id','kind','module','inputs'} <= set(stage):
                raise ValueError('Unknown or missing external-module stage fields')
            if 'skip' in stage and type(stage['skip']) is not bool:
                raise ValueError('Stage skip must be true or false')
            module_name=stage.get('module')
            if not valid_module_name(module_name):
                raise ValueError('External module name must be a safe registered identifier')
            module=registry.get_module(module_name)
            if module is not None:
                required=module.input_fields or frozenset()
                allowed=required | module.optional_input_fields
                if not required <= set(stage['inputs']) or set(stage['inputs'])-allowed:
                    raise ValueError('External module has incorrect input fields')
                registry.validate_config(module.kind,stage.get('config',{}))
            else:
                _validate_input_mapping(stage['inputs'],seen,dynamic=True)
                if not isinstance(stage.get('config',{}),dict):
                    raise ValueError('External module config must be an object')
                try:json.dumps(stage.get('config',{}),allow_nan=False)
                except (TypeError,ValueError) as error:raise ValueError('External module config must be JSON-safe') from error
        else:
            if set(stage) - {'id','kind','inputs','config','skip'} or not {'id','kind','inputs'} <= set(stage):
                raise ValueError('Unknown or missing stage configuration fields')
            if 'skip' in stage and type(stage['skip']) is not bool:
                raise ValueError('Stage skip must be true or false')
            required=definition.input_fields or frozenset()
            allowed=required | definition.optional_input_fields
            if not definition.dynamic_inputs and (not required <= set(stage['inputs']) or set(stage['inputs'])-allowed):
                raise ValueError('Unknown stage or incorrect input fields')
            _validate_input_mapping(stage['inputs'],seen,dynamic=definition.dynamic_inputs)
            registry.validate_config(kind,stage.get('config',{}))
        seen.add(sid)
        portable_seen.add(sid.casefold())
    return stages


def inspect_configuration(manifest,registry=None):
    """Read-only preflight: paths and stage requirements, without running stages."""
    registry = registry or DEFAULT_STAGE_REGISTRY
    manifest=Path(manifest).resolve(strict=True)
    if manifest.stat().st_size>1_000_000:raise ValueError('Workflow specification exceeds 1 MB')
    stages=validate(json.loads(manifest.read_text(encoding='utf-8')),registry)
    rows=[]
    for stage in stages:
        inputs={}
        for key,value in stage['inputs'].items():
            if isinstance(value,str):
                path=(manifest.parent/value).resolve()
                inputs[key]={'path':str(path),'status':'available' if path.is_file() else 'missing'}
            else:inputs[key]={'status':'produced_by_earlier_stage',**value}
        row={'id':stage['id'],'kind':stage['kind'],'inputs':inputs}
        if stage['kind']=='external_module':
            row.update(module=stage['module'],
                       module_status='registered' if registry.has_module(stage['module']) else 'external_module_required')
        rows.append(row)
    return {'schema':'artifact-preflight-v1','specification':str(manifest),'sha256':checksum(manifest),
            'stages':rows,'registry':registry.describe(),
            'note':'Syntax/path check only. Use dependency diagnostics for runtime readiness.'}


def write_status(output, result):
    """Write a useful report even when a stage cannot start or is interrupted."""
    write_json(output/'workflow.json', result)
    reproducibility.save(output, result)
    labels={
        'pending':'PENDING — not started',
        'running':'RUNNING — in progress',
        'complete':'COMPLETE',
        'skipped':'SKIPPED — not executed by request',
        'dependency_missing':'DEPENDENCY MISSING — required executable unavailable',
        'external_module_required':'EXTERNAL MODULE REQUIRED — trusted module not registered',
        'failed':'FAILED — execution did not complete',
        'interrupted':'INTERRUPTED — execution was stopped',
        'partial':'PARTIAL — some stages were skipped',
    }
    body = '<!doctype html><meta charset="utf-8"><title>Artifact workflow</title><h1>Artifact workflow</h1>'
    body += '<p>Status: ' + html.escape(labels.get(result['status'],result['status'])) + '</p>'
    body += '<p>Descriptive supplied-artifact stages only. No autonomous biological discovery.</p><ul>'
    for stage in result['stages']:
        label = html.escape(stage['id'] + ': ' + labels.get(stage['status'],stage['status']))
        if stage['status'] == 'complete' and (output/stage['id']/'report.html').is_file():
            label = '<a href="' + stage['id'] + '/report.html">' + label + '</a>'
        body += '<li>' + label
        if stage.get('required_module'):
            body += '<p>Required trusted module: ' + html.escape(stage['required_module']) + '</p>'
        if stage.get('reason'):
            body += '<p>' + html.escape(stage['reason']) + '</p>'
        if stage.get('kind') == 'assembly':
            assembly = stage.get('assembly', {})
            assembler = stage.get('assembler') or assembly.get('assembler')
            if assembler:
                body += '<p>Assembler: ' + html.escape(str(assembler)) + '</p>'
            if stage.get('status') == 'dependency_missing':
                body += '<p>DEPENDENCY MISSING</p>'
            if assembly:
                for label_text, key in (
                    ('Version', 'tool_version'),
                    ('Input layout', 'input_layout'),
                    ('Runtime (seconds)', 'runtime_seconds'),
                    ('Contig count', 'contig_count'),
                    ('Canonical contigs', 'contig_path'),
                    ('Dependency status', 'dependency_status'),
                    ('Reuse status', 'reuse_status'),
                ):
                    if assembly.get(key) is not None:
                        body += '<p>' + html.escape(label_text + ': ' + str(assembly[key])) + '</p>'
                for warning in assembly.get('warnings', []):
                    body += '<p>Warning: ' + html.escape(str(warning)) + '</p>'
        if stage.get('status')=='pending':
            body += '<p>Not started because an earlier stage did not finish.</p>'
        if stage.get('dependency_report'):
            for dependency in stage['dependency_report'].get('dependencies',[]):
                text=f"Executable {dependency.get('tool','unknown')}: {dependency.get('status','unknown')}"
                if dependency.get('path'):text+=' ('+dependency['path']+')'
                body += '<p>' + html.escape(text) + '</p>'
        if 'error' in stage:
            body += '<pre>' + html.escape(stage['error']) + '</pre>'
        body += '</li>'
    if 'error' in result:
        body += '<li>' + html.escape(result['error']) + '</li>'
    body += '</ul><p><a href="reproducibility.json">Reproducibility manifest</a></p>'
    temporary = output/'report.html.tmp'
    temporary.write_text(body, encoding='utf-8')
    temporary.replace(output/'report.html')
    result['report_sha256'] = checksum(output/'report.html')
    write_json(output/'workflow.json', result)

def run(manifest,output,registry=None):
    registry=registry or DEFAULT_STAGE_REGISTRY
    manifest=Path(manifest).resolve(strict=True);output=Path(output).resolve()
    if manifest.is_relative_to(output):raise ValueError('Keep workflow specification outside output folder')
    if manifest.stat().st_size>1_000_000:raise ValueError('Workflow specification exceeds 1 MB')
    specification=json.loads(manifest.read_text(encoding='utf-8'))
    digest=checksum(manifest);stages=validate(specification,registry)
    output.mkdir(parents=True,exist_ok=True);lock=output/'.workflow.lock'
    lock_token=stage_lock.acquire(lock)
    marker=output/'workflow.json';result=None;active=None
    try:
        runtime=reproducibility.environment()
        identity={'specification_sha256':digest,'engine_sha256':checksum(__file__),
                  'package_sha256':runtime['source_sha256'],
                  'portable_paths_sha256':checksum(Path(__file__).with_name('portable_paths.py'))}
        if marker.exists():
            previous=json.loads(marker.read_text(encoding='utf-8'))
            if not isinstance(previous,dict):raise ValueError('Workflow manifest is malformed; existing files preserved')
            if previous.get('identity')!=identity:raise ValueError('Workflow specification/engine changed; choose a new output folder')
        elif any(p!=lock for p in output.iterdir()):raise ValueError('Nonempty output has no workflow manifest')
        stage_rows=[]
        for item in stages:
            row={'id':item['id'],'kind':item['kind'],'status':'pending'}
            if item['kind']=='external_module':row['module']=item['module']
            stage_rows.append(row)
        result={'identity':identity,'environment':runtime,'registry':registry.describe(),
                'configuration':specification,'status':'pending',
                'stages':stage_rows}
        transition(result,'running',WORKFLOW_TRANSITIONS,
                   started_utc=datetime.now(timezone.utc).isoformat())
        write_status(output,result)
        for stage,active in zip(stages,result['stages']):
            if stage.get('skip') is True:
                transition(active,'skipped',STAGE_TRANSITIONS,
                           reason='Explicitly skipped by workflow configuration.',
                           finished_utc=datetime.now(timezone.utc).isoformat())
                write_status(output,result)
                active=None
                continue

            if stage['kind']=='external_module':
                definition=registry.get_module(stage['module'])
                if definition is None:
                    reason='The required trusted external module is not registered in this application.'
                    active.update(required_module=stage['module'])
                    transition(active,'external_module_required',STAGE_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    transition(result,'external_module_required',WORKFLOW_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    write_status(output,result)
                    active=None
                    return output/'report.html'
                config=registry.validate_config(definition.kind,stage.get('config',{}))
                module_name=stage['module']
            else:
                definition=registry.get(stage['kind'])
                config=registry.validate_config(stage['kind'],stage.get('config',{}))
                module_name=None

            transition(active,'running',STAGE_TRANSITIONS,
                       started_utc=datetime.now(timezone.utc).isoformat())
            if module_name:active['registered_module']=module_name
            if stage['kind'] == 'assembly':
                active['assembler'] = config['assembler']
            write_status(output,result)
            inputs={}
            for key,value in stage['inputs'].items():
                if isinstance(value,str):path=(manifest.parent/value).resolve(strict=True)
                else:
                    base=output/value['stage'];prior=json.loads((base/'manifest.json').read_text())
                    if not isinstance(prior,dict):raise ValueError('Stage manifest is malformed')
                    artifact=value['artifact']
                    digests=prior.get('output_sha256',{})
                    if prior.get('status')!='complete' or artifact not in digests:raise ValueError('Requested artifact is not a verified completed-stage output')
                    path=(base/artifact).resolve(strict=True)
                    if not path.is_relative_to(base) or checksum(path)!=digests[artifact]:raise ValueError('Workflow artifact failed integrity check')
                inputs[key]=path
            active['inputs']={key:{'path':str(path),'sha256':checksum(path),'bytes':path.stat().st_size} for key,path in inputs.items()}
            stage_output=(output/stage['id']).resolve()
            if not stage_output.is_relative_to(output):raise ValueError('Stage output redirects outside the workflow folder')

            if definition.external_tool:
                configured_inspector=getattr(definition.handler,'inspect_dependency_for_config',None)
                dependency=(
                    configured_inspector(config)
                    if callable(configured_inspector)
                    else definition.handler.inspect_dependency()
                )
                active['dependency_report']=dependency
                if dependency['status']!='available':
                    reason='One or more required external executables are unavailable.'
                    transition(active,'dependency_missing',STAGE_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    transition(result,'dependency_missing',WORKFLOW_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    write_status(output,result)
                    active=None
                    return output/'report.html'

            stage_marker=stage_output/'manifest.json'
            before=checksum(stage_marker) if stage_marker.is_file() else None
            try:
                if definition.external_tool:
                    if stage['kind'] == 'assembly':
                        outcome=definition.handler.execute(
                            inputs,stage_output,config,context={'stage_id':stage['id']}
                        )
                    else:
                        outcome=definition.handler.execute(inputs,stage_output,config)
                else:
                    outcome=definition.handler(inputs,stage_output,config)
            except DependencyMissingError as error:
                reason=str(error)
                active['dependency_report']=error.dependency_report
                transition(active,'dependency_missing',STAGE_TRANSITIONS,
                           reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                transition(result,'dependency_missing',WORKFLOW_TRANSITIONS,
                           reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                write_status(output,result)
                active=None
                return output/'report.html'

            if isinstance(outcome,ExternalToolExecution):
                active.update(
                    execution=outcome.execution,
                    external_adapter=outcome.adapter,
                    external_tool=outcome.tool,
                    command=outcome.command,
                    output_inventory=outcome.output_inventory,
                    external_manifest_sha256=outcome.manifest_sha256,
                )
                if stage['kind'] == 'assembly':
                    assembly_record = json.loads((stage_output/'assembly_manifest.json').read_text(encoding='utf-8'))
                    active['assembly'] = {
                        'assembler': assembly_record['assembler'],
                        'tool_version': assembly_record['external_tool_version'],
                        'input_layout': assembly_record['input_layout'],
                        'runtime_seconds': assembly_record['duration_seconds'],
                        'contig_count': assembly_record['contig_count'],
                        'contig_path': assembly_record['contig_output'],
                        'dependency_status': 'available',
                        'reuse_status': outcome.execution,
                        'warnings': assembly_record.get('warnings', []),
                    }
            else:
                active['execution']='verified_reuse' if before is not None and stage_marker.is_file() and checksum(stage_marker)==before else 'executed'
            if stage['kind']=='reference_snapshot':
                source=reproducibility.bounded_json(inputs['manifest'],inputs['manifest'].parent)
                fields=('name','bytes','sha256','source','version','role','accession','database_version',
                        'reference_id','display_name','category','provenance','update_status')
                active['reference_specification']=[{k:r[k] for k in fields if k in r} for r in source['files']]
            transition(active,'complete',STAGE_TRANSITIONS,
                       finished_utc=datetime.now(timezone.utc).isoformat())
            write_status(output,result)
            active=None
        if checksum(manifest)!=digest:raise ValueError('Workflow specification changed during execution')
        final_status=aggregate_stage_status(result['stages'])
        transition(result,final_status,WORKFLOW_TRANSITIONS,
                   finished_utc=datetime.now(timezone.utc).isoformat())
        write_status(output,result);return output/'report.html'
    except BaseException as exc:
        if result is not None:
            status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
            failure={'error':str(exc) or type(exc).__name__,
                     'error_type':type(exc).__name__,'finished_utc':datetime.now(timezone.utc).isoformat()}
            if active is not None and active.get('status')=='running':
                transition(active,status,STAGE_TRANSITIONS,**failure)
            if result.get('status')=='running':
                transition(result,status,WORKFLOW_TRANSITIONS,**failure)
            write_status(output,result)
        raise
    finally:stage_lock.release(lock,lock_token)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(run(args.manifest,args.output))
