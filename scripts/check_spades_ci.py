"""Execute fixed artificial SPAdes diagnostics using an external installation."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from satellite_discovery.artificial_spades import run

root=Path(__file__).resolve().parents[1]/'.tools'
for paired,name in ((False,'single'),(True,'paired')):
    output=root/('spades-diagnostic-'+name)
    try:
        run(output,paired)
    except BaseException:
        for name in ('diagnostic.json','version.log','assembly.log'):
            path=output/name
            if path.is_file():
                with path.open('rb') as source:
                    source.seek(max(0,path.stat().st_size-8000))
                    print(name+': '+source.read().decode('utf-8',errors='replace'),flush=True)
        raise
    before=(output/'manifest.json').read_bytes()
    run(output,paired)
    assert before==(output/'manifest.json').read_bytes()
    details=json.loads((output/'diagnostic.json').read_text())
    print(json.dumps({key:details[key] for key in ('status','version','paired','input_reads','contig_count','contig_length','elapsed_seconds')}))
    print('SPAdes '+name+' fixed artificial execution and verified reuse passed')
