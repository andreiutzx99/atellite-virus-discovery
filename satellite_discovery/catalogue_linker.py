"""Link exact supplied sequences across verified catalogue snapshots."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .observation_report import SAMPLE_COLUMNS, summarize
from .review_stage import execute, table, report
from .sequence_downloader import checksum

ARTIFACTS = {'records.csv', 'summary.json', 'catalogue.sqlite', 'sequences.fasta', 'report.html'}


def prepare(imports_file):
    imports_file = Path(imports_file).resolve()
    rows = table(imports_file, ('catalogue_dir',) + SAMPLE_COLUMNS, limit=100)
    if not rows:
        raise ValueError('Provide at least one catalogue import')
    inputs = {'imports': imports_file}
    snapshots, owners, samples, seen_paths = [], {}, {}, set()
    for index, row in enumerate(rows):
        directory = (imports_file.parent / row['catalogue_dir']).resolve()
        if directory in seen_paths:
            raise ValueError('The same catalogue directory was supplied twice')
        seen_paths.add(directory)
        manifest = directory / 'manifest.json'
        manifest_digest = checksum(manifest)
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        if not isinstance(metadata, dict):
            raise ValueError('Catalogue manifest must be an object')
        digests = metadata.get('output_sha256', {})
        identity = metadata.get('identity', {})
        if not isinstance(identity,dict) or not isinstance(digests,dict) or metadata.get('status') != 'complete' or identity.get('schema') != 'sequence-inventory-v1' or set(digests) != ARTIFACTS:
            raise ValueError('Import requires a completed sequence inventory with its full manifest')
        input_hash = identity.get('input_sha256', '')
        if not re.fullmatch(r'[a-f0-9]{64}', input_hash):
            raise ValueError('Catalogue input provenance hash is missing')
        sid = row['sample_id']
        if row['condition'] not in {'positive', 'negative', 'unknown'} or row['sample_type'] not in {'biological', 'technical_control', 'unknown'} or row['library_molecule'] not in {'RNA', 'DNA', 'mixed', 'unknown'}:
            raise ValueError('Invalid sample metadata; use the observation-report schema')
        sample = {k: row[k] for k in SAMPLE_COLUMNS}
        if sid in samples and samples[sid] != sample:
            raise ValueError('Conflicting metadata for one biological sample; resolve before linking')
        samples[sid] = sample
        if input_hash in owners and owners[input_hash] != sid:
            raise ValueError('Identical input bytes cannot establish two independent samples; review provenance')
        owners[input_hash] = sid
        inputs[f'import_{index}_manifest'] = manifest
        for name, digest in digests.items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory) or checksum(path) != digest:
                raise ValueError('Catalogue output integrity failure')
            inputs[f'import_{index}_{name}'] = path
        snapshots.append({'index': index, 'directory': directory, 'sample': sample,
                          'manifest_sha256': manifest_digest, 'input_sha256': input_hash,
                          'artifact_digests': digests})
    return inputs, snapshots, list(samples.values())


def run(imports_file, output):
    import_hash = checksum(imports_file)
    inputs, snapshots, samples = prepare(imports_file)

    def produce(paths, directory):
        if checksum(paths['imports']) != import_hash:
            raise ValueError('Import metadata changed during preparation')
        sequences, presence, records = {}, set(), []
        distinct_bases = 0
        for snapshot in snapshots:
            if checksum(paths[f"import_{snapshot['index']}_manifest"]) != snapshot['manifest_sha256'] or any(checksum(paths[f"import_{snapshot['index']}_{name}"]) != digest for name,digest in snapshot['artifact_digests'].items()):
                raise ValueError('Catalogue changed after preparation')
            source = paths[f"import_{snapshot['index']}_catalogue.sqlite"]
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
                db.execute('PRAGMA query_only=ON')
                db.execute('PRAGMA trusted_schema=OFF')
                query = 'SELECT records.record_id, records.sha256, sequences.sequence FROM records JOIN sequences ON records.sha256=sequences.sha256'
                found = db.execute(query).fetchmany(10_001)
                if len(found) > 10_000:
                    raise ValueError('Catalogue exceeds the inventory record limit')
                if db.execute('SELECT COUNT(*) FROM records').fetchone()[0] != len(found):
                    raise ValueError('Catalogue has unresolved sequence references')
                ids = set()
                for record_id, digest, sequence in found:
                    if record_id in ids or not sequence or hashlib.sha256(sequence.encode('ascii')).hexdigest() != digest:
                        raise ValueError('Invalid catalogue record or sequence hash')
                    ids.add(record_id)
                    if digest in sequences and sequences[digest] != sequence:
                        raise ValueError('Sequence hash collision')
                    if digest not in sequences:
                        distinct_bases += len(sequence)
                        sequences[digest] = sequence
                    presence.add((snapshot['sample']['sample_id'], digest))
                    records.append({'import_id': snapshot['index'], 'sample_id': snapshot['sample']['sample_id'],
                                    'record_id': record_id, 'sequence_sha256': digest,
                                    'catalogue_manifest_sha256': snapshot['manifest_sha256'],
                                    'original_fasta_sha256': snapshot['input_sha256']})
                    if len(records) > 100_000 or distinct_bases > 40_000_000:
                        raise ValueError('Link job exceeds 100,000 records or 40 million distinct bases')
        observations = [{'sample_id': sid, 'feature_id': digest, 'detection': 'present'} for sid, digest in sorted(presence)]
        if not observations or len(samples) * len(sequences) > 100_000:
            raise ValueError('Empty or oversized sample/sequence matrix')
        descriptive = summarize(samples, observations)
        temporary = directory / 'linked.building.sqlite'
        if temporary.exists():
            temporary.unlink()
        with closing(sqlite3.connect(temporary)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE samples (sample_id TEXT PRIMARY KEY, metadata_json TEXT)')
            db.execute('CREATE TABLE sequences (sha256 TEXT PRIMARY KEY, sequence TEXT)')
            db.execute('CREATE TABLE observations (sample_id TEXT REFERENCES samples(sample_id), sha256 TEXT REFERENCES sequences(sha256), PRIMARY KEY(sample_id,sha256))')
            db.execute('CREATE TABLE provenance (import_id INTEGER, record_id TEXT, sample_id TEXT, sha256 TEXT, manifest_sha256 TEXT, fasta_sha256 TEXT, PRIMARY KEY(import_id,record_id))')
            db.executemany('INSERT INTO samples VALUES (?,?)', [(s['sample_id'], json.dumps(s)) for s in samples])
            db.executemany('INSERT INTO sequences VALUES (?,?)', sorted(sequences.items()))
            db.executemany('INSERT INTO observations VALUES (?,?)', sorted(presence))
            db.executemany('INSERT INTO provenance VALUES (?,?,?,?,?,?)', [tuple(r[k] for k in ('import_id','record_id','sample_id','sequence_sha256','catalogue_manifest_sha256','original_fasta_sha256')) for r in records])
        temporary.replace(directory / 'linked.sqlite')
        files = report(directory, 'Exact cross-import sequence links', {
            'samples': samples, 'observations': observations, 'provenance': records,
            'recurrence': descriptive['recurrence']}, descriptive['limitations'] + [
                'Only exact normalized sequence identity is linked. No similarity search, consensus or reconstruction is performed.',
                'Multiple imports from the same biological sample count once per sequence. Missing sequences are unknown, not absent.',
                'Input-file identity checks detect copied exports; they cannot establish sample independence or detect all mislabeled duplicates.',
                'The samples and observations CSVs can be passed to the existing observation-report stage.'])
        return files + ['linked.sqlite']

    return execute('catalogue-linker-v1', inputs, output, __file__, produce)
