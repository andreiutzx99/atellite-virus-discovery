"""Execute fixed artificial SPAdes diagnostics using an external installation."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from satellite_discovery.artificial_spades import run

root=Path(__file__).resolve().parents[1]/'.tools'
for paired,name in ((False,'single'),(True,'paired')):
    output=root/('spades-diagnostic-'+name)
    run(output,paired)
    before=(output/'manifest.json').read_bytes()
    run(output,paired)
    assert before==(output/'manifest.json').read_bytes()
    details=json.loads((output/'diagnostic.json').read_text())
    print(json.dumps({key:details[key] for key in ('status','version','paired','input_reads','contig_count','contig_length','elapsed_seconds')}))
    print('SPAdes '+name+' fixed artificial execution and verified reuse passed')
