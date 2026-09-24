"""Descriptive repeat/ambiguity measurements for supplied records, not rejection rules."""
from collections import Counter
from itertools import groupby
from pathlib import Path
from .sequence_catalogue import read_fasta
from .review_stage import execute,report

def measures(records):
    rows=[]
    for identifier,header,sequence in records:
        canonical=sum(c in 'ACGTU' for c in sequence)
        counts=Counter(sequence[i:i+2] for i in range(len(sequence)-1) if set(sequence[i:i+2])<=set('ACGTU'))
        total=sum(counts.values())
        rows.append({'record_id':identifier,'length':len(sequence),'canonical_bases':canonical,
                     'ambiguous_bases':len(sequence)-canonical,
                     'longest_identical_symbol_run':max(sum(1 for _ in group) for _,group in groupby(sequence)),
                     'distinct_called_dinucleotides':len(counts),
                     'most_frequent_dinucleotide_fraction':max(counts.values())/total if total else None,
                     'rejection_status':'not_assessed'})
    return rows

def run(fasta,output):
    def produce(paths,directory):
        rows=measures(read_fasta(paths['fasta']))
        return report(directory,'Supplied sequence quality descriptors',{'sequence_quality':rows},['Descriptive measures only; repetitive or ambiguous sequence is not automatically an artefact.','No threshold, biological classification or rejection decision is applied.','A high dinucleotide fraction does not uniquely diagnose repeats, contamination or sequencing errors.'])
    return execute('sequence-quality-v1',{'fasta':fasta,'fasta_parser':Path(__file__).with_name('sequence_catalogue.py')},output,__file__,produce)
