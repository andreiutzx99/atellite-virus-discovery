"""Evaluate supplied file-digest observations; no sequence processing or discovery."""
import argparse
from collections import Counter, defaultdict
import re
import time
from .review_stage import execute, report, table, unique


def run(datasets, expectations, artifacts, output):
    def produce(paths, directory):
        start = time.monotonic()
        data = table(paths['datasets'], ('dataset_id', 'role', 'processing_status', 'reference_version'))
        expected = table(paths['expectations'], ('benchmark_id', 'artifact_sha256'))
        observed = table(paths['artifacts'], ('dataset_id', 'artifact_id', 'artifact_sha256', 'classification'))
        samples = unique(data, 'dataset_id')
        unique(expected, 'benchmark_id')
        if not samples or not expected:
            raise ValueError('Provide at least one dataset and expectation')
        for sample in data:
            if sample['role'] not in {'positive', 'negative', 'unspecified'}:
                raise ValueError('Invalid dataset role')
            if sample['processing_status'] != 'complete':
                raise ValueError('Incomplete processing cannot be interpreted as a negative result')
        seen = set()
        by_sample = defaultdict(list)
        recurrence = defaultdict(set)
        for row in expected + observed:
            if not re.fullmatch('[0-9a-f]{64}', row['artifact_sha256']):
                raise ValueError('Expected a lowercase SHA256 digest')
        for row in observed:
            key = (row['dataset_id'], row['artifact_id'])
            if row['dataset_id'] not in samples or key in seen:
                raise ValueError('Unknown dataset or duplicate artifact ID within a dataset')
            if row['classification'] not in {'classified', 'unclassified'}:
                raise ValueError('Classification must be classified or unclassified')
            seen.add(key)
            by_sample[row['dataset_id']].append(row)
            recurrence[row['artifact_sha256']].add(row['dataset_id'])
        # Bound the output cross product, not just input table sizes.
        if len(data) * len(expected) > 200_000:
            raise ValueError('Benchmark comparison exceeds 200,000 rows')
        results, counts = [], []
        for sample in data:
            rows = by_sample[sample['dataset_id']]
            matches = defaultdict(list)
            for row in rows:
                matches[row['artifact_sha256']].append(row['artifact_id'])
            classes = Counter(row['classification'] for row in rows)
            counts.append({'dataset_id': sample['dataset_id'], 'role': sample['role'],
                           'produced': len(rows), 'classified': classes['classified'],
                           'unclassified': classes['unclassified'],
                           'reference_version': sample['reference_version']})
            for target in expected:
                ids = matches[target['artifact_sha256']]
                results.append({'benchmark_id': target['benchmark_id'], 'dataset_id': sample['dataset_id'],
                                'role': sample['role'], 'expected_sha256': target['artifact_sha256'],
                                'exact_digest_observed': bool(ids), 'matching_artifact_count': len(ids),
                                'first_artifact_id': ids[0] if ids else '',
                                'withheld_identity': 'not_verified', 'similarity': 'not_computed',
                                'scientific_recovery': 'not_assessed'})
        repeated = [{'artifact_sha256': digest, 'dataset_count': len(ids),
                     'negative_dataset_count': sum(samples[s]['role'] == 'negative' for s in ids)}
                    for digest, ids in sorted(recurrence.items())]
        return report(directory, 'Supplied artifact benchmark and control accounting',
                      {'comparisons': results, 'counts': counts, 'recurrence': repeated,
                       'execution': [{'elapsed_seconds': time.monotonic()-start}]}, [
            'Exact file digests and supplied classifications only. Underlying files and processing declarations are not independently verified.',
            'Expected identities are evaluator-only inputs; this report cannot prove they were withheld upstream.',
            'Zero observations require an explicit completed dataset row. Failed or unassessed processing is never a negative result.',
            'Recurrence counts each dataset once per digest. No sensitivity, specificity, false-positive rate, biological identity or candidate rank is inferred.',
            'Input/output hashes, software version and command are recorded in manifest.json; workflow execution also writes reproducibility.json.'])
    return execute('supplied-artifact-benchmark-v1',
                   {'datasets': datasets, 'expectations': expectations, 'artifacts': artifacts}, output, __file__, produce)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('datasets', 'expectations', 'artifacts', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    run(args.datasets, args.expectations, args.artifacts, args.output)
