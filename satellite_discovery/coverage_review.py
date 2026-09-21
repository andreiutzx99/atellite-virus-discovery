"""Descriptive coverage from supplied zero-based, half-open alignment blocks."""
from collections import defaultdict
from pathlib import Path
import re
from .review_stage import execute, table, unique, report


def calculate(references, samples, blocks):
    refs = unique(references, 'reference_id')
    sample_ids = unique(samples, 'sample_id')
    lengths = {}
    for key, row in refs.items():
        length = int(row['length'])
        if length <= 0:
            raise ValueError('Reference lengths must be positive integers')
        lengths[key] = length
    if not refs or not samples or len(refs) * len(samples) > 100_000:
        raise ValueError('Provide references and samples; matrix limit is 100,000 cells')
    alignments = defaultdict(list)
    for row in blocks:
        if row['sample_id'] not in sample_ids or row['reference_id'] not in refs:
            raise ValueError('Unknown sample or reference in alignment blocks')
        start, end = int(row['start']), int(row['end'])
        if not 0 <= start < end <= lengths[row['reference_id']]:
            raise ValueError('Invalid zero-based half-open alignment coordinates')
        alignments[(row['sample_id'], row['reference_id'], row['alignment_id'])].append((start, end))
    events, counts = defaultdict(lambda: defaultdict(int)), defaultdict(int)
    for (sample, ref, _), intervals in alignments.items():
        # Union blocks within one alignment, so overlapping blocks do not inflate depth.
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        counts[sample, ref] += 1
        for start, end in merged:
            events[sample, ref][start] += 1
            events[sample, ref][end] -= 1
    result = []
    for sample in sorted(sample_ids):
        for ref, length in sorted(lengths.items()):
            depth = last = covered = bases = square = maximum = 0
            for position, change in sorted(events[sample, ref].items()):
                span = position - last
                bases += span * depth
                square += span * depth * depth
                covered += span if depth else 0
                maximum = max(maximum, depth if span else 0)
                depth += change
                last = position
            mean = bases / length
            result.append({'sample_id': sample, 'reference_id': ref, 'reference_length': length,
                           'alignment_count': counts[sample, ref], 'covered_bases': covered,
                           'breadth_fraction': covered / length, 'mean_block_depth': mean,
                           'depth_standard_deviation': max(0, square / length - mean * mean) ** .5,
                           'maximum_block_depth': maximum})
    return result


def run(references, samples, blocks, output):
    def produce(paths, directory):
        rows = calculate(table(paths['references'], ('reference_id', 'length')),
                         table(paths['samples'], ('sample_id',)),
                         table(paths['blocks'], ('sample_id', 'reference_id', 'alignment_id', 'start', 'end')))
        return report(directory, 'Supplied alignment coverage', {'coverage': rows}, [
            'Coordinates are zero-based and half-open. Gaps outside supplied blocks contribute zero depth.',
            'Overlapping blocks within the same alignment ID are unioned; different IDs contribute separately.',
            'Depth counts supplied alignment blocks, not molecules, fragments or independent biological support.',
            'Missing blocks mean zero only because the input sample/reference panel declares those cells assessed.',
            'Input must already define quality, duplicate, secondary-alignment and mate-overlap policies; no such filtering is inferred.'])
    return execute('coverage-review-v1', {'references': references, 'samples': samples, 'blocks': blocks}, output, __file__, produce)


