"""Resumable allowlisted workflow over existing artifacts; no discovery or shell steps."""
import argparse
from datetime import datetime,timezone
import html
import hashlib
from importlib import import_module
import json
from pathlib import Path
import re
import sys
import tempfile
import uuid
from .sequence_downloader import checksum,write_json
from .portable_paths import portable_name
from . import reproducibility
from . import stage_lock
from .external_tool import DependencyMissingError, ExternalToolExecution
from .example_transform_adapter import ExampleTextTransformAdapter
from .assembly_adapters import AssemblyWorkflowAdapter
from .virema_adapter import ViReMaDVGAdapter
from .residual_evidence_adapter import ResidualEvidenceAdapter
from . import (
    artifact_contracts, artifact_stage_handlers, dvg_evidence, execution_outcome,
    independent_recurrence, local_comparison, m8_homology,
    m9_blastp_stage, m9_orf_stage, m10_stage, m11_stage,
    m12_artifact_review, m13_contracts, m13_stage,
    m14_descriptive_observations,
    stage_cache_identity,
    # M15_CACHE_NEUTRAL_BEGIN
    m15_contracts, m15_stage,
    # M15_CACHE_NEUTRAL_END
)
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
    invoke._cache_source_modules = (f'{__package__}.{module_name}',)
    invoke._cache_source_descriptor = {
        'module': module_name,
        'function': function_name,
        'input_names': tuple(input_names),
        'alignment': bool(alignment),
    }
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
        'fastq_qc', ('read1',), artifact_stage_handlers.quality_control_fastq,
        optional_input_fields=('read2',), version='1',
        config_validator=artifact_stage_handlers.validate_qc_config,
        input_contracts={
            'read1': ('raw_read', 'validated_fastq'),
            'read2': ('raw_read', 'validated_fastq'),
        },
        output_contracts={
            'clean_single.fastq.gz': 'qc_fastq',
            'rejected.fastq.gz': 'qc_fastq',
            'clean_R1.fastq.gz': 'qc_fastq',
            'clean_R2.fastq.gz': 'qc_fastq',
            'orphan_R1.fastq.gz': 'qc_fastq',
            'orphan_R2.fastq.gz': 'qc_fastq',
            'qc.json': 'qc_manifest',
        },
        description='Runs the existing QC engine as a checksum-bound typed stage.',
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
        'independent_recurrence', None, independent_recurrence.run_stage,
        version=independent_recurrence.STAGE_VERSION, dynamic_inputs=True,
        config_validator=independent_recurrence.validate_config,
        input_contracts={
            '*': tuple(sorted(set(independent_recurrence.INPUT_TYPES.values()))),
        },
        output_contracts=independent_recurrence.OUTPUT_CONTRACTS,
        description=(
            'Compares exact sequences from independently supported M6 observations; '
            'does not pool reads or perform biological classification.'
        ),
    )
    registry.register(
        'm8_homology', None, m8_homology.run_stage,
        version=m8_homology.STAGE_VERSION, dynamic_inputs=True,
        config_validator=m8_homology.validate_config,
        dependency_inspector=m8_homology.inspect_dependency,
        input_contracts={
            '*': (
                'm8_candidate_sequence_set',
                'm8_reference_snapshot_manifest',
                'm8_reference_payload',
                'm7_observation_table', 'm7_exact_recurrence_table',
                'm7_independence_summary', 'm7_validation_report',
                'm7_provenance_manifest',
            ),
        },
        output_contracts={
            'query_status.json': 'm8_query_status',
            'matches.json': 'm8_match_evidence',
            'summary.json': 'm8_summary',
            'commands.json': 'm8_search_commands',
            '*.tsv': 'm8_raw_blast_output',
            '*.stdout.log': 'm8_raw_blast_output',
            '*.stderr.log': 'm8_raw_blast_output',
        },
        description=(
            'Compares checksum-bound M6 nucleotide candidates with one declared '
            'external M8 snapshot using the pinned BLASTN profile; records '
            'homology evidence without biological classification.'
        ),
    )
    registry.register(
        'm9_orf_translation', None, m9_orf_stage.run_stage,
        version=m9_orf_stage.STAGE_VERSION, dynamic_inputs=True,
        config_validator=m9_orf_stage.validate_config,
        input_contracts={
            '*': (
                'm8_candidate_sequence_set',
                'm7_observation_table', 'm7_exact_recurrence_table',
                'm7_independence_summary', 'm7_validation_report',
                'm7_provenance_manifest', 'm8_query_status',
                'm8_match_evidence', 'm8_summary', 'm8_search_commands',
                'm8_raw_blast_output',
            ),
        },
        output_contracts={
            'orf_results.json': 'm9_orf_results',
            'proteins.faa': 'm9_protein_fasta',
            'orf_bundle.json': 'm9_orf_bundle',
        },
        description=(
            'Enumerates deterministic six-frame table-1 ORF hypotheses from '
            'the checksum-bound M6 candidate handoff; preserves optional M7/M8 '
            'context without gating translation.'
        ),
    )
    registry.register(
        'm9_blastp', None, m9_blastp_stage.run_stage,
        version=m9_blastp_stage.STAGE_VERSION, dynamic_inputs=True,
        config_validator=m9_blastp_stage.validate_config,
        dependency_inspector=m9_blastp_stage.inspect_dependency,
        input_contracts={
            '*': tuple(m9_blastp_stage._INPUT_TYPES.values()),
        },
        output_contracts={
            'query_status.json': 'm9_protein_search_status',
            'matches.json': 'm9_protein_match_evidence',
            'summary.json': 'm9_protein_summary',
            'commands.json': 'm9_search_commands',
            'm9_bundle.json': 'm9_output_bundle',
            '*.tsv': 'm9_raw_blast_output',
            '*.log': 'm9_raw_blast_output',
        },
        description=(
            'Runs pinned local ordinary BLASTP against one explicitly supplied '
            'and checksum-validated protein snapshot; does not retrieve references.'
        ),
    )
    registry.register(
        'm10_exact_first', None, m10_stage.run_stage,
        version=m10_stage.STAGE_VERSION, dynamic_inputs=True,
        config_validator=m10_stage.validate_config,
        input_contracts={
            '*': tuple(sorted({
                'm8_candidate_sequence_set',
                'm7_observation_table', 'm7_exact_recurrence_table',
                'm7_independence_summary', 'm7_validation_report',
                'm7_provenance_manifest',
                'm8_query_status', 'm8_match_evidence', 'm8_summary',
                'm8_search_commands', 'm8_raw_blast_output',
                'm9_orf_results', 'm9_protein_fasta', 'm9_orf_bundle',
                'm9_protein_search_status', 'm9_protein_match_evidence',
                'm9_protein_summary', 'm9_search_commands',
                'm9_output_bundle', 'm9_raw_blast_output',
            })),
        },
        output_contracts=m10_stage._OUTPUT_TYPES,
        description=(
            'Runs the dependency-free exact M10 sequence-architecture baseline '
            'over the validated M6 candidate handoff and preserves optional '
            'M7–M9 context without biological classification.'
        ),
    )
    registry.register(
        'm11_rna_mfe', None, m11_stage.run_stage,
        version=m11_stage.STAGE_VERSION, dynamic_inputs=True,
        config_validator=m11_stage.validate_config,
        input_contracts={'*': ('m8_candidate_sequence_set',)},
        output_contracts=m11_stage._OUTPUT_TYPES,
        description=(
            'Optionally predicts one single-sequence ViennaRNA MFE structure '
            'from the immutable M6 candidate handoff; no biological search or '
            'classification is performed.'
        ),
    )
    m12_artifact_review.register_stage(registry)
    m13_stage.register_stage(registry)
    # M15_CACHE_NEUTRAL_BEGIN
    m15_stage.register_stage(registry)
    # M15_CACHE_NEUTRAL_END
    registry.register(
        m14_descriptive_observations.STAGE_KIND,
        None,
        m14_descriptive_observations.run_stage,
        version=m14_descriptive_observations.STAGE_VERSION,
        dynamic_inputs=True,
        config_validator=m14_descriptive_observations.validate_config,
        dependency_inspector=m14_descriptive_observations.inspect_dependency,
        output_contracts=m14_descriptive_observations.OUTPUT_CONTRACTS,
        description=(
            'Validates caller-authored candidate/helper observations and emits '
            'offline descriptive counts only.'
        ),
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
            'dvg_evidence', 'dvg_evidence_summary', 'dvg_parameters',
            'qc_manifest', 'residual_read_manifest', 'read_triage_table',
            'read_support_evidence', 'read_support_table',
            'reconstruction_evidence', 'm7_observation_table',
            'm7_exact_recurrence_table', 'm7_independence_summary',
            'm7_validation_report', 'm7_provenance_manifest',
            'm8_candidate_sequence_set', 'm8_reference_snapshot_manifest',
            'm8_raw_blast_output', 'm8_query_status', 'm8_match_evidence',
            'm8_summary', 'm8_search_commands',
             'm9_orf_results', 'm9_protein_fasta', 'm9_orf_bundle',
             'm9_protein_reference_manifest', 'm9_protein_reference_payload',
             'm9_protein_search_status', 'm9_protein_match_evidence',
             'm9_protein_summary', 'm9_search_commands', 'm9_output_bundle',
             'm9_raw_blast_output',
             'm14_observation_table', 'm14_descriptive_summary',
             'm14_result_bundle',
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
    registry.register_external_adapter(ViReMaDVGAdapter())
    registry.register_external_adapter(ResidualEvidenceAdapter())
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
        m7_input_types=None
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
            if kind=='independent_recurrence':
                m7_input_types=independent_recurrence.expected_input_types(normalized_config)
                if set(stage['inputs'])!=set(m7_input_types):
                    raise ValueError(
                        'M7 workflow inputs must match the declared M6 artifact roles exactly'
                    )
            if kind=='m8_homology':
                required_m8 = {
                    'candidate_sequence_set': 'm8_candidate_sequence_set',
                    'reference_snapshot_manifest': 'm8_reference_snapshot_manifest',
                }
                optional_m7 = {
                    'm7_observations': 'm7_observation_table',
                    'm7_recurrence': 'm7_exact_recurrence_table',
                    'm7_independence': 'm7_independence_summary',
                    'm7_validation': 'm7_validation_report',
                    'm7_provenance': 'm7_provenance_manifest',
                }
                payload_names = {
                    name for name in stage['inputs']
                    if name.startswith('reference_payload_')
                }
                if (
                    not set(required_m8) <= set(stage['inputs'])
                    or set(stage['inputs']) - set(required_m8)
                    - set(optional_m7) - payload_names
                ):
                    raise ValueError(
                        'M8 requires a typed candidate set, snapshot manifest, '
                        'all declared payload files and only supported optional M7 inputs'
                    )
                exact_types = {
                    **required_m8,
                    **{
                        name: expected_type for name, expected_type in optional_m7.items()
                        if name in stage['inputs']
                    },
                    **{name: 'm8_reference_payload' for name in payload_names},
                }
                for input_name, required_type in exact_types.items():
                    value = stage['inputs'][input_name]
                    if isinstance(value, str):
                        raise ValueError(
                            f'M8 input {input_name!r} must declare its exact artifact_type'
                        )
                    if isinstance(value, dict) and set(value) == {'path', 'artifact_type'}:
                        if value['artifact_type'] != required_type:
                            raise ValueError(
                                f'M8 input {input_name!r} must be {required_type!r}'
                            )
                    elif isinstance(value, dict) and set(value) == {'stage', 'artifact'}:
                        producer = seen_stages[value['stage']]
                        producer_definition = registry.get(producer['kind'])
                        if producer['kind'] == 'external_module':
                            producer_definition = (
                                registry.get_module(producer['module']) or producer_definition
                            )
                        produced = _output_contract(producer_definition, value['artifact'])
                        if required_type not in produced:
                            raise ValueError(
                                f'M8 input {input_name!r} requires {required_type!r}, '
                                f'not {list(produced)}'
                            )
                    else:
                        raise ValueError(f'M8 input {input_name!r} is not a typed input or stage handoff')
            if kind=='workflow_report' and not stage['inputs']:
                raise ValueError('Consolidated report requires at least one declared upstream artifact')
        contracts=contract_definition.input_contracts or {}
        for input_name,value in stage['inputs'].items():
            expected=contracts.get(input_name,contracts.get('*',()))
            if m7_input_types is not None:
                role_type=m7_input_types[input_name]
                if isinstance(value,str):
                    raise ValueError(
                        'M7 direct file inputs must declare their exact artifact_type'
                    )
                if (isinstance(value,dict) and set(value)=={'path','artifact_type'}
                        and value['artifact_type']!=role_type):
                    raise ValueError(
                        f'M7 input {input_name!r} must declare artifact_type {role_type!r}'
                    )
                if isinstance(value,dict) and set(value)=={'stage','artifact'}:
                    producer=seen_stages[value['stage']]
                    producer_definition=registry.get(producer['kind'])
                    if producer['kind']=='external_module':
                        producer_definition=registry.get_module(producer['module']) or producer_definition
                    produced=_output_contract(producer_definition,value['artifact'])
                    if role_type not in produced:
                        raise ValueError(
                            f'M7 input {input_name!r} requires {role_type!r}, '
                            f'not {list(produced)}'
                        )
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


WORKFLOW_CACHE_SEMANTICS_VERSION = '1'


def _cache_contract_mapping(contracts):
    normalized={}
    for name,value in sorted((contracts or {}).items()):
        if isinstance(value,(set,frozenset)):
            value=sorted(value)
        elif isinstance(value,(tuple,list)):
            value=list(value)
        normalized[name]=value
    return normalized


def _stage_cache_registration_identity(definition):
    """Describe one stage registration, not the complete workflow registry."""
    return {
        'kind':definition.kind,
        'version':definition.version,
        'input_fields':sorted(definition.input_fields or ()),
        'optional_input_fields':sorted(definition.optional_input_fields),
        'dynamic_inputs':definition.dynamic_inputs,
        'external_tool':definition.external_tool,
        'module_name':definition.module_name,
        'input_contracts':_cache_contract_mapping(definition.input_contracts),
        'output_contracts':_cache_contract_mapping(definition.output_contracts),
    }


def _legacy_package_cache_digest(runtime):
    # M15_CACHE_NEUTRAL_BEGIN
    runtime = m15_stage.legacy_compatible_runtime(runtime)
    # M15_CACHE_NEUTRAL_END
    current = runtime.get('source_sha256')
    if not isinstance(current, str):
        return current
    compatibility_file = Path(__file__).with_name(
        'm12_legacy_cache_compatibility.txt')
    try:
        values = {}
        for line in compatibility_file.read_text(encoding='utf-8').splitlines():
            if '=' not in line:
                continue
            name, value = line.split('=', 1)
            values[name] = value
    except OSError:
        return current
    if values.get('schema') != 'm12-legacy-cache-compat-v1':
        return current
    source_hashes = runtime.get('source_files')
    if (
        isinstance(source_hashes, dict)
        and all(
            isinstance(name, str)
            and isinstance(digest, str)
            and len(digest) == 64
            and all(char in '0123456789abcdef' for char in digest)
            for name, digest in source_hashes.items()
        )
        and hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True).encode('utf-8')
        ).hexdigest() == current
        and 'm14_descriptive_observations.py' in source_hashes
    ):
        # M14 has its own implementation identity. Normalize only its source
        # hash, and the exact cache-compatibility helper change in this file,
        # before applying the existing package mapping for upstream stages.
        for suffix in ('', '_crlf'):
            accepted = values.get(f'accepted_source_sha256{suffix}')
            legacy = values.get(f'legacy_source_sha256{suffix}')
            m14_source = values.get(f'm14_source_sha256{suffix}')
            workflow_source = values.get(
                f'artifact_workflow_source_sha256{suffix}')
            cache_helper_source = values.get(
                f'cache_helper_artifact_workflow_sha256{suffix}')
            if (
                isinstance(accepted, str)
                and isinstance(legacy, str)
                and isinstance(m14_source, str)
                and isinstance(workflow_source, str)
                and source_hashes.get('artifact_workflow.py') == cache_helper_source
                and len(m14_source) == 64
                and all(char in '0123456789abcdef' for char in m14_source)
                and len(workflow_source) == 64
                and all(char in '0123456789abcdef' for char in workflow_source)
            ):
                normalized = dict(source_hashes)
                normalized['m14_descriptive_observations.py'] = m14_source
                normalized['artifact_workflow.py'] = workflow_source
                normalized_digest = hashlib.sha256(
                    json.dumps(normalized, sort_keys=True).encode('utf-8')
                ).hexdigest()
                if normalized_digest == accepted:
                    return legacy
    for suffix in ('', '_crlf'):
        accepted = values.get(f'accepted_source_sha256{suffix}')
        legacy = values.get(f'legacy_source_sha256{suffix}')
        if (current == accepted
                and isinstance(legacy, str)
                and len(legacy) == 64
                and all(char in '0123456789abcdef' for char in legacy)):
            return legacy
    return current


