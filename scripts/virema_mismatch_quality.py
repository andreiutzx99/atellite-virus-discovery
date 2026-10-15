"""Controlled synthetic investigation of ViReMa mismatch and FASTQ quality effects."""
import hashlib
import json
from pathlib import Path
import random
import re
import time

from scripts.virema_stress import (
    _mutate_read, _write_fastq, artificial_genome,
)


GENOMES = (1729, 2718, 31415)
BREAKPOINTS = {1729: (400, 2051), 2718: (1600, 4001), 31415: (3900, 1251)}
SUPPORT = 10
READ_LENGTH = 100


def _read(seed, rate):
    genome = artificial_genome(seed)
    left_bp, right_start = BREAKPOINTS[seed]
    sequence = genome[left_bp - 50:left_bp] + genome[right_start - 1:right_start + 49]
    positions = []
    changed = list(sequence)
    if rate:
        rng = random.Random(seed * 100 + rate)
        positions = sorted(rng.sample(range(len(sequence)), rate))
        for position in positions:
            changed[position] = rng.choice([base for base in 'ACGT' if base != sequence[position]])
    return genome, sequence, ''.join(changed), positions


def _quality(length, changed_positions=(), score=40):
    chars = ['I' if score == 40 else '5' if score == 20 else '!'] * length
    for position in changed_positions:
        chars[position] = '!'
    return ''.join(chars)


def _condition_rows():
    rows = []
    for seed in GENOMES:
        genome, exact, _, _ = _read(seed, 0)
        for score in (0, 20, 40):
            rows.append((f's{seed}_exact_q{score}', seed, 0, exact,
                         _quality(len(exact), score=score), 1, 'quality_only'))
        for rate in (2, 5):
            _, _, altered, positions = _read(seed, rate)
            rows.append((f's{seed}_{rate}pct_q40', seed, rate, altered,
                         _quality(len(altered), score=40), 1, 'substitution_only'))
            rows.append((f's{seed}_{rate}pct_q0mut', seed, rate, altered,
                         _quality(len(altered), positions, score=40), 1, 'combined'))
    # A bounded mismatch sweep on one 5%-substitution sequence at both
    # quality profiles. Mismatch=1 is already represented above.
    _, _, altered, positions = _read(1729, 5)
    for score_name, quality in (
        ('q40', _quality(len(altered), score=40)),
        ('q0mut', _quality(len(altered), positions, score=40)),
    ):
        for mismatches in (0, 2, 3):
            rows.append((f's1729_5pct_{score_name}_n{mismatches}', 1729, 5,
                         altered, quality, mismatches, 'mismatch_sweep'))
    # A junction-free control is run once at each supported setting so a
    # sensitivity change is not presented without an observed false-call check.
    for mismatches in (0, 1, 2, 3):
        rows.append((f'negative_continuous_n{mismatches}', 2718, -1, '',
                     '', mismatches, 'negative_control'))
    # Recreate PR72's precise missed input: independently mutated reads from
    # its original seed, position, and per-read mutation seed rule.
    for score_name in ('q40', 'q0mut'):
        for mismatches in (0, 1, 2, 3):
            rows.append((f'pr72_anchor_{score_name}_n{mismatches}', 1729, -5,
                         '', '', mismatches, 'pr72_anchor'))
    return rows


def _unknown_ambiguous(stdout):
    matches = re.findall(
        r'(\d+)\s+events?\s+were\s+Unknown or Ambiguous',
        stdout, flags=re.IGNORECASE,
    )
    return sum(map(int, matches))


