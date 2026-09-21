"""Import existing nucleotide BLAST standard 12-column outfmt 6 evidence."""
import math
from .review_stage import execute, table, unique, report
from .contamination_review import ROLES


def normalize_hits(path, features, references):
    features = unique(features, 'feature_id')
    references = unique(references, 'reference_id')
    lengths = {key: int(row['length']) for key,row in features.items()}
    if any(n <= 0 for n in lengths.values()):
        raise ValueError('Feature lengths must be positive')
    if any(r['reference_role'] not in ROLES for r in references.values()):
        raise ValueError('Invalid reference role')
    if path.stat().st_size > 64_000_000:
        raise ValueError('BLAST table exceeds 64 MB')
    rows = []
    with path.open(encoding='utf-8') as source:
        for line in source:
            if not line.strip():
                continue
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) != 12 or len(rows) >= 200_000:
                raise ValueError('Expected standard 12-column BLAST outfmt 6; maximum 200,000 hits')
            query, reference = fields[:2]
            if query not in features or reference not in references:
                raise ValueError('BLAST query/reference ID is absent from its supplied manifest')
            identity, aligned = float(fields[2]), int(fields[3])
            mismatches, gaps = int(fields[4]), int(fields[5])
            qstart,qend,sstart,send = map(int, fields[6:10])
            evalue,bitscore = map(float,fields[10:12])
            if not all(math.isfinite(n) for n in (identity,evalue,bitscore)) or not 0 <= identity <= 100 or min(evalue,bitscore,mismatches,gaps) < 0 or aligned <= 0 or max(mismatches,gaps) > aligned:
                raise ValueError('Invalid BLAST numeric values')
            if not 1 <= min(qstart,qend) <= max(qstart,qend) <= lengths[query] or min(sstart,send) < 1 or max(abs(qend-qstart),abs(send-sstart))+1 > aligned:
                raise ValueError('BLAST coordinates do not fit the supplied nucleotide feature')
            ref = references[reference]
            rows.append({'feature_id':query,'reference_id':reference,'reference_role':ref['reference_role'],
                         'query_start':min(qstart,qend)-1,'query_end':max(qstart,qend),
                         'percent_identity':identity,'reference_source':ref['reference_source'],
                         'reference_version':ref['reference_version'],'query_orientation':'forward' if qstart <= qend else 'reverse',
                         'evalue':evalue,'bitscore':bitscore})
    found = {r['feature_id'] for r in rows}
    status = [{'feature_id':key,'reported_hit_status':'reported_match' if key in found else 'no_reported_hit',
               'biological_classification':'not_determined'} for key in features]
    return rows,status


def run(features, references, hits, output):
    def produce(paths,directory):
        rows,status = normalize_hits(paths['hits'], table(paths['features'],('feature_id','length')),
                                    table(paths['references'],('reference_id','reference_role','reference_source','reference_version')))
        files = report(directory,'Imported BLAST evidence',{'matches':rows,'features':status},[
            'Imports existing standard nucleotide BLAST outfmt 6; does not query databases or generate new alignments.',
            'One-based inclusive BLAST query endpoints become zero-based half-open intervals; reverse coordinates are retained as orientation metadata.',
            'No reported hit is not evidence of novelty or absence. Database coverage, search settings and sensitivity remain external evidence.',
            'No E-value or score threshold is silently applied; values are descriptive and not calibrated biological probabilities.',
            'The matches CSV can be used by the existing contamination-evidence review.'])
        if not rows:
            (directory/'matches.csv').write_text('feature_id,reference_id,reference_role,query_start,query_end,percent_identity,reference_source,reference_version\n',encoding='utf-8')
        return files
    return execute('blast-table-import-v1',{'features':features,'references':references,'hits':hits},output,__file__,produce)
