"""Resumable allowlisted workflow over existing artifacts; no discovery or shell steps."""
import argparse
from datetime import datetime,timezone
import html
import hashlib
from importlib import import_module
import json
from pathlib import Path
import re
import tempfile
import uuid
from .sequence_downloader import checksum,write_json
from .portable_paths import portable_name
from . import reproducibility
from . import stage_lock
from .external_tool import DependencyMissingError, ExternalToolExecution
from .example_transform_adapter import ExampleTextTransformAdapter
from .assembly_adapters import AssemblyWorkflowAdapter
from . import artifact_contracts, artifact_stage_handlers, local_comparison
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
        'contamination': ('contamination_review', 'run', ('features','matches','controls'), False),
        'catalogue_links': ('catalogue_linker', 'run', ('imports',), False),
        'reference_snapshot': ('reference_snapshot', 'snapshot', ('manifest',), False),
        'reference_record_import': ('reference_record_import', 'import_from_snapshot', ('references_table',), False),
    }
    input_contracts = {
        'sra_conversion': {'archive': 'sra_archive'},
        'inventory': {'fasta': ('raw_fasta', 'canonical_contig_fasta',
                                'catalogue_fasta', 'reference_records_fasta')},
        'observations': {'samples': 'sample_table', 'observations': 'observation_table'},
        'catalogue_links': {'imports': 'catalogue_imports'},
        'reference_snapshot': {'manifest': 'reference_snapshot_config'},
        'reference_record_import': {'references_table': 'reference_catalogue'},
        'blast_import': {'features': 'sequence_catalogue_records',
                         'references': 'reference_roles',
                         'hits': 'blast_hit_table'},
        'contamination': {'features': 'sequence_catalogue_records',
                          'matches': 'sequence_comparison_evidence',
                          'controls': 'sample_table'},
    }
    output_contracts = {
        'sra_conversion': {'*.fastq.gz': 'validated_fastq'},
        'inventory': {
            'records.csv': 'sequence_catalogue_records',
            'summary.json': 'sequence_catalogue_summary',
            'catalogue.sqlite': 'sequence_catalogue',
            'sequences.fasta': 'catalogue_fasta',
            'report.html': 'report',
        },
        'observations': {
            'summary.json': 'occurrence_summary',
            'recurrence.csv': 'occurrence_table',
            'comparisons.csv': 'occurrence_table',
            'report.html': 'report',
        },
        'catalogue_links': {
            'summary.json': 'occurrence_summary',
            'report.html': 'report',
            'linked.sqlite': 'sequence_catalogue',
        },
        'reference_snapshot': {
            'references.csv': 'reference_catalogue',
            'summary.json': 'reference_snapshot_summary',
            'report.html': 'report',
        },
        'reference_record_import': {
            'records.csv': 'reference_record_catalogue',
            'records.fasta': 'reference_records_fasta',
            'catalogue.sqlite': 'reference_record_database',
            'snapshot.json': 'reference_snapshot_manifest',
            'report.html': 'report',
        },
        'blast_import': {
            'matches.csv': 'sequence_comparison_evidence',
            'summary.json': 'comparison_summary',
            'report.html': 'report',
        },
    }
    for kind, (module, function, fields, alignment) in builtins.items():
        registry.register(
            kind, fields, _legacy_handler(module, function, fields, alignment),
            version='1', description='Existing trusted built-in workflow stage.',
            input_contracts=input_contracts.get(kind, {}),
            output_contracts=output_contracts.get(kind, {}),
        )
    registry.register(
        'fastq_validate', ('read1',), artifact_stage_handlers.validate_fastq,
        optional_input_fields=('read2',), version='1',
        config_validator=artifact_stage_handlers.validate_fastq_config,
        input_contracts={'read1': 'raw_read', 'read2': 'raw_read'},
        output_contracts={
            'read1.fastq.gz': 'validated_fastq',
            'read2.fastq.gz': 'validated_fastq',
            'fastq.json': 'fastq_manifest',
        },
        description='Validates and snapshots declared FASTQ inputs without running QC.',
    )
    registry.register(
        'catalogue_observations', None, artifact_stage_handlers.catalogue_observations,
        version='1', dynamic_inputs=True,
        config_validator=artifact_stage_handlers.validate_observation_config,
        input_contracts={'*': 'sequence_catalogue'},
        output_contracts={
            'samples.csv': 'sample_table',
            'observations.csv': 'observation_table',
            'occurrences.csv': 'occurrence_table',
            'summary.json': 'occurrence_summary',
            'recurrence.csv': 'occurrence_table',
            'comparisons.csv': 'occurrence_table',
            'report.html': 'report',
        },
        description='Links exact catalogue sequences to explicitly declared sample metadata.',
    )
    registry.register(
        'reference_roles', ('records',), artifact_stage_handlers.reference_roles_from_records,
        version='1', input_contracts={'records': 'reference_record_catalogue'},
        output_contracts={'roles.csv': 'reference_roles', 'report.html': 'report'},
        description='Maps explicitly supplied reference categories to comparison roles.',
    )
    registry.register(
        'workflow_report', None, artifact_stage_handlers.workflow_report,
        version='1', dynamic_inputs=True,
        config_validator=artifact_stage_handlers.validate_workflow_report_config,
        input_contracts={'*': (
            'assembly_manifest', 'canonical_contig_fasta',
            'sequence_catalogue_summary', 'reference_snapshot_summary',
            'reference_snapshot_manifest', 'comparison_summary',
            'comparison_parameters', 'occurrence_summary', 'report',
        )},
        output_contracts={'report.json': 'workflow_report_json', 'report.html': 'report'},
        description='Consolidates declared structured stage artifacts without interpretation.',
    )
    registry.register(
        'blast_compare', ('query', 'reference', 'roles'),
        _legacy_handler('local_comparison', 'compare', ('query', 'reference', 'roles'), False),
        version='1',
        config_validator=lambda config: _empty_stage_config(config),
        dependency_inspector=_blast_dependency,
        input_contracts={
            'query': ('canonical_contig_fasta', 'catalogue_fasta', 'raw_fasta'),
            'reference': ('reference_records_fasta', 'raw_fasta'),
            'roles': 'reference_roles',
        },
        output_contracts={
            'matches.csv': 'sequence_comparison_evidence',
            'summary.json': 'comparison_summary',
            'hits.tsv': 'blast_hit_table',
            'commands.json': 'comparison_parameters',
        },
        description='Compares declared sequences only against the supplied reference collection.',
    )
    registry.register(
        'external_module', None, None, version='1', dynamic_inputs=True,
        description='Declarative requirement resolved only from trusted registrations.',
    )
    registry.register_external_adapter(ExampleTextTransformAdapter())
    registry.register_external_adapter(AssemblyWorkflowAdapter())
    return registry


