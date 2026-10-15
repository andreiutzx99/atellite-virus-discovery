"""Deterministic bounded stress cases for the pinned ViReMa adapter."""
import json
from pathlib import Path
import random
import time

try:
    import resource
except ImportError:  # pragma: no cover - benchmark runner is Linux-only
    resource = None


GENOME_SEEDS = (1729, 2718, 31415)
GENOME_LENGTH = 6000
ADAPTER = 'AGATCGGAAGAGCACACGTCTGAACTCCAGTCA'
BREAKPOINT_TOLERANCES = (0, 5, 10)


def artificial_genome(seed, repeat=False):
    rng = random.Random(seed)
    sequence = ''.join(rng.choice('ACGT') for _ in range(GENOME_LENGTH))
    if repeat:
        sequence = sequence[:4500] + sequence[300:360] + sequence[4560:]
    return sequence


def _write_fastq(path, reads):
    with Path(path).open('w', encoding='ascii', newline='\n') as stream:
        for index, (sequence, quality) in enumerate(reads, 1):
            stream.write(f'@synthetic_read_{index:04d}\n{sequence}\n+\n{quality}\n')
    return Path(path)


def _mutate_read(sequence, rate_percent, seed):
    result = list(sequence)
    quality = ['I'] * len(result)
    if rate_percent:
        rng = random.Random(seed)
        count = max(1, round(len(result) * rate_percent / 100))
        for position in rng.sample(range(len(result)), count):
            alternatives = [base for base in 'ACGT' if base != result[position]]
            result[position] = rng.choice(alternatives)
            quality[position] = '!'
    return ''.join(result), ''.join(quality)


def _overlapping_occurrences(sequence, fragment):
    count = 0
    start = 0
    while True:
        start = sequence.find(fragment, start)
        if start < 0:
            return count
        count += 1
        start += 1