def run_failure_investigation(adapter, output_dir):
    """Run 39 controlled caller executions; all truth stays in this harness."""
    output_dir = Path(output_dir)
    input_dir, output_root = output_dir / 'inputs', output_dir / 'outputs'
    input_dir.mkdir(parents=True, exist_ok=False)
    output_root.mkdir()
    rows = []
    for label, seed, rate, sequence, quality, mismatches, comparison in _condition_rows():
        case_dir = input_dir / label
        case_dir.mkdir()
        genome = artificial_genome(seed)
        reference = case_dir / 'reference.fasta'
        reference.write_text(f'>SYNTHETIC_GENOME_{seed}\n{genome}\n', encoding='ascii')
        anchor_sequences = anchor_qualities = None
        anchor_mutation_positions = None
        if comparison == 'pr72_anchor':
            template = genome[2450:2500] + genome[4450:4500]
            pairs = [
                _mutate_read(template, 5, seed * 1000 + index)
                for index in range(SUPPORT)
            ]
            anchor_sequences = [pair[0] for pair in pairs]
            anchor_mutation_positions = [
                [index for index, (base, original) in enumerate(zip(seq, template))
                 if base != original]
                for seq in anchor_sequences
            ]
            anchor_qualities = [
                'I' * len(pair[0]) if '_q40_' in label else pair[1]
                for pair in pairs
            ]
            sequence = anchor_sequences[0]
            quality = anchor_qualities[0]
            reads = _write_fastq(
                case_dir / 'reads.fastq', list(zip(anchor_sequences, anchor_qualities))
            )
            expected = [2500, 4451]
            rate = 5
        elif comparison == 'negative_control':
            sequence = genome[600:700]
            quality = _quality(len(sequence), score=40)
            reads = _write_fastq(case_dir / 'reads.fastq',
                                 [(sequence, quality)] * SUPPORT)
            expected = None
        else:
            reads = _write_fastq(case_dir / 'reads.fastq',
                                 [(sequence, quality)] * SUPPORT)
            expected = list(BREAKPOINTS[seed])
        started = time.perf_counter()
        outcome = adapter.execute(
            {'reads': reads, 'reference': reference},
            output_root / label,
            {'sample_id': 'mq_' + label, 'mismatches': mismatches},
        )
        if outcome.execution != 'executed':
            raise RuntimeError(f'{label}: expected a fresh ViReMa execution')
        output = output_root / label
        evidence = json.loads((output / 'evidence.json').read_text(encoding='utf-8'))
        summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
        events = evidence.get('events', [])
        matched = next((event for event in events if expected and (
            abs(event['breakpoint_1'] - expected[0]) <= 10
            and abs(event['breakpoint_2'] - expected[1]) <= 10
        )), None)
        stdout_path = output / 'stdout.log'
        stderr_path = output / 'stderr.log'
        stdout = stdout_path.read_text(encoding='utf-8', errors='replace') if stdout_path.exists() else ''
        stderr = stderr_path.read_text(encoding='utf-8', errors='replace') if stderr_path.exists() else ''
        positions = _read(seed, rate)[3] if rate > 0 and comparison != 'pr72_anchor' else []
        if comparison == 'pr72_anchor':
            positions = anchor_mutation_positions
        rows.append({
            'label': label, 'comparison': comparison, 'genome_seed': seed,
            'read_length': READ_LENGTH, 'supporting_reads_input': SUPPORT,
            'substitution_percent': rate, 'mismatches_setting': mismatches,
            'expected_breakpoints_1based': expected,
            'read_sequence': sequence, 'read_sequence_sha256':
                hashlib.sha256(sequence.encode('ascii')).hexdigest(),
            'read_sequences': anchor_sequences,
            'read_sequence_sha256s': (
                [hashlib.sha256(value.encode('ascii')).hexdigest()
                 for value in anchor_sequences] if anchor_sequences else None
            ),
            'quality_profile': 'Q40 with Q0 at substitutions' if rate and comparison == 'combined'
                else 'Q40 continuous negative' if comparison == 'negative_control'
                else 'Q40 or original PR72 Q0-at-substitutions' if comparison == 'pr72_anchor'
                else f'Q{40 if quality[0] == "I" else 20 if quality[0] == "5" else 0}',
            'quality_string': quality,
            'quality_strings': anchor_qualities,
            'quality_sha256': hashlib.sha256(quality.encode('ascii')).hexdigest(),
            'quality_sha256s': (
                [hashlib.sha256(value.encode('ascii')).hexdigest()
                 for value in anchor_qualities] if anchor_qualities else None
            ),
            'substitution_positions_0based': positions,
            'execution': outcome.execution,
            'normalized_status': summary.get('status'),
            'event_count': len(events), 'observed_events': events,
            'matched_within_10bp': matched is not None if expected else None,
            'exact_breakpoint_match': bool(matched and
                expected and [matched['breakpoint_1'], matched['breakpoint_2']] == expected),
            'coordinate_offsets': (
                [matched['breakpoint_1'] - expected[0],
                 matched['breakpoint_2'] - expected[1]] if matched and expected else None
            ),
            'observed_support': matched['supporting_read_count'] if matched else 0,
            'extra_event_count': len(events) - int(matched is not None),
            'unknown_or_ambiguous_events': _unknown_ambiguous(stdout),
            'native_output': (
                output / 'raw' / 'Virus_Recombination_Results.txt'
            ).read_text(encoding='utf-8', errors='replace')[:4000],
            'stdout_tail': stdout[-4000:], 'stderr_tail': stderr[-4000:],
            'runtime_seconds': round(time.perf_counter() - started, 4),
            'output_bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
        })
    return {
        'schema': 'virema-mismatch-quality-investigation-v1',
        'interpretation': 'synthetic associations only; not causal or biological estimates',
        'design': {
            'conditions': len(rows), 'genome_seeds': list(GENOMES),
            'supporting_reads_per_condition': SUPPORT, 'read_length_nt': READ_LENGTH,
            'substitution_rates_percent': [0, 2, 5],
            'mismatch_values_swept': [0, 1, 2, 3],
            'quality_only_scores': [0, 20, 40],
            'truth_passed_to_caller': False, 'junction_transcript_references': 0,
        },
        'rows': rows,
        'runtime_seconds_total': round(sum(row['runtime_seconds'] for row in rows), 4),
        'output_bytes_total': sum(row['output_bytes'] for row in rows),
        'execution_errors': sum(row['execution'] == 'error' for row in rows),
    }