def _empty_stage_config(config):
    if config:
        raise ValueError('This workflow stage does not accept configuration')
    return {}


def _blast_dependency(config):
    try:
        binaries = local_comparison.tools()
    except Exception as error:
        return {
            'status': 'dependency_missing',
            'dependencies': [{'tool': 'BLAST+', 'status': 'missing', 'reason': str(error)}],
        }
    return {
        'status': 'available',
        'dependencies': [
            {'tool': name, 'status': 'available', **value}
            for name, value in sorted(binaries.items())
        ],
    }


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
        if (isinstance(value, dict) and set(value) == {'path', 'artifact_type'}
                and isinstance(value['path'], str) and value['path']
                and artifact_contracts.known_contract(value['artifact_type'])):
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
    stages=spec.get('stages',[]);seen=set();portable_seen=set();seen_stages={}
    if spec.get('schema')!='artifact-workflow-v1' or not isinstance(stages,list) or not stages or len(stages)>30:raise ValueError('Provide schema artifact-workflow-v1 and 1..30 stages')
    for stage in stages:
        if not isinstance(stage,dict) or not isinstance(stage.get('inputs'),dict):raise ValueError('Every stage and inputs must be objects')
        sid=stage.get('id','');kind=stage.get('kind')
        if not portable_name(sid) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}',sid) or sid.casefold() in portable_seen:raise ValueError('Invalid/duplicate portable stage ID')
        if not isinstance(kind,str):
            raise ValueError('Unknown workflow stage')
        definition=registry.get(kind)
        contract_definition=definition
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
                contract_definition=module
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
            normalized_config=registry.validate_config(kind,stage.get('config',{}))
            if kind=='catalogue_observations' and set(stage['inputs'])!=set(normalized_config['samples']):
                raise ValueError('Catalogue inputs and declared sample metadata keys must match exactly')
            if kind=='workflow_report' and not stage['inputs']:
                raise ValueError('Consolidated report requires at least one declared upstream artifact')
        contracts=contract_definition.input_contracts or {}
        for input_name,value in stage['inputs'].items():
            expected=contracts.get(input_name,contracts.get('*',()))
            if isinstance(value,dict) and set(value)=={'path','artifact_type'}:
                if expected and value['artifact_type'] not in expected:
                    raise ValueError(
                        f'Input {input_name!r} declares {value["artifact_type"]}, '
                        f'but {kind!r} accepts only {list(expected)}'
                    )
            elif isinstance(value,dict) and set(value)=={'stage','artifact'} and expected:
                producer=seen_stages[value['stage']]
                producer_definition=registry.get(producer['kind'])
                if producer['kind']=='external_module':
                    producer_definition=registry.get_module(producer['module']) or producer_definition
                produced=_output_contract(producer_definition,value['artifact'])
                if not produced:
                    raise ValueError(
                        f'Stage {producer["id"]!r} does not declare a contract for {value["artifact"]!r}'
                    )
                if produced[0] not in expected:
                    raise ValueError(
                        f'Incompatible artifact handoff: {producer["id"]}.{value["artifact"]} '
                        f'is {produced[0]}, but {sid}.{input_name} accepts {list(expected)}'
                    )
                if producer.get('skip') is True:
                    raise ValueError('A downstream stage cannot consume output from a skipped stage')
        seen.add(sid)
        portable_seen.add(sid.casefold())
        seen_stages[sid]=stage
    return stages


def _input_contracts(definition, name):
    contracts=definition.input_contracts or {}
    return contracts.get(name,contracts.get('*',()))


def _producer_definition(stage,registry):
    definition=registry.get(stage['kind'])
    if stage['kind']=='external_module':
        definition=registry.get_module(stage['module']) or definition
    return definition


def _output_contract(definition, artifact_name):
    """Return the declared contract for one exact or safely suffixed output."""
    contracts=definition.output_contracts or {}
    if artifact_name in contracts:
        return contracts[artifact_name]
    for pattern,contract in contracts.items():
        if pattern.startswith('*') and artifact_name.endswith(pattern[1:]):
            return contract
    return ()


def _dependency_report(definition,kind,config):
    if definition.external_tool:
        inspector=getattr(definition.handler,'inspect_dependency_for_config',None)
        return (inspector(config) if callable(inspector)
                else definition.handler.inspect_dependency())
    if definition.dependency_inspector is not None:
        return definition.dependency_inspector(config)
    return None


