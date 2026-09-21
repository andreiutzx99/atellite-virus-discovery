"""Conservative metadata scope checks; never a biosafety or strain-identity certificate."""
import hashlib
import json
import re
from pathlib import Path

POLICY_PATH = Path(__file__).with_name('model_scope.json')
POLICY = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
MODELS = POLICY['models']
POLICY_SHA256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()


def mentions(text, term):
    pattern = re.escape(term).replace(r'\ ', r'\s+').replace(r'\-', r'[-\s]?')
    return re.search(r'(?<![a-z0-9])' + pattern + r'(?![a-z0-9])', text, re.I) is not None


def require_model(model):
    if model not in MODELS:
        raise ValueError('Choose an exact model from the revised scope; broad or excluded virus labels are disabled')
    return MODELS[model]


def search_terms(model):
    item = require_model(model)
    organisms = '(' + ' OR '.join('"' + x + '"[All Fields]' for x in item['organism_terms']) + ')'
    strains = item['strain_terms'] + [item['catalog']]
    return organisms + ' AND (' + ' OR '.join('"' + x + '"[All Fields]' for x in strains) + ')'


def evaluate(row, model):
    item = require_model(model)
    attrs = row.get('attributes') or {}
    if not isinstance(attrs, dict):
        raise ValueError('Sample attributes must be a dictionary')
    fields = {key: str(row.get(key) or '') for key in ('organism', 'sample_title', 'experiment_title')}
    fields.update({'attribute:' + str(k): str(v) for k, v in attrs.items()})
    sample_text = '\n'.join(fields.values())
    context = sample_text + '\n' + str(row.get('study_title') or '')
    excluded = [term for term in POLICY['excluded_mentions'] if mentions(context, term)]
    review = [term for term in POLICY['review_mentions'] if mentions(context, term)]
    evidence = [key for key, text in fields.items() if mentions(text, item['catalog'])]
    strain_fields = [str(v) for k, v in attrs.items() if str(k).lower().replace('_', ' ') in
                     {'strain', 'virus strain', 'viral strain', 'isolate', 'strain designation'}]
    strain_hit = any(value.strip().casefold() == term.casefold()
                     for value in strain_fields for term in item['strain_terms'])
    organism_hit = any(mentions(sample_text, term) for term in item['organism_terms'])
    other_catalogs = [m['catalog'] for key, m in MODELS.items()
                      if key != model and mentions(sample_text, m['catalog'])]
    status, reason = 'review_required', 'exact_model_metadata_missing'
    if excluded:
        status, reason = 'excluded', 'excluded_pathogen_mentioned_in_metadata'
    elif review or other_catalogs:
        reason = 'mixed_modified_or_conflicting_model_metadata'
    elif evidence or (organism_hit and strain_hit):
        status, reason = 'metadata_match', 'catalog_or_structured_strain_match'
    return {'model': model, 'status': status, 'reason': reason, 'policy_sha256': POLICY_SHA256,
            'catalog_evidence_fields': evidence, 'structured_strain_match': strain_hit,
            'excluded_mentions': excluded, 'review_mentions': review,
            'conflicting_catalogs': other_catalogs,
            'limitation': 'Metadata screening only; does not verify stock provenance, sequence identity, infection or absence of unreported organisms'}


def enforce(row, model=None):
    model = model or row.get('proposed_helper')
    if model not in MODELS:
        decision = {'model': model, 'status': 'excluded', 'reason': 'legacy_or_out_of_scope_model',
                    'policy_sha256': POLICY_SHA256}
    else:
        decision = evaluate(row, model)
    row['scope'] = decision
    if decision['status'] != 'metadata_match':
        row['selection'] = 'excluded'
        row['exclusion_reasons'] = list(dict.fromkeys([*row.get('exclusion_reasons', []), decision['reason']]))
    return row


def mapping_scope(qc_directory, reference_manifest, model):
    """Bind a mapped QC folder to its actual source-run metadata and model."""
    require_model(model)
    qc = Path(qc_directory).resolve(strict=True)
    if qc.name != 'qc' or qc.parent.parent.name != 'phase3':
        raise ValueError('Use an existing run/phase3/<accession>/qc folder')
    metadata = qc.parents[2] / 'datasets.json'
    rows = json.loads(metadata.read_text(encoding='utf-8'))
    matches = [row for row in rows if row.get('run_accession') == qc.parent.name]
    if len(matches) != 1:
        raise ValueError('QC accession must have exactly one source metadata record')
    decision = evaluate(matches[0], model)
    if decision['status'] != 'metadata_match':
        raise ValueError('Mapping held by revised scope: ' + decision['reason'])
    spec = json.loads(Path(reference_manifest).read_text(encoding='utf-8'))
    if spec.get('model_id') != model:
        raise ValueError('Reference manifest must declare the same exact model_id')
    for entry in spec.get('references', []):
        if entry.get('role') == 'helper' and entry.get('model_id') != model:
            raise ValueError('Every helper reference must declare the selected model_id')
    return {'model': model, 'policy_sha256': POLICY_SHA256, 'metadata_scope': decision,
            'run_accession': qc.parent.name,
            'datasets_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest()}