def _stage_cache_key(stage,definition,config,input_descriptors,runtime,dependency,
                     stage_identity_context=None):
    scoped_identity=getattr(definition.handler,'cache_implementation_identity',None)
    if callable(scoped_identity):
        package_identity=None
    else:
        source_identity,line_profile=stage_cache_identity.stage_implementation_identity(
            definition,_stage_cache_registration_identity(definition))
        package_identity=(
            stage_cache_identity.legacy_package_cache_alias(
                definition.kind,source_identity,line_profile)
            or source_identity
        )
    identity={
        'stage_id':stage['id'],
        'kind':stage['kind'],
        'stage_version':definition.version,
        'config':config,
        'inputs':{
            name:{'sha256':row['sha256'],'artifact_type':row.get('artifact_type')}
            for name,row in sorted(input_descriptors.items())
        },
        'package_sha256':package_identity,
        'dependency':dependency,
    }
    if callable(scoped_identity):
        identity['key_schema']='artifact-stage-cache-v2'
        identity['workflow_cache_semantics_version']=WORKFLOW_CACHE_SEMANTICS_VERSION
        identity['stage_registration']=_stage_cache_registration_identity(definition)
        identity['implementation']=scoped_identity()
        if getattr(definition.handler,'cache_input_contract_semantics',False):
            contract_semantics_version=getattr(
                definition.handler,'cache_input_contract_semantics_version',None
            )
            if not isinstance(contract_semantics_version,str) or not contract_semantics_version:
                raise ValueError(
                    'Scoped input-contract cache semantics require a version'
                )
            identity['input_contract_semantics_version']=contract_semantics_version
            contract_types=sorted({
                row.get('artifact_type')
                for row in input_descriptors.values()
                if row.get('artifact_type')
            })
            if contract_types:
                identity['input_contract_semantics']=artifact_contracts.semantic_identity(
                    contract_types)
    if stage_identity_context is not None:
        identity['stage_identity_context']=stage_identity_context
    return hashlib.sha256(
        json.dumps(identity,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    ).hexdigest()


def _m12_manifest_path(manifest,stage):
    value=stage.get('inputs',{}).get('manifest')
    if (not isinstance(value,dict)
            or set(value)!={'path','artifact_type'}
            or value.get('artifact_type')!='m12_input_manifest'
            or not isinstance(value.get('path'),str)):
        raise ValueError('M12 requires a direct typed m12_input_manifest input')
    path=manifest.parent/value['path']
    if path.is_symlink():
        raise ValueError('M12 input manifest must not be a symbolic link')
    return path.resolve(strict=True)


def _m12_handoff_plans(manifest,stages,registry):
    if not any(stage['kind']=='m12_artifact_review' for stage in stages):
        return {}
    definitions={
        stage['id']:_producer_definition(stage,registry)
        for stage in stages
    }
    plans={}
    for stage in stages:
        if stage['kind']!='m12_artifact_review':
            continue
        path=_m12_manifest_path(manifest,stage)
        plans[stage['id']]=m12_artifact_review.validate_handoff_declarations(
            path,stage,stages,definitions)
    return plans


def _m13_manifest_path(manifest, stage):
    value = stage.get('inputs', {}).get('manifest')
    if (not isinstance(value, dict)
            or set(value) != {'path', 'artifact_type'}
            or value.get('artifact_type') != 'm13_input_manifest'
            or not isinstance(value.get('path'), str)):
        raise ValueError('M13 requires a direct typed m13_input_manifest input')
    relative = Path(value['path'])
    if (relative.is_absolute() or '\\' in value['path']
            or any(part in {'', '.', '..'} for part in value['path'].split('/'))):
        raise ValueError('M13 input manifest path must be normalized and relative')
    path = manifest.parent / value['path']
    current = manifest.parent
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('M13 input manifest path must not contain symbolic links')
    return path.resolve(strict=True)


def _m13_handoff_plans(manifest, stages, registry):
    if not any(stage['kind'] == m13_stage.STAGE_KIND for stage in stages):
        return {}
    definitions = {
        stage['id']: _producer_definition(stage, registry)
        for stage in stages
    }
    plans = {}
    for stage in stages:
        if stage['kind'] != m13_stage.STAGE_KIND:
            continue
        input_manifest_path = _m13_manifest_path(manifest, stage)
        manifest_value = m13_contracts.load_input_manifest(input_manifest_path)
        expected = {}
        bindings = []
        for run_index, run in enumerate(manifest_value['m5_runs']):
            for ref in run['artifacts']:
                name = m13_contracts.artifact_input_name(
                    run_index, ref['artifact_type'])
                expected[name] = ref
                supplied = stage['inputs'].get(name)
                if supplied is None:
                    bindings.append({
                        'input_name': name,
                        'run_index': run_index,
                        'artifact_ref': ref,
                        'declared': False,
                    })
                    continue
                if (isinstance(supplied, dict)
                        and set(supplied) == {'path', 'artifact_type'}):
                    if supplied['artifact_type'] != ref['artifact_type']:
                        bindings.append({
                            'input_name': name,
                            'run_index': run_index,
                            'artifact_ref': ref,
                            'declared': True,
                            'static_failure': 'INVALID',
                        })
                        continue
                    path_value = supplied['path']
                    relative = Path(path_value) if isinstance(path_value, str) else None
                    if (relative is None or relative.is_absolute()
                            or '\\' in path_value
                            or any(part in {'', '.', '..'} for part in path_value.split('/'))):
                        bindings.append({
                            'input_name': name,
                            'run_index': run_index,
                            'artifact_ref': ref,
                            'declared': True,
                            'static_failure': 'INVALID',
                        })
                    else:
                        current = manifest.parent
                        for part in relative.parts:
                            current = current / part
                            if current.is_symlink():
                                bindings.append({
                                    'input_name': name,
                                    'run_index': run_index,
                                    'artifact_ref': ref,
                                    'declared': True,
                                    'static_failure': 'INVALID',
                                })
                                break
                        else:
                            bindings.append({
                                'input_name': name,
                                'run_index': run_index,
                                'artifact_ref': ref,
                                'declared': True,
                            })
                elif (isinstance(supplied, dict)
                      and set(supplied) == {'stage', 'artifact'}):
                    producer_id = supplied['stage']
                    producer_stage = next(
                        (item for item in stages if item['id'] == producer_id), None)
                    producer_definition = definitions.get(producer_id)
                    position = {item['id']: index for index, item in enumerate(stages)}
                    if (producer_stage is None or producer_definition is None
                            or position[producer_id] >= position[stage['id']]
                            or producer_id != ref['producer_stage_id']
                            or supplied['artifact'] != ref['relative_path']):
                        bindings.append({
                            'input_name': name,
                            'run_index': run_index,
                            'artifact_ref': ref,
                            'declared': True,
                            'static_failure': 'INVALID',
                        })
                        continue
                    produced = _output_contract(
                        producer_definition, supplied['artifact'])
                    handler = producer_definition.handler
                    if (produced != (ref['artifact_type'],)
                            or getattr(handler, 'evidence_family', None) != 'dvg'):
                        bindings.append({
                            'input_name': name,
                            'run_index': run_index,
                            'artifact_ref': ref,
                            'declared': True,
                            'static_failure': 'INVALID',
                        })
                        continue
                    bindings.append({
                        'input_name': name,
                        'run_index': run_index,
                        'artifact_ref': ref,
                        'declared': True,
                    })
                else:
                    bindings.append({
                        'input_name': name,
                        'run_index': run_index,
                        'artifact_ref': ref,
                        'declared': True,
                        'static_failure': 'INVALID',
                    })

        extra = set(stage['inputs']) - {'manifest'} - set(expected)
        if extra:
            raise ValueError('M13 workflow declares unlisted M5 artifact inputs')
        static_failures = {
            row['input_name']: row['static_failure']
            for row in bindings
            if row.get('static_failure') is not None
        }
        plans[stage['id']] = {
            'manifest_path': str(input_manifest_path),
            'bindings': bindings,
            'static_input_failures': static_failures,
        }
    return plans


# M15_CACHE_NEUTRAL_BEGIN
def _m15_manifest_path(manifest, stage):
    value = stage.get('inputs', {}).get('manifest')
    if (not isinstance(value, dict)
            or set(value) != {'path', 'artifact_type'}
            or value.get('artifact_type') != 'm15_input_manifest'
            or not isinstance(value.get('path'), str)):
        raise ValueError('M15 requires a direct typed m15_input_manifest input')
    relative = Path(value['path'])
    if (relative.is_absolute() or '\\' in value['path']
            or re.match(r'^[A-Za-z]:', value['path'])
            or any(part in {'', '.', '..'} for part in value['path'].split('/'))):
        raise ValueError('M15 input manifest path must be normalized and relative')
    path = manifest.parent / value['path']
    current = manifest.parent
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('M15 input manifest path must not contain symbolic links')
    return path.resolve(strict=True)


def _m15_handoff_plans(manifest, stages, registry):
    if not any(stage['kind'] == m15_stage.STAGE_KIND for stage in stages):
        return {}
    definitions = {
        stage['id']: _producer_definition(stage, registry)
        for stage in stages
    }
    plans = {}
    for stage in stages:
        if stage['kind'] != m15_stage.STAGE_KIND:
            continue
        input_manifest_path = _m15_manifest_path(manifest, stage)
        manifest_value = m15_contracts.validate_input_manifest(
            m15_contracts.read_json(input_manifest_path))
        bindings = []
        expected = {}
        static_failures = {}
        position = {item['id']: index for index, item in enumerate(stages)}
        for index, ref in enumerate(manifest_value['artifact_refs']):
            name = m15_stage.artifact_input_name(index)
            expected[name] = ref
            supplied = stage['inputs'].get(name)
            binding = {
                'input_name': name,
                'artifact_ref_index': index,
                'artifact_ref': ref,
                'declared': supplied is not None,
            }
            if supplied is None:
                binding['static_failure'] = 'UNAVAILABLE'
            elif isinstance(supplied, dict) and set(supplied) == {'path', 'artifact_type'}:
                if supplied['artifact_type'] != ref['artifact_type']:
                    binding['static_failure'] = 'INPUT_ARTIFACT_TYPE_MISMATCH'
                else:
                    value = supplied['path']
                    relative = Path(value)
                    if (relative.is_absolute() or '\\' in value
                            or re.match(r'^[A-Za-z]:', value)
                            or any(part in {'', '.', '..'} for part in value.split('/'))):
                        binding['static_failure'] = 'PATH_UNSAFE'
                    else:
                        current = manifest.parent
                        for part in relative.parts:
                            current = current / part
                            if current.is_symlink():
                                binding['static_failure'] = 'PATH_UNSAFE'
                                break
            elif isinstance(supplied, dict) and set(supplied) == {'stage', 'artifact'}:
                producer_id = supplied['stage']
                producer_stage = next(
                    (item for item in stages if item['id'] == producer_id), None)
                definition = definitions.get(producer_id)
                if (producer_stage is None or definition is None
                        or position[producer_id] >= position[stage['id']]
                        or producer_id != ref['producer_stage_id']
                        or supplied['artifact'] != ref['relative_path']
                        or _output_contract(definition, supplied['artifact'])
                        != (ref['artifact_type'],)):
                    binding['static_failure'] = 'PRODUCER_TYPE_MISMATCH'
            else:
                binding['static_failure'] = 'INPUT_BINDING_INVALID'
            if binding.get('static_failure') is not None:
                static_failures[name] = binding['static_failure']
            bindings.append(binding)
        extra = set(stage['inputs']) - {'manifest'} - set(expected)
        if extra:
            raise ValueError('M15 workflow declares unlisted artifact inputs')
        plans[stage['id']] = {
            'manifest_path': str(input_manifest_path),
            'bindings': bindings,
            'static_input_failures': static_failures,
        }
    return plans
# M15_CACHE_NEUTRAL_END
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
    m12_binding_plans=_m12_handoff_plans(manifest,stages,registry)
    m13_binding_plans=_m13_handoff_plans(manifest,stages,registry)
    # M15_CACHE_NEUTRAL_BEGIN
    m15_binding_plans=_m15_handoff_plans(manifest,stages,registry)
    # M15_CACHE_NEUTRAL_END
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
        m12_context=None
        m12_validation_error=None
        m13_context=None
        m13_validation_error=None
        m13_plan=m13_binding_plans.get(stage['id'])
        m13_input_failures=(
            dict(m13_plan.get('static_input_failures',{}))
            if m13_plan is not None else {}
        )
        # M15_CACHE_NEUTRAL_BEGIN
        m15_context=None
        m15_plan=m15_binding_plans.get(stage['id'])
        m15_input_failures=(
            dict(m15_plan.get('static_input_failures',{}))
            if m15_plan is not None else {}
        )
        m15_artifact_input_names=(
            {row['input_name'] for row in m15_plan['bindings']}
            if m15_plan is not None else set()
        )
        # M15_CACHE_NEUTRAL_END
        has_missing_input=False
        waits_for_upstream=False
        for key,value in stage['inputs'].items():
            # M15_CACHE_NEUTRAL_BEGIN
            if (definition.kind==m15_stage.STAGE_KIND
                    and key in m15_input_failures):
                inputs[key]={
                    'status':m15_input_failures[key].lower(),
                    'artifact_type':None,
                    'validation_state':m15_input_failures[key].lower(),
                }
                continue
            # M15_CACHE_NEUTRAL_END
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

            if (definition.kind==m13_stage.STAGE_KIND
                    and key!='manifest'
                    and key in m13_input_failures):
                inputs[key]={
                    'status':'invalid',
                    'artifact_type':artifact_type,
                    'validation_state':'invalid',
                }
                continue
            if raw.is_symlink():
                if definition.kind==m13_stage.STAGE_KIND and key!='manifest':
                    m13_input_failures[key]='INVALID'
                # M15_CACHE_NEUTRAL_BEGIN
                elif definition.kind==m15_stage.STAGE_KIND and key!='manifest':
                    m15_input_failures[key]='PATH_UNSAFE'
                # M15_CACHE_NEUTRAL_END
                else:
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
                if definition.kind==m13_stage.STAGE_KIND and key!='manifest':
                    m13_input_failures[key]='UNAVAILABLE'
                # M15_CACHE_NEUTRAL_BEGIN
                elif definition.kind==m15_stage.STAGE_KIND and key!='manifest':
                    m15_input_failures[key]='UNAVAILABLE'
                # M15_CACHE_NEUTRAL_END
                else:
                    has_missing_input=True
                continue
            # M15_CACHE_NEUTRAL_BEGIN
            direct_m15_input = (
                definition.kind==m15_stage.STAGE_KIND
                and key in m15_artifact_input_names
                and isinstance(stage['inputs'].get(key),dict)
                and set(stage['inputs'][key])=={'path','artifact_type'}
            )
            if direct_m15_input:
                digest=checksum(path)
                descriptor={'sha256':digest,'artifact_type':artifact_type}
                inputs[key]['validation_state']='deferred_to_m15_verifier'
                inputs[key]['sha256']=digest
                input_descriptors[key]=descriptor
                continue
            # M15_CACHE_NEUTRAL_END
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
                inputs[key]['validation_state']='invalid'
                inputs[key]['validation_error']=str(error)
                if definition.kind==m13_stage.STAGE_KIND and key!='manifest':
                    m13_input_failures[key]=(
                        'UNAVAILABLE' if isinstance(error,OSError) else 'INVALID'
                    )
                # M15_CACHE_NEUTRAL_BEGIN
                elif definition.kind==m15_stage.STAGE_KIND and key!='manifest':
                    m15_input_failures[key]=(
                        'UNAVAILABLE' if isinstance(error,OSError)
                        else 'ARTIFACT_SCHEMA_INVALID'
                    )
                # M15_CACHE_NEUTRAL_END
                else:
                    has_missing_input=True

        if (definition.kind=='m12_artifact_review'
                and not has_missing_input
                and not waits_for_upstream):
            try:
                resolved_paths={
                    name:Path(value['path'])
                    for name,value in inputs.items()
                    if value.get('path')
                }
                if output_path is None or output_path.is_dir() or not m12_binding_plans[stage['id']]:
                    m12_context=m12_artifact_review.build_stage_context(
                        resolved_paths,
                        m12_binding_plans[stage['id']],
                        previous_rows,
                        output_path,
                    )
            except (OSError,ValueError,KeyError,TypeError) as error:
                has_missing_input=True
                m12_validation_error=str(error)

        if (definition.kind==m13_stage.STAGE_KIND
                and not has_missing_input
                and not waits_for_upstream):
            try:
                resolved_paths={
                    name:Path(value['path'])
                    for name,value in inputs.items()
                    if isinstance(value,dict) and value.get('path')
                }
                m13_context=m13_stage.build_stage_context(
                    resolved_paths,
                    m13_plan,
                    m13_input_failures,
                )
            except (OSError,ValueError,KeyError,TypeError) as error:
                has_missing_input=True
                m13_validation_error=str(error)

        # M15_CACHE_NEUTRAL_BEGIN
        if (definition.kind==m15_stage.STAGE_KIND
                and not has_missing_input
                and not waits_for_upstream):
            try:
                resolved_paths={
                    name:Path(value['path'])
                    for name,value in inputs.items()
                    if isinstance(value,dict) and value.get('path')
                }
                m15_context=m15_stage.build_stage_context(
                    resolved_paths, m15_plan, m15_input_failures)
            except (OSError,ValueError,KeyError,TypeError):
                has_missing_input=True
        # M15_CACHE_NEUTRAL_END
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
        if definition.kind=='m12_artifact_review':
            row['m12_handoff_count']=len(m12_binding_plans[stage['id']])
            row['m12_handoff_validation']=(
                'valid' if m12_validation_error is None else 'invalid'
            )
            if m12_validation_error is not None:
                row['m12_validation_error']=m12_validation_error
        if definition.kind==m13_stage.STAGE_KIND:
            row['m13_handoff_count']=len(m13_plan['bindings'])
            row['m13_handoff_validation']=(
                'valid' if m13_validation_error is None else 'invalid'
            )
            if m13_validation_error is not None:
                row['m13_validation_error']=m13_validation_error
        # M15_CACHE_NEUTRAL_BEGIN
        if definition.kind==m15_stage.STAGE_KIND:
            row['m15_handoff_count']=len(m15_plan['bindings'])
            row['m15_handoff_validation']=(
                'valid' if m15_context is not None else 'unavailable'
            )
        # M15_CACHE_NEUTRAL_END
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
                stage,definition,config,input_descriptors,runtime,dependency,
                stage_identity_context=(
                    m12_context['cache_identity'] if m12_context is not None
                    else m13_context['cache_identity'] if m13_context is not None
                    # M15_CACHE_NEUTRAL_BEGIN
                    else m15_context['cache_identity'] if m15_context is not None
                    # M15_CACHE_NEUTRAL_END
                    else None
                ))
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