def _resolve_stage_input(manifest,output,result,stage,definition,key,value,registry):
    expected=_input_contracts(definition,key)
    producer_id=producer_artifact=None
    if isinstance(value,str):
        raw_path=manifest.parent/value
        explicit_type=None
        source={'declared_path':value}
    elif set(value)=={'path','artifact_type'}:
        raw_path=manifest.parent/value['path']
        explicit_type=value['artifact_type']
        source={'declared_path':value['path']}
    else:
        producer_id=value['stage']
        producer_artifact=value['artifact']
        producer=next((row for row in result['stages'] if row['id']==producer_id),None)
        if producer is None or producer.get('status')!='complete' or not producer.get('output_path'):
            raise ValueError('Requested upstream stage has not completed successfully')
        base=(output/producer['output_path']).resolve()
        prior_path=base/'manifest.json'
        prior=json.loads(prior_path.read_text(encoding='utf-8'))
        digests=prior.get('output_sha256',{})
        if prior.get('status')!='complete' or producer_artifact not in digests:
            raise ValueError('Requested artifact is not a verified completed-stage output')
        raw_path=base/producer_artifact
        producer_definition=_producer_definition(
            next(item for item in result['stages'] if item['id']==producer_id),registry
        )
        produced=_output_contract(producer_definition,producer_artifact)
        explicit_type=produced[0] if produced else None
        source={'stage':producer_id,'artifact':producer_artifact}
        if expected and explicit_type not in expected:
            raise ValueError('Upstream artifact contract is incompatible with this stage input')

    if raw_path.is_symlink():
        raise ValueError('Workflow inputs must not be symbolic links')
    path=raw_path.resolve(strict=True)
    if producer_id is not None:
        base=(output/next(row for row in result['stages'] if row['id']==producer_id)['output_path']).resolve()
        if not path.is_relative_to(base):
            raise ValueError('Workflow artifact redirects outside its completed stage folder')
        producer=next(row for row in result['stages'] if row['id']==producer_id)
        prior=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
        digest=prior.get('output_sha256',{}).get(producer_artifact)
        if not digest or checksum(path)!=digest:
            raise ValueError('Workflow artifact failed integrity check')
        old_descriptor=producer.get('artifacts',{}).get(producer_artifact)
        if old_descriptor and explicit_type:
            artifact_contracts.verify_descriptor(path,old_descriptor,explicit_type)
    else:
        explicit_type=explicit_type or (expected[0] if expected else None)

    descriptor=None
    if explicit_type:
        if expected and explicit_type not in expected:
            raise ValueError('Declared input artifact contract is incompatible with this stage')
        descriptor=artifact_contracts.describe_artifact(
            path,explicit_type,producer_stage=producer_id,
            input_provenance=source,
        )
    return path,descriptor