def read_sam(path):
    """Read bounded text SAM, counting primary nonduplicate alignment records."""
    path = Path(path)
    if path.stat().st_size > 256_000_000:
        raise ValueError('SAM review currently supports text files up to 256 MB')
    references, blocks, skipped = {}, [], defaultdict(int)
    records_started = False
    with path.open(encoding='utf-8') as source:
        for number, line in enumerate(source, 1):
            if number > 2_000_000:
                raise ValueError('SAM exceeds the two-million-line review limit')
            fields = line.rstrip('\r\n').split('\t')
            if fields[0].startswith('@'):
                if records_started:
                    raise ValueError('SAM header appears after alignment records')
                if fields[0] == '@SQ':
                    pairs = [f.split(':',1) for f in fields[1:] if ':' in f]
                    tags = dict(pairs)
                    if len(tags) != len(pairs):
                        raise ValueError('Duplicate SAM reference header tag')
                    name, length = tags.get('SN'), int(tags.get('LN',0))
                    if not name or name in references or length <= 0:
                        raise ValueError('Invalid or duplicate SAM reference header')
                    references[name] = {'reference_id':name,'length':str(length)}
                elif fields[0] not in {'@HD','@RG','@PG','@CO'}:
                    raise ValueError('Unrecognized SAM header')
                continue
            if len(fields) < 11:
                raise ValueError('Malformed SAM alignment record')
            records_started = True
            flag = int(fields[1])
            if not 0 <= flag <= 65535:
                raise ValueError('Invalid SAM flags')
            reason = next((label for bit,label in ((4,'unmapped'),(256,'secondary'),(2048,'supplementary'),(512,'qc_failed'),(1024,'duplicate')) if flag & bit), None)
            if reason:
                skipped[reason] += 1
                continue
            ref, position, cigar = fields[2], int(fields[3])-1, fields[5]
            mapq = int(fields[4])
            if not 0 <= mapq <= 255:
                raise ValueError('Invalid SAM mapping quality')
            if ref not in references or position < 0:
                raise ValueError('Mapped SAM record lacks a declared reference or valid position')
            parts = re.findall(r'([1-9][0-9]*)([MIDNSHP=X])', cigar)
            if not parts or ''.join(n+op for n,op in parts) != cigar:
                raise ValueError('Invalid or missing mapped CIGAR')
            core = [op for _,op in parts]
            if core and core[0] == 'H': core = core[1:]
            if core and core[-1] == 'H': core = core[:-1]
            if core and core[0] == 'S': core = core[1:]
            if core and core[-1] == 'S': core = core[:-1]
            if any(op in 'HS' for op in core):
                raise ValueError('CIGAR clipping is only supported at alignment ends')
            before_blocks = len(blocks)
            query_length = 0
            for raw, operation in parts:
                size = int(raw)
                if operation in 'MIS=X':
                    query_length += size
                if operation in 'M=X':
                    blocks.append({'sample_id':'sam_sample','reference_id':ref,'alignment_id':str(number),
                                   'start':str(position),'end':str(position+size)})
                    if len(blocks) > 200_000:
                        raise ValueError('SAM review exceeds 200,000 aligned blocks')
                if operation in 'MDN=X':
                    position += size
            if position > int(references[ref]['length']):
                raise ValueError('SAM alignment extends beyond the declared reference')
            if fields[9] != '*' and len(fields[9]) != query_length:
                raise ValueError('SAM sequence length disagrees with CIGAR')
            if fields[10] != '*' and (fields[9] == '*' or len(fields[10]) != len(fields[9])):
                raise ValueError('SAM quality length disagrees with sequence')
            if len(blocks) == before_blocks:
                skipped['no_aligned_bases'] += 1
    if not references:
        raise ValueError('SAM reference lengths are required in @SQ headers')
    return list(references.values()), blocks, dict(skipped)


def run_sam(sam, output):
    def produce(paths, directory):
        references, blocks, skipped = read_sam(paths['sam'])
        rows = calculate(references,[{'sample_id':'sam_sample'}],blocks)
        return report(directory, 'Supplied SAM alignment coverage', {'coverage':rows, 'excluded_records':[{'reason':k,'records':v} for k,v in sorted(skipped.items())]},[
            'Primary mapped records are counted; unmapped, secondary, supplementary, QC-failed and duplicate-flagged records are excluded.',
            'M, = and X consume covered reference positions. Deletions and reference skips contribute no coverage; clipping and insertions do not cover reference positions.',
            'Mates are counted separately; overlapping mates can contribute depth twice. This is alignment depth, not unique molecule support.',
            'No MAPQ threshold is applied, including records with unavailable MAPQ. This report does not establish reliable biological support.',
            'sam_sample denotes one input alignment file, not an independently verified biological sample. BAM/CRAM and compressed SAM are not accepted.'])
    return execute('sam-coverage-review-v1',{'sam':sam},output,__file__,produce)