def write_status(output, result, execution_outcome_failure_codes=None):
    """Write a useful report even when a stage cannot start or is interrupted."""
    result['final_report_paths']=['report.html','workflow.json','reproducibility.json']
    result['stage_statuses']={}
    result['input_artifacts']={}
    result['output_artifacts']={}
    if any(stage.get('evidence_family') == 'dvg' for stage in result['stages']):
        result['dvg_evaluations'] = {}
    for stage in result['stages']:
        result['stage_statuses'][stage['id']]=stage.get('status')
        if stage.get('evidence_family') == 'dvg':
            status = dvg_evidence.NOT_EVALUATED
            count = None
            raw = None
            caller = stage.get('caller', 'External DVG caller')
            caller_version = stage.get('caller_version')
            event_references = []
            remaining_event_references = 0
            evidence_file = None
            state = stage.get('status')
            if state in {'dependency_missing', 'external_module_required'}:
                status = dvg_evidence.ANALYSIS_UNAVAILABLE
            elif state in {'failed', 'interrupted'}:
                status = (
                    dvg_evidence.INVALID_RESULT
                    if stage.get('error_type') == 'InvalidDVGResultError'
                    else dvg_evidence.ANALYSIS_FAILED
                )
                if status == dvg_evidence.INVALID_RESULT:
                    failure_code = (
                        (execution_outcome_failure_codes or {}).get(stage['id'])
                        or dvg_evidence.UNCLASSIFIED_INVALID_RESULT
                    )
            elif state == 'complete':
                try:
                    record = stage['output_files']['summary.json']
                    path = output / stage['output_path'] / 'summary.json'
                    if checksum(path) != record['sha256']:
                        raise dvg_evidence.InvalidDVGResultError(
                            'DVG summary changed after output verification',
                            failure_code=dvg_evidence.CORRUPT_OUTPUT,
                        )
                    summary = json.loads(path.read_text(encoding='utf-8'))
                    dvg_evidence.validate_summary(summary)
                    if summary['status'] not in {
                        dvg_evidence.DVG_EVIDENCE_DETECTED,
                        dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
                    }:
                        raise dvg_evidence.InvalidDVGResultError(
                            'Completed DVG stage has no completed evaluation',
                            failure_code=dvg_evidence.INVALID_M5_CONTRACT,
                        )
                    status = summary['status']
                    count = summary['event_count']
                    raw = summary.get('raw_output')
                    caller = summary['caller']
                    caller_version = summary.get('caller_version', caller_version)
                    references = summary.get('event_references', [])
                    if not isinstance(references, list):
                        raise ValueError('DVG event references must be a list')
                    event_references = references[:25]
                    remaining_event_references = max(0, len(references) - 25)
                    evidence_file = summary.get('evidence_file')
                except dvg_evidence.InvalidDVGResultError as error:
                    status = dvg_evidence.INVALID_RESULT
                    failure_code = error.failure_code
                except (OSError, ValueError, TypeError, KeyError):
                    status = dvg_evidence.INVALID_RESULT
                    failure_code = dvg_evidence.UNCLASSIFIED_INVALID_RESULT
            if execution_outcome_failure_codes is not None:
                if status == dvg_evidence.INVALID_RESULT:
                    execution_outcome_failure_codes[stage['id']] = (
                        failure_code
                        if failure_code in dvg_evidence.M5_FAILURE_CODES
                        else dvg_evidence.UNCLASSIFIED_INVALID_RESULT
                    )
                else:
                    execution_outcome_failure_codes.pop(stage['id'], None)
            stage['dvg_evidence'] = {
                'caller': caller, 'caller_version': caller_version, 'status': status,
                'event_count': count, 'raw_output': raw,
                'event_references': event_references,
                'remaining_event_references': remaining_event_references,
                'evidence_file': evidence_file,
                'limitations': (
                    'No detected event is not proof that a sequence is not a DVG; '
                    'failed or unavailable analysis has no biological interpretation.'
                ),
            }
            result['dvg_evaluations'][stage['id']] = stage['dvg_evidence']
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
        evidence = stage.get('dvg_evidence')
        if evidence:
            caller = str(evidence['caller'])
            status = evidence['status']
            descriptions = {
                dvg_evidence.DVG_EVIDENCE_DETECTED: (
                    f"{caller} detected {evidence['event_count']} junction events."
                ),
                dvg_evidence.NO_DVG_EVIDENCE_DETECTED: (
                    'No DVG evidence detected by the configured caller '
                    f'({caller}) under this analysis configuration.'
                ),
                dvg_evidence.NOT_EVALUATED: f'{caller} analysis was not evaluated.',
                dvg_evidence.ANALYSIS_UNAVAILABLE: (
                    f'{caller} analysis was not performed because the dependency was unavailable.'
                ),
                dvg_evidence.ANALYSIS_FAILED: (
                    f'{caller} execution failed or was interrupted; no biological conclusion can be drawn.'
                ),
                dvg_evidence.INVALID_RESULT: (
                    f'{caller} result is invalid or incomplete; no biological conclusion can be drawn.'
                ),
            }
            body += '<p>DVG evidence: ' + html.escape(descriptions[status]) + '</p>'
            if evidence['caller_version']:
                body += '<p>Caller version: ' + html.escape(
                    str(evidence['caller_version'])[:120]
                ) + '</p>'
            if evidence['raw_output']:
                raw = evidence['raw_output']
                if (isinstance(raw, dict) and isinstance(raw.get('path'), str)
                        and raw['path'] in stage.get('output_files', {})
                        and stage['output_files'][raw['path']].get('sha256') == raw.get('sha256')):
                    href = (Path(stage_output) / raw['path']).as_posix()
                    body += '<p>Raw caller output: <a href="' + html.escape(
                        href, quote=True
                    ) + '">' + html.escape(raw['path']) + '</a> (SHA256 ' + html.escape(
                        str(raw['sha256'])
                    ) + ')</p>'
                else:
                    body += '<p>Raw caller output: <code>' + html.escape(
                        str(raw)[:500]
                    ) + '</code></p>'
            if evidence['event_references']:
                body += '<p>Evidence references:</p><ul>'
                evidence_file = evidence.get('evidence_file')
                href = None
                if (evidence_file == 'evidence.json'
                        and evidence_file in stage.get('output_files', {})):
                    href = (Path(stage_output) / evidence_file).as_posix()
                for reference in evidence['event_references']:
                    label = html.escape(str(reference)[:180])
                    if href:
                        body += '<li><a href="' + html.escape(
                            href, quote=True
                        ) + '">' + label + '</a></li>'
                    else:
                        body += '<li><code>' + label + '</code></li>'
                body += '</ul>'
                if evidence['remaining_event_references']:
                    body += '<p>' + str(evidence['remaining_event_references']) + (
                        ' more evidence references are in the stage summary.</p>'
                    )
            body += '<p>' + html.escape(evidence['limitations']) + '</p>'
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
    m12_binding_plans=_m12_handoff_plans(manifest,stages,registry)
    m13_binding_plans=_m13_handoff_plans(manifest,stages,registry)
    # M15_CACHE_NEUTRAL_BEGIN
    m15_binding_plans=_m15_handoff_plans(manifest,stages,registry)
    # M15_CACHE_NEUTRAL_END
    dvg_module_names = {
        name for name in registry.module_names()
        if getattr(registry.get_module(name).handler, 'evidence_family', None) == 'dvg'
    }

    output.mkdir(parents=True,exist_ok=True)
    lock=output/'.workflow.lock'
    lock_token=stage_lock.acquire(lock)
    marker=output/'workflow.json'
    result=None
    active=None
    execution_outcome_failure_codes={}
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
            definition=_producer_definition(item,registry)
            if getattr(definition.handler,'evidence_family',None)=='dvg':
                row['evidence_family']='dvg'
                row['caller']=getattr(definition.handler,'caller_name','External DVG caller')
                row['caller_version']=getattr(definition.handler,'caller_version',None)
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
        write_status(output,result,execution_outcome_failure_codes)

        for stage,active in zip(stages,result['stages']):
            if stage.get('skip') is True:
                transition(active,'skipped',STAGE_TRANSITIONS,
                           reason='Explicitly skipped by workflow configuration.',
                           finished_utc=datetime.now(timezone.utc).isoformat())
                write_status(output,result,execution_outcome_failure_codes)
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
                    write_status(output,result,execution_outcome_failure_codes)
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
            m13_plan=m13_binding_plans.get(stage['id'])
            m13_input_failures=(
                dict(m13_plan.get('static_input_failures',{}))
                if m13_plan is not None else {}
            )
            m13_artifact_input_names=(
                {row['input_name'] for row in m13_plan['bindings']}
                if m13_plan is not None else set()
            )
            # M15_CACHE_NEUTRAL_BEGIN
            m15_plan=m15_binding_plans.get(stage['id'])
            m15_input_failures=(
                dict(m15_plan.get('static_input_failures',{}))
                if m15_plan is not None else {}
            )
            m15_artifact_input_names=(
                {row['input_name'] for row in m15_plan['bindings']}
                if m15_plan is not None else set()
            )
            # M15_CACHE_NEUTRAL_END
            for key,value in stage['inputs'].items():
                if (definition.kind==m13_stage.STAGE_KIND
                        and key in m13_input_failures):
                    inputs[key]=None
                    active.setdefault('inputs',{})[key]={
                        'status':'invalid',
                        'validation_state':'invalid',
                        'artifact_type':m13_input_failures[key],
                    }
                    continue
                # M15_CACHE_NEUTRAL_BEGIN
                if (definition.kind==m15_stage.STAGE_KIND
                        and key in m15_input_failures):
                    failure=m15_input_failures[key]
                    inputs[key]=None
                    state='unavailable' if failure=='UNAVAILABLE' else 'invalid'
                    active.setdefault('inputs',{})[key]={
                        'status':state,
                        'validation_state':state,
                        'artifact_type':failure,
                    }
                    continue
                # M15_CACHE_NEUTRAL_END
                # M15_CACHE_NEUTRAL_BEGIN
                direct_m15_input = (
                    definition.kind==m15_stage.STAGE_KIND
                    and key in m15_artifact_input_names
                    and isinstance(value,dict)
                    and set(value)=={'path','artifact_type'}
                )
                if direct_m15_input:
                    try:
                        raw_path=manifest.parent/value['path']
                        if raw_path.is_symlink():
                            raise ValueError('Workflow inputs must not be symbolic links')
                        path=raw_path.resolve(strict=True)
                        if not path.is_file():
                            raise OSError('M15 input artifact is not a regular file')
                        inputs[key]=path
                        descriptor={
                            'sha256':checksum(path),
                            'artifact_type':value['artifact_type'],
                        }
                        input_descriptors[key]=descriptor
                        active.setdefault('inputs',{})[key]={
                            'path':str(path),
                            'sha256':descriptor['sha256'],
                            'artifact_type':value['artifact_type'],
                            'status':'available',
                            'validation_state':'deferred_to_m15_verifier',
                        }
                    except OSError:
                        inputs[key]=None
                        m15_input_failures[key]='UNAVAILABLE'
                        active.setdefault('inputs',{})[key]={
                            'status':'unavailable',
                            'validation_state':'unavailable',
                        }
                    except (ValueError,KeyError,TypeError):
                        inputs[key]=None
                        m15_input_failures[key]='PATH_UNSAFE'
                        active.setdefault('inputs',{})[key]={
                            'status':'invalid',
                            'validation_state':'invalid',
                        }
                    continue
                # M15_CACHE_NEUTRAL_END
                try:
                    path,descriptor=_resolve_stage_input(
                        manifest,output,result,stage,definition,key,value,registry)
                except OSError:
                    # M15_CACHE_NEUTRAL_BEGIN
                    if (definition.kind==m15_stage.STAGE_KIND
                            and key in m15_artifact_input_names):
                        inputs[key]=None
                        m15_input_failures[key]='UNAVAILABLE'
                        active.setdefault('inputs',{})[key]={
                            'status':'unavailable',
                            'validation_state':'unavailable',
                        }
                        continue
                    # M15_CACHE_NEUTRAL_END
                    if (definition.kind!=m13_stage.STAGE_KIND
                            or key not in m13_artifact_input_names):
                        raise
                    inputs[key]=None
                    m13_input_failures[key]='UNAVAILABLE'
                    active.setdefault('inputs',{})[key]={
                        'status':'unavailable',
                        'validation_state':'unavailable',
                    }
                    continue
                except (ValueError,KeyError,TypeError):
                    # M15_CACHE_NEUTRAL_BEGIN
                    if (definition.kind==m15_stage.STAGE_KIND
                            and key in m15_artifact_input_names):
                        inputs[key]=None
                        m15_input_failures[key]='ARTIFACT_SCHEMA_INVALID'
                        active.setdefault('inputs',{})[key]={
                            'status':'invalid',
                            'validation_state':'invalid',
                        }
                        continue
                    # M15_CACHE_NEUTRAL_END
                    if (definition.kind!=m13_stage.STAGE_KIND
                            or key not in m13_artifact_input_names):
                        raise
                    inputs[key]=None
                    m13_input_failures[key]='INVALID'
                    active.setdefault('inputs',{})[key]={
                        'status':'invalid',
                        'validation_state':'invalid',
                    }
                    continue
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

            m12_context=None
            if definition.kind=='m12_artifact_review':
                m12_context=m12_artifact_review.build_stage_context(
                    inputs,
                    m12_binding_plans[stage['id']],
                    {row['id']:row for row in result['stages']},
                    output,
                )
            m13_context=None
            if definition.kind==m13_stage.STAGE_KIND:
                m13_context=m13_stage.build_stage_context(
                    inputs,
                    m13_plan,
                    m13_input_failures,
                )
            # M15_CACHE_NEUTRAL_BEGIN
            m15_context=None
            if definition.kind==m15_stage.STAGE_KIND:
                m15_context=m15_stage.build_stage_context(
                    inputs,
                    m15_plan,
                    m15_input_failures,
                )
            # M15_CACHE_NEUTRAL_END

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
                handles_missing = getattr(definition.handler, 'handles_dependency_missing', False)
                if dependency.get('status')!='available' and not handles_missing:
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
                    write_status(output,result,execution_outcome_failure_codes)
                    active=None
                    return output/'report.html'

            cache_key=_stage_cache_key(
                stage,definition,config,input_descriptors,runtime,dependency,
                stage_identity_context=(
                    m12_context['cache_identity'] if m12_context is not None
                    else m13_context['cache_identity'] if m13_context is not None
                    # M15_CACHE_NEUTRAL_BEGIN
                    else m15_context['cache_identity'] if m15_context is not None
                    # M15_CACHE_NEUTRAL_END
                    else None
                ),
            )
            stage_output=_stage_output_directory(output,stage['id'],cache_key,previous_rows)
            if not stage_output.is_relative_to(output):
                raise ValueError('Stage output redirects outside the workflow folder')
            active['cache_key']=cache_key
            active['output_path']=stage_output.relative_to(output).as_posix()
            write_status(output,result,execution_outcome_failure_codes)
            stage_marker=stage_output/'manifest.json'
            before=checksum(stage_marker) if stage_marker.is_file() else None
            try:
                if definition.external_tool:
                    if stage['kind']=='assembly':
                        outcome=definition.handler.execute(
                            inputs,stage_output,config,context={'stage_id':stage['id']})
                    else:
                        outcome=definition.handler.execute(inputs,stage_output,config)
                elif definition.kind=='m12_artifact_review':
                    outcome=definition.handler(
                        inputs,stage_output,config,workflow_context=m12_context)
                elif definition.kind==m13_stage.STAGE_KIND:
                    outcome=definition.handler(
                        inputs,stage_output,config,workflow_context=m13_context)
                # M15_CACHE_NEUTRAL_BEGIN
                elif definition.kind==m15_stage.STAGE_KIND:
                    outcome=definition.handler(
                        inputs,stage_output,config,workflow_context=m15_context)
                # M15_CACHE_NEUTRAL_END
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
                write_status(output,result,execution_outcome_failure_codes)
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
            write_status(output,result,execution_outcome_failure_codes)
            active=None

        if checksum(manifest)!=digest:
            raise ValueError('Workflow specification changed during execution')
        final_status=aggregate_stage_status(result['stages'])
        transition(result,final_status,WORKFLOW_TRANSITIONS,
                   finished_utc=datetime.now(timezone.utc).isoformat())
        write_status(output,result,execution_outcome_failure_codes)
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
            if (
                active is not None
                and active.get('evidence_family') == 'dvg'
                and getattr(exc, 'failure_code', None) in dvg_evidence.M5_FAILURE_CODES
            ):
                execution_outcome_failure_codes[active['id']] = exc.failure_code
            if active is not None and active.get('status')=='running':
                transition(active,status,STAGE_TRANSITIONS,**failure)
            if result.get('status')=='running':
                transition(result,status,WORKFLOW_TRANSITIONS,**failure)
            write_status(output,result,execution_outcome_failure_codes)
        raise
    finally:
        active_exception = sys.exception()
        try:
            if result is not None:
                try:
                    execution_outcome.write_final_outcomes(
                        output,
                        dvg_module_names,
                        execution_outcome_failure_codes,
                    )
                except Exception as error:
                    if active_exception is None:
                        raise
                    active_exception.add_note(
                        'Failed to write M5 execution outcome sidecar: '
                        + (str(error) or type(error).__name__)
                    )
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