def _stage_cache_key(stage,definition,config,input_descriptors,runtime,dependency):
    identity={
        'stage_id':stage['id'],
        'kind':stage['kind'],
        'stage_version':definition.version,
        'config':config,
        'inputs':{
            name:{'sha256':row['sha256'],'artifact_type':row.get('artifact_type')}
            for name,row in sorted(input_descriptors.items())
        },
        'package_sha256':runtime.get('source_sha256'),
        'dependency':dependency,
    }
    return hashlib.sha256(
        json.dumps(identity,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    ).hexdigest()


def _stage_output_directory(output,stage_id,cache_key,previous_rows):
    prior=previous_rows.get(stage_id,{})
    if prior.get('cache_key')==cache_key and isinstance(prior.get('output_path'),str):
        candidate=(output/prior['output_path']).resolve()
        if candidate.is_relative_to(output) and candidate.exists():
            return candidate
    legacy=(output/stage_id).resolve()
    if not legacy.exists():
        return legacy
    if not any(legacy.iterdir()):
        return legacy
    return (output/'.stage-runs'/stage_id/cache_key).resolve()


def _verified_previous_stage(output, stage, definition, prior):
    """Return verified previous outputs only when the stage manifest is intact."""
    if (prior.get('status') != 'complete' or prior.get('kind') != stage['kind']
            or not isinstance(prior.get('output_path'), str)):
        return None
    base=(output/prior['output_path']).resolve()
    if not base.is_relative_to(output) or not base.is_dir():
        return None
    marker=base/'manifest.json'
    try:
        if (not marker.is_file() or marker.is_symlink()
                or (prior.get('stage_manifest_sha256')
                    and checksum(marker) != prior['stage_manifest_sha256'])):
            return None
        _manifest, artifacts, _files = _verify_stage_outputs(base,stage,definition,output)
    except (OSError,ValueError,KeyError,TypeError):
        return None
    return base, artifacts


def inspect_configuration(manifest,registry=None,output=None):
    """Read-only preflight: paths and stage requirements, without running stages."""
    registry = registry or DEFAULT_STAGE_REGISTRY
    manifest=Path(manifest).resolve(strict=True)
    if manifest.stat().st_size>1_000_000:raise ValueError('Workflow specification exceeds 1 MB')
    stages=validate(json.loads(manifest.read_text(encoding='utf-8')),registry)
    rows=[]
    output_path=Path(output).resolve() if output is not None else None
    previous_rows={}
    previous_path=output_path/'workflow.json' if output_path is not None else None
    if previous_path is not None and previous_path.is_file():
        previous=json.loads(previous_path.read_text(encoding='utf-8'))
        if isinstance(previous,dict) and isinstance(previous.get('stages'),list):
            previous_rows={row.get('id'):row for row in previous['stages'] if isinstance(row,dict)}
    runtime=reproducibility.environment()
    planned={}
    reusable_artifacts={}
    missing_dependencies=[]
    for stage in stages:
        definition=_producer_definition(stage,registry)
        config=registry.validate_config(definition.kind,stage.get('config',{}))
        inputs={}
        input_descriptors={}
        has_missing_input=False
        waits_for_upstream=False
        for key,value in stage['inputs'].items():
            expected=_input_contracts(definition,key)
            if isinstance(value,str):
                raw=manifest.parent/value
                artifact_type=expected[0] if expected else None
            elif set(value)=={'path','artifact_type'}:
                raw=manifest.parent/value['path']
                artifact_type=value['artifact_type']
            else:
                producer=next(item for item in stages if item['id']==value['stage'])
                producer_definition=_producer_definition(producer,registry)
                produced=_output_contract(producer_definition,value['artifact'])
                artifact_type=produced[0] if produced else None
                producer_plan=planned.get(value['stage'],{})
                prior_artifact=reusable_artifacts.get((value['stage'],value['artifact']))
                if producer_plan.get('expected_action')=='reuse_verified' and prior_artifact:
                    path,descriptor=prior_artifact
                    inputs[key]={
                        'status':'available_from_verified_reuse',
                        'path':str(path),
                        'sha256':descriptor['sha256'],
                        'artifact_type':artifact_type,
                        **value,
                        'validation_state':'valid',
                    }
                    input_descriptors[key]=descriptor
                else:
                    waits_for_upstream=True
                    inputs[key]={
                        'status':'produced_by_earlier_stage',
                        'artifact_type':artifact_type,
                        **value,
                    }
                continue

            if raw.is_symlink():
                has_missing_input=True
                inputs[key]={
                    'path':str(raw),
                    'status':'invalid',
                    'artifact_type':artifact_type,
                    'validation_error':'Workflow inputs must not be symbolic links',
                }
                continue
            path=raw.resolve()
            inputs[key]={
                'path':str(path),
                'status':'available' if path.is_file() else 'missing',
                'artifact_type':artifact_type,
                'accepted_contracts':list(expected),
            }
            if not path.is_file():
                has_missing_input=True
                continue
            try:
                if artifact_type:
                    descriptor=artifact_contracts.describe_artifact(path,artifact_type)
                    inputs[key]['contract_validation']=descriptor['metadata']
                    inputs[key]['validation_state']='valid'
                else:
                    if path.stat().st_size<=0:
                        raise ValueError('Workflow input must be a non-empty regular file')
                    descriptor={'sha256':checksum(path),'artifact_type':None}
                    inputs[key]['validation_state']='not_typed'
                inputs[key]['sha256']=checksum(path)
                input_descriptors[key]=descriptor
            except (OSError,ValueError,KeyError,TypeError) as error:
                has_missing_input=True
                inputs[key]['validation_state']='invalid'
                inputs[key]['validation_error']=str(error)

        row={
            'id':stage['id'],
            'kind':stage['kind'],
            'inputs':inputs,
            'input_contracts':{
                name:list(_input_contracts(definition,name))
                for name in sorted(stage['inputs'])
            },
            'output_contracts':dict(sorted((definition.output_contracts or {}).items())),
        }
        if stage.get('skip') is True:
            row['expected_action']='skipped'
        if stage['kind']=='external_module':
            row.update(
                module=stage['module'],
                module_status=('registered' if registry.has_module(stage['module'])
                               else 'external_module_required'),
            )
        dependency=_dependency_report(definition,stage['kind'],config)
        if dependency is not None:
            row['dependencies']=dependency
            if dependency.get('status')!='available':
                missing_dependencies.append({'stage':stage['id'],'dependency_report':dependency})

        previous=previous_rows.get(stage['id'],{})
        cache_key=None
        if (stage.get('skip') is not True and not has_missing_input
                and not waits_for_upstream
                and (dependency is None or dependency.get('status')=='available')):
            cache_key=_stage_cache_key(
                stage,definition,config,input_descriptors,runtime,dependency)
            row['cache_key']=cache_key
        if 'expected_action' not in row:
            if has_missing_input:
                row['expected_action']='blocked_input'
            elif dependency is not None and dependency.get('status')!='available':
                row['expected_action']='blocked_dependency'
            elif waits_for_upstream:
                row['expected_action']='execute_after_upstream'
            elif (cache_key and output_path is not None
                  and previous.get('cache_key')==cache_key):
                reusable=_verified_previous_stage(
                    output_path,stage,definition,previous)
                if reusable is not None:
                    prior_dir,artifacts=reusable
                    row['expected_action']='reuse_verified'
                    for artifact_name,descriptor in artifacts.items():
                        reusable_artifacts[(stage['id'],artifact_name)]=(
                            prior_dir/artifact_name,descriptor)
                else:
                    row['expected_action']='execute'
            else:
                row['expected_action']='execute'
        row['configuration_validated']=True
        planned[stage['id']]=row
        rows.append(row)
    return {'schema':'artifact-preflight-v1','specification':str(manifest),'sha256':checksum(manifest),
            'stages':rows,'registry':registry.describe(),
            'output':str(output_path) if output_path else None,
            'missing_dependencies':missing_dependencies,
            'execution_started':False,
            'note':'Read-only configuration, path, contract and dependency inspection. No stage was executed.'}


def write_status(output, result):
    """Write a useful report even when a stage cannot start or is interrupted."""
    result['final_report_paths']=['report.html','workflow.json','reproducibility.json']
    result['stage_statuses']={}
    result['input_artifacts']={}
    result['output_artifacts']={}
    for stage in result['stages']:
        result['stage_statuses'][stage['id']]=stage.get('status')
        for name,details in stage.get('inputs',{}).items():
            result['input_artifacts'][stage['id']+'.'+name]=details
        for name,descriptor in stage.get('artifacts',{}).items():
            result['output_artifacts'][stage['id']+'.'+name]=descriptor
        output_path=stage.get('output_path')
        if not output_path or stage.get('status')!='complete':
            continue
        for name in ('report.html','report.json'):
            if name in stage.get('output_files',{}):
                result['final_report_paths'].append(
                    (Path(output_path)/name).as_posix())
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
    body += '<p>Descriptive supplied-artifact stages only. No autonomous biological discovery.</p>'
    body += '<h2>Workflow provenance</h2><ul>'
    for label, value in (
        ('Workflow ID',result.get('workflow_id')),
        ('Workflow version',result.get('workflow_version')),
        ('Git revision',result.get('git_revision')),
        ('Configuration SHA256',result.get('configuration_sha256')),
        ('Started',result.get('started_utc')),
        ('Finished',result.get('finished_utc')),
        ('Reference snapshot IDs',', '.join(result.get('reference_snapshot_ids',[]))),
    ):
        if value is not None:
            body += '<li>' + html.escape(label+': '+str(value)) + '</li>'
    body += '</ul><h2>Stages, inputs and outputs</h2><ul>'
    if result.get('environment'):
        body += '<details><summary>Environment and runtime</summary><pre>' + html.escape(
            json.dumps(result['environment'], indent=2, sort_keys=True)
        ) + '</pre></details>'
    dependency_versions = result.get('dependency_versions', {})
    if dependency_versions:
        body += '<h2>Dependencies by stage</h2><ul>'
        for stage_id, dependency in sorted(dependency_versions.items()):
            body += '<li>' + html.escape(stage_id) + '<pre>' + html.escape(
                json.dumps(dependency, indent=2, sort_keys=True)
            ) + '</pre></li>'
        body += '</ul>'
    for stage in result['stages']:
        label = html.escape(stage['id'] + ': ' + labels.get(stage['status'],stage['status']))
        stage_output=stage.get('output_path',stage['id'])
        if stage['status'] == 'complete' and (output/stage_output/'report.html').is_file():
            label = '<a href="' + html.escape(stage_output) + '/report.html">' + label + '</a>'
        body += '<li>' + label
        if stage.get('execution'):
            body += '<p>Execution/reuse: ' + html.escape(str(stage['execution'])) + '</p>'
        if stage.get('required_module'):
            body += '<p>Required trusted module: ' + html.escape(stage['required_module']) + '</p>'
        if stage.get('reason'):
            body += '<p>' + html.escape(stage['reason']) + '</p>'
        if stage.get('cache_key'):
            body += '<p>Cache key: <code>' + html.escape(stage['cache_key']) + '</code></p>'
        if stage.get('output_path'):
            body += '<p>Output: <code>' + html.escape(stage['output_path']) + '</code></p>'
        if stage.get('comparison_result'):
            body += '<p>Comparison result: ' + html.escape(stage['comparison_result']) + '</p>'
        if stage.get('inputs'):
            body += '<h3>Declared inputs</h3><ul>'
            for name, details in sorted(stage['inputs'].items()):
                label_text=name
                if details.get('artifact_type'):
                    label_text+=' ['+str(details['artifact_type'])+']'
                if details.get('path'):
                    label_text+=' — '+str(details['path'])
                if details.get('sha256'):
                    label_text+=' — SHA256 '+str(details['sha256'])
                if details.get('validation_state'):
                    label_text+=' — '+str(details['validation_state'])
                body += '<li>' + html.escape(label_text) + '</li>'
            body += '</ul>'
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
            blocker=next((row for row in result['stages']
                          if row.get('status') in {
                              'dependency_missing','external_module_required',
                              'failed','interrupted',
                          }),None)
            if blocker:
                body += '<p>Not executed because upstream stage ' + html.escape(
                    blocker['id']+' ended with status '+blocker['status']) + '.</p>'
            else:
                body += '<p>Not started because an earlier stage did not finish.</p>'
        if stage.get('dependency_report'):
            for dependency in stage['dependency_report'].get('dependencies',[]):
                text=f"Executable {dependency.get('tool','unknown')}: {dependency.get('status','unknown')}"
                if dependency.get('path'):text+=' ('+dependency['path']+')'
                body += '<p>' + html.escape(text) + '</p>'
        if stage.get('warnings'):
            for warning in stage['warnings']:
                body += '<p>Warning: ' + html.escape(str(warning)) + '</p>'
        if stage.get('output_files'):
            summary_name = (
                'assembly_manifest.json' if stage.get('kind') == 'assembly'
                else 'report.json' if stage.get('kind') == 'workflow_report'
                else 'summary.json'
            )
            summary_record = stage['output_files'].get(summary_name)
            summary_path = output/stage_output/summary_name
            if (stage.get('status') == 'complete' and summary_record
                    and summary_path.is_file() and summary_path.stat().st_size <= 32_000_000
                    and checksum(summary_path) == summary_record.get('sha256')):
                try:
                    summary_value = json.loads(summary_path.read_text(encoding='utf-8'))

                    def concise(value):
                        if isinstance(value, dict):
                            return {key: concise(item) for key, item in sorted(value.items())}
                        if isinstance(value, list):
                            return {
                                'record_count': len(value),
                                'examples': [concise(item) for item in value[:3]],
                            }
                        return value

                    summary_text = json.dumps(concise(summary_value), indent=2, sort_keys=True)
                    if len(summary_text) > 12_000:
                        summary_text = summary_text[:12_000] + '\n… summary truncated; see linked stage report.'
                    body += '<details><summary>Verified structured summary</summary><pre>' + html.escape(
                        summary_text
                    ) + '</pre></details>'
                except (OSError, UnicodeError, ValueError, TypeError):
                    body += '<p>Structured summary could not be displayed; inspect the linked stage report.</p>'
            body += '<ul>'
            for name, details in sorted(stage['output_files'].items()):
                body += '<li>' + html.escape(name) + ' — SHA256 <code>' + html.escape(
                    str(details.get('sha256',''))) + '</code></li>'
            body += '</ul>'
        if 'error' in stage:
            body += '<pre>' + html.escape(stage['error']) + '</pre>'
        body += '</li>'
    if 'error' in result:
        body += '<li>' + html.escape(result['error']) + '</li>'
    if result.get('failure'):
        failure=result['failure']
        body += '<li>Failure: ' + html.escape(str(
            failure.get('reason') or failure.get('error') or failure)) + '</li>'
    body += '</ul><h2>Final reports and machine-readable outputs</h2><ul>'
    for name in result['final_report_paths']:
        body += '<li><a href="' + html.escape(name) + '">' + html.escape(name) + '</a></li>'
    body += '</ul><p><a href="reproducibility.json">Reproducibility manifest</a></p>'
    temporary = output/'report.html.tmp'
    temporary.write_text(body, encoding='utf-8')
    temporary.replace(output/'report.html')
    result['report_sha256'] = checksum(output/'report.html')
    result['final_artifacts'] = {
        'report.html': artifact_contracts.describe_artifact(
            output/'report.html','report',display_path='report.html'
        ),
    }
    write_json(output/'workflow.json', result)


def _preflight_direct_inputs(manifest,stages,registry):
    """Validate declared external files before creating workflow outputs."""
    for stage in stages:
        if stage.get('skip') is True:
            continue
        definition=_producer_definition(stage,registry)
        if stage['kind']=='external_module' and not registry.has_module(stage['module']):
            continue
        config=registry.validate_config(definition.kind,stage.get('config',{}))
        paths={}
        for key,value in stage['inputs'].items():
            if isinstance(value,str):
                raw=manifest.parent/value
                explicit_type=None
            elif isinstance(value,dict) and set(value)=={'path','artifact_type'}:
                raw=manifest.parent/value['path']
                explicit_type=value['artifact_type']
            else:
                continue
            if raw.is_symlink():
                raise ValueError(f'Workflow input {key!r} must not be a symbolic link')
            path=raw.resolve(strict=True)
            expected=_input_contracts(definition,key)
            artifact_type=explicit_type or (expected[0] if expected else None)
            if artifact_type:
                if expected and artifact_type not in expected:
                    raise ValueError(f'Workflow input {key!r} declares an incompatible artifact type')
                artifact_contracts.describe_artifact(path,artifact_type)
            elif not path.is_file() or path.stat().st_size <= 0:
                raise ValueError(f'Workflow input {key!r} must be a non-empty regular file')
            paths[key]=path

        if definition.kind=='fastq_validate' and set(paths)==set(stage['inputs']):
            if (config['layout']=='paired-end') != ('read2' in paths):
                raise ValueError('Declared FASTQ layout does not match supplied read mates')
            with tempfile.TemporaryDirectory(prefix='artifact-fastq-preflight-') as folder:
                from .assembly_adapters import _validate_fastq_inputs
                _validate_fastq_inputs(paths,Path(folder))
        elif definition.kind=='assembly' and set(paths)==set(stage['inputs']):
            with tempfile.TemporaryDirectory(prefix='artifact-assembly-preflight-') as folder:
                from .assembly_adapters import _validate_fastq_inputs
                _validate_fastq_inputs(paths,Path(folder))


def _verify_stage_outputs(stage_output,stage,definition,output):
    marker=stage_output/'manifest.json'
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Completed workflow stage must write a regular manifest.json')
    stage_manifest=json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(stage_manifest,dict) or stage_manifest.get('status')!='complete':
        raise ValueError('Workflow stage manifest does not report complete status')
    digests=stage_manifest.get('output_sha256')
    if not isinstance(digests,dict) or not digests:
        raise ValueError('Completed workflow stage has no checksummed output inventory')
    artifacts={}
    output_files={}
    for name,digest in sorted(digests.items()):
        parts=name.split('/') if isinstance(name,str) else []
        if (not parts or '\\' in name or any(not portable_name(part) for part in parts)
                or name.casefold()=='manifest.json'):
            raise ValueError('Workflow stage manifest contains an unsafe output name')
        path=stage_output.joinpath(*parts)
        if any(parent.is_symlink() for parent in (path,*path.parents) if parent!=stage_output.parent):
            raise ValueError('Workflow stage output path contains a symbolic link')
        try:
            resolved=path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f'Workflow stage output is missing: {name}') from error
        if (not resolved.is_relative_to(stage_output) or path.is_symlink()
                or not path.is_file() or checksum(path)!=digest):
            raise ValueError(f'Workflow stage output failed integrity verification: {name}')
        output_files[name]={'sha256':digest,'size_bytes':path.stat().st_size}
        declared=_output_contract(definition,name)
        if declared:
            artifacts[name]=artifact_contracts.describe_artifact(
                path,declared[0],
                display_path=path.relative_to(output).as_posix(),
                producer_stage=stage['id'],
                input_provenance={
                    input_name: input_value
                    for input_name,input_value in stage['inputs'].items()
                },
            )
    return stage_manifest,artifacts,output_files


