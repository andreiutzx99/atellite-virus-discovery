"""Summarize supplied reference matches and technical-control observations."""
import math
from collections import defaultdict
from .review_stage import execute, table, unique, report

ROLES = {'host', 'microbial', 'vector', 'adapter', 'technical_reference', 'known_virus'}


def summarize(features, matches, controls):
    indexed = unique(features, 'feature_id')
    lengths = {key: int(row['length']) for key, row in indexed.items()}
    if any(length <= 0 for length in lengths.values()):
        raise ValueError('Feature lengths must be positive')
    intervals, identities, references = defaultdict(list), defaultdict(list), defaultdict(set)
    for row in matches:
        feature, role = row['feature_id'], row['reference_role']
        if feature not in indexed or role not in ROLES:
            raise ValueError('Unknown feature or reference role')
        start, end = int(row['query_start']), int(row['query_end'])
        identity = float(row['percent_identity'])
        if not 0 <= start < end <= lengths[feature] or not math.isfinite(identity) or not 0 <= identity <= 100:
            raise ValueError('Invalid match coordinates or percent identity')
        key = feature, role
        intervals[key].append((start, end))
        identities[key].append(identity)
        references[key].add((row['reference_id'], row['reference_source'], row['reference_version']))
    calls = defaultdict(dict)
    for row in controls:
        feature, sample, detection = row['feature_id'], row['sample_id'], row['detection']
        if feature not in indexed or sample in calls[feature] or detection not in {'present', 'absent', 'unknown'}:
            raise ValueError('Invalid or duplicate technical-control observation')
        calls[feature][sample] = detection
    summaries, evidence = [], []
    for feature in sorted(indexed):
        roles = []
        for role in sorted(ROLES):
            key = feature, role
            if not intervals[key]:
                continue
            merged = []
            for start, end in sorted(intervals[key]):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            roles.append(role)
            evidence.append({'feature_id': feature, 'reference_role': role,
                             'union_query_coverage': sum(b-a for a,b in merged) / lengths[feature],
                             'maximum_reported_identity': max(identities[key]),
                             'reference_provenance': sorted(references[key])})
        detections = list(calls[feature].values())
        summaries.append({'feature_id': feature, 'reference_match_roles': roles,
                          'technical_controls_present': detections.count('present'),
                          'technical_controls_absent': detections.count('absent'),
                          'technical_controls_unknown': detections.count('unknown'),
                          'technical_controls_supplied': len(detections),
                          'review_status': 'evidence_requires_review' if roles or 'present' in detections else 'insufficient_evidence',
                          'contamination_probability': None})
    return summaries, evidence


def run(features, matches, controls, output):
    def produce(paths, directory):
        summaries, evidence = summarize(table(paths['features'], ('feature_id', 'length')),
            table(paths['matches'], ('feature_id', 'reference_id', 'reference_role', 'query_start', 'query_end', 'percent_identity', 'reference_source', 'reference_version')),
            table(paths['controls'], ('sample_id', 'feature_id', 'detection')))
        return report(directory, 'Descriptive contamination evidence', {'features': summaries, 'matches': evidence}, [
            'Reference matches and control detections are supplied inputs; this stage does not perform sequence searches.',
            'Coordinates are zero-based, half-open. Coverage is the union across matches within each role, not proof of one full-length reference match.',
            'No match, or no supplied controls, is insufficient evidence rather than evidence of cleanliness.',
            'A technical-control detection flags review; it does not establish the source or mechanism of contamination.',
            'No automatic rejection, calibrated probability, index-hopping diagnosis or taxonomic determination is made.'])
    return execute('contamination-review-v1', {'features': features, 'matches': matches, 'controls': controls}, output, __file__, produce)