def build_stress_cases(root):
    """Return separate truth-blind input files and harness-only expected truth."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    genomes = {seed: artificial_genome(seed) for seed in GENOME_SEEDS}
    designs = [
        # Baselines across independent references and three rearrangement patterns.
        ('baseline_seed_1729', 1729, 100, 10, 0, 'leader_body_like', 350, 2050),
        ('baseline_seed_2718', 2718, 100, 10, 0, 'internal_deletion_like', 1050, 3450),
        ('baseline_seed_31415', 31415, 100, 10, 0, 'reverse_order_like', 3900, 1250),
        # Read-length sweep, holding support and errors constant.
        ('length_50', 1729, 50, 10, 0, 'leader_body_like', 850, 2750),
        ('length_75', 2718, 75, 10, 0, 'internal_deletion_like', 1650, 4050),
        ('length_150', 31415, 150, 10, 0, 'reverse_order_like', 4200, 1850),
        # Support sweep; the baseline is the 10-read condition above.
        ('support_1', 1729, 100, 1, 0, 'leader_body_like', 1350, 3250),
        ('support_2', 2718, 100, 2, 0, 'internal_deletion_like', 2250, 4550),
        ('support_5', 31415, 100, 5, 0, 'reverse_order_like', 3650, 950),
        ('support_20', 1729, 100, 20, 0, 'leader_body_like', 1850, 4250),
        # Error sweep; 0% is represented by the baseline conditions.
        ('error_1pct', 2718, 100, 10, 1, 'internal_deletion_like', 2850, 950),
        ('error_2pct', 31415, 100, 10, 2, 'reverse_order_like', 3150, 1150),
        ('error_5pct', 1729, 100, 10, 5, 'leader_body_like', 2450, 4450),
    ]
    positive = []
    for label, seed, length, support, error_rate, pattern, first_start, second_start in designs:
        genome = genomes[seed]
        left_length = length // 2
        right_length = length - left_length
        reverse = pattern == 'reverse_order_like'
        if reverse:
            first = genome[first_start:first_start + left_length]
            second = genome[second_start:second_start + right_length]
            breakpoints = (first_start + left_length, second_start + 1)
        else:
            first = genome[first_start:first_start + left_length]
            second = genome[second_start:second_start + right_length]
            breakpoints = (first_start + left_length, second_start + 1)
        junction_read = first + second
        case_dir = root / label
        case_dir.mkdir()
        reference_path = case_dir / 'reference.fasta'
        reference_path.write_text(
            f'>SYNTHETIC_GENOME_SEED_{seed}\n{genome}\n', encoding='ascii'
        )
        reads = [
            _mutate_read(junction_read, error_rate, seed * 1000 + index)
            for index in range(support)
        ]
        positive.append({
            'label': label,
            'kind': 'positive',
            'reference_path': reference_path,
            'reads_path': _write_fastq(case_dir / 'reads.fastq', reads),
            'seed': seed,
            'read_length': length,
            'support': support,
            'error_rate_percent': error_rate,
            'quality': 'Q40 matches; Q0 at simulated substitutions',
            'substitutions_per_read': (
                max(1, round(length * error_rate / 100)) if error_rate else 0
            ),
            'pattern': pattern,
            'expected_breakpoints': list(breakpoints),
            'mapping_ambiguity': {
                'left_flank_occurrences': _overlapping_occurrences(genome, first),
                'right_flank_occurrences': _overlapping_occurrences(genome, second),
                'seed_length_25mer_occurrences': {
                    'left_prefix': _overlapping_occurrences(genome, first[:25]),
                    'left_suffix': _overlapping_occurrences(genome, first[-25:]),
                    'right_prefix': _overlapping_occurrences(genome, second[:25]),
                    'right_suffix': _overlapping_occurrences(genome, second[-25:]),
                },
            },
        })

    # Each negative condition is a separate caller execution and report row.
    negative_seed = 2718
    negative_genome = artificial_genome(negative_seed, repeat=True)
    continuous = negative_genome[600:700]
    changed, changed_quality = _mutate_read(continuous, 1, 7001)
    repeated = negative_genome[300:360]
    adapter_read = negative_genome[800:834] + ADAPTER[:32] + negative_genome[834:868]
    negative_specs = [
        ('negative_continuous', [(continuous, 'I' * len(continuous))] * 20),
        ('negative_substitution', [(changed, changed_quality)] * 20),
        ('negative_repetitive_ambiguous', [(repeated, 'I' * len(repeated))] * 20),
        ('negative_low_complexity', [('A' * 100, 'I' * 100)] * 20),
        ('negative_adapter_chimera', [(adapter_read, 'I' * len(adapter_read))] * 20),
        ('negative_low_quality', [(continuous, '!' * len(continuous))] * 20),
        ('negative_short_continuous', [
            (negative_genome[1100:1150], 'I' * 50),
        ] * 20),
    ]
    negatives = []
    for label, reads in negative_specs:
        case_dir = root / label
        case_dir.mkdir()
        reference_path = case_dir / 'reference.fasta'
        reference_path.write_text(
            f'>SYNTHETIC_NEGATIVE_SEED_{negative_seed}\n{negative_genome}\n',
            encoding='ascii',
        )
        negatives.append({
            'label': label,
            'kind': 'negative',
            'reference_path': reference_path,
            'reads_path': _write_fastq(case_dir / 'reads.fastq', reads),
            'seed': negative_seed,
            'read_length': len(reads[0][0]),
            'support': len(reads),
            'error_rate_percent': None,
            'quality': label,
            'substitutions_per_read': None,
            'pattern': 'junction_free_control',
            'expected_breakpoints': None,
            'mapping_ambiguity': None,
        })
    return positive, negatives


def _breakpoint_distance(expected, observed):
    if expected is None:
        return None
    return max(
        abs(expected[0] - observed['breakpoint_1']),
        abs(expected[1] - observed['breakpoint_2']),
    )


def _case_result(adapter, case, output_dir):
    started = time.perf_counter()
    result = {
        'label': case['label'],
        'kind': case['kind'],
        'seed': case['seed'],
        'read_length': case['read_length'],
        'supporting_reads': case['support'],
        'error_rate_percent': case['error_rate_percent'],
        'substitutions_per_read': case['substitutions_per_read'],
        'quality_profile': case['quality'],
        'pattern': case['pattern'],
        'expected_breakpoints': case['expected_breakpoints'],
        'mapping_ambiguity': case['mapping_ambiguity'],
    }
    try:
        outcome = adapter.execute(
            {'reads': case['reads_path'], 'reference': case['reference_path']},
            output_dir, {'sample_id': 'stress_' + case['label'], 'mismatches': 1},
        )
        evidence_path = Path(output_dir) / 'evidence.json'
        summary_path = Path(output_dir) / 'summary.json'
        evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        events = evidence.get('events', [])
        distances = [
            _breakpoint_distance(case['expected_breakpoints'], event)
            for event in events
        ] if case['expected_breakpoints'] else []
        matched_index = next((
            index for index, distance in enumerate(distances) if distance <= 10
        ), None)
        result.update({
            'execution': outcome.execution,
            'status': summary.get('status'),
            'observed_events': events,
            'event_count': len(events),
            'breakpoint_distances': distances,
            'matched_within_10bp': matched_index is not None,
            'exact_match': matched_index is not None and distances[matched_index] == 0,
            'within_5bp': matched_index is not None and distances[matched_index] <= 5,
            'false_positive_events': (
                len(events) if case['kind'] == 'negative'
                else len(events) - int(matched_index is not None)
            ),
            'false_negative_events': int(
                case['kind'] == 'positive' and matched_index is None
            ),
            'raw_output': (
                Path(output_dir) / 'raw' / 'Virus_Recombination_Results.txt'
            ).read_text(encoding='utf-8', errors='replace')[:4000],
            'caller_logs': {
                name: (Path(output_dir) / name).read_text(
                    encoding='utf-8', errors='replace'
                )[-4000:]
                for name in ('stdout.log', 'stderr.log')
                if (Path(output_dir) / name).is_file()
            },
            'runtime_seconds': round(time.perf_counter() - started, 4),
            'output_bytes': sum(
                path.stat().st_size for path in Path(output_dir).rglob('*')
                if path.is_file()
            ),
        })
        if case['kind'] == 'positive' and matched_index is None:
            result['failure_analysis'] = {
                'classification': 'missed_or_misplaced_event',
                'mapping_ambiguity': case['mapping_ambiguity'],
                'possible_explanation': (
                    'This is an observation, not a causal conclusion; inspect the '
                    'captured ViReMa/Bowtie logs and compare support, errors, and '
                    'reference uniqueness.'
                ),
            }
        elif case['kind'] == 'positive' and distances[matched_index] != 0:
            result['failure_analysis'] = {
                'classification': 'breakpoint_offset',
                'mapping_ambiguity': case['mapping_ambiguity'],
                'possible_explanation': (
                    'The event is within 10 nt but not exact; mapping uncertainty '
                    'or the caller seed/mismatch settings may contribute.'
                ),
            }
        return result
    except Exception as error:
        result.update({
            'execution': 'error',
            'error': f'{type(error).__name__}: {error}'[:2000],
            'runtime_seconds': round(time.perf_counter() - started, 4),
            'observed_events': [],
            'false_positive_events': 0,
            'false_negative_events': int(case['kind'] == 'positive'),
            'failure_analysis': {
                'classification': 'execution_or_normalization_error',
                'mapping_ambiguity': case['mapping_ambiguity'],
                'possible_explanation': (
                    'The caller did not yield a normalized report; inspect the '
                    'case directory logs before drawing a detection conclusion.'
                ),
            },
        })
        return result


def run_stress_benchmark(adapter, output_dir):
    """Run 13 positive and 7 independent negative datasets and return metrics."""
    output_dir = Path(output_dir)
    inputs_dir = output_dir / 'inputs'
    outputs_dir = output_dir / 'outputs'
    outputs_dir.mkdir(parents=True, exist_ok=False)
    positive, negative = build_stress_cases(inputs_dir)
    rows = [
        _case_result(adapter, case, outputs_dir / case['label'])
        for case in (*positive, *negative)
    ]
    positive_rows = [row for row in rows if row['kind'] == 'positive']
    negative_rows = [row for row in rows if row['kind'] == 'negative']
    tp10 = sum(row['matched_within_10bp'] for row in positive_rows)
    tp5 = sum(row['within_5bp'] for row in positive_rows)
    exact = sum(row['exact_match'] for row in positive_rows)
    fp = sum(row['false_positive_events'] for row in rows)
    fn10 = len(positive_rows) - tp10
    stratified = {}
    for dimension, field in (
        ('read_length_nt', 'read_length'),
        ('supporting_reads', 'supporting_reads'),
        ('substitution_rate_percent', 'error_rate_percent'),
    ):
        groups = {}
        for row in positive_rows:
            key = str(row[field])
            groups.setdefault(key, []).append(row)
        stratified[dimension] = {}
        for key, members in sorted(groups.items()):
            recovered = sum(item['matched_within_10bp'] for item in members)
            exact_members = sum(item['exact_match'] for item in members)
            stratified[dimension][key] = {
                'independent_trials': len(members),
                'recovered_within_10bp': recovered,
                'false_negative_trials': len(members) - recovered,
                'exact_breakpoint_trials': exact_members,
            }
    report = {
        'schema': 'virema-synthetic-stress-v1',
        'interpretation': 'generated data only; not a biological error-rate estimate',
        'design': {
            'positive_independent_trials': len(positive_rows),
            'negative_independent_datasets': len(negative_rows),
            'reads_per_positive_event': sorted({case['support'] for case in positive}),
            'reads_per_negative_dataset': 20,
            'read_lengths_nt': sorted({case['read_length'] for case in positive}),
            'substitution_rates_percent': [0, 1, 2, 5],
            'reference_seeds': list(GENOME_SEEDS),
            'reference_length_nt': GENOME_LENGTH,
            'caller_mismatches': 1,
            'truth_passed_to_caller': False,
            'junction_transcript_references': 0,
            'breakpoint_tolerances_nt': list(BREAKPOINT_TOLERANCES),
        },
        'metrics': {
            'true_positive_events_within_10bp': tp10,
            'false_positive_events': fp,
            'false_negative_events_at_10bp': fn10,
            'sensitivity_within_10bp': tp10 / len(positive_rows) if positive_rows else None,
            'precision_within_10bp': tp10 / (tp10 + fp) if tp10 + fp else None,
            'exact_breakpoint_trials': exact,
            'within_5bp_trials': tp5,
            'within_10bp_trials': tp10,
            'missed_or_outside_10bp_trials': fn10,
        },
        'stratified_positive_results': stratified,
        'negative_datasets': [{
            'name': row['label'],
            'false_positive_events': row['false_positive_events'],
            'event_count': row['event_count'] if 'event_count' in row else None,
            'calls': row.get('observed_events', []),
        } for row in negative_rows],
        'cases': rows,
        'runtime_seconds_total': round(
            sum(row.get('runtime_seconds', 0) for row in rows), 4
        ),
        'output_bytes_total': sum(row.get('output_bytes', 0) for row in rows),
        'peak_child_rss_kb': (
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            if resource is not None else None
        ),
        'resource_measurement_note': (
            'Peak child-process RSS is the runner-level high-water mark; per-case '
            'wall time and output bytes are recorded separately.'
        ),
        'infrastructure_errors': sum(row['execution'] == 'error' for row in rows),
    }
    return report