def run(manifest,output,registry=None):
    registry=registry or DEFAULT_STAGE_REGISTRY
    manifest=Path(manifest).resolve(strict=True)
    output=Path(output).resolve()
    if manifest.is_relative_to(output):
        raise ValueError('Keep workflow specification outside output folder')
    if manifest.stat().st_size>1_000_000:
        raise ValueError('Workflow specification exceeds 1 MB')
    specification=json.loads(manifest.read_text(encoding='utf-8'))
    digest=checksum(manifest)
    stages=validate(specification,registry)

    output.mkdir(parents=True,exist_ok=True)
    lock=output/'.workflow.lock'
    lock_token=stage_lock.acquire(lock)
    marker=output/'workflow.json'
    result=None
    active=None
    try:
        runtime=reproducibility.environment()
        identity={
            'specification_sha256':digest,
            'engine_sha256':checksum(__file__),
            'package_sha256':runtime['source_sha256'],
            'portable_paths_sha256':checksum(Path(__file__).with_name('portable_paths.py')),
        }
        previous={}
        if marker.is_symlink():
            raise ValueError('Existing workflow.json must not be a symbolic link')
        if marker.exists():
            previous=json.loads(marker.read_text(encoding='utf-8'))
            if not isinstance(previous,dict) or not isinstance(previous.get('stages'),list):
                raise ValueError('Workflow manifest is malformed; existing files preserved')
            previous_digest=previous.get('configuration_sha256')
            if (previous_digest != digest
                    and previous.get('configuration') == specification):
                raise ValueError(
                    'Workflow specification bytes changed without a configuration change'
                )
        elif any(path!=lock for path in output.iterdir()):
            raise ValueError('Nonempty output has no workflow manifest')
        previous_rows={
            row.get('id'):row for row in previous.get('stages',[])
            if isinstance(row,dict) and isinstance(row.get('id'),str)
        }
        stage_rows=[]
        graph=[]
        for item in stages:
            row={'id':item['id'],'kind':item['kind'],'status':'pending'}
            if item['kind']=='external_module':
                row['module']=item['module']
            stage_rows.append(row)
            for name,value in item['inputs'].items():
                if isinstance(value,dict) and set(value)=={'stage','artifact'}:
                    producer=next(stage for stage in stages if stage['id']==value['stage'])
                    produced=_output_contract(
                        _producer_definition(producer,registry),value['artifact'])
                    graph.append({
                        'from_stage':value['stage'],
                        'artifact':value['artifact'],
                        'artifact_type':produced[0] if produced else None,
                        'to_stage':item['id'],
                        'input':name,
                    })
        result={
            'schema':'artifact-workflow-manifest-v2',
            'workflow_id':previous.get('workflow_id') or uuid.uuid4().hex,
            'workflow_version':'2',
            'git_revision':runtime.get('git_revision'),
            'configuration_sha256':digest,
            'identity':identity,
            'specification_sha256':digest,
            'environment':runtime,
            'registry':registry.describe(),
            'configuration':specification,
            'status':'pending',
            'stage_graph':graph,
            'stage_order':[stage['id'] for stage in stages],
            'dependency_versions':{},
            'reference_snapshot_ids':[],
            'warnings':[],
            'stages':stage_rows,
        }
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
                    result['failure']={
                        'stage_id':stage['id'],
                        'status':'external_module_required',
                        'reason':reason,
                    }
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
            if module_name:
                active['registered_module']=module_name
            if stage['kind']=='assembly':
                active['assembler']=config['assembler']

            inputs={}
            input_descriptors={}
            for key,value in stage['inputs'].items():
                path,descriptor=_resolve_stage_input(
                    manifest,output,result,stage,definition,key,value,registry)
                inputs[key]=path
                item={
                    'path':str(path),
                    'sha256':checksum(path),
                    'bytes':path.stat().st_size,
                }
                if descriptor:
                    item['artifact_type']=descriptor['artifact_type']
                    item['validation_state']=descriptor['validation_state']
                    item['descriptor']=descriptor
                    input_descriptors[key]=descriptor
                else:
                    input_descriptors[key]={
                        'sha256':item['sha256'],
                        'artifact_type':None,
                    }
                active.setdefault('inputs',{})[key]=item

            if definition.kind=='fastq_validate':
                if (config['layout']=='paired-end') != ('read2' in inputs):
                    raise ValueError('Declared FASTQ layout does not match supplied read mates')
                with tempfile.TemporaryDirectory(prefix='artifact-fastq-preflight-') as folder:
                    from .assembly_adapters import _validate_fastq_inputs
                    _validate_fastq_inputs(inputs,Path(folder))
            elif definition.kind=='assembly':
                with tempfile.TemporaryDirectory(prefix='artifact-assembly-preflight-') as folder:
                    from .assembly_adapters import _validate_fastq_inputs
                    _validate_fastq_inputs(inputs,Path(folder))

            dependency=_dependency_report(definition,stage['kind'],config)
            if dependency is not None:
                active['dependency_report']=dependency
                result['dependency_versions'][stage['id']]=dependency
                if dependency.get('status')!='available':
                    reason='One or more required external executables are unavailable.'
                    result['failure']={
                        'stage_id':stage['id'],
                        'status':'dependency_missing',
                        'reason':reason,
                    }
                    if stage['kind']=='blast_compare':
                        active['comparison_result']=(
                            'not executed because the required comparison dependency is missing; '
                            'no comparison result was produced')
                    transition(active,'dependency_missing',STAGE_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    transition(result,'dependency_missing',WORKFLOW_TRANSITIONS,
                               reason=reason,finished_utc=datetime.now(timezone.utc).isoformat())
                    write_status(output,result)
                    active=None
                    return output/'report.html'

            cache_key=_stage_cache_key(stage,definition,config,input_descriptors,runtime,dependency)
            stage_output=_stage_output_directory(output,stage['id'],cache_key,previous_rows)
            if not stage_output.is_relative_to(output):
                raise ValueError('Stage output redirects outside the workflow folder')
            active['cache_key']=cache_key
            active['output_path']=stage_output.relative_to(output).as_posix()
            write_status(output,result)
            stage_marker=stage_output/'manifest.json'
            before=checksum(stage_marker) if stage_marker.is_file() else None
            try:
                if definition.external_tool:
                    if stage['kind']=='assembly':
                        outcome=definition.handler.execute(
                            inputs,stage_output,config,context={'stage_id':stage['id']})
                    else:
                        outcome=definition.handler.execute(inputs,stage_output,config)
                else:
                    outcome=definition.handler(inputs,stage_output,config)
            except DependencyMissingError as error:
                reason=str(error)
                result['failure']={
                    'stage_id':stage['id'],
                    'status':'dependency_missing',
                    'reason':reason,
                }
                if stage['kind']=='blast_compare':
                    active['comparison_result']=(
                        'not executed because the required comparison dependency is missing; '
                        'no comparison result was produced')
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
                if stage['kind']=='assembly':
                    assembly_record=json.loads(
                        (stage_output/'assembly_manifest.json').read_text(encoding='utf-8'))
                    active['assembly']={
                        'assembler':assembly_record['assembler'],
                        'tool_version':assembly_record['external_tool_version'],
                        'input_layout':assembly_record['input_layout'],
                        'runtime_seconds':assembly_record['duration_seconds'],
                        'contig_count':assembly_record['contig_count'],
                        'contig_path':assembly_record['contig_output'],
                        'dependency_status':'available',
                        'reuse_status':outcome.execution,
                        'warnings':assembly_record.get('warnings',[]),
                    }
                    active['warnings']=assembly_record.get('warnings',[])
                    result['warnings'].extend(
                        f"{stage['id']}: {warning}" for warning in assembly_record.get('warnings',[]))
            else:
                active['execution']=(
                    'verified_reuse'
                    if before is not None and stage_marker.is_file() and checksum(stage_marker)==before
                    else 'executed'
                )

            stage_manifest,artifacts,output_files=_verify_stage_outputs(
                stage_output,stage,definition,output)
            active['artifacts']=artifacts
            active['output_files']=output_files
            active['stage_manifest_sha256']=checksum(stage_marker)
            active['stage_manifest_identity']=stage_manifest.get('identity')
            if stage['kind']=='reference_snapshot':
                source=reproducibility.bounded_json(inputs['manifest'],inputs['manifest'].parent)
                fields=('name','bytes','sha256','source','version','role','accession','database_version',
                        'reference_id','display_name','category','provenance','update_status')
                active['reference_specification']=[
                    {key:row[key] for key in fields if key in row} for row in source['files']]
            if stage['kind']=='reference_record_import':
                snapshot=json.loads((stage_output/'snapshot.json').read_text(encoding='utf-8'))
                snapshot_id=snapshot.get('snapshot_id')
                if isinstance(snapshot_id,str) and snapshot_id not in result['reference_snapshot_ids']:
                    result['reference_snapshot_ids'].append(snapshot_id)
            if stage['kind']=='blast_compare':
                comparison=json.loads((stage_output/'summary.json').read_text(encoding='utf-8'))
                matches=comparison.get('tables',{}).get('matches',[])
                if not matches:
                    active['comparison_result']='no match found under the configured comparison'
            transition(active,'complete',STAGE_TRANSITIONS,
                       finished_utc=datetime.now(timezone.utc).isoformat())
            write_status(output,result)
            active=None

        if checksum(manifest)!=digest:
            raise ValueError('Workflow specification changed during execution')
        final_status=aggregate_stage_status(result['stages'])
        transition(result,final_status,WORKFLOW_TRANSITIONS,
                   finished_utc=datetime.now(timezone.utc).isoformat())
        write_status(output,result)
        return output/'report.html'
    except BaseException as exc:
        if result is not None:
            status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed'
            failure={
                'error':str(exc) or type(exc).__name__,
                'error_type':type(exc).__name__,
                'finished_utc':datetime.now(timezone.utc).isoformat(),
            }
            result['failure']={
                'stage_id':active.get('id') if active is not None else None,
                'status':status,
                **failure,
            }
            if active is not None and active.get('status')=='running':
                transition(active,status,STAGE_TRANSITIONS,**failure)
            if result.get('status')=='running':
                transition(result,status,WORKFLOW_TRANSITIONS,**failure)
            write_status(output,result)
        raise
    finally:
        stage_lock.release(lock,lock_token)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Run or preflight a validated artifact workflow.')
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--output')
    parser.add_argument('--preflight',action='store_true',
                        help='validate paths, contracts and dependencies without executing stages')
    args=parser.parse_args()
    if args.preflight:
        print(json.dumps(inspect_configuration(args.manifest,output=args.output),indent=2))
    else:
        if not args.output:
            parser.error('--output is required unless --preflight is selected')
        print(run(args.manifest,args.output))
